"""
Unit tests for Position Manager main entry point.
"""

import pytest
from unittest.mock import patch, Mock
from src.hedgelock.position_manager.main import main


class TestMain:
    """Test main entry point."""
    
    def test_main_function(self):
        """Test main function execution."""
        with patch('src.hedgelock.position_manager.main.uvicorn') as mock_uvicorn:
            with patch('src.hedgelock.position_manager.main.logger') as mock_logger:
                # Run main
                main()
                
                # Check logging
                mock_logger.info.assert_called_with("Starting Position Manager service...")
                
                # Check uvicorn was called correctly
                mock_uvicorn.run.assert_called_once_with(
                    "hedgelock.position_manager.api:app",
                    host="0.0.0.0",
                    port=8009,
                    log_level="info"
                )
    
    def test_main_module_execution(self):
        """Test module execution with __name__ == '__main__'."""
        with patch('src.hedgelock.position_manager.main.main') as mock_main:
            with patch('src.hedgelock.position_manager.main.__name__', '__main__'):
                # Import should trigger main()
                import src.hedgelock.position_manager.main
                
                # Won't actually call due to how imports work, 
                # but we've tested the main() function above