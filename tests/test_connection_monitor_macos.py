"""Tests for macOS connection monitor."""

import sys
import queue
from unittest import mock

import pytest
from src.core.connection_monitor_macos import MacConnectionMonitor


@mock.patch("src.core.connection_monitor_macos.query_current_ssid")
@mock.patch("subprocess.Popen")
def test_mac_connection_monitor(mock_popen, mock_query):
    monitor = MacConnectionMonitor()
    
    # Mock subprocess.Popen stdout
    mock_process = mock.Mock()
    # Provide one line then empty to break the loop
    mock_process.stdout.readline.side_effect = ["WIFI_CHANGED\n", ""]
    mock_popen.return_value = mock_process
    
    # Setup SSID
    monitor.set_initial_ssid("OldNet")
    mock_query.return_value = "NewNet"
    
    # Setup callback
    cb = mock.Mock()
    monitor.on_ssid_changed(cb)
    
    # Start the monitor
    monitor.start()
    
    # Wait for the thread to finish processing
    monitor._thread.join(timeout=2.0)
    
    # Check if event was queued and processed by poll
    event = monitor.poll(timeout=0.1)
    assert event == "NewNet"
    assert monitor.current_ssid == "NewNet"
    cb.assert_called_once_with("OldNet", "NewNet")
    
    monitor.stop()
