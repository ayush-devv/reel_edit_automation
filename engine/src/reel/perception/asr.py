"""Speech-to-text with word timing behind one interface (ADR-0007).

Default backend: mlx-whisper large-v3-turbo (MIT) — measured 4.6 s for 74 s of English on
the M5. The Hinglish/Hindi backend is chosen by the bake-off and registered here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from reel.schemas.perception import Word, WordTable

SUSPECT_US = 1_200_000
LOW_CONF = 0.5
EN_FILLERS = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "hmm", "hm", "mm", "mmm", "ah", "ahh"}
# Lexical fillers are often real words ("so", "like"); they are only *candidates* — Claude judges in context.
CANDIDATE_FILLERS = {"like", "basically", "actually", "literally", "matlab", "toh", "yaar", "accha", "acha", "haan", "bas", "मतलब", "तो", "यार"}


@dataclass
class RawWord:
    text: str
    start_s: float
    end_s: float
    prob: float


class Backend(Protocol):
    name: str

    def transcribe(self, wav: Path, language: str | None, prompt: str | None) -> tuple[list[RawWord], str | None]: ...


class MlxWhisper:
    def __init__(self, repo: str = "mlx-community/whisper-large-v3-turbo"):
        self.repo = repo
        self.name = f"mlx-whisper:{repo}"

    def transcribe(self, wav: Path, language: str | None, prompt: str | None) -> tuple[list[RawWord], str | None]:
        import mlx_whisper  # lazy: perception extra

        result = mlx_whisper.transcribe(
            str(wav), path_or_hf_repo=self.repo, word_timestamps=True, language=language,
            initial_prompt=prompt or None, condition_on_previous_text=False,
        )
        words = [
            RawWord(w["word"].strip(), float(w["start"]), float(w["end"]), float(w.get("probability", 1.0)))
            for seg in result.get("segments", []) for w in seg.get("words", [])
        ]
        return [w for w in words if w.text], result.get("language")


BACKENDS: dict[str, type] = {"mlx-whisper": MlxWhisper}


def _norm(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum() or ch == " ").strip()


def vocabulary_prompt(terms: list[str], limit: int = 60) -> str | None:
    """Names/brands from brief, brand kit and on-screen text, as a Whisper initial prompt."""
    seen, out = set(), []
    for t in terms:
        t = t.strip()
        if t and t.casefold() not in seen:
            seen.add(t.casefold())
            out.append(t)
    return ("Names: " + ", ".join(out[:limit]) + ".") if out else None


def to_words(raw: list[RawWord], clip: str, start_index: int, duration_us: int) -> list[Word]:
    """Clamp to the clip, force monotonic times, and flag fillers / suspects / low confidence."""
    words: list[Word] = []
    prev_start = 0
    for k, r in enumerate(raw):
        s = max(prev_start, min(int(round(r.start_s * 1e6)), duration_us))
        e = max(s + 1, min(int(round(r.end_s * 1e6)), duration_us))
        key = _norm(r.text)
        words.append(Word(
            i=start_index + k, clip=clip, text=r.text, start_us=s, end_us=e, prob=round(r.prob, 3),
            filler=key in EN_FILLERS, candidate_filler=key in CANDIDATE_FILLERS,
            suspect=(e - s) > SUSPECT_US, low_conf=r.prob < LOW_CONF,
        ))
        prev_start = s
    return words


AUTO_CORRECT = 0.85
SUGGEST = 0.5


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def apply_vocabulary(words: list[Word], vocabulary: list[str]) -> list[Word]:
    """Correct near-misses of known names; flag unconfirmed name-like words for the proof list.

    A misheard brand often has *high* ASR confidence ("DearMa" → "Dioma" at p≈0.9), so
    confidence alone is not enough (ADR-0021).
    """
    terms = sorted({t for term in vocabulary for t in term.split() if len(_norm(t)) >= 3}, key=str.casefold)
    out = []
    for k, w in enumerate(words):
        stripped = w.text.strip(".,!?;:\"'।॥")
        tail = w.text[len(stripped):] if w.text.startswith(stripped) else ""
        prev = words[k - 1].text if k else ""
        prev_is_filler = k > 0 and (words[k - 1].filler or _norm(prev) in EN_FILLERS)
        sentence_start = (k == 0 or prev.endswith((".", "?", "!", "।")) or words[k - 1].clip != w.clip
                          or (prev_is_filler and prev.endswith(",")))
        name_like = stripped[:1].isupper() and not sentence_start and stripped not in ("I", "I'm", "I'll", "I've")
        best, score = None, 0.0
        for t in terms:
            s = _similarity(stripped, t)
            if s > score:
                best, score = t, s
        update: dict = {}
        if best and score >= AUTO_CORRECT and _norm(stripped) != _norm(best):
            update = {"original_text": w.text, "text": best + tail, "vocab_suggestion": best}
        elif best and _norm(stripped) == _norm(best):
            pass  # confirmed by the vocabulary
        elif name_like or (best and score >= SUGGEST and len(_norm(stripped)) >= 4):
            if name_like or w.low_conf:
                update = {"vocab_suspect": True, "vocab_suggestion": best if score >= SUGGEST else None}
        out.append(w.model_copy(update=update) if update else w)
    return out


def transcribe_clips(clips: list[tuple[str, Path, int]], backend: Backend, *, language: str | None = None, vocabulary: list[str] | None = None) -> WordTable:
    """clips = [(clip_id, wav_path, duration_us)] in project order → one WordTable with global indices."""
    prompt = vocabulary_prompt(vocabulary or [])
    all_words: list[Word] = []
    detected = None
    for clip_id, wav, dur in clips:
        raw, lang = backend.transcribe(wav, language, prompt)
        detected = detected or lang
        all_words.extend(to_words(raw, clip_id, len(all_words), dur))
    return WordTable(language=language or detected, words=apply_vocabulary(all_words, vocabulary or []))
