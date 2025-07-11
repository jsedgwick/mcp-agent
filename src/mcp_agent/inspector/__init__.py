"""
mcp-agent-inspector: Zero-dependency debugging and observability tool for mcp-agent.
"""

# re-export public API — ignore "unused import" warnings
from .gateway import mount  # noqa: F401
from .version import __version__  # noqa: F401

__all__ = ["mount", "__version__"]