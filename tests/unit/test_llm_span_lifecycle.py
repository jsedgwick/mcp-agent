"""Unit tests for LLM span lifecycle management."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.core.context import Context
from mcp_agent.config import AnthropicSettings, OpenAISettings, Settings
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp.types import Tool


@pytest.fixture
def setup_tracing():
    """Set up in-memory tracing for tests."""
    # Create an in-memory span exporter
    exporter = InMemorySpanExporter()
    
    # Create a tracer provider with the exporter
    provider = TracerProvider()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    # Set as global tracer provider
    trace.set_tracer_provider(provider)
    
    yield exporter
    
    # Clean up
    exporter.clear()


@pytest.fixture
def mock_context(mock_executor):
    """Create a mock context for testing."""
    context = MagicMock()
    context.tracing_enabled = True
    context.config = Settings(
        anthropic=AnthropicSettings(api_key="test-key"),
        openai=OpenAISettings(api_key="test-key")
    )
    context.executor = mock_executor
    context.model_selector = MagicMock()
    context.model_selector.select_model = AsyncMock(return_value="claude-3-haiku-20240307")
    return context


@pytest.fixture
def mock_agent():
    """Create a mock agent."""
    agent = MagicMock()
    agent.name = "test-agent"
    agent.list_tools = AsyncMock(return_value=MagicMock(tools=[
        Tool(name="test-tool", description="Test tool", inputSchema={})
    ]))
    agent.call_tool = AsyncMock(return_value=MagicMock(
        content=[MagicMock(type="text", text="Tool result")]
    ))
    return agent


@pytest.fixture
def mock_executor():
    """Create a mock executor."""
    executor = MagicMock()
    executor.execution_engine = "asyncio"
    executor.execute = AsyncMock()
    executor.execute_many = AsyncMock()
    return executor


class TestAnthropicSpanLifecycle:
    """Test span lifecycle in Anthropic LLM implementation."""
    
    @pytest.mark.asyncio
    async def test_span_properly_closed_on_success(
        self, setup_tracing, mock_context, mock_agent, mock_executor
    ):
        """Test that span is properly closed after successful generation."""
        exporter = setup_tracing
        
        # Create LLM instance
        llm = AnthropicAugmentedLLM(
            context=mock_context,
            agent=mock_agent,
            executor=mock_executor,
            name="test-llm"
        )
        
        # Mock the executor to return a successful response
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_response.stop_reason = "end_turn"
        mock_response.content = []
        mock_executor.execute.return_value = mock_response
        
        # Call generate
        await llm.generate("Test message")
        
        # Check spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        span = spans[0]
        assert span.name == "AnthropicAugmentedLLM.test-llm.generate"
        assert span.status.status_code == StatusCode.UNSET  # Success
        
        # Verify attributes were set (these would fail if span was ended early)
        assert span.attributes.get("gen_ai.agent.name") == "test-agent"
        assert span.attributes.get("gen_ai.usage.input_tokens") == 10
        assert span.attributes.get("gen_ai.usage.output_tokens") == 20
        assert span.attributes.get("gen_ai.response.finish_reasons") == ["end_turn"]
    
    @pytest.mark.asyncio
    async def test_span_properly_closed_on_error(
        self, setup_tracing, mock_context, mock_agent, mock_executor
    ):
        """Test that span is properly closed after error."""
        exporter = setup_tracing
        
        # Create LLM instance
        llm = AnthropicAugmentedLLM(
            context=mock_context,
            agent=mock_agent,
            executor=mock_executor,
            name="test-llm"
        )
        
        # Mock the executor to return an error
        error = Exception("API Error")
        mock_executor.execute.return_value = error
        
        # Call generate
        await llm.generate("Test message")
        
        # Check spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        span = spans[0]
        assert span.name == "AnthropicAugmentedLLM.test-llm.generate"
        assert span.status.status_code == StatusCode.ERROR
        
        # Verify error was recorded
        events = span.events
        assert len(events) > 0
        assert any(event.name == "exception" for event in events)
    
    @pytest.mark.asyncio
    async def test_span_attributes_set_throughout_method(
        self, setup_tracing, mock_context, mock_agent, mock_executor
    ):
        """Test that span attributes can be set throughout the entire method."""
        exporter = setup_tracing
        
        # Create LLM instance
        llm = AnthropicAugmentedLLM(
            context=mock_context,
            agent=mock_agent,
            executor=mock_executor,
            name="test-llm"
        )
        
        # Mock multiple responses for tool use iteration
        mock_response1 = MagicMock()
        mock_response1.usage.input_tokens = 10
        mock_response1.usage.output_tokens = 20
        mock_response1.stop_reason = "tool_use"
        mock_response1.content = [
            MagicMock(
                type="tool_use",
                name="test-tool",
                input={},
                id="tool-1"
            )
        ]
        
        mock_response2 = MagicMock()
        mock_response2.usage.input_tokens = 5
        mock_response2.usage.output_tokens = 15
        mock_response2.stop_reason = "end_turn"
        mock_response2.content = []
        
        mock_executor.execute.side_effect = [mock_response1, mock_response2]
        
        # Call generate
        params = RequestParams(max_iterations=2)
        await llm.generate("Test message", params)
        
        # Check spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        span = spans[0]
        # Verify cumulative token counts
        assert span.attributes.get("gen_ai.usage.input_tokens") == 15  # 10 + 5
        assert span.attributes.get("gen_ai.usage.output_tokens") == 35  # 20 + 15
        
        # Verify multiple responses were recorded
        assert "response.0.id" in span.attributes
        assert "response.1.id" in span.attributes


class TestOpenAISpanLifecycle:
    """Test span lifecycle in OpenAI LLM implementation."""
    
    @pytest.mark.asyncio
    async def test_span_properly_closed_on_success(
        self, setup_tracing, mock_context, mock_agent, mock_executor
    ):
        """Test that span is properly closed after successful generation."""
        exporter = setup_tracing
        
        # Create LLM instance
        llm = OpenAIAugmentedLLM(
            context=mock_context,
            agent=mock_agent,
            executor=mock_executor,
            name="test-llm"
        )
        
        # Mock the executor to return a successful response
        mock_response = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.choices = [
            MagicMock(
                finish_reason="stop",
                message=MagicMock(tool_calls=None)
            )
        ]
        mock_executor.execute.return_value = mock_response
        
        # Call generate
        await llm.generate("Test message")
        
        # Check spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        span = spans[0]
        assert span.name == "OpenAIAugmentedLLM.test-llm.generate"
        assert span.status.status_code == StatusCode.UNSET  # Success
        
        # Verify attributes were set (these would fail if span was ended early)
        assert span.attributes.get("gen_ai.agent.name") == "test-agent"
        assert span.attributes.get("gen_ai.usage.input_tokens") == 10
        assert span.attributes.get("gen_ai.usage.output_tokens") == 20
        assert span.attributes.get("finish_reason") == "stop"
    
    @pytest.mark.asyncio
    async def test_span_properly_closed_on_error(
        self, setup_tracing, mock_context, mock_agent, mock_executor
    ):
        """Test that span is properly closed after error."""
        exporter = setup_tracing
        
        # Create LLM instance
        llm = OpenAIAugmentedLLM(
            context=mock_context,
            agent=mock_agent,
            executor=mock_executor,
            name="test-llm"
        )
        
        # Mock the executor to return an error
        error = Exception("API Error")
        mock_executor.execute.return_value = error
        
        # Call generate
        await llm.generate("Test message")
        
        # Check spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        span = spans[0]
        assert span.name == "OpenAIAugmentedLLM.test-llm.generate"
        assert span.status.status_code == StatusCode.ERROR
        
        # Verify error was recorded
        events = span.events
        assert len(events) > 0
        assert any(event.name == "exception" for event in events)
    
    @pytest.mark.asyncio
    async def test_span_attributes_set_at_end_of_method(
        self, setup_tracing, mock_context, mock_agent, mock_executor
    ):
        """Test that span attributes can be set at the end of the method."""
        exporter = setup_tracing
        
        # Create LLM instance
        llm = OpenAIAugmentedLLM(
            context=mock_context,
            agent=mock_agent,
            executor=mock_executor,
            name="test-llm"
        )
        
        # Mock response
        mock_response = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.choices = [
            MagicMock(
                finish_reason="stop",
                message=MagicMock(tool_calls=None)
            )
        ]
        mock_executor.execute.return_value = mock_response
        
        # Call generate
        await llm.generate("Test message")
        
        # Check spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        
        span = spans[0]
        
        # These attributes are set at the very end of the method
        # If the span was closed early, these would not be present
        assert span.attributes.get("gen_ai.response.finish_reasons") == ["stop"]
        assert "response.0.role" in span.attributes


@pytest.mark.asyncio
async def test_concurrent_span_management(
    setup_tracing, mock_context, mock_agent, mock_executor
):
    """Test that concurrent LLM calls don't interfere with each other's spans."""
    exporter = setup_tracing
    
    # Create two LLM instances
    llm1 = AnthropicAugmentedLLM(
        context=mock_context,
        agent=mock_agent,
        executor=mock_executor,
        name="llm1"
    )
    
    llm2 = AnthropicAugmentedLLM(
        context=mock_context,
        agent=mock_agent,
        executor=mock_executor,
        name="llm2"
    )
    
    # Mock responses
    mock_response = MagicMock()
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 20
    mock_response.stop_reason = "end_turn"
    mock_response.content = []
    
    # Add delay to simulate concurrent execution
    async def delayed_execute(*args, **kwargs):
        await asyncio.sleep(0.01)
        return mock_response
    
    mock_executor.execute = delayed_execute
    
    # Call both LLMs concurrently
    results = await asyncio.gather(
        llm1.generate("Test 1"),
        llm2.generate("Test 2")
    )
    
    # Check spans
    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    
    # Each span should have its own name
    span_names = {span.name for span in spans}
    assert "AnthropicAugmentedLLM.llm1.generate" in span_names
    assert "AnthropicAugmentedLLM.llm2.generate" in span_names
    
    # Both spans should be successful
    for span in spans:
        assert span.status.status_code == StatusCode.UNSET
        assert span.attributes.get("gen_ai.usage.input_tokens") == 10
        assert span.attributes.get("gen_ai.usage.output_tokens") == 20