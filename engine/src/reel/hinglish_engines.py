"""Hinglish ASR bake-off candidates beyond mlx-whisper (ADR-0007). Optional extra: `bakeoff`.

Facts checked 2026-11-18 (see docs/plan/step8-hinglish.md):
- Shruti (udgamlabs/Shruti, Apache-2.0, 55M) — Cactus engine, Devanagari Hindi + Latin English,
  native word timestamps. Trained on MUCS (in-domain advantage there; we score on owner clips).
- Oriserve Whisper-Hindi2Hinglish-Apex (Apache-2.0, large-v3-turbo fine-tune) — Roman Hinglish;
  ships without `alignment_heads`, so word timestamps use the turbo base heads (fit unverified —
  the bake-off's timing scores tell).
- IndicConformer Hindi (MIT) via the ungated ONNX CTC export + onnx-asr — Devanagari only;
  token timestamps merged into words.
Every adapter returns reel.perception.asr.RawWord lists like the mlx-whisper backend.
"""

from __future__ import annotations

import os
from pathlib import Path

from reel.perception.asr import RawWord

TURBO_HEADS = [[2, 4], [2, 11], [3, 3], [3, 6], [3, 11], [3, 14]]


class Shruti:
    name = "shruti"

    def __init__(self, repo: str = "udgamlabs/Shruti", filename: str = "shruti.cact"):
        self.repo, self.filename = repo, filename

    _model = None

    def transcribe(self, wav: Path, language: str | None, prompt: str | None) -> tuple[list[RawWord], str | None]:
        os.environ.setdefault("CACTUS_TELEMETRY", "0")
        if self._model is None:
            from cactus import Whistle  # cactus-compute
            from huggingface_hub import hf_hub_download

            self._model = Whistle(hf_hub_download(self.repo, self.filename))
        res = self._model.transcribe(str(wav), word_timestamps=True)
        words = res.get("words") if isinstance(res, dict) else getattr(res, "words", None)
        out = []
        for w in words or []:
            g = w.get if isinstance(w, dict) else (lambda k, d=None, _w=w: getattr(_w, k, d))
            text = str(g("word") or g("text") or "").strip()
            if text:
                out.append(RawWord(text, float(g("start", 0.0)), float(g("end", 0.0)), float(g("probability", g("prob", 1.0)) or 1.0)))
        return out, "hi"


class OriserveApex:
    name = "oriserve-apex"

    def __init__(self, repo: str = "Oriserve/Whisper-Hindi2Hinglish-Apex", heads: list[list[int]] | None = None):
        self.repo, self.heads = repo, heads or TURBO_HEADS
        self._pipe = None

    def _pipeline(self):
        if self._pipe is None:
            import torch
            from transformers import pipeline

            device = "mps" if torch.backends.mps.is_available() else "cpu"
            self._pipe = pipeline("automatic-speech-recognition", model=self.repo, device=device,
                                  torch_dtype=torch.float16 if device == "mps" else torch.float32)
            self._pipe.model.generation_config.alignment_heads = self.heads  # not shipped by the fine-tune
        return self._pipe

    def transcribe(self, wav: Path, language: str | None, prompt: str | None) -> tuple[list[RawWord], str | None]:
        import soundfile as sf

        audio, rate = sf.read(str(wav), dtype="float32")
        res = self._pipeline()({"raw": audio, "sampling_rate": rate}, return_timestamps="word", chunk_length_s=30,
                               generate_kwargs={"task": "transcribe"})
        out = []
        for ch in res.get("chunks", []):
            s, e = ch.get("timestamp", (None, None))
            text = ch.get("text", "").strip()
            if text and s is not None:
                out.append(RawWord(text, float(s), float(e if e is not None else s), 1.0))
        return out, "hi"


class IndicConformer:
    name = "indicconformer"

    def __init__(self, repo: str = "OpenVoiceOS/ai4bharat-indicconformer-hi-onnx"):
        self.repo = repo
        self._model = None

    def transcribe(self, wav: Path, language: str | None, prompt: str | None) -> tuple[list[RawWord], str | None]:
        import onnx_asr
        from huggingface_hub import snapshot_download

        if self._model is None:
            self._model = onnx_asr.load_model("nemo-conformer-ctc", snapshot_download(self.repo)).with_timestamps()
        res = self._model.recognize(str(wav))
        tokens = list(getattr(res, "tokens", None) or [])
        stamps = list(getattr(res, "timestamps", None) or [])
        return merge_tokens(tokens, stamps), "hi"


def merge_tokens(tokens: list[str], stamps: list[float], *, frame_s: float = 0.04) -> list[RawWord]:
    """SentencePiece tokens ('▁' starts a word) + per-token start times → words with start/end."""
    words: list[RawWord] = []
    for tok, t in zip(tokens, stamps):
        if tok.startswith("▁") or tok.startswith(" ") or not words:
            text = tok.lstrip("▁ ")
            if text:
                words.append(RawWord(text, float(t), float(t) + frame_s, 1.0))
            continue
        last = words[-1]
        words[-1] = RawWord(last.text + tok, last.start_s, float(t) + frame_s, last.prob)
    return [w for w in words if w.text]


def register() -> None:
    from reel import bakeoff

    bakeoff.EXTRA_ENGINES.update({"shruti": Shruti, "oriserve-apex": OriserveApex, "indicconformer": IndicConformer})
