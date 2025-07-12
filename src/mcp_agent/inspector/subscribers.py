"""
Hook subscribers for span enrichment in mcp-agent-inspector.

This module contains all the hook subscriber functions that enrich
OpenTelemetry spans with mcp-agent specific attributes.
"""

import json
from typing import Any, Optional

from opentelemetry import trace

from mcp_agent.core import instrument
from .span_meta import SpanMeta, safe_json_attribute
from . import context


# Agent hooks

async def before_agent_call(agent, **_kw) -> None:
    """Capture agent attributes before call."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanMeta.AGENT_CLASS, agent.__class__.__name__)
        span.set_attribute(SpanMeta.AGENT_NAME, agent.name)
        
        # Also set session ID if available
        session_id = context.get()
        if session_id != "unknown":
            span.set_attribute(SpanMeta.SESSION_ID, session_id)


# Workflow hooks

async def before_workflow_run(workflow, context, **_kw) -> None:
    """Capture workflow attributes before run."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanMeta.WORKFLOW_TYPE, workflow.__class__.__name__)
        
        # Capture workflow input if available
        if hasattr(context, "dict"):
            try:
                input_json = json.dumps(context.dict())
                safe_json_attribute(SpanMeta.WORKFLOW_INPUT_JSON, input_json, span)
            except Exception:
                pass


async def after_workflow_run(workflow, context, result, **_kw) -> None:
    """Capture workflow result after run."""
    span = trace.get_current_span()
    if span and span.is_recording():
        # Set success status
        span.set_attribute(SpanMeta.STATUS_CODE, "ok")
        
        # Capture workflow output
        try:
            if hasattr(result, "model_dump_json"):
                output_json = result.model_dump_json()
            elif hasattr(result, "dict"):
                output_json = json.dumps(result.dict())
            else:
                output_json = json.dumps(result)
            
            safe_json_attribute(SpanMeta.WORKFLOW_OUTPUT_JSON, output_json, span)
        except Exception:
            pass


async def error_workflow_run(workflow, context, exc, **_kw) -> None:
    """Capture workflow error information."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanMeta.STATUS_CODE, "error")
        span.set_attribute(SpanMeta.ERROR_CODE, type(exc).__name__)
        span.set_attribute(SpanMeta.ERROR_MESSAGE, str(exc))


# Tool hooks

async def before_tool_call(tool_name, args, context, **_kw) -> None:
    """Capture tool call attributes before execution."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanMeta.TOOL_NAME, tool_name)
        
        # Capture tool input
        try:
            input_json = json.dumps(args)
            safe_json_attribute(SpanMeta.TOOL_INPUT_JSON, input_json, span)
        except Exception:
            pass


async def after_tool_call(tool_name, args, result, context, **_kw) -> None:
    """Capture tool result after execution."""
    span = trace.get_current_span()
    if span and span.is_recording():
        # Capture tool output
        try:
            if hasattr(result, "content"):
                # Handle CallToolResult type
                output_data = {
                    "isError": getattr(result, "isError", False),
                    "content": []
                }
                
                # Extract content
                if hasattr(result, "content") and result.content:
                    for content_item in result.content:
                        if hasattr(content_item, "text"):
                            output_data["content"].append({
                                "type": "text",
                                "text": content_item.text
                            })
                        elif hasattr(content_item, "dict"):
                            output_data["content"].append(content_item.dict())
                        else:
                            output_data["content"].append(str(content_item))
                
                output_json = json.dumps(output_data)
            elif hasattr(result, "dict"):
                output_json = json.dumps(result.dict())
            else:
                output_json = json.dumps(result)
            
            safe_json_attribute(SpanMeta.TOOL_OUTPUT_JSON, output_json, span)
        except Exception:
            pass


async def error_tool_call(tool_name, args, exc, context, **_kw) -> None:
    """Capture tool error information."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(SpanMeta.ERROR_CODE, type(exc).__name__)
        span.set_attribute(SpanMeta.ERROR_MESSAGE, str(exc))


# LLM hooks (these complement the existing hooks in LLM providers)

async def before_llm_generate(llm, prompt, **_kw) -> None:
    """Capture additional LLM attributes before generation."""
    span = trace.get_current_span()
    if span and span.is_recording():
        # Add provider and model info
        if hasattr(llm, "provider"):
            span.set_attribute(SpanMeta.LLM_PROVIDER, llm.provider)
        
        # Model info might be in different places
        model = None
        if hasattr(llm, "model"):
            model = llm.model
        elif hasattr(llm, "default_request_params") and hasattr(llm.default_request_params, "model"):
            model = llm.default_request_params.model
        
        if model:
            span.set_attribute(SpanMeta.LLM_MODEL, model)
        
        # Capture prompt as JSON
        try:
            if isinstance(prompt, str):
                prompt_json = json.dumps({"type": "text", "content": prompt})
            elif hasattr(prompt, "dict"):
                prompt_json = json.dumps(prompt.dict())
            elif isinstance(prompt, list):
                prompt_json = json.dumps(prompt)
            else:
                prompt_json = json.dumps(str(prompt))
            
            safe_json_attribute(SpanMeta.LLM_PROMPT_JSON, prompt_json, span)
        except Exception:
            pass


async def after_llm_generate(llm, prompt, response, **_kw) -> None:
    """Capture LLM response attributes after generation."""
    span = trace.get_current_span()
    if span and span.is_recording():
        # Capture response as JSON
        try:
            if isinstance(response, list):
                # List of response objects
                response_data = []
                for resp in response:
                    if hasattr(resp, "dict"):
                        response_data.append(resp.dict())
                    elif hasattr(resp, "content"):
                        response_data.append({"content": resp.content})
                    else:
                        response_data.append(str(resp))
                response_json = json.dumps(response_data)
            elif hasattr(response, "dict"):
                response_json = json.dumps(response.dict())
            else:
                response_json = json.dumps(str(response))
            
            safe_json_attribute(SpanMeta.LLM_RESPONSE_JSON, response_json, span)
        except Exception:
            pass


def register_all_subscribers() -> None:
    """
    Register all inspector hook subscribers with the instrumentation system.
    
    This should be called once during inspector initialization to enable
    span enrichment throughout the mcp-agent execution.
    
    Examples:
        >>> register_all_subscribers()
        >>> # Now all hooks are registered and will enrich spans
    """
    # Agent hooks
    instrument.register("before_agent_call", before_agent_call)
    
    # Workflow hooks
    instrument.register("before_workflow_run", before_workflow_run)
    instrument.register("after_workflow_run", after_workflow_run)
    instrument.register("error_workflow_run", error_workflow_run)
    
    # Tool hooks
    instrument.register("before_tool_call", before_tool_call)
    instrument.register("after_tool_call", after_tool_call)
    instrument.register("error_tool_call", error_tool_call)
    
    # LLM hooks (complement existing provider hooks)
    instrument.register("before_llm_generate", before_llm_generate)
    instrument.register("after_llm_generate", after_llm_generate)


def unregister_all_subscribers() -> None:
    """
    Unregister all inspector hook subscribers.
    
    This is mainly useful for testing to ensure clean state between tests.
    
    Examples:
        >>> unregister_all_subscribers()
        >>> # All hooks are now unregistered
    """
    # Agent hooks
    instrument.unregister("before_agent_call", before_agent_call)
    
    # Workflow hooks
    instrument.unregister("before_workflow_run", before_workflow_run)
    instrument.unregister("after_workflow_run", after_workflow_run)
    instrument.unregister("error_workflow_run", error_workflow_run)
    
    # Tool hooks
    instrument.unregister("before_tool_call", before_tool_call)
    instrument.unregister("after_tool_call", after_tool_call)
    instrument.unregister("error_tool_call", error_tool_call)
    
    # LLM hooks
    instrument.unregister("before_llm_generate", before_llm_generate)
    instrument.unregister("after_llm_generate", after_llm_generate)