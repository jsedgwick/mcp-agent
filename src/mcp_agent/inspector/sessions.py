"""Session management and listing functionality for Inspector."""

import asyncio
import gzip
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

import aiofiles


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
        # Remove .jsonl.gz extension
        session_id = trace_path.name.removesuffix('.jsonl.gz')
        
        # Read first and last spans to determine start/end times and status
        first_span = None
        last_span = None
        status = "completed"
        
        async with aiofiles.open(trace_path, 'rb') as f:
            # Read compressed content
            content = await f.read()
            
        # Decompress and parse line by line
        lines = gzip.decompress(content).decode('utf-8').strip().split('\n')
        
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


async def list_sessions() -> List[SessionMeta]:
    """List all sessions from trace files.
    
    Returns:
        List of SessionMeta objects sorted by start time (newest first)
    """
    # Get trace directory from environment or default
    trace_dir_str = os.environ.get("MCP_TRACES_DIR", "~/.mcp_traces")
    trace_dir = Path(os.path.expanduser(trace_dir_str))
    
    if not trace_dir.exists():
        return []
    
    # Find all trace files
    trace_files = list(trace_dir.glob("*.jsonl.gz"))
    
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