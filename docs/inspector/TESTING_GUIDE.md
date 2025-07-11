# Inspector Testing Guide

**Port Isolation Note**: All Playwright fixtures now set `process.env.INSPECTOR_PORT` to a random free port before launching the demo agent to avoid collisions during parallel test runs.

## 1. Folder Layout

```
tests/
├── unit/          # pure-python, no IO
├── integration/   # file IO, network to localhost
├── contracts/     # OpenAPI + JSON-Schema
└── e2e/           # Playwright (auto-spawns demo agent)
```

## 2. Fixtures

### Python Fixtures (pytest)

```python
@pytest.fixture
async def demo_agent():
    """Launches examples/workflows/orchestrator_worker.py"""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "examples/workflows/orchestrator_worker.py",
        env={**os.environ, "INSPECTOR_PORT": "7801"}
    )
    await asyncio.sleep(2)  # Wait for startup
    yield "http://localhost:7801"
    proc.terminate()
    await proc.wait()

@pytest.fixture
def temp_trace_dir(tmp_path):
    """Overrides ~/.mcp_traces"""
    os.environ["MCP_TRACES_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["MCP_TRACES_DIR"]

@pytest.fixture
async def sse_client():
    """Async generator that yields events"""
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:7800/_inspector/events") as resp:
            async for line in resp.content:
                if line.startswith(b"data: "):
                    yield json.loads(line[6:])

@pytest.fixture(scope="session")
def free_port():
    """Get a free port for test isolation."""
    import socket, contextlib
    with contextlib.closing(socket.socket()) as s:
        s.bind(("", 0))
        yield s.getsockname()[1]
```

**Note**: Every Playwright/pytest-started agent should set `INSPECTOR_PORT=str(free_port)` to avoid port collisions during parallel test runs.

### Frontend Fixtures (vitest)

**Note**: Frontend tests should verify compliance with patterns defined in [@docs/inspector/ux-ui-playbook.md](ux-ui-playbook.md).

```typescript
import { render } from '@testing-library/react'
import { vi } from 'vitest'

export const mockSSE = () => {
  const events = new EventTarget()
  global.EventSource = vi.fn(() => ({
    addEventListener: events.addEventListener.bind(events),
    close: vi.fn(),
  }))
  return events
}
```

## 3. Golden Files

`tests/golden/` contains reference data:

```
tests/golden/
├── trace-mini.jsonl.gz       # 15 spans: tool, resource, prompt calls
├── trace-large.jsonl.gz      # 50k spans for perf testing
└── envelopes/
    ├── tools-call.json       # Valid MCP request/response
    ├── resources-fetch.json  # Resource fetch envelope
    └── prompts-apply.json    # Prompt application
```

## 4. Writing a New Test

### Example: Testing ProgressUpdate Events

#### Unit Test (Python)

```python
# tests/unit/test_progress_update.py
import pytest
from mcp_agent.inspector.events import ProgressUpdate
from mcp_agent.inspector.listeners import throttle_events

async def test_progress_update_throttling():
    """Progress events throttled to 2Hz max"""
    events = []
    
    # Simulate rapid progress updates
    for i in range(10):
        event = ProgressUpdate(
            session_id="test-123",
            progress_token="op-1",
            percent=i * 10,
            message=f"Step {i}"
        )
        throttled = await throttle_events(event, max_hz=2)
        if throttled:
            events.append(throttled)
    
    # Should have ≤5 events for 10 inputs at 2Hz
    assert len(events) <= 5
    assert events[-1].percent == 90  # Last event preserved
```

#### Integration Test

```python
# tests/integration/test_progress_integration.py
async def test_progress_events_flow(demo_agent, sse_client):
    """Progress events flow from agent to SSE"""
    # Trigger long operation
    async with aiohttp.post(f"{demo_agent}/run-with-progress") as resp:
        task_id = (await resp.json())["task_id"]
    
    # Collect progress events
    progress_events = []
    async for event in sse_client:
        if event["type"] == "ProgressUpdate":
            progress_events.append(event)
        if event["type"] == "SessionFinished":
            break
    
    assert len(progress_events) >= 2
    assert progress_events[-1]["percent"] == 100
```

#### E2E Test (Playwright)

```typescript
// tests/e2e/m2/progress.spec.ts
import { test, expect } from '@playwright/test'

test('progress bar updates during long operation', async ({ page }) => {
  // Start demo agent with progress simulation
  await page.goto('http://localhost:7800/_inspector/ui')
  
  // Trigger long operation
  await page.click('[data-testid="run-demo-progress"]')
  
  // Wait for progress bar
  const progressBar = page.locator('[role="progressbar"]')
  await expect(progressBar).toBeVisible()
  
  // Verify updates
  await expect(progressBar).toHaveAttribute('aria-valuenow', '50', {
    timeout: 5000
  })
  
  // Test cancellation
  await page.click('[data-testid="cancel-workflow"]')
  await expect(progressBar).not.toBeVisible()
})
```

#### Contract Test

```python
# tests/contracts/test_progress_schema.py
import schemathesis

schema = schemathesis.from_dict({
    "openapi": "3.0.0",
    "paths": {
        "/_inspector/events": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "text/event-stream": {
                                "schema": {"$ref": "#/components/schemas/ProgressUpdate"}
                            }
                        }
                    }
                }
            }
        }
    },
    "components": {
        "schemas": {
            "ProgressUpdate": {
                "type": "object",
                "required": ["type", "session_id", "progress_token", "percent"],
                "properties": {
                    "type": {"const": "ProgressUpdate"},
                    "session_id": {"type": "string"},
                    "progress_token": {"type": "string"},
                    "percent": {"type": "number", "minimum": 0, "maximum": 100},
                    "message": {"type": "string"}
                }
            }
        }
    }
})

@schema.parametrize()
def test_progress_event_schema(case):
    case.call_and_validate()
```

#### Contract Test for Transport Enums

```python
# tests/contracts/test_transport_schema.py
import schemathesis

# Schema for transport attributes
transport_schema = schemathesis.from_dict({
    "openapi": "3.0.0",
    "paths": {
        "/_inspector/trace/{session_id}": {
            "get": {
                "parameters": [
                    {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/x-ndjson": {
                                "schema": {"$ref": "#/components/schemas/Span"}
                            }
                        }
                    }
                }
            }
        }
    },
    "components": {
        "schemas": {
            "Span": {
                "type": "object",
                "properties": {
                    "attributes": {
                        "type": "object",
                        "properties": {
                            "mcp.rpc.transport": {
                                "type": "string",
                                "enum": ["stdio", "sse", "http", "websocket"],
                                "description": "Transport protocol used"
                            },
                            "mcp.transport.status": {
                                "type": "string",
                                "enum": ["connected", "disconnected", "reconnecting"],
                                "description": "Transport connection status"
                            }
                        }
                    }
                }
            }
        }
    }
})

@transport_schema.parametrize()
def test_transport_enum_values(case):
    """Validate transport enum values match telemetry spec"""
    case.call_and_validate()
```

## 5. CI Matrix

### Primary CI (GitHub Actions)

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest]
    python: ["3.9", "3.10", "3.11"]
    node: ["18", "20"]
```

- Linux & macOS on every PR
- Windows nightly builds
- All tests must pass in <90s

### Test Commands

```bash
# Backend
pytest tests/unit tests/integration -v
pytest tests/contracts --hypothesis-show-statistics

# Frontend
pnpm test
pnpm test:coverage

# E2E
pnpm playwright test
pnpm playwright test --debug  # Interactive mode
```

## 6. Performance Tests

```python
# tests/perf/test_span_parse_time.py
import time
import gzip
import json

def test_50k_span_load_time():
    """Ensure 50k spans load in <1.5s"""
    start = time.time()
    
    with gzip.open("tests/golden/trace-large.jsonl.gz", "rt") as f:
        spans = [json.loads(line) for line in f]
    
    elapsed = time.time() - start
    assert len(spans) == 50000
    assert elapsed < 1.5, f"Took {elapsed:.2f}s, expected <1.5s"
```

## 7. Debugging Test Failures

### Playwright Debug Mode

```bash
# Run with headed browser
pnpm playwright test --headed

# Debug specific test
pnpm playwright test progress.spec.ts --debug

# Save trace on failure
pnpm playwright test --trace on
```

### pytest Debug Options

```bash
# Drop into debugger on failure
pytest --pdb

# Show print statements
pytest -s

# Run specific test
pytest tests/unit/test_progress_update.py::test_progress_update_throttling -v
```

## 8. Test Data Generation

```python
# scripts/generate_test_data.py
import gzip
import json
import uuid
from datetime import datetime

def generate_trace(num_spans=15):
    """Generate test trace with tool, resource, prompt spans"""
    spans = []
    
    # Add tool call
    spans.append({
        "name": "tool.call",
        "trace_id": str(uuid.uuid4()),
        "span_id": str(uuid.uuid4()),
        "attributes": {
            "mcp.tool.name": "search_code",
            "mcp.rpc.method": "tools/call"
        }
    })
    
    # Add resource fetch
    spans.append({
        "name": "resource.fetch",
        "attributes": {
            "mcp.resource.uri": "file:///project/README.md",
            "mcp.resource.mime_type": "text/markdown"
        }
    })
    
    return spans
```

## 9. Common Test Patterns

### Mocking Time

```python
from freezegun import freeze_time

@freeze_time("2025-01-01T12:00:00Z")
async def test_session_timestamp():
    session = await create_session()
    assert session.started_at == "2025-01-01T12:00:00Z"
```

### Testing SSE Streams

```python
async def test_sse_heartbeat():
    events = []
    async with timeout(10):
        async for event in sse_client():
            events.append(event)
            if len(events) >= 3:
                break
    
    heartbeats = [e for e in events if e["type"] == "Heartbeat"]
    assert len(heartbeats) >= 1
```

### Schema Validation

```python
from jsonschema import validate

def test_session_response_schema():
    response = client.get("/_inspector/sessions")
    schema = load_schema("SessionMeta.json")
    
    for session in response.json():
        validate(instance=session, schema=schema)
```

## 10. Spec Regression

```bash
# Run contract tests against the OpenAPI spec
schemathesis run docs/inspector/openapi.yaml --checks all
# Fails if any endpoint or event deviates from spec-alignment.md mappings

# Test specific endpoints
schemathesis run docs/inspector/openapi.yaml --endpoint=/health
schemathesis run docs/inspector/openapi.yaml --endpoint=/sessions
```