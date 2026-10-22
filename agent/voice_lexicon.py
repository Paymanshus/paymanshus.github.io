"""
Word fixes for the voice pipeline, in one config: what the speech-to-text
mishears, and what the text-to-speech mispronounces.

Three layers, cheapest first:

1. STT_FIXES (free): regex corrections applied to the caller's final
   transcript before BM25 and the LLM see it. Seen in real calls: "Pimanshu"
   for Paymanshu, "shipment co captain" for Shipment CoCaptain. Only add
   patterns that can't be a real word in context ("mask" is a word, so Maersk
   isn't corrected from it).

2. STT_KEYTERMS (paid, off by default): Deepgram nova-3 keyterm prompting
   biases recognition toward these names. Deepgram bills it on top of normal
   streaming (about $0.0013/min per third-party pricing pages, roughly +17%),
   so it's behind VOICE_STT_KEYTERMS=true.

3. TTS_SPOKEN_FORMS (free): word -> what to send to Cartesia instead, applied
   only to the text going to TTS (the transcript and chat history keep the real
   spelling). Accents and hyphens fix most cases ("résumé"). For a word that
   still comes out wrong, Cartesia sonic-3 accepts inline phonemes
   (<<p|h|o|n|e|m|e|s>>, charsiu phoneset, from the Cartesia playground's
   phoneme tool) as the spoken form, or a pronunciation dictionary via
   CARTESIA_PRONUNCIATION_DICT_ID.

Case-insensitive, whole words only. Edit freely; nothing else needs changing.
"""

import os
import re

# Regex (case-insensitive, matched on word boundaries) -> correct text.
STT_FIXES: dict[str, str] = {
    r"p(?:i|ai|ee|y)\s?man\s?(?:shu|shoe|shoo|su)": "Paymanshu",
    r"pay\s?man\s?(?:shoe|shoo|su)": "Paymanshu",
    r"co[\s-]?captain": "CoCaptain",
    r"m(?:ea|e|a)rsk": "Maersk",
    r"lang\s?graph": "LangGraph",
    r"meta\s?flux|met\s?flux": "MetFlux",
}

# Names Deepgram should expect (only sent with VOICE_STT_KEYTERMS=true).
STT_KEYTERMS: list[str] = [
    "Paymanshu", "Maersk", "CoCaptain", "LangGraph", "Mphasis", "MetFlux",
    "Hike", "Amicus", "Awarathon", "NMIMS", "QLoRA", "vLLM",
]

# Word -> spoken form for Cartesia (case-insensitive whole words).
TTS_SPOKEN_FORMS: dict[str, str] = {
    "resume": "résumé",
    "resumes": "résumés",
    "CoCaptain": "Co-Captain",
    "QLoRA": "Q-Lora",
    "vLLM": "V-L-L-M",
    "NMIMS": "N-Mims",
    "MPSTME": "M-P-S-T-M-E",
    "IIT": "I-I-T",
    "SaaS": "sass",
    "MAE": "M-A-E",
}

USE_STT_KEYTERMS = os.environ.get("VOICE_STT_KEYTERMS", "false").lower() in ("1", "true", "yes")
CARTESIA_PRONUNCIATION_DICT_ID = os.environ.get("CARTESIA_PRONUNCIATION_DICT_ID", "").strip() or None

_STT_PATTERNS = [(re.compile(rf"\b{p}\b", re.IGNORECASE), fix) for p, fix in STT_FIXES.items()]


def fix_transcript(text: str) -> str:
    """Apply STT_FIXES to a caller transcript."""
    for pattern, fix in _STT_PATTERNS:
        text = pattern.sub(fix, text)
    return text


def _spoken_pattern(forms: dict[str, str]):
    if not forms:
        return None, {}
    keys = sorted(forms, key=len, reverse=True)  # longer keys win on overlap
    pattern = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, keys)) + r")(?![\w-])", re.IGNORECASE)
    return pattern, {k.lower(): v for k, v in forms.items()}


_SPOKEN_RE, _SPOKEN = _spoken_pattern(TTS_SPOKEN_FORMS)
_TRAILING_WORD = re.compile(r"[\w-]*\Z")


def spoken_form(text: str) -> str:
    """TTS_SPOKEN_FORMS applied to a whole string (whole words only, so
    "resume" changes but "resumed" doesn't)."""
    if _SPOKEN_RE is None:
        return text
    return _SPOKEN_RE.sub(lambda m: _SPOKEN[m.group(1).lower()], text)


async def spoken_forms_transform(text):
    """Streaming version for LiveKit's tts_text_transforms. LLM chunks split
    words anywhere, so the trailing (possibly unfinished) word is held back
    until the next chunk shows where it ends. LiveKit's built-in `replace`
    isn't used because it matches inside words ("MAE" in "Maersk")."""
    buf = ""
    async for chunk in text:
        buf += chunk
        cut = len(buf) - len(_TRAILING_WORD.search(buf).group())
        if cut > 0:
            yield spoken_form(buf[:cut])
            buf = buf[cut:]
    if buf:
        yield spoken_form(buf)


def tts_transforms() -> list:
    """LiveKit tts_text_transforms: the defaults plus the spoken forms."""
    return ["filter_markdown", "filter_emoji", spoken_forms_transform]
