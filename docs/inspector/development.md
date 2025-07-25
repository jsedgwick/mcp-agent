# Development Guide

This guide covers setting up, developing, testing, and debugging mcp-agent-inspector.

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/mcp-agent-inspector
cd mcp-agent-inspector

# Install in development mode
uv pip install -e ".[dev]"

# Install frontend dependencies
cd packages/inspector_ui
pnpm install

### Python extras

```bash
uv pip install "mcp-agent[inspector]"  # pulls fastapi, uvicorn[standard]
```
```

### Running with Inspector

```python
# In any mcp-agent script
from mcp_agent.inspector import mount
from mcp_agent import MCPApp

app = MCPApp()
mount(app)  # One line to enable inspector!

# Access at http://localhost:7800/_inspector/ui
```

### Configuration

Inspector is configured via the `inspector:` section in your `mcp_agent.config.yaml` file. Create this file in your project root if it doesn't exist.

```yaml
# mcp_agent.config.yaml

inspector:
  # Master switch for the inspector. Must be true to enable.
  # Defaults to false for backward compatibility.
  enabled: true
  
  # Port for the Inspector UI and API
  port: 7800
  
  # Directory to store trace files
  storage:
    traces_dir: "~/.mcp_traces"
  
  # Security settings (important for future milestones)
  security:
    auth_enabled: false
    cors_origins:
      - "http://localhost:5173"  # For local Vite dev server
  
  # Enable verbose debugging for inspector components
  debug:
    debug: true
```

Settings are loaded with this precedence: Runtime arguments > Environment variables > YAML file > Defaults.

## Development Workflow

### Pre-commit Checklist
Before starting any work, ensure your environment is properly configured:

```bash
# Install pre-commit hooks
pre-commit install

# Run all checks manually
pre-commit run --all-files
```

### Backend Development

1. **Write tests first** - TDD is not optional
   ```bash
   # Write test first in tests/unit/test_new_feature.py
   # Then implement in src/
   ```

2. **Add type hints** - Every function, every parameter, every return
   ```python
   # Bad: def process(data): ...
   # Good: def process(data: Dict[str, Any]) -> ProcessResult: ...
   ```

3. **Format and lint code** - Before every commit
   ```bash
   make format  # Auto-format with ruff
   make lint    # Fix linting issues
   # Or both: uv run scripts/lint.py --fix
   ```

4. **Type check** - mypy is aspirational but recommended
   ```bash
   # Optional local check (not enforced in CI):
   # mypy --strict mcp_agent/inspector/
   ```

5. **Run your test script** - Any mcp-agent example works
6. **Open Inspector** - http://localhost:7800/_inspector/ui
7. **Verify changes** - Check spans, events, and state capture

### Frontend Development

```bash
# Terminal 1: Run your mcp-agent script with inspector
uv run python examples/workflows/orchestrator_worker.py

# Terminal 2: Start frontend dev server
cd packages/inspector_ui
pnpm run dev

# Browser: http://localhost:5173 (Vite dev server with HMR)
```

### Testing

```bash
# Run all tests
pytest tests/inspector/

# Run with coverage
pytest tests/inspector/ --cov=mcp_agent.inspector --cov-report=html

# Type checking
mypy mcp_agent/inspector

# Linting and formatting
make format  # Run ruff format
make lint    # Run ruff check --fix
# Or use the combined script:
uv run scripts/lint.py --fix

# Frontend tests
cd packages/inspector_ui
pnpm test
pnpm run type-check
```

### Testing mcp-agent Core Changes

**IMPORTANT**: If your changes touch any mcp-agent core functionality (not just inspector-specific code), you MUST run the full mcp-agent test suite before pushing:

```bash
# Sync all dependencies first
uv sync --all-extras --all-packages --group dev

# Run the full test suite (839 tests as of 2025-07)
make tests
# or directly:
uv run pytest

# For faster iteration, test specific modules first:
uv run pytest tests/agents/           # If you changed agent.py
uv run pytest tests/executor/         # If you changed workflow execution
uv run pytest tests/workflows/llm/    # If you changed LLM providers
uv run pytest tests/inspector/        # For inspector-specific changes
```

**Common test failures and solutions**:

1. **Import errors**: Usually means missing dependencies
   ```bash
   uv sync --all-extras --all-packages --group dev
   ```

2. **Syntax errors**: Often from incomplete try/except blocks
   - Check indentation is consistent
   - Ensure all `try:` blocks have `except:` or `finally:`

3. **Python version mismatch**: Use `uv run` prefix
   ```bash
   uv run pytest  # Uses the correct Python version
   ```

4. **Test isolation issues**: Clear any cached state
   ```bash
   rm -rf .pytest_cache __pycache__
   ```

## Debugging Inspector

### Debug Mode

Enable comprehensive debugging output:

```bash
INSPECTOR_DEBUG=1 uv run python my_script.py
```

This enables:
- Verbose logging for all inspector components
- Schema validation on every event
- Performance timers for operations
- Unminified frontend bundle
- Detailed error stack traces

### Common Debugging Tasks

#### 1. Verify Span Enrichment

```python
import json
import gzip

# Check if spans are being enriched
with gzip.open("/Users/you/.mcp_traces/session-id.jsonl.gz", 'rt') as f:
    for line in f:
        span = json.loads(line)
        attrs = span.get("attributes", {})
        print(f"Span: {span['name']}")
        print(f"  Agent: {attrs.get('mcp.agent.class')}")
        print(f"  State: {attrs.get('mcp.state.plan_json', 'None')[:100]}...")
```

#### 2. Monitor Real-time Events

```python
# Add debug listener to event bus
from mcp_agent.logging.events import AsyncEventBus

async def debug_listener(event):
    print(f"[EVENT] {event.__class__.__name__}: {event.dict()}")

# In your async code
bus = AsyncEventBus.get()
bus.add_listener(debug_listener)
```

#### 3. Test Endpoints Manually

```bash
# Health check
curl http://localhost:7800/_inspector/health

# List sessions
curl http://localhost:7800/_inspector/sessions | jq

# Stream events (Server-Sent Events)
curl -N http://localhost:7800/_inspector/events

# Get specific trace
curl http://localhost:7800/_inspector/trace/session-123 --output trace.jsonl.gz
```

#### 4. API Documentation

The complete HTTP API is documented in OpenAPI format at [docs/inspector/openapi.yaml](../../openapi.yaml). This spec:
- Defines all endpoints, request/response schemas
- Used by Schemathesis for contract testing
- Source of truth for frontend TypeScript types (via `pnpm run gen:schemas`)
- Validates session IDs, signal types, and error responses

For version management guidelines, see [openapi-versioning.md](openapi-versioning.md).

#### 5. Inspect File Storage

```bash
# Check trace files
ls -la ~/.mcp_traces/

# Decompress and pretty-print trace
gunzip -c ~/.mcp_traces/session-id.jsonl.gz | jq -s '.[0:5]'

# Check file sizes
du -h ~/.mcp_traces/*

# Monitor writes in real-time
tail -f ~/.mcp_traces/*.jsonl.gz | gunzip
```

## Instrumentation Patterns

**⚠️ CRITICAL: Dual System Reality**

The codebase currently contains TWO parallel instrumentation systems:
1. **Legacy**: Direct OpenTelemetry calls throughout core (`@telemetry.traced`, manual spans)
2. **New**: Hook-based system with Inspector as subscriber

This is technical debt being actively migrated. See [Architecture §6.6](architecture.md#66-architectural-migration-from-direct-otel-to-hook-based) for full context.

### Required Pattern for NEW Development

All new features MUST use ONLY the hook-based pattern:

#### Step 1: Define the Hook
Add to [instrumentation-hooks.md](instrumentation-hooks.md) if needed:
```markdown
| before_my_operation | Before operation starts | context, params | v1.3 |
| after_my_operation | After success | context, params, result | v1.3 |
| error_my_operation | On failure | context, params, exc | v1.3 |
```

#### Step 2: Emit in Core Code
```python
# In core mcp-agent code - NO OpenTelemetry imports!
from mcp_agent.core import instrument

async def my_operation(context, params):
    # Fast-path optimization for hot paths
    if instrument._hooks.get("before_my_operation"):
        await instrument._emit("before_my_operation", 
                             context=context, 
                             params=params)
    
    try:
        result = await self._do_work(params)
        
        if instrument._hooks.get("after_my_operation"):
            await instrument._emit("after_my_operation",
                                 context=context,
                                 params=params,
                                 result=result)
        return result
        
    except Exception as e:
        if instrument._hooks.get("error_my_operation"):
            await instrument._emit("error_my_operation",
                                 context=context,
                                 params=params,
                                 exc=e)
        raise
```

#### Step 3: Subscribe in Inspector
```python
# In mcp_agent/inspector/subscribers.py
from opentelemetry import trace
import json

async def _before_my_operation(context, params, **_kw):
    """Enrich span with operation details"""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute("mcp.operation.params_json", 
                          json.dumps(params))
        # Use inspector.context.get() for session_id
        span.set_attribute("session.id", 
                          inspector.context.get())

# In register_all_subscribers()
instrument.register("before_my_operation", _before_my_operation)
```

### Common Patterns

#### State Capture
Use the `@dump_state_to_span()` decorator for automatic result capture:
```python
from mcp_agent.inspector.decorators import dump_state_to_span

class MyWorkflow(Workflow):
    @dump_state_to_span()  # Captures as mcp.state.run_json
    async def run(self, context: Context) -> WorkflowResult:
        return WorkflowResult(...)
```

#### JSON Attribute Convention
- Always suffix JSON attributes with `_json`
- Apply 30KB size limit with truncation flag
- Use consistent paths: `mcp.{category}.{name}_json`

```python
if len(json_str) > 30720:  # 30KB
    span.set_attribute(f"{key}_truncated", True)
    json_str = json_str[:30720]
span.set_attribute(key, json_str)
```

#### Session ID Propagation
Never generate new session IDs - always use context:
```python
from mcp_agent.inspector import context as insp_ctx

# At workflow root (once)
session_id = str(uuid4())
insp_ctx.set(session_id)

# Anywhere else
current_session = insp_ctx.get()
```

### What NOT to Do

❌ **Direct OTel in New Code**
```python
# WRONG - Never do this in new features
from opentelemetry import trace

@telemetry.traced("my_new_feature")  # NO!
async def my_new_feature():
    span = trace.get_current_span()  # NO!
    span.set_attribute("foo", "bar")  # NO!
```

❌ **Mutating Hook Arguments**
```python
# WRONG - Never mutate objects
async def _before_tool_call(tool_name, args, **_kw):
    args["injected"] = "value"  # NO! Read-only!
```

❌ **Heavy Processing in Subscribers**
```python
# WRONG - Keep under 200µs
async def _after_llm_generate(response, **_kw):
    embeddings = await compute_embeddings(response)  # NO!
    # Instead: enqueue to background task
```

### Migration Path for Existing Code

When refactoring legacy code:

1. **Add hooks FIRST** (alongside existing OTel)
2. **Verify parity** (same spans/attributes generated)
3. **Remove OTel** (only after verification)
4. **Update tests** (use hook capture utilities)

Example migration:
```python
# PHASE 1: Add hooks (OTel still present)
@telemetry.traced("agent.call")
async def call(self):
    # NEW: Add hook
    await instrument._emit("before_agent_call", agent=self)
    
    # EXISTING: OTel still here temporarily
    span = trace.get_current_span()
    # ... existing span manipulation ...

# PHASE 2: Verify both produce same telemetry

# PHASE 3: Remove OTel (separate PR)
async def call(self):
    # ONLY hooks remain
    await instrument._emit("before_agent_call", agent=self)
    # ... business logic ...
```

### Testing Patterns

Use the hook capture utility for tests:
```python
from mcp_agent.core.instrument import capture_hook

async def test_my_operation_emits_hooks():
    async with capture_hook("before_my_operation") as calls:
        await my_operation(context, params)
    
    assert len(calls) == 1
    assert calls[0][1]["params"] == params
```

### Performance Considerations

- Hook emission overhead: <2µs per call
- Use fast-path guards for hot paths
- Batch related hooks when possible
- Profile before optimizing

### Legacy Support

For older mcp-agent versions without hooks:
```bash
INSPECTOR_ENABLE_PATCH=1 python my_script.py
```

This enables monkey-patching fallback (discouraged).

### Lazy Imports Pattern

Avoid heavy dependencies in module scope:

```python
def mount(app):
    """Mount inspector with lazy imports"""
    try:
        # Import only when mounting
        from fastapi import FastAPI
        from .gateway import create_gateway
    except ImportError:
        raise ImportError("uv pip install mcp-agent[inspector]")
    
    gateway = create_gateway()
    app.mount("/_inspector", gateway)
```

## Troubleshooting

### Inspector Not Loading

1. **Check mount was called**:
   ```python
   print(app.routes)  # Should show /_inspector routes
   ```

2. **Verify no port conflicts**:
   ```bash
   lsof -i :7800
   ```

3. **Check trace directory**:
   ```bash
   ls -la ~/.mcp_traces/
   # Should be writable by current user
   ```

### Missing Spans

1. **Verify OpenTelemetry setup**:
   ```python
   from opentelemetry import trace
   print(trace.get_tracer_provider())
   ```

2. **Check exporter**:
   ```bash
   INSPECTOR_DEBUG=1 uv run python script.py 2>&1 | grep FileSpanExporter
   ```

3. **Ensure spans are ended**:
   ```python
   # Spans must be ended to be exported
   with tracer.start_as_current_span("test"):
       pass  # Automatically ended
   ```

### Frontend Not Updating

1. **Check SSE connection**:
   - Browser DevTools → Network → events stream
   - Should show persistent connection

2. **Verify events are published**:
   ```python
   # In your code
   print(f"Publishing event: {event}")
   ```

3. **Check browser console** for errors

### Known Infrastructure Issues

#### AsyncEventBus Initialization Error

**Symptom**: Test logs show repeated errors:
```
AttributeError: 'AsyncEventBus' object has no attribute '_queue'
```

**Root Cause**: The AsyncEventBus in `mcp_agent.logging.transport` expects initialization that may not happen in test environments.

**Impact**: 
- Tests may show these errors in logs but still pass
- Real-time event streaming in 2-observe milestone may be affected
- Future Temporal executor integration needs to ensure proper event bus initialization

**Workarounds**:
1. For tests, these errors can be safely ignored if tests pass
2. For production, ensure proper context initialization:
   ```python
   from mcp_agent.core.context import initialize_context
   context = await initialize_context()
   ```

**Permanent Fix**: Will be addressed in `observe/fix/async-event-bus-init` task in 2-observe milestone.

#### Context Import Confusion

**Symptom**: Import errors when trying to use Context class:
```
ModuleNotFoundError: No module named 'mcp_agent.workflows.contexts'
```

**Correct Import**:
```python
from mcp_agent.core.context import Context  # Correct
# NOT from mcp_agent.workflows.contexts import Context  # Wrong
```

## Code Quality Standards

### Type Annotations (MANDATORY)
```python
# BAD - Missing type hints
def get_session(id):
    return db.get(id)

# GOOD - Complete type annotations
from typing import Optional
from mcp_agent.types import Session

def get_session(session_id: str) -> Optional[Session]:
    """Retrieve session by ID.
    
    Args:
        session_id: Unique session identifier
        
    Returns:
        Session object if found, None otherwise
        
    Examples:
        >>> session = get_session("test-123")
        >>> assert session is None or isinstance(session, Session)
    """
    return db.get(session_id)
```

### Unit Testing Requirements
```python
# Every function MUST have a corresponding test
# tests/unit/test_session_manager.py
import pytest
from mcp_agent.inspector.sessions import get_session

@pytest.mark.asyncio
async def test_get_session_returns_none_for_missing():
    """get_session should return None for non-existent IDs"""
    result = await get_session("non-existent")
    assert result is None

async def test_get_session_returns_session_object():
    """get_session should return Session for valid IDs"""
    # Arrange
    test_id = "test-123"
    await create_test_session(test_id)
    
    # Act
    result = await get_session(test_id)
    
    # Assert
    assert isinstance(result, Session)
    assert result.session_id == test_id
```

### Code Formatting Standards
```bash
# Before EVERY commit - Backend:
make format      # Auto-format with ruff
make lint        # Fix linting issues with ruff check --fix
# Or run both with: uv run scripts/lint.py --fix

# Optional type checking (not enforced in CI):
# mypy mcp_agent/inspector/ --strict

# Frontend:
cd packages/inspector_ui
pnpm run format  # Prettier
pnpm run lint:fix  # ESLint
pnpm run type-check  # TypeScript
```

### Documentation Requirements
Every public function/class MUST have:
1. **Type hints** for all parameters and return values
2. **Docstring** with:
   - One-line summary
   - Args section (if applicable)
   - Returns section (if applicable)
   - Examples section showing usage
   - Raises section (if exceptions possible)

### Performance Standards
- Span processing overhead: <1ms per span
- Memory usage: <150MB for 100k spans
- UI responsiveness: 60fps (16ms frame budget)
- Test execution: <1.5s per test file

## Best Practices

1. **Keep PRs Small**: <500 lines changed per PR
2. **Write Tests First**: TDD is mandatory, not optional
3. **Type Everything**: No `Any` unless absolutely necessary
4. **Document Patterns**: Update this guide with new patterns
5. **Performance First**: Profile before optimizing
6. **Zero Dependencies**: No external services or heavy libraries
7. **Error Handling**: Explicit is better than implicit
8. **Async by Default**: Use async/await for all I/O operations

## Testing Stack – One Ring To Rule Them All

| Scope | Framework | Command | Notes |
|-------|-----------|---------|-------|
| Python unit / integration | pytest (+ pytest-asyncio) | `pytest -q` | Coverage via `--cov` |
| Front-end component & plugin | vitest (jest-compatible) | `pnpm test` | Runs in JSDOM |
| Full-stack (browser) | Playwright | `pnpm playwright test` | Spins demo agent in-process |
| Contract / schema | schemathesis (OpenAPI) | `schemathesis run docs/inspector/openapi.yaml` | Validates against OpenAPI spec |

All milestone tasks MUST supply:
- ✔ pytest (backend)
- ✔ vitest or jest (if React work)
- ✔ Playwright (if UI-visible)
- ...plus one Schemathesis check when an HTTP surface is added/changed.

## Implementation Details

### Gateway Implementation (bootstrap/feat/gateway-health-endpoint)

```python
# src/mcp_agent/inspector/gateway.py
from __future__ import annotations
import os, threading, atexit
from fastapi import FastAPI, APIRouter
from starlette.responses import JSONResponse
from typing import Optional

_router = APIRouter(prefix="/_inspector")

@_router.get("/health", include_in_schema=False)
async def health():
    from .version import __version__
    return JSONResponse({"name": "mcp-agent-inspector", "version": __version__})

def _run_local_uvicorn(app: FastAPI) -> None:
    import uvicorn
    port = int(os.getenv("INSPECTOR_PORT", "7800"))
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port,
                         lifespan="off", log_level="warning")
    server = uvicorn.Server(cfg)
    
    # Clean shutdown
    def shutdown():
        server.should_exit = True
    atexit.register(shutdown)
    
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

def mount(app: Optional[FastAPI] = None, *, expose: bool = False) -> None:
    if app is not None:
        app.mount("/_inspector", _router)
        return
    _run_local_uvicorn(FastAPI(routes=_router.routes))
```

### Instrumentation Patterns

#### Hook-based Instrumentation

```python
# src/mcp_agent/inspector/subscribers.py
from mcp_agent.core import instrument
from . import span_enrichment

def register_all_subscribers():
    """Register all Inspector hook subscribers"""
    instrument.register("before_llm_generate", span_enrichment.before_llm_generate)
    instrument.register("after_llm_generate", span_enrichment.after_llm_generate)  
    instrument.register("before_tool_call", span_enrichment.before_tool_call)
    instrument.register("after_tool_call", span_enrichment.after_tool_call)
    instrument.register("before_workflow_run", span_enrichment.before_workflow_run)
    instrument.register("after_workflow_run", span_enrichment.after_workflow_run)
```

#### Accessing Core Services

```python
from fastapi import Request

@_router.get("/sessions")
async def list_sessions(request: Request):
    # Access app.state populated by mount()
    bus = request.app.state.event_bus          # AsyncEventBus
    registry = request.app.state.workflow_registry  # InMemoryWorkflowRegistry
    
    # Handle Temporal gracefully
    sessions = registry.list_active()
    if request.app.state.config.execution_engine == "temporal":
        try:
            temporal_sessions = await _get_temporal_sessions(request)
            sessions.extend(temporal_sessions)
        except Exception as e:
            # Include error but don't fail
            return {"sessions": sessions, "temporal_error": str(e)}
    
    return {"sessions": sessions}
```

### Event Handling

#### WaitingOnSignal Implementation

```python
# src/mcp_agent/inspector/events.py
from pydantic import BaseModel
from typing import Literal

class WaitingOnSignal(BaseModel):
    type: Literal["WaitingOnSignal"] = "WaitingOnSignal"
    session_id: str
    signal_name: str
    prompt: str | None = None
    schema: dict | None = None
```

#### Context & Session ID Propagation

Inspector relies on a single, durable identifier — **session_id** — to thread together every span, event, and file written during a workflow.

**Why not pass Context objects everywhere?**

Passing `Context` through every call leads to brittle APIs and breaks FastAPI middleware or async callbacks whose signatures we do not own. Instead we rely on `contextvars`, the std-lib friendly cousin of thread-locals.

**Public helper API (mcp_agent.inspector.context)**

```python
# src/mcp_agent/inspector/context.py
import contextvars, functools, asyncio

_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="unknown")

def set(session_id: str):  # called exactly once per workflow root
    _session_id.set(session_id)

def get() -> str:
    return _session_id.get()

def bind(fn):
    """Decorator that injects the current session_id into *kw
       if the wrapped function accepts it."""
    @functools.wraps(fn)
    async def _w(*a, **kw):
        if "session_id" in fn.__code__.co_varnames:
            kw.setdefault("session_id", get())
        return await fn(*a, **kw) if asyncio.iscoroutinefunction(fn) else fn(*a, **kw)
    return _w
```

**Lifecycle**
1. Workflow (or inbound request) allocates a session_id and immediately calls `context.set(session_id)`
2. Any nested code, middleware, or background task may call `context.get()`; they never need an explicit argument
3. FileSpanExporter & SSE listener use `context.get()` during export so trace files are always written to the right `{session_id}.jsonl.gz`

**FastAPI Middleware Example**
```python
from fastapi import Request
from mcp_agent.inspector import context as insp_ctx

@app.middleware("http")
async def attach_session(request: Request, call_next):
    rid = request.headers.get("X-MCP-Request-Id") or uuid4().hex
    insp_ctx.set(rid)
    return await call_next(request)
```

### Inbound MCP Middleware

```python
# src/mcp_agent/inspector/inbound.py
from starlette.middleware.base import BaseHTTPMiddleware

class InspectorInboundMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if "X-MCP-Request-Id" in request.headers:
            sid = request.headers["X-MCP-Request-Id"]
            _start_inbound_session(sid, request)
        response = await call_next(request)
        return response
```

### Workflow Lookup Pattern

```python
# In signal handler
workflow = request.app.state.workflow_registry.get(session_id)
if workflow:
    await workflow.signal(body.signal, body.payload)
else:
    raise HTTPException(404, "Workflow not found")
```

## Dogfooding Philosophy & Guide

ℹ️ The guide is authoritative for QA plans, CI fixtures and demo screenshots. Any example referenced here **must never be renamed** without a chore-ticket updating the guide and the Playwright tests.

### Core Principle

We dogfood the Inspector on mcp-agent itself from day one. Every milestone must deliver immediate value to our own development workflow.

### Milestone-by-Milestone Dogfooding Mapping

| Milestone | Dogfood Use Case | Example Script | Expected "Aha!" |
|-----------|------------------|----------------|------------------|
| 1-bootstrap | "It's alive!" | `examples/quickstart.py` | Health endpoint returns version |
| 2-observe | Debug orchestrator failures | `examples/workflows/orchestrator_worker.py` | See PlanResult JSON without grep |
| 2-observe | Understand router decisions | `examples/workflows/router.py` | View RouterDecision scores |
| 2-observe | Track human input waits | `examples/elicitation/main.py` | "PAUSED" badge appears |
| 3-understand | Analyze prompt evolution | `examples/mcp_primitives/mcp_basic_agent/` | Context viewer shows full history |
| 3-understand | Resume paused workflows | `examples/human_input/handler.py` | Answer form unblocks execution |
| 4-visualize | Visualize orchestrator DAG | `examples/workflows/orchestrator_worker.py` | Plan steps as connected graph |
| 4-visualize | Debug tool resolution | `examples/mcp_server_aggregator/` | Aggregator path visualization |

### Testing Against Real Examples

1. **Never mock what you can test real**: Use actual mcp-agent examples in tests
2. **Screenshot regression**: Each milestone includes visual regression tests
3. **Performance baselines**: Measure overhead on real workflows
4. **Error scenarios**: Test with intentionally broken examples

### Dogfood Checklist (per PR)

- [ ] Tested against at least one real example from `examples/`
- [ ] Verified no performance regression (< 1ms span overhead)
- [ ] Updated relevant example if API changed
- [ ] Added screenshot to PR if UI changed
- [ ] Ran through complete workflow (start → debug → fix)

### Common Dogfooding Scenarios

1. **"Why did my orchestrator fail?"**
   - Run `examples/workflows/orchestrator_worker.py`
   - Open Inspector at http://localhost:7800/_inspector/ui
   - Click failed session
   - View error in span attributes
   - Check PlanResult for context

2. **"Where is my workflow stuck?"**
   - Run any human_input example
   - See "PAUSED" status in session list
   - Click to see WaitingOnSignal details
   - Use form to resume (M2+)

3. **"How did the router decide?"**
   - Run `examples/workflows/router.py`
   - Find router span
   - View RouterDecision with scores
   - Understand routing logic

### Integration with Development Workflow

```bash
# Start any example with inspector
uv run python examples/workflows/orchestrator_worker.py

# In another terminal, make changes
vim src/mcp_agent/workflows/orchestrator/orchestrator.py

# Restart and see changes reflected in Inspector
# No need to grep logs or add print statements
```

### See Also

- Each milestone doc has a "Dogfooding Guide" link at the bottom
- `tests/e2e/dogfood/` contains scenario-based tests
- Screenshots in `docs/screenshots/` show expected states

## UI/UX Patterns

**Note**: For comprehensive UI/UX guidelines, design tokens, and component architecture patterns, see [@docs/inspector/ux-ui-playbook.md](ux-ui-playbook.md).

### Component Library Structure

```
packages/inspector_ui/src/
├── components/
│   ├── core/              # Reusable UI primitives
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   └── VirtualList.tsx
│   ├── session/           # Session-specific components
│   │   ├── SessionList.tsx
│   │   └── SessionCard.tsx
│   └── trace/             # Trace visualization
│       ├── SpanTree.tsx
│       └── AttributeInspector.tsx
├── hooks/                 # Custom React hooks
│   ├── useSSE.ts         # Server-sent events
│   └── useTraceLoader.ts # Web worker integration
└── styles/               # Design tokens
    └── tokens.ts
```

### Design Tokens System

```typescript
// src/styles/tokens.ts
export const tokens = {
  colors: {
    // Semantic colors
    status: {
      running: '#3b82f6',   // blue-500
      paused: '#f59e0b',    // amber-500
      completed: '#10b981', // emerald-500
      failed: '#ef4444'     // red-500
    },
    // Workflow type colors
    workflow: {
      orchestrator: '#8b5cf6', // violet-500
      router: '#ec4899',       // pink-500
      evaluator: '#06b6d4'     // cyan-500
    }
  },
  spacing: {
    xs: '0.25rem',
    sm: '0.5rem',
    md: '1rem',
    lg: '1.5rem',
    xl: '2rem'
  }
}
```

### Virtual Scrolling Pattern

```typescript
// For large trace lists (>500 items)
import { VirtualList } from '@tanstack/react-virtual'

function SpanTree({ spans }: { spans: Span[] }) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: spans.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32, // Row height
    overscan: 5 // Render 5 items outside viewport
  })

  return (
    <div ref={parentRef} className="h-full overflow-auto">
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map(virtualRow => (
          <SpanRow
            key={spans[virtualRow.index].span_id}
            span={spans[virtualRow.index]}
            style={{
              position: 'absolute',
              top: 0,
              transform: `translateY(${virtualRow.start}px)`
            }}
          />
        ))}
      </div>
    </div>
  )
}
```

### State Viewer Components

```typescript
// Specialized viewers for common state types
const stateViewers = {
  'mcp.state.plan_json': PlanViewer,
  'mcp.state.router_decision_json': RouterDecisionViewer,
  'mcp.result.evaluation_json': EvaluationResultViewer
}

// Example: PlanViewer component
function PlanViewer({ plan }: { plan: PlanResult }) {
  return (
    <div className="space-y-2">
      <h3 className="font-semibold">Execution Plan</h3>
      {plan.steps.map(step => (
        <Card key={step.step_id} status={step.status}>
          <div className="flex items-center gap-2">
            <StatusIcon status={step.status} />
            <span>{step.description}</span>
          </div>
          {step.dependencies.length > 0 && (
            <div className="text-sm text-gray-600">
              Depends on: {step.dependencies.join(', ')}
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}
```

### Testing UI Components

```typescript
// Component test example
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

test('SessionCard shows pause button when running', async () => {
  const session = {
    session_id: 'test-123',
    status: 'running',
    workflow_type: 'orchestrator'
  }
  
  render(<SessionCard session={session} />)
  
  const pauseButton = screen.getByRole('button', { name: /pause/i })
  expect(pauseButton).toBeInTheDocument()
  
  await userEvent.click(pauseButton)
  expect(mockSignalAPI).toHaveBeenCalledWith('test-123', 'pause')
})
```

### Accessibility Guidelines

1. **Color Contrast**: All text must meet WCAG AA standards (4.5:1 for normal text)
2. **Keyboard Navigation**: All interactive elements accessible via Tab
3. **Screen Reader Support**: Proper ARIA labels and live regions
4. **Focus Indicators**: Visible focus rings on all interactive elements

```typescript
// Example: Accessible status badge
function StatusBadge({ status }: { status: WorkflowStatus }) {
  return (
    <span
      className={`badge badge-${status}`}
      role="status"
      aria-label={`Workflow status: ${status}`}
    >
      {status}
    </span>
  )
}
```

### Performance Optimization Patterns

1. **Lazy Loading**: Load trace data on demand
2. **Memoization**: Cache expensive computations
3. **Debouncing**: Batch rapid updates
4. **Web Workers**: Parse large traces off main thread

```typescript
// Debounced search
const debouncedSearch = useMemo(
  () => debounce((query: string) => {
    searchSpans(query)
  }, 300),
  []
)
```

## Handling CodeRabbit PR Reviews

CodeRabbit automatically reviews PRs and provides actionable feedback. Here's how to handle reviews effectively:

### 1. Accessing CodeRabbit Feedback

```bash
# View PR with reviews
gh pr view <PR_NUMBER> --repo <OWNER/REPO> --json reviews,comments

# Or use the web interface
gh pr view <PR_NUMBER> --web
```

### 2. Processing Feedback

CodeRabbit typically provides:
- **Actionable comments**: Specific issues with suggested fixes
- **Nitpick comments**: Minor improvements (prefixed with 🧹)
- **Summary statistics**: Files changed, issues found

### 3. Common Feedback Patterns

| Category | Common Issues | How to Fix |
|----------|--------------|------------|
| **Code Safety** | Missing imports, error handling | Add proper imports, try/except blocks |
| **Documentation** | Missing language specs, typos | Add language tags to code blocks, fix spelling |
| **Task Clarity** | Confusing status in PROGRESS.md | Move "not started" tasks from "In Progress" to "Pending" |
| **Performance** | Missing metrics, vague timelines | Add concrete numbers and dates |
| **Security** | Missing validation, threat modeling | Add input validation, security tasks |
| **Style** | Inconsistent formatting | Run formatters, fix linting issues |

### 4. Addressing Feedback Workflow

```bash
# 1. Create a todo list for tracking
# Use TodoWrite tool to track all feedback items

# 2. Fix issues by priority
# High: Security, bugs, missing error handling
# Medium: Performance, documentation
# Low: Style, minor improvements

# 3. Test your changes
pytest tests/  # Run tests
mypy --strict  # Type check
ruff check     # Lint

# 4. Commit with clear messages
git commit -m "fix(inspector): address CodeRabbit review feedback

- Add missing error handling to signal endpoints
- Fix code block language specifications
- Update task status clarity in PROGRESS.md files
- Add security validation for state injection

Addresses PR review comments"
```

### 5. Responding to Reviews

After addressing feedback:
1. Reply to each comment explaining what was done
2. Mark resolved conversations as outdated
3. Request re-review if substantial changes were made
4. Thank the bot for catching issues (good karma!)

### 6. Example Response Template

```markdown
Thanks @coderabbitai for the thorough review! I've addressed all the feedback:

✅ **Fixed**: Added error handling to all code examples
✅ **Fixed**: Added language specifications to code blocks
✅ **Fixed**: Clarified task status in milestone PROGRESS.md files
✅ **Fixed**: Added security considerations for state injection
✅ **Fixed**: Updated performance metrics with concrete values

The only suggestion I didn't implement was X because [valid reason].
```

## PR Checklist

Before submitting any PR, ensure you have:

### Code Quality
- [ ] All functions have complete type annotations
- [ ] All public functions have docstrings with Examples section
- [ ] `uv run scripts/lint.py --fix` has been run (formats and fixes linting issues)
- [ ] Optional: `mypy --strict` passes if you choose to run it locally
- [ ] No `# type: ignore` comments without explanation

### Testing
- [ ] Unit tests written for all new functions
- [ ] Tests achieve >90% code coverage
- [ ] All tests pass locally
- [ ] Performance tests added for critical paths
- [ ] E2E tests updated if UI changed
- [ ] **If touching mcp-agent core**: Full test suite passes (`make tests`)

### Documentation
- [ ] Updated relevant .md files in same PR
- [ ] Added/updated code examples
- [ ] Screenshots included for UI changes
- [ ] Docstrings follow Google style guide

### Final Checks
- [ ] PR is <500 lines (excluding generated files)
- [ ] Tested against real mcp-agent examples
- [ ] No new external dependencies added
- [ ] Performance impact measured (<1ms overhead)
- [ ] Error handling is explicit and typed

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification:

```text
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

#### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only changes
- `style`: Code style changes (formatting, missing semicolons, etc.)
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: Performance improvement
- `test`: Adding missing tests or correcting existing tests
- `build`: Changes to build system or dependencies
- `ci`: Changes to CI configuration files and scripts
- `chore`: Other changes that don't modify src or test files

#### Scopes
- `inspector`: Core inspector module
- `gateway`: HTTP gateway and routing
- `telemetry`: Span and trace handling
- `ui`: Frontend React components
- `e2e`: End-to-end tests

#### Examples
```text
feat(inspector): add progress tracking to spans

- Implement ProgressUpdate event type
- Add throttling to prevent event spam (2Hz max)
- Include progress bar in UI with cancel button

Task: understand/feat/progress-cancellation
Closes #123
```

```text
fix(gateway): handle missing trace files gracefully

Previously the gateway would crash with FileNotFoundError when
attempting to read non-existent trace files. This fix adds proper
error handling and returns 404 status.

Fixes #456
```

#### Task References
When implementing milestone tasks, always include the task ID:
```text
feat(inspector): create package skeleton

- Add inspector module with mount function
- Create version.py with __version__ constant
- Add gateway.py stub for re-export

Task: bootstrap/feat/inspector-package-skeleton
```

## Related Documentation

- [Architecture](architecture.md) - System design and components
- [Error Handling](error-handling.md) - Resilience patterns
- [Telemetry Spec](telemetry-spec.md) - Span and attribute conventions
- [Roadmap](roadmap.md) - Development milestones
- [Testing Guide](TESTING_GUIDE.md) - Comprehensive testing patterns