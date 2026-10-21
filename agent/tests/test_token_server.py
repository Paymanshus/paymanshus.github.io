"""Tests for token_server.py — token minting, CORS, rate limiting, chat validation.

Run: cd agent && .venv/bin/python -m pytest tests/test_token_server.py -v
"""

import base64
import json
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

pytestmark = pytest.mark.asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

import token_server
from token_server import create_token_app

TEST_ENV = {
    "LIVEKIT_URL": "wss://test.livekit.cloud",
    "LIVEKIT_API_KEY": "test_api_key",
    "LIVEKIT_API_SECRET": "test_api_secret_value_long_enough",
}


@pytest.fixture(autouse=True)
def reset_rate_limits(monkeypatch, tmp_path):
    """Fresh rate-limit state and LiveKit env for every test."""
    # Voice availability: no live rooms (never call LiveKit), fresh state dir.
    import voice_availability

    async def no_rooms():
        return set()

    monkeypatch.setattr(voice_availability, "_live_rooms", no_rooms)
    monkeypatch.setenv("VOICE_STATE_DIR", str(tmp_path))
    # These tests mint more tokens than the 5-call cap; the cap has its own tests.
    monkeypatch.setenv("VOICE_MAX_CONCURRENT", "100")
    voice_availability._reservations.clear()
    token_server._minute_hits.clear()
    token_server._day_hits.clear()
    token_server._global_day_hits.clear()
    token_server._global_minute_hits.clear()
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    # Never send real canary requests from tests.
    monkeypatch.setattr(token_server.llm_health, "scheduler", FakeScheduler())


class FakeScheduler:
    def __init__(self):
        self.kicks = 0
        self.started = False

    def kick(self, now=None):
        self.kicks += 1

    def start(self):
        self.started = True

    async def stop(self):
        self.started = False


@pytest_asyncio.fixture
async def client():
    app = create_token_app()
    async with TestClient(TestServer(app)) as c:
        yield c


def _decode_jwt_payload(jwt: str) -> dict:
    payload = jwt.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "ok"


async def test_token_minting(client):
    resp = await client.get("/api/token")
    assert resp.status == 200
    body = await resp.json()
    # Both key conventions present
    assert body["serverUrl"] == TEST_ENV["LIVEKIT_URL"]
    assert body["participantToken"] == body["token"]
    assert body["room"].startswith("voice-resume-")

    payload = _decode_jwt_payload(body["participantToken"])
    assert payload["video"]["roomJoin"] is True
    # The critical bit: named agents require explicit dispatch in the token
    agents = payload["roomConfig"]["agents"]
    assert agents[0]["agentName"] == token_server.AGENT_NAME
    # Short-lived token
    assert payload["exp"] - payload["nbf"] <= token_server.TOKEN_TTL_SECONDS + 60


async def test_token_minting_kicks_llm_canary(client):
    """Minting a voice token checks the voice rungs before the job starts."""
    scheduler = token_server.llm_health.scheduler
    assert scheduler.started, "periodic canaries start with the app"
    resp = await client.get("/api/token")
    assert resp.status == 200
    assert scheduler.kicks == 1


async def test_token_rooms_are_unique(client):
    body1 = await (await client.get("/api/token")).json()
    body2 = await (await client.get("/api/token")).json()
    assert body1["room"] != body2["room"]


async def test_token_missing_credentials(client, monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_KEY")
    resp = await client.get("/api/token")
    assert resp.status == 500


async def test_cors_allows_known_origin(client):
    origin = "https://paymanshus.github.io"
    resp = await client.options("/api/token", headers={"Origin": origin})
    assert resp.status == 204
    assert resp.headers["Access-Control-Allow-Origin"] == origin


async def test_cors_rejects_unknown_origin(client):
    resp = await client.options("/api/token", headers={"Origin": "https://evil.example"})
    # Falls back to production origin, so the browser will block evil.example
    assert resp.headers["Access-Control-Allow-Origin"] == "https://paymanshus.github.io"


async def test_token_rate_limit_per_minute(client):
    per_min = token_server.RATE_LIMITS["token"][0]
    for _ in range(per_min):
        assert (await client.get("/api/token")).status == 200
    resp = await client.get("/api/token")
    assert resp.status == 429


async def test_chat_rejects_empty_message(client):
    resp = await client.post("/api/chat", json={"message": "  "})
    assert resp.status == 400


async def test_chat_rejects_invalid_json(client):
    resp = await client.post("/api/chat", data=b"not json")
    assert resp.status == 400


async def test_chat_rate_limit(client):
    per_min = token_server.RATE_LIMITS["chat"][0]
    # Exhaust the per-minute budget with invalid payloads (no LLM calls made)
    for _ in range(per_min):
        await client.post("/api/chat", json={"message": ""})
    resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status == 429


async def test_chat_global_per_minute_cap(client, monkeypatch):
    """The global per-minute cap is what protects upstream RPM quotas during a
    concurrency spike — per-IP limits do nothing when 40 different visitors
    arrive at once. It must trip even when no single IP is over its own budget.
    """
    per_ip_min, per_ip_day, global_day, global_min = token_server.RATE_LIMITS["chat"]
    # Global cap below the per-IP cap, so only the global one can fire here.
    monkeypatch.setitem(token_server.RATE_LIMITS, "chat", (per_ip_min, per_ip_day, global_day, 3))

    for i in range(3):
        resp = await client.post(
            "/api/chat", json={"message": ""},
            headers={"X-Forwarded-For": f"198.51.100.{i}"},
        )
        assert resp.status == 400, "distinct IPs, each well under the per-IP budget"

    # A fourth distinct visitor is shed by the global cap, not by a per-IP one.
    resp = await client.post(
        "/api/chat", json={"message": "hello"},
        headers={"X-Forwarded-For": "198.51.100.99"},
    )
    assert resp.status == 429
    body = await resp.json()
    # Worded as "busy", not "you misbehaved" — this visitor did nothing unusual.
    assert "Busy" in body["error"]


async def test_global_minute_window_recovers(client, monkeypatch):
    per_ip_min, per_ip_day, global_day, _ = token_server.RATE_LIMITS["chat"]
    monkeypatch.setitem(token_server.RATE_LIMITS, "chat", (per_ip_min, per_ip_day, global_day, 1))

    await client.post("/api/chat", json={"message": ""},
                      headers={"X-Forwarded-For": "203.0.113.1"})
    resp = await client.post("/api/chat", json={"message": "hi"},
                             headers={"X-Forwarded-For": "203.0.113.2"})
    assert resp.status == 429

    # Age the recorded hits past the 60s window rather than sleeping.
    token_server._global_minute_hits["chat"] = [
        t - 61 for t in token_server._global_minute_hits["chat"]
    ]
    resp = await client.post("/api/chat", json={"message": ""},
                             headers={"X-Forwarded-For": "203.0.113.3"})
    assert resp.status == 400, "window expired, requests flow again"
