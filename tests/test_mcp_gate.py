"""The token gate in front of Snacky's MCP port.

Needs the MCP SDK, so it runs inside the homelab-mcp image (see the image
workflow) and is skipped where the SDK is not installed.
"""

import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/homelab-mcp/src"))

HAVE_SDK = all(importlib.util.find_spec(m) is not None for m in ("mcp", "jwt", "httpx", "starlette", "cryptography"))

ISSUER = "https://auth.example.test/application/o/snacky-mcp/"
AUDIENCE = "gate-test-client"
ENV = {
    "UPSTREAM_URL": "http://upstream.test/mcp",
    "OAUTH_ISSUER": ISSUER,
    "OAUTH_AUDIENCE": AUDIENCE,
    "OAUTH_RESOURCE_URL": "https://snacky-mcp.example.test/mcp",
}


@unittest.skipUnless(HAVE_SDK, "needs the MCP SDK and PyJWT (run inside the homelab-mcp image)")
class GateTest(unittest.TestCase):
    def setUp(self):
        import httpx
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        self.jwt = jwt
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.seen = []

        async def upstream(request: Request):
            body = await request.body()
            self.seen.append({"headers": dict(request.headers), "body": body, "method": request.method})
            return JSONResponse(
                {"ok": True},
                headers={"mcp-session-id": "s1", "set-cookie": "leak=1", "x-internal": "1"},
            )

        upstream_app = Starlette(routes=[Route("/mcp", upstream, methods=["GET", "POST", "DELETE"])])
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=upstream_app))

        with mock.patch.dict(os.environ, ENV):
            from mcp_gate.server import create_app

            app = create_app(client)

        # The verifier fetches keys from the JWKS URL; hand it the test key instead.
        public = self.key.public_key()
        fake_jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _t: SimpleNamespace(key=public))
        for m in app.user_middleware:
            backend = m.kwargs.get("backend")
            if backend is not None:
                backend.token_verifier._jwks = fake_jwks

        from starlette.testclient import TestClient

        self.client = TestClient(app)

    def token(self, key=None, **overrides):
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "u1", "exp": int(time.time()) + 300}
        claims.update(overrides)
        return self.jwt.encode(claims, key or self.key, algorithm="RS256")

    def post(self, token=None, **kw):
        headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        headers.update(kw.pop("headers", {}))
        return self.client.post("/mcp", headers=headers, content=kw.pop("content", b'{"jsonrpc":"2.0"}'))

    def test_without_token_is_refused_with_a_pointer_to_the_metadata(self):
        r = self.post()
        self.assertEqual(r.status_code, 401)
        self.assertIn(
            'resource_metadata="https://snacky-mcp.example.test/.well-known/oauth-protected-resource/mcp"',
            r.headers["www-authenticate"],
        )
        self.assertEqual(self.seen, [])

    def test_bad_tokens_are_refused(self):
        bad = [
            "not-a-jwt",
            self.token(key=self.other_key),
            self.token(aud="another-client"),
            self.token(iss="https://auth.example.test/application/o/vault-mcp/"),
            self.token(exp=int(time.time()) - 10),
        ]
        for t in bad:
            with self.subTest(token=t[:20]):
                self.assertEqual(self.post(t).status_code, 401)
        self.assertEqual(self.seen, [])

    def test_valid_token_is_forwarded_without_the_token(self):
        r = self.post(self.token(), headers={"mcp-protocol-version": "2025-06-18", "cookie": "a=b"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True})
        self.assertEqual(r.headers["mcp-session-id"], "s1")
        self.assertNotIn("set-cookie", r.headers)
        self.assertNotIn("x-internal", r.headers)
        (call,) = self.seen
        self.assertEqual(call["body"], b'{"jsonrpc":"2.0"}')
        self.assertNotIn("authorization", call["headers"])
        self.assertNotIn("cookie", call["headers"])
        self.assertEqual(call["headers"]["mcp-protocol-version"], "2025-06-18")

    def test_oversized_body_is_refused(self):
        from mcp_gate.server import MAX_BODY_BYTES

        r = self.post(self.token(), content=b"x" * (MAX_BODY_BYTES + 1))
        self.assertEqual(r.status_code, 413)
        self.assertEqual(self.seen, [])

    def test_metadata_names_the_issuer(self):
        r = self.client.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["authorization_servers"], [ISSUER])
        self.assertEqual(r.json()["resource"], ENV["OAUTH_RESOURCE_URL"])

    def test_refuses_to_start_without_a_token_check(self):
        from mcp_gate.server import create_app

        env = {k: v for k, v in ENV.items() if k != "OAUTH_ISSUER"}
        with mock.patch.dict(os.environ, env, clear=True), self.assertRaises(SystemExit):
            create_app()


if __name__ == "__main__":
    unittest.main()
