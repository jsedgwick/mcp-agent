"""Unit tests for Inspector mount function."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from mcp_agent.inspector.gateway import mount
from mcp_agent.inspector.settings import InspectorSettings


class TestInspectorMount:
    """Test cases for the Inspector mount function."""
    
    def test_mount_with_disabled_inspector(self):
        """Mount should return early if Inspector is disabled."""
        settings = InspectorSettings(enabled=False)
        app = Mock()
        
        # Temporarily disable the INSPECTOR_ENABLED env var from conftest
        with patch('os.getenv', return_value=''):
            with patch('mcp_agent.inspector.gateway.load_inspector_settings', return_value=settings):
                mount(app)
        
        # Should not create router or start server
        app.include_router.assert_not_called()
    
    def test_mount_with_mcpapp_config(self):
        """Mount should properly read config from MCPApp.config."""
        # Mock MCPApp with config
        app = Mock(spec=['config'])  # Only has config attribute, not include_router
        app.config = Mock()
        app.config.inspector = Mock()
        app.config.inspector.dict = Mock(return_value={
            "enabled": True,
            "port": 7801,
            "host": "127.0.0.1"
        })
        
        with patch('mcp_agent.inspector.gateway._run_local_uvicorn') as mock_run:
            with patch('mcp_agent.inspector.gateway.Path.exists', return_value=True):
                mount(app)
        
        # Should start server since app is not FastAPI
        mock_run.assert_called_once()
        # Check that the settings were loaded correctly
        standalone_app, settings = mock_run.call_args[0]
        assert settings.port == 7801
    
    def test_mount_with_fastapi_app(self):
        """Mount should mount on existing FastAPI app."""
        # Mock FastAPI app
        app = Mock()
        app.include_router = Mock()
        app.mount = Mock()
        app.state = Mock()
        
        settings = InspectorSettings(enabled=True)
        
        with patch('mcp_agent.inspector.gateway.load_inspector_settings', return_value=settings):
            with patch('mcp_agent.inspector.gateway.Path.exists', return_value=True):
                mount(app)
        
        # Should mount router
        app.include_router.assert_called_once()
        # Should mount static files
        app.mount.assert_called_once()
    
    def test_mount_standalone_mode(self):
        """Mount with no app should create standalone server."""
        settings = InspectorSettings(enabled=True, port=7802)
        
        with patch('mcp_agent.inspector.gateway.load_inspector_settings', return_value=settings):
            with patch('mcp_agent.inspector.gateway._run_local_uvicorn') as mock_run:
                with patch('mcp_agent.inspector.gateway.Path.exists', return_value=True):
                    mount(None)
        
        # Should create and run standalone app
        mock_run.assert_called_once()
        standalone_app = mock_run.call_args[0][0]
        assert hasattr(standalone_app, 'state')
        assert standalone_app.state.inspector_settings == settings
    
    def test_mount_respects_env_override(self):
        """Mount should respect INSPECTOR_ENABLED env var."""
        settings = InspectorSettings(enabled=False)
        app = Mock(spec=[])  # No include_router attribute
        
        with patch('mcp_agent.inspector.gateway.load_inspector_settings', return_value=settings):
            with patch('os.getenv', return_value='true'):
                with patch('mcp_agent.inspector.gateway._run_local_uvicorn') as mock_run:
                    with patch('mcp_agent.inspector.gateway.Path.exists', return_value=True):
                        mount(app)
        
        # Should start server despite settings.enabled=False
        mock_run.assert_called_once()
    
    def test_mount_handles_missing_ui_files(self):
        """Mount should handle missing UI dist files gracefully."""
        app = Mock()
        app.include_router = Mock()
        app.mount = Mock()
        app.state = Mock()
        
        settings = InspectorSettings(enabled=True)
        
        with patch('mcp_agent.inspector.gateway.load_inspector_settings', return_value=settings):
            with patch('mcp_agent.inspector.gateway.Path.exists', return_value=False):
                mount(app)
        
        # Should mount router even without UI files
        app.include_router.assert_called_once()
        # Should not mount static files when UI doesn't exist
        app.mount.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_mount_with_custom_settings(self):
        """Mount should accept custom settings parameter."""
        app = Mock(spec=[])  # No include_router attribute
        custom_settings = InspectorSettings(
            enabled=True,
            port=8000,
            host="0.0.0.0",
            debug={"debug": True}
        )
        
        with patch('mcp_agent.inspector.gateway._run_local_uvicorn') as mock_run:
            with patch('mcp_agent.inspector.gateway.Path.exists', return_value=True):
                mount(app, settings=custom_settings)
        
        # Should use custom settings
        mock_run.assert_called_once()
        standalone_app, used_settings = mock_run.call_args[0]
        assert used_settings == custom_settings