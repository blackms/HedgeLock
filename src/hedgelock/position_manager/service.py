"""
Position Manager service for delta-neutral trading.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from .manager import DeltaNeutralManager
from .models import PositionState, MarketRegime
from .storage import create_storage, PositionStorage
from .pnl_calculator import PnLCalculator
from .metrics import (
    metrics_collector, hedge_decision_duration, 
    pnl_calculation_duration, kafka_publish_duration,
    storage_operation_duration
)

logger = logging.getLogger(__name__)


class PositionManagerService:
    """Service for managing delta-neutral positions."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.manager = DeltaNeutralManager()
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.running = False
        
        # Initialize storage
        storage_type = config.get('storage_type', 'redis')
        storage_url = config.get('storage_url', 'redis://localhost:6379')
        self.storage: Optional[PositionStorage] = create_storage(storage_type, storage_url)
        
        # Initialize P&L calculator
        self.pnl_calculator = PnLCalculator()
        
        # Track positions
        self.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            market_regime=MarketRegime.NEUTRAL
        )
    
    async def start(self):
        """Start the service."""
        logger.info("Starting Position Manager service...")
        
        # Try to recover previous state
        await self.recover_state()
        
        # Initialize Kafka
        self.consumer = AIOKafkaConsumer(
            'funding_context',  # Listen to funding updates
            'market_data',      # Listen to price updates
            bootstrap_servers=self.config['kafka_servers'],
            group_id='position-manager-group',
            value_deserializer=lambda v: json.loads(v.decode('utf-8'))
        )
        
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await self.consumer.start()
        await self.producer.start()
        
        self.running = True
        
        # Start processing loops
        await asyncio.gather(
            self.process_messages(),
            self.periodic_rehedge(),
            self.periodic_state_save(),
            self.hourly_volatility_update()
        )
    
    async def process_messages(self):
        """Process incoming messages."""
        async for msg in self.consumer:
            if not self.running:
                break
                
            try:
                start_time = datetime.utcnow()
                
                if msg.topic == 'funding_context':
                    await self.handle_funding_update(msg.value)
                elif msg.topic == 'market_data':
                    await self.handle_price_update(msg.value)
                
                # Record successful processing
                duration = (datetime.utcnow() - start_time).total_seconds()
                metrics_collector.record_message_processed(msg.topic, True, duration)
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                metrics_collector.record_error('message_processing')
                metrics_collector.record_message_processed(msg.topic, False, 0)
    
    async def handle_funding_update(self, data: Dict):
        """Handle funding context updates."""
        funding_context = data.get('funding_context', {})
        
        # Update position state with funding info
        self.current_position.funding_regime = funding_context.get(
            'current_regime', 'NORMAL'
        )
        self.current_position.funding_rate = funding_context.get(
            'current_rate', 0) / 100 / 365 / 3  # Convert to 8h rate
        
        # Check if we need to adjust positions due to funding
        if funding_context.get('should_exit', False):
            logger.warning("Emergency exit triggered by funding!")
            await self.emergency_close_positions()
    
    async def handle_price_update(self, data: Dict):
        """Handle price updates."""
        # Update price in position state
        price = data.get('price', self.current_position.btc_price)
        self.current_position.btc_price = price
        
        # Add to price history for volatility calculation
        self.manager.price_history.append(price)
        # Keep last 24 hours of hourly prices
        if len(self.manager.price_history) > 24:
            self.manager.price_history.pop(0)
        
        # Recalculate volatility
        if len(self.manager.price_history) >= 2:
            self.current_position.volatility_24h = self.manager.calculate_volatility_24h(
                self.manager.price_history
            )
        
        # Update P&L on price change
        await self.update_pnl_and_publish()
    
    async def periodic_rehedge(self):
        """Periodically check and adjust hedges."""
        while self.running:
            try:
                if self.manager.should_rehedge():
                    await self.rehedge_positions()
                
                # Check profit targets
                if self.manager.check_profit_targets(self.current_position):
                    await self.take_profit()
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in rehedge loop: {e}")
    
    async def rehedge_positions(self):
        """Rehedge positions based on current market conditions."""
        logger.info("Rehedging positions...")
        
        # Generate hedge decision with timing
        with hedge_decision_duration.time():
            decision = self.manager.generate_hedge_decision(
                self.current_position,
                target_delta=0.0  # Target delta-neutral
            )
        
        # Send orders via trade executor
        if abs(decision.adjust_long) > 0.001 or abs(decision.adjust_short) > 0.001:
            # Calculate net adjustment (for perpetual futures)
            net_adjustment = decision.adjust_long + decision.adjust_short
            
            if abs(net_adjustment) > 0.001:
                # Create hedge trade message in expected format
                hedge_trade_msg = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'service': 'position-manager',
                    'hedge_decision': {
                        'timestamp': decision.timestamp.isoformat(),
                        'risk_state': 'NORMAL',  # From position state
                        'current_delta': self.manager.calculate_delta(self.current_position),
                        'target_delta': 0.0,
                        'hedge_size': abs(net_adjustment),
                        'side': 'Buy' if net_adjustment > 0 else 'Sell',
                        'reason': decision.reason,
                        'urgency': 'NORMAL',
                        'funding_adjusted': True,
                        'funding_regime': self.current_position.funding_regime,
                        'position_multiplier': decision.target_hedge_ratio
                    },
                    'order_request': {
                        'category': 'inverse',  # BTC perpetual
                        'symbol': 'BTCUSDT',
                        'side': 'Buy' if net_adjustment > 0 else 'Sell',
                        'orderType': 'Market',
                        'qty': str(abs(net_adjustment)),
                        'timeInForce': 'IOC'
                    },
                    'risk_state': 'NORMAL',
                    'ltv': 0.5,  # TODO: Get from risk engine
                    'risk_score': 0.5,
                    'funding_context': {
                        'current_regime': self.current_position.funding_regime,
                        'multiplier': decision.target_hedge_ratio
                    },
                    'trace_id': f'pm-{datetime.utcnow().timestamp()}'
                }
                
                with kafka_publish_duration.labels(topic='hedge_trades').time():
                    await self.producer.send_and_wait(
                        'hedge_trades',
                        value=hedge_trade_msg
                    )
                
                # Update P&L calculator with new positions
                old_long = self.current_position.long_perp
                old_short = self.current_position.short_perp
                
                # Update positions based on adjustments
                self.current_position.long_perp += decision.adjust_long
                self.current_position.short_perp += decision.adjust_short
                
                # Track entry prices for P&L calculation
                if decision.adjust_long != 0:
                    self.pnl_calculator.update_entry_prices(
                        'long_perp', self.current_position.btc_price,
                        old_long, self.current_position.long_perp
                    )
                if decision.adjust_short != 0:
                    self.pnl_calculator.update_entry_prices(
                        'short_perp', self.current_position.btc_price,
                        old_short, self.current_position.short_perp
                    )
        
        # Update state
        self.current_position.hedge_ratio = decision.target_hedge_ratio
        self.manager.last_hedge_update = datetime.utcnow()
        
        # Update P&L after position changes
        await self.update_pnl_and_publish()
        
        # Publish position state
        with kafka_publish_duration.labels(topic='position_states').time():
            await self.producer.send_and_wait(
                'position_states',
                value={
                    'timestamp': datetime.utcnow().isoformat(),
                    'position_state': self.current_position.model_dump()
                }
            )
        
        # Save state after rehedge
        await self.save_state_after_update()
        
        # Record rehedge metric
        metrics_collector.record_rehedge('periodic')
    
    async def take_profit(self):
        """Execute profit taking logic."""
        logger.info("Taking profit on positions...")
        
        # Calculate position to close
        total_position = self.current_position.long_perp - self.current_position.short_perp
        
        if abs(total_position) > 0.001:
            # Send close order via trade executor
            hedge_trade_msg = {
                'timestamp': datetime.utcnow().isoformat(),
                'service': 'position-manager',
                'hedge_decision': {
                    'timestamp': datetime.utcnow().isoformat(),
                    'risk_state': 'TAKING_PROFIT',
                    'current_delta': self.manager.calculate_delta(self.current_position),
                    'target_delta': self.current_position.spot_btc,  # Return to spot only
                    'hedge_size': abs(total_position),
                    'side': 'Sell' if total_position > 0 else 'Buy',
                    'reason': 'Profit target reached',
                    'urgency': 'HIGH',
                    'funding_adjusted': False,
                    'funding_regime': self.current_position.funding_regime,
                    'position_multiplier': 0.0
                },
                'order_request': {
                    'category': 'inverse',
                    'symbol': 'BTCUSDT',
                    'side': 'Sell' if total_position > 0 else 'Buy',
                    'orderType': 'Market',
                    'qty': str(abs(total_position)),
                    'timeInForce': 'IOC'
                },
                'risk_state': 'TAKING_PROFIT',
                'ltv': 0.5,
                'risk_score': 0.0,
                'trace_id': f'pm-profit-{datetime.utcnow().timestamp()}'
            }
            
            await self.producer.send_and_wait('hedge_trades', value=hedge_trade_msg)
            
            # Realize P&L from closed positions
            closed_positions = {
                'long_perp': self.current_position.long_perp if self.current_position.long_perp > 0 else 0,
                'short_perp': self.current_position.short_perp if self.current_position.short_perp > 0 else 0
            }
            realized_pnl = self.pnl_calculator.realize_pnl(
                closed_positions, 
                self.current_position.btc_price
            )
        
        # Update P&L before sending profit taking event
        await self.update_pnl_and_publish()
        
        # Also send profit taking event
        await self.producer.send_and_wait(
            'profit_taking',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'position_state': self.current_position.model_dump(),
                'action': 'TAKE_PROFIT',
                'pnl': self.current_position.unrealized_pnl,
                'realized_pnl': self.current_position.realized_pnl,
                'total_realized': self.pnl_calculator.cumulative_realized_pnl
            }
        )
        
        # Reset position state
        self.current_position.market_regime = MarketRegime.TAKING_PROFIT
        self.current_position.long_perp = 0.0
        self.current_position.short_perp = 0.0
        
        # Save state after profit taking
        await self.save_state_after_update()
        
        # Record profit taking metric
        reason = 'trailing_stop' if self.current_position.unrealized_pnl < self.current_position.peak_pnl * 0.7 else 'target_reached'
        metrics_collector.record_profit_take(reason)
    
    async def emergency_close_positions(self):
        """Emergency close all positions."""
        logger.error("EMERGENCY: Closing all positions!")
        
        # Calculate total position to close
        total_position = self.current_position.long_perp - self.current_position.short_perp
        
        if abs(total_position) > 0.001:
            # Send emergency close order
            hedge_trade_msg = {
                'timestamp': datetime.utcnow().isoformat(),
                'service': 'position-manager',
                'hedge_decision': {
                    'timestamp': datetime.utcnow().isoformat(),
                    'risk_state': 'EMERGENCY',
                    'current_delta': self.manager.calculate_delta(self.current_position),
                    'target_delta': self.current_position.spot_btc,
                    'hedge_size': abs(total_position),
                    'side': 'Sell' if total_position > 0 else 'Buy',
                    'reason': 'EMERGENCY: Extreme funding rate',
                    'urgency': 'CRITICAL',
                    'funding_adjusted': True,
                    'funding_regime': 'EXTREME',
                    'position_multiplier': 0.0
                },
                'order_request': {
                    'category': 'inverse',
                    'symbol': 'BTCUSDT',
                    'side': 'Sell' if total_position > 0 else 'Buy',
                    'orderType': 'Market',
                    'qty': str(abs(total_position)),
                    'timeInForce': 'IOC'
                },
                'risk_state': 'EMERGENCY',
                'ltv': 0.9,  # High risk
                'risk_score': 1.0,
                'trace_id': f'pm-emergency-{datetime.utcnow().timestamp()}'
            }
            
            await self.producer.send_and_wait('hedge_trades', value=hedge_trade_msg)
        
        # Send emergency action event
        await self.producer.send_and_wait(
            'emergency_actions',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'action': 'CLOSE_ALL',
                'reason': 'Extreme funding rate',
                'position_state': self.current_position.model_dump()
            }
        )
        
        # Update state
        self.current_position.long_perp = 0.0
        self.current_position.short_perp = 0.0
        self.current_position.net_delta = self.current_position.spot_btc
        
        # Save state after emergency close
        await self.save_state_after_update()
        
        # Record emergency close metric
        metrics_collector.record_emergency_close('funding_extreme')
    
    async def stop(self):
        """Stop the service."""
        logger.info("Stopping Position Manager service...")
        self.running = False
        
        # Save final state before stopping
        if self.storage:
            await self.storage.save_state(self.current_position)
        
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
    
    async def recover_state(self):
        """Recover position state from storage on startup."""
        if not self.storage:
            logger.warning("No storage configured, starting with default state")
            return
            
        try:
            saved_state = await self.storage.get_latest_state()
            if saved_state:
                self.current_position = saved_state
                logger.info(f"Recovered position state: delta={saved_state.net_delta:.4f}, "
                           f"long={saved_state.long_perp:.4f}, short={saved_state.short_perp:.4f}")
                
                # Load recent price history for volatility calculation
                history = await self.storage.get_state_history(hours=24)
                if history:
                    self.manager.price_history = [state.btc_price for state in history]
                    logger.info(f"Loaded {len(history)} historical price points")
            else:
                logger.info("No saved state found, starting with default state")
                
        except Exception as e:
            logger.error(f"Failed to recover state: {e}")
            logger.info("Starting with default state")
    
    async def periodic_state_save(self):
        """Periodically save position state to storage."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Save every minute
                
                if self.storage:
                    success = await self.storage.save_state(self.current_position)
                    if not success:
                        logger.warning("Failed to save position state")
                        
                    # Clean up old states periodically (every hour)
                    if datetime.utcnow().minute == 0:
                        deleted = await self.storage.delete_old_states(days=7)
                        logger.info(f"Cleaned up {deleted} old position states")
                        
            except Exception as e:
                logger.error(f"Error in periodic state save: {e}")
                
    async def save_state_after_update(self):
        """Save state after significant updates."""
        if self.storage:
            try:
                with storage_operation_duration.labels(operation='save').time():
                    await self.storage.save_state(self.current_position)
            except Exception as e:
                logger.error(f"Failed to save state after update: {e}")
                metrics_collector.record_error('storage')
    
    async def hourly_volatility_update(self):
        """Recalculate volatility every hour using historical data."""
        while self.running:
            try:
                # Wait for the next hour
                now = datetime.utcnow()
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                wait_seconds = (next_hour - now).total_seconds()
                
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                
                if not self.running:
                    break
                
                # Get 24-hour price history from storage
                if self.storage:
                    history = await self.storage.get_state_history(hours=24)
                    if len(history) >= 2:
                        prices = [state.btc_price for state in history]
                        
                        # Recalculate volatility
                        new_volatility = self.manager.calculate_volatility_24h(prices)
                        old_volatility = self.current_position.volatility_24h
                        
                        self.current_position.volatility_24h = new_volatility
                        logger.info(f"Updated 24h volatility: {old_volatility:.2%} -> {new_volatility:.2%}")
                        
                        # Check if we need to rehedge due to volatility change
                        volatility_change = abs(new_volatility - old_volatility) / old_volatility
                        if volatility_change > 0.2:  # 20% change in volatility
                            logger.info(f"Significant volatility change ({volatility_change:.1%}), triggering rehedge")
                            await self.rehedge_positions()
                        
                        # Save updated state
                        await self.save_state_after_update()
                else:
                    logger.debug("No storage configured, using price history buffer for volatility")
                    if len(self.manager.price_history) >= 2:
                        new_volatility = self.manager.calculate_volatility_24h(self.manager.price_history)
                        self.current_position.volatility_24h = new_volatility
                
            except Exception as e:
                logger.error(f"Error in hourly volatility update: {e}")
                # Wait an hour before retrying
                await asyncio.sleep(3600)
    
    async def update_pnl_and_publish(self):
        """Update P&L calculations and publish to Kafka."""
        try:
            # Calculate current P&L with timing
            with pnl_calculation_duration.time():
                pnl_breakdown = self.pnl_calculator.calculate_pnl(self.current_position)
            
            # Update position state with latest P&L
            self.current_position.unrealized_pnl = pnl_breakdown.total_unrealized_pnl
            self.current_position.realized_pnl = pnl_breakdown.total_realized_pnl
            
            # Get comprehensive metrics
            pnl_metrics = self.pnl_calculator.get_pnl_metrics(self.current_position)
            
            # Update Prometheus metrics
            metrics_collector.update_position_metrics(self.current_position)
            metrics_collector.update_pnl_metrics(pnl_breakdown, pnl_metrics)
            metrics_collector.calculate_health_scores(self.current_position, pnl_metrics)
            
            # Publish P&L update to Kafka
            if self.producer:
                pnl_message = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'position_state': self.current_position.model_dump(),
                    'pnl_breakdown': {
                        'spot_pnl': pnl_breakdown.spot_pnl,
                        'long_perp_pnl': pnl_breakdown.long_perp_pnl,
                        'short_perp_pnl': pnl_breakdown.short_perp_pnl,
                        'funding_pnl': pnl_breakdown.funding_pnl,
                        'unrealized_pnl': pnl_breakdown.total_unrealized_pnl,
                        'realized_pnl': pnl_breakdown.total_realized_pnl,
                        'net_pnl': pnl_breakdown.net_pnl
                    },
                    'metrics': pnl_metrics,
                    'trace_id': f'pnl-{datetime.utcnow().timestamp()}'
                }
                
                with kafka_publish_duration.labels(topic='pnl_updates').time():
                    await self.producer.send_and_wait(
                        'pnl_updates',
                        value=pnl_message
                    )
                
                # Log significant P&L changes
                if abs(pnl_breakdown.net_pnl) > 100:  # Log if P&L > $100
                    logger.info(f"P&L Update: Net=${pnl_breakdown.net_pnl:.2f}, "
                               f"Unrealized=${pnl_breakdown.total_unrealized_pnl:.2f}, "
                               f"Realized=${pnl_breakdown.total_realized_pnl:.2f}")
                    
        except Exception as e:
            logger.error(f"Error updating P&L: {e}")