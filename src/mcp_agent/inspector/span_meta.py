"""
Span attribute metadata and constants for mcp-agent-inspector.

This module defines all span attribute names following the mcp.* namespace
convention and provides utilities for attribute size management.
"""

from typing import Final


class SpanMeta:
    """
    Constants for OpenTelemetry span attribute names.
    
    All attributes follow the mcp.* namespace convention as defined in
    the telemetry specification.
    """
    
    # Size limits
    MAX_ATTRIBUTE_SIZE: Final[int] = 30 * 1024  # 30KB per attribute
    
    # Session and context attributes
    SESSION_ID: Final[str] = "session.id"
    
    # Agent attributes
    AGENT_CLASS: Final[str] = "mcp.agent.class"
    AGENT_NAME: Final[str] = "mcp.agent.name"
    
    # Workflow attributes
    WORKFLOW_TYPE: Final[str] = "mcp.workflow.type"
    WORKFLOW_INPUT_JSON: Final[str] = "mcp.workflow.input_json"
    WORKFLOW_OUTPUT_JSON: Final[str] = "mcp.workflow.output_json"
    
    # Tool attributes
    TOOL_NAME: Final[str] = "mcp.tool.name"
    TOOL_INPUT_JSON: Final[str] = "mcp.tool.input_json"
    TOOL_OUTPUT_JSON: Final[str] = "mcp.tool.output_json"
    TOOL_STRUCTURED_OUTPUT_JSON: Final[str] = "mcp.tool.structured_output_json"
    
    # LLM attributes (already captured by LLM hooks)
    LLM_PROMPT_JSON: Final[str] = "mcp.llm.prompt_json"
    LLM_RESPONSE_JSON: Final[str] = "mcp.llm.response_json"
    LLM_PROVIDER: Final[str] = "mcp.llm.provider"
    LLM_MODEL: Final[str] = "mcp.llm.model"
    
    # State and result attributes
    # These use dynamic naming: mcp.state.<description>_json or mcp.result.<description>_json
    STATE_PREFIX: Final[str] = "mcp.state."
    RESULT_PREFIX: Final[str] = "mcp.result."
    
    # Model selection attributes
    MODEL_PREFERENCES_JSON: Final[str] = "mcp.model.preferences_json"
    
    # Resource attributes
    RESOURCE_URI: Final[str] = "mcp.resource.uri"
    RESOURCE_MIME_TYPE: Final[str] = "mcp.resource.mime_type"
    RESOURCE_BYTES: Final[str] = "mcp.resource.bytes"
    
    # Prompt attributes
    PROMPT_TEMPLATE_ID: Final[str] = "mcp.prompt.template_id"
    PROMPT_PARAMETERS_JSON: Final[str] = "mcp.prompt.parameters_json"
    
    # Progress and cancellation
    PROGRESS_TOKEN: Final[str] = "mcp.progress.token"
    CANCELLATION_REQUESTED: Final[str] = "mcp.cancellation.requested"
    
    # Error attributes
    STATUS_CODE: Final[str] = "mcp.status.code"
    ERROR_CODE: Final[str] = "mcp.error.code"
    ERROR_MESSAGE: Final[str] = "mcp.error.message"
    STOP_REASON: Final[str] = "mcp.stop_reason"


def truncate_attribute(value: str, max_size: int = SpanMeta.MAX_ATTRIBUTE_SIZE) -> tuple[str, bool]:
    """
    Truncate an attribute value if it exceeds the maximum size.
    
    Args:
        value: The attribute value to potentially truncate
        max_size: Maximum allowed size in bytes
        
    Returns:
        A tuple of (truncated_value, was_truncated)
        
    Examples:
        >>> val, truncated = truncate_attribute("small string")
        >>> assert not truncated
        >>> assert val == "small string"
        
        >>> large = "x" * 40000
        >>> val, truncated = truncate_attribute(large)
        >>> assert truncated
        >>> assert len(val) == 30 * 1024
    """
    if len(value) <= max_size:
        return value, False
    return value[:max_size], True


def safe_json_attribute(key: str, value: str, span) -> None:
    """
    Safely set a JSON attribute on a span with size limits.
    
    If the value exceeds MAX_ATTRIBUTE_SIZE, it will be truncated and
    a {key}_truncated=True attribute will be added.
    
    Args:
        key: The attribute key
        value: The JSON string value
        span: The OpenTelemetry span
        
    Examples:
        >>> from unittest.mock import Mock
        >>> span = Mock()
        >>> safe_json_attribute("mcp.state.test_json", '{"data": "value"}', span)
        >>> span.set_attribute.assert_called_once_with("mcp.state.test_json", '{"data": "value"}')
    """
    truncated_value, was_truncated = truncate_attribute(value)
    
    if was_truncated:
        span.set_attribute(f"{key}_truncated", True)
    
    span.set_attribute(key, truncated_value)