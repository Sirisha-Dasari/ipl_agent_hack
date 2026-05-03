#!/usr/bin/env python3
"""Find InvocationContext import."""

try:
    from google.adk.context import InvocationContext
    print("✓ Found at: google.adk.context.InvocationContext")
except ImportError as e:
    print(f"✗ Not at google.adk.context: {e}")

try:
    from google.adk.agents import InvocationContext
    print("✓ Found at: google.adk.agents.InvocationContext")
except ImportError as e:
    print(f"✗ Not at google.adk.agents: {e}")

try:
    from google.adk.agents.context import InvocationContext
    print("✓ Found at: google.adk.agents.context.InvocationContext")
except ImportError as e:
    print(f"✗ Not at google.adk.agents.context: {e}")

try:
    from google.adk.agents.base_agent import InvocationContext
    print("✓ Found at: google.adk.agents.base_agent.InvocationContext")
except ImportError as e:
    print(f"✗ Not at google.adk.agents.base_agent: {e}")

# Try to find it from an agent instance
print("\n--- Checking agent attributes ---")
from ipl_agent.agent import root_agent
print("Agent type:", type(root_agent))

import inspect
frame = inspect.signature(root_agent.run_async)
print("run_async signature:", frame)
print("run_async annotations:")
for param_name, param in frame.parameters.items():
    print(f"  {param_name}: {param.annotation}")
