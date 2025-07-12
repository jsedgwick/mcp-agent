#!/usr/bin/env python3
"""Demo script showing session listing and event streaming endpoints."""

import asyncio
import json
import os
from pathlib import Path

import aiohttp

from mcp_agent.inspector import mount
from mcp_agent.inspector.events import SessionStarted, WaitingOnSignal, SessionFinished, get_event_stream


async def demo_sessions():
    """Demo the session listing functionality."""
    print("=== Session Listing Demo ===\n")
    
    # Create a demo trace file to show up in sessions
    trace_dir = Path(os.path.expanduser("~/.mcp_traces"))
    trace_dir.mkdir(exist_ok=True)
    
    # Note: In real usage, traces would be created by the FileSpanExporter
    # This is just for demo purposes
    
    async with aiohttp.ClientSession() as session:
        # List sessions
        async with session.get("http://localhost:7800/_inspector/sessions") as resp:
            data = await resp.json()
            print(f"Found {len(data['sessions'])} sessions:")
            for sess in data['sessions']:
                print(f"  - {sess['id']}: {sess['status']} ({sess['engine']})")
                print(f"    Started: {sess['started_at']}")
                if sess.get('ended_at'):
                    print(f"    Ended: {sess['ended_at']}")
                print()


async def demo_events():
    """Demo the event streaming functionality."""
    print("\n=== Event Streaming Demo ===\n")
    print("Publishing some events...\n")
    
    # Get the event stream and publish some demo events
    stream = await get_event_stream()
    
    # Simulate a workflow starting
    event1 = SessionStarted("demo-session-1", "asyncio", "Demo Workflow")
    await stream.publish_event(event1.to_dict())
    print(f"Published: {event1.to_dict()}")
    
    await asyncio.sleep(0.5)
    
    # Simulate waiting for input
    event2 = WaitingOnSignal("demo-session-1", "human_input", "Please enter your name")
    await stream.publish_event(event2.to_dict())
    print(f"Published: {event2.to_dict()}")
    
    await asyncio.sleep(0.5)
    
    # Simulate completion
    event3 = SessionFinished("demo-session-1", "completed")
    await stream.publish_event(event3.to_dict())
    print(f"Published: {event3.to_dict()}")
    
    print("\nYou can connect to http://localhost:7800/_inspector/events to see the event stream")
    print("Example: curl -N http://localhost:7800/_inspector/events")


async def listen_to_events():
    """Connect to the event stream and print events."""
    print("\n=== Listening to Event Stream ===\n")
    print("Connecting to SSE stream...")
    
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:7800/_inspector/events") as resp:
            async for line in resp.content:
                line = line.decode('utf-8').strip()
                if line.startswith('data: '):
                    event_data = json.loads(line[6:])
                    print(f"Received event: {event_data}")


async def main():
    """Run the demo."""
    # Start the inspector in standalone mode
    mount()
    
    # Give the server a moment to start
    await asyncio.sleep(1)
    
    print("Inspector is running at http://localhost:7800/_inspector/ui\n")
    
    # Run the demos
    await demo_sessions()
    await demo_events()
    
    print("\nPress Ctrl+C to stop the demo")
    
    # Keep running to allow manual testing
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nDemo stopped")


if __name__ == "__main__":
    asyncio.run(main())