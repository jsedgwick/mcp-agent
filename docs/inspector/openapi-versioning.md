# OpenAPI Versioning Guide

This guide explains how to manage versions of the Inspector HTTP API documented in `docs/inspector/openapi.yaml`.

## Version Management Process

1. **When to Update Version**
   - When adding new endpoints
   - When modifying existing endpoint schemas
   - When changing response formats
   - When adding/removing required fields

2. **How to Update**
   ```yaml
   info:
     version: "0.2.0"  # Increment according to semver
   ```

3. **Changelog Entry**
   When updating the OpenAPI spec version, add an entry to the project CHANGELOG (when created):
   ```markdown
   ## [0.2.0] - 2025-07-XX
   ### Added
   - New /signal/{session_id} endpoint for workflow control
   ### Changed
   - Updated SessionMeta schema to include engine field
   ```

4. **Frontend Type Generation**
   After updating the OpenAPI spec:
   ```bash
   cd packages/inspector_ui
   pnpm run gen:schemas
   ```

5. **Contract Testing**
   All changes are validated automatically via CI:
   ```bash
   schemathesis run docs/inspector/openapi.yaml --checks all
   ```

## Version Compatibility

- The Inspector frontend includes the API version in its requests
- The backend validates version compatibility
- Breaking changes require a major version bump (1.0.0 → 2.0.0)

## Cross-References

- API endpoints are tested in `tests/contracts/`
- Frontend types are generated to `packages/inspector_ui/src/generated/api.ts`
- Contract tests run automatically in CI via `.github/workflows/checks.yml`