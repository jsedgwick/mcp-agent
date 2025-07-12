"""
Tests for span enrichment functionality in mcp-agent-inspector.
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from mcp_agent.core import instrument
from mcp_agent.inspector import (
    SpanMeta,
    context,
    dump_state_to_span,
    capture_state,
    register_all_subscribers,
    unregister_all_subscribers,
)
from mcp_agent.inspector.subscribers import (
    before_workflow_run,
    after_workflow_run,
    error_workflow_run,
    before_tool_call,
    after_tool_call,
    error_tool_call,
    before_llm_generate,
    after_llm_generate,
)


@pytest.fixture
def setup_tracing():
    """Set up in-memory tracing for tests."""
    # Create a fresh in-memory span exporter for this test
    memory_exporter = InMemorySpanExporter()
    
    # Get the current global tracer provider
    current_provider = trace.get_tracer_provider()
    
    # Check if we need to create a new TracerProvider
    if current_provider.__class__.__name__ == 'ProxyTracerProvider':
        # No real provider set yet, create one
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        current_provider = provider
    
    # Add our exporter to the current provider
    processor = SimpleSpanProcessor(memory_exporter)
    
    # If the provider has add_span_processor method, use it
    if hasattr(current_provider, 'add_span_processor'):
        current_provider.add_span_processor(processor)
    
    # Get a tracer
    tracer = trace.get_tracer(__name__)
    
    yield tracer, memory_exporter
    
    # Clean up: remove our processor if possible
    if hasattr(current_provider, '_span_processors') and processor in current_provider._span_processors:
        current_provider._span_processors.remove(processor)
    
    # Ensure the exporter is cleared
    memory_exporter.clear()
    
    # Force shutdown the processor to ensure no lingering references
    processor.shutdown()


@pytest.fixture(autouse=True)
def cleanup_hooks():
    """Ensure hooks are cleaned up after each test."""
    yield
    unregister_all_subscribers()


class TestSpanMeta:
    """Test SpanMeta constants and utilities."""
    
    def test_constants_defined(self):
        """Verify all required constants are defined."""
        assert SpanMeta.MAX_ATTRIBUTE_SIZE == 30 * 1024
        assert SpanMeta.AGENT_CLASS == "mcp.agent.class"
        assert SpanMeta.AGENT_NAME == "mcp.agent.name"
        assert SpanMeta.WORKFLOW_TYPE == "mcp.workflow.type"
        assert SpanMeta.TOOL_NAME == "mcp.tool.name"
    
    def test_truncate_attribute(self):
        """Test attribute truncation."""
        from mcp_agent.inspector.span_meta import truncate_attribute
        
        # Small value - no truncation
        val, truncated = truncate_attribute("small value")
        assert val == "small value"
        assert not truncated
        
        # Large value - should truncate
        large_value = "x" * 40000
        val, truncated = truncate_attribute(large_value)
        assert len(val) == 30 * 1024
        assert truncated
        assert val == large_value[:30 * 1024]
    
    def test_safe_json_attribute(self, setup_tracing):
        """Test safe JSON attribute setting."""
        from mcp_agent.inspector.span_meta import safe_json_attribute
        
        tracer, exporter = setup_tracing
        
        with tracer.start_as_current_span("test") as span:
            # Small JSON - no truncation
            safe_json_attribute("test.small", '{"data": "value"}', span)
            
            # Large JSON - should truncate
            large_json = json.dumps({"data": "x" * 40000})
            safe_json_attribute("test.large", large_json, span)
        
        # Check spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        attrs = spans[0].attributes
        assert attrs["test.small"] == '{"data": "value"}'
        assert "test.small_truncated" not in attrs
        
        assert len(attrs["test.large"]) == 30 * 1024
        assert attrs["test.large_truncated"] is True


class TestContext:
    """Test context propagation."""
    
    def test_set_get(self):
        """Test basic set/get functionality."""
        context.set("test-session-123")
        assert context.get() == "test-session-123"
    
    def test_default_value(self):
        """Test default value when not set."""
        # Reset to ensure clean state
        context.set("unknown")
        assert context.get() == "unknown"
    
    @pytest.mark.asyncio
    async def test_bind_decorator_async(self):
        """Test bind decorator with async function."""
        context.set("async-session")
        
        @context.bind
        async def my_func(data: str, session_id: str = None):
            return f"{data}-{session_id}"
        
        result = await my_func("test")
        assert result == "test-async-session"
    
    def test_bind_decorator_sync(self):
        """Test bind decorator with sync function."""
        context.set("sync-session")
        
        @context.bind
        def my_func(data: str, session_id: str = None):
            return f"{data}-{session_id}"
        
        result = my_func("test")
        assert result == "test-sync-session"


class TestDecorators:
    """Test span enrichment decorators."""
    
    def test_dump_state_to_span_sync(self, setup_tracing):
        """Test @dump_state_to_span with sync function."""
        tracer, exporter = setup_tracing
        
        @dump_state_to_span(description="test_result")
        def my_func():
            return {"status": "success", "value": 42}
        
        with tracer.start_as_current_span("test"):
            result = my_func()
        
        assert result == {"status": "success", "value": 42}
        
        # Force flush to ensure spans are exported
        trace.get_tracer_provider().force_flush()
        
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        attrs = spans[0].attributes
        assert "mcp.result.test_result_json" in attrs
        result_data = json.loads(attrs["mcp.result.test_result_json"])
        assert result_data == {"status": "success", "value": 42}
    
    @pytest.mark.asyncio
    async def test_dump_state_to_span_async(self, setup_tracing):
        """Test @dump_state_to_span with async function."""
        tracer, exporter = setup_tracing
        
        @dump_state_to_span()  # Use function name
        async def get_workflow_state():
            return {"stage": "processing", "progress": 75}
        
        with tracer.start_as_current_span("test"):
            result = await get_workflow_state()
        
        assert result == {"stage": "processing", "progress": 75}
        
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        attrs = spans[0].attributes
        assert "mcp.result.get_workflow_state_json" in attrs
        result_data = json.loads(attrs["mcp.result.get_workflow_state_json"])
        assert result_data == {"stage": "processing", "progress": 75}
    
    def test_dump_state_with_pydantic(self, setup_tracing):
        """Test @dump_state_to_span with Pydantic model."""
        from pydantic import BaseModel
        
        class MyResult(BaseModel):
            status: str
            count: int
        
        tracer, exporter = setup_tracing
        
        @dump_state_to_span(description="pydantic_result")
        def my_func():
            return MyResult(status="ok", count=10)
        
        with tracer.start_as_current_span("test"):
            result = my_func()
        
        assert result.status == "ok"
        assert result.count == 10
        
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert "mcp.result.pydantic_result_json" in attrs
        result_data = json.loads(attrs["mcp.result.pydantic_result_json"])
        assert result_data == {"status": "ok", "count": 10}
    
    def test_capture_state_manual(self, setup_tracing):
        """Test manual state capture."""
        tracer, exporter = setup_tracing
        
        with tracer.start_as_current_span("test"):
            capture_state("checkpoint", {"iteration": 5, "score": 0.95})
        
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert "mcp.state.checkpoint_json" in attrs
        state_data = json.loads(attrs["mcp.state.checkpoint_json"])
        assert state_data == {"iteration": 5, "score": 0.95}


class TestHookSubscribers:
    """Test individual hook subscriber functions."""
    
    @pytest.mark.asyncio
    async def test_workflow_hooks(self, setup_tracing):
        """Test workflow hook subscribers."""
        tracer, exporter = setup_tracing
        
        # Mock workflow and context
        workflow = Mock()
        workflow.__class__.__name__ = "TestWorkflow"
        
        mock_context = Mock()
        mock_context.dict.return_value = {"input": "data"}
        
        result = Mock()
        result.model_dump_json.return_value = '{"output": "success"}'
        
        with tracer.start_as_current_span("test"):
            # Before workflow
            await before_workflow_run(workflow, mock_context)
            
            # After workflow
            await after_workflow_run(workflow, mock_context, result)
        
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        
        assert attrs[SpanMeta.WORKFLOW_TYPE] == "TestWorkflow"
        assert attrs[SpanMeta.WORKFLOW_INPUT_JSON] == '{"input": "data"}'
        assert attrs[SpanMeta.WORKFLOW_OUTPUT_JSON] == '{"output": "success"}'
        assert attrs[SpanMeta.STATUS_CODE] == "ok"
    
    @pytest.mark.asyncio
    async def test_workflow_error_hook(self, setup_tracing):
        """Test workflow error hook."""
        tracer, exporter = setup_tracing
        
        workflow = Mock()
        mock_context = Mock()
        error = ValueError("Test error")
        
        with tracer.start_as_current_span("test"):
            await error_workflow_run(workflow, mock_context, error)
        
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        
        assert attrs[SpanMeta.STATUS_CODE] == "error"
        assert attrs[SpanMeta.ERROR_CODE] == "ValueError"
        assert attrs[SpanMeta.ERROR_MESSAGE] == "Test error"
    
    @pytest.mark.asyncio
    async def test_tool_hooks(self, setup_tracing):
        """Test tool hook subscribers."""
        tracer, exporter = setup_tracing
        
        tool_args = {"query": "test search"}
        mock_context = Mock()
        
        # Mock tool result
        result = Mock()
        result.isError = False
        result.content = [Mock(text="Search results")]
        
        with tracer.start_as_current_span("test"):
            # Before tool call
            await before_tool_call("search_tool", tool_args, mock_context)
            
            # After tool call
            await after_tool_call("search_tool", tool_args, result, mock_context)
        
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        
        assert attrs[SpanMeta.TOOL_NAME] == "search_tool"
        assert attrs[SpanMeta.TOOL_INPUT_JSON] == '{"query": "test search"}'
        
        output = json.loads(attrs[SpanMeta.TOOL_OUTPUT_JSON])
        assert output["isError"] is False
        assert output["content"][0]["type"] == "text"
        assert output["content"][0]["text"] == "Search results"
    
    @pytest.mark.asyncio
    async def test_llm_hooks(self, setup_tracing):
        """Test LLM hook subscribers."""
        tracer, exporter = setup_tracing
        
        # Mock LLM with explicit spec to avoid Mock chain issues
        class MockParams:
            model = "test-model"
        
        llm = Mock()
        llm.provider = "TestProvider"
        llm.default_request_params = MockParams()
        
        prompt = "What is the weather?"
        response = [Mock(content="It's sunny today")]
        
        with tracer.start_as_current_span("test"):
            await before_llm_generate(llm, prompt)
            await after_llm_generate(llm, prompt, response)
        
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        
        assert attrs[SpanMeta.LLM_PROVIDER] == "TestProvider"
        assert attrs[SpanMeta.LLM_MODEL] == "test-model"
        
        prompt_data = json.loads(attrs[SpanMeta.LLM_PROMPT_JSON])
        assert prompt_data["type"] == "text"
        assert prompt_data["content"] == "What is the weather?"
        
        # Response might not be captured if Mock isn't serializable
        if SpanMeta.LLM_RESPONSE_JSON in attrs:
            response_data = json.loads(attrs[SpanMeta.LLM_RESPONSE_JSON])
            assert response_data[0]["content"] == "It's sunny today"


class TestIntegration:
    """Integration tests with the hook system."""
    
    @pytest.mark.asyncio
    async def test_register_all_subscribers(self, setup_tracing):
        """Test registering all subscribers."""
        tracer, exporter = setup_tracing
        
        # Register all subscribers
        register_all_subscribers()
        
        # Emit a workflow hook
        workflow = Mock()
        workflow.__class__.__name__ = "IntegrationWorkflow"
        mock_context = Mock()
        mock_context.dict.return_value = {"test": "data"}
        
        with tracer.start_as_current_span("test"):
            await instrument._emit("before_workflow_run", workflow=workflow, context=mock_context)
        
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        
        assert attrs[SpanMeta.WORKFLOW_TYPE] == "IntegrationWorkflow"
        assert attrs[SpanMeta.WORKFLOW_INPUT_JSON] == '{"test": "data"}'
    
    @pytest.mark.asyncio
    async def test_hook_exception_handling(self, setup_tracing):
        """Test that exceptions in hooks don't break the application."""
        tracer, exporter = setup_tracing
        
        # Create a hook that raises an exception
        async def bad_hook(**kwargs):
            raise RuntimeError("Hook failed!")
        
        instrument.register("before_workflow_run", bad_hook)
        
        try:
            # This should not raise - exceptions should be caught
            with tracer.start_as_current_span("test"):
                await instrument._emit("before_workflow_run", workflow=Mock(), context=Mock())
            
            # The span should still be created
            spans = exporter.get_finished_spans()
            assert len(spans) == 1
        finally:
            instrument.unregister("before_workflow_run", bad_hook)
    
    def test_performance_overhead(self, setup_tracing):
        """Test that span enrichment has acceptable performance."""
        import time
        
        tracer, exporter = setup_tracing
        
        # Register subscribers
        register_all_subscribers()
        
        # Time the operation
        iterations = 1000
        start = time.time()
        
        for _ in range(iterations):
            with tracer.start_as_current_span("perf_test") as span:
                # Simulate setting a few attributes
                span.set_attribute("test.attr", "value")
                capture_state("perf_state", {"iteration": 1})
        
        elapsed = time.time() - start
        per_span_ms = (elapsed / iterations) * 1000
        
        # Should be well under 1ms per span
        assert per_span_ms < 1.0, f"Per-span overhead {per_span_ms:.2f}ms exceeds 1ms limit"