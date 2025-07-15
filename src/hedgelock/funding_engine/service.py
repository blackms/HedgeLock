"""
Funding Engine service - processes funding rates and manages funding context.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import uuid

from ..shared.funding_models import (
    FundingRate, FundingSnapshot, FundingContext,
    FundingDecision, FundingAlert, FundingRegime,
    FundingRateMessage, FundingContextMessage
)
from ..shared.funding_calculator import FundingCalculator
from .config import FundingEngineConfig
from .kafka_config import FundingEngineConsumer, FundingEngineProducer
from .storage import FundingStorage

logger = logging.getLogger(__name__)


class FundingEngineService:
    """
    Main service for processing funding rates and generating funding context.
    
    Responsibilities:
    - Consume funding rate messages from Kafka
    - Store funding rate history
    - Detect funding regimes
    - Calculate position multipliers
    - Generate funding context for other services
    - Trigger alerts for extreme conditions
    """
    
    def __init__(self, config: Optional[FundingEngineConfig] = None):
        self.config = config or FundingEngineConfig()
        self.consumer = FundingEngineConsumer(self.config)
        self.producer = FundingEngineProducer(self.config)
        self.storage = FundingStorage(self.config)
        
        # Track current contexts by symbol
        self.current_contexts: Dict[str, FundingContext] = {}
        self.previous_regimes: Dict[str, FundingRegime] = {}
        
        # Service state
        self.running = False
        self.tasks = []
        
    async def start(self):
        """Start the funding engine service."""
        logger.info("Starting Funding Engine service...")
        
        # Start Kafka components
        await self.consumer.start()
        await self.producer.start()
        
        # Start background tasks
        self.running = True
        self.tasks = [
            asyncio.create_task(self.process_funding_rates()),
            asyncio.create_task(self.periodic_context_update())
        ]
        
        logger.info("Funding Engine service started")
        
    async def stop(self):
        """Stop the funding engine service."""
        logger.info("Stopping Funding Engine service...")
        
        self.running = False
        
        # Cancel tasks
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Stop Kafka components
        await self.consumer.stop()
        await self.producer.stop()
        
        logger.info("Funding Engine service stopped")
        
    async def process_funding_rates(self):
        """Main loop for processing funding rate messages."""
        while self.running:
            try:
                async for funding_msg in self.consumer.consume_messages():
                    await self._handle_funding_rate(funding_msg)
            except Exception as e:
                logger.error(f"Error in funding rate processing: {e}")
                await asyncio.sleep(5)  # Brief pause before retry
                
    async def _handle_funding_rate(self, msg: FundingRateMessage):
        """Handle a single funding rate message."""
        try:
            rate = msg.funding_rate
            logger.info(
                f"Processing funding rate for {rate.symbol}: "
                f"{rate.annualized_rate:.2f}% APR"
            )
            
            # Store the rate
            self.storage.store_funding_rate(rate)
            
            # Create funding snapshot
            snapshot = await self._create_funding_snapshot(rate.symbol)
            
            # Calculate funding context
            previous_regime = self.previous_regimes.get(rate.symbol)
            context = FundingCalculator.calculate_funding_context(
                snapshot,
                previous_regime
            )
            
            # Store current regime
            self.previous_regimes[rate.symbol] = context.current_regime
            self.storage.store_funding_regime(rate.symbol, context.current_regime)
            
            # Generate funding decision
            decision = self._generate_funding_decision(context)
            
            # Send funding context message
            context_msg = FundingContextMessage(
                service=self.config.service_name,
                funding_context=context,
                funding_decision=decision,
                trace_id=msg.trace_id or str(uuid.uuid4())
            )
            await self.producer.send_funding_context(context_msg)
            
            # Update current context
            self.current_contexts[rate.symbol] = context
            
            # Check for alerts
            await self._check_funding_alerts(context, previous_regime)
            
        except Exception as e:
            logger.error(f"Error handling funding rate: {e}")
            
    async def _create_funding_snapshot(self, symbol: str) -> FundingSnapshot:
        """Create a funding snapshot with historical data."""
        # Get current rate
        current_rate = self.storage.get_current_funding_rate(symbol)
        if not current_rate:
            raise ValueError(f"No current funding rate for {symbol}")
            
        # Get historical rates
        rates_24h = self.storage.get_funding_history(symbol, hours=24)
        rates_7d = self.storage.get_funding_history(symbol, hours=168)
        
        return FundingSnapshot(
            symbol=symbol,
            current_rate=current_rate,
            rates_24h=rates_24h,
            rates_7d=rates_7d
        )
        
    def _generate_funding_decision(self, context: FundingContext) -> FundingDecision:
        """Generate funding decision based on context."""
        # Calculate risk score
        risk_score = FundingCalculator.calculate_funding_risk_score(context)
        
        # Get recommended action
        action, reason = FundingCalculator.recommend_action(context)
        
        # Determine urgency
        if context.should_exit:
            urgency = "critical"
        elif context.current_regime in [FundingRegime.MANIA, FundingRegime.EXTREME]:
            urgency = "high"
        elif context.regime_change:
            urgency = "medium"
        else:
            urgency = "low"
            
        # Calculate projected costs
        # Assume $100k position for projection
        position_size = 100000
        current_rate_8h = context.current_rate / 100 / 365 / 3
        projected_cost_24h = FundingCalculator.project_funding_cost(
            position_size,
            current_rate_8h,
            periods=3
        )
        
        # Determine position adjustment
        if action == "exit_all":
            position_adjustment = 0.0
        elif action == "reduce_position":
            position_adjustment = context.position_multiplier
        elif action == "increase_position":
            position_adjustment = min(context.position_multiplier * 1.5, 1.0)
        else:
            position_adjustment = context.position_multiplier
            
        # Max position size based on regime
        regime_limits = {
            FundingRegime.NEUTRAL: 2.0,
            FundingRegime.NORMAL: 1.5,
            FundingRegime.HEATED: 1.0,
            FundingRegime.MANIA: 0.5,
            FundingRegime.EXTREME: 0.0
        }
        max_position = regime_limits.get(context.current_regime, 1.0)
        
        return FundingDecision(
            context=context,
            action=action,
            position_adjustment=position_adjustment,
            max_position_size=max_position,
            reason=reason,
            urgency=urgency,
            funding_risk_score=risk_score,
            projected_cost_24h=projected_cost_24h,
            trace_id=context.trace_id
        )
        
    async def _check_funding_alerts(
        self,
        context: FundingContext,
        previous_regime: Optional[FundingRegime]
    ):
        """Check for funding-related alerts."""
        alerts = []
        
        # Emergency alert for extreme funding
        if context.should_exit:
            alert = FundingAlert(
                alert_type="emergency",
                severity="critical",
                symbol=context.symbol,
                current_regime=context.current_regime,
                current_rate=context.current_rate,
                threshold_breached=self.config.emergency_exit_threshold,
                title=f"EMERGENCY: Extreme Funding Rate on {context.symbol}",
                message=(
                    f"Funding rate has reached {context.current_rate:.1f}% APR. "
                    "Exit all positions immediately!"
                ),
                recommended_action="exit_all",
                trace_id=context.trace_id
            )
            alerts.append(alert)
            
        # Regime change alert
        elif context.regime_change and previous_regime:
            severity = "warning"
            if context.current_regime in [FundingRegime.MANIA, FundingRegime.EXTREME]:
                severity = "critical"
            elif context.current_regime == FundingRegime.HEATED:
                severity = "high"
                
            alert = FundingAlert(
                alert_type="regime_change",
                severity=severity,
                symbol=context.symbol,
                current_regime=context.current_regime,
                previous_regime=previous_regime,
                current_rate=context.current_rate,
                title=f"Funding Regime Change: {context.symbol}",
                message=(
                    f"Funding regime changed from {previous_regime.value} "
                    f"to {context.current_regime.value} ({context.current_rate:.1f}% APR)"
                ),
                recommended_action="adjust_position",
                trace_id=context.trace_id
            )
            alerts.append(alert)
            
        # High funding rate alert
        elif context.current_rate > 100 and context.current_regime != FundingRegime.EXTREME:
            alert = FundingAlert(
                alert_type="high_funding",
                severity="warning",
                symbol=context.symbol,
                current_regime=context.current_regime,
                current_rate=context.current_rate,
                threshold_breached=100.0,
                title=f"High Funding Rate: {context.symbol}",
                message=(
                    f"Funding rate is {context.current_rate:.1f}% APR. "
                    "Consider reducing position size."
                ),
                recommended_action="reduce_position",
                trace_id=context.trace_id
            )
            alerts.append(alert)
            
        # Log alerts (in production, send to alerting system)
        for alert in alerts:
            logger.warning(f"FUNDING ALERT: {alert.title} - {alert.message}")
            
    async def periodic_context_update(self):
        """Periodically update funding context for all symbols."""
        while self.running:
            try:
                await asyncio.sleep(self.config.regime_update_interval_seconds)
                
                # Update context for all tracked symbols
                for symbol in list(self.current_contexts.keys()):
                    try:
                        snapshot = await self._create_funding_snapshot(symbol)
                        previous_regime = self.previous_regimes.get(symbol)
                        
                        context = FundingCalculator.calculate_funding_context(
                            snapshot,
                            previous_regime
                        )
                        
                        # Only send update if regime changed or significant rate change
                        old_context = self.current_contexts.get(symbol)
                        if (old_context and 
                            (context.current_regime != old_context.current_regime or
                             abs(context.current_rate - old_context.current_rate) > 5.0)):
                            
                            decision = self._generate_funding_decision(context)
                            
                            context_msg = FundingContextMessage(
                                service=self.config.service_name,
                                funding_context=context,
                                funding_decision=decision,
                                trace_id=str(uuid.uuid4())
                            )
                            await self.producer.send_funding_context(context_msg)
                            
                            self.current_contexts[symbol] = context
                            self.previous_regimes[symbol] = context.current_regime
                            
                    except Exception as e:
                        logger.error(f"Error updating context for {symbol}: {e}")
                        
            except Exception as e:
                logger.error(f"Error in periodic context update: {e}")
                
    def get_funding_status(self) -> Dict:
        """Get current funding status for all symbols."""
        status = {
            "service": self.config.service_name,
            "running": self.running,
            "symbols_tracked": len(self.current_contexts),
            "contexts": {}
        }
        
        for symbol, context in self.current_contexts.items():
            status["contexts"][symbol] = {
                "regime": context.current_regime.value,
                "current_rate": f"{context.current_rate:.2f}%",
                "position_multiplier": context.position_multiplier,
                "should_exit": context.should_exit,
                "daily_cost_bps": context.daily_cost_bps,
                "weekly_cost_pct": context.weekly_cost_pct
            }
            
        return status