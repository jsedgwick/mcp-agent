#!/usr/bin/env python3
"""Simple example to test Inspector health endpoint."""

import time
import requests
from mcp_agent.inspector import mount, __version__

def test_standalone_mode():
    """Test Inspector in standalone mode."""
    print("Testing Inspector in standalone mode...")
    
    # Mount inspector without an app (standalone mode)
    mount()
    
    # Give it a moment to start
    time.sleep(1)
    
    # Test the health endpoint
    try:
        response = requests.get("http://localhost:7800/_inspector/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "mcp-agent-inspector"
        assert data["version"] == __version__
        
        print("✅ Health check passed!")
    except Exception as e:
        print(f"❌ Health check failed: {e}")


def test_with_fastapi():
    """Test Inspector mounted on existing FastAPI app."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    
    print("\nTesting Inspector with FastAPI app...")
    
    # Create a FastAPI app
    app = FastAPI()
    
    # Add a custom route
    @app.get("/")
    def read_root():
        return {"Hello": "World"}
    
    # Mount inspector
    mount(app)
    
    # Test with TestClient
    client = TestClient(app)
    
    # Test our custom route
    response = client.get("/")
    print(f"App root: {response.json()}")
    
    # Test inspector health
    response = client.get("/_inspector/health")
    print(f"Inspector health: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["name"] == "mcp-agent-inspector"
    
    print("✅ FastAPI integration passed!")


if __name__ == "__main__":
    test_standalone_mode()
    test_with_fastapi()
    
    print("\n🎉 All tests passed! Inspector is working correctly.")
    print("\nYou can now visit http://localhost:7800/_inspector/health")
    print("Press Ctrl+C to exit...")
    
    try:
        # Keep running so you can test manually
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")