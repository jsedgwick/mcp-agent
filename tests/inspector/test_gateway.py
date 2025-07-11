"""Tests for the Inspector gateway module."""

import asyncio
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_agent.inspector import __version__, mount
from mcp_agent.inspector.gateway import _router, health


class TestHealthEndpoint:
    """Test the health check endpoint directly."""
    
    @pytest.mark.asyncio
    async def test_health_returns_correct_response(self):
        """Health endpoint should return name and version."""
        response = await health()
        data = response.body.decode()
        import json
        result = json.loads(data)
        
        assert result["name"] == "mcp-agent-inspector"
        assert result["version"] == __version__


class TestMountFunction:
    """Test the mount() function behavior."""
    
    def test_mount_on_existing_app(self):
        """mount() should attach routes to existing FastAPI app."""
        app = FastAPI()
        
        # Mount inspector
        mount(app)
        
        # Create test client
        client = TestClient(app)
        
        # Test health endpoint
        response = client.get("/_inspector/health")
        assert response.status_code == 200
        assert response.json() == {
            "name": "mcp-agent-inspector",
            "version": __version__
        }
    
    def test_mount_with_custom_port_env(self):
        """mount() should respect INSPECTOR_PORT environment variable."""
        # Set custom port
        os.environ["INSPECTOR_PORT"] = "7801"
        
        try:
            with patch("mcp_agent.inspector.gateway.threading.Thread") as mock_thread:
                with patch("uvicorn.Server") as mock_server:
                    with patch("uvicorn.Config") as mock_config:
                        # Call mount without app (standalone mode)
                        mount()
                        
                        # Verify uvicorn.Config was called with correct port
                        mock_config.assert_called_once()
                        args = mock_config.call_args
                        assert args[1]["port"] == 7801
                        
                        # Verify thread was started
                        mock_thread.return_value.start.assert_called_once()
        finally:
            # Clean up
            del os.environ["INSPECTOR_PORT"]
    
    def test_mount_standalone_mode(self):
        """mount() without app should spawn internal server."""
        with patch("mcp_agent.inspector.gateway.threading.Thread") as mock_thread:
            with patch("uvicorn.Server") as mock_server:
                with patch("uvicorn.Config") as mock_config:
                    with patch("builtins.print") as mock_print:
                        # Call mount without app
                        mount()
                        
                        # Verify server was created
                        mock_server.assert_called_once()
                        
                        # Verify thread was created and started
                        mock_thread.assert_called_once()
                        mock_thread.return_value.start.assert_called_once()
                        
                        # Verify print message
                        mock_print.assert_called_with(
                            "Inspector running at http://127.0.0.1:7800/_inspector/ui"
                        )
    
    def test_mount_with_expose_not_implemented(self):
        """mount() with expose=True should raise NotImplementedError."""
        with pytest.raises(NotImplementedError, match="External exposure not yet implemented"):
            mount(expose=True)
    
    def test_mount_with_auth_not_implemented(self):
        """mount() with auth should raise NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Authentication not yet implemented"):
            mount(auth={"some": "auth"})
    
    def test_mount_registers_atexit_handler(self):
        """mount() in standalone mode should register atexit handler."""
        with patch("mcp_agent.inspector.gateway.atexit.register") as mock_atexit:
            with patch("mcp_agent.inspector.gateway.threading.Thread"):
                with patch("uvicorn.Server"):
                    with patch("uvicorn.Config"):
                        mount()
                        
                        # Verify atexit handler was registered
                        mock_atexit.assert_called_once()
    
    def test_router_has_correct_prefix(self):
        """Router should have /_inspector prefix."""
        assert _router.prefix == "/_inspector"
    
    def test_health_endpoint_not_in_schema(self):
        """Health endpoint should not be included in OpenAPI schema."""
        # The health endpoint is configured with include_in_schema=False
        # Let's verify by checking the route decorator
        app = FastAPI()
        app.include_router(_router)
        
        # Check in the app's routes
        health_found = False
        for route in app.routes:
            if hasattr(route, 'path') and route.path == "/_inspector/health":
                health_found = True
                # FastAPI routes have include_in_schema attribute
                if hasattr(route, 'include_in_schema'):
                    assert route.include_in_schema is False
                break
        
        assert health_found, "Health endpoint not found in app routes"


class TestIntegration:
    """Integration tests with real server spawning."""
    
    @pytest.mark.skipif(
        os.environ.get("CI") == "true",
        reason="Skip real server tests in CI"
    )
    def test_real_standalone_server(self):
        """Test actual server spawning in standalone mode."""
        # Use a custom port to avoid conflicts
        os.environ["INSPECTOR_PORT"] = "7899"
        
        try:
            # Mount in standalone mode
            mount()
            
            # Give server time to start
            time.sleep(1)
            
            # Try to connect
            import requests
            response = requests.get("http://127.0.0.1:7899/_inspector/health")
            
            assert response.status_code == 200
            assert response.json() == {
                "name": "mcp-agent-inspector",
                "version": __version__
            }
        finally:
            # Clean up
            del os.environ["INSPECTOR_PORT"]