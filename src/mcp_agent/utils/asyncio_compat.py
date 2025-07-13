"""Asyncio compatibility utilities for mcp-agent.

This module provides fixes for asyncio compatibility issues, particularly
the child watcher problem on macOS with Python 3.8+.
"""

import asyncio
import sys
from typing import Optional


def ensure_child_watcher_compatibility() -> None:
    """Ensure asyncio child watcher compatibility on macOS.
    
    On macOS with Python 3.8+, asyncio requires an explicit child watcher
    to spawn subprocesses. This is particularly problematic when using
    libraries like OpenTelemetry that create background threads, as any
    event loops created in those threads will lack a child watcher by default.
    
    This function patches the asyncio event loop policy to always return
    a ThreadedChildWatcher when get_child_watcher() would otherwise raise
    NotImplementedError.
    
    This should be called as early as possible in the application lifecycle,
    ideally before any asyncio operations or thread-creating libraries are used.
    """
    if sys.platform == 'win32' or sys.version_info < (3, 8):
        # Only needed on Unix-like systems with Python 3.8+
        return
    
    import asyncio.events
    
    # Save the original get_child_watcher method
    _original_get_child_watcher = asyncio.events.AbstractEventLoopPolicy.get_child_watcher
    
    def patched_get_child_watcher(self):
        """Always return a ThreadedChildWatcher to avoid NotImplementedError."""
        try:
            # Try the original method first
            return _original_get_child_watcher(self)
        except NotImplementedError:
            # If it fails, create and return a ThreadedChildWatcher
            if not hasattr(self, '_threaded_watcher'):
                self._threaded_watcher = asyncio.ThreadedChildWatcher()
                # Try to attach to current loop if available
                try:
                    loop = asyncio.get_running_loop()
                    self._threaded_watcher.attach_loop(loop)
                except RuntimeError:
                    # No running loop, that's OK
                    pass
            return self._threaded_watcher
    
    # Apply the monkey patch
    asyncio.events.AbstractEventLoopPolicy.get_child_watcher = patched_get_child_watcher
    
    # Also try to set a ThreadedChildWatcher for the current policy
    try:
        asyncio.set_child_watcher(asyncio.ThreadedChildWatcher())
    except RuntimeError:
        # May fail if called from a thread without an event loop
        pass


# Apply the fix automatically when this module is imported
ensure_child_watcher_compatibility()