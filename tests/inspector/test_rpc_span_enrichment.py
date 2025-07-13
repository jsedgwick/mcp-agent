"""Tests for RPC span enrichment via Inspector subscribers."""

import json
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import timedelta

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from mcp_agent.config import MCPServerSettings
from mcp_agent.core import instrument
from mcp_agent.core.context import Context
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp_agent.inspector import register_all_subscribers, unregister_all_subscribers
from mcp_agent.inspector.span_meta import SpanMeta


@pytest.fixture
def setup_tracing():
    """Set up OpenTelemetry tracing with in-memory exporter."""
    # Create an in-memory span exporter
    exporter = InMemorySpanExporter()
    
    # Check if a tracer provider is already set
    current_provider = trace.get_tracer_provider()
    if isinstance(current_provider, TracerProvider):
        # Use existing provider, just add our exporter
        provider = current_provider
        processor = SimpleSpanProcessor(exporter)
        provider.add_span_processor(processor)
    else:
        # Set up the tracer provider with the exporter
        provider = TracerProvider()
        processor = SimpleSpanProcessor(exporter)
        provider.add_span_processor(processor)
        
        # Set as global tracer provider
        trace.set_tracer_provider(provider)
    
    # Get tracer
    tracer = trace.get_tracer(__name__)
    
    # Clear any existing spans in the exporter
    exporter.clear()
    
    yield tracer, exporter
    
    # Clean up
    processor.shutdown()


@pytest.fixture
def mock_streams():
    """Create mock read/write streams."""
    read_stream = Mock()
    write_stream = Mock()
    return read_stream, write_stream


@pytest.fixture
def mock_context(setup_tracing):
    """Create a mock context with proper tracer."""
    tracer, exporter = setup_tracing
    context = Mock(spec=Context)
    context.tracing_enabled = True
    # Mock the get_tracer function to return our test tracer
    with patch('mcp_agent.mcp.mcp_agent_client_session.get_tracer', return_value=tracer):
        yield context


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


@pytest.fixture(autouse=True)
def register_subscribers():
    """Register all Inspector subscribers for the test."""
    register_all_subscribers()
    yield
    unregister_all_subscribers()


@pytest.mark.asyncio
async def test_rpc_span_enrichment_request(client_session, setup_tracing):
    """Test that RPC request spans are properly enriched by Inspector subscribers."""
    tracer, exporter = setup_tracing
    
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
    mock_result.model_dump.return_value = {"result": "test_response"}
    
    # Import ClientSession here to avoid import errors
    from mcp import ClientSession
    
    with tracer.start_as_current_span("test_rpc_request") as span:
        with patch.object(ClientSession, 'send_request', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_result
            
            # Call send_request
            await client_session.send_request(request, Mock)
    
    # Get the spans
    spans = exporter.get_finished_spans()
    assert len(spans) > 0
    
    # Find the send_request span created by MCPAgentClientSession
    # It should contain the RPC attributes
    send_request_span = next((s for s in spans if "send_request" in s.name), None)
    assert send_request_span is not None, f"No send_request span found. Available spans: {[s.name for s in spans]}"
    
    attrs = send_request_span.attributes
    
    # Verify RPC attributes were added by subscribers
    assert attrs.get(SpanMeta.JSONRPC_VERSION) == "2.0"
    assert attrs.get(SpanMeta.RPC_METHOD) == "tools/call"
    assert attrs.get(SpanMeta.RPC_ID) == "123"
    assert attrs.get(SpanMeta.RPC_TRANSPORT) == "stdio"
    assert attrs.get(SpanMeta.RPC_DIRECTION) == "outbound"
    assert attrs.get(SpanMeta.TRANSPORT_STATUS) == "connected"
    assert SpanMeta.RPC_DURATION_MS in attrs
    
    # Verify request/response envelopes
    request_json = attrs.get(SpanMeta.RPC_REQUEST_JSON)
    assert request_json is not None
    request_data = json.loads(request_json)
    assert request_data["method"] == "tools/call"
    assert request_data["id"] == 123
    
    response_json = attrs.get(SpanMeta.RPC_RESPONSE_JSON)
    assert response_json is not None
    response_data = json.loads(response_json)
    assert response_data["result"] == {"result": "test_response"}


@pytest.mark.asyncio
async def test_rpc_span_enrichment_error(client_session, setup_tracing):
    """Test that RPC error spans are properly enriched."""
    tracer, exporter = setup_tracing
    
    # Create a mock request
    request = Mock()
    request.root = Mock()
    request.root.jsonrpc = "2.0"
    request.root.method = "tools/call"
    request.root.id = 456
    request.root.params = Mock()
    request.root.params.model_dump.return_value = {"name": "failing_tool"}
    
    # Import ClientSession here to avoid import errors
    from mcp import ClientSession
    
    with tracer.start_as_current_span("test_rpc_error") as span:
        with patch.object(ClientSession, 'send_request', new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = TimeoutError("Request timed out")
            
            # Call send_request and expect exception
            with pytest.raises(TimeoutError):
                await client_session.send_request(request, Mock)
    
    # Get the spans
    spans = exporter.get_finished_spans()
    print(f"Number of spans in error test: {len(spans)}")
    for s in spans:
        print(f"  Span: {s.name}, Status: {s.status}")
    assert len(spans) > 0
    
    # Find the send_request span
    send_request_span = next((s for s in spans if "send_request" in s.name), None)
    assert send_request_span is not None, f"No send_request span found. Available spans: {[s.name for s in spans]}"
    
    attrs = send_request_span.attributes
    
    # Debug print the attributes
    print(f"Attributes: {dict(attrs)}")
    
    # Verify error attributes
    assert attrs.get(SpanMeta.STATUS_CODE) == "error"
    # The error_rpc_request hook sets ERROR_CODE to the exception class name,
    # but also sets it to "TIMEOUT" if "timeout" is in the error message
    assert attrs.get(SpanMeta.ERROR_CODE) == "TIMEOUT"  # Should be TIMEOUT because "timed out" is in message
    assert attrs.get(SpanMeta.ERROR_MESSAGE) == "Request timed out"
    assert attrs.get(SpanMeta.TRANSPORT_STATUS) == "disconnected"


@pytest.mark.asyncio
async def test_rpc_span_enrichment_notification(client_session, setup_tracing):
    """Test that RPC notification spans are properly enriched."""
    tracer, exporter = setup_tracing
    
    # Create a mock notification
    notification = Mock()
    notification.root = Mock()
    notification.root.jsonrpc = "2.0"
    notification.root.method = "notifications/progress"
    notification.root.params = Mock()
    notification.root.params.model_dump.return_value = {
        "progress": 50,
        "message": "Processing..."
    }
    
    # Import ClientSession here to avoid import errors
    from mcp import ClientSession
    
    with tracer.start_as_current_span("test_rpc_notification") as span:
        with patch.object(ClientSession, 'send_notification', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            
            # Call send_notification
            await client_session.send_notification(notification)
    
    # Get the spans
    spans = exporter.get_finished_spans()
    assert len(spans) > 0
    
    # Find the send_notification span
    send_notification_span = next((s for s in spans if "send_notification" in s.name), None)
    assert send_notification_span is not None, f"No send_notification span found. Available spans: {[s.name for s in spans]}"
    
    attrs = send_notification_span.attributes
    
    # Verify RPC attributes (notifications don't have ID)
    assert attrs.get(SpanMeta.JSONRPC_VERSION) == "2.0"
    assert attrs.get(SpanMeta.RPC_METHOD) == "notifications/progress"
    assert SpanMeta.RPC_ID not in attrs  # Notifications don't have ID
    assert attrs.get(SpanMeta.RPC_TRANSPORT) == "stdio"
    assert attrs.get(SpanMeta.RPC_DIRECTION) == "outbound"


@pytest.mark.asyncio
async def test_rpc_span_different_transports(mock_streams, mock_context, setup_tracing):
    """Test that different transport types are correctly captured in spans."""
    tracer, exporter = setup_tracing
    
    from mcp import ClientSession
    
    # Test different transport types
    transports = ["stdio", "sse", "websocket", "streamable_http"]
    
    for transport in transports:
        # Clear previous spans
        exporter.clear()
        
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
        request.root.id = 789
        request.root.params = None
        
        # Mock the response
        mock_result = Mock()
        mock_result.model_dump.return_value = {"resources": []}
        
        with tracer.start_as_current_span(f"test_transport_{transport}") as span:
            with patch.object(ClientSession, 'send_request', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = mock_result
                
                await session.send_request(request, Mock)
        
        # Get the spans
        spans = exporter.get_finished_spans()
        print(f"Number of spans: {len(spans)}")
        for s in spans:
            print(f"  Span: {s.name}, Status: {s.status}")
        assert len(spans) > 0
        
        # Find the send_request span
        send_request_span = next((s for s in spans if "send_request" in s.name), None)
        assert send_request_span is not None, f"No send_request span found for transport {transport}"
        
        attrs = send_request_span.attributes
        
        # Verify transport was captured correctly
        assert attrs.get(SpanMeta.RPC_TRANSPORT) == transport