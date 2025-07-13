"""Trace streaming functionality for Inspector."""

import asyncio
import gzip
import os
import re
from pathlib import Path
from typing import AsyncIterator, Optional, Tuple

from fastapi import HTTPException, Request, Response
from starlette.responses import StreamingResponse, FileResponse

from .settings import InspectorSettings


def generate_etag(file_path: Path) -> str:
    """Generate a weak ETag based on file stats.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Weak ETag string
    """
    stat = os.stat(file_path)
    # W/ prefix indicates a weak ETag
    return f'W/"{stat.st_mtime_ns}-{stat.st_size}"'


def validate_session_id(session_id: str) -> str:
    """Validate and sanitize session ID to prevent path traversal.
    
    Args:
        session_id: User-provided session ID
        
    Returns:
        Sanitized session ID
        
    Raises:
        HTTPException: If session ID is invalid
    """
    # URL decode to catch encoded traversal attempts
    import urllib.parse
    decoded_id = urllib.parse.unquote(session_id)
    
    # Check for path traversal attempts in both raw and decoded forms
    for check_id in [session_id, decoded_id]:
        if ".." in check_id or "/" in check_id or "\\" in check_id:
            raise HTTPException(status_code=400, detail="Invalid session_id")
    
    # Validate format (alphanumeric, hyphens, underscores)
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    
    return session_id


def validate_trace_path(trace_path: Path, traces_dir: Path) -> Path:
    """Validate that the resolved trace path is within the allowed directory.
    
    Args:
        trace_path: Path to validate
        traces_dir: Allowed traces directory
        
    Returns:
        Resolved absolute path
        
    Raises:
        HTTPException: If path is outside allowed directory
    """
    # Resolve to absolute paths
    traces_dir_absolute = traces_dir.resolve()
    resolved_path = trace_path.resolve()
    
    # Check if the resolved path is within the traces directory
    try:
        resolved_path.relative_to(traces_dir_absolute)
    except ValueError:
        # Path is outside the allowed directory
        raise HTTPException(status_code=403, detail="Forbidden")
    
    return resolved_path


async def stream_gzipped_file_decompressed(
    file_path: Path, 
    start: int = 0, 
    end: Optional[int] = None
) -> AsyncIterator[bytes]:
    """Stream a gzipped file, decompressing on the fly for the given byte range.
    
    Args:
        file_path: Path to the gzipped file
        start: Start byte position in decompressed content
        end: End byte position in decompressed content (exclusive), None for EOF
        
    Yields:
        Chunks of decompressed data within the requested range
    """
    chunk_size = 1024 * 1024  # 1MB chunks
    bytes_read = 0
    
    def read_file():
        """Read and decompress file synchronously."""
        nonlocal bytes_read
        chunks = []
        
        try:
            with gzip.open(file_path, 'rb') as f:
                while True:
                    # Read a chunk
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    chunk_start = bytes_read
                    chunk_end = bytes_read + len(chunk)
                    
                    # Check if this chunk overlaps with our desired range
                    if end is not None and chunk_start >= end:
                        # We've passed the end of the range
                        break
                    
                    if chunk_end > start:
                        # This chunk contains some data we want
                        # Calculate the slice within this chunk
                        slice_start = max(0, start - chunk_start)
                        slice_end = min(len(chunk), (end - chunk_start) if end is not None else len(chunk))
                        
                        if slice_start < slice_end:
                            chunks.append(chunk[slice_start:slice_end])
                    
                    bytes_read = chunk_end
                    
        except (OSError, gzip.BadGzipFile):
            # Log error but don't raise - just end the stream
            # In production, this would be logged properly
            pass
        
        return chunks
    
    # Run the blocking I/O in a thread
    loop = asyncio.get_event_loop()
    chunks = await loop.run_in_executor(None, read_file)
    
    # Yield chunks one by one
    for chunk in chunks:
        yield chunk


async def get_trace_stream(
    session_id: str,
    request: Request,
    settings: Optional[InspectorSettings] = None
) -> Response:
    """Stream a trace file, handling Range requests and ETags.
    
    Args:
        session_id: Session ID to fetch
        request: FastAPI request object
        settings: Inspector settings
        
    Returns:
        Streaming response or 304 Not Modified
    """
    # Validate session ID
    safe_session_id = validate_session_id(session_id)
    
    # Get traces directory from settings
    if settings:
        traces_dir = Path(settings.storage.traces_dir).expanduser()
    else:
        traces_dir = Path("~/.mcp_traces").expanduser()
    
    # Construct file path - try both compressed and uncompressed
    gz_file_name = f"{safe_session_id}.jsonl.gz"
    gz_trace_path = traces_dir / gz_file_name
    
    plain_file_name = f"{safe_session_id}.jsonl"
    plain_trace_path = traces_dir / plain_file_name
    
    # Check which file exists (prefer compressed)
    if gz_trace_path.exists():
        trace_path = gz_trace_path
        is_gzipped = True
    elif plain_trace_path.exists():
        trace_path = plain_trace_path
        is_gzipped = False
    else:
        raise HTTPException(status_code=404, detail="Trace not found")
    
    # Validate the path is within allowed directory
    trace_path = validate_trace_path(trace_path, traces_dir)
    
    # Generate ETag
    etag = generate_etag(trace_path)
    
    # Check If-None-Match header
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)  # Not Modified
    
    # Check for Range header
    range_header = request.headers.get("range")
    
    if range_header:
        # Handle Range request - serve partial content
        try:
            # Parse Range header (e.g., "bytes=0-499")
            range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if not range_match:
                raise ValueError("Invalid Range format")
            
            start = int(range_match.group(1))
            end_str = range_match.group(2)
            end = int(end_str) if end_str else None
            
            # Stream the content for the requested range
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end or ''}/*",
                "ETag": etag,
            }
            
            if is_gzipped:
                # For gzipped files, decompress and serve partial content
                return StreamingResponse(
                    stream_gzipped_file_decompressed(trace_path, start, end),
                    status_code=206,  # Partial Content
                    media_type="application/x-ndjson",
                    headers=headers
                )
            else:
                # For plain files, serve partial content directly
                return StreamingResponse(
                    stream_plain_file_partial(trace_path, start, end),
                    status_code=206,  # Partial Content
                    media_type="application/x-ndjson",
                    headers=headers
                )
            
        except (ValueError, AttributeError) as e:
            raise HTTPException(status_code=400, detail="Invalid Range header")
    
    else:
        # No Range header - serve the entire file
        async def stream_file():
            """Stream the file."""
            chunk_size = 1024 * 1024  # 1MB chunks
            with open(trace_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        
        # Get file size for Content-Length
        file_size = trace_path.stat().st_size
        
        headers = {
            "ETag": etag,
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }
        
        # Add Content-Encoding header only for gzipped files
        if is_gzipped:
            headers["Content-Encoding"] = "gzip"
        
        return StreamingResponse(
            stream_file(),
            media_type="application/x-ndjson", 
            headers=headers
        )


async def stream_plain_file_partial(
    file_path: Path, 
    start: int = 0, 
    end: Optional[int] = None
) -> AsyncIterator[bytes]:
    """Stream a plain file for the given byte range.
    
    Args:
        file_path: Path to the plain file
        start: Start byte position
        end: End byte position (exclusive), None for EOF
        
    Yields:
        Chunks of data within the requested range
    """
    chunk_size = 1024 * 1024  # 1MB chunks
    
    def read_file():
        """Read file synchronously."""
        chunks = []
        
        with open(file_path, 'rb') as f:
            # Seek to start position
            f.seek(start)
            
            # Calculate bytes to read
            if end is not None:
                bytes_to_read = end - start
            else:
                bytes_to_read = None
            
            bytes_read = 0
            while True:
                # Determine chunk size
                if bytes_to_read is not None:
                    current_chunk_size = min(chunk_size, bytes_to_read - bytes_read)
                    if current_chunk_size <= 0:
                        break
                else:
                    current_chunk_size = chunk_size
                
                # Read chunk
                chunk = f.read(current_chunk_size)
                if not chunk:
                    break
                
                chunks.append(chunk)
                bytes_read += len(chunk)
        
        return chunks
    
    # Run the blocking I/O in a thread
    loop = asyncio.get_event_loop()
    chunks = await loop.run_in_executor(None, read_file)
    
    # Yield chunks one by one
    for chunk in chunks:
        yield chunk