"""
Pre-rendered speech for fixed lines (greetings, goodbyes): synthesize once,
cache the audio on disk, play it from disk forever after.

WHY
    Every call used to start with an LLM call (generate a greeting) plus TTS of
    its ~60 characters. That was the slowest turn of the first real call (3.5 s
    to first token) and ~$0.004 of Cartesia credits per visitor, for a line
    that doesn't need to be different every time. A fixed set of lines in the
    owner's voice, rendered once, starts instantly and costs nothing after the
    first play.

HOW
    The cache key is sha256(tts model | voice id | text), so editing a line or
    switching voice simply renders it once on its next use. Files are 16-bit PCM
    WAV in VOICE_AUDIO_CACHE_DIR; on the Oracle VM that's a bind mount
    (deploy/oracle/compose.yaml), so the cache survives rebuilds. If anything
    goes wrong (no cache dir, TTS error), `say_cached` falls back to a normal
    live `session.say`, so a cache problem can never cost the visitor the line.
"""

import hashlib
import io
import logging
import os
import wave
from pathlib import Path

logger = logging.getLogger("voice-greeting")

CACHE_DIR = Path(os.environ.get("VOICE_AUDIO_CACHE_DIR", "/tmp/voice-audio-cache"))
FRAME_MS = 20


def cache_key(text: str, *, model: str, voice: str) -> str:
    return hashlib.sha256(f"{model}|{voice}|{text}".encode()).hexdigest()[:24]


def _path(key: str, cache_dir: Path | None = None) -> Path:
    return (cache_dir or CACHE_DIR) / f"{key}.wav"


def save_pcm(key: str, pcm: bytes, *, sample_rate: int, num_channels: int,
             cache_dir: Path | None = None) -> Path:
    path = _path(key, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(num_channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(path)
    return path


def load_pcm(key: str, cache_dir: Path | None = None) -> tuple[bytes, int, int] | None:
    """(pcm bytes, sample_rate, num_channels) or None if not cached / unreadable."""
    path = _path(key, cache_dir)
    try:
        with wave.open(str(path), "rb") as w:
            return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()
    except Exception:
        return None


def to_frames(pcm: bytes, sample_rate: int, num_channels: int):
    """Split PCM into 20 ms rtc.AudioFrames for session.say(audio=...)."""
    from livekit import rtc

    samples = sample_rate * FRAME_MS // 1000
    step = samples * num_channels * 2
    for i in range(0, len(pcm), step):
        chunk = pcm[i:i + step]
        yield rtc.AudioFrame(
            data=chunk, sample_rate=sample_rate, num_channels=num_channels,
            samples_per_channel=len(chunk) // (2 * num_channels),
        )


async def _iter(frames):
    for f in frames:
        yield f


async def render(text: str, tts, key: str, cache_dir: Path | None = None) -> tuple[bytes, int, int]:
    """Synthesize `text` with `tts` (one Cartesia request), cache it, return PCM."""
    parts, sample_rate, num_channels = [], None, None
    async with tts.synthesize(text) as stream:
        async for ev in stream:
            frame = ev.frame
            sample_rate, num_channels = frame.sample_rate, frame.num_channels
            parts.append(bytes(frame.data))
    if not parts:
        raise RuntimeError("TTS returned no audio")
    pcm = b"".join(parts)
    save_pcm(key, pcm, sample_rate=sample_rate, num_channels=num_channels, cache_dir=cache_dir)
    logger.info("voice cache: rendered %d chars -> %s (%.1fs audio)",
                len(text), key, len(pcm) / (2 * num_channels * sample_rate))
    return pcm, sample_rate, num_channels


async def say_cached(session, text: str, *, tts, model: str, voice: str,
                     allow_interruptions: bool = True, cache_dir: Path | None = None):
    """Speak `text` from cached audio, rendering it once if needed. Returns the
    SpeechHandle. Any cache or TTS failure falls back to a live session.say."""
    key = cache_key(text, model=model, voice=voice)
    try:
        cached = load_pcm(key, cache_dir)
        if cached is None:
            cached = await render(text, tts, key, cache_dir)
            source = "rendered"
        else:
            source = "cache"
        pcm, sr, ch = cached
        logger.info("voice line from %s: %r", source, text[:60])
        return session.say(text, audio=_iter(list(to_frames(pcm, sr, ch))),
                           allow_interruptions=allow_interruptions)
    except Exception as e:
        logger.warning("voice cache unavailable (%s), speaking live: %r", e, text[:60])
        return session.say(text, allow_interruptions=allow_interruptions)
