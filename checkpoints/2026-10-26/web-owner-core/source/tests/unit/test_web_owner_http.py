"""Authored, in-process ASGI events only; no sockets, browser, TLS or app wiring."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

from pex_bridge.web_owner_auth import OwnerSessions, ProvisionedOwnerVerifier, WebOwnerConfig
from pex_bridge import web_owner_http as http

SECRET = 'S' * 43  # Synthetic fixture, never a deployed credential.
HOST = b'owner.example.test'
ORIGIN = b'https://owner.example.test'


class OwnerHttpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 100.0
        self.sequence = 0
        self.config = WebOwnerConfig(enabled=True, public_origin=ORIGIN.decode(),
            verifier=ProvisionedOwnerVerifier(hashlib.sha256(SECRET.encode()).hexdigest()))
        def token():
            self.sequence += 1
            return f'T{self.sequence:042d}'
        self.sessions = OwnerSessions(self.config, clock=lambda: self.now, token_factory=token)
        self.app = http.create_web_owner_auth_app(self.sessions)
        self.receives = 0

    async def request(self, path='/owner/auth/login', method='POST', *, body=None,
                      headers=None, scope_changes=None, events=None, during=None):
        if body is None:
            body = json.dumps({'owner_secret': SECRET}).encode() if path.endswith('login') else b''
        if headers is None:
            headers = [(b'host', HOST), (b'origin', ORIGIN)]
            if path.endswith('login'):
                headers += [(b'content-type', b'application/json')]
        scope = dict(type='http', scheme='https', method=method, path=path,
                     raw_path=path.encode(), query_string=b'', headers=headers)
        scope.update(scope_changes or {})
        messages = list(events) if events is not None else [dict(type='http.request', body=body)]
        output = []
        async def receive():
            self.receives += 1
            if during:
                await during()
            if not messages:
                raise AssertionError('Unexpected extra receive')
            return messages.pop(0)
        async def send(message):
            output.append(message)
        await self.app(scope, receive, send)
        return output

    def response(self, messages, status):
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['type'], 'http.response.start')
        self.assertEqual(messages[0]['status'], status)
        headers = dict(messages[0]['headers'])
        self.assertEqual(headers[b'cache-control'], b'no-store')
        self.assertEqual(headers[b'x-content-type-options'], b'nosniff')
        self.assertNotIn(b'access-control-allow-origin', headers)
        self.assertNotIn(b'location', headers)
        body = messages[1]['body']
        self.assertEqual(int(headers[b'content-length']), len(body))
        return headers, json.loads(body)

    async def signed_in(self):
        headers, data = self.response(await self.request(), 200)
        cookie = headers[b'set-cookie'].split(b';', 1)[0]
        return cookie, data['csrf_token'].encode()

    def auth_headers(self, cookie, csrf=None, origin=True):
        headers = [(b'host', HOST), (b'cookie', cookie)]
        if origin:
            headers.append((b'origin', ORIGIN))
        if csrf:
            headers.append((b'x-pex-owner-csrf', csrf))
        return headers

    async def test_login_reload_logout_and_no_cookie_in_json(self):
        headers, data = self.response(await self.request(), 200)
        set_cookie = headers[b'set-cookie']
        for flag in [b'Path=/', b'Secure', b'HttpOnly', b'SameSite=Strict']:
            self.assertIn(flag, set_cookie)
        cookie = set_cookie.split(b';', 1)[0]
        self.assertNotIn(cookie.split(b'=')[1].decode(), json.dumps(data))
        self.assertNotIn(SECRET, json.dumps(data))
        self.now += 2
        h, status = self.response(await self.request('/owner/auth/session', 'GET',
            headers=self.auth_headers(cookie, origin=False)), 200)
        self.assertNotIn(b'set-cookie', h)
        self.assertEqual(status['csrf_token'], data['csrf_token'])
        self.assertEqual(status['expires_in_seconds'], 898)
        h, result = self.response(await self.request('/owner/auth/logout',
            headers=self.auth_headers(cookie, data['csrf_token'].encode())), 200)
        self.assertIn(b'Max-Age=0', h[b'set-cookie'])
        self.assertFalse(result['authenticated'])
        self.response(await self.request('/owner/auth/session', 'GET',
            headers=self.auth_headers(cookie)), 401)

    async def test_boundary_rejected_before_body(self):
        cases = [({'scheme':'http'}, None, 403),
                 ({}, [(b'host', b'evil.test'), (b'origin', ORIGIN)], 400),
                 ({}, [(b'host', HOST), (b'host', HOST), (b'origin', ORIGIN)], 400),
                 ({}, [(b'host', HOST), (b'origin', b'https://evil.test')], 403),
                 ({}, [(b'host', HOST), (b'origin', ORIGIN), (b'origin', ORIGIN)], 403),
                 ({}, [(b'host', HOST)], 403),
                 ({'query_string':b'owner_secret=not-real'}, None, 400)]
        for scope, headers, expected in cases:
            with self.subTest(scope=scope, expected=expected):
                before = self.receives
                self.response(await self.request(headers=headers, scope_changes=scope), expected)
                self.assertEqual(self.receives, before)
        self.assertEqual(self.sessions._sessions, {})

    async def test_exact_inventory_no_private_or_docs_routes(self):
        for path in ['/owner/auth/login/', '/v1/sessions', '/docs', '/openapi.json',
                     '/mcp/', '/hooks', '/owner/auth/%6cogin', '/不存在']:
            with self.subTest(path=path):
                self.response(await self.request(path), 404)
        for method in ['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE']:
            self.response(await self.request(method=method), 405)
        self.response(await self.request(scope_changes={'raw_path':b'/owner/auth/%6cogin'}), 404)
        self.assertEqual(self.receives, 0)

    async def test_strict_json(self):
        bodies = [b'[]', b'null', b'{}', b'{"owner_secret":false}',
                  b'{"owner_secret":"short"}', b'{"owner_secret":NaN}', b'\xff',
                  ('{"owner_secret":"'+SECRET+'","owner_secret":"'+SECRET+'"}').encode(),
                  json.dumps({'owner_secret':SECRET, 'extra':True}).encode(),
                  b'['*500+b']'*500]
        for body in bodies:
            with self.subTest(body=body[:40]):
                self.response(await self.request(body=body), 400)
        self.assertEqual(self.sessions._sessions, {})

    async def test_wrong_secret_and_rate_limit(self):
        for _ in range(8):
            self.response(await self.request(body=json.dumps({'owner_secret':'X'*43}).encode()),401)
        self.response(await self.request(),429)
        self.assertEqual(self.sessions._sessions,{})

    async def test_content_headers(self):
        base = [(b'host',HOST),(b'origin',ORIGIN)]
        good = base+[(b'content-type',b'application/json')]
        for extra, status in [([(b'content-type',b'text/plain')],415),
                ([(b'content-type',b'application/json'),(b'content-type',b'application/json')],415),
                ([],415)]:
            self.response(await self.request(headers=base+extra),status)
        for extra, status in [([(b'content-encoding',b'identity')],415),
                ([(b'content-length',b'1'),(b'content-length',b'1')],400),
                ([(b'content-length',b'1'),(b'transfer-encoding',b'chunked')],400),
                ([(b'content-length',b'-1')],400), ([(b'content-length',b'+1')],400),
                ([(b'content-length',b'1025')],413), ([(b'content-length',b'1')],400)]:
            self.response(await self.request(headers=good+extra),status)
        self.assertEqual(self.sessions._sessions,{})

    async def test_streamed_limits_and_chunked_success(self):
        self.response(await self.request(events=[{'type':'http.request','body':b'x'*700,'more_body':True},
            {'type':'http.request','body':b'x'*325}]),413)
        self.response(await self.request(events=[{'type':'http.request','body':b'', 'more_body':True}]*128),413)
        body = json.dumps({'owner_secret':SECRET}).encode()
        self.response(await self.request(events=[{'type':'http.request','body':body[:10],'more_body':True},
            {'type':'http.request','body':body[10:]}]),200)

    async def test_disconnect_and_timeout(self):
        self.assertEqual(await self.request(events=[{'type':'http.disconnect'}]),[])
        async def slow():
            await asyncio.sleep(.02)
        with patch.object(http,'BODY_TIMEOUT_SECONDS',.001):
            self.response(await self.request(during=slow),408)
        self.assertEqual(self.sessions._sessions,{})

    async def test_bad_body_event_types(self):
        for event in [{'type':'other'}, {'type':'http.request','body':'string'},
                      {'type':'http.request','body':b'', 'more_body':1}]:
            self.response(await self.request(events=[event]),400)

    async def test_reconfiguration_during_login_body(self):
        async def disable():
            self.sessions.reconfigure(replace(self.config,enabled=False))
        self.response(await self.request(during=disable),503)
        self.assertEqual(self.sessions._sessions,{})

    async def test_reconfiguration_and_expiry_during_status_body(self):
        cookie,_ = await self.signed_in()
        async def change_origin():
            self.sessions.reconfigure(replace(self.config,public_origin='https://new.example.test'))
        self.response(await self.request('/owner/auth/session','GET',headers=self.auth_headers(cookie),
            during=change_origin),400)
        self.sessions.reconfigure(self.config)
        cookie,_ = await self.signed_in()
        async def expire():
            self.now += 901
        self.response(await self.request('/owner/auth/session','GET',headers=self.auth_headers(cookie),
            during=expire),401)

    async def test_logout_csrf_and_replay(self):
        cookie,csrf = await self.signed_in()
        self.response(await self.request('/owner/auth/logout',headers=self.auth_headers(cookie)),403)
        self.response(await self.request('/owner/auth/logout',headers=self.auth_headers(cookie,b'X'*43)),403)
        self.response(await self.request('/owner/auth/logout',headers=self.auth_headers(cookie,csrf,False)),403)
        self.response(await self.request('/owner/auth/logout',headers=self.auth_headers(cookie,csrf)),200)
        self.response(await self.request('/owner/auth/logout',headers=self.auth_headers(cookie,csrf)),401)

    async def test_authenticated_routes_refuse_bodies(self):
        cookie,csrf = await self.signed_in()
        for path,method in [('/owner/auth/session','GET'),('/owner/auth/logout','POST')]:
            self.response(await self.request(path,method,headers=self.auth_headers(cookie,csrf),body=b'x'),413)
        self.response(await self.request('/owner/auth/session','GET',headers=self.auth_headers(cookie)),200)

    async def test_logout_revalidates_after_await(self):
        cookie,csrf=await self.signed_in()
        async def revoke():
            self.sessions.reconfigure(replace(self.config,ttl_seconds=800))
        self.response(await self.request('/owner/auth/logout',headers=self.auth_headers(cookie,csrf),during=revoke),401)

    async def test_disabled_default_and_no_ambient_configuration(self):
        self.app=http.create_web_owner_auth_app(OwnerSessions(WebOwnerConfig()))
        self.response(await self.request(),503)
        self.assertEqual(self.receives,0)
        with self.assertRaises(ValueError):
            http.create_web_owner_auth_app(None)

    async def test_websockets_and_lifespan(self):
        output=[]
        async def forbidden():
            raise AssertionError('WebSocket may not read')
        async def send(message):
            output.append(message)
        await self.app({'type':'websocket'},forbidden,send)
        self.assertEqual(output,[{'type':'websocket.close','code':1008}])
        output.clear()
        events=iter([{'type':'lifespan.startup'},{'type':'lifespan.shutdown'}])
        async def receive():
            return next(events)
        await self.app({'type':'lifespan'},receive,send)
        self.assertEqual(output,[{'type':'lifespan.startup.complete'},{'type':'lifespan.shutdown.complete'}])


if __name__ == '__main__':
    attempts=[]
    def audit(event,args):
        if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.sendmsg'}:
            attempts.append(event)
            raise AssertionError('No network allowed in authored ASGI tests')
    sys.addaudithook(audit)
    outcome=unittest.main(exit=False,verbosity=2).result
    print('NETWORK_AUDIT='+json.dumps({'attempts':len(attempts),'events':attempts}))
    raise SystemExit(0 if outcome.wasSuccessful() and not attempts else 1)
