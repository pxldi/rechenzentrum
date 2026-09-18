"""Serve an MCPServer over Streamable HTTP inside the cluster.

The SDK arms DNS-rebinding protection by default and then answers 421 to any
Host that is not localhost, which is every request a Kubernetes Service
delivers. Nothing but the ZeroClaw pod can reach these servers (the
NetworkPolicy beside the Deployment names it), so switching the check off is
the honest configuration rather than allowlisting a Service name that the
policy already enforces.
"""

import functools
import inspect
import logging
import os
from collections.abc import Callable

import uvicorn
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def guarded(*errors: type[BaseException]) -> Callable:
    """Turn an anticipated failure into a ToolError, so the model reads the
    message ("pod not found", "Tandoor answered 400: ...") and can correct its
    call. Anything else stays a crash, which the SDK logs with a traceback and
    reports to the model only as "the call failed"."""

    def deco(fn: Callable) -> Callable:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def aw(*a, **kw):
                try:
                    return await fn(*a, **kw)
                except errors as e:
                    raise ToolError(_describe(e)) from e

            return aw

        @functools.wraps(fn)
        def w(*a, **kw):
            try:
                return fn(*a, **kw)
            except errors as e:
                raise ToolError(_describe(e)) from e

        return w

    return deco


def _describe(e: BaseException) -> str:
    # kubernetes.client.ApiException carries the status and the API's reason;
    # httpx errors carry the request; RuntimeError carries what we wrote.
    status = getattr(e, "status", None)
    reason = getattr(e, "reason", None)
    if status and reason:
        return f"API server answered {status} {reason}"
    return str(e)[:600] or type(e).__name__


def serve(mcp: MCPServer) -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok", "server": mcp.name, "build": os.environ.get("IMAGE_SHA", "")})

    app = mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), log_level="info")  # noqa: S104
