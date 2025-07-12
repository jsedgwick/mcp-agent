"""Tests for session listing and event streaming endpoints."""

import asyncio
import gzip
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_agent.inspector import mount
from mcp_agent.inspector.sessions import SessionMeta, list_sessions
from mcp_agent.inspector.events import (
    get_event_stream,
    SessionStarted,
    SessionFinished,
    WaitingOnSignal,
    Heartbeat
)


@pytest.fixture
def app():
    """Create a test FastAPI app with inspector mounted."""
    app = FastAPI()
    mount(app)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def temp_trace_dir(tmp_path):
    """Create a temporary trace directory."""
    # Override the trace directory for testing
    original = os.environ.get("MCP_TRACES_DIR")
    os.environ["MCP_TRACES_DIR"] = str(tmp_path)
    yield tmp_path
    # Restore original
    if original:
        os.environ["MCP_TRACES_DIR"] = original
    else:
        os.environ.pop("MCP_TRACES_DIR", None)


def create_test_trace(trace_dir: Path, session_id: str, spans: list[Dict[str, Any]]) -> Path:
    """Create a test trace file."""
    trace_path = trace_dir / f"{session_id}.jsonl.gz"
    
    # Write spans as gzipped JSONL
    with gzip.open(trace_path, 'wt') as f:
        for span in spans:
            f.write(json.dumps(span) + '\n')
    
    return trace_path


class TestSessionsEndpoint:
    """Tests for the /sessions endpoint."""
    
    def test_sessions_empty(self, client, temp_trace_dir):
        """Test listing sessions when no traces exist."""
        response = client.get("/_inspector/sessions")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert data["sessions"] == []
    
    def test_sessions_single_trace(self, client, temp_trace_dir):
        """Test listing a single session."""
        # Create a test trace
        session_id = "test-session-123"
        spans = [
            {
                "span_id": "span1",
                "trace_id": "trace1",
                "start_time": "2025-01-01T12:00:00Z",
                "end_time": "2025-01-01T12:00:10Z",
                "name": "workflow.run",
                "attributes": {
                    "mcp.workflow.type": "orchestrator",
                    "mcp.session.title": "Test Orchestrator"
                },
                "status": {"status_code": "OK"}
            }
        ]
        create_test_trace(temp_trace_dir, session_id, spans)
        
        # Get sessions
        response = client.get("/_inspector/sessions")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["sessions"]) == 1
        session = data["sessions"][0]
        assert session["id"] == session_id
        assert session["status"] == "completed"
        assert session["started_at"] == "2025-01-01T12:00:00Z"
        assert session["ended_at"] == "2025-01-01T12:00:10Z"
        assert session["engine"] == "asyncio"
        assert session["title"] == "Test Orchestrator"
    
    def test_sessions_multiple_traces(self, client, temp_trace_dir):
        """Test listing multiple sessions sorted by start time."""
        # Create multiple test traces with proper status indicators
        # Session 1: Completed (has end time)
        create_test_trace(temp_trace_dir, "session1", [{
            "span_id": "span-1",
            "trace_id": "trace-1",
            "start_time": "2025-01-01T10:00:00Z",
            "end_time": "2025-01-01T10:10:00Z",
            "name": "workflow.run",
            "attributes": {},
            "status": {"status_code": "OK"}
        }])
        
        # Session 2: Failed (ERROR status)
        create_test_trace(temp_trace_dir, "session2", [{
            "span_id": "span-2",
            "trace_id": "trace-2",
            "start_time": "2025-01-01T11:00:00Z",
            "end_time": "2025-01-01T11:05:00Z",
            "name": "workflow.run",
            "attributes": {},
            "status": {"status_code": "ERROR"}
        }])
        
        # Session 3: Paused (has paused attribute, no end time on workflow)
        create_test_trace(temp_trace_dir, "session3", [{
            "span_id": "span-3",
            "trace_id": "trace-3",
            "start_time": "2025-01-01T12:00:00Z",
            # NO end_time - still running/paused
            "name": "workflow.run",
            "attributes": {"mcp.session.paused": True},
            "status": {"status_code": "OK"}
        }])
        
        # Get sessions
        response = client.get("/_inspector/sessions")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["sessions"]) == 3
        
        # Check sorting (newest first)
        assert data["sessions"][0]["id"] == "session3"
        assert data["sessions"][1]["id"] == "session2"
        assert data["sessions"][2]["id"] == "session1"
        
        # Check statuses
        assert data["sessions"][0]["status"] == "paused"
        assert data["sessions"][1]["status"] == "failed"
        assert data["sessions"][2]["status"] == "completed"
    
    def test_sessions_running_state(self, client, temp_trace_dir):
        """Test detection of running sessions (no end time, not paused)."""
        # Create a running session
        create_test_trace(temp_trace_dir, "running-session", [{
            "span_id": "span-1",
            "trace_id": "trace-1",
            "start_time": "2025-01-01T14:00:00Z",
            # NO end_time and NO paused attribute = running
            "name": "workflow.run",
            "attributes": {
                "mcp.workflow.type": "orchestrator",
                "mcp.session.title": "Active Processing"
            },
            "status": {"status_code": "OK"}
        }])
        
        response = client.get("/_inspector/sessions")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["sessions"]) == 1
        session = data["sessions"][0]
        assert session["id"] == "running-session"
        assert session["status"] == "running"
        assert session["title"] == "Active Processing"
        assert "ended_at" not in session  # No end time for running sessions
    
    def test_sessions_corrupt_trace(self, client, temp_trace_dir):
        """Test handling of corrupted trace files."""
        # Create a valid trace
        create_test_trace(temp_trace_dir, "valid-session", [{
            "span_id": "span1",
            "start_time": "2025-01-01T12:00:00Z",
            "name": "workflow.run"
        }])
        
        # Create a corrupted trace
        corrupt_path = temp_trace_dir / "corrupt-session.jsonl.gz"
        with gzip.open(corrupt_path, 'wt') as f:
            f.write("invalid json content\n")
        
        # Should still return the valid session
        response = client.get("/_inspector/sessions")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["id"] == "valid-session"


class TestEventsEndpoint:
    """Tests for the /events SSE endpoint."""
    
    def test_events_endpoint_exists(self, app):
        """Test that events endpoint is registered."""
        # Note: TestClient doesn't support SSE streaming properly
        # We just verify the route exists
        routes = [route.path for route in app.routes]
        assert "/_inspector/events" in routes
    
    @pytest.mark.asyncio
    async def test_event_publishing(self):
        """Test publishing events to the stream."""
        stream = await get_event_stream()
        
        # Add a test client
        queue = await stream.add_client()
        
        # Publish some events
        event1 = SessionStarted("test-session", "asyncio", "Test Session")
        await stream.publish_event(event1.to_dict())
        
        event2 = WaitingOnSignal("test-session", "human_input", "Enter your name")
        await stream.publish_event(event2.to_dict())
        
        # Retrieve events
        received = []
        while not queue.empty():
            received.append(await queue.get())
        
        assert len(received) == 2
        assert received[0]["type"] == "SessionStarted"
        assert received[0]["session_id"] == "test-session"
        assert received[1]["type"] == "WaitingOnSignal"
        assert received[1]["signal_name"] == "human_input"
        
        # Cleanup
        await stream.remove_client(queue)
    
    @pytest.mark.asyncio
    async def test_event_types(self):
        """Test all event types serialize correctly."""
        events = [
            SessionStarted("session1", "temporal", "Temporal Workflow"),
            SessionFinished("session1", "completed"),
            WaitingOnSignal("session2", "approval", "Approve deployment?", {"type": "boolean"}),
            Heartbeat("session3", llm_calls_delta=5, tokens_delta=1500)
        ]
        
        for event in events:
            data = event.to_dict()
            assert "type" in data
            assert data["type"] == event.__class__.__name__
            
            # Verify JSON serializable
            json_str = json.dumps(data)
            assert len(json_str) > 0


@pytest.mark.asyncio
async def test_list_sessions_function():
    """Test the list_sessions function directly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock trace directory
        original = os.environ.get("MCP_TRACES_DIR")
        os.environ["MCP_TRACES_DIR"] = tmpdir
        
        try:
            # No traces
            sessions = await list_sessions()
            assert sessions == []
            
            # Create a trace
            create_test_trace(Path(tmpdir), "test-123", [{
                "span_id": "s1",
                "start_time": "2025-01-01T10:00:00Z",
                "name": "agent.call"
            }])
            
            sessions = await list_sessions()
            assert len(sessions) == 1
            assert sessions[0].id == "test-123"
            
        finally:
            if original:
                os.environ["MCP_TRACES_DIR"] = original
            else:
                os.environ.pop("MCP_TRACES_DIR", None)


def test_session_meta():
    """Test SessionMeta class."""
    # Basic session
    session = SessionMeta(
        id="test-123",
        status="running",
        started_at="2025-01-01T12:00:00Z"
    )
    
    data = session.to_dict()
    assert data["id"] == "test-123"
    assert data["status"] == "running"
    assert data["started_at"] == "2025-01-01T12:00:00Z"
    assert data["engine"] == "asyncio"
    assert data["title"] == "Session test-123"
    assert "ended_at" not in data
    
    # Session with all fields
    session2 = SessionMeta(
        id="test-456",
        status="completed",
        started_at="2025-01-01T12:00:00Z",
        engine="temporal",
        title="Custom Title",
        ended_at="2025-01-01T12:10:00Z"
    )
    
    data2 = session2.to_dict()
    assert data2["engine"] == "temporal"
    assert data2["title"] == "Custom Title"
    assert data2["ended_at"] == "2025-01-01T12:10:00Z"