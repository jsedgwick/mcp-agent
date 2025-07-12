# mcp-agent-inspector Implementation Roadmap

**Version**: 2.0 (Conventional Commits Edition)  
**Updated**: 2025-07-11  
**Audience**: Developers, AI Assistants, Project Managers

> **Note**: This document now uses semantic versioning for milestones and conventional commit-friendly task naming. See [MIGRATION_MAP.md](milestones/MIGRATION_MAP.md) for old→new ID mappings.

## Why this revision?
• Internal developers run every example in examples/ at least daily.
• The very first time they enable Inspector it should already answer: "What session is active?", "Where is it paused or failing?", "What state did that workflow end up with?"
• Fancy graphs, Sandpit, and Step-Through can come later, but basic state, paused-signal visibility and Temporal parity must arrive in the same milestone as the raw tree.

The original plan reached that insight at the end of the 3-understand milestone; we pull a handful of low-cost backend changes forward so the 2-observe milestone becomes immediately indispensable.

## Core Design Principle: Zero External Dependencies
The fundamental goal for milestones 1-4 is that developers can add Inspector with one line of code and zero new processes or databases. See docs/inspector/zero-dependency-design.md for details.

## Milestone Naming Convention

Milestones use simple sequential numbering with descriptive suffixes:
- `1-bootstrap` - Core foundation
- `2-observe` - Basic observability
- `3-understand` - Enhanced debugging
- `4-visualize` - Workflow visualizations
- `5-interact` - Interactive development
- `6-production` - Production readiness

## Task Naming Convention

Tasks follow the pattern: `<milestone>/<type>/<scope>-<description>`

Examples:
- `bootstrap/feat/inspector-package-skeleton`
- `observe/fix/gateway-error-handling`
- `understand/docs/api-reference`

This enables:
- Direct mapping to conventional commits
- Easy filtering and querying
- Self-documenting task references
- Automated changelog generation

## Progress Tracking

Each milestone has two documents:
1. `README.md` - Immutable task definitions and requirements
2. `PROGRESS.md` - Living document tracking completion status

See [1-bootstrap/](milestones/1-bootstrap/) for the template.

## Milestone Overview

| ID | Name | Focus | Target Completion |
|----|------|-------|-------------------|
| 1-bootstrap | Core Foundation | Package structure, health endpoint | Week 1 |
| 2-observe | Dogfood MVP | Sessions, traces, state visibility | Week 2-3 |
| 3-understand | Enhanced Debugging | Context viewer, human input, polish | Week 4-5 |
| 4-visualize | Workflow Visuals | DAGs, routers, rich visualizations | Week 6-7 |
| 5-interact | Interactive Dev | REPL, step-through, sandpit | Week 8-9 |
| 6-production | Production Ready | Security, monitoring, Temporal | Week 10-12 |

────────────────────────────────────────
## 1-bootstrap – "Hello Inspector"
────────────────────────────────────────
Goal: lay plumbing that never changes again; ship a /_inspector/health page so everyone can iterate quickly.

**Full Details**: See [milestones/1-bootstrap/README.md](milestones/1-bootstrap/README.md)

### bootstrap/feat/instrumentation-hook-bus
WHY: Inspector needs to observe mcp-agent without runtime patching.
WHAT: Implement core hook bus in mcp_agent.core.instrument with register/unregister/_emit.
HOW: Follow contract in [instrumentation-hooks.md](instrumentation-hooks.md). Add first three emit sites: Agent.call_tool, Workflow.run, AugmentedLLM.generate.
DONE-WHEN: Unit test shows callbacks fire when hooks are emitted.

### bootstrap/feat/inspector-package-skeleton
WHY: import path must exist.
WHAT: create mcp_agent/inspector/__init__.py with mount and __version__.
HOW: mount stub, version constant, proper re-exports.
DONE-WHEN: uv run python -c "from mcp_agent.inspector import mount, __version__" works.

### bootstrap/feat/gateway-health-endpoint
WHY: host process must expose HTTP quickly.
WHAT: mount(app, expose=False) adds Starlette sub-app at /_inspector; adds /health GET returning JSON {version:"0.0.1"}.
HOW: If expose=False but parent FastAPI not present, spawn internal Uvicorn bound to 127.0.0.1:7800.
DONE-WHEN: unit-test calls mount(FastAPI()) and client.get("/_inspector/health") returns 200.

### bootstrap/feat/telemetry-span-attributes
WHY: early spans prove enrichment path.
WHAT: file span_meta.py (Enum-like class).
Insert attribute "mcp.agent.class" = agent.__class__.__name__ to agent spans using decorator on Agent.call.
DONE-WHEN: pytest opens trace JSON, key exists.

### bootstrap/feat/ui-react-scaffold
WHY: backend teams need static hosting to check integration.
WHAT: Vite + React + TypeScript in packages/inspector_ui; single page "Inspector Online".
Gateway serves dist/ under /_inspector/ui (StaticFiles).
Include npm script in package.json: `"gen:schemas": "openapi-typescript ../../docs/inspector/openapi.yaml -o src/generated/api.ts"`
DONE-WHEN: curl http://localhost:7800/_inspector/ui/ returns HTML.

### bootstrap/ci/github-actions-setup
WHY: new code must gatekeep quality from day 1.
WHAT: GitHub Actions workflow: pytest, mypy, eslint, prettier.
Sample Playwright test hits /_inspector/health.
DONE-WHEN: PR fails if tests fail.

User-visible value after 1-bootstrap: developer runs script, visits http://127.0.0.1:7800/_inspector/ui and sees confirmation banner – proves embedding works.

────────────────────────────────────────
## 2-observe – Dogfood MVP
────────────────────────────────────────
User story at end of 2-observe:
"I launch any example (asyncio or Temporal). The Inspector list shows it instantly; I click and watch spans appear; I click the workflow span and immediately read the PlanResult JSON; if the run pauses for human_input, a yellow badge tells me why nothing new appears."

**Full Details**: See [milestones/2-observe/README.md](milestones/2-observe/README.md)

### Backend tasks for 2-observe

### observe/feat/sessions-unified-list
WHY: developers need to see all active sessions regardless of engine.
WHAT: queries InMemoryWorkflowRegistry and Temporal client list_workflows(filter running) if engine==temporal.
HOW: merge both sources into unified format: id • status • started_at • engine • title.
DONE-WHEN: pytest asserts both asyncio & temporal sessions appear in same list.

### observe/feat/trace-file-exporter
WHY: front-end must download traces progressively.
WHAT: extend existing FileSpanExporter to write JSONL to ~/.mcp_traces/{session_id}.jsonl.gz.
HOW: use aiofiles async generator; send Content-Encoding: gzip; honour Range header.
DONE-WHEN: curl -H"Range:bytes=0-2000" returns 206.

### observe/feat/events-sse-stream
WHY: real-time updates without polling.
WHAT: listener serialises Events to SSE stream.
HOW: attach to existing AsyncEventBus; SSE id = monotonic counter; retry 2000 ms.
DONE-WHEN: Browser EventSource receives >1 message during 30 s run.

### observe/feat/telemetry-full-enrichment
WHY: To provide meaningful debugging, we must capture the full richness of MCP interactions from day one.
WHAT: Implement the full set of telemetry attributes defined in telemetry-spec.md:
• Multi-part messages: Hook into AugmentedLLM.generate to capture mcp.llm.prompt_json and mcp.llm.response_json
• Resource/Prompt Usage: Hook into MCPAggregator to add mcp.resource.uri and mcp.prompt.template_id attributes
• Model Selection: Hook into ModelSelector to capture mcp.model.preferences_json
• State capture: Generic decorator @dump_state_to_span() for workflow results
DONE-WHEN: examples/mcp_primitives/mcp_basic_agent/ produces trace with rich, spec-compliant attributes.

### observe/feat/sessions-inbound-mcp
WHY: The "agent-as-a-server" pattern is fundamental. We must provide visibility into inbound requests.
WHAT: Implement middleware for app_server.py to create "inbound" sessions, using MCP request_id as session_id.
HOW: Extract request_id from envelope; create span with mcp.request_id attribute; show with engine="mcp-inbound".
DONE-WHEN: Running examples/mcp_agent_server/ with client creates new session in UI with engine: "mcp-inbound".

### observe/feat/workflow-pause-signals
WHY: Paused states are a primary debugging pain point. The spec defines elicitation, and mcp-agent has human_input.
WHAT: Implement WaitingOnSignal event emission for both console_elicitation_callback and human_input_callback.
HOW: Hook into elicitation/handler.py and human_input/handler.py; emit WaitingOnSignal events.
DONE-WHEN: Running examples/elicitation/main.py causes "PAUSED" status to appear in the UI.

### observe/feat/ui-session-navigator
WHY: Combine initial frontend tasks into one deliverable for complete debugging view.
WHAT: Session List, virtualized Navigator Tree, and Inspector panel with three tabs:
• Attributes: Raw key-value view of all span attributes
• State/Result: Renders any attribute ending in _json using JSON pretty-printer
• Context: Renders mcp.llm.prompt_json and mcp.llm.response_json
DONE-WHEN: Developer can run any example, see session, navigate spans, and see all state/message data as formatted JSON.

### observe/docs/api-reference-stubs
WHY: Need clear documentation for early adopters.
WHAT: README with install, usage, screenshots; API reference stubs for public endpoints.
HOW: Update telemetry-spec.md header to note all attributes are implemented from observe milestone onward. Create initial OpenAPI spec at docs/inspector/openapi.yaml defining all HTTP endpoints (/health, /sessions, /trace/{session_id}, /events, /signal/{session_id}, /cancel/{session_id}).
DONE-WHEN: Developer can follow README to set up and use Inspector; OpenAPI spec validates with contract tests.

### observe/test/e2e-playwright-suite
WHY: Ensure complete integration works.
WHAT: Spin demo agent, visit UI, verify session appears, spans load, attributes visible.
HOW: Test multi-part messages, resource usage, and inbound sessions.
DONE-WHEN: Playwright test passes with all key features verified.

### Front-end tasks for 2-observe
**Note**: All frontend tasks must follow the UI/UX patterns defined in [@docs/inspector/ux-ui-playbook.md](ux-ui-playbook.md).

- Table columns: ID, status dot, engine badge, started_at.
- Span tree – minimal styling; new "⚠ waiting signal" leaf lines.
- Inspector Overview table with JSON prettified.
- Minimal toast: "SSE connected / disconnected".

### Dog-food checklist for 2-observe
✓ Run examples/workflows/orchestrator_worker.py: see session, open tree, click orchestrator; PlanResult JSON visible.
✓ Run examples/mcp_primitives/mcp_basic_agent.py: multi-part prompt/response visible in Context tab.
✓ Run examples/mcp_agent_server/ with external client: inbound session appears with engine="mcp-inbound".
✓ Run examples/elicitation/main.py: session shows yellow "PAUSED" status; waiting signal visible.
✓ Run examples/temporal/orchestrator.py: session appears with engine=temporal badge; span tree loads.

────────────────────────────────────────
## 3-understand – Enhanced Debugging
────────────────────────────────────────
Adds the "nice" UI for state JSON, full Context Window, and ability to answer the paused human input.

**Full Details**: See [milestones/3-understand/README.md](milestones/3-understand/README.md)

### Backend additions
### understand/feat/llm-history-snapshot
WHY: developers need to see what the model saw.
WHAT: in AugmentedLLM.generate, slice last N=20 message dicts, json.dumps w/out whitespace; size guard 10 kB.
DONE-WHEN: unit test ensures <=10 kB.

### understand/feat/metrics-heartbeat
WHY: live metrics without F5 refresh.
WHAT: mount() adds asyncio.create_task(emit_heartbeat()) storing last counters per session; fire Event Heartbeat.
DONE-WHEN: Explorer sparkline shows live token usage.

### understand/feat/workflow-signal-api
WHY: unblock paused workflows.
WHAT: endpoint accepts JSON with answer field, calls workflow signal handler.
DONE-WHEN: human_input example resumes after form submission.

### Front-end additions
**Note**: All frontend tasks must follow the UI/UX patterns defined in [@docs/inspector/ux-ui-playbook.md](ux-ui-playbook.md).

### understand/feat/ui-state-json-viewer
WHY: editable JSON for future inject_state feature.
WHAT: integrate react-json-view with collapse/expand, copy path.
DONE-WHEN: State tab shows collapsible JSON tree.

### understand/feat/ui-context-viewer
WHY: understand prompt evolution.
WHAT: tab icon 📜; pill shows tokens "3k/8k"; chat transcript style rendering. Must render text, image, resource and tool_use parts.
DONE-WHEN: selecting LLM span shows message history with all content types.

### understand/feat/ui-human-input-form
WHY: answer paused workflows from UI.
WHAT: auto-renders JSON-Schema from signal metadata; on submit calls /signal.
DONE-WHEN: form appears when workflow paused, submission resumes execution.

### understand/feat/ui-session-sparklines
WHY: at-a-glance resource usage.
WHAT: accumulate heartbeat deltas; inline SVG path; tooltip shows details.
DONE-WHEN: table shows live sparklines updating every 10s.

### understand/feat/mcp-request-log
WHY: debug MCP server tool implementations.
WHAT: Inspector tab shows request/response bodies for inbound MCP calls; filterable by tool name.
HOW: FastToolServer middleware captures bodies; stores in ring buffer; exposes via /trace/{sid}/mcp_requests endpoint.
DONE-WHEN: clicking inbound session shows list of tool calls with expandable request/response JSON.

### understand/feat/progress-cancellation
WHY: Long-running operations need visibility and control.
WHAT: Backend captures progress notifications, emits ProgressUpdate events. Frontend shows progress bar & Cancel button.
HOW: Hook into MCP progress callback; store progress_token in span attributes. Cancel button sends /cancel/{session_id} POST.
DONE-WHEN: Unit test with stubbed long-running tool shows progress bar updating and cancellation working.

Dogfood win → Agents unblock themselves from UI; dev sees prompt history.

────────────────────────────────────────
## 4-visualize – Workflow Visuals
────────────────────────────────────────
Making sense of complex workflows through rich visualizations.

**Full Details**: See [milestones/4-visualize/README.md](milestones/4-visualize/README.md)

### visualize/feat/plugin-architecture
WHY: extensible visualization system.
WHAT: VisualizerPlugin interface; registry with match() predicate; built-in fallback.
DONE-WHEN: new plugins can be registered without modifying core.

### visualize/feat/plugin-orchestrator-dag
WHY: DAG understanding at a glance.
WHAT: react-flow graph from workflow.plan_json; nodes show status; click navigates to span.
DONE-WHEN: 6-node plan renders with correct dependencies and live status.

### visualize/feat/plugin-router-scores
WHY: understand routing logic.
WHAT: table with scores, bar charts, winner highlighted.
DONE-WHEN: router spans show score breakdown visually.

### visualize/feat/plugin-aggregator-path
WHY: trace tool resolution path.
WHAT: vertical flow showing server hits/misses with latency.
DONE-WHEN: aggregator spans show resolution steps clearly.

### visualize/feat/plugin-additional
• EvaluatorLoop: iteration cards with ratings
• ParallelFanOut: swimlanes per sub-agent
• SwarmHandOff: sequence diagram

### visualize/feat/plugin-model-selection
WHY: Debug model routing decisions and preferences.
WHAT: Show mcp.model.preferences_json as ranked table with scores.
DONE-WHEN: Model selection spans display preference matrix.

Test Plan:
* Unit: tests/unit/test_model_preferences.py
* Component: tests/components/ModelSelectionViewer.test.tsx
* E2E: tests/e2e/visualize/model_selection.spec.ts

### visualize/feat/trace-distributed-view
WHY: Correlate traces across client/server boundaries.
WHAT: Stitch spans using mcp.rpc.id correlation; timeline view.
DONE-WHEN: Clicking tool call shows both client and server spans.

Test Plan:
* Unit: tests/unit/test_trace_correlation.py
* Component: tests/components/DistributedTraceView.test.tsx
* E2E: tests/e2e/visualize/distributed_trace.spec.ts

### visualize/feat/plugin-resource-browser
WHY: Visualize resource hierarchy and access patterns.
WHAT: Tree view of resources accessed, with MIME types and sizes.
DONE-WHEN: Resource spans show collapsible URI tree with metadata.

### visualize/feat/plugin-prompt-template
WHY: Understand prompt composition and parameter substitution.
WHAT: Side-by-side template vs rendered view with parameter highlighting.
DONE-WHEN: Prompt spans show template with substituted values highlighted.

Value after 4-visualize → complex workflows become intuitive visual stories.

────────────────────────────────────────
## 5-interact – Interactive Development
────────────────────────────────────────
Change the future through interactive debugging and experimentation.

**Full Details**: See [milestones/5-interact/README.md](milestones/5-interact/README.md)

### interact/feat/debug-step-through
WHY: pause at each orchestrator step.
WHAT: before_step Event + await logic; continue signal with optional state override.
DONE-WHEN: workflow pauses between plan steps.

### interact/feat/ui-repl-chat
WHY: interactive agent development.
WHAT: split view chat/debugger; streaming tokens; human_input forms inline.
DONE-WHEN: full conversation flow works with live debugging.

### interact/feat/ui-agent-sandbox
WHY: rapid prompt iteration.
WHAT: agent selector, instruction editor, tool toggle, result viewer.
DONE-WHEN: can test agent variations without code changes.

### interact/feat/debug-state-injection
WHY: modify workflow state while paused.
WHAT: editable JSON with diff preview; confirmation modal.
DONE-WHEN: modified state affects subsequent plan execution.

Value after 5-interact → developers iterate on prompts and debug state issues interactively.

────────────────────────────────────────
## 6-production – Production Ready
────────────────────────────────────────
Enterprise-grade security, monitoring, and operational controls.

**Full Details**: See [milestones/6-production/README.md](milestones/6-production/README.md)

### production/feat/temporal-controls
WHY: production workflow management.
WHAT: pause/resume signals; workflow info panel; event history browser.
DONE-WHEN: can pause and resume Temporal workflows from UI.

### production/feat/temporal-determinism
WHY: debug Temporal non-determinism.
WHAT: fetch original vs replay histories; diff algorithm; side-by-side view.
DONE-WHEN: divergence point highlighted in red.

### production/feat/security-rbac-auth
WHY: secure production deployment, prevent RCE vulnerabilities.
WHAT: Session-token auth (hardened from understand milestone), configurable CORS origin allow-list, pluggable auth providers, role-based views, audit logging.
HOW: Early session-token auth shipped in understand milestone is hardened here with proper CORS configuration.
DONE-WHEN: observer role can't modify state; CSRF attempts rejected.

### production/feat/monitoring-alerts
WHY: proactive issue detection.
WHAT: cost alerts, error rate monitoring, custom thresholds.
DONE-WHEN: alert fires when cost exceeds limit.

Value after 6-production → production-ready system with enterprise controls.

────────────────────────────────────────
## Why this sequencing maximises value
────────────────────────────────────────
• State attribute today, fancy viewer tomorrow. State JSON is tiny hook yet huge informational gain.
• Paused reason today, form tomorrow. Just knowing a workflow is paused removes confusion; actual answer form is next milestone.
• Temporal parity today. Nothing is worse than opening a new tool and seeing an empty page—unified /sessions removes that risk with <100 LOC.
• Heartbeats & context can wait without frustrating debugging.

────────────────────────────────────────
## Impact on timeline
────────────────────────────────────────
No milestones pushed back: tasks pulled into 2-observe are low-effort (~2–3 dev-days) because they piggy-back on already-touched files. Later milestones unchanged.

────────────────────────────────────────
## Cross-cutting artefacts to generate
────────────────────────────────────────
• API schema files (OpenAPI + JSON-Schema) per milestone - see [openapi.yaml](openapi.yaml)
• SpanMeta v1 schema document with truncation rules
• React component storybook for visualizer plugins
• Performance test harness (100k spans target)
• Security hardening checklist
• Contribution guide for community plugins
• Sampling policy configurations
• CI test gates:
  - Unit tests (pytest + vitest) must pass
  - Contract tests (Schemathesis) verify all schemas against [openapi.yaml](openapi.yaml)
  - E2E tests (Playwright) validate critical paths
  - Performance tests ensure <1.5s for 50k spans
  - All tests must complete in <90s total

## Future Work (Beyond 6-production)

### Sampling, Roots & Elicitation
Future enhancements may include:
- Configurable span sampling strategies
- Root span detection for distributed traces
- Elicitation UI for guided debugging sessions
- Integration with external observability platforms

## Plugin API (Future Enhancement)

The Inspector plugin system will enable community extensions without modifying core code. This section outlines the planned API for future implementation.

### Extension Points

```typescript
interface InspectorPlugin {
  id: string
  name: string
  version: string
  
  // Lifecycle hooks
  onMount?: (inspector: InspectorAPI) => void
  onUnmount?: () => void
  
  // Visualization plugins
  visualizers?: VisualizerPlugin[]
  
  // State transformers
  stateTransformers?: StateTransformer[]
  
  // Custom panels
  panels?: PanelPlugin[]
}
```

### Visualizer Plugin API

```typescript
interface VisualizerPlugin {
  // Matcher predicate
  matches: (span: Span) => boolean
  
  // React component
  component: React.ComponentType<{span: Span}>
  
  // Display metadata
  meta: {
    name: string
    icon?: string
    priority?: number  // Higher priority wins when multiple match
  }
}
```

### Example Plugin: Custom Workflow Visualizer

```typescript
// my-workflow-plugin.ts
export default {
  id: 'my-workflow-viz',
  name: 'Custom Workflow Visualizer',
  version: '1.0.0',
  
  visualizers: [{
    matches: (span) => 
      span.attributes['mcp.workflow.type'] === 'my_custom_workflow',
    
    component: MyCustomVisualizer,
    
    meta: {
      name: 'Custom Workflow',
      icon: '🎯',
      priority: 100
    }
  }]
} satisfies InspectorPlugin
```

### Registration Pattern

```typescript
// In user code
import { registerPlugin } from 'mcp_agent.inspector'
import myPlugin from './my-workflow-plugin'

registerPlugin(myPlugin)
```

### Community Plugin Guidelines

1. **Naming**: Use npm-style naming (`@org/inspector-plugin-xyz`)
2. **Dependencies**: Minimize external dependencies
3. **Performance**: Visualizers must render in <50ms
4. **Testing**: Include unit tests with plugin
5. **Documentation**: README with usage examples

────────────────────────────────────────
## How to use this roadmap
────────────────────────────────────────
1. Pick the next uncompleted task from the current milestone
2. Check milestone's PROGRESS.md for status and blockers
3. Read task's WHY → WHAT → HOW → DONE-WHEN carefully
4. Write code following all quality standards (types, tests, docs)
5. Open PR with conventional commit message including task ID
6. Update PROGRESS.md when task is completed

Example workflow:
```bash
# Check current progress
cat docs/inspector/milestones/1-bootstrap/PROGRESS.md

# Pick next task (e.g., bootstrap/feat/gateway-health-endpoint)
# Implement following the spec

# Commit with proper message
git commit -m "feat(gateway): implement health endpoint

- Add Starlette router with /_inspector prefix
- Implement /health endpoint returning version
- Add standalone server mode with Uvicorn

Task: bootstrap/feat/gateway-health-endpoint"
```

Every PR must maintain backward compatibility and zero external dependencies.

────────────────────────────────────────
## Next steps
────────────────────────────────────────
1. Complete remaining tasks in 1-bootstrap milestone
2. Update PROGRESS.md after each task completion
3. Create detailed README.md for subsequent milestones as needed
4. Maintain progress tracking discipline throughout development

Current status: See [1-bootstrap/PROGRESS.md](milestones/1-bootstrap/PROGRESS.md)