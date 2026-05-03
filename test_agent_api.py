#!/usr/bin/env python3
"""Test agent invocation methods."""

from ipl_agent.agent import root_agent
import inspect

print("Agent Type:", type(root_agent))
print("\n" + "="*60)
print("run_async signature:")
print(inspect.signature(root_agent.run_async))

print("\n" + "="*60)
print("run_live signature:")
print(inspect.signature(root_agent.run_live))

print("\n" + "="*60)
print("Checking for other methods...")
for name in dir(root_agent):
    if callable(getattr(root_agent, name)) and not name.startswith('_'):
        try:
            sig = inspect.signature(getattr(root_agent, name))
            print(f"{name}: {sig}")
        except:
            pass
