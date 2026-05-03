from ipl_agent import agent
r = agent.root_agent
print('root_agent type:', type(r))
print('\navailable attributes/methods:')
for m in dir(r):
    if not m.startswith('_'):
        print(m)
