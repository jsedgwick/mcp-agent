#!/usr/bin/env python3
"""
Basic MCP Agent example with Inspector enabled.

This example demonstrates how to use the Inspector with mcp-agent to gain
visibility into agent operations, tool calls, and LLM interactions.

To run this example:
1. Ensure you have API keys configured in mcp_agent.secrets.yaml or environment
2. Run: python mcp_basic_agent_with_inspector.py
3. Open http://localhost:7800/_inspector/ui in your browser
4. Watch the Inspector as the agent executes tasks
"""

import asyncio
import os
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.inspector import mount


async def example_with_inspector():
    """Run the basic agent example with Inspector enabled."""
    
    # Create the MCP app - it will load mcp_agent.config.yaml from current directory
    app = MCPApp(name="mcp_basic_agent_with_inspector")
    
    # Mount the Inspector
    # This enables the web UI at http://localhost:7800/_inspector/ui
    mount(app)
    
    print("\n=== Inspector is running at http://localhost:7800/_inspector/ui ===")
    print("Open this URL in your browser to see real-time traces and events\n")
    
    # Give the Inspector a moment to start
    await asyncio.sleep(1)
    
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context
        
        logger.info("Starting agent with Inspector enabled")
        logger.info("Current config:", data=context.config.model_dump())
        
        # Check if MCP servers are configured
        if not context.config.mcp.servers:
            logger.error("No MCP servers configured. Check your mcp_agent.config.yaml")
            return
            
        # Add the current directory to the filesystem server's args
        if "filesystem" in context.config.mcp.servers:
            context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])
        
        # Create an agent with access to filesystem and URL fetching
        finder_agent = Agent(
            name="finder",
            instruction="""You are an agent with access to the filesystem, 
            as well as the ability to fetch URLs. Your job is to identify 
            the closest match to a user's request, make the appropriate tool calls, 
            and return the URI and CONTENTS of the closest match.""",
            server_names=["fetch", "filesystem"],
        )
        
        async with finder_agent:
            logger.info("finder: Connected to server, calling list_tools...")
            result = await finder_agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())
            
            # Attach OpenAI LLM and make a request
            print("\n--- Task 1: Reading local config file with OpenAI ---")
            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(
                message="Print the contents of mcp_agent.config.yaml verbatim",
            )
            logger.info(f"mcp_agent.config.yaml contents: {result}")
            print(f"Result: {result[:200]}..." if len(result) > 200 else f"Result: {result}")
            
            # Switch to Anthropic and fetch from web
            print("\n--- Task 2: Fetching web content with Anthropic ---")
            llm = await finder_agent.attach_llm(AnthropicAugmentedLLM)
            
            result = await llm.generate_str(
                message="Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            )
            logger.info(f"First 2 paragraphs of Model Context Protocol docs: {result}")
            print(f"Result: {result[:300]}..." if len(result) > 300 else f"Result: {result}")
            
            # Multi-turn conversation with model preferences
            print("\n--- Task 3: Multi-turn conversation with model preferences ---")
            result = await llm.generate_str(
                message="Summarize those paragraphs in a 128 character tweet",
                request_params=RequestParams(
                    # Model preferences affect which model is selected
                    modelPreferences=ModelPreferences(
                        costPriority=0.1, 
                        speedPriority=0.2, 
                        intelligencePriority=0.7
                    ),
                ),
            )
            logger.info(f"Paragraph as a tweet: {result}")
            print(f"Tweet: {result}")
            
            print("\n--- All tasks completed! ---")
            print("\nCheck the Inspector UI to see:")
            print("- The workflow execution tree")
            print("- Tool calls and their inputs/outputs")
            print("- LLM prompts and responses")
            print("- Model selection preferences")
            print("- Token usage and costs")
            
            # Keep the script running for 30 seconds to allow exploration
            print("\n" + "="*60)
            logger.info("Workflow complete. Inspector UI is available for review.")
            logger.info(f"Visit: http://localhost:7800/_inspector/ui")
            logger.info("The script will exit in 30 seconds...")
            print("="*60)
            
            await asyncio.sleep(30)


if __name__ == "__main__":
    print("=== MCP Basic Agent with Inspector Demo ===")
    print("\nThis demo shows how Inspector provides visibility into:")
    print("- Agent workflows and tool calls")
    print("- LLM interactions and model selection")
    print("- Real-time event streaming")
    
    start = time.time()
    asyncio.run(example_with_inspector())
    end = time.time()
    t = end - start
    
    print(f"\n\nTotal run time: {t:.2f}s")