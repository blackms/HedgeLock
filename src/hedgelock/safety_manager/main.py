"""
Safety Manager service entry point.
"""

import os
import sys
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hedgelock.safety_manager.api import app
from hedgelock.logging import setup_logging


def main():
    """Run the Safety Manager service."""
    # Setup logging
    setup_logging("safety-manager")
    
    # Get port from environment or use default
    port = int(os.environ.get("SAFETY_MANAGER_PORT", "8012"))
    
    # Run the service
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()