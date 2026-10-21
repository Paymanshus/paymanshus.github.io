"""Tests for voice_availability.py and its token-server endpoints.

Run: cd agent && .venv/bin/python -m pytest tests/test_voice_availability.py -v
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

pytestmark = pytest.mark.asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

import token_server
import voice_availability as va
from token_server import create_token_app

TEST_ENV = {
    "LIVEKIT_URL": "wss://test.livekit.cloud",
    "LIVEKIT_API_KEY": "test_api_key",
    "LIVEKIT_API_SECRET": "test_api_secret_value_long_enough",
}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Fresh state dir, no live rooms, no reservations, no SMTP."""
    monkeypatch.setenv("VOICE_STATE_DIR", str(tmp_path))
    for key in ("VOICE_DISABLED", "VOICE_MAX_CONCURRENT", "VOICE_MONTHLY_MINUTES",
                "VOICE_QUOTA_RESET_DAY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    va._reservations.clear()
    rooms: set[str] = set()

    async def fake_live_rooms():
        return set(rooms)

    monkeypatch.setattr(va, "_live_rooms", fake_live_rooms)
    token_server._minute_hits.clear()
    token_server._day_hits.clear()
    token_server._global_day_hits.clear()
    token_server._global_minute_hits.clear()
    return rooms


@pytest_asyncio.fixture
async def client(monkeypatch):
    # The waitlist notifier loop is irrelevant here and would outlive the test.
    async def no_loop(app=None):
        return None

    monkeypatch.setattr(va, "notify_loop", no_loop)
    async with TestClient(TestServer(create_token_app())) as c:
        yield c


# ─── status ────────────────────────────────────────────────────────

async def test_available_when_below_cap(isolated):
    isolated.update({"voice-resume-a", "voice-resume-b"})
    st = await va.status()
    assert st.available and st.reason == va.REASON_OK
    assert st.active == 2 and st.cap == 5


async def test_busy_at_cap_counts_rooms_and_reservations(isolated):
    isolated.update({f"voice-resume-{i}" for i in range(3)})
    va.reserve("voice-resume-x")
    va.reserve("voice-resume-y")
    st = await va.status()
    assert not st.available and st.reason == va.REASON_BUSY
    assert st.active == 5 and st.retry_after_s


async def test_reservation_for_a_room_already_listed_is_not_double_counted(isolated):
    isolated.add("voice-resume-a")
    va.reserve("voice-resume-a")
    assert await va.active_sessions() == 1


async def test_reservations_expire(isolated, monkeypatch):
    va.reserve("voice-resume-old")
    later = va.time.monotonic() + va.RESERVATION_TTL_S + 1
    assert va._live_reservations(now=later) == set()


async def test_cap_is_configurable(isolated, monkeypatch):
    monkeypatch.setenv("VOICE_MAX_CONCURRENT", "2")
    isolated.update({"voice-resume-a", "voice-resume-b"})
    assert (await va.status()).reason == va.REASON_BUSY


async def test_disabled_wins(isolated, monkeypatch):
    monkeypatch.setenv("VOICE_DISABLED", "true")
    st = await va.status()
    assert not st.available and st.reason == va.REASON_DISABLED


async def test_daily_limit_reports_next_utc_midnight():
    st = await va.status(daily_cap_reached=True)
    assert st.reason == va.REASON_DAILY
    back = datetime.fromisoformat(st.back_at)
    assert back.hour == 0 and back.minute == 0 and back > datetime.now(timezone.utc)


async def test_monthly_limit_from_recorded_minutes(monkeypatch):
    monkeypatch.setenv("VOICE_MONTHLY_MINUTES", "10")
    va.record_session_seconds(9 * 60)
    assert (await va.status()).available
    va.record_session_seconds(61)
    st = await va.status()
    assert st.reason == va.REASON_MONTHLY
    assert st.minutes_used >= 10 and datetime.fromisoformat(st.back_at) > datetime.now(timezone.utc)


async def test_quota_period_with_mid_month_reset(monkeypatch):
    monkeypatch.setenv("VOICE_QUOTA_RESET_DAY", "19")
    start, end = va.quota_period(datetime(2026, 11, 3, tzinfo=timezone.utc))
    assert (start.month, start.day, end.month, end.day) == (10, 19, 11, 19)
    start, end = va.quota_period(datetime(2026, 12, 31, tzinfo=timezone.utc))
    assert (start.month, start.day, end.year, end.month, end.day) == (12, 19, 2027, 1, 19)


async def test_usage_is_per_period(monkeypatch):
    va.record_session_seconds(120, now=datetime(2026, 10, 30, tzinfo=timezone.utc))
    assert va.minutes_used(datetime(2026, 10, 31, tzinfo=timezone.utc)) == 2
    assert va.minutes_used(datetime(2026, 11, 2, tzinfo=timezone.utc)) == 0


# ─── waitlist ──────────────────────────────────────────────────────

async def test_waitlist_validates_and_dedupes():
    assert not va.add_to_waitlist("not-an-email", "busy")
    assert va.add_to_waitlist("Someone@Example.com ", "busy")
    assert va.add_to_waitlist("someone@example.com", "monthly_limit")
    entries = va._read_waitlist()
    assert len(entries) == 1
    assert entries[0]["email"] == "someone@example.com"
    assert entries[0]["reason"] == "monthly_limit"


async def test_notify_does_nothing_without_smtp():
    va.add_to_waitlist("a@example.com", "busy")
    assert await va.notify_waitlist_once() == 0


async def test_notify_sends_once_when_available(monkeypatch):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.setenv(k, "x")
    sent = []
    monkeypatch.setattr(va, "_send_back_email", lambda to: sent.append(to))
    va.add_to_waitlist("a@example.com", "busy")
    va.add_to_waitlist("b@example.com", "monthly_limit")
    assert await va.notify_waitlist_once() == 2
    assert await va.notify_waitlist_once() == 0
    assert sorted(sent) == ["a@example.com", "b@example.com"]


async def test_notify_waits_while_unavailable(monkeypatch, isolated):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setattr(va, "_send_back_email", lambda to: pytest.fail("sent while busy"))
    isolated.update({f"voice-resume-{i}" for i in range(5)})
    va.add_to_waitlist("a@example.com", "busy")
    assert await va.notify_waitlist_once() == 0


# ─── endpoints ─────────────────────────────────────────────────────

async def test_status_endpoint(client, isolated):
    isolated.add("voice-resume-a")
    resp = await client.get("/api/voice/status")
    body = await resp.json()
    assert resp.status == 200 and body["available"] and body["active"] == 1


async def test_token_refused_with_reason_at_cap(client, isolated):
    isolated.update({f"voice-resume-{i}" for i in range(5)})
    resp = await client.post("/api/token")
    body = await resp.json()
    assert resp.status == 503
    assert body["error"] == "busy" and body["reason"] == "busy" and body["cap"] == 5


async def test_minted_tokens_reserve_slots(client, monkeypatch):
    monkeypatch.setenv("VOICE_MAX_CONCURRENT", "2")
    assert (await client.post("/api/token")).status == 200
    assert (await client.post("/api/token")).status == 200
    third = await client.post("/api/token")
    assert third.status == 503 and (await third.json())["reason"] == "busy"


async def test_notify_endpoint(client):
    ok = await client.post("/api/voice/notify", json={"email": "v@example.com", "reason": "busy"})
    assert ok.status == 200
    bad = await client.post("/api/voice/notify", json={"email": "nope", "reason": "busy"})
    assert bad.status == 400
    lines = (Path(va.state_dir()) / "voice_waitlist.jsonl").read_text().splitlines()
    assert [json.loads(l)["email"] for l in lines] == ["v@example.com"]
