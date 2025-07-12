#!/usr/bin/env python
"""Test script to verify UI integration with gateway."""

import sys
from pathlib import Path

# Add the src directory to Python path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from mcp_agent.inspector import mount

# Run standalone inspector
print("Starting inspector standalone server...")
mount()

# Keep the server running
try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nShutting down inspector...")