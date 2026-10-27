"""Inert authored stdio MCP: never executes commands or touches worker files."""
import sys,json
for line in sys.stdin:
    r=json.loads(line);method=r.get('method');ident=r.get('id')
    if ident is None: continue
    if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'pex-authored-only','version':'0'}}
    elif method=='tools/list': result={'tools':[{'name':'run','description':'Execute a command in the remote isolated PUBLIC workspace (authored fixture is inert).','inputSchema':{'type':'object','properties':{'command':{'type':'string'}},'required':['command'],'additionalProperties':False}}]}
    elif method=='tools/call': result={'content':[{'type':'text','text':'AUTHORED FIXTURE ONLY; command not executed'}]}
    elif method in ('resources/list','prompts/list'): result={'resources':[]} if method=='resources/list' else {'prompts':[]}
    else: result={}
    print(json.dumps({'jsonrpc':'2.0','id':ident,'result':result}),flush=True)
