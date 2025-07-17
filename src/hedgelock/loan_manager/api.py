"""
Loan Manager API endpoints.
"""

from fastapi import FastAPI, HTTPException, Request
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from .models import LoanRepaymentRequest, RepaymentPriority
from .service import LoanManagerService

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="HedgeLock Loan Manager")

# Global service instance
loan_service: Optional[LoanManagerService] = None


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    global loan_service
    
    logger.info("Starting Loan Manager API...")
    
    # Configure service
    config = {
        'kafka_servers': 'kafka:29092',
        'loan_config': {
            'initial_principal': 16200.0,
            'apr': 0.06,
            'auto_repay_enabled': True,
            'profit_allocation_percent': 0.5,
            'ltv_check_interval': 60,
            'reserve_deployment_enabled': True
        }
    }
    
    # Create and start service
    loan_service = LoanManagerService(config)
    # Note: Don't await start() here as it runs forever
    import asyncio
    asyncio.create_task(loan_service.start())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global loan_service
    
    if loan_service:
        await loan_service.stop()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Loan Manager",
        "version": "1.0.0",
        "status": "active",
        "description": "Automatic loan tracking and repayment for HedgeLock"
    }


@app.get("/status")
async def get_status():
    """Get service status and current state."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    state = loan_service.get_current_state()
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "service": "loan-manager",
        "status": "active" if loan_service.running else "inactive",
        "current_state": state
    }


@app.get("/loan/state")
async def get_loan_state():
    """Get current loan state."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    loan_state = loan_service.loan_manager.loan_state
    metrics = loan_service.loan_manager.get_loan_metrics()
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "loan_state": {
            "original_principal": loan_state.principal,
            "current_balance": loan_state.current_balance,
            "accrued_interest": loan_state.accrued_interest,
            "total_paid": loan_state.total_paid,
            "principal_paid": loan_state.principal_paid,
            "interest_paid": loan_state.interest_paid,
            "apr": loan_state.apr,
            "loan_start_date": loan_state.loan_start_date.isoformat(),
            "last_payment_date": loan_state.last_payment_date.isoformat() if loan_state.last_payment_date else None
        },
        "metrics": metrics,
        "is_paid_off": loan_service.loan_manager.is_loan_paid_off()
    }


@app.get("/loan/metrics")
async def get_loan_metrics():
    """Get comprehensive loan metrics."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    metrics = loan_service.loan_manager.get_loan_metrics()
    
    # Add payoff estimation
    monthly_payment_scenarios = [100, 500, 1000, 2000]
    payoff_estimates = {}
    
    for payment in monthly_payment_scenarios:
        months = loan_service.loan_manager.estimate_payoff_time(payment)
        if months:
            payoff_estimates[f"${payment}/month"] = {
                "months": months,
                "years": round(months / 12, 1)
            }
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics,
        "payoff_estimates": payoff_estimates
    }


@app.get("/ltv/current")
async def get_current_ltv():
    """Get current LTV state."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not loan_service.loan_manager.ltv_history:
        # Calculate current LTV if no history
        if loan_service.current_collateral_value > 0:
            ltv_state = loan_service.loan_manager.calculate_ltv(
                loan_service.current_collateral_value
            )
        else:
            raise HTTPException(status_code=404, detail="No LTV data available")
    else:
        ltv_state = loan_service.loan_manager.ltv_history[-1]
    
    return {
        "timestamp": ltv_state.timestamp.isoformat(),
        "ltv_ratio": ltv_state.ltv_ratio,
        "ltv_percent": f"{ltv_state.ltv_ratio * 100:.1f}%",
        "collateral_value": ltv_state.total_collateral_value,
        "loan_balance": ltv_state.loan_balance,
        "current_action": ltv_state.current_action.value,
        "reserve_deployment": ltv_state.reserve_deployment,
        "position_scaling": ltv_state.position_scaling,
        "distance_to_liquidation": ltv_state.distance_to_liquidation,
        "health_score": ltv_state.health_score
    }


@app.get("/ltv/history")
async def get_ltv_history(hours: int = 24):
    """Get LTV history for specified hours."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    recent_ltvs = loan_service.loan_manager.get_recent_ltv_trend(hours)
    
    # Get full history entries
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    history = [
        {
            "timestamp": ltv.timestamp.isoformat(),
            "ltv_ratio": ltv.ltv_ratio,
            "action": ltv.current_action.value,
            "collateral_value": ltv.total_collateral_value,
            "loan_balance": ltv.loan_balance
        }
        for ltv in loan_service.loan_manager.ltv_history
        if ltv.timestamp >= cutoff
    ]
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "hours": hours,
        "ltv_values": recent_ltvs,
        "history": history,
        "average_ltv": sum(recent_ltvs) / len(recent_ltvs) if recent_ltvs else 0,
        "max_ltv": max(recent_ltvs) if recent_ltvs else 0,
        "min_ltv": min(recent_ltvs) if recent_ltvs else 0
    }


@app.get("/repayments/history")
async def get_repayment_history(limit: int = 50):
    """Get repayment history."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    history = loan_service.loan_manager.repayment_history[-limit:]
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(history),
        "total_repayments": len(loan_service.loan_manager.repayment_history),
        "repayments": [
            {
                "timestamp": record.timestamp.isoformat(),
                "amount": record.amount,
                "principal_portion": record.principal_portion,
                "interest_portion": record.interest_portion,
                "remaining_balance": record.remaining_balance,
                "notes": record.notes
            }
            for record in history
        ]
    }


@app.post("/repayment/manual")
async def make_manual_repayment(request: LoanRepaymentRequest):
    """Make a manual loan repayment."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Set source to manual if not specified
    if not request.source:
        request.source = "manual"
    
    # Add to repayment queue
    loan_service.repayment_queue.append(request)
    
    return {
        "status": "queued",
        "message": f"Repayment of ${request.amount:.2f} queued for processing",
        "timestamp": datetime.utcnow().isoformat(),
        "queue_size": len(loan_service.repayment_queue)
    }


@app.get("/reserves/deployment")
async def get_reserve_deployment_history(limit: int = 20):
    """Get reserve deployment history."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    history = loan_service.loan_manager.deployment_history[-limit:]
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(history),
        "total_deployments": len(loan_service.loan_manager.deployment_history),
        "deployments": [
            {
                "timestamp": deployment.timestamp.isoformat(),
                "ltv_ratio": deployment.ltv_ratio,
                "amount": deployment.deployment_amount,
                "reason": deployment.deployment_reason,
                "emergency": deployment.emergency,
                "from_reserve": deployment.from_reserve,
                "to_reserve": deployment.to_reserve
            }
            for deployment in history
        ],
        "total_deployed": sum(d.deployment_amount for d in loan_service.loan_manager.deployment_history)
    }


@app.get("/config")
async def get_configuration():
    """Get current loan manager configuration."""
    if not loan_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    config = loan_service.config
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "configuration": {
            "initial_principal": config.initial_principal,
            "apr": config.apr,
            "auto_repay_enabled": config.auto_repay_enabled,
            "repayment_priority": config.repayment_priority.value,
            "profit_allocation_percent": config.profit_allocation_percent,
            "min_payment_amount": config.min_payment_amount,
            "ltv_check_interval": config.ltv_check_interval,
            "reserve_deployment_enabled": config.reserve_deployment_enabled,
            "emergency_deployment_threshold": config.emergency_deployment_threshold,
            "alert_on_high_ltv": config.alert_on_high_ltv,
            "alert_ltv_threshold": config.alert_ltv_threshold
        }
    }


# Add health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}