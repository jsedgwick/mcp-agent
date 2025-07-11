# Inspector Telemetry Specification

**Version**: 1.2 (2025-07-11)
**Status**: Current
**Primary Audience**: Developers, AI Assistants
**MCP Spec Version**: 2025-06-18

This document defines the practical OpenTelemetry (OTel) semantic conventions used by `mcp-agent-inspector`. It serves as the implementation guide for instrumenting the `mcp-agent` codebase.

This specification is aligned with the MCP specification rev 2025-06-18, translating its JSON-RPC 2.0 protocol and state-machine concepts into a pragmatic tracing implementation based on spans and attributes.

## 1. Guiding Principles

-   **Pragmatism over Granularity**: We capture the essential states and data of a workflow without creating an excessive number of spans. The duration of a span is as meaningful as its start and end events.
-   **Hierarchy is Key**: The structure of `mcp-agent` workflows (e.g., an Orchestrator calling workers) is modeled using parent-child relationships between spans. This is the primary mechanism for visualizing workflow composition.
-   **State via Attributes**: Rich contextual data (inputs, outputs, plans, decisions) is attached to spans as attributes, typically as JSON strings. This avoids "event explosion" and keeps related data co-located with the operation that produced it.

## 2. Core Span Names

The `name` of a span should be one of the following, indicating the type of operation.

| Span Name        | Description                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------- |
| `workflow.run`   | Represents the full execution of an `mcp-agent` workflow (e.g., `Orchestrator`, `Router`).                |
| `agent.call`     | Represents a call to an `Agent`, which may involve one or more LLM calls and tool calls.                |
| `llm.generate`   | Represents a single call to a Large Language Model's generation endpoint.                               |
| `tool.call`      | Represents a call to a specific tool, either through an `Agent` or directly.                            |
| `resource.fetch` | Represents fetching an MCP resource by URI.                                                             |
| `prompt.apply`   | Represents applying an MCP prompt template with parameters.                                             |
| `session.summary`| A special span, typically the last in a trace, holding summary statistics for the entire session.       |

## 3. Core MCP Attributes (The `mcp.*` Namespace)

These attributes provide the core data for the Inspector UI. They are populated through instrumentation hooks defined in [instrumentation-hooks.md](instrumentation-hooks.md). See the "Hook" column in each table for the specific hook that captures each attribute.

### 3.1. Workflow Attributes

*   `mcp.workflow.type` (string): The type of workflow. **Required** on `workflow.run` spans. [Hook: `before_workflow_run`]
    *   *Examples*: `orchestrator`, `router`, `parallel`, `evaluator_optimizer`, `swarm`
*   `mcp.workflow.input_json` (string): The initial input arguments for the workflow, serialized as JSON. [Hook: `before_workflow_run`]
*   `mcp.workflow.output_json` (string): The final result of the workflow, serialized as JSON. [Hook: `after_workflow_run`]

### 3.2. Agent and Tool Attributes

*   `mcp.agent.name` (string): The name of the `Agent` being called. Added to `agent.call` spans.
*   `mcp.tool.name` (string): The name of the tool being executed (e.g., `fetch-fetch`). Added to `tool.call` spans. [Hook: `before_tool_call`]
*   `mcp.tool.input_json` (string): The arguments passed to the tool, serialized as JSON. [Hook: `before_tool_call`]
*   `mcp.tool.output_json` (string): The result returned by the tool, serialized as JSON. [Hook: `after_tool_call`]
*   `mcp.tool.structured_output_json` (string): MCP §6.2 structured data from tool response. Added by `agent.call_tool()`. Shown in "Structured Data" tab. [Hook: `after_tool_call`]
*   `mcp.model.preferences_json` (string): MCP §4.4 model preferences for selection. Added by `llm_selector.py`. Shown in Model Viewer.

### 3.3. LLM Attributes

*   `mcp.llm.prompt_json` (string): The full prompt (including messages, system prompt, etc.) sent to the LLM, serialized as JSON. [Hook: `before_llm_generate`]
*   `mcp.llm.response_json` (string): The full response received from the LLM, serialized as JSON. [Hook: `after_llm_generate`]
*   `mcp.llm.provider` (string): The name of the LLM provider (e.g., `openai`, `anthropic`). [Hook: `before_llm_generate`]
*   `mcp.llm.model` (string): The specific model name (e.g., `gpt-4o`, `claude-3-opus-20240229`). [Hook: `before_llm_generate`]

**Multi-part messages**  
The JSON stored in `mcp.llm.prompt_json` and `mcp.llm.response_json` is **exactly** the
MCP `Message` schema (array of `Content` blocks, §5.1 of the spec).  
See §3.4.1 for the canonical example.

### 3.4. State and Result Attributes

This is a flexible mechanism for capturing arbitrary state from workflows.

#### Naming Conventions

*   `mcp.state.<description>_json` (string): A snapshot of a Pydantic model or other state object within a workflow, serialized as JSON. The `<description>` should be a concise, snake_cased name of the state being captured.
*   `mcp.result.<description>_json` (string): The return value of a function or workflow, serialized as JSON.
*   **Required Suffix**: Attributes capturing state or results MUST end with `_state_json` or `_result_json`
*   **Default key** =  
    `mcp.result.<func_name>_json`  (for return values)  
    `mcp.state.<func_name>_json`   (for explicit snapshots)

    where `<func_name>` is the **snake_cased Python function name** unless the decorator is called with `description="custom_name"`.

    ```python
    @dump_state_to_span(description="plan")
    def run(...) -> PlanResult: ...   # → mcp.result.plan_json
    
    @dump_state_to_span(description="router_decision")
    def route(...) -> RouterDecision: ...  # → mcp.result.router_decision_json
    ```

*   **Examples**: 
    *   `mcp.state.plan_json` - PlanResult from orchestrator
    *   `mcp.state.router_decision_json` - RouterDecision from router  
    *   `mcp.result.evaluation_json` - EvaluationResult from evaluator
    *   `mcp.state.aggregator_resolution_json` - Tool resolution from aggregator

#### Size Limits and Truncation

*   **Default Limit**: 30KB per attribute (applies to all `*_json` attributes)
*   **Truncation Behavior**: When an attribute exceeds the size limit:
    ```python
    if len(json_str) > MAX_ATTR_SIZE:
        span.set_attribute(f"{key}_truncated", True)
        json_str = json_str[:MAX_ATTR_SIZE]
    ```
*   **Truncation Flag**: `<attribute_name>_truncated` (boolean) indicates partial data

#### Standard State Models

Common Pydantic models captured as state:

```python
# PlanResult (orchestrator workflows)
{
    "plan_id": "uuid",
    "steps": [
        {
            "step_id": "uuid",
            "description": "string",
            "status": "pending|in_progress|completed|failed",
            "dependencies": ["step_id"],
            "result": {...}
        }
    ],
    "metadata": {...}
}

# RouterDecision (router workflows)
{
    "selected_route": "route_name",
    "confidence": 0.95,
    "reasoning": "string",
    "scores": {
        "route1": 0.95,
        "route2": 0.05
    }
}

# EvaluationResult (evaluator workflows)
{
    "quality_score": 0.85,
    "passed": true,
    "feedback": "string",
    "metrics": {...}
}
```

#### Implementation via Decorator

The `@dump_state_to_span` decorator automatically captures return values:

```python
@dump_state_to_span()
async def run(self, context: Context) -> PlanResult:
    # ... workflow logic
    return result  # Automatically captured as mcp.state.plan_json
```

### 3.4.1. Message Content Schema

The MCP Message schema supports multi-part content blocks, enabling rich interactions:

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "Analyze this image and code"
    },
    {
      "type": "image",
      "data": "base64_encoded_image_data",
      "mimeType": "image/png"
    },
    {
      "type": "resource",
      "resource": {
        "uri": "file:///project/main.py",
        "mimeType": "text/x-python",
        "text": "def main():\n    pass"
      }
    }
  ]
}
```

Content types include:
- `text`: Plain text content
- `image`: Base64-encoded image data with MIME type
- `resource`: File or remote resource with URI and content
- `tool_use`: Tool invocation request (in assistant messages)

### 3.5. RPC Wire Attributes

These attributes capture the JSON-RPC 2.0 protocol details:

*   `mcp.jsonrpc.version` (string): JSON-RPC version, always "2.0"
*   `mcp.rpc.method` (string): The RPC method being called (e.g., "tools/call", "resources/list", "prompts/get")
*   `mcp.rpc.id` (string | int): The JSON-RPC request ID for correlation

#### Protocol-level Debugging Attributes (Optional)
*   `mcp.rpc.request_json` (string): The full JSON-RPC request envelope, serialized as JSON. Subject to size limits (30KB).
*   `mcp.rpc.response_json` (string): The full JSON-RPC response envelope, serialized as JSON. Subject to size limits (30KB).
*   `mcp.rpc.duration_ms` (int): Time taken for the RPC call in milliseconds
*   `mcp.rpc.retry_count` (int): Number of retry attempts for this RPC call (0 if successful on first attempt)
*   `mcp.rpc.transport` (string): Transport protocol used: "stdio", "sse", "http"
*   `mcp.rpc.server_uri` (string): URI of the MCP server (e.g., "http://localhost:8080", "stdio:///path/to/server", "sse://example.com/events")
*   `mcp.rpc.direction` (string): Whether this is an "inbound" or "outbound" RPC call

#### Transport Health Attributes

These attributes track transport layer health and configuration:

| Attribute | Type | Description | Hook |
|-----------|------|-------------|------|
| `mcp.transport.status` | string | Transport connection status: "connected", "disconnected", "reconnecting" | `after_rpc_response`, `error_rpc_request` |
| `mcp.transport.reconnect_count` | int | Number of reconnection attempts | `error_rpc_request` |
| `mcp.transport.config_json` | string | Transport configuration as JSON (e.g., timeout, retry settings) | `before_rpc_request` |

### 3.6. Feature-specific Attributes

#### Resource Attributes
*   `mcp.resource.uri` (string): The URI of the resource being fetched
*   `mcp.resource.mime_type` (string): MIME type of the resource content
*   `mcp.resource.bytes` (int): Size of the resource in bytes

#### Prompt Attributes
*   `mcp.prompt.template_id` (string): ID of the prompt template being used
*   `mcp.prompt.parameters_json` (string): Parameters passed to the prompt, as JSON

#### Progress & Cancellation
*   `mcp.progress.token` (string): Progress tracking token
*   `mcp.cancellation.requested` (bool): Whether cancellation was requested

### 3.7. Standard Error & Status Codes

MCP defines standard error codes that map to JSON-RPC errors:

| Error Code | Description | Example Span Attributes |
|------------|-------------|------------------------|
| `UNKNOWN_TOOL` | Tool not found in registry | `mcp.error.code="UNKNOWN_TOOL"` |
| `INVALID_PARAMS` | Invalid parameters provided | `mcp.error.code="INVALID_PARAMS"` |
| `TIMEOUT` | Operation timed out | `mcp.error.code="TIMEOUT"` |
| `CANCELLED` | Operation was cancelled | `mcp.error.code="CANCELLED"` |
| `SERVER_ERROR` | Internal server error | `mcp.error.code="SERVER_ERROR"` |

*   `mcp.status.code` (string): The final status of the operation represented by the span. Should be `ok` or `error`.
*   `mcp.error.code` (string): Standard MCP error code when status is `error`
*   `mcp.error.message` (string): Human-readable error description
*   `mcp.stop_reason` (string): If present, explains why an LLM generation ended (e.g. "length", "tool_use").

### 3.8. Canonical Correlation Identifier

For any *cross-process* stitch-up the **single source of truth is `mcp.request_id`**.  
The Inspector UI performs distributed-trace stitching by matching `mcp.request_id` on a **client-side `tool.call` span** with the `workflow.run` *root* span on the server side.

• `session_id` remains a purely local container for file storage and UI routing (`/_inspector/trace/{session_id}`).

• `mcp.rpc.id` (JSON-RPC id) may differ and MUST **never** be used for stitching because a single tool call can fan-out into multiple RPC ids.

## 4. Real-time Events (via SSE)

In addition to traces, the Inspector uses a real-time event stream for live updates. These events are not part of the OTel trace but are sent via Server-Sent Events (SSE).

| Event Type          | Description                                                              | Key Fields                                        |
| ------------------- | ------------------------------------------------------------------------ | ------------------------------------------------- |
| `SessionStarted`    | Fired when a new workflow session begins.                                | `session_id`, `start_time`, `engine`, `title`     |
| `Heartbeat`         | Fired periodically with delta metrics for a running session.             | `session_id`, `llm_calls_delta`, `tokens_delta`   |
| `WaitingOnSignal`   | Fired when a workflow pauses, awaiting external input (e.g., human).     | `session_id`, `signal_name`, `prompt`, `schema`   |
| `SessionFinished`   | Fired when a workflow session completes, fails, or is cancelled.         | `session_id`, `status`, `end_time`, `error`       |
| `ResourceFetched`   | Fired when a resource is successfully fetched.                           | `session_id`, `uri`, `mime_type`, `bytes`         |
| `PromptUsed`        | Fired when a prompt template is applied.                                 | `session_id`, `template_id`, `parameters`         |
| `ProgressUpdate`    | Fired to report progress on long-running operations.                     | `session_id`, `progress_token`, `percent`, `message` |

## 5. Temporal-Specific Conventions

When running with the optional Temporal executor, the following conventions apply:

-   The `session.id` attribute on spans corresponds to the Temporal `workflow_id`.
-   The `run.id` attribute corresponds to the Temporal `run_id`.
-   Workers write traces to a shared filesystem, and the gateway reads them. This allows for distributed tracing without direct communication between workers and the gateway.
-   The `@dump_state_to_span` decorator should check `workflow.unsafe.is_replaying()` and avoid expensive serialization during replay.

**Testing Note**: All events are contract-tested via Schemathesis against the OpenAPI spec at [docs/inspector/openapi.yaml](openapi.yaml). The OpenAPI spec defines event schemas in the SSE endpoint definition. PRs failing Schemathesis will be blocked.
