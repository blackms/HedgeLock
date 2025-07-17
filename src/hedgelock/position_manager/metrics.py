"""
Prometheus metrics for Position Manager.
"""

from prometheus_client import Counter, Gauge, Histogram, Info
from typing import Optional

# Service info
service_info = Info(
    'position_manager_info',
    'Position Manager service information'
)

# Position metrics
position_delta = Gauge(
    'position_manager_delta',
    'Current net delta exposure in BTC'
)

position_spot = Gauge(
    'position_manager_spot_btc',
    'Current spot BTC holdings'
)

position_long_perp = Gauge(
    'position_manager_long_perp',
    'Current long perpetual position in BTC'
)

position_short_perp = Gauge(
    'position_manager_short_perp',
    'Current short perpetual position in BTC'
)

position_hedge_ratio = Gauge(
    'position_manager_hedge_ratio',
    'Current hedge ratio (0-1)'
)

# P&L metrics
pnl_unrealized = Gauge(
    'position_manager_pnl_unrealized_usd',
    'Unrealized P&L in USD'
)

pnl_realized = Gauge(
    'position_manager_pnl_realized_usd',
    'Realized P&L in USD'
)

pnl_total = Gauge(
    'position_manager_pnl_total_usd',
    'Total P&L (realized + unrealized) in USD'
)

pnl_spot = Gauge(
    'position_manager_pnl_spot_usd',
    'Spot position P&L in USD'
)

pnl_long_perp = Gauge(
    'position_manager_pnl_long_perp_usd',
    'Long perpetual P&L in USD'
)

pnl_short_perp = Gauge(
    'position_manager_pnl_short_perp_usd',
    'Short perpetual P&L in USD'
)

pnl_funding = Gauge(
    'position_manager_pnl_funding_usd',
    'Funding P&L in USD'
)

pnl_roi = Gauge(
    'position_manager_roi_percent',
    'Return on investment percentage'
)

# Market metrics
btc_price = Gauge(
    'position_manager_btc_price_usd',
    'Current BTC price in USD'
)

volatility_24h = Gauge(
    'position_manager_volatility_24h',
    '24-hour realized volatility'
)

funding_rate = Gauge(
    'position_manager_funding_rate',
    'Current funding rate (8-hour)'
)

# Operation counters
rehedge_total = Counter(
    'position_manager_rehedge_total',
    'Total number of rehedge operations',
    ['trigger']  # manual, periodic, volatility
)

profit_take_total = Counter(
    'position_manager_profit_take_total',
    'Total number of profit taking operations',
    ['reason']  # target_reached, trailing_stop
)

emergency_close_total = Counter(
    'position_manager_emergency_close_total',
    'Total number of emergency position closures',
    ['reason']  # funding_extreme, error, manual
)

errors_total = Counter(
    'position_manager_errors_total',
    'Total number of errors',
    ['operation']  # rehedge, pnl_calc, storage, kafka
)

# Performance metrics
hedge_decision_duration = Histogram(
    'position_manager_hedge_decision_seconds',
    'Time to generate hedge decision',
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

pnl_calculation_duration = Histogram(
    'position_manager_pnl_calculation_seconds',
    'Time to calculate P&L',
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1)
)

kafka_publish_duration = Histogram(
    'position_manager_kafka_publish_seconds',
    'Time to publish message to Kafka',
    ['topic'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

storage_operation_duration = Histogram(
    'position_manager_storage_operation_seconds',
    'Time for storage operations',
    ['operation'],  # save, load, query
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25)
)

# Health metrics
health_score = Gauge(
    'position_manager_health_score',
    'Overall health score (0-100)'
)

position_balance_score = Gauge(
    'position_manager_position_balance_score',
    'Position balance health (0-100)'
)

funding_health_score = Gauge(
    'position_manager_funding_health_score',
    'Funding rate health (0-100)'
)

# Message processing
messages_processed_total = Counter(
    'position_manager_messages_processed_total',
    'Total messages processed',
    ['topic', 'status']  # success, error
)

message_processing_duration = Histogram(
    'position_manager_message_processing_seconds',
    'Time to process messages',
    ['topic'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5)
)

# API metrics
api_requests_total = Counter(
    'position_manager_api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

api_request_duration = Histogram(
    'position_manager_api_request_seconds',
    'API request duration',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)


class MetricsCollector:
    """Helper class for collecting and updating metrics."""
    
    def __init__(self):
        """Initialize metrics collector."""
        service_info.info({
            'version': '1.0.0',
            'service': 'position-manager'
        })
    
    def update_position_metrics(self, position_state):
        """Update position-related metrics."""
        position_spot.set(position_state.spot_btc)
        position_long_perp.set(position_state.long_perp)
        position_short_perp.set(position_state.short_perp)
        position_delta.set(position_state.net_delta)
        position_hedge_ratio.set(position_state.hedge_ratio)
        
        # Market metrics
        btc_price.set(position_state.btc_price)
        volatility_24h.set(position_state.volatility_24h)
        funding_rate.set(position_state.funding_rate)
    
    def update_pnl_metrics(self, pnl_breakdown, pnl_metrics):
        """Update P&L-related metrics."""
        pnl_unrealized.set(pnl_breakdown.total_unrealized_pnl)
        pnl_realized.set(pnl_breakdown.total_realized_pnl)
        pnl_total.set(pnl_breakdown.net_pnl)
        
        pnl_spot.set(pnl_breakdown.spot_pnl)
        pnl_long_perp.set(pnl_breakdown.long_perp_pnl)
        pnl_short_perp.set(pnl_breakdown.short_perp_pnl)
        pnl_funding.set(pnl_breakdown.funding_pnl)
        
        roi = pnl_metrics.get('roi_percent', 0)
        pnl_roi.set(roi)
    
    def record_rehedge(self, trigger: str = 'periodic'):
        """Record rehedge operation."""
        rehedge_total.labels(trigger=trigger).inc()
    
    def record_profit_take(self, reason: str = 'target_reached'):
        """Record profit taking operation."""
        profit_take_total.labels(reason=reason).inc()
    
    def record_emergency_close(self, reason: str = 'funding_extreme'):
        """Record emergency close operation."""
        emergency_close_total.labels(reason=reason).inc()
    
    def record_error(self, operation: str):
        """Record error occurrence."""
        errors_total.labels(operation=operation).inc()
    
    def calculate_health_scores(self, position_state, pnl_metrics) -> dict:
        """Calculate various health scores."""
        # Position balance health (how close to delta-neutral)
        delta_deviation = abs(position_state.net_delta - position_state.spot_btc)
        balance_score = max(0, 100 - (delta_deviation * 200))  # 0.5 BTC deviation = 0 score
        position_balance_score.set(balance_score)
        
        # Funding health (based on funding regime)
        funding_scores = {
            'NORMAL': 100,
            'NEUTRAL': 100,
            'HEATED': 70,
            'MANIA': 40,
            'EXTREME': 10
        }
        funding_score = funding_scores.get(position_state.funding_regime, 50)
        funding_health_score.set(funding_score)
        
        # Overall health score
        pnl_health = 100 if pnl_metrics.get('net_pnl', 0) >= 0 else 50
        overall_score = (balance_score + funding_score + pnl_health) / 3
        health_score.set(overall_score)
        
        return {
            'overall': overall_score,
            'balance': balance_score,
            'funding': funding_score,
            'pnl': pnl_health
        }
    
    def record_api_request(self, method: str, endpoint: str, status: int, duration: float):
        """Record API request metrics."""
        api_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=str(status)
        ).inc()
        
        api_request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def record_message_processed(self, topic: str, success: bool, duration: float):
        """Record message processing metrics."""
        status = 'success' if success else 'error'
        messages_processed_total.labels(topic=topic, status=status).inc()
        message_processing_duration.labels(topic=topic).observe(duration)


# Global metrics collector instance
metrics_collector = MetricsCollector()