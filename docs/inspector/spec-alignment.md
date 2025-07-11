# MCP-Agent-Inspector Spec Alignment Guide

**Aligned to MCP spec rev 2025-06-18**

This document maps concepts between the official Machine Control Protocol spec and Inspector's internal implementation.

## Core Identity Mappings

| MCP Spec Term | Inspector Term | Location | Notes |
|---------------|----------------|----------|-------|
| request_id | session_id (for inbound) | McpRequestStarted event | Inbound requests create sessions |
| server_id | peer_server_id | mcp.peer.server_id attribute | Identity of remote MCP server |
| agent.server_id | mcp.agent.server_id | Span attribute | Identity of local agent server |
| tool_name | tool.name → mcp.tool.name | Span attribute | Tool being invoked |
| jsonrpc | mcp.jsonrpc.version | Span attribute | JSON-RPC version (always "2.0") |
| method | mcp.rpc.method | Span attribute | RPC method (e.g., "tools/call") |
| id | mcp.rpc.id | Span attribute | JSON-RPC request ID |
| structured_output | mcp.tool.structured_output_json | Span attribute | MCP §6.2 structured data |
| model_preferences | mcp.model.preferences_json | Span attribute | MCP §4.4 model selection |
| stop_reason | mcp.stop_reason | Span attribute | LLM generation termination reason |

## Request/Response Envelope (Spec §3)

The MCP spec defines standard envelope fields that Inspector captures:

```json
{
  "request_id": "uuid-here",
  "server_id": "remote-server-id",
  "method": "tool.call",
  "params": {
    "tool_name": "search_code",
    "arguments": {}
  }
}
```

Inspector mapping:
- `request_id` → `mcp.request_id` span attribute
- `server_id` → `mcp.peer.server_id` span attribute
- Inbound requests create session with `id = request_id`

## Trace Propagation (Spec §4.2)

MCP spec mandates request_id propagation for distributed tracing:

1. **Outbound (client role)**:
   - Generate `mcp.request_id` if not present
   - Include in HTTP header: `X-MCP-Request-Id`
   - Set `mcp.parent_request_id` from current context

2. **Inbound (server role)**:
   - Extract `mcp.request_id` from header
   - Create span with this ID
   - Propagate to child operations

## Agent Identity (Spec §2.1.3)

Every agent has a server_id for identification:
- Set via `MCP_SERVER_ID` env var or config
- Inspector captures as `mcp.agent.server_id`
- Used to differentiate multiple agents in UI

## Sessions vs Workflows

| Concept | Definition | Inspector Usage |
|---------|------------|-----------------|
| Session | Top-level execution context | Row in session table |
| Workflow | Asyncio/Temporal execution | Type of session (engine field) |
| Inbound Request | MCP server handling | Another session type |

Session types in Inspector:
- `engine="asyncio"` - Local workflow execution
- `engine="temporal"` - Temporal workflow execution  
- `engine="inbound"` - MCP server request handling

## Event Mappings

| MCP Concept | Inspector Event | When Emitted |
|-------------|-----------------|--------------|
| Request start | McpRequestStarted | Inbound/outbound request begins |
| Request end | McpRequestFinished | Request completes (OK/ERROR) |
| Tool not found | McpRequestFinished with status=ERROR | Unknown tool requested |

## Attribute Naming Convention

All MCP-related attributes use `mcp.` prefix:
- `mcp.agent.*` - Local agent properties
- `mcp.peer.*` - Remote server properties
- `mcp.workflow.*` - Workflow execution details
- `mcp.llm.*` - LLM interaction details
- `mcp.state.*` - State snapshots

## Error Code Alignment

MCP spec defines standard error codes (§5):

| Spec Error | Inspector Representation |
|------------|-------------------------|
| UNKNOWN_TOOL | McpRequestFinished.error_code = "UNKNOWN_TOOL" |
| TIMEOUT | Span error.type = "timeout" |
| INVALID_REQUEST | HTTP 400 + no span created |

## Resources & Prompts Mapping

| MCP Term | Inspector Attribute/Event | Notes |
|----------|---------------------------|-------|
| resource.uri | mcp.resource.uri | Present on tool.call or resource.fetch spans |
| prompt.templateId | mcp.prompt.template_id | Captured from inbound/outbound prompt APIs |
| progressToken | mcp.progress.token | Passed through ProgressUpdate events |

## Protocol & Transport Attributes (Spec §3-4)

The Inspector captures detailed protocol-level information for debugging transport issues:

| MCP Spec Section | Inspector Attribute | Description | Hook |
|------------------|---------------------|-------------|------|
| §3.1 JSON-RPC | mcp.jsonrpc.version | Always "2.0" | before_rpc_request |
| §3.2 Request | mcp.rpc.method | RPC method (tools/call, etc.) | before_rpc_request |
| §3.2 Request ID | mcp.rpc.id | JSON-RPC request ID | before_rpc_request |
| §3.3 Transport | mcp.rpc.transport | stdio\|sse\|http\|websocket | before_rpc_request |
| §3.4 Response | mcp.rpc.duration_ms | Round-trip time | after_rpc_response |
| §4.1 Connection | mcp.transport.status | connected\|disconnected\|reconnecting | after_rpc_response, error_rpc_request |
| §4.2 Retry | mcp.transport.reconnect_count | Number of reconnect attempts | error_rpc_request |

## Dual Tracing Surfaces

Every mcp-agent process opens two tracing surfaces:

1. **Client-side outbound** (engine="asyncio" or "temporal")
   - Traces outgoing tool calls, resource fetches, prompt applications
   - Uses local `mcp.agent.server_id` as identity

2. **Server-side inbound** (engine="inbound")
   - Traces incoming MCP requests when acting as server
   - Creates sessions with `session_id = request_id`

Both surfaces share the `mcp.agent.server_id` value to enable UI call-graph stitching.

## Implementation Notes

1. **Zero External Dependencies**: Inspector captures MCP data without requiring external MCP libraries
2. **In-Process Only**: All MCP inspection happens within the Python process
3. **Spec-First**: When in doubt, follow MCP spec naming exactly
4. **Backwards Compatible**: Old attributes (gen_ai.*, tool.*) mapped internally to mcp.*

## Spec Compliance Warnings

### 1. Attribute Size Limits (Deviation)

**MCP Spec**: No explicit size limits on message content
**Inspector**: 30KB limit per attribute

```python
# WARNING: Large prompts/responses will be truncated
if len(json_str) > 30720:  # 30KB
    span.set_attribute(f"{key}_truncated", True)
    json_str = json_str[:30720]
```

**Impact**: Large prompts or tool outputs (> 30 KB) may be truncated in the UI. Check for `*_truncated=true` attributes.

### 2. Session ID Semantics (Extension)

**MCP Spec**: `request_id` for correlation only
**Inspector**: Uses `request_id` as `session_id` for inbound requests

```python
# Inspector-specific behavior
if inbound_request:
    session_id = request_headers["X-MCP-Request-Id"]
```

**Impact**: Inbound MCP requests create full Inspector sessions, not just spans.

### 3. Progress Granularity (Implementation Choice)

**MCP Spec**: No rate limiting on progress updates
**Inspector**: Throttles to 2Hz maximum

```python
# Prevents UI flooding but may miss rapid updates
throttled = await throttle_events(event, max_hz=2)
```

**Impact**: Very rapid progress updates will be sampled, showing only ~2 updates per second.

### 4. Cancellation Scope (Limitation)

**MCP Spec**: Cancellation applies to specific operation
**Inspector**: Cancel button cancels entire session

**Impact**: Fine-grained cancellation of individual operations not yet supported.

### 5. Resource Content Storage (Security)

**MCP Spec**: Resources can contain arbitrary content
**Inspector**: Does NOT store resource content in traces

```python
# Only metadata is captured
span.set_attribute("mcp.resource.uri", uri)
span.set_attribute("mcp.resource.mime_type", mime_type)
# Content deliberately omitted for security
```

**Impact**: Resource content must be re-fetched for viewing; not available in historical traces.

### 6. Multi-Agent Correlation (Future)

**MCP Spec**: Supports arbitrary agent-to-agent communication
**Inspector**: Currently correlates only direct client-server pairs

**Impact**: Complex multi-hop agent chains may not show full correlation until M3.

### 7. Error Serialization (Partial)

**MCP Spec**: Rich error objects with stack traces
**Inspector**: Captures only error code and message

```python
# Stack traces not captured to avoid leaking sensitive paths
span.set_attribute("mcp.error.code", error.code)
span.set_attribute("mcp.error.message", str(error))
```

**Impact**: Detailed error diagnostics require checking application logs.

### 8. Bearer Token Handling (Security Critical)

**MCP Spec §9**: Bearer tokens for authentication
**Inspector 1-bootstrap to 5-interact**: No token validation (localhost only)
**Inspector 6-production**: Full bearer token passthrough

**⚠️ WARNING**: Until 6-production, Inspector should NOT be exposed externally as it doesn't validate MCP bearer tokens, creating a security risk.