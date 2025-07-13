# Inspector Examples

This directory contains examples demonstrating the mcp-agent-inspector in action.

## Prerequisites

1. Install mcp-agent with inspector support:
   ```bash
   uv pip install -e ".[inspector]"
   ```

2. Set up your API keys in environment variables or `mcp_agent.secrets.yaml`:
   ```bash
   export OPENAI_API_KEY="your-key-here"
   export ANTHROPIC_API_KEY="your-key-here"
   ```

## Examples

### 1. Basic Agent with Inspector (`mcp_basic_agent/`)
Shows how to integrate Inspector with a basic MCP agent to monitor:
- Tool calls and responses
- LLM interactions with multiple providers
- Model selection based on preferences
- Real-time tracing and events

To run:
```bash
cd mcp_basic_agent
python mcp_basic_agent_with_inspector.py
```

Then open http://localhost:7800/_inspector/ui in your browser.

### 2. Session and Event Streaming Demo (`session_events_demo.py`)
Demonstrates the Inspector's session listing and Server-Sent Events (SSE) capabilities:
- Lists historical sessions from trace files
- Streams real-time events
- Shows different session statuses (completed, failed, paused)

To run:
```bash
python session_events_demo.py
```

## Key Features Demonstrated

1. **Zero Configuration**: Inspector works with just one line: `mount(app)`
2. **Automatic Tracing**: All agent operations are automatically traced
3. **Real-time Events**: Live updates via Server-Sent Events
4. **Session Management**: View and navigate historical sessions
5. **Multi-Provider Support**: Works with OpenAI, Anthropic, and other LLM providers

## Configuration

Inspector configuration is managed through `mcp_agent.config.yaml`. The basic agent example includes a ready-to-use configuration with Inspector enabled.

Key settings:
- `inspector.enabled`: Must be `true` to enable Inspector
- `inspector.port`: Port for the Inspector UI (default: 7800)
- `inspector.storage.traces_dir`: Where trace files are stored (default: ~/.mcp_traces)

### Full Configuration Example

```yaml
inspector:
  enabled: true
  port: 7800
  host: "127.0.0.1"
  
  storage:
    traces_dir: "~/.mcp_traces"
    max_trace_size: 104857600  # 100MB
    retention_days: 7
  
  security:
    auth_enabled: false  # No auth for local development
    cors_origins: []
  
  performance:
    sample_rate: 1.0     # Capture all spans
    max_sse_clients: 10
    sse_buffer_size: 1000
  
  debug:
    debug: false
    verbose_spans: false
```

## Environment Variables

You can override configuration with environment variables:
- `INSPECTOR_ENABLED=true`: Enable Inspector even if config says false
- `INSPECTOR_PORT=8000`: Use a different port
- `INSPECTOR_STORAGE__TRACES_DIR=/tmp/traces`: Change trace directory
- `INSPECTOR_DEBUG__DEBUG=true`: Enable debug logging

## What You'll See in the Inspector

- **Session List**: All active and historical workflow sessions
- **Trace Tree**: Hierarchical view of spans showing the execution flow
- **Span Attributes**: Detailed information about each operation
- **State/Result**: JSON data showing workflow outputs and decisions
- **Context**: Full LLM prompts and responses
- **Real-time Updates**: Live event stream showing workflow progress

## Note on Tracing

The current examples create mock trace files for demonstration. Full tracing integration requires the `inspector-span-exporter` task to be completed. Once that's done, the basic agent example will produce real traces automatically.

## Configuration Precedence

The Inspector configuration follows this precedence (highest to lowest):
1. Runtime parameters passed to `mount()`
2. Environment variables
3. Configuration file (`mcp_agent.config.yaml`)
4. Default values