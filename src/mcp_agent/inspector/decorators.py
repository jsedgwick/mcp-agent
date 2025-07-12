"""
Decorators for automatic span enrichment in mcp-agent-inspector.

This module provides decorators that automatically capture function
return values and add them as span attributes.
"""

import asyncio
import functools
import json
from typing import Any, Callable, Optional, TypeVar, Union

from opentelemetry import trace

from .span_meta import SpanMeta, safe_json_attribute


F = TypeVar("F", bound=Callable[..., Any])


def dump_state_to_span(description: Optional[str] = None) -> Callable[[F], F]:
    """
    Decorator that automatically captures function return values as span attributes.
    
    The return value is serialized to JSON and stored as either:
    - mcp.result.<description>_json if description is provided
    - mcp.result.<function_name>_json if description is not provided
    
    Args:
        description: Optional custom description for the attribute name.
                    If not provided, uses the function name.
    
    Returns:
        Decorator function
        
    Examples:
        >>> @dump_state_to_span(description="plan")
        ... def create_plan() -> dict:
        ...     return {"steps": ["analyze", "execute"]}
        
        >>> @dump_state_to_span()  # Uses function name
        ... async def get_router_decision() -> dict:
        ...     return {"route": "primary", "confidence": 0.95}
    """
    
    def decorator(func: F) -> F:
        # Determine the attribute key
        if description:
            attr_key = f"{SpanMeta.RESULT_PREFIX}{description}_json"
        else:
            # Convert function name to snake_case if needed
            func_name = func.__name__
            attr_key = f"{SpanMeta.RESULT_PREFIX}{func_name}_json"
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            _capture_result(attr_key, result)
            return result
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            _capture_result(attr_key, result)
            return result
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore
    
    return decorator


def _capture_result(attr_key: str, result: Any) -> None:
    """
    Capture a result value as a span attribute.
    
    Args:
        attr_key: The attribute key to use
        result: The result value to capture
    """
    span = trace.get_current_span()
    if not span or not span.is_recording():
        return
    
    try:
        # Handle different result types
        if hasattr(result, "model_dump_json"):
            # Pydantic model with efficient JSON serialization
            json_str = result.model_dump_json()
        elif hasattr(result, "dict"):
            # Objects with dict method
            json_str = json.dumps(result.dict())
        elif hasattr(result, "__dict__"):
            # Regular objects
            json_str = json.dumps(result.__dict__)
        else:
            # Primitive types or already dict-like
            json_str = json.dumps(result)
        
        # Set the attribute with size limits
        safe_json_attribute(attr_key, json_str, span)
        
    except Exception:
        # If serialization fails, just skip - don't break the function
        # This follows the principle that telemetry should never break the app
        pass


def capture_state(description: str, state: Any) -> None:
    """
    Manually capture arbitrary state to the current span.
    
    The state is serialized to JSON and stored as mcp.state.<description>_json.
    
    Args:
        description: Description for the state being captured
        state: The state object to capture
        
    Examples:
        >>> from unittest.mock import Mock
        >>> span = Mock()
        >>> # In real code, this would be within an active span
        >>> capture_state("checkpoint", {"progress": 50, "status": "running"})
    """
    span = trace.get_current_span()
    if not span or not span.is_recording():
        return
    
    attr_key = f"{SpanMeta.STATE_PREFIX}{description}_json"
    
    try:
        # Serialize the state
        if hasattr(state, "model_dump_json"):
            json_str = state.model_dump_json()
        elif hasattr(state, "dict"):
            json_str = json.dumps(state.dict())
        elif hasattr(state, "__dict__"):
            json_str = json.dumps(state.__dict__)
        else:
            json_str = json.dumps(state)
        
        # Set the attribute with size limits
        safe_json_attribute(attr_key, json_str, span)
        
    except Exception:
        # Silent failure - telemetry should not break the app
        pass