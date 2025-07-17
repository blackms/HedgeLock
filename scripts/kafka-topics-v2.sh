#!/bin/bash
#
# Kafka Topics Setup for HedgeLock v2.0
# Creates all required topics for the complete system
#

set -e

KAFKA_CONTAINER="hedgelock-kafka-1"
REPLICATION_FACTOR=1
PARTITIONS=3

echo "🚀 Creating Kafka topics for HedgeLock v2.0..."

# Function to create topic
create_topic() {
    local TOPIC=$1
    local PARTITIONS=${2:-3}
    local REPLICATION=${3:-1}
    
    echo "Creating topic: $TOPIC"
    docker exec $KAFKA_CONTAINER kafka-topics --create \
        --if-not-exists \
        --bootstrap-server localhost:9092 \
        --topic $TOPIC \
        --partitions $PARTITIONS \
        --replication-factor $REPLICATION
}

# Existing topics (v1.x)
create_topic "market_data" 3
create_topic "funding_rates" 3
create_topic "funding_context" 3
create_topic "hedge_trades" 3
create_topic "risk_assessments" 3
create_topic "trading_signals" 3
create_topic "trade_executions" 3

# New topics for v2.0

# Position Manager topics
create_topic "position_states" 3
create_topic "hedge_decisions" 3
create_topic "profit_taking" 3
create_topic "pnl_updates" 3

# Loan Manager topics
create_topic "loan_updates" 3
create_topic "loan_repayments" 3
create_topic "ltv_updates" 3
create_topic "loan_events" 3

# Reserve Manager topics
create_topic "reserve_deployments" 3
create_topic "reserve_deployment_results" 3
create_topic "profit_distribution" 3
create_topic "trading_withdrawals" 3

# Safety Manager topics
create_topic "safety_metrics" 3
create_topic "emergency_actions" 3
create_topic "risk_alerts" 3
create_topic "safety_triggers" 3
create_topic "safety_notifications" 3
create_topic "service_health" 3

# Cross-service topics
create_topic "treasury_updates" 3
create_topic "position_scaling" 3
create_topic "system_events" 3

echo "✅ All Kafka topics created successfully!"

# List all topics
echo -e "\n📋 Current topics:"
docker exec $KAFKA_CONTAINER kafka-topics --list --bootstrap-server localhost:9092 | sort