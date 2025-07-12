"""
mcp-agent-inspector: Zero-dependency debugging and observability tool for mcp-agent.
"""

# re-export public API — ignore "unused import" warnings
from .gateway import mount  # noqa: F401
from .version import __version__  # noqa: F401
from .decorators import dump_state_to_span, capture_state  # noqa: F401
from .span_meta import SpanMeta  # noqa: F401
from . import context  # noqa: F401
from .subscribers import register_all_subscribers, unregister_all_subscribers  # noqa: F401

__all__ = [
    "mount",
    "__version__",
    "dump_state_to_span",
    "capture_state",
    "SpanMeta",
    "context",
    "register_all_subscribers",
    "unregister_all_subscribers",
]