#!/usr/bin/env python3
"""
Run Position Manager tests with coverage report.
"""

import subprocess
import sys
import os

def run_tests():
    """Run pytest with coverage."""
    # Add src to Python path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
    
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/unit/position_manager/',
        '-v',
        '--cov=src/hedgelock/position_manager',
        '--cov-report=term-missing',
        '--cov-report=html:htmlcov/position_manager',
        '--cov-fail-under=100',
        '-x'  # Stop on first failure
    ]
    
    print("🧪 Running Position Manager Tests with Coverage")
    print("==============================================")
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✅ All tests passed with 100% coverage!")
        print("\n📊 Coverage report: htmlcov/position_manager/index.html")
    else:
        print("\n❌ Tests failed or coverage below 100%")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()