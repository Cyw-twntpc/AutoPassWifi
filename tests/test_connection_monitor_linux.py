"""Tests for Linux connection monitor."""

import sys
import queue
from unittest import mock

import pytest


@pytest.fixture
def mock_jeepney():
    with mock.patch.dict("sys.modules", {"jeepney": mock.MagicMock(), "jeepney.io.blocking": mock.MagicMock(), "jeepney.bus_messages": mock.MagicMock()}):
        yield

@mock.patch("src.core.connection_monitor_linux.query_current_ssid")
def test_linux_connection_monitor(mock_query, mock_jeepney):
    # Now that jeepney is mocked, we can import the monitor
    from src.core.connection_monitor_linux import LinuxConnectionMonitor
    
    monitor = LinuxConnectionMonitor()
    monitor.set_initial_ssid("OldNet")
    mock_query.return_value = "NewNet"
    
    cb = mock.Mock()
    monitor.on_ssid_changed(cb)
    
    # We will mock the thread loop instead of actually running it, because jeepney is mocked and it would require deep mocking of context managers
    # Let's just simulate the internal DBus loop receiving a signal
    def fake_dbus_loop():
        # Simulate receiving a signal and checking SSID
        import time
        time.sleep(0.1)
        if monitor._running.is_set():
            new_ssid = mock_query()
            if new_ssid != monitor._current_ssid:
                monitor._queue.put({"type": "changed", "ssid": new_ssid})
    
    with mock.patch.object(monitor, "_dbus_loop", side_effect=fake_dbus_loop):
        monitor.start()
        
        # Wait for fake thread to finish
        monitor._thread.join(timeout=2.0)
        
        event = monitor.poll(timeout=0.1)
        assert event == "NewNet"
        assert monitor.current_ssid == "NewNet"
        cb.assert_called_once_with("OldNet", "NewNet")
        
        monitor.stop()
