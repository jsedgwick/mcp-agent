#!/usr/bin/env python
"""Test script to verify UI integration with gateway."""

import sys
import time
from pathlib import Path

# Add the src directory to Python path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

try:
    from mcp_agent.inspector import mount
except ImportError as e:
    print(f"Error importing inspector: {e}", file=sys.stderr)
    print("\nMake sure you're running from the project root with:", file=sys.stderr)
    print("  uv run python packages/inspector_ui/test_ui.py", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    # Run standalone inspector
    print("Starting inspector standalone server...")
    print("Open http://localhost:7800/_inspector/ui/ in your browser")
    print("Press Ctrl+C to stop the server.")
    
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