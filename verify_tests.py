#!/usr/bin/env python3
"""Verify Position Manager tests can be imported."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("Testing imports...")

try:
    # Test model imports
    from src.hedgelock.position_manager.models import PositionState, HedgeDecision
    print("✓ Models imported successfully")
except Exception as e:
    print(f"✗ Models import failed: {e}")

try:
    # Test manager import
    from src.hedgelock.position_manager.manager import DeltaNeutralManager
    print("✓ Manager imported successfully")
except Exception as e:
    print(f"✗ Manager import failed: {e}")

try:
    # Test service import
    from src.hedgelock.position_manager.service import PositionManagerService
    print("✓ Service imported successfully")
except Exception as e:
    print(f"✗ Service import failed: {e}")

try:
    # Test API import
    from src.hedgelock.position_manager.api import app
    print("✓ API imported successfully")
except Exception as e:
    print(f"✗ API import failed: {e}")

print("\nRunning basic tests...")

# Test model creation
try:
    from datetime import datetime
    state = PositionState(
        timestamp=datetime.utcnow(),
        spot_btc=0.27,
        long_perp=0.213,
        short_perp=0.213,
        net_delta=0.27,
        hedge_ratio=1.0,
        btc_price=116000,
        volatility_24h=0.02,
        funding_rate=0.0001
    )
    print("✓ PositionState created successfully")
except Exception as e:
    print(f"✗ PositionState creation failed: {e}")

# Test manager
try:
    manager = DeltaNeutralManager()
    delta = manager.calculate_delta(state)
    print(f"✓ Delta calculation works: {delta}")
except Exception as e:
    print(f"✗ Manager test failed: {e}")

print("\nAll basic tests completed!")