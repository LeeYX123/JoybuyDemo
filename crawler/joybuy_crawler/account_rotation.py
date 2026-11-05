"""Multi-account rotation inside one crawl (2026-11-05, user decision).

A run used to hold a single identity from first byte to last. The operator
decided a crawl should spread its requests across the account pool instead,
switching identities at randomised intervals so no single account absorbs
the whole run and each account's footprint stays small.

Design notes
------------
- **Randomised, not scheduled.** Each stint draws a fresh pair of budgets
  (seconds and request count), so the switch cadence is never a fixed
  period. A predictable cadence is itself a signal.
- **Per-account cookie state.** Only the active account's cookie pairs are
  attached to a request; nothing is carried across a rotation. Scrapy's
  global cookie jar is disabled for these runs (see ``runner``) precisely
  because it would merge accounts together.
- **A blocked account is ejected, not retried.** When a page comes back as
  a risk-control wall, that account stops receiving requests for the rest
  of the run and the pool moves on. Accounts are never re-used after a
  signal inside the same run.
- **Exhaustion is reported, not hidden.** When every account is blocked the
  pool stops rotating and the caller writes an ``ACCOUNT_POOL_EXHAUSTED``
  event; the crawl keeps whatever guard rails the source itself imposes.

This module is intentionally free of Scrapy/Django imports so rotation
behaviour can be tested with a fake clock and no database.
"""

import random
import time
from dataclasses import dataclass, field


@dataclass
class PooledAccount:
    """One account available to the current crawl."""

    public_id: str
    label: str
    group: str
    cookies: dict[str, str] = field(default_factory=dict)
    used_requests: int = 0
    blocked: bool = False
    blocked_reason: str = ""


class AccountPool:
    """Rotate through accounts at randomised intervals.

    ``min_seconds``/``max_seconds`` and ``min_requests``/``max_requests``
    bound one stint. A stint ends when *either* budget runs out, whichever
    comes first, which keeps fast pages from burning an account by count
    alone and slow pages from holding one for too long by time alone.
    """

    def __init__(
        self,
        records: list[dict],
        *,
        min_seconds: float = 300.0,
        max_seconds: float = 900.0,
        min_requests: int = 20,
        max_requests: int = 60,
        rng: random.Random | None = None,
        clock=time.monotonic,
    ):
        self._rng = rng or random.Random()
        self._clock = clock
        self._min_seconds = max(1.0, float(min_seconds))
        self._max_seconds = max(self._min_seconds, float(max_seconds))
        self._min_requests = max(1, int(min_requests))
        self._max_requests = max(self._min_requests, int(max_requests))
        self.entries = [
            PooledAccount(
                public_id=str(record.get("public_id") or ""),
                label=str(record.get("label") or ""),
                group=str(record.get("group") or ""),
                cookies=dict(record.get("cookies") or {}),
            )
            for record in records or []
        ]
        self._index = 0
        self.rotations = 0
        self._stint_started = self._clock()
        self._request_budget = self._plan_requests()
        self._second_budget = self._plan_seconds()

    # -- state ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def enabled(self) -> bool:
        """Rotation only makes sense with at least two accounts."""

        return len(self.entries) > 1

    @property
    def active(self) -> PooledAccount | None:
        if not self.entries:
            return None
        return self.entries[self._index]

    @property
    def all_blocked(self) -> bool:
        return bool(self.entries) and all(entry.blocked for entry in self.entries)

    def labels(self) -> list[str]:
        return [entry.label for entry in self.entries]

    # -- rotation -------------------------------------------------------

    def record_request(self) -> None:
        entry = self.active
        if entry is not None:
            entry.used_requests += 1

    def should_rotate(self) -> bool:
        if not self.enabled:
            return False
        entry = self.active
        if entry is not None and entry.blocked:
            return True
        if entry is not None and entry.used_requests >= self._request_budget:
            return True
        return (self._clock() - self._stint_started) >= self._second_budget

    def rotate(self) -> PooledAccount | None:
        """Move to the next usable account; ``None`` when none is left."""

        if not self.entries:
            return None
        start = self._index
        for step in range(1, len(self.entries) + 1):
            candidate = (start + step) % len(self.entries)
            if not self.entries[candidate].blocked:
                self._advance(candidate)
                return self.entries[candidate]
        return None

    def mark_blocked(self, reason: str = "") -> PooledAccount | None:
        """Eject the active account for the rest of the run."""

        entry = self.active
        if entry is None:
            return None
        entry.blocked = True
        entry.blocked_reason = reason.strip()
        return entry

    def _advance(self, index: int) -> None:
        self._index = index
        self.rotations += 1
        entry = self.entries[index]
        # Counters and budgets belong to a stint, not to the account's whole
        # life: coming back to an account later must start a fresh stint.
        entry.used_requests = 0
        self._stint_started = self._clock()
        self._request_budget = self._plan_requests()
        self._second_budget = self._plan_seconds()

    def _plan_requests(self) -> int:
        return self._rng.randint(self._min_requests, self._max_requests)

    def _plan_seconds(self) -> float:
        return self._rng.uniform(self._min_seconds, self._max_seconds)
