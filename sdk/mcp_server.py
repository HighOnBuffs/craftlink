"""CraftLink stdio MCP facade. Set CRAFTLINK_ADDRESS and CRAFTLINK_TOKEN privately."""
import json,os,sys
from craftlink import Client,CraftLinkError

METHODS=['register_application','negotiate_capabilities','applications','enumerate_objects','search_assets','resolve_link','begin_transaction','apply_changes','commit_transaction','rollback_transaction','create_link','dependencies','undo','redo','conflicts','bind_native','place_link','reconnect','native_changed','bindings','detach','freeze','open_in_source_application','resolve_conflict','subscribe_to_changes']

def main():
    client=Client(os.environ['CRAFTLINK_ADDRESS'],os.environ['CRAFTLINK_TOKEN'])
    for line in iter(lambda:sys.stdin.buffer.readline(1024*1024+1),b''):
        if len(line)>1024*1024:raise ValueError('MCP frame exceeds 1 MiB')
        req={}
        try:
            req=json.loads(line);method=req.get('method');params=req.get('params',{})
            if 'id' not in req:continue
            if method=='initialize':
                result=dict(protocolVersion='2025-06-18',capabilities=dict(tools={}),serverInfo=dict(name='craftlink',version='0.1.0'),instructions='Local candidate. Semantic name/opacity native links only. Saves trigger propagation. Committed broker state and asynchronous UI projection are separate.')
            elif method=='ping':result={}
            elif method=='tools/list':
                result=dict(tools=[dict(name='craftlink',description='Operate the authenticated local CraftLink project; guarded revisions required for edits. Inspect bindings/conflicts after a commit.',inputSchema=dict(type='object',properties=dict(method=dict(type='string',enum=METHODS),params=dict(type='object')),required=['method'],additionalProperties=False))])
            elif method=='tools/call' and params.get('name')=='craftlink':
                args=params.get('arguments',{})
                if args.get('method') not in METHODS:raise ValueError('unknown CraftLink method')
                try:
                    response=client.request(args['method'],args.get('params',{}))
                    result=dict(content=[dict(type='text',text=json.dumps(response))],isError=False)
                except CraftLinkError as error:
                    result=dict(content=[dict(type='text',text=json.dumps(error.response))],isError=True)
            else:
                print(json.dumps(dict(jsonrpc='2.0',id=req.get('id'),error=dict(code=-32601,message='Unknown method or tool'))),flush=True);continue
            print(json.dumps(dict(jsonrpc='2.0',id=req.get('id'),result=result)),flush=True)
        except (ValueError,KeyError,TypeError) as error:
            print(json.dumps(dict(jsonrpc='2.0',id=req.get('id') if isinstance(req,dict) else None,error=dict(code=-32602,message=str(error)))),flush=True)

if __name__=='__main__':main()
