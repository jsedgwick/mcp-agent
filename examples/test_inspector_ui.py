#!/usr/bin/env python
"""
Example script demonstrating the Inspector UI integration.

Run this script to start the Inspector in standalone mode:
    python examples/test_inspector_ui.py

Then open your browser to:
    http://localhost:7800/_inspector/ui/

You should see the "Inspector Online" message and the backend version.
"""

import sys
import time

try:
    from mcp_agent.inspector import mount
except ImportError as e:
    print(f"Error: {e}", file=sys.stderr)
    print("\nPlease install mcp-agent with inspector support:", file=sys.stderr)
    print("  pip install 'mcp-agent[inspector]'", file=sys.stderr)
    sys.exit(1)

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
    try:
        mount()
    except Exception as e:
        print(f"\nError starting inspector: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Keep the server running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down inspector...")
        sys.exit(0)