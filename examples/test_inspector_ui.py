#!/usr/bin/env python
"""
Example script demonstrating the Inspector UI integration.

Run this script to start the Inspector in standalone mode:
    python examples/test_inspector_ui.py

Then open your browser to:
    http://localhost:7800/_inspector/ui/

You should see the "Inspector Online" message and the backend version.
"""

from mcp_agent.inspector import mount

if __name__ == "__main__":
    print("Starting mcp-agent-inspector...")
    print("")
    print("The Inspector UI is available at:")
    print("  http://localhost:7800/_inspector/ui/")
    print("")
    print("API endpoints:")
    print("  Health: http://localhost:7800/_inspector/health")
    print("  Sessions: http://localhost:7800/_inspector/sessions")
    print("")
    print("Press Ctrl+C to stop the server.")
    
    # Start the inspector in standalone mode
    mount()
    
    # Keep the server running
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down inspector...")