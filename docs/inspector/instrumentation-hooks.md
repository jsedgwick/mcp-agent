# Instrumentation Hooks – Formal Contract
Version 1.2 (2025-07-13)  
Status: **Current**

> This document is canonical.  
> • Telemetry spec, milestones, UI docs, and tests must **link here**  
>   (`@docs/inspector/instrumentation-hooks.md`).  
> • Any change to a hook signature **requires** updating this file **and**
>   bumping the minor version in §11.

────────────────────────────────────────────────────────────────────────
0  Why hooks?
────────────────────────────────────────────────────────────────────────
Inspector needs to **observe** mcp-agent without resorting to runtime
monkey-patching.  A tiny hook bus:

1. Maintains zero-dependency philosophy (no OpenTelemetry SDK hacking).  
2. Creates a **stable, versioned contract** for all downstream tools
   (Inspector, cost-tracking, cache, etc.).  
3. Makes refactors explicit: you add / rename / remove a hook, you update
   this doc.

────────────────────────────────────────────────────────────────────────
1  Non-goals
────────────────────────────────────────────────────────────────────────
* Not an event-bus for business logic – strictly **side-effect free /   observation only**.  
* Not a plug-in loader – it merely publishes in-process callbacks.  
* No guarantees of ordering **between different hook names**. Inside the
  *same* hook name order is FIFO registration.

────────────────────────────────────────────────────────────────────────
2  Design constraints
────────────────────────────────────────────────────────────────────────
| Constraint | Spec |
|------------|------|
| Overhead   | ≤ 2000 ns (2 µs) per `_emit()` with zero subscribers |
| Async-safe | Supports sync def, async def & returns ignored |
| Thread-safe| Works under asyncio default loop + potential threads |
| Exception handling | Exceptions in a subscriber are logged **and swallowed** (never break app code). |
| Import cost| Pure std-lib (collections, inspect, asyncio, logging) |

────────────────────────────────────────────────────────────────────────
3  Public API – `mcp_agent.core.instrument`
────────────────────────────────────────────────────────────────────────
```python
from collections import defaultdict
from inspect import iscoroutinefunction
from typing import Any, Awaitable, Callable, Coroutine, Dict, List

_Callback = Callable[..., Any | Awaitable[Any]]
_hooks: Dict[str, List[_Callback]] = defaultdict(list)

def register(name: str, fn: _Callback) -> None:
    """
    Subscribe to a hook.
    `fn` is awaited if coroutine; its return value is ignored.
    """
    _hooks[name].append(fn)

def unregister(name: str, fn: _Callback) -> None:
    """Remove callback; no error if not present."""
    callbacks = _hooks.get(name, [])
    if fn in callbacks:
        callbacks.remove(fn)

async def _emit(name: str, *a, **k) -> None:
    """
    Internal: fan-out to all registered callbacks.
    Exceptions are logged and swallowed.
    """
    for cb in _hooks.get(name, []):
        try:
            if iscoroutinefunction(cb):
                await cb(*a, **k)
            else:
                cb(*a, **k)
        except Exception:      # noqa: BLE001
            _logger.exception("Hook %s failed in %s", name, cb)
```

_emit is private – only core mcp-agent calls it.
Subscribers must not call _emit directly.

────────────────────────────────────────────────────────────────────────
4  Taxonomy & naming convention
────────────────────────────────────────────────────────────────────────

<phase>_<noun>                # snake_case
before_llm_generate
after_tool_call
before_* called immediately before user-visible side effect.
after_* called immediately after successful return.
error_* called when an action raises (includes exc kwarg).

────────────────────────────────────────────────────────────────────────
5  Core hook catalogue (v1.2)
────────────────────────────────────────────────────────────────────────

### Comprehensive Hook Catalogue

| Hook name | When emitted | Signature (kwargs) | Added |
|-----------|--------------|-------------------|-------|
| **Agent hooks** | | | |
| before_agent_call | Before Agent.call() | agent | v1.1 |
| after_agent_call | On successful return | agent, result | v1.1 |
| error_agent_call | Exception in Agent.call() | agent, exc | v1.1 |
| **LLM hooks** | | | |
| before_llm_generate | Just before provider call | llm, prompt | v1.0 |
| after_llm_generate | On successful return | llm, prompt, response, usage | v1.0 |
| error_llm_generate | Exception | llm, prompt, exc | v1.0 |
| **Tool hooks** | | | |
| before_tool_call | Right before tool resolver | tool_name, args, context | v1.0 |
| after_tool_call | On ok return | tool_name, args, result, context | v1.0 |
| error_tool_call | Tool raised | tool_name, args, exc, context | v1.0 |
| **Workflow hooks** | | | |
| before_workflow_run | At entry of Workflow.run | workflow, context | v1.0 |
| after_workflow_run | On ok return | workflow, context, result | v1.0 |
| error_workflow_run | Exception | workflow, context, exc | v1.0 |
| **RPC hooks** | | | |
| before_rpc_request | Just before JSON-RPC send | envelope, transport | v1.0 |
| after_rpc_response | On response receive | envelope, transport, duration_ms | v1.0 |
| error_rpc_request | Transport / RPC failure | envelope, transport, exc | v1.0 |
| **Resource hooks** | | | |
| before_resource_fetch | Before fetching resource | uri, context | v1.2 |
| after_resource_fetch | On successful fetch | uri, content, mime_type, context | v1.2 |
| error_resource_fetch | Fetch failure | uri, exc, context | v1.2 |
| **Prompt hooks** | | | |
| before_prompt_apply | Before applying template | template_id, parameters, context | v1.2 |
| after_prompt_apply | After template rendered | template_id, rendered, context | v1.2 |
| error_prompt_apply | Template error | template_id, parameters, exc, context | v1.2 |
| **Session lifecycle hooks** | | | |
| session_started | New session begins | session_id, metadata | v1.2 |
| session_paused | Session paused | session_id, signal_name, prompt | v1.2 |
| session_resumed | Session resumed | session_id, signal_name, payload | v1.2 |
| session_finished | Session ends | session_id, status, error | v1.2 |
| **Model selection hooks** | | | |
| before_model_select | Before selection | preferences, available_models, context | v1.2 |
| after_model_select | After selection | selected_model, scores, context | v1.2 |
| **Progress hooks** | | | |
| progress_update | Progress reported | operation_id, percent, message, context | v1.2 |
| operation_cancelled | Cancellation | operation_id, context | v1.2 |
| **Transport health hooks** | | | |
| transport_connected | Transport up | transport_type, uri | v1.2 |
| transport_disconnected | Transport down | transport_type, uri, reason | v1.2 |
| transport_reconnecting | Retry attempt | transport_type, uri, attempt | v1.2 |

**Notes:**
- `transport` is one of: `stdio` | `sse` | `http` | `websocket`
- All kwargs are positional-only for emitters; subscribers accept **kwargs to forward-compat when new fields appear.
- Hooks added in v1.2 enable full MCP spec coverage without direct OTel dependencies.

────────────────────────────────────────────────────────────────────────
6  Backwards & forwards-compat rules
────────────────────────────────────────────────────────────────────────

New hooks MAY be added in minor versions (1.1, 1.2). – Subscribers must ignore unknown names.
Removing or renaming a hook → major version (2.0) and NOTICE in CHANGELOG.
Adding kwargs to an existing hook is backwards compatible; always pass by keyword.
instrumentation-hooks.md contains the authoritative version table:

## Version history
v1.0  (2025-07-11) initial set with core hooks
v1.1  (2025-07-13) added agent hooks
v1.2  (2025-07-13) expanded catalogue for full MCP coverage

────────────────────────────────────────────────────────────────────────
7  Subscriber best-practice
────────────────────────────────────────────────────────────────────────

```python
# inspector/subscribers/llm_attrs.py
from mcp_agent.core import instrument
from opentelemetry import trace
import json

async def _before_llm_generate(llm, prompt, **_kw):
    span = trace.get_current_span()
    if span:
        span.set_attribute("mcp.llm.prompt_json", json.dumps(prompt))

instrument.register("before_llm_generate", _before_llm_generate)
```

### Guidelines

Never mutate positional objects (prompt, args, etc.).
Do not assume sync context – always support being awaited.
Keep CPU work < 200 µs; heavy work must be enqueued elsewhere.
Capture session_id via inspector.context.get() – don't construct one.

────────────────────────────────────────────────────────────────────────
8  Emitter guidelines (for core mcp-agent developers)
────────────────────────────────────────────────────────────────────────

Emit as close to the edge of user-observable behaviour as possible. – Example: after_tool_call goes after JSON‐schema validation but before serialising structured_output.
Never put _emit inside hot inner loops; instead aggregate and emit once if necessary.
Wrap emit in a fast path guard when high-frequency:
```python
if _hooks.get("before_llm_generate"):
    await _emit("before_llm_generate", llm=self, prompt=prompt)
```

────────────────────────────────────────────────────────────────────────
9  Error handling philosophy
────────────────────────────────────────────────────────────────────────

A bug in a subscriber must not break agent execution.
Failure is logged under logger "mcp.instrument" level WARNING.
Subscribers needing guaranteed delivery should implement their own retry/staging.

────────────────────────────────────────────────────────────────────────
10  Testing strategy
────────────────────────────────────────────────────────────────────────

Unit – stub subscriber, call internal function, assert fire count.
Integration – Inspector Playwright test asserts attribute captured (e.g., PlanResult visible) which indirectly tests hook flow.
Contract – Schemathesis tests against the OpenAPI spec at [docs/inspector/openapi.yaml](openapi.yaml), verifying the /events endpoint produces spans with required attributes when hooks are present.
Utility helper for tests:

```python
from contextlib import asynccontextmanager
from mcp_agent.core.instrument import register, unregister

@asynccontextmanager
async def capture_hook(name):
    calls = []
    async def _rec(*a, **k):
        calls.append((a, k))
    register(name, _rec)
    try:
        yield calls
    finally:
        unregister(name, _rec)
```

────────────────────────────────────────────────────────────────────────
11  Version history & bump process
────────────────────────────────────────────────────────────────────────

Increment minor when: – new hook added – new kwargs added
Increment major when: – hook renamed or removed – breaking change in callback semantics
Update CHANGELOG and this header.

## History
v1.0  2025-07-11  initial catalogue
v1.0  2025-07-13  finalized; adjusted performance target from 70ns to 2µs based on implementation testing
v1.1  2025-07-13  added before_agent_call, after_agent_call, error_agent_call hooks
v1.2  2025-07-13  expanded catalogue: resources, prompts, sessions, models, progress, transport

────────────────────────────────────────────────────────────────────────
12  Referencing this doc from others
────────────────────────────────────────────────────────────────────────

telemetry-spec.md – Each attribute table row that originates from a
hook must have a final column "Hook" pointing to the hook name.

Example row:

Attribute	Added by	Hook
mcp.llm.prompt_json	Inspector subscriber	before_llm_generate
milestones/*/README.md – When a task says "add emit", link with
@docs/inspector/instrumentation-hooks.md.

development.md – Under "Backend patterns → Hook subscriber template"
import this file with @instrumentation-hooks.md#subscriber-best-practice.

────────────────────────────────────────────────────────────────────────
13  Legacy fallback (optional)
────────────────────────────────────────────────────────────────────────
If environment variable INSPECTOR_ENABLE_PATCH=1 and
not hasattr(mcp_agent.core, "instrument"), Inspector will apply the
old monkey patches once for backward compatibility.  This shim is
documented in legacy-patching.md (not imported by default).

────────────────────────────────────────────────────────────────────────
14  Open questions  (add PRs here)
────────────────────────────────────────────────────────────────────────
Do we need "around_*" hooks that expose both before and after?
Should hook registration support priorities?
Formal TypedDict classes for kwargs to satisfy MyPy?
Please discuss in GitHub issue #42 – Hook API bake-off.

────────────────────────────────────────────────────────────────────────
15  Architectural Migration Context
────────────────────────────────────────────────────────────────────────

**CRITICAL**: The hook system documented here is the future-state architecture. 
Currently, mcp-agent core has extensive direct OpenTelemetry integration that 
creates its own spans via `@telemetry.traced()` decorators and manual 
`tracer.start_as_current_span()` calls.

This creates a dual-instrumentation situation where:
- Core code creates spans directly AND emits hooks
- Inspector subscribers enrich the same spans created by core
- This redundancy is technical debt being addressed via migration

**Migration Rules**:
1. All NEW features MUST use ONLY the hook-based pattern
2. Existing direct OTel code will be gradually refactored
3. Future state: Core mcp-agent will have zero OTel imports
4. During transition: Inspector enriches existing spans

See [architecture.md §6.6](architecture.md#66-architectural-migration-from-direct-otel-to-hook-based) 
for full migration strategy.

End of instrumentation-hooks.md