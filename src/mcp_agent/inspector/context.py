"""
Context propagation utilities for mcp-agent-inspector.

This module provides context variable management for session IDs,
enabling spans to be correlated without passing context objects everywhere.
"""

import asyncio
import contextvars
import functools
from typing import Callable, Optional, TypeVar, Union


# Context variable for session ID propagation
_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "session_id", default="unknown"
)


def set(session_id: str) -> None:
    """
    Set the current session ID in the context.
    
    This should be called exactly once at the beginning of a workflow
    or when handling an inbound request.
    
    Args:
        session_id: The session identifier to set
        
    Examples:
        >>> set("test-session-123")
        >>> assert get() == "test-session-123"
    """
    _session_id.set(session_id)


def get() -> str:
    """
    Get the current session ID from the context.
    
    Returns:
        The current session ID, or "unknown" if not set
        
    Examples:
        >>> set("my-session")
        >>> assert get() == "my-session"
    """
    return _session_id.get()


F = TypeVar("F", bound=Callable)


def bind(fn: F) -> F:
    """
    Decorator that injects the current session_id into function kwargs
    if the wrapped function accepts it.
    
    This allows functions to optionally receive the session_id without
    requiring all callers to pass it explicitly.
    
    Args:
        fn: The function to wrap
        
    Returns:
        The wrapped function
        
    Examples:
        >>> @bind
        ... async def my_func(data: str, session_id: str = None):
        ...     return f"{data}-{session_id}"
        >>> set("test-123")
        >>> import asyncio
        >>> result = asyncio.run(my_func("hello"))
        >>> assert result == "hello-test-123"
    """
    
    @functools.wraps(fn)
    async def async_wrapper(*args, **kwargs):
        # Check if function accepts session_id parameter
        if "session_id" in fn.__code__.co_varnames:
            kwargs.setdefault("session_id", get())
        return await fn(*args, **kwargs)
    
    @functools.wraps(fn)
    def sync_wrapper(*args, **kwargs):
        # Check if function accepts session_id parameter
        if "session_id" in fn.__code__.co_varnames:
            kwargs.setdefault("session_id", get())
        return fn(*args, **kwargs)
    
    # Return appropriate wrapper based on function type
    if asyncio.iscoroutinefunction(fn):
        return async_wrapper  # type: ignore
    else:
        return sync_wrapper  # type: ignore