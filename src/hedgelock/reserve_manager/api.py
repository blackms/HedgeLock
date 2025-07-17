"""
Reserve Manager API endpoints.
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, Any, Optional
import logging
from datetime import datetime

from .models import DeploymentRequest, DeploymentAction
from .service import ReserveManagerService

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="HedgeLock Reserve Manager")

# Global service instance
reserve_service: Optional[ReserveManagerService] = None


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    global reserve_service
    
    logger.info("Starting Reserve Manager API...")
    
    # Configure service
    config = {
        'kafka_servers': 'kafka:29092',
        'reserve_config': {
            'initial_reserves': 10000.0,
            'min_reserve_balance': 1000.0,
            'max_deployment_percent': 0.9,
            'profit_to_reserve_percent': 0.2,
            'target_reserve_ratio': 0.2,
            'emergency_deployment_enabled': True
        }
    }
    
    # Create and start service
    reserve_service = ReserveManagerService(config)
    import asyncio
    asyncio.create_task(reserve_service.start())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global reserve_service
    
    if reserve_service:
        await reserve_service.stop()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Reserve Manager",
        "version": "1.0.0",
        "status": "active",
        "description": "USDC reserve management for HedgeLock"
    }


@app.get("/status")
async def get_status():
    """Get service status and current state."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    state = reserve_service.get_current_state()
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "service": "reserve-manager",
        "status": "active" if reserve_service.running else "inactive",
        "current_state": state
    }


@app.get("/reserves/state")
async def get_reserve_state():
    """Get current reserve state."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    state = reserve_service.reserve_manager.reserve_state
    
    return {
        "timestamp": state.timestamp.isoformat(),
        "reserves": {
            "total": state.total_reserves,
            "available": state.available_reserves,
            "deployed": state.deployed_reserves,
            "deployed_to_collateral": state.deployed_to_collateral,
            "deployed_to_trading": state.deployed_to_trading
        },
        "metrics": {
            "deployment_ratio": state.deployment_ratio,
            "deployable_amount": state.calculate_deployable_amount(),
            "reserve_health": state.reserve_health,
            "min_reserve_balance": state.min_reserve_balance
        }
    }


@app.get("/reserves/metrics")
async def get_reserve_metrics():
    """Get comprehensive reserve metrics."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    metrics = reserve_service.reserve_manager.get_reserve_metrics()
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics,
        "deployment_capacity": {
            "normal": reserve_service.reserve_manager.get_deployment_capacity(emergency=False),
            "emergency": reserve_service.reserve_manager.get_deployment_capacity(emergency=True)
        }
    }


@app.get("/deployments/history")
async def get_deployment_history(hours: int = 24):
    """Get deployment history."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    deployments = reserve_service.reserve_manager.get_recent_deployments(hours)
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "hours": hours,
        "count": len(deployments),
        "deployments": [
            {
                "timestamp": d.timestamp.isoformat(),
                "amount_requested": d.amount_requested,
                "amount_deployed": d.amount_deployed,
                "action": d.action.value,
                "success": d.success,
                "reason": d.reason,
                "reserves_after": d.reserves_after
            }
            for d in deployments
        ],
        "total_deployed": sum(d.amount_deployed for d in deployments if d.success)
    }


@app.post("/deployment/manual")
async def create_manual_deployment(
    amount: float,
    action: str = "deploy_to_collateral",
    reason: str = "Manual deployment",
    emergency: bool = False
):
    """Create manual deployment request."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Validate action
    try:
        action_enum = DeploymentAction(action)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    
    # Create deployment request
    request = DeploymentRequest(
        amount=amount,
        action=action_enum,
        reason=reason,
        emergency=emergency,
        requester="manual_api"
    )
    
    # Add to queue
    reserve_service.deployment_queue.append(request)
    
    return {
        "status": "queued",
        "message": f"Deployment of ${amount:.2f} queued for processing",
        "timestamp": datetime.utcnow().isoformat(),
        "queue_size": len(reserve_service.deployment_queue)
    }


@app.post("/withdrawal/trading")
async def withdraw_from_trading(amount: float, reason: str = "Manual withdrawal"):
    """Withdraw reserves from trading."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    success = reserve_service.reserve_manager.withdraw_from_trading(amount, reason)
    
    if not success:
        raise HTTPException(status_code=400, detail="Withdrawal failed - insufficient deployed reserves")
    
    return {
        "status": "success",
        "message": f"Withdrew ${amount:.2f} from trading",
        "timestamp": datetime.utcnow().isoformat(),
        "available_reserves": reserve_service.reserve_manager.reserve_state.available_reserves
    }


@app.get("/alerts/recent")
async def get_recent_alerts(limit: int = 20):
    """Get recent reserve alerts."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    alerts = reserve_service.reserve_manager.alert_history[-limit:]
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(alerts),
        "alerts": [
            {
                "timestamp": alert.timestamp.isoformat(),
                "type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "action_required": alert.action_required,
                "suggested_action": alert.suggested_action
            }
            for alert in alerts
        ]
    }


@app.get("/deployment/ltv-calculation")
async def calculate_ltv_deployment(ltv_ratio: float):
    """Calculate deployment amount for given LTV."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not 0 <= ltv_ratio <= 1:
        raise HTTPException(status_code=400, detail="LTV ratio must be between 0 and 1")
    
    deployment = reserve_service.reserve_manager.calculate_deployment_for_ltv(ltv_ratio)
    available = reserve_service.reserve_manager.get_deployment_capacity(
        emergency=ltv_ratio >= 0.85
    )
    
    return {
        "ltv_ratio": ltv_ratio,
        "ltv_percent": f"{ltv_ratio * 100:.1f}%",
        "calculated_deployment": deployment,
        "available_capacity": available,
        "actual_deployment": min(deployment, available),
        "is_emergency": ltv_ratio >= 0.85
    }


@app.get("/config")
async def get_configuration():
    """Get current reserve manager configuration."""
    if not reserve_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    config = reserve_service.config
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "configuration": {
            "initial_reserves": config.initial_reserves,
            "min_reserve_balance": config.min_reserve_balance,
            "max_deployment_percent": config.max_deployment_percent,
            "max_single_deployment": config.max_single_deployment,
            "profit_to_reserve_percent": config.profit_to_reserve_percent,
            "target_reserve_ratio": config.target_reserve_ratio,
            "emergency_deployment_enabled": config.emergency_deployment_enabled,
            "emergency_ltv_threshold": config.emergency_ltv_threshold,
            "low_reserve_alert_threshold": config.low_reserve_alert_threshold
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}