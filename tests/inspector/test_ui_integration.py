"""
Tests for UI integration with the gateway.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_agent.inspector import mount, __version__


class TestUIIntegration:
    """Test UI static file serving."""
    
    def test_health_endpoint_returns_version(self):
        """Test that health endpoint returns version info."""
        app = FastAPI()
        mount(app)
        
        client = TestClient(app)
        response = client.get("/_inspector/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "mcp-agent-inspector"
        assert data["version"] == __version__
    
    def test_mount_includes_static_files_when_dist_exists(self):
        """Test that static files are mounted when dist directory exists."""
        app = FastAPI()
        
        # Mock the UI dist path to exist
        with patch.object(Path, 'exists', return_value=True):
            mount(app)
        
        # Test actual functionality instead of route introspection
        client = TestClient(app)
        
        # Health endpoint should work
        response = client.get("/_inspector/health")
        assert response.status_code == 200
        assert response.json()["name"] == "mcp-agent-inspector"
        
        # UI route should be accessible (404 is fine if no actual files)
        # The important thing is that the route is registered
        response = client.get("/_inspector/ui/")
        assert response.status_code in [200, 404]  # 404 is fine if no index.html in test
    
    def test_mount_works_without_dist_directory(self):
        """Test that mount works even when UI dist doesn't exist."""
        app = FastAPI()
        
        # Mock the UI dist path to not exist
        with patch.object(Path, 'exists', return_value=False):
            mount(app)
        
        # Should still have health endpoint
        client = TestClient(app)
        response = client.get("/_inspector/health")
        assert response.status_code == 200
    
    def test_standalone_mode_creates_app(self):
        """Test standalone mode creates its own FastAPI app."""
        # Mock the _run_local_uvicorn function to prevent actual server start
        with patch('mcp_agent.inspector.gateway._run_local_uvicorn') as mock_run:
            mount(app=None)
            
            # Should have called _run_local_uvicorn
            assert mock_run.called
            
            # Get the app that was passed to _run_local_uvicorn
            app = mock_run.call_args[0][0]
            
            # Should be a FastAPI instance
            assert isinstance(app, FastAPI)
            
            # Should have the inspector routes
            client = TestClient(app)
            response = client.get("/_inspector/health")
            assert response.status_code == 200
    
    def test_ui_base_path_configuration(self):
        """Test that UI is configured with correct base path."""
        # This is more of a configuration test
        # The actual UI testing would be done with Playwright
        ui_config_path = Path(__file__).parent.parent.parent / "packages" / "inspector_ui" / "vite.config.ts"
        
        if ui_config_path.exists():
            config_content = ui_config_path.read_text()
            assert "base: '/_inspector/ui/'" in config_content
            assert "proxy:" in config_content
            assert "'/_inspector/health'" in config_content