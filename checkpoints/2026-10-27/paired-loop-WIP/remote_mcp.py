"""Private stdio MCP to controller-owned remote VM operations only.

No exec/eval/shell/filesystem tool implementation exists on this host. The RPC
owner holds the already-admitted E2B RemoteWorker; no keys cross this socket.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import socket
import socketserver
import sys
import threading

MAX=1024*1024
SCHEMAS={
    "run": {"command":{"type":"string","maxLength":16384}},
    "read": {"path":{"type":"string","maxLength":512}},
    "write": {"path":{"type":"string","maxLength":512},"text":{"type":"string","maxLength":262144}},
    "list": {"path":{"type":"string","maxLength":512}},
}
DESCRIPTIONS={"run":"Run shell command ONLY in the isolated remote PUBLIC task workspace.",
              "read":"Read a PUBLIC task file in the isolated remote workspace.",
              "write":"Write a PUBLIC task file in the isolated remote workspace.",
              "list":"List a PUBLIC task directory in the isolated remote workspace."}


def checked(method,args):
    if method not in SCHEMAS or type(args) is not dict or set(args)!=set(SCHEMAS[method]):
        raise ValueError("invalid_remote_tool_arguments")
    for k,definition in SCHEMAS[method].items():
        if type(args[k]) is not str or len(args[k].encode())>definition["maxLength"] or '\0' in args[k]:
            raise ValueError("invalid_remote_tool_text")
    return args


@contextlib.contextmanager
def serve_remote(remote, private_dir):
    directory=Path(private_dir)
    directory.mkdir(mode=0o700,parents=False,exist_ok=False)
    path=directory/'remote.sock'
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                line=self.rfile.readline(MAX+1)
                if len(line)>MAX: raise ValueError("rpc_bound")
                obj=json.loads(line)
                if type(obj) is not dict or set(obj)!={"method","arguments"}: raise ValueError("rpc_shape")
                method=obj['method'];args=checked(method,obj['arguments'])
                with self.server.serial:
                    if self.server.revoked: raise ValueError("worker_tool_access_revoked")
                    result=getattr(remote,method)(**args)
                reply={"result":result}
            except Exception as error:
                reply={"error":type(error).__name__} # never secret-bearing error text
            raw=json.dumps(reply,ensure_ascii=False).encode()+b'\n'
            if len(raw)>MAX: raw=b'{"error":"remote_output_bound"}\n'
            self.wfile.write(raw)
    server=socketserver.ThreadingUnixStreamServer(str(path),Handler)
    server.daemon_threads=True;server.serial=threading.Lock();server.revoked=False
    os.chmod(path,0o600)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield path
    finally:
        with server.serial: server.revoked=True
        server.shutdown();server.server_close();thread.join()
        path.unlink(missing_ok=True)
        directory.rmdir()


def rpc(path,method,args):
    checked(method,args)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(90)
        s.connect(str(path))
        s.sendall(json.dumps({"method":method,"arguments":args}).encode()+b'\n')
        with s.makefile('rb') as f: raw=f.readline(MAX+1)
    if not raw or len(raw)>MAX: raise ValueError('rpc_response_bound')
    return json.loads(raw)


def stdio(path):
    for raw in iter(lambda:sys.stdin.buffer.readline(MAX+1),b''):
        if len(raw)>MAX: raise ValueError('mcp_input_bound')
        req=json.loads(raw)
        if req.get('id') is None: continue
        method=req.get('method');params=req.get('params',{})
        try:
            if method=='initialize':
                result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'pex-isolated-worker','version':'0.1-wip'}}
            elif method=='tools/list':
                result={'tools':[{'name':n,'description':DESCRIPTIONS[n],'inputSchema':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}} for n,props in SCHEMAS.items()]}
            elif method=='tools/call':
                reply=rpc(path,params.get('name'),params.get('arguments'))
                result={'content':[{'type':'text','text':json.dumps(reply,ensure_ascii=False)}], 'isError':'error' in reply}
            elif method=='resources/list': result={'resources':[]}
            elif method=='prompts/list': result={'prompts':[]}
            elif method=='ping': result={}
            else: raise ValueError('unsupported_mcp_method')
            response={'jsonrpc':'2.0','id':req['id'],'result':result}
        except Exception as error:
            response={'jsonrpc':'2.0','id':req['id'],'error':{'code':-32602,'message':type(error).__name__}}
        print(json.dumps(response,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--socket',type=Path,required=True)
    args=parser.parse_args();stdio(args.socket)
