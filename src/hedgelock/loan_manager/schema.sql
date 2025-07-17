-- Loan Manager Database Schema

-- Loan state tracking
CREATE TABLE IF NOT EXISTS loan_states (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    principal DECIMAL(20, 8) NOT NULL,
    current_balance DECIMAL(20, 8) NOT NULL,
    apr DECIMAL(5, 4) NOT NULL,
    total_paid DECIMAL(20, 8) NOT NULL DEFAULT 0,
    principal_paid DECIMAL(20, 8) NOT NULL DEFAULT 0,
    interest_paid DECIMAL(20, 8) NOT NULL DEFAULT 0,
    accrued_interest DECIMAL(20, 8) NOT NULL DEFAULT 0,
    total_interest_accrued DECIMAL(20, 8) NOT NULL DEFAULT 0,
    loan_start_date TIMESTAMPTZ NOT NULL,
    last_interest_calc TIMESTAMPTZ NOT NULL,
    last_payment_date TIMESTAMPTZ,
    repayment_priority VARCHAR(20) NOT NULL DEFAULT 'interest_first',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index for timestamp queries
CREATE INDEX idx_loan_states_timestamp ON loan_states(timestamp DESC);

-- Repayment history
CREATE TABLE IF NOT EXISTS loan_repayments (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    amount DECIMAL(20, 8) NOT NULL,
    principal_portion DECIMAL(20, 8) NOT NULL,
    interest_portion DECIMAL(20, 8) NOT NULL,
    remaining_balance DECIMAL(20, 8) NOT NULL,
    source VARCHAR(50) NOT NULL,
    transaction_id VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index for timestamp queries
CREATE INDEX idx_loan_repayments_timestamp ON loan_repayments(timestamp DESC);
CREATE INDEX idx_loan_repayments_source ON loan_repayments(source);

-- LTV history tracking
CREATE TABLE IF NOT EXISTS ltv_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_collateral_value DECIMAL(20, 8) NOT NULL,
    loan_balance DECIMAL(20, 8) NOT NULL,
    ltv_ratio DECIMAL(5, 4) NOT NULL,
    current_action VARCHAR(20) NOT NULL,
    reserve_deployment DECIMAL(20, 8) NOT NULL DEFAULT 0,
    position_scaling DECIMAL(5, 4) NOT NULL DEFAULT 1.0,
    distance_to_liquidation DECIMAL(5, 4) NOT NULL,
    health_score DECIMAL(5, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_ltv_history_timestamp ON ltv_history(timestamp DESC);
CREATE INDEX idx_ltv_history_ltv_ratio ON ltv_history(ltv_ratio);
CREATE INDEX idx_ltv_history_action ON ltv_history(current_action);

-- Reserve deployment tracking
CREATE TABLE IF NOT EXISTS reserve_deployments (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ltv_ratio DECIMAL(5, 4) NOT NULL,
    deployment_amount DECIMAL(20, 8) NOT NULL,
    deployment_reason VARCHAR(200) NOT NULL,
    from_reserve DECIMAL(20, 8) NOT NULL,
    to_reserve DECIMAL(20, 8) NOT NULL,
    to_collateral DECIMAL(20, 8) NOT NULL,
    emergency BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_reserve_deployments_timestamp ON reserve_deployments(timestamp DESC);
CREATE INDEX idx_reserve_deployments_emergency ON reserve_deployments(emergency);

-- Interest accrual log
CREATE TABLE IF NOT EXISTS interest_accruals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    hours_elapsed DECIMAL(10, 4) NOT NULL,
    interest_rate DECIMAL(10, 8) NOT NULL,
    balance_used DECIMAL(20, 8) NOT NULL,
    interest_amount DECIMAL(20, 8) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index
CREATE INDEX idx_interest_accruals_timestamp ON interest_accruals(timestamp DESC);

-- LTV alerts
CREATE TABLE IF NOT EXISTS ltv_alerts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ltv_ratio DECIMAL(5, 4) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_ltv_alerts_timestamp ON ltv_alerts(timestamp DESC);
CREATE INDEX idx_ltv_alerts_severity ON ltv_alerts(severity);
CREATE INDEX idx_ltv_alerts_acknowledged ON ltv_alerts(acknowledged);

-- Loan events (milestones)
CREATE TABLE IF NOT EXISTS loan_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_loan_events_timestamp ON loan_events(timestamp DESC);
CREATE INDEX idx_loan_events_type ON loan_events(event_type);

-- Views for easier querying

-- Current loan state view
CREATE OR REPLACE VIEW current_loan_state AS
SELECT * FROM loan_states
ORDER BY timestamp DESC
LIMIT 1;

-- Recent repayments view
CREATE OR REPLACE VIEW recent_repayments AS
SELECT * FROM loan_repayments
ORDER BY timestamp DESC
LIMIT 100;

-- Current LTV view
CREATE OR REPLACE VIEW current_ltv AS
SELECT * FROM ltv_history
ORDER BY timestamp DESC
LIMIT 1;

-- Daily loan metrics
CREATE OR REPLACE VIEW daily_loan_metrics AS
SELECT 
    DATE(timestamp) as date,
    MIN(current_balance) as min_balance,
    MAX(current_balance) as max_balance,
    AVG(current_balance) as avg_balance,
    SUM(CASE WHEN source = 'trading_profit' THEN amount ELSE 0 END) as profit_repayments,
    SUM(CASE WHEN source = 'manual' THEN amount ELSE 0 END) as manual_repayments,
    COUNT(*) as repayment_count
FROM loan_repayments
GROUP BY DATE(timestamp)
ORDER BY date DESC;

-- LTV statistics view
CREATE OR REPLACE VIEW ltv_statistics AS
SELECT 
    DATE(timestamp) as date,
    MIN(ltv_ratio) as min_ltv,
    MAX(ltv_ratio) as max_ltv,
    AVG(ltv_ratio) as avg_ltv,
    COUNT(CASE WHEN current_action = 'WARNING' THEN 1 END) as warning_count,
    COUNT(CASE WHEN current_action = 'CRITICAL' THEN 1 END) as critical_count,
    COUNT(CASE WHEN current_action = 'EMERGENCY' THEN 1 END) as emergency_count
FROM ltv_history
GROUP BY DATE(timestamp)
ORDER BY date DESC;