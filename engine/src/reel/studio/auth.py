"""Per-install token (NFR-4): 32 random bytes, hex, in ~/.config/reel/studio_token (0600).

Every /api/* request carries `X-Reel-Token`. Only the endpoints a browser loads by URL (SSE, media,
package.zip, library previews) may pass it as `?token=` instead. Checked in ASGI middleware, before any body parsing.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import parse_qs

QUERY_TOKEN_PATHS = re.compile(
    r"^/api/(projects/[^/]+/(events|media/.+|package\.zip)|libraries/(sfx|music|broll)/[^/]+/media|listening/(sfx|music|voice)/media/.+)$"
)


def load_or_create_token(path: Path) -> str:
    if path.exists():
        token = path.read_text().strip()
        if re.fullmatch(r"[0-9a-f]{64}", token):
            return token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (token + "\n").encode())
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return token


class TokenMiddleware:
    """Pure ASGI middleware: 401 for /api/* without the right token."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/") or scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)
        given = dict(scope.get("headers") or []).get(b"x-reel-token", b"")
        if not given and QUERY_TOKEN_PATHS.match(scope["path"]):
            given = (parse_qs(scope.get("query_string", b"").decode()).get("token") or [""])[0].encode()
        if given and hmac.compare_digest(given, self.token):
            return await self.app(scope, receive, send)
        body = json.dumps({"error": "missing or wrong token"}).encode()
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
