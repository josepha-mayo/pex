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

class FundingChannel(dict):
    # Trusted server exception object; never serialized into guard config or MCP.
    last_error=None

@contextlib.contextmanager
def serve_budget(ledger):
    raw_bound=getattr(ledger,'max_response_bytes',MAX_RAW)
    if (type(raw_bound)is not int or raw_bound not in (MAX_RAW,8*1024*1024)
            or (raw_bound==8*1024*1024) != (getattr(ledger,'output_token_bound',4096)==16384)):
        raise ValueError('fixed_funding_response_bound_required')
    request_bound=MAX_REQUEST if raw_bound==MAX_RAW else 12*1024*1024
    channel=FundingChannel()
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
                if not 0<length<=request_bound: raise ValueError('request_bound')
                obj=json.loads(self.rfile.read(length))
                if type(obj) is not dict: raise ValueError('request_shape')
                with lock:
                    if state['closed']: raise PermissionError('funding_closed')
                    common={'operation','call_id','request_sha256'}
                    if obj.get('operation')=='reserve' and set(obj)==common|{'request_base64'}:
                        if type(obj['request_base64']) is not str: raise ValueError('request_body_shape')
                        body=base64.b64decode(obj['request_base64'],validate=True)
                        if len(body)>MAX_RAW: raise ValueError('request_body_bound')
                        result=ledger.reserve(obj['call_id'],obj['request_sha256'],body)
                    elif obj.get('operation')=='settle' and set(obj)==common|{'status','content_type','raw_base64'}:
                        if type(obj['raw_base64']) is not str: raise ValueError('raw_shape')
                        raw=base64.b64decode(obj['raw_base64'],validate=True)
                        if len(raw)>raw_bound: raise ValueError('raw_bound')
                        result=ledger.settle_raw(obj['call_id'],obj['request_sha256'],obj['status'],obj['content_type'],raw)
                    else: raise ValueError('operation_denied')
                reply={'ok':True,'result':result}
            except Exception as error:
                channel.last_error=error
                status=403;reply={'ok':False,'category':type(error).__name__}
            payload=json.dumps(reply).encode()
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    channel.update(url=f'http://127.0.0.1:{server.server_port}/funding',token=token)
    try: yield channel
    finally:
        with lock: state['closed']=True
        server.shutdown();server.server_close();thread.join()
