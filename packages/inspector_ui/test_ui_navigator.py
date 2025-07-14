#!/usr/bin/env python3
"""Test script to verify UI Session Navigator is working."""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from mcp_agent.app import MCPApp
from mcp_agent.inspector import mount
from mcp_agent.executor.workflow import Workflow, WorkflowResult

# Create test app
app = MCPApp(name="UINavigatorTest")

# Simple test workflow
@app.workflow
class TestWorkflow(Workflow):
    @app.workflow_run
    async def run(self, message: str) -> WorkflowResult[str]:
        """Test workflow for UI verification."""
        print(f"[WORKFLOW] Processing: {message}")
        
        # Simulate some work with pauses
        await asyncio.sleep(1)
        print("[WORKFLOW] Step 1 complete")
        
        await asyncio.sleep(1)
        print("[WORKFLOW] Step 2 complete")
        
        result = f"Completed: {message}"
        print(f"[WORKFLOW] Result: {result}")
        
        return WorkflowResult(value=result)


async def main():
    """Run test workflows and keep server running."""
    # Enable Inspector via environment variable
    os.environ["INSPECTOR_ENABLED"] = "true"
    
    # Mount inspector
    mount(app)
    print("\n✅ Inspector mounted at http://localhost:7800/_inspector/ui")
    print("\n📱 UI Dev Server should be running at http://localhost:5173/_inspector/ui/")
    
    async with app.run() as agent_app:
        print("\n🚀 Starting test workflows...")
        
        # Create workflow instances
        workflows = []
        
        # Create multiple workflows to test session list
        for i in range(3):
            workflow = await TestWorkflow.create(
                name=f"test_workflow_{i}",
                context=agent_app.context
            )
            
            print(f"\n➡️  Starting workflow {i+1}/3...")
            execution = await workflow.run_async(f"Test message {i+1}")
            workflows.append(execution)
            
            # Stagger the starts
            await asyncio.sleep(2)
        
        print("\n✅ All workflows started!")
        print("\n📊 Check the Inspector UI to see:")
        print("   - 3 running sessions in the session list")
        print("   - Real-time updates via SSE")
        print("   - Span tree when clicking a session")
        print("   - Inspector tabs with attributes")
        
        print("\n⌛ Keeping server running... Press Ctrl+C to stop")
        
        try:
            # Keep running
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")