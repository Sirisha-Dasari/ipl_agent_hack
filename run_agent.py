#!/usr/bin/env python3
"""
IPL ADK Agent Runner - Multi-step agentic reasoning with Google Search + Tool Trace
Run this to query the IPL agent with full tracing enabled.
"""

import sys
import asyncio
from typing import TYPE_CHECKING
from ipl_agent.agent import root_agent, ADK_AVAILABLE

# Import the InvocationContext from google-adk (optional at runtime)
if TYPE_CHECKING:
    # For static type checkers only; avoid runtime import errors in editors
    from google.adk.agents import InvocationContext  # type: ignore

try:
    from google.adk.agents import InvocationContext  # type: ignore[import]
except Exception:
    InvocationContext = None

async def run_agent_query(query: str):
    """Run IPL agent query with tracing."""
    if not ADK_AVAILABLE:
        print("⚠️  Google ADK is not installed.")
        print("Install with: pip install google-adk")
        return
    
    if root_agent is None:
        print("❌ Agent initialization failed")
        return
    
    if InvocationContext is None:
        print("❌ Could not import InvocationContext from google-adk")
        return
    
    print(f"🏏 IPL Agent Query: {query}")
    print("━" * 60)
    
    try:
        # Create an InvocationContext with the query as content
        context = InvocationContext(contents=query)
        
        # Use run_async() with the context
        # It returns an async generator of Events
        print("\n✅ Agent Response:")
        print("─" * 60)
        
        full_response = ""
        async for event in root_agent.run_async(context):
            # Extract text from the event
            event_text = str(event)
            if event_text:
                print(event_text, end="", flush=True)
                full_response += event_text
        
        print("\n" + "─" * 60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "What's the latest IPL match status? Give me a full analysis with win probability and strategy."
    
    if ADK_AVAILABLE:
        asyncio.run(run_agent_query(query))
    else:
        print("❌ Google ADK not available. Install with:")
        print("   pip install google-adk")
        print("\nAlternatively, use the FastAPI dashboard at http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
