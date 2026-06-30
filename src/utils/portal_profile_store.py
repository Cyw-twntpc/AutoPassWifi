"""Persist per-SSID recorded interaction profiles for replay."""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from loguru import logger

from src.utils.paths import resolve_app_path


@dataclass
class RecordedStep:
    """A single user interaction recorded during interactive login."""
    type: str = ""
    """'click' or 'fill'"""
    selector: str = ""
    """CSS selector of the target element"""
    value: str = ""
    """Value filled (for 'fill' steps)"""
    text: str = ""
    """Element text content (for 'click' steps)"""
    url: str = ""
    """Page URL when the step was recorded"""
    wait_after: float = 2.0
    """Seconds to wait after replaying this step"""
    must_interact: bool = False
    """True = this step needs manual input every time (captcha etc)"""


@dataclass
class PortalProfile:
    """Per-SSID recorded interaction profile."""
    ssid: str = ""
    steps: list[RecordedStep] = field(default_factory=list)
    recorded_at: Optional[float] = None
    replay_count: int = 0
    replay_success_count: int = 0


class PortalProfileStore:
    """Manage per-SSID portal interaction profiles with JSON persistence."""

    def __init__(self, data_file: str = "portal_profiles.json") -> None:
        self._filepath = resolve_app_path(data_file)
        self._profiles: dict[str, PortalProfile] = {}
        self._ensure_dir()
        self._load()

    # ── public API ──────────────────────────────────────────────

    def get_profile(self, ssid: str) -> Optional[PortalProfile]:
        """Return the recorded profile for an SSID, or None."""
        return self._profiles.get(ssid)

    def has_profile(self, ssid: str) -> bool:
        """Check if a recorded profile exists for this SSID."""
        return ssid in self._profiles

    def save_profile(self, ssid: str, steps: list[RecordedStep]) -> None:
        """Save a recorded interaction profile for an SSID."""
        profile = PortalProfile(
            ssid=ssid,
            steps=steps,
            recorded_at=time.time(),
            replay_count=0,
            replay_success_count=0,
        )
        self._profiles[ssid] = profile
        self._save()
        logger.info("Portal profile saved for {ssid} ({n} steps)", ssid=ssid, n=len(steps))

    def record_replay_result(self, ssid: str, success: bool) -> None:
        """Track replay success/failure for this SSID."""
        profile = self._profiles.get(ssid)
        if profile is not None:
            profile.replay_count += 1
            if success:
                profile.replay_success_count += 1
            self._save()

    # ── persistence ─────────────────────────────────────────────

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
                steps = [RecordedStep(**s) for s in data.get("steps", [])]
                self._profiles[ssid] = PortalProfile(
                    ssid=ssid,
                    steps=steps,
                    recorded_at=data.get("recorded_at"),
                    replay_count=data.get("replay_count", 0),
                    replay_success_count=data.get("replay_success_count", 0),
                )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load portal profiles: {exc}", exc=exc)

    def _save(self) -> None:
        raw = {}
        for ssid, profile in self._profiles.items():
            raw[ssid] = {
                "steps": [asdict(s) for s in profile.steps],
                "recorded_at": profile.recorded_at,
                "replay_count": profile.replay_count,
                "replay_success_count": profile.replay_success_count,
            }
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
        except OSError as exc:
            logger.warning("Failed to save portal profiles: {exc}", exc=exc)
