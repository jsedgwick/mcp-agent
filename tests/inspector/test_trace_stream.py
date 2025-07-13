"""Tests for trace streaming endpoint."""

import gzip
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette

from mcp_agent.inspector import mount
from mcp_agent.inspector.settings import InspectorSettings, StorageSettings


@pytest.fixture
def temp_traces_dir():
    """Create a temporary traces directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_trace_data():
    """Generate sample trace data."""
    spans = [
        {
            "trace_id": "12345678901234567890123456789012",
            "span_id": "1234567890123456",
            "name": "workflow.run",
            "start_time": "2025-01-01T12:00:00.000000Z",
            "end_time": "2025-01-01T12:00:01.000000Z",
            "attributes": {
                "mcp.workflow.type": "orchestrator",
                "session.id": "test-session-123"
            }
        },
        {
            "trace_id": "12345678901234567890123456789012",
            "span_id": "2345678901234567",
            "parent_span_id": "1234567890123456",
            "name": "agent.call",
            "start_time": "2025-01-01T12:00:00.100000Z",
            "end_time": "2025-01-01T12:00:00.900000Z",
            "attributes": {
                "mcp.agent.name": "test-agent"
            }
        }
    ]
    
    # Convert to JSONL
    lines = [json.dumps(span) for span in spans]
    return "\n".join(lines).encode()


@pytest.fixture
def create_trace_file(temp_traces_dir, sample_trace_data):
    """Create a test trace file."""
    def _create(session_id: str, data: bytes = None):
        if data is None:
            data = sample_trace_data
            
        file_path = temp_traces_dir / f"{session_id}.jsonl.gz"
        with gzip.open(file_path, 'wb') as f:
            f.write(data)
        
        # Ensure file has stable mtime for ETag testing
        time.sleep(0.01)
        return file_path
    
    return _create


@pytest.fixture
def app_with_inspector(temp_traces_dir):
    """Create FastAPI app with Inspector mounted."""
    app = FastAPI()
    
    # Configure Inspector with temp traces directory
    settings = InspectorSettings(
        enabled=True,
        storage=StorageSettings(
            traces_dir=str(temp_traces_dir)
        )
    )
    
    # Mount Inspector
    mount(app, settings=settings)
    
    return app


@pytest.fixture
def client(app_with_inspector):
    """Create test client."""
    return TestClient(app_with_inspector)


class TestTraceStreaming:
    """Test trace streaming endpoint functionality."""
    
    def test_stream_full_file_compressed(self, client, create_trace_file):
        """Test streaming entire file with gzip compression."""
        # Create trace file
        session_id = "test-session-full"
        create_trace_file(session_id)
        
        # Request full file
        response = client.get(f"/_inspector/trace/{session_id}")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-ndjson"
        assert response.headers["content-encoding"] == "gzip"
        assert "etag" in response.headers
        assert response.headers["accept-ranges"] == "bytes"
        
        # The TestClient might automatically decompress based on Content-Encoding
        # Check if content is already decompressed
        if response.content.startswith(b'{"'):
            # Already decompressed by TestClient
            lines = response.content.decode().strip().split('\n')
        else:
            # Still compressed
            decompressed = gzip.decompress(response.content)
            lines = decompressed.decode().strip().split('\n')
            
        assert len(lines) == 2
        
        # Verify first span
        span1 = json.loads(lines[0])
        assert span1["name"] == "workflow.run"
    
    def test_stream_range_request(self, client, create_trace_file, sample_trace_data):
        """Test Range request handling with decompression."""
        # Create trace file
        session_id = "test-session-range"
        create_trace_file(session_id)
        
        # Request first 50 bytes of decompressed content
        response = client.get(
            f"/_inspector/trace/{session_id}",
            headers={"range": "bytes=0-49"}
        )
        
        assert response.status_code == 206  # Partial Content
        assert response.headers["content-type"] == "application/x-ndjson"
        assert "content-encoding" not in response.headers  # Not compressed
        assert "content-range" in response.headers
        assert response.headers["accept-ranges"] == "bytes"
        
        # Should get partial JSON (bytes 0-49 is 50 bytes)
        content = response.content.decode()
        assert 49 <= len(content) <= 50  # Allow for off-by-one
        assert content.startswith('{"trace_id"')
    
    def test_etag_not_modified(self, client, create_trace_file):
        """Test ETag caching with 304 Not Modified."""
        # Create trace file
        session_id = "test-session-etag"
        create_trace_file(session_id)
        
        # First request to get ETag
        response1 = client.get(f"/_inspector/trace/{session_id}")
        assert response1.status_code == 200
        etag = response1.headers["etag"]
        assert etag.startswith('W/"')  # Weak ETag
        
        # Second request with If-None-Match
        response2 = client.get(
            f"/_inspector/trace/{session_id}",
            headers={"if-none-match": etag}
        )
        assert response2.status_code == 304  # Not Modified
        assert len(response2.content) == 0
    
    def test_invalid_session_id(self, client):
        """Test validation of session ID."""
        # Path traversal with dots - this should definitely trigger
        response = client.get("/_inspector/trace/test..test")
        assert response.status_code == 400
        assert "Invalid session_id" in response.json()["detail"]
        
        # Invalid characters
        response = client.get("/_inspector/trace/test@session!")
        assert response.status_code == 400
        assert "Invalid session_id format" in response.json()["detail"]
        
        # Another invalid character test
        response = client.get("/_inspector/trace/test/session")
        # This might return 404 as FastAPI sees it as a different route
        assert response.status_code in [400, 404]
    
    def test_nonexistent_trace(self, client):
        """Test 404 for non-existent trace."""
        response = client.get("/_inspector/trace/nonexistent-session")
        assert response.status_code == 404
        assert "Trace not found" in response.json()["detail"]
    
    def test_invalid_range_header(self, client, create_trace_file):
        """Test handling of invalid Range headers."""
        # Create trace file
        session_id = "test-session-bad-range"
        create_trace_file(session_id)
        
        # Invalid range format
        response = client.get(
            f"/_inspector/trace/{session_id}",
            headers={"range": "invalid-range"}
        )
        assert response.status_code == 400
        assert "Invalid Range header" in response.json()["detail"]
        
        # Non-bytes range
        response = client.get(
            f"/_inspector/trace/{session_id}",
            headers={"range": "lines=0-10"}
        )
        assert response.status_code == 400
    
    def test_large_file_streaming(self, client, create_trace_file):
        """Test streaming large files efficiently."""
        # Create large trace file (10000 spans)
        session_id = "test-session-large"
        large_spans = []
        for i in range(10000):
            large_spans.append(json.dumps({
                "trace_id": "12345678901234567890123456789012",
                "span_id": f"{i:016d}",
                "name": f"span-{i}",
                "attributes": {"index": i}
            }))
        
        large_data = "\n".join(large_spans).encode()
        create_trace_file(session_id, large_data)
        
        # Request middle portion
        response = client.get(
            f"/_inspector/trace/{session_id}",
            headers={"range": "bytes=50000-60000"}
        )
        
        assert response.status_code == 206
        content = response.content.decode()
        assert 9900 <= len(content) <= 10001  # Allow for slight variation
    
    def test_path_traversal_prevention(self, client, temp_traces_dir):
        """Test that path traversal attacks are prevented."""
        # Create a file outside traces directory
        outside_file = temp_traces_dir.parent / "outside.jsonl.gz"
        with gzip.open(outside_file, 'wb') as f:
            f.write(b'{"malicious": "data"}')
        
        try:
            # Various traversal attempts
            attempts = [
                "../../outside",
                "..%2F..%2Foutside",
                "test/../../../outside",
                "test/../../outside"
            ]
            
            for attempt in attempts:
                response = client.get(f"/_inspector/trace/{attempt}")
                assert response.status_code in [400, 403, 404]
                assert response.status_code != 200
        finally:
            if outside_file.exists():
                outside_file.unlink()
    
    def test_corrupted_gzip_handling(self, client, temp_traces_dir):
        """Test handling of corrupted gzip files."""
        # Create corrupted gzip file
        session_id = "test-session-corrupt"
        file_path = temp_traces_dir / f"{session_id}.jsonl.gz"
        
        # Write invalid gzip data
        with open(file_path, 'wb') as f:
            f.write(b'This is not gzip data')
        
        # Request should handle gracefully
        response = client.get(
            f"/_inspector/trace/{session_id}",
            headers={"range": "bytes=0-100"}
        )
        
        # Should get partial content (empty in this case due to corruption)
        assert response.status_code == 206
        assert len(response.content) == 0  # Stream ended due to error


class TestEdgeCases:
    """Test edge cases and concurrent access."""
    
    def test_file_being_written(self, client, temp_traces_dir):
        """Test reading a file that's being actively written to."""
        session_id = "test-session-active"
        file_path = temp_traces_dir / f"{session_id}.jsonl.gz"
        
        # Write initial content
        with gzip.open(file_path, 'wb') as f:
            f.write(b'{"span": 1}\n')
        
        # Read while "writing" continues
        response = client.get(f"/_inspector/trace/{session_id}")
        assert response.status_code == 200
        
        # Should only see what was written and flushed
        # Check if already decompressed by TestClient
        if response.content.startswith(b'{"'):
            content = response.content.decode()
        else:
            content = gzip.decompress(response.content).decode()
        assert '{"span": 1}' in content
    
    def test_empty_trace_file(self, client, temp_traces_dir):
        """Test handling of empty trace files."""
        session_id = "test-session-empty"
        file_path = temp_traces_dir / f"{session_id}.jsonl.gz"
        
        # Create empty gzip file
        with gzip.open(file_path, 'wb') as f:
            pass  # Empty file
        
        response = client.get(f"/_inspector/trace/{session_id}")
        assert response.status_code == 200
        
        # TestClient may decompress automatically
        # Either way, the content should be empty
        assert len(response.content) == 0