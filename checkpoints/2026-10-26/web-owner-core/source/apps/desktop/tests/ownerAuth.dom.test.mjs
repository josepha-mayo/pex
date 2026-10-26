// Built owner-page DOM tests with authored fetch responses. Not real browser/TLS.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { parseHTML } from 'linkedom';

const html = fs.readFileSync(new URL('../dist-owner/owner.html', import.meta.url), 'utf8');
const script = html.match(/src="([^\"]+\.js)"/)[1];
const js = fs.readFileSync(new URL('../dist-owner' + script, import.meta.url), 'utf8');
const good = () => new Response(JSON.stringify({ authenticated:true, principal_id:'web-owner', csrf_token:'C'.repeat(43), expires_in_seconds:900 }));
const denied = () => new Response('',{status:401});
const flush = async () => { for (let i=0;i<6;i++) await new Promise(resolve=>setImmediate(resolve)); };
function setup(responses, origin='https://owner.example.test') {
  const {window,document} = parseHTML(html);
  window.location={origin};
  Object.defineProperty(document,'hidden',{value:false,writable:true});
  const calls=[]; const timers=new Map(); let next=0;
  const fetch=async (url,init) => {
    calls.push({url,init}); const response=responses.shift();
    assert.ok(response,'unexpected extra request'); return await response;
  };
  vm.runInNewContext(js,{window,document,fetch,URL,AbortController,TextDecoder,Uint8Array,
    MutationObserver:window.MutationObserver,console,
    setTimeout(fn){const id=++next;timers.set(id,fn);return id;},
    clearTimeout(id){timers.delete(id);}});
  return {window,document,calls,timers,el:id=>document.getElementById(id),
    submit(){document.getElementById('owner-form').dispatchEvent(new window.Event('submit',{cancelable:true}));}};
}

test('built page login clears form, shows honest pending workspace, logout clears view',async()=>{
  const f=setup([denied(),good(),new Response('{"authenticated":false}')]);await flush();
  assert.equal(f.el('sign-in').disabled,false);assert.equal(f.el('workspace').hidden,true);
  f.el('owner-secret').value='S'.repeat(43);f.submit();
  assert.equal(f.el('owner-secret').value,'');await flush();
  assert.equal(f.el('workspace').hidden,false);assert.equal(f.el('owner-form').hidden,true);
  assert.match(f.el('workspace').textContent,/not connected/);
  f.el('sign-out').click();assert.equal(f.el('workspace').hidden,true);await flush();
  assert.match(f.el('status').textContent,/revoked/);assert.equal(f.calls.length,3);
  assert.equal(f.document.toString().includes('S'.repeat(43)),false);
});

test('unconfigured endpoint leaves login disabled with retry, not operational controls',async()=>{
  const f=setup([new Response('',{status:503})]);await flush();
  assert.match(f.el('status').textContent,/not configured/);assert.equal(f.el('sign-in').disabled,true);
  assert.equal(f.el('workspace').hidden,true);assert.equal(f.el('check-session').hidden,false);
});

test('HTTP page refuses all authentication traffic and explains HTTPS',async()=>{
  const f=setup([],'http://127.0.0.1:1420');await flush();
  assert.equal(f.calls.length,0);assert.match(f.el('status').textContent,/HTTPS/);
  assert.equal(f.el('sign-in').disabled,true);assert.equal(f.el('check-session').hidden,true);
});

test('pagehide locks and clears secret; bfcache restore revalidates before showing workspace',async()=>{
  const f=setup([good(),denied()]);await flush();assert.equal(f.el('workspace').hidden,false);
  f.el('owner-secret').value='S'.repeat(43);f.window.dispatchEvent(new f.window.Event('pagehide'));
  assert.equal(f.el('workspace').hidden,true);assert.equal(f.el('owner-secret').value,'');
  const event=new f.window.Event('pageshow');event.persisted=true;f.window.dispatchEvent(event);
  assert.equal(f.el('workspace').hidden,true);await flush();assert.equal(f.el('workspace').hidden,true);
  assert.equal(f.calls.length,2);assert.equal(f.el('owner-form').hidden,false);
});

test('visibility hide locks and expiry timer locks without automatic auth retry',async()=>{
  const f=setup([good(),good()]);await flush();
  f.document.hidden=true;f.document.dispatchEvent(new f.window.Event('visibilitychange'));
  assert.equal(f.el('workspace').hidden,true);
  f.document.hidden=false;f.document.dispatchEvent(new f.window.Event('visibilitychange'));await flush();
  assert.equal(f.el('workspace').hidden,false);
  for(const fn of [...f.timers.values()])fn();
  assert.equal(f.el('workspace').hidden,true);assert.equal(f.calls.length,2);
});

test('uncertain logout remains locally locked with explicit warning',async()=>{
  const f=setup([good(),new Response('',{status:500})]);await flush();
  f.el('sign-out').click();await flush();
  assert.equal(f.el('workspace').hidden,true);assert.equal(f.el('owner-form').hidden,true);
  assert.match(f.el('status').textContent,/could not be confirmed/);assert.equal(f.calls.length,2);
});


test('static HTML cannot submit the secret through a query string before JavaScript',()=>{
  const {document}=parseHTML(html);
  assert.equal(document.getElementById('owner-form').getAttribute('method'),'post');
  assert.equal(document.getElementById('owner-form').getAttribute('action'),'/owner/auth/login');
  assert.equal(document.getElementById('owner-secret').disabled,true);
  assert.equal(document.getElementById('sign-in').disabled,true);
});
