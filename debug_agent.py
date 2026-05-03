#!/usr/bin/env python3
"""Debug script to inspect the actual Agent object structure"""

from ipl_agent.agent import root_agent

if root_agent is None:
    print("❌ root_agent is None")
else:
    print(f"Agent type: {type(root_agent)}")
    print(f"Agent class: {root_agent.__class__.__name__}")
    print(f"\nAll attributes (including private):")
    for attr in sorted(dir(root_agent)):
        try:
            val = getattr(root_agent, attr)
            if callable(val):
                print(f"  {attr}() - method")
            else:
                print(f"  {attr} - {type(val).__name__}")
        except:
            print(f"  {attr} - <inaccessible>")
