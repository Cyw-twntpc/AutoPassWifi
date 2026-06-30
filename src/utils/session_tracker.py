"""Track per-SSID session durations and dynamically adjust health-check intervals."""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from loguru import logger

from src.utils.paths import resolve_app_path


@dataclass
class SsidRecord:
    """Persistent record for a single SSID."""
    last_duration: float = 0.0
    """Last known session duration (seconds), or 0 if unknown."""

    last_auth_at: Optional[float] = None
    """Unix timestamp of the most recent successful authentication."""

    stable: bool = False
    """True when the session has outlasted the stable_threshold."""


def get_cubic_optimized_interval(
    elapsed: float,
    duration: float,
    k: float = 0.001,
) -> float:
    """Calculate optimized health-check interval using a cubic rational function."""
    x_min = 1.0
    x_max = max(0.1 * duration, x_min)

    if elapsed >= duration:
        return x_min

    p = elapsed / duration
    rem_cube = (1.0 - p) ** 3
    prog_cube = p ** 3
    ratio = rem_cube / (rem_cube + k * prog_cube)

    return x_min + (x_max - x_min) * ratio


class SessionTracker:
    """Track per-SSID session data with JSON persistence."""

    def __init__(
        self,
        data_file: str = "session_history.json",
        default_interval: float = 60.0,
        overrun_interval: float = 20.0,
        stable_threshold: float = 18000.0,
        cubic_k: float = 0.001,
    ) -> None:
        self._filepath = resolve_app_path(data_file)
        self._default_interval = default_interval
        self._overrun_interval = overrun_interval
        self._stable_threshold = stable_threshold
        self._cubic_k = cubic_k
        self._records: dict[str, SsidRecord] = {}
        self._ensure_dir()
        self._load()

    @property
    def stable_threshold(self) -> float:
        """Return the stable threshold in seconds."""
        return self._stable_threshold

    def record_auth(self, ssid: str) -> None:
        """Mark the moment authentication succeeded for an SSID."""
        record = self._get_or_create(ssid)
        record.last_auth_at = time.time()
        logger.debug("Session auth recorded for {ssid}", ssid=ssid)
        self._save()

    def record_reset(self, ssid: str) -> None:
        """Called when the captive portal reappears (session reset)."""
        record = self._get_or_create(ssid)
        now = time.time()

        if record.last_auth_at is not None:
            elapsed = now - record.last_auth_at
            if elapsed < self._stable_threshold:
                record.last_duration = elapsed
                logger.info(
                    "{ssid} session ended after {elapsed:.0f}s — stored",
                    ssid=ssid,
                    elapsed=elapsed,
                )
            else:
                logger.info(
                    "{ssid} session ended after {elapsed:.0f}s — not stored (>= {threshold:.0f}s)",
                    ssid=ssid,
                    elapsed=elapsed,
                    threshold=self._stable_threshold,
                )

        record.last_auth_at = None
        record.stable = False
        self._save()

    def record_disconnect(self, ssid: str) -> None:
        """Clear the auth timestamp when the SSID is lost."""
        record = self._get_or_create(ssid)
        if record.last_auth_at is not None:
            logger.debug("Disconnect recorded for {ssid}", ssid=ssid)
        record.last_auth_at = None
        self._save()

    def mark_stable(self, ssid: str) -> None:
        """Mark this SSID as stable (session outlasted stable_threshold)."""
        record = self._get_or_create(ssid)
        if not record.stable:
            record.stable = True
            logger.info("{ssid} marked as stable", ssid=ssid)
            self._save()

    def get_interval(self, ssid: str) -> float:
        """Return the health-check interval (seconds) for a given SSID."""
        record = self._get_or_create(ssid)

        if record.stable:
            return float("inf")

        duration = record.last_duration
        if duration == 0.0:
            return self._default_interval

        elapsed = 0.0
        if record.last_auth_at is not None:
            elapsed = time.time() - record.last_auth_at

        if elapsed >= duration:
            return self._overrun_interval

        return get_cubic_optimized_interval(elapsed, duration, k=self._cubic_k)

    def get_record(self, ssid: str) -> SsidRecord:
        """Return the record for an SSID (creates one if missing)."""
        return self._get_or_create(ssid)

    def _ensure_dir(self) -> None:
        parent = Path(self._filepath).parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if not os.path.exists(self._filepath):
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for ssid, data in raw.items():
                self._records[ssid] = SsidRecord(
                    last_duration=data.get("last_duration", 0.0),
                    last_auth_at=data.get("last_auth_at"),
                    stable=data.get("stable", False),
                )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load session data: {exc}", exc=exc)

    def _save(self) -> None:
        raw = {}
        for ssid, rec in self._records.items():
            d = asdict(rec)
            d.pop("last_auth_at", None)
            if rec.last_auth_at is not None:
                d["last_auth_at"] = rec.last_auth_at
            raw[ssid] = d
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
        except OSError as exc:
            logger.warning("Failed to save session data: {exc}", exc=exc)

    def _get_or_create(self, ssid: str) -> SsidRecord:
        if ssid not in self._records:
            self._records[ssid] = SsidRecord()
        return self._records[ssid]
