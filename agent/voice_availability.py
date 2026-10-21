"""
Voice availability: concurrency cap, monthly minutes, kill switch, waitlist.

LiveKit Cloud's free Build plan allows 5 concurrent agent sessions and 1,000
agent minutes a month. A 6th caller is not refused by LiveKit: the agent simply
never joins, and the visitor watches "summoning the agent" forever. So the cap
is enforced here, before a token is minted, and every reason voice can be
unavailable is reported to the frontend as a structured status it can explain.

Reasons (the `reason` field of /api/voice/status and of a refused /api/token):

    ok             a slot is free
    busy           VOICE_MAX_CONCURRENT sessions are live; back in minutes
    daily_limit    the token server's global daily token cap is spent; back at
                   UTC midnight
    monthly_limit  tracked agent minutes reached VOICE_MONTHLY_MINUTES; back at
                   the next quota reset (VOICE_QUOTA_RESET_DAY, UTC)
    disabled       VOICE_DISABLED=true (owner kill switch)

Two further states live only in the frontend: the server is unreachable (the
existing "resting" view) and the agent was granted a slot but never joined
(a timeout, covering LiveKit refusing a dispatch for reasons we can't see).

Active sessions come from LiveKit's room list (rooms named `voice-resume-*`),
plus slots reserved by tokens minted in the last RESERVATION_TTL_S seconds that
haven't shown up as rooms yet, so a burst of six clicks can't all get through.

Agent minutes are recorded by the voice job itself (main.py calls
`record_session_seconds` on shutdown) into a JSON file in VOICE_STATE_DIR, which
is a Docker volume on the VM so it survives rebuilds.

The waitlist stores emails left on the unavailable screen (JSONL in the same
directory). When SMTP_* is configured, a background task emails everyone still
waiting once voice is available again; without it, entries are only stored and
`python voice_availability.py waitlist` lists them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import smtplib
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger("voice-availability")

ROOM_PREFIX = "voice-resume-"
RESERVATION_TTL_S = 45
ROOM_CACHE_TTL_S = 3.0
NOTIFY_INTERVAL_S = 300

REASON_OK = "ok"
REASON_BUSY = "busy"
REASON_DAILY = "daily_limit"
REASON_MONTHLY = "monthly_limit"
REASON_DISABLED = "disabled"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def max_concurrent() -> int:
    return _env_int("VOICE_MAX_CONCURRENT", 5)


def monthly_minutes_cap() -> int:
    # Below LiveKit's 1,000 so a session that's already running when the cap is
    # hit can finish without tipping the account over.
    return _env_int("VOICE_MONTHLY_MINUTES", 950)


def quota_reset_day() -> int:
    return min(max(_env_int("VOICE_QUOTA_RESET_DAY", 1), 1), 28)


def is_disabled() -> bool:
    return os.environ.get("VOICE_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def state_dir() -> Path:
    path = Path(os.environ.get("VOICE_STATE_DIR", Path(__file__).parent / ".voice_state"))
    path.mkdir(parents=True, exist_ok=True)
    return path


# ─── Monthly agent minutes ─────────────────────────────────────────

def quota_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Start and end (exclusive) of the quota month containing `now`, UTC."""
    now = now or datetime.now(timezone.utc)
    day = quota_reset_day()
    start = now.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
    if now < start:
        start = (start - timedelta(days=28)).replace(day=day)
    end = (start + timedelta(days=32)).replace(day=day)
    return start, end


def _usage_path() -> Path:
    return state_dir() / "voice_usage.json"


def _period_key(now: datetime | None = None) -> str:
    return quota_period(now)[0].strftime("%Y-%m-%d")


def record_session_seconds(seconds: float, now: datetime | None = None) -> None:
    """Add one finished session's agent time to the current quota period.

    Called from the voice job process. Best effort: a failure here must never
    break a call, so it only logs.
    """
    if seconds <= 0:
        return
    try:
        path = _usage_path()
        data = json.loads(path.read_text()) if path.exists() else {}
        key = _period_key(now)
        data[key] = round(float(data.get(key, 0)) + seconds, 1)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(path)
        logger.info("voice usage: +%.0fs, period %s total %.1f min", seconds, key, data[key] / 60)
    except Exception as e:  # pragma: no cover - logged, never raised
        logger.warning("voice usage not recorded: %s", e)


def minutes_used(now: datetime | None = None) -> float:
    try:
        data = json.loads(_usage_path().read_text())
    except (FileNotFoundError, ValueError):
        return 0.0
    return float(data.get(_period_key(now), 0)) / 60


# ─── Active sessions ───────────────────────────────────────────────

_reservations: dict[str, float] = {}
_room_cache: tuple[float, set[str]] = (0.0, set())


async def _live_rooms() -> set[str]:
    """Names of live `voice-resume-*` rooms, cached for a few seconds.

    If LiveKit can't be asked, fall back to the reservations alone rather than
    blocking every visitor: the frontend's join timeout still catches the case
    where LiveKit really is full.
    """
    global _room_cache
    now = time.monotonic()
    if now - _room_cache[0] < ROOM_CACHE_TTL_S:
        return _room_cache[1]
    try:
        from livekit import api

        lk = api.LiveKitAPI()
        try:
            resp = await lk.room.list_rooms(api.ListRoomsRequest())
        finally:
            await lk.aclose()
        rooms = {r.name for r in resp.rooms if r.name.startswith(ROOM_PREFIX)}
    except Exception as e:
        logger.warning("could not list LiveKit rooms: %s", e)
        rooms = set(_room_cache[1])
    _room_cache = (now, rooms)
    return rooms


def _live_reservations(now: float | None = None) -> set[str]:
    now = now or time.monotonic()
    for room, at in list(_reservations.items()):
        if now - at > RESERVATION_TTL_S:
            del _reservations[room]
    return set(_reservations)


def reserve(room: str) -> None:
    """Hold a slot for a freshly minted token until its room appears."""
    _reservations[room] = time.monotonic()


async def active_sessions() -> int:
    rooms = await _live_rooms()
    return len(rooms | _live_reservations())


# ─── Status ────────────────────────────────────────────────────────

@dataclass
class Status:
    available: bool
    reason: str
    active: int
    cap: int
    retry_after_s: int | None = None
    back_at: str | None = None        # ISO-8601 UTC, when known
    minutes_used: float | None = None
    minutes_cap: int | None = None

    def to_json(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _next_utc_midnight(now: datetime) -> datetime:
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


async def status(*, daily_cap_reached: bool = False) -> Status:
    now = datetime.now(timezone.utc)
    cap = max_concurrent()
    used, mcap = minutes_used(now), monthly_minutes_cap()

    if is_disabled():
        return Status(False, REASON_DISABLED, 0, cap)
    if used >= mcap:
        reset = quota_period(now)[1]
        return Status(False, REASON_MONTHLY, 0, cap,
                      retry_after_s=int((reset - now).total_seconds()),
                      back_at=reset.isoformat(), minutes_used=round(used, 1), minutes_cap=mcap)
    if daily_cap_reached:
        back = _next_utc_midnight(now)
        return Status(False, REASON_DAILY, 0, cap,
                      retry_after_s=int((back - now).total_seconds()), back_at=back.isoformat())

    active = await active_sessions()
    if active >= cap:
        # Typical call is a few minutes; this is a hint for the copy, not a promise.
        return Status(False, REASON_BUSY, active, cap, retry_after_s=180,
                      minutes_used=round(used, 1), minutes_cap=mcap)
    return Status(True, REASON_OK, active, cap, minutes_used=round(used, 1), minutes_cap=mcap)


# ─── Waitlist ──────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
WAITLIST_MAX = 5000


def _waitlist_path() -> Path:
    return state_dir() / "voice_waitlist.jsonl"


def _read_waitlist() -> list[dict]:
    path = _waitlist_path()
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _write_waitlist(entries: list[dict]) -> None:
    path = _waitlist_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e) + "\n" for e in entries))
    tmp.replace(path)


def add_to_waitlist(email: str, reason: str) -> bool:
    """Store an email. Returns False if it's invalid. Re-adding a pending email
    just updates its reason, so a visitor can't queue themselves twice."""
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return False
    entries = _read_waitlist()
    now = datetime.now(timezone.utc).isoformat()
    for e in entries:
        if e.get("email") == email and not e.get("notified_at"):
            e["reason"], e["updated_at"] = reason, now
            _write_waitlist(entries)
            return True
    if len(entries) >= WAITLIST_MAX:
        logger.warning("waitlist full (%d); not storing", len(entries))
        return True
    entries.append({"email": email, "reason": reason, "created_at": now})
    _write_waitlist(entries)
    logger.info("waitlist: +1 (%s), %d pending", reason,
                sum(1 for e in entries if not e.get("notified_at")))
    return True


def _smtp_configured() -> bool:
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


SITE_URL = os.environ.get("VOICE_SITE_URL", "https://paymanshus.github.io")


def _send_back_email(to: str) -> None:
    msg = EmailMessage()
    msg["From"] = os.environ.get("NOTIFY_FROM") or os.environ["SMTP_USER"]
    msg["To"] = to
    msg["Subject"] = "AI me is back"
    msg.set_content(
        "You asked to know when the voice agent on my site was back. It is.\n\n"
        f"{SITE_URL}\n\n"
        "No more emails unless you reply.\n— Paymanshu\n"
    )
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


async def notify_waitlist_once() -> int:
    """If voice is available, email everyone pending. Returns how many sent."""
    if not _smtp_configured():
        return 0
    st = await status()
    if not st.available:
        return 0
    entries = _read_waitlist()
    sent = 0
    for e in entries:
        if e.get("notified_at"):
            continue
        try:
            await asyncio.to_thread(_send_back_email, e["email"])
        except Exception as err:
            logger.warning("waitlist email failed: %s", err)
            break
        e["notified_at"] = datetime.now(timezone.utc).isoformat()
        sent += 1
        if sent >= 50:  # stay far below Gmail's sending limits per pass
            break
    if sent:
        _write_waitlist(entries)
        logger.info("waitlist: notified %d", sent)
    return sent


async def notify_loop(app=None) -> None:
    while True:
        try:
            await notify_waitlist_once()
        except Exception as e:  # pragma: no cover
            logger.warning("waitlist loop error: %s", e)
        await asyncio.sleep(NOTIFY_INTERVAL_S)


if __name__ == "__main__":
    # python voice_availability.py waitlist   → pending and notified entries
    # python voice_availability.py usage      → minutes used this quota period
    cmd = sys.argv[1] if len(sys.argv) > 1 else "usage"
    if cmd == "waitlist":
        for e in _read_waitlist():
            print(json.dumps(e))
    else:
        s, e = quota_period()
        print(f"period {s:%Y-%m-%d} → {e:%Y-%m-%d}: {minutes_used():.1f} / {monthly_minutes_cap()} min")
