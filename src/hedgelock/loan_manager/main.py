"""
Loan Manager service entry point.
"""

import os
import sys
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hedgelock.loan_manager.api import app
from hedgelock.logging import setup_logging


def main():
    """Run the Loan Manager service."""
    # Setup logging
    setup_logging("loan-manager")
    
    # Get port from environment or use default
    port = int(os.environ.get("LOAN_MANAGER_PORT", "8010"))
    
    # Run the service
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()