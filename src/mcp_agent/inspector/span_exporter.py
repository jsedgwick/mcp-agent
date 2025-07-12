"""Inspector-specific span exporter that writes gzipped JSONL files."""

import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence
import uuid

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from mcp_agent.config import TracePathSettings
from mcp_agent.logging.logger import get_logger
from .context import get as get_session_id

logger = get_logger(__name__)


class InspectorFileSpanExporter(SpanExporter):
    """
    Inspector-specific span exporter that writes gzipped JSONL to ~/.mcp_traces/.
    
    This exporter:
    - Writes spans as gzipped JSONL files
    - Uses session_id from Inspector context for filenames
    - Properly expands ~ in paths
    - Handles file rotation at configured size limits
    """
    
    def __init__(
        self,
        service_name: Optional[str] = None,
        session_id: Optional[str] = None,
        formatter: Callable[[ReadableSpan], str] = lambda span: span.to_json(indent=None),
        path_settings: Optional[TracePathSettings] = None,
        custom_path: Optional[str] = None,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB default
    ):
        self.formatter = formatter
        self.service_name = service_name
        self.session_id = session_id
        self.path_settings = path_settings or TracePathSettings()
        self.custom_path = custom_path
        self.max_file_size = max_file_size
        self._current_chunk = 0
        self._setup_file()
    
    def _setup_file(self) -> None:
        """Set up the trace file path and create directory if needed."""
        self.filepath = Path(self._get_trace_filename())
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
    
    def _get_trace_filename(self) -> str:
        """Generate a trace filename based on the path settings."""
        # Get session_id from Inspector context if not provided
        if not self.session_id:
            self.session_id = get_session_id()
        
        # If custom_path is provided, use it directly
        if self.custom_path:
            base_path = Path(self.custom_path).expanduser()
            if self._current_chunk > 0:
                return str(base_path.with_suffix(f'.chunk_{self._current_chunk}.jsonl.gz'))
            return str(base_path.with_suffix('.jsonl.gz'))
        
        # Use path pattern from settings
        path_pattern = self.path_settings.path_pattern
        unique_id_type = self.path_settings.unique_id
        
        if unique_id_type == "session_id":
            unique_id = self.session_id
        elif unique_id_type == "timestamp":
            now = datetime.now()
            time_format = self.path_settings.timestamp_format
            unique_id = now.strftime(time_format)
        else:
            raise ValueError(
                f"Invalid unique_id type: {unique_id_type}. Expected 'session_id' or 'timestamp'."
            )
        
        # Replace unique_id and expand tilde
        path = path_pattern.replace("{unique_id}", unique_id)
        base_path = Path(path).expanduser()
        
        # Add chunk number if needed
        if self._current_chunk > 0:
            return str(base_path.with_suffix(f'.chunk_{self._current_chunk}.jsonl.gz'))
        
        # Ensure .gz extension
        if not str(base_path).endswith('.gz'):
            return str(base_path) + '.gz'
        return str(base_path)
    
    def _check_rotation(self) -> None:
        """Check if file needs rotation due to size."""
        if self.filepath.exists() and self.filepath.stat().st_size >= self.max_file_size:
            self._current_chunk += 1
            self._setup_file()
            logger.info(f"Rotated trace file to chunk {self._current_chunk}")
    
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export spans to gzipped JSONL file."""
        if not spans:
            return SpanExportResult.SUCCESS
        
        try:
            self._check_rotation()
            
            # Open in append binary mode for gzip
            with gzip.open(self.filepath, 'ab') as f:
                for span in spans:
                    # Format span as JSON and encode to bytes
                    json_str = self.formatter(span)
                    if not json_str.endswith('\n'):
                        json_str += '\n'
                    f.write(json_str.encode('utf-8'))
            
            logger.debug(f"Exported {len(spans)} spans to {self.filepath}")
            return SpanExportResult.SUCCESS
            
        except Exception as e:
            logger.error(f"Failed to export spans to {self.filepath}: {e}", exc_info=True)
            return SpanExportResult.FAILURE
    
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush any pending spans."""
        # File writes are immediate, so nothing to flush
        return True
    
    def shutdown(self) -> None:
        """Shutdown the exporter."""
        # No resources to clean up
        pass