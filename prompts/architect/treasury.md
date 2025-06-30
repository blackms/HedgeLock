# Architect Prompt: hedgelock-treasury

You are a senior Python developer implementing the **hedgelock-treasury** microservice for the HedgeLock MVP.

## Context
The HedgeLock system generates profits from hedging operations. The treasury service manages these profits strategically, either repaying loan principal to reduce leverage or adding collateral to improve LTV ratios.

## Your Task
Design and implement a Python microservice that:

1. **Tracks realized PnL from hedging**:
   - Monitors `hedge-executions` for completed trades
   - Calculates realized profits/losses
   - Maintains running PnL accounting

2. **Makes intelligent allocation decisions**:
   - When LTV > 45%: Add profits as collateral
   - When LTV < 35%: Repay loan principal
   - Between 35-45%: Optimize based on rates

3. **Executes treasury operations**:
   - Initiate loan repayments via Bybit API
   - Add collateral to existing loans
   - Manage USDT settlement flows

## Technical Requirements

### Stack
- Python 3.12 with asyncio
- FastAPI for treasury API
- aiokafka for event streaming
- SQLAlchemy for transaction history
- pybit for Bybit operations

### Treasury Logic
```python
class TreasuryManager:
    async def process_realized_pnl(self, execution: HedgeExecution) -> TreasuryAction:
        """Process profits from hedging operations"""
        # 1. Calculate realized PnL
        pnl = self._calculate_realized_pnl(execution)
        
        # 2. Get current loan state
        loan_state = await self._get_loan_state()
        
        # 3. Decide allocation strategy
        action = self._determine_allocation(pnl, loan_state)
        
        # 4. Execute treasury operation
        result = await self._execute_treasury_action(action)
        
        return result
```

### Allocation Strategy
```python
class AllocationEngine:
    def determine_allocation(
        self,
        available_funds: Decimal,
        ltv_ratio: Decimal,
        loan_apr: Decimal,
        collateral_yield: Decimal
    ) -> AllocationDecision:
        """Intelligent fund allocation based on economics"""
        
        if ltv_ratio > 45:
            # High risk - prioritize safety
            return AllocationDecision(
                action="add_collateral",
                amount=available_funds * Decimal("0.95"),  # Keep 5% buffer
                reason="ltv_risk_reduction"
            )
        
        elif ltv_ratio < 35:
            # Low risk - optimize returns
            if loan_apr > collateral_yield + 2:  # 2% spread threshold
                return AllocationDecision(
                    action="repay_principal",
                    amount=available_funds * Decimal("0.90"),
                    reason="interest_optimization"
                )
            else:
                return AllocationDecision(
                    action="add_collateral",
                    amount=available_funds * Decimal("0.90"),
                    reason="yield_optimization"
                )
        
        else:
            # Balanced approach
            return AllocationDecision(
                action="split",
                repay_amount=available_funds * Decimal("0.45"),
                collateral_amount=available_funds * Decimal("0.45"),
                reason="balanced_allocation"
            )
```

### Transaction Management
```python
class TransactionManager:
    async def execute_repayment(
        self,
        loan_id: str,
        amount: Decimal
    ) -> RepaymentResult:
        """Execute loan principal repayment"""
        # Pre-flight checks
        await self._validate_repayment_amount(loan_id, amount)
        
        # Execute repayment
        tx = await self.bybit_client.repay_loan(
            loan_id=loan_id,
            amount=amount,
            currency="USDT"
        )
        
        # Record transaction
        await self._record_transaction(tx)
        
        return RepaymentResult(
            transaction_id=tx.id,
            amount_repaid=amount,
            new_loan_balance=tx.remaining_balance
        )
```

### PnL Accounting
```python
class PnLAccounting:
    def calculate_realized_pnl(self, execution: HedgeExecution) -> PnLRecord:
        """Track realized profits from hedging"""
        entry_price = execution.entry_price
        exit_price = execution.exit_price
        size = execution.size
        
        # Short position PnL
        gross_pnl = (entry_price - exit_price) * size
        
        # Deduct costs
        fees = self._calculate_fees(execution)
        funding = self._calculate_funding(execution)
        
        net_pnl = gross_pnl - fees - funding
        
        return PnLRecord(
            gross_pnl=gross_pnl,
            fees=fees,
            funding=funding,
            net_pnl=net_pnl,
            timestamp=datetime.utcnow()
        )
```

### Data Models
```python
class TreasuryAction(BaseModel):
    timestamp: datetime
    action_type: str  # repay_principal, add_collateral, split
    amounts: Dict[str, Decimal]
    loan_state_before: LoanState
    loan_state_after: LoanState
    transaction_ids: List[str]
    
class LoanState(BaseModel):
    loan_id: str
    principal_amount: Decimal
    collateral_value: Decimal
    ltv_ratio: Decimal
    interest_rate: Decimal
    accrued_interest: Decimal
```

## Deliverables

1. **Service Implementation**:
   - `src/treasury/main.py`: Service orchestrator
   - `src/treasury/allocation.py`: Fund allocation logic
   - `src/treasury/transactions.py`: Bybit operations
   - `src/treasury/accounting.py`: PnL tracking

2. **Database Schema**:
   - Transaction history table
   - PnL records table
   - Allocation decisions audit

3. **Configuration**:
   - `config/treasury.yaml`: Allocation thresholds
   - Buffer percentages
   - Min/max operation amounts

4. **Tests**:
   - Unit tests for allocation logic
   - Integration tests with mock APIs
   - Accounting reconciliation tests

## Financial Controls

### Safety Measures
- Minimum buffer: Always keep 5% of profits
- Maximum single operation: $10,000
- Daily operation limit: $50,000
- Require confirmations for large amounts

### Audit Trail
```python
@dataclass
class AuditRecord:
    timestamp: datetime
    decision_type: str
    input_data: Dict
    decision_logic: str
    output_action: TreasuryAction
    approvals: List[str]
    execution_result: Dict
```

### Error Handling
- Retry failed operations with exponential backoff
- Rollback mechanisms for partial failures
- Dead letter queue for manual review
- Emergency pause functionality

## Performance Requirements
- Process PnL within 1 minute of realization
- Support 100+ treasury operations/day
- Maintain complete audit trail
- Zero fund loss tolerance

## Important Considerations

### Regulatory Compliance
- Maintain detailed transaction records
- Support tax reporting requirements
- Implement KYC/AML checks if required
- Enable regulatory audits

### Optimization Factors
- Consider loan interest rates
- Factor in collateral yield opportunities
- Account for tax implications
- Optimize for long-term sustainability

### Risk Management
- Never exceed authorized limits
- Implement maker-checker for large amounts
- Monitor for unusual patterns
- Maintain emergency procedures

## Quality Criteria
- 100% accurate fund accounting
- Complete audit trail
- Optimal allocation decisions
- Robust error recovery
- Clear, maintainable code

Remember: This service manages user funds directly. Accuracy, security, and auditability are non-negotiable.