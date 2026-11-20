"""Review links: a private page for the client with the review copy and a notes box, expiring after a set time.

- A link id is 24 random URL-safe bytes; the link opens `/r/<id>` without the studio token, and that page can
  only see one thing: this project's watermarked review copy (export/review/review.mp4). Nothing else is served.
- Links live in one per-install index (<projects root>/.review_links.json) so a lookup never scans projects.
- The client's notes go to <project>/client/review_notes.jsonl; the owner reads them in the Studio and sends them
  to the Editor with the usual client-notes flow (the page never triggers an edit by itself).
- The studio listens on 127.0.0.1 only, so a link works from outside this Mac only if the owner exposes it on
  purpose (for example with a tunnel). The page says nothing about other projects.
"""

from __future__ import annotations

import html
import json
import re
import secrets
import threading
import time
from pathlib import Path

from reel.workspace import atomic_write_json

LINK_ID = re.compile(r"[A-Za-z0-9_-]{24,64}")
MAX_HOURS = 24 * 30
MAX_NOTE_CHARS = 4000
MAX_NAME_CHARS = 80
MAX_NOTES_PER_LINK = 200
REVIEW_COPY = Path("export") / "review" / "review.mp4"

_lock = threading.Lock()


def _index_path(root: Path) -> Path:
    return root / ".review_links.json"


def _load(root: Path) -> dict:
    try:
        data = json.loads(_index_path(root).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _notes_path(ws: Path) -> Path:
    return ws / "client" / "review_notes.jsonl"


def review_copy(ws: Path) -> Path | None:
    p = ws / REVIEW_COPY
    return p if p.is_file() and not p.is_symlink() else None


FINAL = Path("render") / "final.mp4"
WATERMARK = "REVIEW COPY · NOT FOR POSTING"


def can_make(ws: Path) -> bool:
    return review_copy(ws) is not None or (ws / FINAL).is_file() or pending_checkin(ws) is not None or pending_hook(ws) is not None


# ------------------------------------------------------------------ before the render: story check-in (3a.1) and hook A/B (G1.6)
# The client only suggests: answers are recorded, stamped with what they answered, and the owner applies them in the Studio.

CHOICES = Path("client") / "review_choices.jsonl"
HOOK_OPTION = re.compile(r"[AB]")


def _read(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def pending_checkin(ws: Path) -> dict | None:
    c = _read(ws / "plan" / "checkin.json")
    return c if c and c.get("status") == "open" else None


def pending_hook(ws: Path) -> dict | None:
    pv = _read(ws / "export" / "preview" / "preview.json")
    return pv if pv and not pv.get("chosen") and len(pv.get("options") or {}) >= 2 else None


def hook_stamp(pv: dict) -> str:
    """Identifies one set of hook previews: a pick for an older set is never offered for a newer one."""
    import hashlib

    return hashlib.sha256(json.dumps(pv.get("options"), sort_keys=True).encode()).hexdigest()[:16]


def hook_copy(ws: Path, option: str) -> Path | None:
    if not HOOK_OPTION.fullmatch(option or ""):
        return None
    p = ws / "export" / "review" / f"hook_{option}.mp4"
    return p if p.is_file() and not p.is_symlink() else None


def ensure_hook_copies(ws: Path) -> list[str]:
    """Small watermarked copies of the hook previews (the full-quality previews are never served)."""
    pv = pending_hook(ws)
    made = []
    for opt in sorted((pv or {}).get("options", {})):
        if not HOOK_OPTION.fullmatch(opt):
            continue
        src = ws / "export" / "preview" / f"hook_{opt}.mp4"
        dst = ws / "export" / "review" / f"hook_{opt}.mp4"
        if not src.is_file():
            continue
        if not dst.is_file() or dst.stat().st_mtime < src.stat().st_mtime:
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(f".hook_{opt}.tmp.mp4")
            try:
                _transcode(src, tmp)
                tmp.replace(dst)
            finally:
                tmp.unlink(missing_ok=True)
        made.append(opt)
    return made


def refresh_copies(ws: Path) -> None:
    """Owner side only (never on a client request): remake the watermarked copies the client page may show."""
    if (ws / FINAL).is_file():
        ensure_review_copy(ws)
    if pending_hook(ws):
        ensure_hook_copies(ws)


def client_view(ws: Path) -> dict:
    ci, pv = pending_checkin(ws), pending_hook(ws)
    hook = sorted(o for o in (pv or {}).get("options", {}) if hook_copy(ws, o)) if pv else []
    return {"checkin": ci, "hook": hook if len(hook) >= 2 else [], "reel": review_copy(ws) is not None}


def _append_choice(root: Path, ws: Path, link_id: str, entry: dict) -> str | None:
    with _lock:
        data = _load(root)
        link = data.get(link_id)
        if not link:
            return "This link no longer works."
        if link.get("notes", 0) >= MAX_NOTES_PER_LINK:
            return "This link has reached its limit of answers. Ask for a new link."
        f = ws / CHOICES
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": time.time(), "link": link_id[:8], **entry}, ensure_ascii=False) + "\n")
        link["notes"] = link.get("notes", 0) + 1
        atomic_write_json(_index_path(root), data)
    return None


def add_checkin_answer(root: Path, ws: Path, link_id: str, yes: list[str], note: str, name: str) -> str | None:
    ci = pending_checkin(ws)
    if ci is None:
        return "The story has already been settled. Thanks!"
    ids = {q["id"] for q in ci.get("questions", [])}
    yes = [y for y in dict.fromkeys(yes) if y]
    if any(y not in ids for y in yes):
        return "Those suggestions have changed. Reload the page and answer again."
    note = (note or "").strip()
    if len(note) > MAX_NOTE_CHARS:
        return f"That note is too long (max {MAX_NOTE_CHARS} characters)."
    return _append_choice(root, ws, link_id, {"kind": "checkin", "story_fp": ci.get("story_fp"), "yes": yes, "note": note,
                                               "name": " ".join((name or "").split())[:MAX_NAME_CHARS]})


def add_hook_pick(root: Path, ws: Path, link_id: str, option: str, name: str) -> str | None:
    pv = pending_hook(ws)
    if pv is None:
        return "The look has already been picked. Thanks!"
    if option not in (pv.get("options") or {}) or not HOOK_OPTION.fullmatch(option or ""):
        return "Pick A or B."
    return _append_choice(root, ws, link_id, {"kind": "hook", "stamp": hook_stamp(pv), "option": option,
                                               "name": " ".join((name or "").split())[:MAX_NAME_CHARS]})


def choices(ws: Path) -> list[dict]:
    out = []
    try:
        for line in (ws / CHOICES).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def current_choices(ws: Path) -> dict:
    """The client's latest answer to what is open right now (an answer to an older check-in or preview set is not offered)."""
    ci, pv = pending_checkin(ws), pending_hook(ws)
    out: dict = {"checkin": None, "hook": None}
    for c in choices(ws):
        if c.get("kind") == "checkin" and ci and c.get("story_fp") == ci.get("story_fp"):
            out["checkin"] = {k: c.get(k) for k in ("at", "yes", "note", "name")}
        if c.get("kind") == "hook" and pv and c.get("stamp") == hook_stamp(pv):
            out["hook"] = {k: c.get(k) for k in ("at", "option", "name")}
    return out


def _transcode(src: Path, dst: Path) -> None:
    """Small (960 px tall), watermarked H.264 copy. Falls back to a plain small copy if this ffmpeg lacks drawtext."""
    from reel import tools

    scale = "scale=-2:960:flags=bicubic"
    mark = (f"drawtext=text='{WATERMARK}':fontcolor=white@0.45:fontsize=h/30:x=(w-text_w)/2:y=h*0.06:"
            "shadowcolor=black@0.5:shadowx=2:shadowy=2")
    base = ["-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"]
    try:
        tools.ffmpeg([*base, "-vf", f"{scale},{mark}", str(dst)], timeout=600)
    except tools.ToolError:
        tools.ffmpeg([*base, "-vf", scale, str(dst)], timeout=600)


def ensure_review_copy(ws: Path) -> Path:
    """The review copy, made (or remade after a new render) from render/final.mp4. Raises FileNotFoundError without a render."""
    final = ws / FINAL
    have = review_copy(ws)
    if have is not None and (not final.is_file() or have.stat().st_mtime >= final.stat().st_mtime):
        return have
    if not final.is_file():
        raise FileNotFoundError(str(final))
    dst = ws / REVIEW_COPY
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(".review.tmp.mp4")
    try:
        _transcode(final, tmp)
        tmp.replace(dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst


def public(link_id: str, link: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    state = "revoked" if link.get("revoked") else "expired" if link["expires"] <= now else "active"
    return {"id": link_id, "path": f"/r/{link_id}", "created": link["created"], "expires": link["expires"], "state": state,
            "notes": link.get("notes", 0)}


def create(root: Path, pid: str, hours: float) -> dict:
    hours = max(1.0, min(float(hours), MAX_HOURS))
    link_id = secrets.token_urlsafe(24)
    now = time.time()
    link = {"project": pid, "created": now, "expires": now + hours * 3600, "revoked": False, "notes": 0}
    with _lock:
        data = _load(root)
        data[link_id] = link
        atomic_write_json(_index_path(root), data)
    return public(link_id, link, now)


def for_project(root: Path, pid: str) -> list[dict]:
    links = [public(i, link) for i, link in _load(root).items() if link.get("project") == pid]
    return sorted(links, key=lambda x: -x["created"])


def revoke(root: Path, pid: str, link_id: str) -> bool:
    with _lock:
        data = _load(root)
        link = data.get(link_id)
        if not link or link.get("project") != pid:
            return False
        link["revoked"] = True
        atomic_write_json(_index_path(root), data)
    return True


def resolve(root: Path, link_id: str) -> tuple[str, dict] | None:
    """The project id and link for an id that is well formed, known, not revoked and not expired; else None."""
    if not LINK_ID.fullmatch(link_id or ""):
        return None
    link = _load(root).get(link_id)
    if not link or link.get("revoked") or link["expires"] <= time.time():
        return None
    return link["project"], link


def add_note(root: Path, ws: Path, link_id: str, name: str, text: str) -> str | None:
    """Append the client's note. Returns an error message for the page, or None when saved."""
    text = (text or "").strip()
    name = " ".join((name or "").split())[:MAX_NAME_CHARS]
    if not text:
        return "Write a note first."
    if len(text) > MAX_NOTE_CHARS:
        return f"That note is too long (max {MAX_NOTE_CHARS} characters)."
    with _lock:
        data = _load(root)
        link = data.get(link_id)
        if not link:
            return "This link no longer works."
        if link.get("notes", 0) >= MAX_NOTES_PER_LINK:
            return "This link has reached its limit of notes. Ask for a new link."
        f = _notes_path(ws)
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": time.time(), "link": link_id[:8], "name": name, "text": text}, ensure_ascii=False) + "\n")
        link["notes"] = link.get("notes", 0) + 1
        atomic_write_json(_index_path(root), data)
    return None


def notes(ws: Path) -> list[dict]:
    out = []
    try:
        for line in _notes_path(ws).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


# ------------------------------------------------------------------ the client page (self-contained; no studio app)

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def csp(nonce: str) -> str:
    return (f"default-src 'none'; media-src 'self'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")


_STYLE = """
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0F1012;color:#ECEDEE;font:14px/20px Inter,system-ui,sans-serif}
main{max-width:960px;margin:0 auto;padding:32px 16px;display:grid;gap:32px;grid-template-columns:minmax(0,360px) minmax(0,1fr)}
@media (max-width:760px){main{grid-template-columns:1fr}}
h1{font-size:20px;line-height:28px;font-weight:600;margin:0}p{margin:0}.meta{font-size:12px;line-height:16px;color:#90949C}
.well{background:#08090A;border-radius:8px;padding:12px;display:flex;justify-content:center}video{width:100%;max-height:70vh;border-radius:4px;background:#000}
label{display:block;font-size:12px;color:#A9ACB2;margin:16px 0 6px}input,textarea{width:100%;background:#1D1F23;color:#ECEDEE;border:1px solid #666A72;border-radius:4px;padding:8px 12px;font:inherit}
textarea{min-height:140px;resize:vertical;font-family:"JetBrains Mono",ui-monospace,monospace;font-size:13px}
input:focus,textarea:focus,button:focus-visible{outline:2px solid #E8A33D;outline-offset:2px}
.row{display:flex;gap:8px;align-items:center;margin-top:12px;flex-wrap:wrap}
button{height:36px;padding:0 16px;border-radius:4px;font:500 13px/18px Inter,system-ui,sans-serif;cursor:pointer;border:1px solid #3A3E45;background:#1D1F23;color:#ECEDEE}
button.primary{background:#E8A33D;color:#1A1305;border-color:transparent}.ok{color:#3CCB7F}.err{color:#F5606C}
hr{border:0;border-top:1px solid #2A2D32;margin:24px 0}main.gone{display:block;max-width:520px;padding-top:96px}.mt{margin-top:8px}
main.solo{grid-template-columns:minmax(0,560px)}h2{font-size:16px;line-height:24px;font-weight:600;margin:0 0 4px}
.two{gap:12px}.two figure{margin:0;flex:1}.two figcaption{text-align:center;font-size:12px;color:#A9ACB2;margin-top:4px}
ol.lines{margin:12px 0;padding-left:20px;display:grid;gap:6px}ol.lines .meta{display:inline-block;min-width:56px}
label.tick{display:flex;gap:8px;align-items:flex-start;color:#ECEDEE;font-size:14px;margin:8px 0}label.tick input{width:auto;margin-top:3px}
"""

_SCRIPT = """
const v=document.getElementById('v'),t=document.getElementById('note'),b=document.getElementById('stamp');
const fmt=s=>{const t=Math.floor(s*10)/10,m=Math.floor(t/60),r=(t%60).toFixed(1);return m+':'+r.padStart(4,'0')};
v.addEventListener('timeupdate',()=>{b.textContent='Add time '+fmt(v.currentTime)});
b.addEventListener('click',()=>{const s=fmt(v.currentTime)+' ';const i=t.selectionStart;
const before=t.value.slice(0,i),pre=before&&!before.endsWith('\\n')?'\\n':'';t.value=before+pre+s+t.value.slice(i);
t.focus();t.selectionStart=t.selectionEnd=i+pre.length+s.length;v.pause()});
"""


_NAME_FIELD = (f'<label for="name">Your name (optional)</label>'
               f'<input id="name" name="name" maxlength="{MAX_NAME_CHARS}" autocomplete="name">')


def _checkin_block(ci: dict, link_id: str) -> str:
    """The story in plain words, the suggestions as tick boxes (the engine's reasons stay internal), a note box."""
    e = html.escape
    def when(i: int, x: dict) -> str:
        return "Opening" if i == 0 else f"{float(x.get('seconds') or 0):.0f} s"

    lines = "".join(f'<li><span class="meta">{when(i, x)}</span> {e(str(x.get("text", "")))}</li>' for i, x in enumerate(ci.get("lines", [])))
    qs = "".join(f'<label class="tick"><input type="checkbox" name="yes" value="{e(q["id"])}"> {e(str(q.get("text", "")))}</label>'
                 for q in ci.get("questions", []))
    return f"""<h2>Check the story</h2>
<p class="meta">Nothing has been rendered yet. This is the order the reel will tell the story in ({ci.get("total_s", 0):.0f} s of speech).</p>
<ol class="lines">{lines}</ol>
<form method="post" action="/r/{link_id}/checkin">
{f'<p class="meta mt">Suggestions (tick the ones you agree with):</p>{qs}' if qs else ''}
<label for="cnote">Anything else to change in the story? (optional)</label>
<textarea id="cnote" name="note" maxlength="{MAX_NOTE_CHARS}" placeholder="end on the result&#10;don't mention the price"></textarea>
{_NAME_FIELD}
<div class="row"><button class="primary" type="submit">Send my answers</button></div>
</form>"""


def _hook_block(options: list[str], link_id: str) -> str:
    radios = "".join(f'<label class="tick"><input type="radio" name="option" value="{o}" required> Look {o}</label>' for o in options)
    return f"""<h2>Pick the look</h2>
<p class="meta">The opening seconds in two looks (captions and colour). The full reel will be made in the one picked.</p>
<form method="post" action="/r/{link_id}/hook">
{radios}
{_NAME_FIELD}
<div class="row"><button class="primary" type="submit">Send my pick</button></div>
</form>"""


def _notes_block(link_id: str) -> str:
    return f"""<form method="post" action="/r/{link_id}/notes">
<label for="note">Your notes, one per line. Start a line with a time to point at a moment.</label>
<textarea id="note" name="text" maxlength="{MAX_NOTE_CHARS}" placeholder="0:12 make this faster&#10;0:31 spell the doctor's name right&#10;love the ending" required></textarea>
<div class="row"><button type="button" id="stamp">Add time 0:00.0</button><span class="meta">pauses the video and adds the exact moment</span></div>
{_NAME_FIELD}
<div class="row"><button class="primary" type="submit">Send notes</button></div>
</form>"""


def page(title: str, link: dict, nonce: str, link_id: str, flash: str = "", flash_ok: bool = True, view: dict | None = None) -> str:
    """The client page. `view` (client_view) decides what shows: the reel and a notes box once rendered; before that the
    hook A/B pick and/or the story check-in; otherwise a note that the edit is in progress."""
    view = view if view is not None else {"reel": True, "checkin": None, "hook": []}
    left_h = max(0, link["expires"] - time.time()) / 3600
    left = f"{left_h:.0f} hours" if left_h >= 2 else "less than 2 hours"
    msg = f'<p class="{"ok" if flash_ok else "err"}" role="status">{html.escape(flash)}</p>' if flash else ""
    if view.get("reel"):
        media = f'<section class="well" aria-label="Reel"><video id="v" src="/r/{link_id}/video" controls playsinline preload="metadata"></video></section>'
        what, body, script = "Review copy (small and watermarked)", _notes_block(link_id), f'<script nonce="{nonce}">{_SCRIPT}</script>'
    else:
        hook = view.get("hook") or []
        media = ('<section class="well two" aria-label="The two looks">'
                 + "".join(f'<figure><video src="/r/{link_id}/hook/{o}" controls playsinline preload="metadata"></video><figcaption>Look {o}</figcaption></figure>'
                           for o in hook) + "</section>") if hook else ""
        parts = [_hook_block(hook, link_id)] if hook else []
        if view.get("checkin"):
            parts.append(_checkin_block(view["checkin"], link_id))
        body = "<hr>".join(parts) or '<p class="meta mt">The edit is in progress. Open this link again later to watch the reel.</p>'
        what, script = "Before the full edit", ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Review · {html.escape(title)}</title><style nonce="{nonce}">{_STYLE}</style></head>
<body><main class="{'' if media else 'solo'}">
{media}
<section>
<h1>{html.escape(title)}</h1>
<p class="meta">{what} · this link expires in {left}</p>
{msg}
<hr>
{body}
</section></main>{script}</body></html>"""


def gone_page(nonce: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Link expired</title><style nonce="{nonce}">{_STYLE}</style></head>
<body><main class="gone"><h1>This review link no longer works</h1>
<p class="meta mt">It has expired or was turned off. Ask for a new link.</p></main></body></html>"""
