"""Server-Sent Events (SSE) streaming for Inspector."""

import asyncio
import json
from typing import AsyncIterator, Optional, Dict, Any
from datetime import datetime

from starlette.responses import StreamingResponse
from starlette.requests import Request


class EventStream:
    """Manages SSE event streaming to connected clients."""
    
    def __init__(self):
        self._clients: list[asyncio.Queue] = []
        self._event_counter = 0
        self._lock = asyncio.Lock()
    
    async def add_client(self) -> asyncio.Queue:
        """Add a new client to receive events.
        
        Returns:
            Queue for the client to receive events
        """
        queue = asyncio.Queue()
        async with self._lock:
            self._clients.append(queue)
        return queue
    
    async def remove_client(self, queue: asyncio.Queue):
        """Remove a client from the event stream."""
        async with self._lock:
            if queue in self._clients:
                self._clients.remove(queue)
    
    async def publish_event(self, event: Dict[str, Any]):
        """Publish an event to all connected clients.
        
        Args:
            event: Event data to publish
        """
        async with self._lock:
            self._event_counter += 1
            event_id = self._event_counter
            
            # Add event metadata
            event["timestamp"] = datetime.utcnow().isoformat()
            event["event_id"] = event_id
            
            # Send to all clients
            for queue in self._clients:
                try:
                    # Don't block if queue is full
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Client is slow, drop the event
                    pass
    
    def client_count(self) -> int:
        """Get the number of connected clients."""
        return len(self._clients)


# Global event stream instance
_event_stream = EventStream()


async def get_event_stream() -> EventStream:
    """Get the global event stream instance."""
    return _event_stream


async def event_generator(request: Request, queue: asyncio.Queue) -> AsyncIterator[str]:
    """Generate SSE events for a client.
    
    Args:
        request: Starlette request object
        queue: Client's event queue
        
    Yields:
        SSE formatted event strings
    """
    # Send initial connection event
    yield format_sse_event({
        "type": "Connected",
        "message": "Connected to Inspector event stream"
    })
    
    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            
            try:
                # Wait for events with timeout
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield format_sse_event(event)
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield format_sse_event({
                    "type": "Heartbeat",
                    "timestamp": datetime.utcnow().isoformat()
                })
    
    except asyncio.CancelledError:
        # Client disconnected
        pass


def format_sse_event(data: Dict[str, Any], event_type: Optional[str] = None) -> str:
    """Format data as SSE event.
    
    Args:
        data: Event data
        event_type: Optional event type
        
    Returns:
        SSE formatted string
    """
    lines = []
    
    # Add event ID if present
    if "event_id" in data:
        lines.append(f"id: {data['event_id']}")
    
    # Add event type
    if event_type:
        lines.append(f"event: {event_type}")
    
    # Add data
    lines.append(f"data: {json.dumps(data)}")
    
    # Add retry hint (2 seconds)
    lines.append("retry: 2000")
    
    # SSE requires double newline
    return "\n".join(lines) + "\n\n"


async def create_event_stream_response(request: Request) -> StreamingResponse:
    """Create an SSE streaming response.
    
    Args:
        request: Starlette request object
        
    Returns:
        StreamingResponse configured for SSE
    """
    stream = await get_event_stream()
    queue = await stream.add_client()
    
    async def cleanup():
        """Cleanup when client disconnects."""
        await stream.remove_client(queue)
    
    # Register cleanup
    request.scope["cleanup_handlers"] = getattr(request.scope, "cleanup_handlers", [])
    request.scope["cleanup_handlers"].append(cleanup)
    
    return StreamingResponse(
        event_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        }
    )


# Common event types
class InspectorEvent:
    """Base class for Inspector events."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        raise NotImplementedError


class SessionStarted(InspectorEvent):
    """Event emitted when a session starts."""
    
    def __init__(self, session_id: str, engine: str = "asyncio", title: Optional[str] = None):
        self.session_id = session_id
        self.engine = engine
        self.title = title or f"Session {session_id[:8]}"
        self.start_time = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "SessionStarted",
            "session_id": self.session_id,
            "engine": self.engine,
            "title": self.title,
            "start_time": self.start_time
        }


class SessionFinished(InspectorEvent):
    """Event emitted when a session completes."""
    
    def __init__(self, session_id: str, status: str = "completed", error: Optional[str] = None):
        self.session_id = session_id
        self.status = status
        self.error = error
        self.end_time = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": "SessionFinished",
            "session_id": self.session_id,
            "status": self.status,
            "end_time": self.end_time
        }
        if self.error:
            data["error"] = self.error
        return data


class WaitingOnSignal(InspectorEvent):
    """Event emitted when a workflow pauses waiting for input."""
    
    def __init__(self, session_id: str, signal_name: str, prompt: Optional[str] = None, schema: Optional[Dict] = None):
        self.session_id = session_id
        self.signal_name = signal_name
        self.prompt = prompt
        self.schema = schema
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": "WaitingOnSignal",
            "session_id": self.session_id,
            "signal_name": self.signal_name
        }
        if self.prompt:
            data["prompt"] = self.prompt
        if self.schema:
            data["schema"] = self.schema
        return data


class Heartbeat(InspectorEvent):
    """Periodic heartbeat with session metrics."""
    
    def __init__(self, session_id: str, llm_calls_delta: int = 0, tokens_delta: int = 0):
        self.session_id = session_id
        self.llm_calls_delta = llm_calls_delta
        self.tokens_delta = tokens_delta
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Heartbeat",
            "session_id": self.session_id,
            "llm_calls_delta": self.llm_calls_delta,
            "tokens_delta": self.tokens_delta
        }