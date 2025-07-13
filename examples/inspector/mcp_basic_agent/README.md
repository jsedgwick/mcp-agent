# Inspector Demo: Basic Agent Workflow

This example demonstrates how to enable and use the `mcp-agent-inspector` to observe a standard agent workflow. It adapts the `basic_agent` example to showcase the Inspector's configuration and core observability features.

## Objective

- To show how to enable the Inspector via a simple configuration change.
- To illustrate how the Inspector captures and displays the full lifecycle of an agent's execution, including LLM and tool calls.
- To serve as a primary "dogfooding" example for developing and testing Inspector features.

## Setup

1. **Install dependencies** from the project root:
   ```bash
   # Install dependencies, including inspector extras
   uv pip install -e ".[dev,inspector]"
   ```

2. **Create a secrets file** in this directory (`mcp_agent.secrets.yaml`) with your API keys:
   ```yaml
   # mcp_agent.secrets.yaml
   openai:
     api_key: "sk-..."
   anthropic:
     api_key: "sk-ant-..."
   ```

   Or use environment variables:
   ```bash
   export OPENAI_API_KEY="sk-..."
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

## How to Run

Simply run the main script from this directory:

```bash
cd examples/inspector/mcp_basic_agent
python mcp_basic_agent_with_inspector.py
```

The script will:
1. Initialize an MCPApp which automatically loads the local `mcp_agent.config.yaml`.
2. Since `inspector.enabled: true` is set in the config, the Inspector gateway will start.
3. Run the "finder" agent workflow with multiple tasks.
4. Wait for 30 seconds after completion, giving you time to explore the UI.

## What to Look For in the Inspector

After running the script, open your browser to **http://localhost:7800/_inspector/ui**. You will see a new session appear. Click on it to open the debugger view.

### Key Observations:

1. **Session Appears**: A new session named `inspector_basic_agent_demo` will be listed. Its status will be "running" and then "completed".

2. **Span Hierarchy**: In the trace view, you will see a nested structure of spans that mirrors the code's execution flow:
   - `workflow.run` (root span)
   - `agent.call`
     - `llm.generate`
     - `tool.call` (e.g., `filesystem_read_file`)
   - `llm.generate` (the second call for the tweet summary)

3. **Core Attributes**: Click on any span to see its attributes in the inspector panel.
   - **workflow.run span**: Look for the `mcp.workflow.type` attribute.
   - **agent.call span**: You will find the `mcp.agent.name` attribute with the value "finder".
   - **tool.call span**: Look for `mcp.tool.name` (e.g., `filesystem_read_file`) and `mcp.tool.input_json`.
   - **llm.generate span**: Check `mcp.llm.provider` and `mcp.llm.model`.

4. **State and Context**:
   - Click on an `llm.generate` span and select the "Context" tab. You'll see the exact prompt messages sent to and received from the LLM.
   - Click on a `tool.call` span and select the "State / Result" tab. You'll see the `mcp.tool.output_json` attribute, showing the data returned by the tool.

## Configuration Highlights

The `mcp_agent.config.yaml` in this directory shows the key configuration for enabling Inspector:

```yaml
# Enable Inspector
inspector:
  enabled: true
  port: 7800

# Enable OpenTelemetry file exporter (required for Inspector)
otel:
  enabled: true
  exporters: ["file"]
  service_name: "inspector_basic_agent_demo"
```

## Note on Tracing

Currently, this example uses the existing FileSpanExporter which writes uncompressed JSONL files. The full Inspector integration with gzip compression will be available once the `inspector-span-exporter` task is completed. For now, you'll see mock data in the Inspector UI.

## Troubleshooting

- **No sessions appearing**: Check that both `inspector.enabled` and `otel.enabled` are true in the config.
- **KeyError for 'filesystem'**: Make sure the `mcp.servers` section is properly configured in the YAML.
- **API key errors**: Ensure your API keys are set either in `mcp_agent.secrets.yaml` or as environment variables.

This example provides a clear, end-to-end demonstration of how the Inspector provides deep visibility into an agent's execution with minimal setup.