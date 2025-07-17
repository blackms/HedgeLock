"""
Main entry point for Position Manager service.
"""

import logging
import uvicorn
from hedgelock.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


def main():
    """Run the Position Manager API server."""
    logger.info("Starting Position Manager service...")
    
    uvicorn.run(
        "hedgelock.position_manager.api:app",
        host="0.0.0.0",
        port=8009,
        log_level="info"
    )


if __name__ == "__main__":
    main()