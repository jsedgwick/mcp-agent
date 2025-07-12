"""Unit tests for LLM generate hooks in all providers.

Tests verify:
- before_llm_generate hook is called before generation
- after_llm_generate hook is called after successful generation
- error_llm_generate hook is called on exceptions
- Hooks work for all LLM providers
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from mcp_agent.core import instrument
from mcp_agent.config import AnthropicSettings, OpenAISettings, AzureSettings, Settings
from mcp_agent.core.context import Context


class TestLLMGenerateHooks:
    """Test LLM generate hooks across all providers."""

    def setup_method(self) -> None:
        """Clear all hooks before each test."""
        instrument._hooks.clear()

    @pytest.fixture
    def captured_hooks(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fixture to capture hook calls."""
        captured = {
            "before_llm_generate": [],
            "after_llm_generate": [],
            "error_llm_generate": []
        }

        async def capture_before(llm: Any, prompt: Any, **kwargs: Any) -> None:
            captured["before_llm_generate"].append({
                "llm": llm,
                "prompt": prompt,
                **kwargs
            })

        async def capture_after(llm: Any, prompt: Any, response: Any, **kwargs: Any) -> None:
            captured["after_llm_generate"].append({
                "llm": llm,
                "prompt": prompt,
                "response": response,
                **kwargs
            })

        async def capture_error(llm: Any, prompt: Any, exc: Any, **kwargs: Any) -> None:
            captured["error_llm_generate"].append({
                "llm": llm,
                "prompt": prompt,
                "exc": exc,
                **kwargs
            })

        instrument.register("before_llm_generate", capture_before)
        instrument.register("after_llm_generate", capture_after)
        instrument.register("error_llm_generate", capture_error)

        return captured

    @pytest.mark.asyncio
    async def test_anthropic_hooks(self, captured_hooks: Dict[str, List[Dict[str, Any]]]) -> None:
        """Test hooks fire correctly for Anthropic provider."""
        from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
        from anthropic.types import Message, TextBlock, Usage
        
        # Setup mock context and LLM
        anthropic_config = AnthropicSettings(
            api_key="test_key",
            default_model="claude-3-7-sonnet-latest"
        )
        config = Settings(anthropic=anthropic_config)
        context = Context(config=config, tracing_enabled=False)
        
        # Mock the tracer
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
        
        with patch('mcp_agent.workflows.llm.augmented_llm_anthropic.get_tracer', return_value=mock_tracer):
            llm = AnthropicAugmentedLLM(name="test", context=context)
        
        # Mock dependencies
        llm.agent = MagicMock()
        llm.agent.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(return_value="claude-3-7-sonnet-latest")
        
        # Mock successful response
        mock_response = Message(
            id="msg_test",
            type="message",
            role="assistant",
            content=[TextBlock(type="text", text="Test response")],
            model="claude-3-7-sonnet-latest",
            stop_reason="end_turn",
            stop_sequence=None,
            usage=Usage(input_tokens=10, output_tokens=20, cache_creation_input_tokens=None, cache_read_input_tokens=None)
        )
        
        # Mock executor
        llm.executor = MagicMock()
        llm.executor.execute = AsyncMock(return_value=mock_response)
        
        # Test successful generation
        prompt = "Test prompt"
        with patch('mcp_agent.workflows.llm.augmented_llm_anthropic.get_tracer', return_value=mock_tracer):
            result = await llm.generate(prompt)
        
        # Verify hooks were called
        assert len(captured_hooks["before_llm_generate"]) == 1
        assert captured_hooks["before_llm_generate"][0]["prompt"] == prompt
        assert captured_hooks["before_llm_generate"][0]["llm"] == llm
        
        assert len(captured_hooks["after_llm_generate"]) == 1
        assert captured_hooks["after_llm_generate"][0]["prompt"] == prompt
        assert captured_hooks["after_llm_generate"][0]["response"] == [mock_response]
        
        assert len(captured_hooks["error_llm_generate"]) == 0

    @pytest.mark.asyncio
    async def test_anthropic_error_hook(self, captured_hooks: Dict[str, List[Dict[str, Any]]]) -> None:
        """Test error hook fires on exception for Anthropic provider."""
        from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
        
        # Setup mock context and LLM
        anthropic_config = AnthropicSettings(
            api_key="test_key",
            default_model="claude-3-7-sonnet-latest"
        )
        config = Settings(anthropic=anthropic_config)
        context = Context(config=config, tracing_enabled=False)
        
        # Mock the tracer
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
        
        with patch('mcp_agent.workflows.llm.augmented_llm_anthropic.get_tracer', return_value=mock_tracer):
            llm = AnthropicAugmentedLLM(name="test", context=context)
        
        # Mock dependencies
        llm.agent = MagicMock()
        llm.agent.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.select_model = AsyncMock(return_value="claude-3-7-sonnet-latest")
        
        # Mock executor to raise exception
        test_error = ValueError("Test error")
        llm.executor = MagicMock()
        llm.executor.execute = AsyncMock(side_effect=test_error)
        
        # Test error generation
        prompt = "Test prompt"
        with patch('mcp_agent.workflows.llm.augmented_llm_anthropic.get_tracer', return_value=mock_tracer):
            with pytest.raises(ValueError, match="Test error"):
                await llm.generate(prompt)
        
        # Verify hooks were called
        assert len(captured_hooks["before_llm_generate"]) == 1
        assert captured_hooks["before_llm_generate"][0]["prompt"] == prompt
        
        assert len(captured_hooks["after_llm_generate"]) == 0
        
        assert len(captured_hooks["error_llm_generate"]) == 1
        assert captured_hooks["error_llm_generate"][0]["prompt"] == prompt
        assert captured_hooks["error_llm_generate"][0]["exc"] == test_error

    @pytest.mark.asyncio
    async def test_openai_hooks(self, captured_hooks: Dict[str, List[Dict[str, Any]]]) -> None:
        """Test hooks fire correctly for OpenAI provider."""
        from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
        from openai.types.chat import ChatCompletionMessage, ChatCompletion
        from openai.types.chat.chat_completion import Choice
        from openai.types.completion_usage import CompletionUsage
        
        # Setup mock context and LLM
        openai_config = OpenAISettings(
            api_key="test_key",
            default_model="gpt-4"
        )
        config = Settings(openai=openai_config)
        context = Context(config=config, tracing_enabled=False)
        
        # Mock the tracer
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
        
        with patch('mcp_agent.workflows.llm.augmented_llm_openai.get_tracer', return_value=mock_tracer):
            llm = OpenAIAugmentedLLM(name="test", context=context)
        
        # Mock dependencies
        llm.agent = MagicMock()
        llm.agent.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(return_value="gpt-4")
        
        # Mock successful response
        mock_message = ChatCompletionMessage(
            role="assistant",
            content="Test response"
        )
        mock_response = ChatCompletion(
            id="chatcmpl-test",
            object="chat.completion",
            created=1234567890,
            model="gpt-4",
            choices=[Choice(
                index=0,
                message=mock_message,
                finish_reason="stop"
            )],
            usage=CompletionUsage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30
            )
        )
        
        # Mock executor
        llm.executor = MagicMock()
        llm.executor.execute = AsyncMock(return_value=mock_response)
        
        # Test successful generation
        prompt = "Test prompt"
        with patch('mcp_agent.workflows.llm.augmented_llm_openai.get_tracer', return_value=mock_tracer):
            result = await llm.generate(prompt)
        
        # Verify hooks were called
        assert len(captured_hooks["before_llm_generate"]) == 1
        assert captured_hooks["before_llm_generate"][0]["prompt"] == prompt
        assert captured_hooks["before_llm_generate"][0]["llm"] == llm
        
        assert len(captured_hooks["after_llm_generate"]) == 1
        # Debug: print what we actually got
        after_hook = captured_hooks["after_llm_generate"][0]
        print(f"DEBUG: after_llm_generate hook data: {after_hook}")
        print(f"DEBUG: Keys in hook: {list(after_hook.keys())}")
        assert after_hook["prompt"] == prompt
        assert after_hook["response"] == [mock_message]
        
        assert len(captured_hooks["error_llm_generate"]) == 0

    @pytest.mark.asyncio
    async def test_openai_error_hook(self, captured_hooks: Dict[str, List[Dict[str, Any]]]) -> None:
        """Test error hook fires on exception for OpenAI provider."""
        from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
        
        # Setup mock context and LLM
        openai_config = OpenAISettings(
            api_key="test_key",
            default_model="gpt-4"
        )
        config = Settings(openai=openai_config)
        context = Context(config=config, tracing_enabled=False)
        
        # Mock the tracer
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
        
        with patch('mcp_agent.workflows.llm.augmented_llm_openai.get_tracer', return_value=mock_tracer):
            llm = OpenAIAugmentedLLM(name="test", context=context)
        
        # Mock dependencies
        llm.agent = MagicMock()
        llm.agent.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.select_model = AsyncMock(return_value="gpt-4")
        
        # Mock executor to raise exception
        test_error = ValueError("Test error")
        llm.executor = MagicMock()
        llm.executor.execute = AsyncMock(side_effect=test_error)
        
        # Test error generation
        prompt = "Test prompt"
        with patch('mcp_agent.workflows.llm.augmented_llm_openai.get_tracer', return_value=mock_tracer):
            with pytest.raises(ValueError, match="Test error"):
                await llm.generate(prompt)
        
        # Verify hooks were called
        assert len(captured_hooks["before_llm_generate"]) == 1
        assert captured_hooks["before_llm_generate"][0]["prompt"] == prompt
        
        assert len(captured_hooks["after_llm_generate"]) == 0
        
        assert len(captured_hooks["error_llm_generate"]) == 1
        assert captured_hooks["error_llm_generate"][0]["prompt"] == prompt
        assert captured_hooks["error_llm_generate"][0]["exc"] == test_error

    @pytest.mark.asyncio
    async def test_azure_hooks(self, captured_hooks: Dict[str, List[Dict[str, Any]]]) -> None:
        """Test hooks fire correctly for Azure provider."""
        from mcp_agent.workflows.llm.augmented_llm_azure import AzureAugmentedLLM
        from azure.ai.inference.models import (
            CompletionsFinishReason
        )
        
        # Setup mock context and LLM
        azure_config = AzureSettings(
            endpoint="https://test.openai.azure.com",
            api_key="test_key",
            default_model="gpt-4"
        )
        config = Settings(azure=azure_config)
        context = Context(config=config, tracing_enabled=False)
        
        # Mock the tracer
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
        
        with patch('mcp_agent.workflows.llm.augmented_llm_azure.get_tracer', return_value=mock_tracer):
            llm = AzureAugmentedLLM(name="test", context=context)
        
        # Mock dependencies
        llm.agent = MagicMock()
        llm.agent.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()
        llm.select_model = AsyncMock(return_value="gpt-4")
        
        # Mock successful response
        mock_message = MagicMock()
        mock_message.content = "Test response"
        mock_message.role = "assistant"
        mock_message.tool_calls = None
        
        mock_response = MagicMock()
        mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
        mock_response.choices = [MagicMock(
            message=mock_message,
            finish_reason=CompletionsFinishReason.STOPPED
        )]
        
        # Mock executor
        llm.executor = MagicMock()
        llm.executor.execute = AsyncMock(return_value=mock_response)
        
        # Test successful generation
        prompt = "Test prompt"
        with patch('mcp_agent.workflows.llm.augmented_llm_azure.get_tracer', return_value=mock_tracer):
            result = await llm.generate(prompt)
        
        # Verify hooks were called
        assert len(captured_hooks["before_llm_generate"]) == 1
        assert captured_hooks["before_llm_generate"][0]["prompt"] == prompt
        assert captured_hooks["before_llm_generate"][0]["llm"] == llm
        
        assert len(captured_hooks["after_llm_generate"]) == 1
        assert captured_hooks["after_llm_generate"][0]["prompt"] == prompt
        assert len(captured_hooks["after_llm_generate"][0]["response"]) > 0
        
        assert len(captured_hooks["error_llm_generate"]) == 0

    @pytest.mark.asyncio
    async def test_azure_error_hook(self, captured_hooks: Dict[str, List[Dict[str, Any]]]) -> None:
        """Test error hook fires on exception for Azure provider."""
        from mcp_agent.workflows.llm.augmented_llm_azure import AzureAugmentedLLM
        
        # Setup mock context and LLM
        azure_config = AzureSettings(
            endpoint="https://test.openai.azure.com",
            api_key="test_key",
            default_model="gpt-4"
        )
        config = Settings(azure=azure_config)
        context = Context(config=config, tracing_enabled=False)
        
        # Mock the tracer
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
        
        with patch('mcp_agent.workflows.llm.augmented_llm_azure.get_tracer', return_value=mock_tracer):
            llm = AzureAugmentedLLM(name="test", context=context)
        
        # Mock dependencies
        llm.agent = MagicMock()
        llm.agent.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.select_model = AsyncMock(return_value="gpt-4")
        
        # Mock executor to raise exception
        test_error = ValueError("Test error")
        llm.executor = MagicMock()
        llm.executor.execute = AsyncMock(side_effect=test_error)
        
        # Test error generation
        prompt = "Test prompt"
        with patch('mcp_agent.workflows.llm.augmented_llm_azure.get_tracer', return_value=mock_tracer):
            with pytest.raises(ValueError, match="Test error"):
                await llm.generate(prompt)
        
        # Verify hooks were called
        assert len(captured_hooks["before_llm_generate"]) == 1
        assert captured_hooks["before_llm_generate"][0]["prompt"] == prompt
        
        assert len(captured_hooks["after_llm_generate"]) == 0
        
        assert len(captured_hooks["error_llm_generate"]) == 1
        assert captured_hooks["error_llm_generate"][0]["prompt"] == prompt
        assert captured_hooks["error_llm_generate"][0]["exc"] == test_error