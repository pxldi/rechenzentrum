"""The gate's ASGI app. See __init__.py for what it is for."""

import logging
import os
from contextlib import asynccontextmanager

import httpx
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.routes import build_resource_metadata_url, create_protected_resource_routes
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from oauth import server_kwargs

log = logging.getLogger(__name__)

# Only what the streamable HTTP transport uses travels in either direction.
# Authorization in particular stays here: the upstream has no use for the
# token, and a server that never sees one cannot leak it.
REQUEST_HEADERS = ("content-type", "accept", "mcp-session-id", "mcp-protocol-version", "last-event-id")
RESPONSE_HEADERS = ("content-type", "mcp-session-id", "mcp-protocol-version", "cache-control")

# A tool call is a few kilobytes of JSON. The cap keeps a token holder from
# making the gate buffer an arbitrary body.
MAX_BODY_BYTES = 4 * 1024 * 1024


class Proxy:
    """Forward one /mcp request to the upstream and stream the answer back."""

    def __init__(self, upstream: str, client: httpx.AsyncClient) -> None:
        self._upstream = upstream
        self._client = client

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                await JSONResponse({"error": "request body too large"}, status_code=413)(scope, receive, send)
                return
        headers = {k: v for k, v in request.headers.items() if k.lower() in REQUEST_HEADERS}
        upstream_request = self._client.build_request(
            request.method, self._upstream, params=request.query_params, headers=headers, content=bytes(body)
        )
        try:
            upstream = await self._client.send(upstream_request, stream=True)
        except httpx.HTTPError as e:
            log.warning("upstream %s unreachable: %s", self._upstream, e)
            await JSONResponse({"error": "upstream unreachable"}, status_code=502)(scope, receive, send)
            return
        response = StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers={k: v for k, v in upstream.headers.items() if k.lower() in RESPONSE_HEADERS},
            background=BackgroundTask(upstream.aclose),
        )
        await response(scope, receive, send)


def create_app(client: httpx.AsyncClient | None = None) -> Starlette:
    upstream = os.environ["UPSTREAM_URL"]
    auth = server_kwargs()
    if not auth:
        raise SystemExit("mcp_gate needs OAUTH_ISSUER: without a token check it would be an open proxy")
    settings = auth["auth"]
    # No Accept-Encoding goes upstream, so the raw bytes are the plain body
    # and the forwarded content-type describes them. Reads wait long enough
    # for a slow tool (Snacky's Open Food Facts lookups) but not forever.
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0))

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok", "server": "gate", "build": os.environ.get("IMAGE_SHA", "")})

    @asynccontextmanager
    async def lifespan(_: Starlette):
        yield
        await client.aclose()

    routes = [
        Route("/health", health, methods=["GET"]),
        Route(
            "/mcp",
            RequireAuthMiddleware(
                Proxy(upstream, client),
                settings.required_scopes or [],
                build_resource_metadata_url(settings.resource_server_url),
            ),
            methods=["GET", "POST", "DELETE"],
        ),
        *create_protected_resource_routes(settings.resource_server_url, [settings.issuer_url]),
    ]
    middleware = [Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(auth["token_verifier"]))]
    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
