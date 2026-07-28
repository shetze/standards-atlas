"""ASGI construction for authenticated Streamable HTTP MCP operation."""

from __future__ import annotations

import contextlib
import fnmatch
import hmac
import os
from typing import Any

from standards_atlas.adapters.mcp.audit import McpAuditLogger
from standards_atlas.adapters.mcp.configuration import McpServerConfig


def create_http_app(server: Any, config: McpServerConfig) -> Any:
    """Create a secured Starlette application around a FastMCP server."""
    try:
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route
    except ImportError as exc:
        raise RuntimeError("HTTP MCP support is not installed. Run 'uv sync --extra mcp'.") from exc

    expected_token = None
    if config.auth.enabled:
        expected_token = os.environ.get(config.auth.token_environment_variable)
        if not expected_token:
            raise ValueError(
                f"environment variable {config.auth.token_environment_variable!r} is required"
            )

    auditor = McpAuditLogger(config.audit.path, enabled=config.audit.enabled)

    def matches_any(value: str, patterns: tuple[str, ...]) -> bool:
        return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)

    class RequestBodyLimitMiddleware:
        def __init__(self, app: Any) -> None:
            self.app = app

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            content_length = headers.get(b"content-length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = 0
                if declared_size > config.limits.max_request_body_bytes:
                    response = JSONResponse(
                        {"detail": "request body is too large"},
                        status_code=413,
                    )
                    await response(scope, receive, send)
                    return

            messages: list[dict[str, Any]] = []
            received_size = 0
            while True:
                message = await receive()
                messages.append(message)
                if message["type"] != "http.request":
                    break
                received_size += len(message.get("body", b""))
                if received_size > config.limits.max_request_body_bytes:
                    response = JSONResponse(
                        {"detail": "request body is too large"},
                        status_code=413,
                    )
                    await response(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break

            async def replay_receive() -> Any:
                if messages:
                    return messages.pop(0)
                return {"type": "http.disconnect"}

            await self.app(scope, replay_receive, send)

    class SecurityMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Any:
            origin = request.headers.get("origin")
            if origin and not matches_any(origin, config.http.allowed_origins):
                auditor.record(
                    "http_request",
                    method=request.method,
                    path=request.url.path,
                    status=403,
                    origin=origin,
                    remote=request.client.host if request.client else None,
                )
                return JSONResponse({"detail": "origin is not allowed"}, status_code=403)

            if expected_token is not None and request.url.path != "/healthz":
                authorization = request.headers.get("authorization", "")
                supplied = authorization.removeprefix("Bearer ")
                if not authorization.startswith("Bearer ") or not hmac.compare_digest(
                    supplied, expected_token
                ):
                    auditor.record(
                        "http_request",
                        method=request.method,
                        path=request.url.path,
                        status=401,
                        remote=request.client.host if request.client else None,
                    )
                    return JSONResponse(
                        {"detail": "missing or invalid bearer token"},
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            response = await call_next(request)
            auditor.record(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                origin=origin,
                remote=request.client.host if request.client else None,
            )
            return response

    async def health(_: Any) -> Any:
        return JSONResponse({"status": "ok"})

    @contextlib.asynccontextmanager
    async def lifespan(_: Any):
        async with server.session_manager.run():
            yield

    path = config.http.path.rstrip("/") or "/"
    return Starlette(
        routes=[Route("/healthz", health), Mount(path, app=server.streamable_http_app())],
        middleware=[Middleware(RequestBodyLimitMiddleware), Middleware(SecurityMiddleware)],
        lifespan=lifespan,
    )


def run_http_server(server: Any, config: McpServerConfig) -> None:
    """Run the Streamable HTTP ASGI app using uvicorn."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("HTTP MCP support is not installed. Run 'uv sync --extra mcp'.") from exc
    uvicorn.run(create_http_app(server, config), host=config.http.host, port=config.http.port)
