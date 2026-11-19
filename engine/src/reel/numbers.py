"""Numbers in on-screen text versus numbers in the speech (roadmap G1.2: the wrong-number check).

`parse(text)` reads how numbers are written and said in Indian reels: digits with Indian or Western grouping
(5,00,000 / 500,000), decimals, %, ₹/Rs/INR/$, k / L / lakh / Cr / crore / million / billion, English number
words, Hindi number words 1–100 in Latin and Devanagari script with sau / hazaar / lakh / crore, dedh / dhai /
saadhe / sawa / paune, and Devanagari digits.

Each number says whether it is *confident*. Years, ordinals, times, "24/7", "10x", ranges, product names ("COVID-19",
"5G") and words that double as ordinary words ("do", "teen", "saath", "one") are not: the check only raises an error
when the on-screen number is confident, a number was spoken nearby, and none of them match — every false error
costs a paid Editor retry.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


@dataclass(frozen=True)
class Num:
    value: Decimal
    confident: bool
    raw: str
    step: Decimal  # the precision shown: "2.5 crore" → 0.1 crore = 1,000,000; spoken "2.47 crore" rounds to it


EN_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
            "seventeen": 17, "eighteen": 18, "nineteen": 19}
EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}

# Hindi 1–100: Devanagari spellings, then the common Latin (Hinglish) spellings
HI_DEVA = ("एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस बाईस तेईस चौबीस "
           "पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस "
           "बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन "
           "अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर "
           "छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानबे "
           "बानबे तिरानबे चौरानबे पचानबे छियानबे सत्तानबे अट्ठानबे निन्यानबे").split()
HI_LATIN = ("ek do teen char paanch chhah saat aath nau das gyarah barah terah chaudah pandrah solah satrah atharah unnis bees "
            "ikkis baais teis chaubis pachchis chhabbis sattais atthais untis tees iktis battis taintis chauntis paintis chhattis "
            "saintis adtis untalis chalis iktalis bayalis taintalis chauvalis paintalis chhiyalis saintalis adtalis unchas pachas "
            "ikyavan bavan tirpan chauvan pachpan chhappan sattavan atthavan unsath saath iksath basath tirsath chaunsath painsath "
            "chhiyasath sadsath adsath unhattar sattar ikhattar bahattar tihattar chauhattar pachhattar chhihattar sathattar "
            "athhattar unasi assi ikyasi bayasi tirasi chaurasi pachasi chhiyasi sattasi athasi navasi nabbe ikyanve baanve "
            "tiranve chauranve pachanve chhiyanve sattanve atthanve ninyanve").split()
HI_VARIANTS = {"पांच": 5, "छः": 6, "छे": 6, "पन्द्रह": 15, "उनासी": 79, "बानवे": 92, "तिरानवे": 93, "चौरानवे": 94, "पचानवे": 95,
               "छियानवे": 96, "सत्तानवे": 97, "अट्ठानवे": 98, "निन्यानवे": 99, "chaar": 4, "panch": 5, "paach": 5, "chhe": 6, "che": 6,
               "chah": 6, "aat": 8, "dus": 10, "gyara": 11, "baara": 12, "bara": 12, "tera": 13, "chauda": 14, "pandra": 15,
               "sola": 16, "satra": 17, "athara": 18, "unees": 19, "ikkees": 21, "bais": 22, "pachees": 25,
               "pachis": 25, "chabbis": 26, "chalees": 40, "pachaas": 50, "assee": 80}
WORD_UNITS: dict[str, int] = {**EN_UNITS, **{w: n for n, w in enumerate(HI_DEVA, 1)}, **{w: n for n, w in enumerate(HI_LATIN, 1)},
                              **HI_VARIANTS}
# words that are numbers but also ordinary words in Hinglish/English speech: candidates, never confident on their own
AMBIGUOUS_WORDS = {"one", "do", "teen", "saath", "bees", "char", "che", "nau", "ek", "das", "tees", "sola", "bara", "tera", "a"}
FRACTIONS = {"dedh": Decimal("1.5"), "derh": Decimal("1.5"), "डेढ़": Decimal("1.5"), "dhai": Decimal("2.5"), "dhaai": Decimal("2.5"),
             "ढाई": Decimal("2.5")}
MODIFIERS = {"saadhe": Decimal("0.5"), "sade": Decimal("0.5"), "saade": Decimal("0.5"), "साढ़े": Decimal("0.5"),
             "sawa": Decimal("0.25"), "सवा": Decimal("0.25"), "paune": Decimal("-0.25"), "पौने": Decimal("-0.25")}
SCALES = {"hundred": 100, "sau": 100, "सौ": 100, "thousand": 1000, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "हज़ार": 1000,
          "हजार": 1000, "lakh": 10**5, "lakhs": 10**5, "lac": 10**5, "lacs": 10**5, "लाख": 10**5, "crore": 10**7, "crores": 10**7,
          "करोड़": 10**7, "करोड": 10**7, "million": 10**6, "millions": 10**6, "billion": 10**9, "billions": 10**9, "arab": 10**9}
SHORT_SCALES = {"k": 1000, "l": 10**5, "cr": 10**7, "m": 10**6, "mn": 10**6, "b": 10**9, "bn": 10**9}  # only right after digits
CONNECTORS = {"and", "aur", "point"}

_SUFFIX = r"(?:k|l|cr|m|mn|b|bn|lakh|lakhs|lac|lacs|crore|crores)"
_AMBIG_PATTERNS = [re.compile(p, re.I) for p in (
    r"\b\d{1,2}:\d{2}\b",  # a time
    r"\b\d+/\d+\b",  # 24/7, 1/2
    r"\b\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?\b",  # a range
    r"\b\d+(?:st|nd|rd|th)\b",  # an ordinal
    r"\b\d+(?:\.\d+)?x\b",  # 10x
    r"\b[^\W\d_]+-?\d+\b",  # COVID-19, iPhone15
    rf"\b\d+(?:\.\d+)?(?!{_SUFFIX}\b)[^\W\d_\s]+",  # 5G, 4K: digits glued to letters that are not a scale
)]
_TOKEN = re.compile(r"\d+(?:\.\d+)?|%|[^\s\d%.,!?;:\"'“”‘’()\[\]/–—\-₹$#@*]+")


def _dec(s: str) -> Decimal | None:
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _prepare(text: str) -> tuple[str, list[Num]]:
    """Normalise digits and grouping; pull out the ambiguous forms (they still count as spoken candidates)."""
    t = text.translate(DEVA_DIGITS).replace(" ", " ")
    t = re.sub(r"\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b", lambda m: m.group(0).replace(",", ""), t)  # 5,00,000 / 500,000
    ambiguous: list[Num] = []
    for pat in _AMBIG_PATTERNS:
        def keep(m: re.Match) -> str:
            first = re.search(r"\d+(?:\.\d+)?", m.group(0))
            if first:
                ambiguous.append(Num(Decimal(first.group(0)), False, m.group(0), Decimal(1)))
            return " ; "
        t = pat.sub(keep, t)
    t = re.sub(rf"(\d)({_SUFFIX})\b", r"\1 \2", t, flags=re.I)  # 50k → 50 k, 2.5cr → 2.5 cr
    return t, ambiguous


PERCENT = {"%", "percent", "per", "cent", "pratishat", "प्रतिशत", "फीसदी", "feesadi"}
_DIGITS = re.compile(r"\d+(?:\.\d+)?")


def _nfc(s: str) -> str:
    """ज़ / ड़ exist precomposed and decomposed; compare one form."""
    return unicodedata.normalize("NFC", s)


WORD_UNITS = {_nfc(k): v for k, v in WORD_UNITS.items()}
SCALES = {_nfc(k): v for k, v in SCALES.items()}
FRACTIONS = {_nfc(k): v for k, v in FRACTIONS.items()}
MODIFIERS = {_nfc(k): v for k, v in MODIFIERS.items()}
PERCENT = {_nfc(k) for k in PERCENT}


def _is_unit(tok: str) -> bool:
    return tok in WORD_UNITS or tok in EN_TENS


def parse(text: str) -> list[Num]:
    t, out = _prepare(text or "")
    toks = [_nfc(x.casefold()) for x in _TOKEN.findall(t)]
    i, n = 0, len(toks)
    while i < n:
        start = i
        total = Decimal(0)
        current: Decimal | None = None  # the part not yet multiplied by a big scale
        atom_step = Decimal(1)  # precision of `current`
        step: Decimal | None = None  # precision of the whole number once a big scale applied
        plus, last_scale, words_only = Decimal(0), None, True
        raw: list[str] = []
        while i < n:
            tok, nxt = toks[i], (toks[i + 1] if i + 1 < n else "")
            if _DIGITS.fullmatch(tok):
                if current is not None:
                    break  # two numbers in a row are two numbers
                current = Decimal(tok)
                atom_step = Decimal(1).scaleb(-len(tok.split(".")[1])) if "." in tok else Decimal(1)
                words_only = False
            elif tok in MODIFIERS and current is None and (_is_unit(nxt) or _DIGITS.fullmatch(nxt or "x")):
                plus = MODIFIERS[tok]  # saadhe teen = 3.5, sawa do = 2.25, paune paanch = 4.75
                atom_step = Decimal("0.25")
            elif tok in FRACTIONS and current is None:
                current, atom_step = FRACTIONS[tok], Decimal("0.5")
            elif _is_unit(tok):
                v = Decimal(WORD_UNITS.get(tok, EN_TENS.get(tok, 0)))
                if current is None:
                    current = v
                    atom_step = min(atom_step, Decimal(1)) if plus else Decimal(1)
                elif tok in EN_UNITS and 20 <= current < 100 and current % 10 == 0 and v < 10:
                    current += v  # twenty five
                elif current >= 100 and current % 100 == 0 and v < 100:
                    current, atom_step = current + v, Decimal(1)  # one hundred (and) five
                else:
                    break
            elif tok == "a" and current is None and nxt in SCALES:
                current = Decimal(1)
            elif tok in SCALES or (tok in SHORT_SCALES and current is not None and not words_only):
                scale = Decimal(SCALES.get(tok) or SHORT_SCALES[tok])
                if current is None:
                    break  # "hundreds of", "lakhs of" are not numbers
                if scale == 100:  # sawa do sau = 2.25 × 100
                    current, plus, atom_step = (current + plus) * 100, Decimal(0), atom_step * 100
                else:
                    if last_scale is not None and scale >= last_scale:
                        break
                    total += (current + plus) * scale
                    step = atom_step * scale
                    current, plus, last_scale, atom_step = None, Decimal(0), scale, Decimal(1)
            elif tok in CONNECTORS and (current is not None or total) and _is_unit(nxt):
                pass
            elif tok in PERCENT:
                if current is None and not total:
                    break
            else:
                break
            raw.append(tok)
            i += 1
        if current is None and not total:
            i = max(i, start + 1)  # nothing numeric started here
            continue
        value = total + ((current + plus) if current is not None else 0)
        if current is not None:
            step = atom_step if step is None else min(step, atom_step)
        core = [r for r in raw if r not in PERCENT]
        lone_word = words_only and len(core) == 1 and core[0] in AMBIGUOUS_WORDS
        year = not words_only and len(core) == 1 and value == value.to_integral_value() and 1900 <= value <= 2099
        out.append(Num(value, not (lone_word or year), " ".join(raw), step or Decimal(1)))
    return out


def matches(shown: Num, spoken: Num) -> bool:
    """Equal, or the screen shows the spoken number rounded to the screen's precision ("4.97 crore" said, "5 crore" shown)."""
    if shown.value == spoken.value:
        return True
    return spoken.step < shown.step and abs(shown.value - spoken.value) <= shown.step / 2


def counter_text(text: str, value: float) -> str:
    """What a counter shows when it lands: its text with {n} filled in."""
    v = Decimal(str(value))
    s = f"{v.normalize():f}" if v != v.to_integral_value() else str(int(v))
    return (text or "{n}").replace("{n}", s)


def compare(shown_text: str, spoken_text: str) -> tuple[str, list[str]]:
    """'ok' | 'mismatch' (error: confident screen number, numbers were said, none match) | 'unspoken' (warning) — and details."""
    shown = [s for s in parse(shown_text) if s.confident]
    if not shown:
        return "ok", []
    spoken = parse(spoken_text)
    bad = [s for s in shown if not any(matches(s, p) for p in spoken)]
    if not bad:
        return "ok", []
    said = ", ".join(sorted({p.raw for p in spoken})) or "none"
    detail = [f"“{s.raw}” on screen" for s in bad]
    if any(p.confident for p in spoken):
        return "mismatch", [*detail, f"numbers said nearby: {said}"]
    return "unspoken", [*detail, "no number is said nearby" if not spoken else f"only unclear numbers said nearby: {said}"]
