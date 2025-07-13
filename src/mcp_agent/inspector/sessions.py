"""Session management and listing functionality for Inspector."""

import asyncio
import gzip
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

import aiofiles

from .settings import InspectorSettings


class SessionMeta:
    """Metadata for a session."""
    
    def __init__(
        self,
        id: str,
        status: str,
        started_at: str,
        engine: str = "asyncio",
        title: Optional[str] = None,
        ended_at: Optional[str] = None
    ):
        self.id = id
        self.status = status
        self.started_at = started_at
        self.engine = engine
        self.title = title or f"Session {id[:8]}"
        self.ended_at = ended_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            "id": self.id,
            "status": self.status,
            "started_at": self.started_at,
            "engine": self.engine,
            "title": self.title
        }
        if self.ended_at:
            data["ended_at"] = self.ended_at
        return data


async def _extract_session_metadata(trace_path: Path) -> Optional[SessionMeta]:
    """Extract session metadata from a trace file.
    
    Args:
        trace_path: Path to the trace file
        
    Returns:
        SessionMeta object or None if extraction fails
    """
    try:
        # Remove extensions to get session ID
        if trace_path.name.endswith('.jsonl.gz'):
            session_id = trace_path.name.removesuffix('.jsonl.gz')
        else:
            session_id = trace_path.name.removesuffix('.jsonl')
        
        # Read first and last spans to determine start/end times and status
        first_span = None
        last_span = None
        status = "completed"
        
        # Read file content
        if trace_path.suffix == '.gz':
            async with aiofiles.open(trace_path, 'rb') as f:
                content = await f.read()
            # Decompress and parse line by line
            lines = gzip.decompress(content).decode('utf-8').strip().split('\n')
        else:
            # Plain JSONL file
            async with aiofiles.open(trace_path, 'r') as f:
                content = await f.read()
            lines = content.strip().split('\n')
        
        if lines:
            # Get first span
            try:
                first_span = json.loads(lines[0])
            except json.JSONDecodeError:
                pass
            
            # Get last span
            try:
                last_span = json.loads(lines[-1])
            except json.JSONDecodeError:
                # If last line is corrupted, try previous lines
                for i in range(len(lines) - 2, -1, -1):
                    try:
                        last_span = json.loads(lines[i])
                        break
                    except json.JSONDecodeError:
                        continue
        
        if not first_span:
            return None
        
        # Extract metadata
        started_at = first_span.get("start_time", "")
        ended_at = last_span.get("end_time", "") if last_span else None
        
        # Determine status based on span attributes and timing
        # Priority order: paused > running > failed > completed
        
        # 1. Check for paused state (can be on any span)
        is_paused = False
        for line in lines:
            try:
                span = json.loads(line)
                if span.get("attributes", {}).get("mcp.session.paused", False):
                    is_paused = True
                    break
            except json.JSONDecodeError:
                continue
        
        if is_paused:
            status = "paused"
        # 2. Check if still running (no end time on root/workflow span)
        elif first_span.get("name") == "workflow.run" and not first_span.get("end_time"):
            status = "running"
        # 3. Check for errors
        elif last_span and last_span.get("status", {}).get("status_code") == "ERROR":
            status = "failed"
        # 4. Default to completed if has end time
        else:
            status = "completed"
        
        # Try to extract engine type
        engine = "asyncio"
        attributes = first_span.get("attributes", {})
        if attributes.get("mcp.engine.type"):
            engine = attributes["mcp.engine.type"]
        elif attributes.get("mcp.workflow.engine"):
            engine = attributes["mcp.workflow.engine"]
        
        # Extract title if available
        title = None
        if attributes.get("mcp.session.title"):
            title = attributes["mcp.session.title"]
        elif attributes.get("mcp.workflow.type"):
            title = f"{attributes['mcp.workflow.type']} - {session_id[:8]}"
        
        return SessionMeta(
            id=session_id,
            status=status,
            started_at=started_at,
            engine=engine,
            title=title,
            ended_at=ended_at
        )
        
    except Exception as e:
        # Log but don't fail on individual file errors
        print(f"Failed to extract metadata from {trace_path}: {e}")
        return None


async def list_sessions(settings: Optional[InspectorSettings] = None) -> List[SessionMeta]:
    """List all sessions from trace files.
    
    Args:
        settings: Optional InspectorSettings instance. If None, uses environment/defaults.
    
    Returns:
        List of SessionMeta objects sorted by start time (newest first)
    """
    # Get trace directory from settings or environment
    if settings:
        trace_dir_str = settings.storage.traces_dir
    else:
        # Fallback to environment variable for backward compatibility
        trace_dir_str = os.environ.get("MCP_TRACES_DIR", "~/.mcp_traces")
    
    # Always expand user home directory
    trace_dir = Path(trace_dir_str).expanduser()
    
    if not trace_dir.exists():
        return []
    
    # Find all trace files (both gzipped and uncompressed)
    trace_files = list(trace_dir.glob("*.jsonl.gz")) + list(trace_dir.glob("*.jsonl"))
    
    # Extract metadata from each file in parallel
    tasks = [_extract_session_metadata(path) for path in trace_files]
    results = await asyncio.gather(*tasks)
    
    # Filter out None results and sort by start time
    sessions = [s for s in results if s is not None]
    sessions.sort(key=lambda s: s.started_at, reverse=True)
    
    return sessions


async def get_active_sessions_from_registry(registry) -> List[SessionMeta]:
    """Get active sessions from the workflow registry.
    
    Args:
        registry: InMemoryWorkflowRegistry instance
        
    Returns:
        List of active SessionMeta objects
    """
    if not registry:
        return []
    
    active_sessions = []
    
    # Get active workflows from registry
    # This would require implementing a method on the registry
    # For now, return empty list
    # TODO: Implement when registry is available
    
    return active_sessions


class SessionRegistry:
    """In-memory registry of active sessions with metadata and heartbeat tracking."""
    
    def __init__(self):
        self._data: Dict[str, SessionMeta] = {}
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self._metrics: Dict[str, Dict[str, int]] = {}
        self._lock = asyncio.Lock()
    
    async def add(self, meta: SessionMeta) -> None:
        """Add a new session to the registry.
        
        Args:
            meta: SessionMeta object to track
        """
        async with self._lock:
            self._data[meta.id] = meta
            # Initialize metrics for heartbeat tracking
            self._metrics[meta.id] = {
                "llm_calls": 0,
                "tokens": 0,
                "span_count": 0,
                "llm_calls_last": 0,
                "tokens_last": 0,
                "span_count_last": 0
            }
    
    async def finish(self, session_id: str, status: str, error: Optional[str] = None) -> None:
        """Mark a session as finished.
        
        Args:
            session_id: Session ID to finish
            status: Final status ("completed" or "failed")
            error: Optional error message if failed
        """
        async with self._lock:
            if session_id in self._data:
                sess = self._data[session_id]
                sess.status = status
                sess.ended_at = datetime.utcnow().isoformat()
                # Add error attribute if provided
                if error:
                    setattr(sess, 'error', error)
                
                # Cancel heartbeat task if running
                if session_id in self._heartbeat_tasks:
                    task = self._heartbeat_tasks[session_id]
                    if not task.done():
                        task.cancel()
                    del self._heartbeat_tasks[session_id]
    
    def get(self, session_id: str) -> Optional[SessionMeta]:
        """Get session metadata by ID.
        
        Args:
            session_id: Session ID to look up
            
        Returns:
            SessionMeta object or None if not found
        """
        return self._data.get(session_id)
    
    def active_ids(self) -> List[str]:
        """Get list of active session IDs.
        
        Returns:
            List of session IDs that haven't ended
        """
        return [sid for sid, meta in self._data.items() if meta.ended_at is None]
    
    def set_heartbeat_task(self, session_id: str, task: asyncio.Task) -> None:
        """Store reference to heartbeat task for a session.
        
        Args:
            session_id: Session ID
            task: Asyncio task running the heartbeat loop
        """
        self._heartbeat_tasks[session_id] = task
    
    def update_metrics(self, session_id: str, llm_calls: int = 0, tokens: int = 0, spans: int = 0) -> Dict[str, int]:
        """Update metrics and return deltas for heartbeat.
        
        Args:
            session_id: Session ID to update
            llm_calls: Total LLM calls made
            tokens: Total tokens used
            spans: Total span count
            
        Returns:
            Dictionary with delta values
        """
        if session_id not in self._metrics:
            return {"llm_calls_delta": 0, "tokens_delta": 0, "span_count_delta": 0, "current_span_count": 0}
        
        metrics = self._metrics[session_id]
        
        # Calculate deltas
        deltas = {
            "llm_calls_delta": llm_calls - metrics["llm_calls_last"],
            "tokens_delta": tokens - metrics["tokens_last"],
            "span_count_delta": spans - metrics["span_count_last"],
            "current_span_count": spans
        }
        
        # Update last values
        metrics["llm_calls_last"] = llm_calls
        metrics["tokens_last"] = tokens
        metrics["span_count_last"] = spans
        
        # Update totals
        metrics["llm_calls"] = llm_calls
        metrics["tokens"] = tokens
        metrics["span_count"] = spans
        
        return deltas


# Create singleton registry instance
session_registry = SessionRegistry()