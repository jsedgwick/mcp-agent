"""mcp-agent: A framework for building AI agents with the Model Context Protocol.

This module automatically applies compatibility fixes for asyncio on macOS.
"""

# Apply asyncio compatibility fixes as early as possible
from . utils import asyncio_compat  # noqa: F401