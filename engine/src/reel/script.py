"""Hindi / Hinglish script handling (build step 8).

- `script_of`: devanagari | latin | other per token.
- `deva_to_roman`: built-in casual romaniser (no dependencies) — "क्या"→"kya", "है"→"hai",
  "नहीं"→"nahin". Good enough for scoring and as a caption fallback; a learned transliterator
  (IndicXlit) gives more natural spellings where installed.
- `key`: loose spelling key so engines that write the same Hinglish word differently
  ("kyaa"/"kya", "nahi"/"nahin", "hain"/"hai" stay distinct) are compared fairly.
"""

from __future__ import annotations

import re
import unicodedata

DEVA = re.compile(r"[ऀ-ॿ]")

_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
           "ऑ": "o", "ऍ": "e"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e"}
_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
         "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
         "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
         "ष": "sh", "स": "s", "ह": "h", "ळ": "l", "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f", "य़": "y"}
_NUKTA = "़"
_HALANT = "्"
_NASAL = {"ं": "n", "ँ": "n"}
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def script_of(token: str) -> str:
    if DEVA.search(token):
        return "devanagari"
    if any(ch.isalpha() for ch in token):
        return "latin"
    return "other"


# Common words whose casual Hinglish spelling the rules below would not produce.
_EXCEPTIONS = {"यह": "yeh", "वह": "woh", "यहाँ": "yahan", "वहाँ": "wahan", "मैं": "main", "हैं": "hain", "में": "mein",
               "नहीं": "nahin", "हाँ": "haan", "ये": "ye", "वो": "wo"}


def _roman_word(w: str) -> str:
    w = unicodedata.normalize("NFC", w).translate(_DIGITS)
    if w in _EXCEPTIONS:
        return _EXCEPTIONS[w]
    # syllables: [consonant cluster, vowel, inherent?]; nasal/visarga/other text go in a tail list per syllable
    syl: list[list] = []
    i, n = 0, len(w)
    cluster = ""
    while i < n:
        ch = w[i]
        if i + 1 < n and w[i + 1] == _NUKTA and ch + _NUKTA in _CONS:
            ch, i = ch + _NUKTA, i + 1
        if ch in _CONS:
            nxt = w[i + 1] if i + 1 < n else ""
            if nxt == _HALANT:  # conjunct: consonant without vowel joins the next one
                cluster += _CONS[ch]
                i += 2
                continue
            if nxt in _MATRAS:
                syl.append([cluster + _CONS[ch], _MATRAS[nxt], False, ""])
                cluster = ""
                i += 2
                continue
            syl.append([cluster + _CONS[ch], "a", True, ""])
            cluster = ""
        elif ch in _VOWELS:
            syl.append([cluster, _VOWELS[ch], False, ""])
            cluster = ""
        elif ch in _NASAL or ch == "ः":
            if syl:
                syl[-1][3] += _NASAL.get(ch, "h")
        elif ch not in (_HALANT, _NUKTA):
            syl.append([cluster + ch, "", False, ""])
            cluster = ""
        i += 1
    if cluster:
        syl.append([cluster, "", False, ""])
    # schwa deletion (Ohala): the final inherent 'a' is silent; then right to left, an inherent 'a'
    # between a vowel and a consonant+vowel is silent (kar-na → karna, aa-pa-ko → aapko, ma-ta-lab → matlab)
    if len(syl) > 1 and syl[-1][2] and not syl[-1][3]:
        syl[-1][1] = ""
    for k in range(len(syl) - 2, 0, -1):
        cur, prev, nxt = syl[k], syl[k - 1], syl[k + 1]
        if cur[2] and cur[1] and not cur[3] and prev[1] and nxt[0] and nxt[1]:
            cur[1] = ""
    s = "".join(c + v + t for c, v, _inh, t in syl)
    # casual spelling: final long 'aa' is written 'a' (kya, raha); 'ee' at the end → 'i' (nahi, bhi)
    s = re.sub(r"aa$", "a", s)
    s = re.sub(r"ee(n?)$", r"i\1", s)
    return s


def deva_to_roman(text: str) -> str:
    return " ".join(_roman_word(tok) if DEVA.search(tok) else tok for tok in text.split())


def key(token: str) -> str:
    """Loose comparison key for one token (any script)."""
    t = deva_to_roman(token).casefold()
    t = re.sub(r"[^a-z0-9]", "", t)
    for a, b in (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("w", "v"), ("ph", "f"), ("z", "j"),
                 ("q", "k"), ("ck", "k")):
        t = t.replace(a, b)
    t = t.replace("chch", "ch").replace("chh", "ch").replace("cch", "ch")  # achchha / accha / acha
    t = re.sub(r"(.)\1+", r"\1", t)  # doubled letters
    t = re.sub(r"(?<=[aeiou])n$", "", t)  # nahin/nahi, main/mai (final nasal)
    t = re.sub(r"(?<=[aeiou])h$", "", t)  # yeh → ye, woh → vo
    return t


def tokens(text: str) -> list[str]:
    """Words of a transcript, punctuation stripped, any script."""
    return [t for t in (re.sub(r"[^\wऀ-ॿ]", "", w) for w in text.split()) if t]


def mixed_ratio(text: str) -> float:
    """Share of Devanagari tokens — 0 = all Roman, 1 = all Devanagari."""
    toks = [t for t in tokens(text) if script_of(t) != "other"]
    return sum(script_of(t) == "devanagari" for t in toks) / len(toks) if toks else 0.0
