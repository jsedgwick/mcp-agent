"""Instrumentation hook bus for mcp-agent observation.

This module provides a lightweight, zero-dependency hook system that allows
external tools like Inspector to observe mcp-agent behavior without runtime
patching.

Version: 1.0 (2025-07-11)
See docs/inspector/instrumentation-hooks.md for the formal contract.
"""

import logging
import threading
from inspect import iscoroutinefunction
from typing import Any, Awaitable, Callable, Dict, List

__all__ = ["register", "unregister", "_emit"]

_logger = logging.getLogger("mcp.instrument")

# Type aliases
_Callback = Callable[..., Any | Awaitable[Any]]

# Global hook registry with thread safety
_hooks: Dict[str, List[_Callback]] = {}
_hooks_lock = threading.RLock()


def register(name: str, fn: _Callback) -> None:
    """Subscribe to a hook.

    The callback function will be invoked when the named hook is emitted.
    If the callback is a coroutine function, it will be awaited.
    The return value is always ignored.

    Thread-safe: Can be called from any thread.

    Args:
        name: The hook name to subscribe to (e.g., "before_llm_generate")
        fn: The callback function to invoke when the hook fires

    Examples:
        >>> def my_callback(llm, prompt, **kwargs):
        ...     print(f"LLM called with prompt: {prompt}")
        >>> register("before_llm_generate", my_callback)

        >>> async def async_callback(tool_name, args, **kwargs):
        ...     await log_tool_call(tool_name, args)
        >>> register("before_tool_call", async_callback)
    """
    with _hooks_lock:
        if name not in _hooks:
            _hooks[name] = []
        _hooks[name].append(fn)


def unregister(name: str, fn: _Callback) -> None:
    """Remove a previously registered callback.

    This function is idempotent - calling it multiple times or with
    a callback that was never registered will not raise an error.

    Thread-safe: Can be called from any thread.

    Args:
        name: The hook name to unsubscribe from
        fn: The callback function to remove

    Examples:
        >>> def my_callback(**kwargs): pass
        >>> register("before_llm_generate", my_callback)
        >>> unregister("before_llm_generate", my_callback)
    """
    with _hooks_lock:
        callbacks = _hooks.get(name, [])
        if fn in callbacks:
            callbacks.remove(fn)


async def _emit(name: str, *args: Any, **kwargs: Any) -> None:
    """Internal: Emit a hook event to all registered callbacks.

    This function fans out to all callbacks registered for the given hook name.
    Callbacks are invoked in FIFO order (first registered, first called).

    If a callback raises an exception, it is logged and swallowed to ensure
    that instrumentation never breaks application code.

    Thread-safe: Makes a snapshot of callbacks to avoid iteration issues.

    Note: This function is private and should only be called by mcp-agent
    core code. External code should use register() to observe events.

    Args:
        name: The hook name to emit
        *args: Positional arguments (discouraged, use kwargs)
        **kwargs: Keyword arguments to pass to callbacks

    Examples:
        >>> # In mcp-agent core code only:
        >>> await _emit("before_llm_generate", llm=self, prompt=prompt)
    """
    # Fast path: skip if no subscribers
    # Use get() to avoid creating empty lists in defaultdict
    with _hooks_lock:
        callbacks = _hooks.get(name)
        if not callbacks:
            return
        # Make a copy to avoid issues if callbacks are modified during iteration
        callbacks = list(callbacks)

    # Release lock before executing callbacks to avoid deadlocks
    for cb in callbacks:
        try:
            if iscoroutinefunction(cb):
                await cb(*args, **kwargs)
            else:
                cb(*args, **kwargs)
        except Exception:  # noqa: BLE001
            _logger.exception("Hook %s failed in %s", name, cb)
