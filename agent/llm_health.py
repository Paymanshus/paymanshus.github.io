"""
Canary health checks: find a slow or broken rung BEFORE a visitor's turn does.

WHY
    The breaker (llm_ladder) only learns from failures a visitor already paid
    for, and it can't see "slow": a primary that answers in 6 s is "healthy" to
    it. On 2026-10-21 AI Studio took 16-30 s per reply for hours, and every
    visitor in that window found out the hard way.

WHAT IT DOES
    The token server (main process) sends a 1-token request to the first voice
    rungs and the first terminal rung:
      - when a visitor asks for a voice token, at most once per
        LLM_CANARY_MIN_GAP_S (the job process starts a few seconds later, so the
        result is fresh when the session picks its rung order);
      - every LLM_CANARY_INTERVAL_S in the background.
    A canary that fails or takes longer than LLM_CANARY_SLOW_MS marks the rung
    degraded for LLM_HEALTH_TTL_S. Hard failures also go to the shared breaker,
    so the terminal path (same process) skips the rung immediately.

    Voice sessions run in separate job processes, so the results are shared
    through a small JSON file (LLM_HEALTH_PATH). `order_by_health` moves degraded
    rungs to the back of the voice ladder when a session builds it: rung 2
    becomes the primary before anyone talks to it.

COST
    A 1-token canary is ~20 input tokens: ~$0.000002. Every 10 minutes for two
    rungs is well under a cent a day.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import llm_ladder
import llm_models
from llm_models import LadderEntry

logger = logging.getLogger("llm-health")

HEALTH_PATH = Path(os.environ.get("LLM_HEALTH_PATH", "/tmp/llm_health.json"))

# How many rungs of each ladder get a canary. Rung 2 of voice matters too: it's
# the hedge partner and becomes the primary if rung 1 is degraded.
VOICE_CANARY_RUNGS = 2
TERMINAL_CANARY_RUNGS = 1


# ─── Shared state file ─────────────────────────────────────────────

def read_health(path: Path | None = None) -> dict[str, dict]:
    """{entry.key: {"ok", "ms", "at", "error"}}; {} if missing or unreadable."""
    path = path or HEALTH_PATH
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def record(entry: LadderEntry, *, ok: bool, ms: float | None, error: str = "",
           path: Path | None = None, now: float | None = None) -> None:
    """Merge one canary result into the health file (atomic replace)."""
    path = path or HEALTH_PATH
    state = read_health(path)
    state[entry.key] = {
        "ok": ok,
        "ms": round(ms, 1) if ms is not None else None,
        "at": now if now is not None else time.time(),
        "error": error[:200],
    }
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(path)
    except Exception as e:
        # Losing the health file only loses the reordering; never break a request.
        logger.warning("could not write %s: %s", path, e)


def is_degraded(entry: LadderEntry, health: dict, now: float | None = None) -> bool:
    """True if this rung's last canary, within the TTL, failed or was slow."""
    item = health.get(entry.key)
    if not item:
        return False
    now = now if now is not None else time.time()
    if now - float(item.get("at", 0)) > llm_models.LLM_HEALTH_TTL_S:
        return False
    if not item.get("ok"):
        return True
    ms = item.get("ms")
    return ms is not None and ms > llm_models.LLM_CANARY_SLOW_MS


def order_by_health(ladder, health: dict | None = None, now: float | None = None) -> tuple:
    """Healthy rungs first in configured order, then degraded ones (still kept as
    a last resort: a slow model beats no model)."""
    health = read_health() if health is None else health
    healthy = [e for e in ladder if not is_degraded(e, health, now)]
    degraded = [e for e in ladder if is_degraded(e, health, now)]
    if degraded:
        logger.warning(
            "llm health: demoting %s (canary failed or slow)",
            ", ".join(e.label for e in degraded),
        )
    return tuple(healthy + degraded)


# ─── Canary runs ───────────────────────────────────────────────────

def canary_targets() -> list[tuple[LadderEntry, str]]:
    """(entry, surface) pairs to check, deduplicated by breaker key."""
    seen, out = set(), []
    for ladder, n, surface in (
        (llm_models.VOICE_LADDER, VOICE_CANARY_RUNGS, "voice"),
        (llm_models.LLM_LADDER, TERMINAL_CANARY_RUNGS, "terminal"),
    ):
        for entry in ladder[:n]:
            if entry.key in seen:
                continue
            if entry.provider == "openrouter" and not llm_ladder.openrouter_enabled():
                continue
            seen.add(entry.key)
            out.append((entry, surface))
    return out


async def check(entry: LadderEntry, surface: str, *, path: Path | None = None) -> bool:
    """One canary: record the result; feed hard failures to the breaker."""
    try:
        ms = await llm_ladder.ping_entry(entry, surface=surface)
    except llm_ladder.LLMError as err:
        record(entry, ok=False, ms=None, error=f"{err.kind}: {err.message}", path=path)
        llm_ladder.breaker.record_failure(entry, err)
        logger.warning("llm canary: %s failed [%s] %s", entry.label, err.kind, err.message[:120])
        return False
    except Exception as e:  # never let a canary crash its caller
        record(entry, ok=False, ms=None, error=repr(e), path=path)
        logger.warning("llm canary: %s errored: %r", entry.label, e)
        return False
    record(entry, ok=True, ms=ms, path=path)
    slow = ms > llm_models.LLM_CANARY_SLOW_MS
    (logger.warning if slow else logger.info)(
        "llm canary: %s %.0fms%s", entry.label, ms, " (slow)" if slow else ""
    )
    return not slow


async def run_canaries(*, path: Path | None = None) -> dict[str, bool]:
    targets = canary_targets()
    results = await asyncio.gather(*(check(e, s, path=path) for e, s in targets))
    return {e.label: ok for (e, _), ok in zip(targets, results)}


class CanaryScheduler:
    """Debounced on-demand canaries plus a periodic loop, for the token server."""

    def __init__(self, *, min_gap_s: float | None = None, interval_s: float | None = None):
        self.min_gap_s = llm_models.LLM_CANARY_MIN_GAP_S if min_gap_s is None else min_gap_s
        self.interval_s = llm_models.LLM_CANARY_INTERVAL_S if interval_s is None else interval_s
        self._last_started = 0.0
        self._inflight: asyncio.Task | None = None
        self._loop_task: asyncio.Task | None = None

    def kick(self, now: float | None = None) -> asyncio.Task | None:
        """Start a canary run unless one is running or ran within min_gap_s.
        Fire-and-forget: never awaited by the request that triggered it."""
        now = now if now is not None else time.monotonic()
        if self._inflight is not None and not self._inflight.done():
            return None
        if self._last_started and now - self._last_started < self.min_gap_s:
            return None
        self._last_started = now
        self._inflight = asyncio.create_task(run_canaries(), name="llm-canary")
        return self._inflight

    async def _loop(self) -> None:
        while True:
            self.kick()
            await asyncio.sleep(self.interval_s)

    def start(self) -> None:
        if self.interval_s > 0 and self._loop_task is None:
            self._loop_task = asyncio.create_task(self._loop(), name="llm-canary-loop")

    async def stop(self) -> None:
        for task in (self._loop_task, self._inflight):
            if task is not None and not task.done():
                task.cancel()
        self._loop_task = None


scheduler = CanaryScheduler()
