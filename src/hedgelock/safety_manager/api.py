"""
Safety Manager API endpoints.
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from .service import SafetyManagerService
from .models import EmergencyAction, RiskLevel

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="HedgeLock Safety Manager")

# Global service instance
safety_service: Optional[SafetyManagerService] = None


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    global safety_service
    
    logger.info("Starting Safety Manager API...")
    
    # Configure service
    config = {
        'kafka_servers': 'kafka:29092',
        'safety_config': {
            'min_distance_to_liquidation': 0.10,
            'panic_equity_drop': 0.10,
            'daily_loss_limit': 1000.0,
            'funding_cost_limit': 100.0,
            'volatility_limit': 0.10,
            'consecutive_loss_days_limit': 3,
            'heartbeat_timeout_minutes': 60,
            'max_position_value': 50000.0,
            'max_leverage': 25.0,
            'auto_deleverage_enabled': True,
            'auto_close_on_panic': True,
            'halt_on_circuit_breaker': True
        }
    }
    
    # Create and start service
    safety_service = SafetyManagerService(config)
    import asyncio
    asyncio.create_task(safety_service.start())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global safety_service
    
    if safety_service:
        await safety_service.stop()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Safety Manager",
        "version": "1.0.0",
        "status": "active",
        "description": "System safety monitoring and protection for HedgeLock"
    }


@app.get("/status")
async def get_status():
    """Get service status and current state."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    state = safety_service.get_current_state()
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "service": "safety-manager",
        "status": "active" if safety_service.running else "inactive",
        "current_state": state
    }


@app.get("/safety/state")
async def get_safety_state():
    """Get current safety state."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    state = safety_service.safety_manager.safety_state
    
    return {
        "timestamp": state.timestamp.isoformat(),
        "risk_level": state.current_risk_level.value,
        "metrics": {
            "distance_to_liquidation": state.distance_to_liquidation,
            "net_equity_drop": state.net_equity_drop,
            "daily_loss": state.daily_loss,
            "leverage_ratio": state.leverage_ratio,
            "total_position_value": state.total_position_value
        },
        "circuit_breakers": {
            "active": state.circuit_breakers_active,
            "count": len(state.circuit_breakers_active)
        },
        "services": state.services_healthy
    }


@app.get("/safety/metrics")
async def get_safety_metrics():
    """Get comprehensive safety metrics."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    metrics = safety_service.safety_manager.get_safety_metrics()
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics
    }


@app.get("/liquidation/risk")
async def get_liquidation_risk():
    """Get current liquidation risk assessment."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Get latest liquidation risk
    if safety_service.safety_manager.liquidation_history:
        latest = safety_service.safety_manager.liquidation_history[-1]
        
        return {
            "timestamp": latest.timestamp.isoformat(),
            "current_price": latest.current_price,
            "liquidation_prices": {
                "long": latest.liquidation_price_long,
                "short": latest.liquidation_price_short
            },
            "distances": {
                "long_percent": latest.distance_percent_long,
                "short_percent": latest.distance_percent_short,
                "minimum": latest.min_distance_percent
            },
            "risk_level": latest.risk_level.value,
            "recommended_action": latest.recommended_action.value if latest.recommended_action else None
        }
    else:
        raise HTTPException(status_code=404, detail="No liquidation risk data available")


@app.get("/circuit-breakers")
async def get_circuit_breakers():
    """Get circuit breaker states."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    breakers = {}
    for name, cb in safety_service.safety_manager.circuit_breakers.items():
        breakers[name] = {
            "description": cb.description,
            "is_active": cb.is_active,
            "threshold": cb.threshold,
            "last_value": cb.last_value,
            "triggered_at": cb.triggered_at.isoformat() if cb.triggered_at else None,
            "trigger_count": cb.trigger_count,
            "cooldown_minutes": cb.cooldown_minutes
        }
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "circuit_breakers": breakers,
        "active_count": sum(1 for cb in breakers.values() if cb["is_active"])
    }


@app.get("/risk-limits")
async def get_risk_limits():
    """Get risk limit states."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    limits = {}
    for name, limit in safety_service.safety_manager.risk_limits.items():
        limits[name] = {
            "description": limit.description,
            "limit_type": limit.limit_type,
            "limit_value": limit.limit_value,
            "current_value": limit.current_value,
            "breach_percent": limit.breach_percent(),
            "is_breached": limit.is_breached(),
            "action_on_breach": limit.action_on_breach.value,
            "severity": limit.severity.value
        }
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "risk_limits": limits,
        "breached_count": sum(1 for limit in limits.values() if limit["is_breached"])
    }


@app.get("/system-health")
async def get_system_health():
    """Get system health status."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    health = safety_service.safety_manager.system_health
    
    return {
        "timestamp": health.timestamp.isoformat(),
        "services": health.services,
        "unhealthy_services": health.get_unhealthy_services(),
        "dead_mans_switch": {
            "last_activity": health.last_activity.isoformat(),
            "timeout_minutes": health.activity_timeout_minutes,
            "is_triggered": health.is_dead_mans_switch_triggered(),
            "manual_override": health.manual_override_active
        },
        "dependencies": {
            "kafka": health.kafka_healthy,
            "redis": health.redis_healthy,
            "postgres": health.postgres_healthy
        }
    }


@app.get("/alerts/active")
async def get_active_alerts():
    """Get active (unacknowledged) alerts."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    active_alerts = [
        alert for alert in safety_service.safety_manager.alert_history
        if not alert.acknowledged and not alert.resolved
    ]
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(active_alerts),
        "alerts": [
            {
                "alert_id": alert.alert_id,
                "timestamp": alert.timestamp.isoformat(),
                "type": alert.alert_type,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "recommended_actions": [a.value for a in alert.recommended_actions]
            }
            for alert in active_alerts[-20:]  # Last 20 alerts
        ]
    }


@app.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, acknowledged_by: str = "operator"):
    """Acknowledge an alert."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Find alert
    alert = None
    for a in safety_service.safety_manager.alert_history:
        if a.alert_id == alert_id:
            alert = a
            break
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Acknowledge
    alert.acknowledged = True
    alert.acknowledged_by = acknowledged_by
    alert.acknowledged_at = datetime.utcnow()
    
    return {
        "status": "acknowledged",
        "alert_id": alert_id,
        "acknowledged_at": alert.acknowledged_at.isoformat()
    }


@app.get("/emergency-actions/history")
async def get_emergency_action_history(limit: int = 20):
    """Get emergency action history."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    actions = safety_service.safety_manager.action_history[-limit:]
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(actions),
        "actions": [
            {
                "timestamp": action.timestamp.isoformat(),
                "action": action.action.value,
                "reason": action.reason,
                "triggered_by": action.triggered_by,
                "risk_level_before": action.risk_level_before.value,
                "risk_level_after": action.risk_level_after.value if action.risk_level_after else None,
                "success": action.success,
                "positions_affected": action.positions_affected,
                "value_affected": action.value_affected
            }
            for action in actions
        ]
    }


@app.post("/emergency-action/manual")
async def trigger_manual_emergency_action(
    action: str,
    reason: str = "Manual trigger"
):
    """Manually trigger an emergency action."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Validate action
    try:
        action_enum = EmergencyAction(action)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    
    # Add to queue
    safety_service.emergency_actions_queue.append(action_enum)
    
    return {
        "status": "queued",
        "action": action,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/dead-mans-switch/reset")
async def reset_dead_mans_switch():
    """Reset the dead man's switch."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    safety_service.safety_manager.system_health.last_activity = datetime.utcnow()
    
    return {
        "status": "reset",
        "last_activity": safety_service.safety_manager.system_health.last_activity.isoformat()
    }


@app.post("/dead-mans-switch/override")
async def override_dead_mans_switch(enable: bool = True):
    """Enable/disable manual override for dead man's switch."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    safety_service.safety_manager.system_health.manual_override_active = enable
    
    return {
        "status": "override_set",
        "manual_override_active": enable,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/config")
async def get_configuration():
    """Get current safety manager configuration."""
    if not safety_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    config = safety_service.config
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "configuration": config.model_dump()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}