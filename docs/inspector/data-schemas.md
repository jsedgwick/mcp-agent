# Inspector Data Schemas

**Version**: 1.0  
**Status**: Current  
**Primary Audience**: Backend Developers, Frontend Developers, AI Assistants

This document defines the authoritative data schemas for mcp-agent-inspector's internal data structures, API contracts, and event formats.

## 1. Overview

Inspector uses strongly-typed schemas at every layer:
- **Backend**: Pydantic models for validation and serialization
- **API**: OpenAPI 3.1 specification with JSON Schema
- **Frontend**: TypeScript interfaces generated from OpenAPI
- **Events**: JSON Schema for SSE event payloads

## 2. Core Data Models

### 2.1. SessionMeta

Represents a workflow session (running or historical).

```python
class SessionMeta(BaseModel):
    """Metadata for a workflow session."""
    
    id: str = Field(..., description="Unique session identifier (UUID or workflow_id)")
    status: Literal["running", "paused", "failed", "completed"] = Field(
        ..., 
        description="Current session state"
    )
    started_at: datetime = Field(..., description="ISO 8601 timestamp when session began")
    engine: Literal["asyncio", "temporal", "inbound"] = Field(
        default="asyncio",
        description="Execution engine type"
    )
    title: Optional[str] = Field(None, description="Human-readable session title")
    ended_at: Optional[datetime] = Field(None, description="ISO 8601 timestamp when session ended")
    
    # Computed fields
    duration_ms: Optional[int] = Field(None, description="Session duration in milliseconds")
    span_count: Optional[int] = Field(None, description="Number of spans in trace")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "session-123e4567-e89b-12d3-a456-426614174000",
                "status": "running",
                "started_at": "2025-01-01T12:00:00Z",
                "engine": "asyncio",
                "title": "Orchestrator Workflow - Planning Task"
            }
        }
```

### 2.2. Span (OpenTelemetry Compatible)

Follows OTel span data model with MCP-specific attributes.

```python
class SpanStatus(BaseModel):
    status_code: Literal["OK", "ERROR", "UNSET"] = "UNSET"
    description: Optional[str] = None

class Span(BaseModel):
    """OpenTelemetry-compatible span representation."""
    
    # Core fields (required)
    trace_id: str = Field(..., pattern="^[0-9a-f]{32}$")
    span_id: str = Field(..., pattern="^[0-9a-f]{16}$")
    name: str = Field(..., max_length=256)
    start_time: str = Field(..., description="RFC3339 timestamp")
    
    # Core fields (optional)
    end_time: Optional[str] = Field(None, description="RFC3339 timestamp")
    parent_span_id: Optional[str] = Field(None, pattern="^[0-9a-f]{16}$")
    
    # Semantic fields
    kind: SpanKind = SpanKind.INTERNAL
    status: SpanStatus = Field(default_factory=SpanStatus)
    
    # MCP-specific
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value pairs following telemetry-spec.md"
    )
    
    # Events and links
    events: List[SpanEvent] = Field(default_factory=list)
    links: List[SpanLink] = Field(default_factory=list)
    
    @validator("attributes")
    def validate_json_attributes(cls, v):
        """Ensure *_json attributes are valid JSON strings."""
        for key, value in v.items():
            if key.endswith("_json") and isinstance(value, str):
                try:
                    json.loads(value)
                except json.JSONDecodeError:
                    raise ValueError(f"Attribute {key} must be valid JSON")
        return v
```

### 2.3. Event Types (SSE)

All events inherit from a base class for consistent structure.

```python
class InspectorEvent(BaseModel):
    """Base class for all Inspector events."""
    
    type: str = Field(..., description="Event type discriminator")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_id: Optional[int] = Field(None, description="Monotonic event counter")
    
    class Config:
        discriminator = "type"

class SessionStarted(InspectorEvent):
    """Emitted when a new workflow session begins."""
    
    type: Literal["SessionStarted"] = "SessionStarted"
    session_id: str
    engine: Literal["asyncio", "temporal", "inbound"]
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SessionFinished(InspectorEvent):
    """Emitted when a workflow session completes."""
    
    type: Literal["SessionFinished"] = "SessionFinished"
    session_id: str
    status: Literal["completed", "failed", "cancelled"]
    error: Optional[str] = None
    duration_ms: Optional[int] = None

class WaitingOnSignal(InspectorEvent):
    """Emitted when a workflow pauses awaiting input."""
    
    type: Literal["WaitingOnSignal"] = "WaitingOnSignal"
    session_id: str
    signal_name: str
    prompt: Optional[str] = None
    signal_schema: Optional[Dict[str, Any]] = None

class Heartbeat(InspectorEvent):
    """Periodic metrics update for running session."""
    
    type: Literal["Heartbeat"] = "Heartbeat"
    session_id: str
    llm_calls_delta: int = 0
    tokens_delta: int = 0
    tool_calls_delta: int = 0
    current_span_count: int = 0
```

## 3. API Request/Response Schemas

### 3.1. Signal Request

Used to deliver control signals to running workflows.

```python
class SignalRequest(BaseModel):
    """Request body for /signal/{session_id} endpoint."""
    
    signal: Literal["human_input_answer", "pause", "resume", "cancel"]
    payload: Optional[Dict[str, Any]] = Field(
        None,
        description="Signal-specific payload data"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "signal": "human_input_answer",
                    "payload": {"answer": "Yes, proceed with deployment"}
                },
                {
                    "signal": "pause",
                    "payload": None
                }
            ]
        }
```

### 3.2. Sessions Response

```python
class SessionsResponse(BaseModel):
    """Response from /sessions endpoint."""
    
    sessions: List[SessionMeta]
    temporal_error: Optional[str] = Field(
        None,
        description="Present if Temporal query failed (graceful degradation)"
    )
```

## 4. Trace File Format

Inspector stores traces as gzipped JSONL files with specific structure.

### 4.1. File Naming Convention
```
~/.mcp_traces/{session_id}.jsonl.gz
```

### 4.2. Line Format
Each line is a JSON object representing one span:

```json
{
  "trace_id": "a1b2c3d4e5f6789012345678901234567",
  "span_id": "1234567890abcdef",
  "name": "workflow.run",
  "start_time": "2025-01-01T12:00:00.123456Z",
  "end_time": "2025-01-01T12:00:10.456789Z",
  "attributes": {
    "mcp.workflow.type": "orchestrator",
    "mcp.state.plan_json": "{\"steps\": [...]}",
    "session.id": "session-123"
  },
  "status": {"status_code": "OK"}
}
```

### 4.3. Size Constraints

- **Max file size**: 100MB before rotation
- **Max attribute size**: 30KB per attribute
- **Truncation flag**: `{attribute}_truncated: true` when limit exceeded

## 5. MCP-Specific Attribute Schemas

These JSON schemas define the structure of complex attributes.

### 5.1. PlanResult Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["plan_id", "steps"],
  "properties": {
    "plan_id": {"type": "string", "format": "uuid"},
    "steps": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["step_id", "description", "status"],
        "properties": {
          "step_id": {"type": "string", "format": "uuid"},
          "description": {"type": "string"},
          "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed", "failed"]
          },
          "dependencies": {
            "type": "array",
            "items": {"type": "string"}
          },
          "result": {"type": "object"}
        }
      }
    },
    "metadata": {"type": "object"}
  }
}
```

### 5.2. RouterDecision Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["selected_route", "confidence", "scores"],
  "properties": {
    "selected_route": {"type": "string"},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "reasoning": {"type": "string"},
    "scores": {
      "type": "object",
      "additionalProperties": {"type": "number"}
    }
  }
}
```

### 5.3. Message Content Schema (MCP Spec)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["role", "content"],
  "properties": {
    "role": {
      "type": "string",
      "enum": ["user", "assistant", "system"]
    },
    "content": {
      "type": "array",
      "items": {
        "oneOf": [
          {
            "type": "object",
            "required": ["type", "text"],
            "properties": {
              "type": {"const": "text"},
              "text": {"type": "string"}
            }
          },
          {
            "type": "object",
            "required": ["type", "data", "mimeType"],
            "properties": {
              "type": {"const": "image"},
              "data": {"type": "string", "contentEncoding": "base64"},
              "mimeType": {"type": "string"}
            }
          },
          {
            "type": "object",
            "required": ["type", "resource"],
            "properties": {
              "type": {"const": "resource"},
              "resource": {
                "type": "object",
                "required": ["uri"],
                "properties": {
                  "uri": {"type": "string", "format": "uri"},
                  "mimeType": {"type": "string"},
                  "text": {"type": "string"}
                }
              }
            }
          }
        ]
      }
    }
  }
}
```

## 6. Configuration Schema

Inspector configuration within mcp-agent.config.yaml:

```yaml
# JSON Schema for inspector section
type: object
properties:
  inspector:
    type: object
    properties:
      enabled:
        type: boolean
        default: true
        description: Enable Inspector instrumentation
      
      port:
        type: integer
        minimum: 1024
        maximum: 65535
        default: 7800
        description: Port for standalone server mode
      
      traces_dir:
        type: string
        default: "~/.mcp_traces"
        description: Directory for trace storage
      
      compression:
        type: string
        enum: ["gzip", "none"]
        default: "gzip"
        description: Trace file compression
      
      retention_days:
        type: integer
        minimum: 1
        default: 7
        description: Days to retain trace files
      
      performance:
        type: object
        properties:
          max_spans_per_trace:
            type: integer
            default: 100000
          max_attribute_size:
            type: integer
            default: 30720  # 30KB
          sampling_rate:
            type: number
            minimum: 0.0
            maximum: 1.0
            default: 1.0
```

## 7. Frontend TypeScript Interfaces

Generated from OpenAPI spec via `pnpm run gen:schemas`:

```typescript
// Generated by openapi-typescript
export interface SessionMeta {
  id: string
  status: "running" | "paused" | "failed" | "completed"
  started_at: string  // ISO 8601
  engine: "asyncio" | "temporal" | "inbound"
  title?: string
  ended_at?: string
  duration_ms?: number
  span_count?: number
}

export interface Span {
  trace_id: string
  span_id: string
  name: string
  start_time: string
  end_time?: string
  parent_span_id?: string
  attributes: Record<string, unknown>
  status: {
    status_code: "OK" | "ERROR" | "UNSET"
    description?: string
  }
}

export type InspectorEvent = 
  | SessionStarted
  | SessionFinished
  | WaitingOnSignal
  | Heartbeat
  | ProgressUpdate
  // ... other event types
```

## 8. Validation & Contracts

### 8.1. Runtime Validation

```python
# Backend validation
from pydantic import ValidationError

try:
    session = SessionMeta(**data)
except ValidationError as e:
    logger.error(f"Invalid session data: {e}")
    raise HTTPException(422, detail=e.errors())
```

### 8.2. Contract Testing

```python
# Schemathesis contract test
import schemathesis

schema = schemathesis.from_path("docs/inspector/openapi.yaml")

@schema.parametrize()
def test_api_contract(case):
    response = case.call()
    case.validate_response(response)
```

### 8.3. Schema Evolution

1. **Backward Compatible**: Add optional fields only
2. **Version Headers**: Include schema version in responses
3. **Deprecation**: Mark fields deprecated before removal
4. **Migration**: Provide data migration scripts

## Related Documentation

- [OpenAPI Specification](openapi.yaml) - Full API contract
- [Telemetry Specification](telemetry-spec.md) - Span attribute conventions
- [Architecture](architecture.md#file-based-trace-storage) - Storage design
- [Development Guide](development.md#json-attribute-convention) - Coding patterns