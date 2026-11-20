"""The client side of review links (`/r/*`): no token, the link is the key. Shared by the full Studio app and the
client-only app (roadmap 4.3 / E3), so the page the client sees is the same code either way.

The client-only app (`create_client_app`) has **only** these routes: no `/api`, no web app, no media outside the
watermarked copies. It binds 127.0.0.1 and starts only on an explicit `reel share-server`; exposing it beyond this Mac
(a tunnel pointed at its port) is the owner's own decision and action.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from reel.studio import projects, review_links

SENT = {"1": "Thanks — your notes were sent.", "checkin": "Thanks — your answers were sent.", "hook": "Thanks — your pick was sent."}
MAX_FORM_BYTES = 64_000


def add_client_routes(app: FastAPI, projects_root: Callable[[], Path]) -> None:
    def _client_page(body: str, nonce: str, status: int = 200) -> HTMLResponse:
        return HTMLResponse(body, status_code=status, headers={**review_links.SECURITY_HEADERS, "Content-Security-Policy": review_links.csp(nonce)})

    def _gone() -> HTMLResponse:
        nonce = secrets.token_urlsafe(16)
        return _client_page(review_links.gone_page(nonce), nonce, 410)

    def _link_ws(link_id: str) -> tuple[Path, dict] | None:
        """An active link's project (whatever stage it is at: the page says what the client can do now)."""
        hit = review_links.resolve(projects_root(), link_id)
        if hit is None:
            return None
        ws = projects.project_dir(projects_root(), hit[0])
        return (ws, hit[1]) if ws is not None else None

    def _client_view_page(ws: Path, link: dict, link_id: str, flash: str = "", ok: bool = True, status: int = 200) -> HTMLResponse:
        nonce = secrets.token_urlsafe(16)
        title = projects.studio_meta(ws).get("name") or "Your reel"
        return _client_page(review_links.page(title, link, nonce, link_id, flash, flash_ok=ok, view=review_links.client_view(ws)), nonce, status)

    @app.get("/r/{link_id}", include_in_schema=False)
    def review_page(link_id: str, sent: str = ""):
        hit = _link_ws(link_id)
        if hit is None:
            return _gone()
        return _client_view_page(hit[0], hit[1], link_id, SENT.get(sent, ""))

    @app.get("/r/{link_id}/video", include_in_schema=False)
    def review_video(link_id: str):
        hit = _link_ws(link_id)
        if hit is None or review_links.review_copy(hit[0]) is None:
            raise StarletteHTTPException(410, "gone")
        return FileResponse(review_links.review_copy(hit[0]), media_type="video/mp4", headers=review_links.SECURITY_HEADERS)

    @app.get("/r/{link_id}/hook/{option}", include_in_schema=False)
    def review_hook(link_id: str, option: Literal["A", "B"]):
        hit = _link_ws(link_id)
        f = review_links.hook_copy(hit[0], option) if hit and review_links.pending_hook(hit[0]) else None
        if f is None:
            raise StarletteHTTPException(410, "gone")
        return FileResponse(f, media_type="video/mp4", headers=review_links.SECURITY_HEADERS)

    async def _client_form(link_id: str, request: Request):
        hit = _link_ws(link_id)
        if hit is None:
            return None, None
        if int(request.headers.get("content-length") or 0) > MAX_FORM_BYTES:
            raise StarletteHTTPException(413, "too large")
        return hit, await request.form()

    def _after_post(hit, link_id: str, err: str | None, sent: str):
        if err:
            return _client_view_page(hit[0], hit[1], link_id, err, ok=False, status=400)
        return Response(status_code=303, headers={"Location": f"/r/{link_id}?sent={sent}", **review_links.SECURITY_HEADERS})

    @app.post("/r/{link_id}/notes", include_in_schema=False)
    async def review_notes(link_id: str, request: Request):
        hit, form = await _client_form(link_id, request)
        if hit is None:
            return _gone()
        if review_links.review_copy(hit[0]) is None:
            return _after_post(hit, link_id, "The reel isn't ready for notes yet.", "")
        err = review_links.add_note(projects_root(), hit[0], link_id, str(form.get("name") or ""), str(form.get("text") or ""))
        return _after_post(hit, link_id, err, "1")

    @app.post("/r/{link_id}/checkin", include_in_schema=False)
    async def review_checkin(link_id: str, request: Request):
        hit, form = await _client_form(link_id, request)
        if hit is None:
            return _gone()
        err = review_links.add_checkin_answer(projects_root(), hit[0], link_id, [str(x) for x in form.getlist("yes")],
                                              str(form.get("note") or ""), str(form.get("name") or ""))
        return _after_post(hit, link_id, err, "checkin")

    @app.post("/r/{link_id}/hook", include_in_schema=False)
    async def review_hook_pick(link_id: str, request: Request):
        hit, form = await _client_form(link_id, request)
        if hit is None:
            return _gone()
        err = review_links.add_hook_pick(projects_root(), hit[0], link_id, str(form.get("option") or ""), str(form.get("name") or ""))
        return _after_post(hit, link_id, err, "hook")


def create_client_app(projects_root: Path) -> FastAPI:
    """Only the client pages. Anything else is a plain 404 (no API, no web app, no docs)."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    add_client_routes(app, lambda: projects_root)

    @app.api_route("/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"], include_in_schema=False)
    def nothing_else(rest: str):
        return Response(status_code=404, headers=review_links.SECURITY_HEADERS)

    return app
