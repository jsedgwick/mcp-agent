#!/usr/bin/env python3
"""Demo showing session listing and event streaming functionality (2-observe milestone).

This demo demonstrates the core observability features from the 2-observe milestone:
1. Creating sample trace files
2. Starting the Inspector server
3. Listing sessions via the /sessions endpoint
4. Publishing and streaming real-time events via SSE
5. Examples of connecting to the event stream
"""

import asyncio
import gzip
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

from mcp_agent.inspector import mount
from mcp_agent.inspector.events import (
    SessionStarted,
    WaitingOnSignal,
    SessionFinished,
    Heartbeat,
    get_event_stream,
)


def create_demo_trace_files():
    """Create sample trace files to demonstrate session listing."""
    trace_dir = Path(os.path.expanduser("~/.mcp_traces"))
    trace_dir.mkdir(exist_ok=True)

    print("=== Creating Demo Trace Files ===\n")

    # Demo 1: Completed orchestrator workflow
    session1_id = "orchestrator-demo-001"
    now = datetime.utcnow()
    spans1 = [
        {
            "span_id": "span-1",
            "trace_id": "trace-1",
            "name": "workflow.run",
            "start_time": (now - timedelta(hours=2)).isoformat() + "Z",
            "end_time": (now - timedelta(hours=2) + timedelta(minutes=5)).isoformat() + "Z",
            "attributes": {
                "mcp.workflow.type": "orchestrator",
                "mcp.session.title": "Data Processing Pipeline",
                "mcp.workflow.input_json": json.dumps({"task": "process_data", "files": 150}),
                "mcp.workflow.output_json": json.dumps({"processed": 150, "errors": 0}),
            },
            "status": {"status_code": "OK"},
        },
        {
            "span_id": "span-2",
            "trace_id": "trace-1",
            "parent_span_id": "span-1",
            "name": "agent.call",
            "start_time": (now - timedelta(hours=2)).isoformat() + "Z",
            "attributes": {
                "mcp.agent.name": "DataProcessor",
                "mcp.agent.class": "ProcessorAgent",
            },
        },
        {
            "span_id": "span-3",
            "trace_id": "trace-1",
            "parent_span_id": "span-2",
            "name": "tool.call",
            "start_time": (now - timedelta(hours=2)).isoformat() + "Z",
            "attributes": {
                "mcp.tool.name": "read_csv",
                "mcp.tool.input_json": json.dumps({"file": "data.csv"}),
                "mcp.tool.output_json": json.dumps({"rows": 1000}),
            },
        },
    ]

    trace_path1 = trace_dir / f"{session1_id}.jsonl.gz"
    with gzip.open(trace_path1, "wt") as f:
        for span in spans1:
            f.write(json.dumps(span) + "\n")
    print(f"Created trace: {session1_id} (completed orchestrator workflow)")

    # Demo 2: Failed workflow
    session2_id = "failed-workflow-002"
    spans2 = [
        {
            "span_id": "span-4",
            "trace_id": "trace-2",
            "name": "workflow.run",
            "start_time": (now - timedelta(hours=1)).isoformat() + "Z",
            "end_time": (now - timedelta(hours=1) + timedelta(minutes=2)).isoformat() + "Z",
            "attributes": {
                "mcp.workflow.type": "router",
                "mcp.session.title": "API Request Router",
                "mcp.error.message": "Connection timeout to backend service",
            },
            "status": {"status_code": "ERROR", "message": "Backend unavailable"},
        }
    ]

    trace_path2 = trace_dir / f"{session2_id}.jsonl.gz"
    with gzip.open(trace_path2, "wt") as f:
        for span in spans2:
            f.write(json.dumps(span) + "\n")
    print(f"Created trace: {session2_id} (failed router workflow)")

    # Demo 3: Currently paused workflow
    session3_id = "paused-input-003"
    spans3 = [
        {
            "span_id": "span-5",
            "trace_id": "trace-3",
            "name": "workflow.run",
            "start_time": (now - timedelta(minutes=30)).isoformat() + "Z",
            "end_time": (now - timedelta(minutes=28)).isoformat() + "Z",
            "attributes": {
                "mcp.workflow.type": "evaluator",
                "mcp.session.title": "Code Review Assistant",
                "mcp.session.paused": True,
                "mcp.workflow.pause_reason": "Waiting for human approval",
            },
            "status": {"status_code": "OK"},
        },
        {
            "span_id": "span-6",
            "trace_id": "trace-3",
            "parent_span_id": "span-5",
            "name": "llm.generate",
            "start_time": (now - timedelta(minutes=29)).isoformat() + "Z",
            "end_time": (now - timedelta(minutes=28)).isoformat() + "Z",
            "attributes": {
                "mcp.llm.provider": "anthropic",
                "mcp.llm.model": "claude-3-opus-20240229",
                "mcp.llm.prompt_json": json.dumps(
                    [
                        {"role": "system", "content": "You are a code reviewer."},
                        {"role": "user", "content": "Review this Python code for security issues..."},
                    ]
                ),
                "mcp.llm.response_json": json.dumps(
                    {"content": "I found 3 potential security issues...", "usage": {"total_tokens": 1500}}
                ),
            },
        },
    ]

    trace_path3 = trace_dir / f"{session3_id}.jsonl.gz"
    with gzip.open(trace_path3, "wt") as f:
        for span in spans3:
            f.write(json.dumps(span) + "\n")
    print(f"Created trace: {session3_id} (paused evaluator workflow)")

    print(f"\nTrace files created in: {trace_dir}")
    return [session1_id, session2_id, session3_id]


async def demo_session_listing():
    """Demonstrate session listing via the API."""
    print("\n=== Session Listing Demo ===\n")

    async with aiohttp.ClientSession() as session:
        # List sessions
        async with session.get("http://localhost:7800/_inspector/sessions") as resp:
            data = await resp.json()
            print(f"API Response: {json.dumps(data, indent=2)}\n")

            print(f"Found {len(data['sessions'])} sessions:\n")
            for sess in data["sessions"]:
                status_marker = "[COMPLETED]" if sess["status"] == "completed" else f"[{sess['status'].upper()}]"

                print(f"{status_marker} {sess['id']}")
                print(f"   Status: {sess['status']}")
                print(f"   Engine: {sess['engine']}")
                print(f"   Title: {sess['title']}")
                print(f"   Started: {sess['started_at']}")
                if sess.get("ended_at"):
                    print(f"   Ended: {sess['ended_at']}")
                print()


async def demo_live_events():
    """Demonstrate real-time event streaming."""
    print("\n=== Live Event Streaming Demo ===\n")

    # Get the event stream
    stream = await get_event_stream()

    # Simulate a new workflow starting
    print("Simulating a live workflow...\n")

    # Workflow starts
    event1 = SessionStarted("live-demo-004", "temporal", "Order Processing Workflow")
    await stream.publish_event(event1.to_dict())
    print("Published: SessionStarted")
    print(f"   {json.dumps(event1.to_dict(), indent=2)}\n")

    await asyncio.sleep(1)

    # Send heartbeat
    event2 = Heartbeat("live-demo-004", llm_calls_delta=3, tokens_delta=1250)
    await stream.publish_event(event2.to_dict())
    print("Published: Heartbeat")
    print(f"   {json.dumps(event2.to_dict(), indent=2)}\n")

    await asyncio.sleep(1)

    # Workflow pauses for input
    event3 = WaitingOnSignal(
        "live-demo-004",
        "human_input",
        "Please approve order 12345 for 1299.99",
        {"type": "object", "properties": {"approved": {"type": "boolean"}}},
    )
    await stream.publish_event(event3.to_dict())
    print("Published: WaitingOnSignal")
    print(f"   {json.dumps(event3.to_dict(), indent=2)}\n")

    await asyncio.sleep(1)

    # Workflow completes
    event4 = SessionFinished("live-demo-004", "completed")
    await stream.publish_event(event4.to_dict())
    print("Published: SessionFinished")
    print(f"   {json.dumps(event4.to_dict(), indent=2)}\n")


async def show_connection_examples():
    """Show how to connect to the event stream."""
    print("\n=== How to Connect to Event Stream ===\n")
    print("You can connect to the live event stream using curl:")
    print("  curl -N http://localhost:7800/_inspector/events\n")
    print("Or in Python:")
    print(
        """
import aiohttp
import asyncio
import json

async def listen():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:7800/_inspector/events") as resp:
            async for line in resp.content:
                line = line.decode('utf-8').strip()
                if line.startswith('data: '):
                    print(json.loads(line[6:]))

asyncio.run(listen())
"""
    )


async def main():
    """Run the 2-observe milestone demo."""
    # Create demo trace files
    session_ids = create_demo_trace_files()

    # Start the inspector
    print("\n=== Starting Inspector ===\n")
    mount()
    await asyncio.sleep(1)

    print("Inspector is running at http://localhost:7800/_inspector/ui")
    print("Health check: http://localhost:7800/_inspector/health")
    print("Sessions API: http://localhost:7800/_inspector/sessions")
    print("Events SSE: http://localhost:7800/_inspector/events\n")

    # Run demos
    await demo_session_listing()
    await demo_live_events()
    await show_connection_examples()

    print("\n=== Demo Complete ===")
    print("\nThe Inspector is still running. You can:")
    print("1. Visit http://localhost:7800/_inspector/sessions in your browser")
    print("2. Run: curl -N http://localhost:7800/_inspector/events")
    print("3. Check the trace files in ~/.mcp_traces/")
    print("\nPress Ctrl+C to stop the Inspector")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nInspector stopped")


if __name__ == "__main__":
    asyncio.run(main())