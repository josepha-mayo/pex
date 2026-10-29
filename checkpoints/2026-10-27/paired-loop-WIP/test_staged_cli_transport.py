"""Pinned CLI/Bun TLS + child-env probe using ONLY synthetic loopback TLS/proxy.

No provider/model request: a local plugin performs one authored TLS fetch and
exits before inference. Ephemeral local test certificate/key are not provider
credentials, never uploaded, and never added to system trust. No TLS bypass.
"""
import hashlib
import http.server
import json
from pathlib import Path
import select
import socket
import ssl
import subprocess
import threading
import pytest

ROOT=Path(__file__).resolve().parents[1]
BINARY=ROOT/'opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode'
MODULES=ROOT/'opencode-qualification-20261027/mock/node_modules'
PIN='ca9b3ee262e33bb4e7aa0e1230dc61086a474c8c8016b980081d0719712fd2e7'


@pytest.fixture
def tls_fixture(tmp_path):
    # This synthetic certificate has no relation to existing platform CA/key.
    key=tmp_path/'authored-tls.key';cert=tmp_path/'authored-tls.crt'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
        '-subj','/CN=pex-authored.invalid','-addext','subjectAltName=DNS:pex-authored.invalid',
        '-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
    key.chmod(0o600);cert.chmod(0o600)
    connects=[];requests=[]
    class TLS(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.headers.get('Host'),self.path))
            assert self.path=='/authored-probe'
            raw=b'AUTHORED-LOCAL-TLS-ONLY'
            self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*unused):pass
    origin=http.server.ThreadingHTTPServer(('127.0.0.1',0),TLS)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    origin.socket=context.wrap_socket(origin.socket,server_side=True)
    class Proxy(http.server.BaseHTTPRequestHandler):
        def do_CONNECT(self):
            assert self.path in ('pex-authored.invalid:443','wrong-authored.invalid:443')
            connects.append(self.path)
            # Never resolve/connect to the requested host. This fixture proxy
            # can open only its own exact loopback synthetic TLS origin.
            upstream=socket.socket();upstream.settimeout(5)
            upstream.connect(('127.0.0.1',origin.server_port))
            self.send_response(200);self.end_headers()
            try:
                while True:
                    ready,_,_=select.select([self.connection,upstream],[],[],5)
                    if not ready:break
                    for source in ready:
                        data=source.recv(65536)
                        if not data:return
                        (upstream if source is self.connection else self.connection).sendall(data)
            except (OSError,TimeoutError):pass
            finally:upstream.close()
        def log_message(self,*unused):pass
    proxy=http.server.ThreadingHTTPServer(('127.0.0.1',0),Proxy)
    for server in (origin,proxy):threading.Thread(target=server.serve_forever,daemon=True).start()
    try:yield cert,proxy.server_port,connects,requests
    finally:
        for server in (proxy,origin):server.shutdown();server.server_close()
        key.unlink();cert.unlink()  # Owned ephemeral TLS fixture material only.


def probe(tmp_path,tls_fixture,*,trust_var=None,hostname='pex-authored.invalid',extra_env=None):
    assert hashlib.sha256(BINARY.read_bytes()).hexdigest()==PIN
    cert,port,connects,requests=tls_fixture
    case=tmp_path/'case';(case/'plugins/probe').mkdir(parents=True)
    (tmp_path/'node_modules').symlink_to(MODULES,target_is_directory=True)
    result=tmp_path/'probe.json'
    config={'url':'https://'+hostname+'/authored-probe','result':str(result)}
    plugin='''import {Plugin} from '@opencode/plugin';
import {writeFileSync} from 'node:fs';
const cfg=CONFIG;
export default Plugin.define({id:'authored-tls-only',async setup(){
 let result;
 try{
  const response=await fetch(cfg.url,{signal:AbortSignal.timeout(3000)});
  result={ok:response.ok,body:await response.text()};
 }catch(error){result={ok:false,errorName:error?.name,code:error?.code};}
 result.bunVersion=process.versions.bun;
 writeFileSync(cfg.result,JSON.stringify(result));process.exit(0);
}});
'''.replace('CONFIG',json.dumps(config))
    (case/'plugins/probe/index.ts').write_text(plugin)
    settings={'update':'disable','warming':False,'share':'disabled','plugins':['./plugins/probe'],
              'policies':[{'action':'provider.use','resource':'*','effect':'deny'}]}
    (case/'opencode.json').write_text(json.dumps(settings))
    # Explicit synthetic env; never reads/copies the existing platform proxy or
    # CA. Inference/update/model-discovery paths remain disabled.
    env={'PATH':'/usr/bin:/bin','HOME':str(tmp_path/'home'),'LANG':'C.UTF-8','TERM':'dumb',
         'HTTPS_PROXY':f'http://127.0.0.1:{port}','NO_PROXY':'127.0.0.1,localhost',
         'OPENCODE_DISABLE_MODELS_FETCH':'1','OPENCODE_DISABLE_AUTOUPDATE':'1','OPENCODE_DISABLE_FREE_MODELS':'1'}
    env.update({f'XDG_{key}_HOME':str(tmp_path/key.lower()) for key in ('CONFIG','DATA','CACHE','STATE')})
    if trust_var:env[trust_var]=str(cert)
    env.update(extra_env or {})
    completed=subprocess.run([str(BINARY),'run','--standalone','--format','json','--model','authored/no-provider',
                             '--','Authored TLS probe only'],cwd=case,env=env,input='',text=True,
                             capture_output=True,timeout=10)
    assert result.is_file(),(completed.returncode,completed.stderr[-2000:])
    # The plugin host intentionally exits before inference; CLI's supervisor
    # may consequently report its closed local IPC channel with exit1. The
    # completed probe receipt and loopback wire assertions, not CLI exit0,
    # qualify TLS. This is NOT a successful worker/CLI turn.
    assert completed.returncode in (0,1)
    return json.loads(result.read_text()),connects,requests


@pytest.mark.parametrize('trust_var,hostname,accepted',[
    (None,'pex-authored.invalid',False),
    ('SSL_CERT_FILE','pex-authored.invalid',True),
    ('NODE_EXTRA_CA_CERTS','pex-authored.invalid',True),
    ('SSL_CERT_FILE','wrong-authored.invalid',False),
])
def test_pinned_CLI_actual_TLS_proxy_CA_and_hostname(tmp_path,tls_fixture,trust_var,hostname,accepted):
    result,connects,requests=probe(tmp_path,tls_fixture,trust_var=trust_var,hostname=hostname)
    assert result['bunVersion'] and result['ok'] is accepted,result
    assert connects==[hostname+':443']
    if accepted:assert result['body']=='AUTHORED-LOCAL-TLS-ONLY' and requests==[(hostname,'/authored-probe')]
    else:assert not requests


def test_pinned_Bun_HTTPS_route_ignores_distinct_inert_ALL_PROXY_fallback(tmp_path,tls_fixture):
    result,connects,requests=probe(tmp_path,tls_fixture,trust_var='SSL_CERT_FILE',
        extra_env={'ALL_PROXY':'http://127.0.0.1:1','all_proxy':'http://127.0.0.1:2'})
    assert result['bunVersion']=='1.4.4' and result['ok'] is True
    assert connects==['pex-authored.invalid:443']
    assert requests==[('pex-authored.invalid','/authored-probe')]
