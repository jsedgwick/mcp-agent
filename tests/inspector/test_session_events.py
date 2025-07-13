"""Tests for session event emission from workflow lifecycle hooks."""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import Mock, patch, AsyncMock

from mcp_agent.core import instrument
from mcp_agent.inspector import subscribers
from mcp_agent.inspector.events import SessionStarted, SessionFinished, Heartbeat
from mcp_agent.inspector.sessions import SessionMeta, session_registry


class MockContext:
    """Mock context object for testing."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.executor = Mock(execution_engine="asyncio")


class MockWorkflow:
    """Mock workflow object for testing."""
    def __init__(self, title: str = "TestWorkflow"):
        self.title = title
        self.__class__.__name__ = title


@pytest_asyncio.fixture(autouse=True)
async def cleanup_registry():
    """Clean up session registry after each test."""
    yield
    # Clear registry data
    session_registry._data.clear()
    session_registry._heartbeat_tasks.clear()
    session_registry._metrics.clear()


@pytest.fixture
def captured_events():
    """Capture events published to the event stream."""
    events = []
    
    async def mock_publish_event(event_dict):
        events.append(event_dict)
    
    with patch('mcp_agent.inspector.events.get_event_stream') as mock_get_stream:
        mock_stream = AsyncMock()
        mock_stream.publish_event = mock_publish_event
        mock_get_stream.return_value = mock_stream
        yield events


@pytest.mark.asyncio
async def test_session_started_event_emission(captured_events):
    """Test that SessionStarted event is emitted when workflow begins."""
    # Register subscribers
    subscribers.register_all_subscribers()
    
    try:
        # Create mock workflow and context
        workflow = MockWorkflow("TestOrchestrator")
        context = MockContext("test-session-123")
        
        # Emit before_workflow_run hook
        await instrument._emit("before_workflow_run", workflow=workflow, context=context)
        
        # Allow async tasks to complete
        await asyncio.sleep(0.1)
        
        # Verify SessionStarted event was published
        assert len(captured_events) == 1
        event = captured_events[0]
        assert event["type"] == "SessionStarted"
        assert event["session_id"] == "test-session-123"
        assert event["engine"] == "asyncio"
        assert event["title"] == "TestOrchestrator"
        
        # Verify session was added to registry
        meta = session_registry.get("test-session-123")
        assert meta is not None
        assert meta.status == "running"
        assert meta.engine == "asyncio"
        assert meta.title == "TestOrchestrator"
        
    finally:
        subscribers.unregister_all_subscribers()


@pytest.mark.asyncio
async def test_session_finished_event_emission(captured_events):
    """Test that SessionFinished event is emitted when workflow completes."""
    # Register subscribers
    subscribers.register_all_subscribers()
    
    try:
        # Create mock workflow and context
        workflow = MockWorkflow("TestRouter")
        context = MockContext("test-session-456")
        
        # Start session first
        await instrument._emit("before_workflow_run", workflow=workflow, context=context)
        await asyncio.sleep(0.1)
        
        # Clear captured events
        captured_events.clear()
        
        # Emit after_workflow_run hook
        result = {"decision": "route_a", "score": 0.95}
        await instrument._emit("after_workflow_run", workflow=workflow, context=context, result=result)
        
        # Allow async tasks to complete
        await asyncio.sleep(0.1)
        
        # Verify SessionFinished event was published
        assert len(captured_events) == 1
        event = captured_events[0]
        assert event["type"] == "SessionFinished"
        assert event["session_id"] == "test-session-456"
        assert event["status"] == "completed"
        assert "error" not in event
        
        # Verify session was marked as completed in registry
        meta = session_registry.get("test-session-456")
        assert meta is not None
        assert meta.status == "completed"
        assert meta.ended_at is not None
        
    finally:
        subscribers.unregister_all_subscribers()


@pytest.mark.asyncio
async def test_session_error_event_emission(captured_events):
    """Test that SessionFinished event is emitted with error when workflow fails."""
    # Register subscribers
    subscribers.register_all_subscribers()
    
    try:
        # Create mock workflow and context
        workflow = MockWorkflow("TestEvaluator")
        context = MockContext("test-session-789")
        
        # Start session first
        await instrument._emit("before_workflow_run", workflow=workflow, context=context)
        await asyncio.sleep(0.1)
        
        # Clear captured events
        captured_events.clear()
        
        # Emit error_workflow_run hook
        error = ValueError("Evaluation failed")
        await instrument._emit("error_workflow_run", workflow=workflow, context=context, exc=error)
        
        # Allow async tasks to complete
        await asyncio.sleep(0.1)
        
        # Verify SessionFinished event was published with error
        assert len(captured_events) == 1
        event = captured_events[0]
        assert event["type"] == "SessionFinished"
        assert event["session_id"] == "test-session-789"
        assert event["status"] == "failed"
        assert event["error"] == "Evaluation failed"
        
        # Verify session was marked as failed in registry
        meta = session_registry.get("test-session-789")
        assert meta is not None
        assert meta.status == "failed"
        assert meta.ended_at is not None
        
    finally:
        subscribers.unregister_all_subscribers()


@pytest.mark.asyncio
async def test_heartbeat_task_lifecycle():
    """Test that heartbeat task is started and cancelled properly."""
    # Register subscribers
    subscribers.register_all_subscribers()
    
    try:
        # Create mock workflow and context
        workflow = MockWorkflow("TestParallel")
        context = MockContext("test-session-hb")
        
        # Start session
        await instrument._emit("before_workflow_run", workflow=workflow, context=context)
        await asyncio.sleep(0.1)
        
        # Verify heartbeat task was created
        assert "test-session-hb" in session_registry._heartbeat_tasks
        task = session_registry._heartbeat_tasks["test-session-hb"]
        assert not task.done()
        
        # Finish session
        await instrument._emit("after_workflow_run", workflow=workflow, context=context, result={})
        await asyncio.sleep(0.1)
        
        # Verify heartbeat task was cancelled
        assert "test-session-hb" not in session_registry._heartbeat_tasks
        assert task.done()
        
    finally:
        subscribers.unregister_all_subscribers()


@pytest.mark.asyncio
async def test_context_without_session_id():
    """Test that events are not emitted when context lacks session_id."""
    # Register subscribers
    subscribers.register_all_subscribers()
    
    try:
        # Create mock workflow and context without session_id
        workflow = MockWorkflow("TestWorkflow")
        context = Mock(spec=[])  # No session_id attribute
        
        # Emit hooks - should not crash
        await instrument._emit("before_workflow_run", workflow=workflow, context=context)
        await instrument._emit("after_workflow_run", workflow=workflow, context=context, result={})
        await instrument._emit("error_workflow_run", workflow=workflow, context=context, exc=Exception())
        
        # Allow async tasks to complete
        await asyncio.sleep(0.1)
        
        # Verify no sessions were added to registry
        assert len(session_registry._data) == 0
        
    finally:
        subscribers.unregister_all_subscribers()


@pytest.mark.asyncio
async def test_multiple_concurrent_sessions(captured_events):
    """Test that multiple concurrent sessions are tracked correctly."""
    # Register subscribers
    subscribers.register_all_subscribers()
    
    try:
        # Start multiple sessions
        sessions = [
            ("session-1", "Workflow1"),
            ("session-2", "Workflow2"),
            ("session-3", "Workflow3")
        ]
        
        for session_id, title in sessions:
            workflow = MockWorkflow(title)
            context = MockContext(session_id)
            await instrument._emit("before_workflow_run", workflow=workflow, context=context)
        
        # Allow async tasks to complete
        await asyncio.sleep(0.1)
        
        # Verify all sessions are tracked
        assert len(session_registry._data) == 3
        assert session_registry.active_ids() == ["session-1", "session-2", "session-3"]
        
        # Finish one session
        workflow = MockWorkflow("Workflow2")
        context = MockContext("session-2")
        await instrument._emit("after_workflow_run", workflow=workflow, context=context, result={})
        await asyncio.sleep(0.1)
        
        # Verify only two sessions are active
        assert len(session_registry.active_ids()) == 2
        assert "session-2" not in session_registry.active_ids()
        
    finally:
        subscribers.unregister_all_subscribers()