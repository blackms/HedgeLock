# HedgeLock v2.0 Emergency Procedures

## 🚨 Critical Situations & Response Protocols

### 1. Liquidation Risk (< 10% Distance)

**Indicators:**
- Safety Manager alerts: `LIQUIDATION_RISK`
- Distance to liquidation < 10%
- Risk level: CRITICAL or EMERGENCY

**Immediate Actions:**
1. **Automatic Response** (if enabled):
   - Position Manager reduces positions by 50-80%
   - Reserve Manager deploys emergency reserves
   - Safety Manager may trigger PANIC_CLOSE

2. **Manual Intervention:**
   ```bash
   # Check liquidation risk
   curl http://localhost:8012/liquidation/risk
   
   # Manually trigger position reduction
   curl -X POST http://localhost:8012/emergency-action/manual \
     -H "Content-Type: application/json" \
     -d '{"action": "reduce_positions", "reason": "Manual liquidation prevention"}'
   ```

### 2. Dead Man's Switch Triggered

**Indicators:**
- No system activity for 60+ minutes
- Safety Manager alert: `DEAD_MANS_SWITCH`

**Actions:**
1. **Check System Health:**
   ```bash
   curl http://localhost:8012/system-health
   ```

2. **Reset Dead Man's Switch:**
   ```bash
   curl -X POST http://localhost:8012/dead-mans-switch/reset
   ```

3. **Enable Manual Override:**
   ```bash
   curl -X POST http://localhost:8012/dead-mans-switch/override?enable=true
   ```

### 3. Circuit Breaker Activation

**Types:**
- Daily Loss Limit ($1000)
- Funding Cost Limit ($100/day)
- Volatility Limit (10%)
- Consecutive Loss Days (3 days)

**Response:**
1. **Check Active Breakers:**
   ```bash
   curl http://localhost:8012/circuit-breakers
   ```

2. **Trading is automatically halted**
3. **Wait for cooldown period** (30-120 minutes depending on breaker)

### 4. Extreme Funding Rates

**Indicators:**
- Funding regime: EXTREME
- Funding rate > 0.1% per 8h

**Actions:**
1. **Automatic:** Position Manager closes all perpetual positions
2. **Manual Check:**
   ```bash
   # Check funding context
   curl http://localhost:8001/funding/context
   ```

### 5. Service Failures

**Critical Services:**
- Position Manager (port 8009)
- Trade Executor (port 8006)
- Risk Engine (port 8003)

**Recovery Steps:**
1. **Check Service Health:**
   ```bash
   docker-compose -f docker-compose.v2.yml ps
   ```

2. **Restart Failed Service:**
   ```bash
   docker-compose -f docker-compose.v2.yml restart <service-name>
   ```

3. **Check Logs:**
   ```bash
   docker-compose -f docker-compose.v2.yml logs -f <service-name>
   ```

## 📞 Emergency Contacts & Escalation

### Severity Levels

| Level | Response Time | Actions |
|-------|--------------|---------|
| LOW | 24 hours | Monitor, no immediate action |
| MEDIUM | 4 hours | Review and plan response |
| HIGH | 1 hour | Active intervention required |
| CRITICAL | 15 minutes | Immediate action required |
| EMERGENCY | Immediate | All positions closed, trading halted |

### Manual Emergency Controls

**1. Halt All Trading:**
```bash
curl -X POST http://localhost:8012/emergency-action/manual \
  -d '{"action": "halt_trading", "reason": "Emergency stop"}'
```

**2. Close All Positions:**
```bash
curl -X POST http://localhost:8012/emergency-action/manual \
  -d '{"action": "close_all", "reason": "Emergency liquidation"}'
```

**3. Deploy All Reserves:**
```bash
curl -X POST http://localhost:8011/deployment/manual \
  -d '{"amount": 10000, "action": "deploy_to_collateral", "emergency": true}'
```

## 🔍 Monitoring Commands

**System Overview:**
```bash
# Check all service health
for port in 8009 8010 8011 8012; do
  echo "Service on port $port:"
  curl -s http://localhost:$port/health | jq .
done

# View active alerts
curl http://localhost:8012/alerts/active

# Check current positions
curl http://localhost:8009/position

# View loan status
curl http://localhost:8010/loan/state

# Check reserve status
curl http://localhost:8011/reserves/state
```

## 📋 Post-Emergency Checklist

After resolving an emergency:

1. [ ] Document the incident
2. [ ] Review system logs
3. [ ] Check for data inconsistencies
4. [ ] Verify position states
5. [ ] Confirm loan/reserve balances
6. [ ] Reset circuit breakers if needed
7. [ ] Re-enable automated trading
8. [ ] Monitor closely for 24 hours

## 🛡️ Prevention Best Practices

1. **Monitor LTV continuously** - Keep below 65%
2. **Maintain adequate reserves** - Minimum $2000 available
3. **Set conservative limits** - Adjust based on market conditions
4. **Regular system checks** - Daily health monitoring
5. **Test emergency procedures** - Monthly drills recommended