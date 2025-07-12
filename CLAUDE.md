# CLAUDE.md – v2.0 (2025-07-11)
# mcp-agent-inspector - Primary AI assistant instructions

## What is Inspector?
An embedded, zero-dependency debugging and observability tool for mcp-agent. It provides a web UI that helps you answer:
- What workflows are running right now?
- Why did my workflow pause?
- What was the exact plan my Orchestrator decided on?
- How much did that last turn cost in tokens and money?

## Mission
• You are augmenting mcp-agent-inspector (zero-dep, in-process UI).
• Implement tasks in docs/inspector/milestones, always ship tests & docs.
• Obey OpenTelemetry + MCP spec; never add external services.

## Golden Rules
1. Zero external services (no Redis/Postgres).  
2. All spans/events use telemetry-spec names.  
3. Public API = typed + docstring.  
4. TDD mandatory (unit + contract + E2E ≤ 90s).  
5. Docs updated in same PR.

## Code Quality Standards
**MANDATORY for every PR:**

### Type Hints
All functions MUST have complete type annotations (params + return).
```bash
# Bad
def process_data(data):
    return data.upper()

# Good
def process_data(data: str) -> str:
    return data.upper()
```

### Unit Tests  
Write tests FIRST (TDD), aim for >90% coverage.
```bash
# Check coverage
make coverage

# Generate HTML coverage report
make coverage-report
```

### Code Formatting & Linting
Run before EVERY commit:
```bash
# Format code (runs ruff format)
make format

# Fix linting issues (runs ruff check --fix)
make lint

# Or do both in one command
uv run scripts/lint.py --fix
```

### Docstrings
Every public function needs docstring with Examples section.
```python
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
```

### Type Checking
**Note**: mypy is aspirational - not currently enforced in CI but recommended for new code.
```bash
# If you want to use mypy locally (not required):
# uv pip install mypy
# mypy --strict mcp_agent/inspector/
```
The project currently relies on ruff for basic type checking via type annotations.

### Performance
Profile first, optimize second (target <5µs hook overhead per span).
```bash
# Use pytest-benchmark for performance tests
# See tests/perf/ for examples
```

## Critical Documentation
**IMPORTANT**: Before implementing any inspector feature, you MUST read the relevant docs in docs/inspector/:
- **First**: Check @docs/inspector/roadmap.md for current milestone
- **Second**: Read the milestone file (e.g., @docs/inspector/milestones/1-bootstrap/README.md)
- **Always consult**: 
  - @docs/inspector/instrumentation-hooks.md - Hook bus contract and API
  - @docs/inspector/architecture.md - System design, zero-dependency principles
  - @docs/inspector/telemetry-spec.md - Span names, attributes, events
  - @docs/inspector/spec-alignment.md - MCP spec compliance
  - @docs/inspector/openapi.yaml - HTTP API specification
  - @docs/inspector/development.md - Patterns, debugging, dogfooding
  - @docs/inspector/TESTING_GUIDE.md - Test requirements and examples
  - @docs/inspector/error-handling.md - Resilience patterns
  - @docs/inspector/security.md - Auth and security model
  - @docs/inspector/context-propagation.md - Session ID and context handling
  - @docs/inspector/vision.md - Project vision and roadmap
  - @docs/inspector/ux-ui-playbook.md - UI/UX patterns, design tokens

**When starting any task**: Re-read the milestone doc and any related sections from the docs above. The documentation is authoritative and contains critical implementation details.

## Quick Start

### Installation
```bash
# Fast path (requires uv - https://github.com/astral-sh/uv)
uv pip install "mcp-agent[inspector]"

# Or in development mode
git clone https://github.com/your-org/mcp-agent-inspector
cd mcp-agent-inspector
# Install in dev mode
uv pip install -e ".[dev]"

# Frontend setup (one-time)
cd packages/inspector_ui
pnpm install
```

### Usage
```python
from mcp_agent.app import MCPApp
from mcp_agent.inspector import mount

# Assuming you have an existing MCPApp instance
app = MCPApp(name="my-agent-app")

# Mount the inspector (one line!)
mount(app)

# Access at http://localhost:7800/_inspector/ui
```

### Verify Installation
```bash
pytest -q && pnpm playwright test
# Both should pass in <90s
```

## Instrumentation Hooks

Inspector uses the formal hook system instead of monkey-patching:

```python
from mcp_agent.core import instrument
from opentelemetry import trace

async def before_llm_generate(llm, prompt, **_kw):
    span = trace.get_current_span()
    if span:
        span.set_attribute("mcp.llm.prompt_json", json.dumps(prompt))

instrument.register("before_llm_generate", before_llm_generate)
```

See @docs/inspector/instrumentation-hooks.md for the complete contract.

## Daily Flow
1. Pick task → @docs/inspector/roadmap.md  
2. Write failing tests → see @docs/inspector/TESTING_GUIDE.md  
3. Code & run `./scripts/run_ci_local.sh`  
4. Update docs + open PR (follow template in M*.md)

## Core Patterns

### Session ID Propagation
```python
# At workflow entry point (ONCE per session)
from mcp_agent.inspector import context as insp_ctx
session_id = str(uuid4())
insp_ctx.set(session_id)

# Anywhere else in the call stack
session_id = insp_ctx.get()  # Automatically propagated
```

### State Capture
```python
@dump_state_to_span()
async def run(self, context: Context) -> PlanResult:
    # Return value automatically captured as mcp.result.run_json
    return result
```

## Best Practices

### Type Safety First
```python
from typing import Optional, List, Dict, Any
from mcp_agent.types import Context, PlanResult

# BAD - No type hints
def process_workflow(ctx, data):
    return {"result": data}

# GOOD - Complete type annotations
async def process_workflow(
    ctx: Context, 
    data: Dict[str, Any]
) -> PlanResult:
    """Process workflow with given data.
    
    Examples:
        >>> ctx = Context(session_id="test-123")
        >>> result = await process_workflow(ctx, {"task": "analyze"})
        >>> assert result.plan_id
    """
    return PlanResult(plan_id=ctx.session_id, data=data)
```

### Test-Driven Development
```python
# ALWAYS write the test first
async def test_workflow_captures_state():
    """State should be captured in span attributes"""
    # Arrange
    ctx = Context(session_id="test-123")
    expected_state = {"status": "completed"}
    
    # Act
    with tracer.start_as_current_span("test") as span:
        result = await my_workflow(ctx)
    
    # Assert
    assert "mcp.state.workflow_json" in span.attributes
    state = json.loads(span.attributes["mcp.state.workflow_json"])
    assert state["status"] == "completed"
```

### Error Handling
```python
# GOOD - Explicit error handling with proper typing
from typing import Union
from mcp_agent.errors import WorkflowError

async def safe_workflow(
    ctx: Context
) -> Union[PlanResult, WorkflowError]:
    try:
        result = await risky_operation()
        return PlanResult(plan_id=ctx.session_id, data=result)
    except Exception as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.set_status(Status(StatusCode.ERROR))
        return WorkflowError(message=str(e), code="WORKFLOW_FAILED")
```

## Testing

### Test Suite Overview
```bash
# Run all tests (completes in <90s)
pytest tests/inspector && pnpm test && pnpm playwright test

# Run specific test types
pytest tests/unit              # Unit tests only
pytest tests/contracts         # Schema validation
pnpm test                      # Frontend components
pnpm playwright test           # E2E browser tests

# Run with coverage
pytest --cov=mcp_agent.inspector
pnpm test:coverage
```

### Testing Matrix
| Type | Tool | Target |
|------|------|--------|
| Unit | pytest | <1.5s per file |
| Contract | Schemathesis | API schemas |
| Component | vitest | UI components |
| E2E | Playwright | Full workflows |
| Performance | pytest-benchmark | <1.5s for 50k spans |

### Testing mcp-agent Core Changes

**CRITICAL**: Before pushing any changes that touch mcp-agent core functionality (e.g., hooks, instrumentation, workflow execution), you MUST run the full mcp-agent test suite:

```bash
# Ensure all dependencies are installed
uv sync --all-extras --all-packages --group dev

# Run all tests (should complete in <45s)
make tests
# or
uv run pytest

# If you've modified specific areas, test them first:
uv run pytest tests/agents/           # Agent functionality
uv run pytest tests/executor/         # Workflow execution
uv run pytest tests/workflows/llm/    # LLM providers
```

Common issues and fixes:
- **Missing dependencies**: Run `uv sync --all-extras --all-packages --group dev`
- **Syntax errors**: Check any modified Python files for proper indentation
- **Import errors**: Ensure new modules are properly exported in `__init__.py`
- **Different Python versions**: Use `uv run pytest` to ensure consistent environment

## Common Scripts
→ package.json & scripts/*.sh

## Architecture & Patterns
→ @docs/inspector/architecture.md

## Frontend Patterns
→ @docs/inspector/development.md#frontend-development

## Testing Examples
→ @docs/inspector/TESTING_GUIDE.md

## Dogfooding & Examples
→ @docs/inspector/development.md#dogfooding-guide

## The Problem We Solve
Debugging mcp-agent workflows often involves:
- Tailing and parsing large JSONL log files
- Mentally reconstructing async execution flow
- Adding print() statements to inspect state
- Wondering if a paused workflow has hung

Inspector replaces this with a rich, interactive visual interface that dramatically accelerates development.

## Final Checklist
Before submitting any PR, ensure your changes work with ALL these examples:

- [ ] `examples/workflows/orchestrator_worker.py` - PlanResult visible
- [ ] `examples/workflows/router.py` - RouterDecision visible  
- [ ] `examples/elicitation/main.py` - PAUSED state visible
- [ ] `examples/mcp_primitives/mcp_basic_agent/app.py` - Tool calls tracked
- [ ] `examples/human_input/handler.py` - WaitingOnSignal events flowing
- [ ] `examples/temporal/orchestrator.py` - Temporal workflows appear

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/) for all changes:

### Format
```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Types
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

### Scopes
- `inspector`: Core inspector module
- `gateway`: HTTP gateway and routing
- `telemetry`: Span and trace handling
- `ui`: Frontend React components
- `e2e`: End-to-end tests
- `docs`: Documentation

### Examples
```bash
feat(inspector): add session list endpoint
fix(gateway): handle missing trace files gracefully
docs(telemetry): update span attribute conventions
test(ui): add session card component tests
perf(telemetry): optimize span serialization
```

### Task References
Include task ID in footer when completing milestone tasks:
```
feat(inspector): implement health endpoint

Implements gateway mount with Starlette sub-app serving health status

Task: bootstrap/feat/gateway-health-endpoint
```

## Progress Tracking

Each milestone has two critical documents:

### 1. README.md (Immutable Task Definitions)
- Contains the authoritative task specifications
- Should NOT be modified during implementation
- Defines acceptance criteria and implementation notes
- Serves as the "contract" for what needs to be built

### 2. PROGRESS.md (Living Progress Document)
- Updated after EVERY task completion or status change
- Tracks what's been done, what's in progress, blockers
- Records deviations from original plan
- Captures lessons learned and metrics

### Progress Update Protocol
When working on any task:
1. Update PROGRESS.md to mark task as "in_progress"
2. Complete the implementation
3. Update PROGRESS.md with completion details:
   - Date completed
   - Commit hash/PR number
   - Any deviations from plan
   - Lessons learned
4. Never modify the README.md task definitions

Example PROGRESS.md update:
```markdown
### ✅ bootstrap/feat/inspector-package-skeleton
**Completed**: 2025-07-11  
**Commit**: `feat(inspector): create package skeleton`  
**PR**: #123  

**What was done**:
- Created inspector module structure
- Added version constant
- Implemented mount function stub

**Deviations**: None
**Lessons learned**: Following exact spec made implementation smooth
```

## Handling CodeRabbit Reviews

When CodeRabbit reviews a PR, follow this process:

1. **Get the PR review** using GitHub CLI:
   ```bash
   gh pr view <PR_NUMBER> --repo <OWNER/REPO> --json reviews,comments
   ```

2. **Create a todo list** to track all feedback items:
   - High priority: Security issues, bugs, missing error handling
   - Medium priority: Performance issues, documentation gaps
   - Low priority: Style issues, minor improvements

3. **Address feedback systematically**:
   - Start with high-priority items
   - Update todo status as you progress
   - Test changes before committing

4. **Common CodeRabbit feedback categories**:
   - **Task clarity**: Ensure milestone PROGRESS.md files have clear status
   - **Code safety**: Add proper error handling and imports
   - **Documentation**: Fix spelling, formatting, language specs
   - **Security**: Add threat modeling and validation
   - **Performance**: Add concrete metrics and timelines

5. **Respond to the review**:
   - Mark resolved comments as outdated
   - Explain any feedback you disagree with
   - Thank the bot for catching issues

## Remember
Inspector should be so useful we cannot imagine developing mcp-agent without it. Every PR should make debugging easier, not just add features.

## Memory
• Always use `uv` (Universal Virtual) for package management instead of legacy `pip`