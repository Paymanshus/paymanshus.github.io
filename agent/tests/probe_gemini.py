"""Probe available Gemini models + time-to-first-token for voice-relevant candidates.

Run: cd agent && .venv/bin/python tests/probe_gemini.py
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.local")

from google import genai

client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

print("=== generateContent-capable models (flash/lite family) ===")
for m in client.models.list():
    if "generateContent" in (m.supported_actions or []) and "flash" in m.name:
        print(" ", m.name)

CANDIDATES = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash",
]

print("\n=== latency probe (short persona-style prompt, streaming TTFT) ===")
for model in CANDIDATES:
    try:
        start = time.perf_counter()
        first = None
        stream = client.models.generate_content_stream(
            model=model,
            contents="Say hello in five words.",
            config={"max_output_tokens": 30},
        )
        text = ""
        for chunk in stream:
            if first is None:
                first = time.perf_counter() - start
            text += chunk.text or ""
        total = time.perf_counter() - start
        print(f"  {model}: TTFT={first*1000:.0f}ms total={total*1000:.0f}ms → {text.strip()[:60]!r}")
    except Exception as e:
        msg = str(e).replace("\n", " ")[:120]
        print(f"  {model}: FAILED — {msg}")
