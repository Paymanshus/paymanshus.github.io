"""
Component connectivity tests for the voice agent.

Tests each service independently before running the full agent:
  1. Env vars loaded from .env.local
  2. LiveKit token generation (API key + secret)
  3. Deepgram API key validity
  4. Google Gemini API key validity
  5. Cartesia API key + voice ID validity
  6. Silero VAD model load (local, no API)

Run from agent/ directory:
    python tests/test_connections.py
"""

import os
import sys
import asyncio
import urllib.request
import urllib.error
import json

if __name__ != "__main__":
    import pytest

    pytest.skip(
        "test_connections.py is a manual smoke-test script (hits live "
        "third-party APIs); run it directly with `python tests/test_connections.py`.",
        allow_module_level=True,
    )

# Load .env.local before anything else
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
SKIP = "\033[93m~\033[0m"

results = []


def check(name, passed, detail=""):
    mark = PASS if passed else FAIL
    line = f"  {mark}  {name}"
    if detail:
        line += f"  ({detail})"
    print(line)
    results.append(passed)
    return passed


# ─── 1. Env vars ──────────────────────────────────────────────────

print("\n[1] Environment variables")

required_vars = [
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "GOOGLE_API_KEY",
    "DEEPGRAM_API_KEY",
    "CARTESIA_API_KEY",
]

all_env_ok = True
for var in required_vars:
    val = os.environ.get(var, "")
    ok = bool(val) and val not in (
        "your_api_key", "your_api_secret", "your_gemini_api_key",
        "your_deepgram_api_key", "your_cartesia_api_key",
        "livekit_api_key", "livekit_api_secret", "gemini_api_key",
        "deepgram_api_key", "cartesia_api_key", "project-url.livekit.cloud",
    )
    check(var, ok, "set" if ok else "MISSING or placeholder")
    if not ok:
        all_env_ok = False

if not all_env_ok:
    print("\n  ⚠ Fill in real values in agent/.env.local before continuing.\n")
    sys.exit(1)


# ─── 2. LiveKit — token generation ────────────────────────────────

print("\n[2] LiveKit token generation")

try:
    from livekit.api import AccessToken, VideoGrants
    token = (
        AccessToken(
            api_key=os.environ["LIVEKIT_API_KEY"],
            api_secret=os.environ["LIVEKIT_API_SECRET"],
        )
        .with_identity("test-user")
        .with_grants(VideoGrants(room_join=True, room="test-room"))
        .to_jwt()
    )
    check("Token generated", bool(token), f"{len(token)} chars")
except Exception as e:
    check("Token generated", False, str(e))


# ─── 3. Deepgram — list projects (auth check) ─────────────────────

print("\n[3] Deepgram API key")

try:
    req = urllib.request.Request(
        "https://api.deepgram.com/v1/projects",
        headers={"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read())
        check("Auth valid", True, f"{len(data.get('projects', []))} project(s)")
except urllib.error.HTTPError as e:
    check("Auth valid", False, f"HTTP {e.code}")
except Exception as e:
    check("Auth valid", False, str(e))


# ─── 4. Google Gemini — list models ───────────────────────────────

print("\n[4] Google Gemini API key")

try:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={os.environ['GOOGLE_API_KEY']}"
    with urllib.request.urlopen(url, timeout=8) as resp:
        data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", []) if "flash" in m["name"].lower()]
        check("Auth valid", True, f"flash models: {len(models)}")
        flash_models = [m.split("/")[-1] for m in models]
        if flash_models:
            print(f"       Available: {', '.join(flash_models[:5])}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    check("Auth valid", False, f"HTTP {e.code}: {body[:80]}")
except Exception as e:
    check("Auth valid", False, str(e))


# ─── 5. Cartesia — list voices ────────────────────────────────────

print("\n[5] Cartesia API key + voice ID")

cartesia_ok = False
try:
    req = urllib.request.Request(
        "https://api.cartesia.ai/voices",
        headers={
            "X-API-Key": os.environ["CARTESIA_API_KEY"],
            "Cartesia-Version": "2024-06-10",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        voices = json.loads(resp.read())
        cartesia_ok = True
        check("Auth valid", True, f"{len(voices)} voice(s) available")
except urllib.error.HTTPError as e:
    check("Auth valid", False, f"HTTP {e.code}")
except Exception as e:
    check("Auth valid", False, str(e))

if cartesia_ok:
    voice_id = os.environ.get("CARTESIA_VOICE_ID", "79a125e8-cd45-4c13-8a67-188112f4dd22")
    voice_ids = [v.get("id") for v in voices]
    if voice_id in voice_ids:
        idx = voice_ids.index(voice_id)
        check("Voice ID exists", True, voices[idx].get("name", voice_id))
    else:
        # The configured ID might still be valid even if not in user's list (public voices)
        try:
            req2 = urllib.request.Request(
                f"https://api.cartesia.ai/voices/{voice_id}",
                headers={
                    "X-API-Key": os.environ["CARTESIA_API_KEY"],
                    "Cartesia-Version": "2024-06-10",
                },
            )
            with urllib.request.urlopen(req2, timeout=8) as resp2:
                v = json.loads(resp2.read())
                check("Voice ID exists", True, v.get("name", voice_id))
        except Exception as e:
            check("Voice ID exists", False, f"{voice_id[:8]}... not found — {e}")


# ─── 6. Silero VAD — local model load ─────────────────────────────

print("\n[6] Silero VAD (local model)")

try:
    from livekit.plugins import silero
    vad = silero.VAD.load()
    check("Model loaded", True, "local inference ready")
except Exception as e:
    check("Model loaded", False, str(e))


# ─── Summary ──────────────────────────────────────────────────────

total = len(results)
passed = sum(results)
failed = total - passed

print(f"\n{'─'*40}")
print(f"  {passed}/{total} checks passed", end="")
if failed:
    print(f"  ← fix {failed} failure(s) above before running the agent")
else:
    print("  ✓ all clear — run: python main.py dev")
print()

sys.exit(0 if failed == 0 else 1)
