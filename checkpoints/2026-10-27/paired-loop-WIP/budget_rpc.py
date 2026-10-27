"""WIP: private trusted-guard funding IPC, never registered as a model/MCP tool.

No provider transport or activation here. The caller must supply an independently
admitted ledger; this server cannot create credentials, budgets or accounts.
"""
import base64
import contextlib
import hmac
import http.server
import json
import secrets
import threading

MAX_RAW=2*1024*1024
MAX_REQUEST=3*1024*1024

@contextlib.contextmanager
def serve_budget(ledger):
    token=secrets.token_hex(32)
    lock=threading.Lock()
    state={'closed':False}
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            status=200
            try:
                if self.path!='/funding' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                    raise PermissionError('private_guard_only')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=MAX_REQUEST: raise ValueError('request_bound')
                obj=json.loads(self.rfile.read(length))
                if type(obj) is not dict: raise ValueError('request_shape')
                with lock:
                    if state['closed']: raise PermissionError('funding_closed')
                    common={'operation','call_id','request_sha256'}
                    if obj.get('operation')=='reserve' and set(obj)==common:
                        result=ledger.reserve(obj['call_id'],obj['request_sha256'])
                    elif obj.get('operation')=='settle' and set(obj)==common|{'status','content_type','raw_base64'}:
                        if type(obj['raw_base64']) is not str: raise ValueError('raw_shape')
                        raw=base64.b64decode(obj['raw_base64'],validate=True)
                        if len(raw)>MAX_RAW: raise ValueError('raw_bound')
                        result=ledger.settle_raw(obj['call_id'],obj['request_sha256'],obj['status'],obj['content_type'],raw)
                    else: raise ValueError('operation_denied')
                reply={'ok':True,'result':result}
            except Exception as error:
                status=403;reply={'ok':False,'category':type(error).__name__}
            payload=json.dumps(reply).encode()
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield {'url':f'http://127.0.0.1:{server.server_port}/funding','token':token}
    finally:
        with lock: state['closed']=True
        server.shutdown();server.server_close();thread.join()
