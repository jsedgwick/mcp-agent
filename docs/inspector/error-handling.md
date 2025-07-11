# Error Handling & Resilience

This document describes how mcp-agent-inspector handles errors and maintains reliability without external dependencies.

## Core Principles

1. **Graceful Degradation**: Always provide partial functionality rather than complete failure
2. **No Data Loss**: Preserve trace data even during failures  
3. **Clear User Feedback**: Surface issues without interrupting workflows
4. **Self-Healing**: Automatic recovery when conditions improve

## Common Issues & Solutions

### 1. Disk Space Issues

**Problem**: "No space left on device"

**Solution**:
- FileSpanExporter automatically switches to NullExporter
- Emits `DiskSpaceLow` event via AsyncEventBus
- UI displays warning banner to alert users
- Resumes normal operation when space is available

### 2. Corrupted Trace Files

**Problem**: "Trace file corrupted" or malformed JSON

**Solution**:
```python
try:
    with gzip.open(trace_file) as f:
        # ... read spans
except Exception:
    logger.warning(f"Skipping corrupted trace: {trace_file}")
    # Move to .bad file for debugging
    os.rename(trace_file, f"{trace_file}.bad")
    continue
```

### 3. File Handle Limits

**Problem**: "Too many open files"

**Solution**:
- LRU cache for file handles (max 50)
- Automatic handle recycling
- Falls back to open/close per write if needed

### 4. Multiple Inspector Instances

**Problem**: Multiple processes trying to write traces

**Solution**:
- File lock on `~/.mcp_traces/.inspector.lock`
- Second instance automatically disables its exporter
- Only first instance writes traces
- Other instances can still read

### 5. Network Issues (SSE)

**Problem**: "SSE connection lost"

**Solution**:
- Auto-reconnect with exponential backoff (0.25s → 5s max)
- Ring buffer maintains last 1000 events
- Replays missed events on reconnect
- UI shows "Reconnecting..." status

### 6. Temporal Service Unavailable (affects /sessions)

If the gateway fails to contact Temporal the HTTP status remains **200**.
The JSON response includes:

```jsonc
{
  "sessions": [ /* asyncio sessions only */ ],
  "temporal_error": "dial tcp 10.0.0.12:7233: i/o timeout"
}
```

Frontend shows a non-blocking yellow banner ("Temporal unreachable – showing local sessions only"). This implements the project-wide Graceful Degradation rule.

## Resource Management

### File Rotation
- Trace files rotate at 100MB
- Format: `{session_id}_chunk_{n}.jsonl.gz`
- Old chunks remain readable
- No data loss during rotation

### Memory Limits
- Streaming for large traces (1MB chunks)
- Virtual scrolling in UI for >500 items
- Web Workers for background parsing
- Target: <150MB for 100k spans

### Permission Issues
- Falls back to temp directory if `~/.mcp_traces` not writable
- Creates directories with 0755 permissions
- Handles cross-platform path differences

## Error Reporting

### Logging Levels
```python
# Debug: Detailed trace information
logger.debug(f"Writing span to {trace_file}")

# Warning: Recoverable issues
logger.warning(f"Trace file corrupted, moving to .bad: {trace_file}")

# Error: Failures that affect functionality
logger.error(f"Cannot create trace directory: {e}")
```

### User Notifications
- Banner alerts for critical issues (disk space, permissions)
- Toast notifications for transient errors
- Status indicators for degraded functionality
- Clear action items when user intervention needed

## Testing Error Scenarios

### Simulating Failures
```bash
# Test disk full
dd if=/dev/zero of=/tmp/bigfile bs=1M count=$(($(df / | tail -1 | awk '{print $4}') / 1024 - 100))

# Test file corruption  
echo "invalid json" >> ~/.mcp_traces/session.jsonl.gz

# Test permission issues
chmod 000 ~/.mcp_traces

# Test multiple instances
python script1.py & python script2.py
```

### Debug Mode
```bash
INSPECTOR_DEBUG=1 python my_script.py
# Enables verbose error logging
# Shows recovery attempts
# Validates all data schemas
```

## Related Documentation

- [Architecture](architecture.md#zero-dependency-design) - How zero-dependency design enables resilience
- [Development](development.md#debugging-inspector) - Debugging techniques  
- [Telemetry Spec](telemetry-spec.md#size-limits-and-truncation) - Data size constraints
- [Roadmap](roadmap.md) - Implementation milestones for error handling features

## Error Codes Reference

| Code | Description | Recovery Action |
|------|-------------|-----------------|
| INSP-001 | Disk space low | Switch to NullExporter |
| INSP-002 | Trace corrupted | Move to .bad file |
| INSP-003 | Too many handles | Use LRU cache |
| INSP-004 | Lock exists | Disable exporter |
| INSP-005 | SSE disconnected | Auto-reconnect |