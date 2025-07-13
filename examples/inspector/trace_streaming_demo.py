#!/usr/bin/env python3
"""
Demonstration of the Inspector trace streaming endpoint.

This example shows how the trace streaming endpoint works with:
- Full file downloads (gzipped)
- HTTP Range requests (decompressed)
- ETag caching
"""

import asyncio
import gzip
import json
import os
from pathlib import Path

import aiohttp
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.inspector import mount


async def demo_trace_streaming():
    """Demonstrate trace streaming functionality."""
    
    # Create the MCP app
    app = MCPApp(name="trace_streaming_demo")
    
    # Mount the Inspector
    mount(app)
    
    print("=== Inspector Trace Streaming Demo ===")
    print("Inspector is running at http://localhost:7800/_inspector/ui")
    print()
    
    # Give Inspector a moment to start
    await asyncio.sleep(1)
    
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context
        
        # Get the session ID for later API calls
        session_id = context.session_id
        print(f"Session ID: {session_id}")
        print()
        
        # Create a simple agent and perform a task to generate traces
        agent = Agent(
            name="demo_agent",
            instruction="You are a helpful assistant.",
            server_names=[]
        )
        
        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(
                message="Say 'Hello, trace streaming!' in a creative way."
            )
            print(f"Agent response: {result}")
        
        print("\n=== Demonstrating Trace Streaming API ===\n")
        
        # Wait a moment for traces to be written
        await asyncio.sleep(1)
        
        # Now demonstrate the trace streaming API
        async with aiohttp.ClientSession() as session:
            base_url = "http://localhost:7800/_inspector"
            
            # 1. Download full trace file (gzipped)
            print("1. Downloading full trace file...")
            async with session.get(f"{base_url}/trace/{session_id}") as resp:
                if resp.status == 200:
                    print(f"   Status: {resp.status}")
                    print(f"   Content-Type: {resp.headers.get('Content-Type')}")
                    print(f"   Content-Encoding: {resp.headers.get('Content-Encoding')}")
                    print(f"   ETag: {resp.headers.get('ETag')}")
                    
                    # Read and decompress
                    content = await resp.read()
                    if resp.headers.get('Content-Encoding') == 'gzip':
                        # Manual decompression if needed
                        try:
                            decompressed = gzip.decompress(content)
                        except:
                            # TestClient might have already decompressed
                            decompressed = content
                    else:
                        decompressed = content
                    
                    lines = decompressed.decode().strip().split('\n')
                    print(f"   Total spans: {len(lines)}")
                    
                    # Show first span
                    if lines:
                        first_span = json.loads(lines[0])
                        print(f"   First span: {first_span.get('name')}")
                    
                    etag = resp.headers.get('ETag')
                else:
                    print(f"   Failed: {resp.status}")
                    etag = None
            
            print()
            
            # 2. Test ETag caching
            if etag:
                print("2. Testing ETag caching...")
                headers = {"If-None-Match": etag}
                async with session.get(f"{base_url}/trace/{session_id}", headers=headers) as resp:
                    print(f"   Status: {resp.status}")
                    if resp.status == 304:
                        print("   ✓ Not Modified - ETag cache working!")
            
            print()
            
            # 3. Test Range request
            print("3. Testing Range request (first 100 bytes)...")
            headers = {"Range": "bytes=0-99"}
            async with session.get(f"{base_url}/trace/{session_id}", headers=headers) as resp:
                print(f"   Status: {resp.status}")
                if resp.status == 206:
                    print("   ✓ Partial Content")
                    print(f"   Content-Range: {resp.headers.get('Content-Range')}")
                    content = await resp.read()
                    print(f"   Received {len(content)} bytes")
                    print(f"   Preview: {content.decode()[:50]}...")
            
            print()
            
            # 4. Test invalid session ID
            print("4. Testing invalid session ID...")
            async with session.get(f"{base_url}/trace/invalid..session") as resp:
                print(f"   Status: {resp.status}")
                if resp.status == 400:
                    error = await resp.json()
                    print(f"   ✓ Validation working: {error['detail']}")
        
        print("\n=== Demo Complete ===")
        print("The trace file can be found at:")
        print(f"  ~/.mcp_traces/{session_id}.jsonl.gz")


if __name__ == "__main__":
    print("Starting trace streaming demo...")
    asyncio.run(demo_trace_streaming())