# Architect Prompt: hedgelock-alert

You are a senior Python developer implementing the **hedgelock-alert** microservice for the HedgeLock MVP.

## Context
The HedgeLock system protects user funds through automated monitoring and intervention. The alert service ensures users and operators are immediately notified of important events, enabling timely human intervention when needed.

## Your Task
Design and implement a Python microservice that:

1. **Monitors critical events from Kafka**:
   - Risk state changes (especially DANGER/CRITICAL)
   - Large treasury operations
   - System errors and anomalies
   - Connection failures

2. **Routes notifications intelligently**:
   - Telegram for immediate user alerts
   - Email for detailed reports
   - SMS for critical events (future)
   - Webhook for integrations

3. **Manages alert lifecycle**:
   - Rate limiting to prevent spam
   - Escalation for unacknowledged alerts
   - Alert aggregation and summaries

## Technical Requirements

### Stack
- Python 3.12 with asyncio
- FastAPI for webhook API
- aiokafka for event consumption
- python-telegram-bot for Telegram
- aiosmtplib for email
- Redis for rate limiting

### Alert Engine
```python
class AlertEngine:
    async def process_event(self, event: Event) -> List[Alert]:
        """Process events and generate appropriate alerts"""
        # 1. Classify event severity
        severity = self._classify_severity(event)
        
        # 2. Determine recipients and channels
        routing = self._determine_routing(event, severity)
        
        # 3. Format messages for each channel
        messages = self._format_messages(event, routing)
        
        # 4. Apply rate limiting and deduplication
        filtered = await self._apply_filters(messages)
        
        # 5. Send alerts
        results = await self._send_alerts(filtered)
        
        return results
```

### Event Classification
```python
class EventClassifier:
    def classify_severity(self, event: Event) -> Severity:
        """Determine event severity for routing"""
        
        if event.type == "risk_state":
            if event.data.risk_level == "CRITICAL":
                return Severity.CRITICAL
            elif event.data.risk_level == "DANGER":
                return Severity.HIGH
            elif event.data.risk_level == "CAUTION":
                return Severity.MEDIUM
        
        elif event.type == "system_error":
            if "connection_lost" in event.data.error:
                return Severity.CRITICAL
            else:
                return Severity.HIGH
        
        elif event.type == "treasury_action":
            if event.data.amount > 10000:
                return Severity.HIGH
            else:
                return Severity.LOW
        
        return Severity.INFO
```

### Message Formatting
```python
class MessageFormatter:
    def format_telegram_alert(self, event: RiskStateEvent) -> str:
        """Format alert for Telegram"""
        if event.risk_level == "CRITICAL":
            return f"""
🚨 **CRITICAL ALERT** 🚨

Your loan is at immediate risk of liquidation!

📊 **Current Status:**
• LTV Ratio: {event.ltv_ratio:.1f}%
• Liquidation Price: ${event.liquidation_price:,.2f}
• Current BTC Price: ${event.current_price:,.2f}

⚡ **Automatic Action Taken:**
• Hedging {event.hedge_size:.4f} BTC
• Estimated protection: ${event.protection_value:,.2f}

⚠️ **Recommended Actions:**
1. Add collateral immediately
2. Reduce loan amount
3. Monitor closely

[View Dashboard](https://app.hedgelock.io/dashboard)
"""
        
    def format_email_report(self, events: List[Event]) -> EmailMessage:
        """Format daily summary email"""
        # Create HTML email with charts and tables
        # Include performance metrics
        # Add actionable insights
```

### Routing Rules
```python
class RoutingEngine:
    ROUTING_RULES = {
        Severity.CRITICAL: {
            "channels": ["telegram", "email", "sms"],
            "rate_limit": None,  # No limit for critical
            "escalation": 5,  # Escalate after 5 minutes
        },
        Severity.HIGH: {
            "channels": ["telegram", "email"],
            "rate_limit": "5/hour",
            "escalation": 30,
        },
        Severity.MEDIUM: {
            "channels": ["telegram"],
            "rate_limit": "10/hour",
            "escalation": None,
        },
        Severity.LOW: {
            "channels": ["email"],  # Daily digest only
            "rate_limit": "1/day",
            "escalation": None,
        }
    }
```

### Channel Implementations

#### Telegram Bot
```python
class TelegramNotifier:
    async def send_alert(self, chat_id: str, message: str, parse_mode: str = "Markdown"):
        """Send Telegram notification"""
        # Handle message formatting
        # Add inline keyboards for actions
        # Track delivery status
        
    async def setup_bot_commands(self):
        """Configure bot commands"""
        commands = [
            ("status", "Get current loan status"),
            ("mute", "Mute alerts for 1 hour"),
            ("help", "Show help message"),
            ("settings", "Configure alert preferences")
        ]
```

#### Email Service
```python
class EmailNotifier:
    async def send_email(
        self,
        to: List[str],
        subject: str,
        html_body: str,
        attachments: List[Attachment] = None
    ):
        """Send email notification"""
        # Use SMTP with TLS
        # Handle retries
        # Track open rates
```

### Rate Limiting
```python
class RateLimiter:
    async def check_rate_limit(
        self,
        user_id: str,
        channel: str,
        severity: Severity
    ) -> bool:
        """Check if alert should be sent"""
        key = f"rate_limit:{user_id}:{channel}:{severity}"
        
        # Get current count from Redis
        count = await self.redis.incr(key)
        
        # Set TTL on first increment
        if count == 1:
            await self.redis.expire(key, 3600)  # 1 hour window
        
        # Check against limits
        limit = self._get_limit(channel, severity)
        return count <= limit
```

### Alert Analytics
```python
class AlertAnalytics:
    async def track_alert(self, alert: Alert):
        """Track alert metrics"""
        # Record send time
        # Track delivery status
        # Monitor acknowledgments
        # Calculate response times
        
    async def generate_analytics_report(self) -> Report:
        """Generate alert effectiveness report"""
        # Alert volume by severity
        # Response time analysis
        # Channel effectiveness
        # User engagement metrics
```

## Deliverables

1. **Service Implementation**:
   - `src/alert/main.py`: Service orchestrator
   - `src/alert/engine.py`: Alert processing engine
   - `src/alert/channels/`: Channel implementations
   - `src/alert/formatting.py`: Message formatters

2. **Configuration**:
   - `config/alert.yaml`: Routing rules and limits
   - Alert templates
   - Channel credentials

3. **Bot Setup**:
   - Telegram bot with commands
   - Email templates
   - Webhook endpoints

4. **Tests**:
   - Unit tests for routing logic
   - Integration tests for channels
   - Load tests for rate limiting

## User Experience

### Alert Preferences
```python
class UserPreferences(BaseModel):
    telegram_enabled: bool = True
    email_enabled: bool = True
    quiet_hours: Optional[Tuple[int, int]] = None  # (22, 8)
    severity_threshold: Severity = Severity.MEDIUM
    summary_frequency: str = "daily"  # daily, weekly
    language: str = "en"
```

### Interactive Features
- Acknowledge alerts directly from Telegram
- Snooze notifications temporarily
- Configure preferences via bot
- Request status updates on demand

## Quality Criteria
- < 1 second delivery for critical alerts
- 99.9% delivery success rate
- No duplicate alerts
- Clear, actionable messages
- Respects user preferences

## Important Considerations

### Reliability
- Implement failover for each channel
- Queue alerts during outages
- Monitor delivery success
- Handle channel-specific errors

### Security
- Encrypt sensitive data in transit
- Validate webhook signatures
- Rate limit by IP for webhooks
- Implement authentication tokens

### Compliance
- Include required disclaimers
- Support unsubscribe mechanisms
- Log all communications
- Handle GDPR requirements

Remember: Alerts can mean the difference between protected and liquidated funds. Speed, reliability, and clarity are essential.