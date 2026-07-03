"""Tests for cross-platform network utils."""

import sys
import subprocess
from unittest import mock

import pytest
from src.core.sys_network import query_current_ssid

@mock.patch("sys.platform", "win32")
@mock.patch("src.core.connection_monitor_win.query_current_ssid_win")
def test_query_ssid_win32(mock_query_win):
    mock_query_win.return_value = "WindowsNet"
    assert query_current_ssid() == "WindowsNet"
    mock_query_win.assert_called_once()

@mock.patch("sys.platform", "darwin")
@mock.patch("subprocess.run")
def test_query_ssid_darwin(mock_run):
    mock_run.return_value = mock.Mock(
        returncode=0,
        stdout="     agrCtlRSSI: -45\n     agrExtRSSI: 0\n    agrCtlNoise: -96\n    agrExtNoise: 0\n          state: running\n        op mode: station \n     lastTxRate: 145\n        maxRate: 144\nlastAssocStatus: 0\n    802.11 auth: open\n      link auth: wpa2-psk\n          BSSID: aa:bb:cc:dd:ee:ff\n           SSID: MacNet\n            MCS: 15\n        channel: 6\n"
    )
    assert query_current_ssid() == "MacNet"
    mock_run.assert_called_once()
    assert "airport" in mock_run.call_args[0][0][0]

@mock.patch("sys.platform", "linux")
@mock.patch("subprocess.run")
def test_query_ssid_linux_nmcli(mock_run):
    # nmcli succeeds
    mock_run.return_value = mock.Mock(
        returncode=0,
        stdout="no:OtherNet\nyes:LinuxNet\nno:ThirdNet\n"
    )
    assert query_current_ssid() == "LinuxNet"
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0][0] == "nmcli"

@mock.patch("sys.platform", "linux")
@mock.patch("subprocess.run")
def test_query_ssid_linux_iwgetid(mock_run):
    # nmcli fails or raises FileNotFoundError, iwgetid succeeds
    def run_side_effect(cmd, **kwargs):
        if cmd[0] == "nmcli":
            raise FileNotFoundError("nmcli not found")
        elif cmd[0] == "iwgetid":
            return mock.Mock(returncode=0, stdout="FallbackNet\n")
    
    mock_run.side_effect = run_side_effect
    assert query_current_ssid() == "FallbackNet"
    assert mock_run.call_count == 2
