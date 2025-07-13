from datetime import datetime
from os import linesep
from pathlib import Path
from typing import Callable, Sequence, Optional
import uuid
import re
import threading

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.resources import Resource

from mcp_agent.config import TracePathSettings
from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class FileSpanExporter(SpanExporter):
    """Implementation of :class:`SpanExporter` that writes spans as JSON to a file."""

    def __init__(
        self,
        service_name: str | None = None,
        session_id: str | None = None,
        formatter: Callable[[ReadableSpan], str] = lambda span: span.to_json(
            indent=None
        )
        + linesep,
        path_settings: TracePathSettings | None = None,
        custom_path: str | None = None,
    ):
        self.formatter = formatter
        self.service_name = service_name
        # --- START MODIFICATION ---
        # Do NOT resolve session_id or filepath at init time.
        self.path_settings = path_settings or TracePathSettings()
        self.custom_path = custom_path
        self._filepath: Optional[Path] = None
        self._lock = threading.Lock()
        # --- END MODIFICATION ---

    def _get_or_create_filepath(self, span_resource: Resource) -> Path:
        """
        Lazily determines the file path on the first export, ensuring session_id is available.
        """
        with self._lock:
            if self._filepath:
                return self._filepath

            # If custom_path is provided, use it directly
            if self.custom_path:
                self._filepath = Path(self.custom_path).expanduser()
                self._filepath.parent.mkdir(parents=True, exist_ok=True)
                return self._filepath
            
            # Extract session.id from the span's resource attributes
            raw_session_id = span_resource.attributes.get("session.id", str(uuid.uuid4()))
            
            # --- NEW: Sanitize the session ID ---
            sanitized_session_id = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_session_id)
            
            path_pattern = self.path_settings.path_pattern
            unique_id_type = self.path_settings.unique_id
            
            if unique_id_type == "session_id":
                unique_id = sanitized_session_id
            else: # "timestamp"
                now = datetime.now()
                time_format = self.path_settings.timestamp_format
                unique_id = now.strftime(time_format)

            path = path_pattern.replace("{unique_id}", unique_id)
            self._filepath = Path(path).expanduser()
            self._filepath.parent.mkdir(parents=True, exist_ok=True)
            return self._filepath


    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if not spans:
            return SpanExportResult.SUCCESS
        
        # --- START MODIFICATION ---
        # Ensure the filepath is determined using the context from the first span.
        try:
            filepath = self._get_or_create_filepath(spans[0].resource)
        except Exception as e:
            logger.error(f"Failed to determine trace file path: {e}")
            return SpanExportResult.FAILURE
        # --- END MODIFICATION ---

        # (The rest of the export method remains largely the same, but uses `filepath`)
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                for span in spans:
                    f.write(self.formatter(span))
                f.flush()
            return SpanExportResult.SUCCESS
        except Exception as e:
            logger.error(f"Failed to export span to {filepath}: {e}")
            return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
