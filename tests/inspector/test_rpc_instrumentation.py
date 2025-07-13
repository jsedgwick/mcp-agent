"""Tests for RPC instrumentation hooks."""

import json
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import timedelta

from mcp_agent.config import MCPServerSettings
from mcp_agent.core import instrument
from mcp_agent.core.context import Context
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession


@pytest.fixture
def mock_streams():
    """Create mock read/write streams."""
    read_stream = Mock()
    write_stream = Mock()
    return read_stream, write_stream


@pytest.fixture
def mock_context():
    """Create a mock context."""
    context = Mock(spec=Context)
    context.tracing_enabled = True
    return context


@pytest.fixture
def client_session(mock_streams, mock_context):
    """Create a client session with mocked streams."""
    read_stream, write_stream = mock_streams
    session = MCPAgentClientSession(
        read_stream=read_stream,
        write_stream=write_stream,
        context=mock_context
    )
    # Set server config for transport type
    session.server_config = MCPServerSettings(
        name="test-server",
        transport="stdio"
    )
    return session


@pytest_asyncio.fixture
async def capture_rpc_hooks():
    """Fixture to capture RPC hook calls."""
    calls = {
        "before_rpc_request": [],
        "after_rpc_response": [],
        "error_rpc_request": []
    }
    
    async def capture_before(*args, **kwargs):
        calls["before_rpc_request"].append((args, kwargs))
    
    async def capture_after(*args, **kwargs):
        calls["after_rpc_response"].append((args, kwargs))
    
    async def capture_error(*args, **kwargs):
        calls["error_rpc_request"].append((args, kwargs))
    
    instrument.register("before_rpc_request", capture_before)
    instrument.register("after_rpc_response", capture_after)
    instrument.register("error_rpc_request", capture_error)
    
    yield calls
    
    instrument.unregister("before_rpc_request", capture_before)
    instrument.unregister("after_rpc_response", capture_after)
    instrument.unregister("error_rpc_request", capture_error)


@pytest.mark.asyncio
async def test_send_request_emits_hooks(client_session, capture_rpc_hooks):
    """Test that send_request emits before and after hooks."""
    # Create a mock request
    request = Mock()
    request.root = Mock()
    request.root.jsonrpc = "2.0"
    request.root.method = "tools/call"
    request.root.id = 123
    request.root.params = Mock()
    request.root.params.model_dump.return_value = {"name": "test_tool", "arguments": {"arg": "value"}}
    
    # Mock the parent class send_request
    mock_result = Mock()
    mock_result.model_dump.return_value = {"result": "test"}
    
    # Import ClientSession here to avoid import errors
    from mcp import ClientSession
    
    with patch.object(ClientSession, 'send_request', new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_result
        
        # Call send_request
        result = await client_session.send_request(request, Mock)
        
        # Verify hooks were called
        assert len(capture_rpc_hooks["before_rpc_request"]) == 1
        assert len(capture_rpc_hooks["after_rpc_response"]) == 1
        assert len(capture_rpc_hooks["error_rpc_request"]) == 0
        
        # Check before hook
        _, before_kwargs = capture_rpc_hooks["before_rpc_request"][0]
        assert before_kwargs["envelope"]["method"] == "tools/call"
        assert before_kwargs["envelope"]["jsonrpc"] == "2.0"
        assert before_kwargs["envelope"]["id"] == 123
        assert before_kwargs["transport"] == "stdio"
        
        # Check after hook
        _, after_kwargs = capture_rpc_hooks["after_rpc_response"][0]
        assert after_kwargs["envelope"]["result"] == {"result": "test"}
        assert after_kwargs["transport"] == "stdio"
        assert "duration_ms" in after_kwargs
        assert after_kwargs["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_send_request_error_emits_error_hook(client_session, capture_rpc_hooks):
    """Test that send_request emits error hook on exception."""
    # Create a mock request
    request = Mock()
    request.root = Mock()
    request.root.jsonrpc = "2.0"
    request.root.method = "tools/call"
    request.root.id = 123
    request.root.params = Mock()
    request.root.params.model_dump.return_value = {"name": "test_tool", "arguments": {"arg": "value"}}
    
    # Import ClientSession here to avoid import errors
    from mcp import ClientSession
    
    # Mock the parent class to raise an exception
    with patch.object(ClientSession, 'send_request', new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = RuntimeError("Connection failed")
        
        # Call send_request and expect exception
        with pytest.raises(RuntimeError):
            await client_session.send_request(request, Mock)
        
        # Verify hooks were called
        assert len(capture_rpc_hooks["before_rpc_request"]) == 1
        assert len(capture_rpc_hooks["after_rpc_response"]) == 0
        assert len(capture_rpc_hooks["error_rpc_request"]) == 1
        
        # Check error hook
        _, error_kwargs = capture_rpc_hooks["error_rpc_request"][0]
        assert error_kwargs["envelope"]["method"] == "tools/call"
        assert error_kwargs["transport"] == "stdio"
        assert isinstance(error_kwargs["exc"], RuntimeError)


@pytest.mark.asyncio
async def test_send_notification_emits_hooks(client_session, capture_rpc_hooks):
    """Test that send_notification emits hooks."""
    # Create a mock notification
    notification = Mock()
    notification.root = Mock()
    notification.root.jsonrpc = "2.0"
    notification.root.method = "notifications/message"
    notification.root.params = Mock()
    notification.root.params.model_dump.return_value = {
        "level": "info",
        "logger": "test",
        "data": "test message"
    }
    
    # Import ClientSession here to avoid import errors
    from mcp import ClientSession
    
    # Mock the parent class send_notification
    with patch.object(ClientSession, 'send_notification', new_callable=AsyncMock) as mock_send:
        mock_send.return_value = None
        
        # Call send_notification
        await client_session.send_notification(notification)
        
        # Verify hooks were called
        assert len(capture_rpc_hooks["before_rpc_request"]) == 1
        assert len(capture_rpc_hooks["after_rpc_response"]) == 1
        assert len(capture_rpc_hooks["error_rpc_request"]) == 0
        
        # Check before hook (notifications don't have id)
        _, before_kwargs = capture_rpc_hooks["before_rpc_request"][0]
        assert before_kwargs["envelope"]["method"] == "notifications/message"
        assert "id" not in before_kwargs["envelope"]
        
        # Check after hook
        _, after_kwargs = capture_rpc_hooks["after_rpc_response"][0]
        assert after_kwargs["envelope"] == {"jsonrpc": "2.0"}
        assert "duration_ms" in after_kwargs


@pytest.mark.asyncio
async def test_transport_types(mock_streams, mock_context, capture_rpc_hooks):
    """Test that different transport types are correctly captured."""
    # Import ClientSession here to avoid import errors
    from mcp import ClientSession
    
    # Test different transport types
    transports = ["stdio", "sse", "websocket", "streamable_http"]
    
    for transport in transports:
        read_stream, write_stream = mock_streams
        session = MCPAgentClientSession(
            read_stream=read_stream,
            write_stream=write_stream,
            context=mock_context
        )
        session.server_config = MCPServerSettings(
            name="test-server",
            transport=transport
        )
        
        # Create a mock request
        request = Mock()
        request.root = Mock()
        request.root.jsonrpc = "2.0"
        request.root.method = "resources/list"
        request.root.id = 456
        request.root.params = None
        
        # Mock the response
        mock_result = Mock()
        mock_result.model_dump.return_value = {"resources": []}
        
        with patch.object(ClientSession, 'send_request', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_result
            
            # Clear previous hooks
            capture_rpc_hooks["before_rpc_request"].clear()
            
            await session.send_request(request, Mock)
            
            # Check transport was captured correctly
            _, before_kwargs = capture_rpc_hooks["before_rpc_request"][0]
            assert before_kwargs["transport"] == transport