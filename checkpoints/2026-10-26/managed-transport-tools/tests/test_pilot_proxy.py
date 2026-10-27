"""Authored wire checks; no provider calls or credentials."""
import hashlib
import os
import ssl
from pathlib import Path
import httpx
import pytest
import managed_chat as mc

ENDPOINT="https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions"

@pytest.fixture
def binding(monkeypatch):
    proxy="http://platform-fixture.invalid:8080"
    ca=ssl.get_default_verify_paths().cafile
    assert ca
    monkeypatch.setenv("HTTPS_PROXY", proxy)
    monkeypatch.setenv("SSL_CERT_FILE", ca)
    return mc._PilotProxyBinding(hashlib.sha256(proxy.encode()).hexdigest(), ca,
                                hashlib.sha256(Path(ca).read_bytes()).hexdigest())

@pytest.mark.parametrize("change", ["proxy","ca","host","digest"])
def test_changed_binding_refused(binding,monkeypatch,change):
    endpoint=ENDPOINT
    if change=="proxy": monkeypatch.setenv("HTTPS_PROXY","http://other.invalid")
    if change=="ca": monkeypatch.setenv("SSL_CERT_FILE","/tmp/not-platform-ca")
    if change=="host": endpoint="https://other.nebius.com/v1/chat/completions"
    if change=="digest": binding=mc._PilotProxyBinding("0"*64,binding.ca_path,binding.ca_sha256)
    with pytest.raises(mc.Refusal): binding.transport(endpoint)

def test_explicit_tls_and_zero_retry(binding,monkeypatch):
    seen={}
    monkeypatch.setattr(mc.httpx,"AsyncHTTPTransport",lambda **kw:seen.update(kw))
    binding.transport(ENDPOINT)
    assert seen["trust_env"] is False and seen["retries"]==0
    assert seen["verify"].check_hostname
    assert seen["verify"].verify_mode==ssl.CERT_REQUIRED
    assert seen["proxy"]==os.environ["HTTPS_PROXY"]

@pytest.mark.asyncio
@pytest.mark.parametrize("status",[200,302])
async def test_guard_preserves_host_and_does_not_redirect(binding,monkeypatch,status):
    calls=[]
    async def handle(request):
        calls.append(request)
        return httpx.Response(status,headers={"location":"https://other.invalid"},
            json={"id":"fake","object":"chat.completion","model":"fixture",
                  "choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":"authored"}}],
                  "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}})
    monkeypatch.setattr(mc._PilotProxyBinding,"transport",lambda self,endpoint:httpx.MockTransport(handle))
    async def denied(*args): raise AssertionError("pilot must not perform local origin DNS")
    monkeypatch.setattr(mc,"_resolve_public_address",denied)
    class Pilot(mc.ManagedChatCandidate): pass
    c=Pilot(mc.Route(ENDPOINT,"fixture","planner",mc.Limits()))
    c._pilot_proxy_binding=binding
    await c._execute_owned(mc.Invocation("proxy-test","authored"),mc._ScopedCredential("fake-not-key",c.route.fingerprint))
    assert len(calls)==1
    assert str(calls[0].url)==ENDPOINT
    assert calls[0].headers["host"]=="api.tokenfactory.us-central1.nebius.com"
    if status==302: assert c.receipt("proxy-test").http_status==302
