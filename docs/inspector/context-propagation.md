# Context & Session ID Propagation
Version 1.0  (2025-07-11)

## 1  Why ContextVars?
– Avoids threaded-logging pain  
– Works in FastAPI, background tasks, callbacks

## 2  Public Helper API
```python
import contextvars, functools, asyncio
_session_id = contextvars.ContextVar('session_id', default='unknown')

def set(session_id: str):  # call once per session root
    _session_id.set(session_id)

def get() -> str:
    return _session_id.get()

def bind(fn):
    """Decorator that injects `session_id` kwarg if the target accepts it."""
    @functools.wraps(fn)
    async def _w(*a, **kw):
        if 'session_id' in fn.__code__.co_varnames:
            kw.setdefault('session_id', get())
        return await fn(*a, **kw) if asyncio.iscoroutinefunction(fn) else fn(*a, **kw)
    return _w
## 3. Lifecycle
1. Workflow root allocates session_id → `context.set(id)`
2. FileSpanExporter / SSE listener call `context.get()`
3. Middleware / background tasks restore with `context.set(id)` if needed

## 4. Idiomatic Snippets

### FastAPI Middleware
```python
@app.middleware("http")
async def attach_session(request: Request, call_next):
    session_id = request.headers.get("X-Session-Id", str(uuid4()))
    context.set(session_id)
    return await call_next(request)
```

### Background Task
```python
async def background_process(session_id: str = None):
    if session_id:
        context.set(session_id)
    # Now context.get() returns the correct session_id
```

## 5. FAQ / Pitfalls

### Q: How does it interact with hooks?
A: Hooks run in the same async context, so `context.get()` works inside hook callbacks:
```python
async def before_llm_generate(llm, prompt, **_kw):
    session_id = context.get()  # Automatically available
    span = trace.get_current_span()
    if span:
        span.set_attribute("session.id", session_id)
```

### Q: What about asyncio.create_task?
A: Context is automatically copied to new tasks in Python 3.7+:
```python
# Context propagates automatically
task = asyncio.create_task(background_process())
```

### Q: Can I use it in tests?
A: Yes, set context at test start:
```python
async def test_workflow():
    context.set("test-session-123")
    result = await my_workflow()
    assert context.get() == "test-session-123"
```

### Q: What if I need multiple IDs?
A: Never generate a second ID mid-workflow. Use a single session_id throughout the entire execution.


