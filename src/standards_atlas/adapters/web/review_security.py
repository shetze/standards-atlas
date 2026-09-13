"""Local human-adapter security: exact Origin, CSRF and signed displayed-view receipts.

This is browser isolation, not authentication against another same-user local process.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ReviewWorkbenchHttpConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    max_request_body_bytes: int = 262_144

    def __post_init__(self):
        try:
            local = (
                self.host.casefold() == "localhost" or ipaddress.ip_address(self.host).is_loopback
            )
        except ValueError:
            local = False
        if not local:
            raise ValueError("review workbench must bind to a loopback host")
        if not 1 <= self.port <= 65_535:
            raise ValueError("review workbench port must be between 1 and 65535")
        if self.max_request_body_bytes < 1:
            raise ValueError("max_request_body_bytes must be positive")

    @property
    def allowed_hosts(self):
        return {"localhost", "127.0.0.1", "::1", self.host.casefold()}


class ViewReceipts:
    """Receipts expire on server restart and bind the entire displayed source/state."""

    def __init__(self):
        self._key = secrets.token_bytes(32)

    def sign(self, view: dict) -> str:
        raw = json.dumps(view, sort_keys=True, separators=(",", ":")).encode()
        payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        mac = hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{mac}"

    def verify(self, token: str) -> dict:
        try:
            if len(token) > 131_072:
                raise ValueError("oversized view token")
            payload, actual = token.rsplit(".", 1)
            expected = hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(actual, expected):
                raise ValueError("signature mismatch")
            value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            if not isinstance(value, dict):
                raise ValueError("invalid view payload")
            return value
        except (ValueError, UnicodeError, TypeError) as exc:
            raise ValueError("invalid or expired review view; reload the displayed case") from exc


def _authority(raw: str, scheme: str):
    parsed = urlsplit(raw)
    if parsed.scheme != scheme or parsed.username or parsed.password:
        raise ValueError("invalid local authority")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("invalid local authority")
    return parsed.hostname, parsed.port or (443 if scheme == "https" else 80)


class ReviewSecurityMiddleware:
    """Guard reads and writes, including middleware error responses; never enable CORS."""

    def __init__(self, app, *, config: ReviewWorkbenchHttpConfig, csrf_token: str):
        self.app, self.config, self.csrf_token = app, config, csrf_token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secured(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", ()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cross-origin-resource-policy", b"same-origin"),
                    (b"x-frame-options", b"DENY"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; "
                        b"connect-src 'self'; img-src 'self'; object-src 'none'; "
                        b"base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                    ),
                ]
            await send(message)

        async def fail(status, detail):
            from starlette.responses import JSONResponse

            await JSONResponse({"error": detail}, status_code=status)(scope, receive, secured)

        pairs = scope.get("headers", ())
        if any(
            sum(key == name for key, _ in pairs) > 1
            for name in (b"host", b"origin", b"content-length", b"x-atlas-csrf")
        ):
            await fail(400, "duplicate security header")
            return
        headers = {key.decode("latin1"): value.decode("latin1") for key, value in pairs}
        scheme = scope.get("scheme", "http")
        try:
            host = _authority(f"{scheme}://{headers.get('host', '')}", scheme)
            if host[0] not in self.config.allowed_hosts:
                raise ValueError("nonlocal Host")
            origin = headers.get("origin")
            if origin and _authority(origin, scheme) != host:
                raise ValueError("cross-origin request")
            # Reject even same-site/different-port subresources. Direct navigation has 'none'.
            if headers.get("sec-fetch-site") not in {None, "same-origin", "none"}:
                raise ValueError("cross-site request")
        except ValueError:
            await fail(403, "review workbench accepts same-origin loopback requests only")
            return
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            supplied = headers.get("x-atlas-csrf", "")
            if not secrets.compare_digest(
                supplied.encode("utf-8"), self.csrf_token.encode("ascii")
            ):
                await fail(403, "missing or invalid review CSRF token; reload the page")
                return
            if headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                await fail(415, "review writes require application/json")
                return
        length = headers.get("content-length")
        if length is not None:
            try:
                length = int(length)
                if length < 0:
                    raise ValueError()
            except ValueError:
                await fail(400, "invalid Content-Length header")
                return
            if length > self.config.max_request_body_bytes:
                await fail(413, "review request body is too large")
                return
        messages, consumed = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            consumed += len(message.get("body", b""))
            if consumed > self.config.max_request_body_bytes:
                await fail(413, "review request body is too large")
                return
            messages.append(message)
            if not message.get("more_body", False):
                break
        iterator = iter(messages)

        async def replay():
            return next(iterator, {"type": "http.disconnect"})

        await self.app(scope, replay, secured)
