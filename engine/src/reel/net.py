"""One TLS setup for every outbound HTTPS call the engine makes (Pexels, model downloads, asset fetches).

Order: $SSL_CERT_FILE when set (explicit wins) → the OS trust store via `truststore` (picks up corporate /
TLS-inspecting proxy roots installed in the macOS keychain, which certifi alone does not have) → certifi →
Python's default. Studio-launched jobs get no SSL_CERT_FILE, so the trust-store path is what makes them work.
"""

from __future__ import annotations

import os
import ssl
import urllib.request

USER_AGENT = "reel-editor/0.1"


def tls_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE")
    if cafile:
        return ssl.create_default_context(cafile=cafile)
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass
    try:  # python.org builds ship without a CA bundle
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def get(url: str, headers: dict[str, str] | None = None, timeout: int = 60, max_bytes: int | None = None) -> bytes:
    """GET over HTTPS with the shared TLS context. `max_bytes` refuses oversized bodies (asset safety caps)."""
    if not url.startswith("https://"):
        raise ValueError(f"only https URLs are fetched: {url[:60]}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, context=tls_context(), timeout=timeout) as r:  # noqa: S310 — https only (checked above)
        if max_bytes is None:
            return r.read()
        data = r.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"response larger than {max_bytes} bytes: {url[:60]}")
        return data
