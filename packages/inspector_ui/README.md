# Inspector UI

The React-based frontend for mcp-agent-inspector.

## Development

```bash
# Install dependencies
pnpm install

# Start development server
pnpm run dev

# Build for production
pnpm run build

# Generate TypeScript types from OpenAPI schema
pnpm run gen:schemas
```

## Architecture

This is a Vite + React + TypeScript project that provides the web UI for the Inspector.

Key features:
- Displays live sessions and workflow status
- Shows OpenTelemetry spans and attributes
- Provides real-time updates via Server-Sent Events (SSE)
- Visualizes workflow execution with custom plugins

## Building

The UI is built to `dist/` and served by the Inspector gateway at `/_inspector/ui/`.

## Testing

The UI is tested with:
- Unit tests (vitest)
- E2E tests (Playwright)
- Visual regression tests (Chromatic)

## Standalone Usage

To run the Inspector UI with a standalone server:

```bash
# From the project root
python examples/test_inspector_ui.py

# Then open http://localhost:7800/_inspector/ui/
```
