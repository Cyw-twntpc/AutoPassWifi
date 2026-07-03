"""Tests for SessionTracker and get_cubic_optimized_interval."""

import json
import math
import time

from src.utils.session_tracker import (
    SessionTracker,
    SsidRecord,
    get_cubic_optimized_interval,
)


# ── get_cubic_optimized_interval ───────────────────────────────


def test_cubic_at_start():
    """At elapsed=0 the interval should be close to x_max."""
    interval = get_cubic_optimized_interval(elapsed=0.0, duration=600.0, k=0.001)
    expected_max = max(0.1 * 600.0, 1.0)  # 60.0
    assert interval == pytest.approx(expected_max, rel=0.1), f"{interval} ≈ {expected_max}"


def test_cubic_at_end():
    """At elapsed ≈ duration, interval goes to x_min (1.0)."""
    interval = get_cubic_optimized_interval(elapsed=600.0, duration=600.0, k=0.001)
    assert interval == pytest.approx(1.0, abs=0.01)


def test_cubic_beyond_duration():
    """elapsed >= duration returns x_min."""
    interval = get_cubic_optimized_interval(elapsed=700.0, duration=600.0, k=0.001)
    assert interval == 1.0


def test_cubic_zero_duration():
    """With duration=0, x_max clamps to x_min."""
    interval = get_cubic_optimized_interval(elapsed=0.0, duration=0.0, k=0.001)
    assert interval == 1.0


# ── SessionTracker ─────────────────────────────────────────────


def test_tracker_creates_record(tmp_path):
    """get_record creates a default SsidRecord for unknown SSID."""
    fp = tmp_path / "test_history.json"
    tracker = SessionTracker(data_file=str(fp))
    record = tracker.get_record("TestNet")
    assert isinstance(record, SsidRecord)
    assert record.last_duration == 0.0
    assert record.stable is False


def test_record_auth_sets_timestamp(tmp_path):
    """record_auth sets last_auth_at."""
    fp = tmp_path / "test_history.json"
    tracker = SessionTracker(data_file=str(fp))
    tracker.record_auth("TestNet")
    record = tracker.get_record("TestNet")
    assert record.last_auth_at is not None
    assert record.last_auth_at == pytest.approx(time.time(), rel=1.0)


def test_record_reset_stores_duration(tmp_path):
    """record_reset stores the elapsed time as last_duration."""
    fp = tmp_path / "test_history.json"
    tracker = SessionTracker(data_file=str(fp))
    tracker.record_auth("TestNet")
    time.sleep(0.01)  # small elapsed
    tracker.record_reset("TestNet")
    record = tracker.get_record("TestNet")
    assert record.last_auth_at is None
    assert record.stable is False
    assert record.last_duration > 0.0


def test_record_disconnect_clears_timestamp(tmp_path):
    """record_disconnect clears last_auth_at without storing duration."""
    fp = tmp_path / "test_history.json"
    tracker = SessionTracker(data_file=str(fp))
    tracker.record_auth("TestNet")
    tracker.record_disconnect("TestNet")
    record = tracker.get_record("TestNet")
    assert record.last_auth_at is None
    assert record.last_duration == 0.0  # unchanged


def test_mark_stable(tmp_path):
    """mark_stable sets stable=True and get_interval returns infinity."""
    fp = tmp_path / "test_history.json"
    tracker = SessionTracker(data_file=str(fp))
    tracker.mark_stable("TestNet")
    record = tracker.get_record("TestNet")
    assert record.stable is True
    assert tracker.get_interval("TestNet") == math.inf


def test_get_interval_unknown_ssid(tmp_path):
    """Unknown SSID returns default_interval."""
    fp = tmp_path / "test_history.json"
    tracker = SessionTracker(data_file=str(fp), default_interval=120.0)
    interval = tracker.get_interval("NewNet")
    assert interval == 120.0


def test_get_interval_after_overrun(tmp_path):
    """When elapsed exceeds last_duration, return overrun_interval."""
    fp = tmp_path / "test_history.json"
    tracker = SessionTracker(
        data_file=str(fp),
        overrun_interval=30.0,
        default_interval=120.0,
    )
    # Simulate a short previous session.
    tracker.get_record("TestNet").last_duration = 10.0
    # Auth at some point in the past.
    tracker.record_auth("TestNet")

    # We need elapsed > duration. Since record_auth uses time.time(),
    # just set last_auth_at far enough in the past.
    record = tracker.get_record("TestNet")
    record.last_auth_at = time.time() - 60.0  # 60s ago, well past 10s

    interval = tracker.get_interval("TestNet")
    assert interval == 30.0


def test_persistence(tmp_path):
    """Save and reload from disk preserves data."""
    fp = tmp_path / "test_history.json"
    tracker1 = SessionTracker(data_file=str(fp))
    tracker1.record_auth("TestNet")
    tracker1.mark_stable("TestNet")
    del tracker1

    tracker2 = SessionTracker(data_file=str(fp))
    record = tracker2.get_record("TestNet")
    assert record.stable is True
    assert record.last_auth_at is not None


def test_persistence_corrupt_json(tmp_path, caplog):
    """Corrupt JSON file does not crash — logs a warning."""
    fp = tmp_path / "test_history.json"
    fp.write_text("{garbage", encoding="utf-8")
    tracker = SessionTracker(data_file=str(fp))
    # Should start cleanly with empty records.
    assert tracker.get_record("TestNet") is not None


import pytest
