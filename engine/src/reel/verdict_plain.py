"""One plain sentence per quality check for the Review screen (UI plan A1, roadmap G1.7).

The engine's gate details (`cut_in_word: 4 cut(s) inside a word: 0:16.96 start of v_k06.3 …`) stay available as
"details"; the owner first reads what is wrong, why it matters and what happens next, with the timecodes as links.
"""

from __future__ import annotations

# gate → (short title, sentence when it fails). {n} = number of places.
PLAIN: dict[str, tuple[str, str]] = {
    "frame_count": ("Length", "The rendered reel has the wrong number of frames — re-render before sending."),
    "loudness": ("Loudness", "The sound level is outside the platform target (−14 LUFS) — it will play too quiet or distort."),
    "proof_words": ("Caption words to check", "{n} caption word(s) the speech recogniser was unsure of — confirm or correct them."),
    "brief": ("Client brief", "Something the brief asks for is missing (a must-keep line or the call to action), or a banned claim is in."),
    "numbers": ("Numbers on screen", "{n} on-screen number(s) don't match what is said — a wrong number is the most visible mistake."),
    "dead_air": ("Silence", "{n} stretch(es) with no speech longer than 1.5 s — viewers scroll away in silence."),
    "frozen": ("Frozen picture", "{n} place(s) where the picture stops moving for over 3 s."),
    "black": ("Black frames", "{n} stretch(es) of black picture inside the reel."),
    "caption_contrast": ("Caption readability", "{n} caption page(s) are hard to read against the picture behind them."),
    "caption_over_face": ("Captions on the face", "{n} caption page(s) cover the speaker's face."),
    "safe_zone": ("Captions under the app buttons", "{n} caption page(s) sit where Instagram's buttons and caption text will cover them."),
    "reading_speed": ("Reading speed", "Captions go by faster than people can read in one stretch."),
    "face_cut": ("Face cropped", "{n} shot(s) crop the speaker's face at the vertical frame's edge."),
    "cut_pop": ("Clicks at cuts", "{n} cut(s) have an audible click or pop."),
    "cut_flash": ("Flashes at cuts", "{n} cut(s) flash a frame of the wrong picture."),
    "cut_in_word": ("Cuts inside words", "{n} cut(s) clip the start or end of a word."),
    "duration_match": ("Length vs the brief", "The reel's length is outside the target the brief asks for."),
    "pace": ("Pace", "The cut rhythm is off from the reference reel: {detail}."),
    "static_stretch": ("Long unchanged stretch", "One stretch goes too long with no cut, punch-in or cutaway: {detail}."),
    "broll_repeat": ("Repeated cutaway", "The same (or a near-identical) b-roll clip appears twice: {detail}."),
    "client_style_drift": ("Unlike this client's reels", "This reel looks different from the ones the client approved: {detail}."),
}


def explain(gates: list[dict]) -> list[dict]:
    """For every gate that did not pass: title, one sentence, timecodes (jump links), status (fail | warn), raw detail."""
    out = []
    for g in gates:
        if g.get("ok", g.get("status") == "pass"):
            continue
        name = g.get("gate") or g.get("name") or "?"
        at = list(g.get("at") or [])
        title, sentence = PLAIN.get(name, (name.replace("_", " ").capitalize(), "{detail}"))
        n = len(at) or len((g.get("measured") or {}).get("open", []) or (g.get("measured") or {}).get("checks", [])) or 1
        status = g.get("status") or ("fail" if g.get("mode") == "block" else "warn")
        out.append({"gate": name, "status": status, "title": title, "sentence": sentence.format(n=n, detail=g.get("detail", "")),
                    "at": at[:12], "detail": g.get("detail", "")})
    return sorted(out, key=lambda x: (x["status"] != "fail", x["title"]))
