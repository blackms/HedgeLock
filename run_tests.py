#!/usr/bin/env python3
"""Run Position Manager tests directly."""

import sys
import subprocess
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Install dependencies if needed
try:
    import pytest
except ImportError:
    print("Installing pytest...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pytest", "pytest-asyncio", "pytest-cov"])
    import pytest

# Run tests
sys.exit(pytest.main([
    "tests/unit/position_manager/",
    "-v",
    "--cov=src/hedgelock/position_manager",
    "--cov-report=term-missing",
    "--tb=short"
]))