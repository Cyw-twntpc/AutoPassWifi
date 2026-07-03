"""Tests for cross-platform autostart manager."""

import sys
from pathlib import Path
from unittest import mock

import pytest
from src.utils.autostart import AutostartManager


@pytest.fixture
def mock_app_name():
    return "TestAutoPass"

def test_autostart_manager_init(mock_app_name):
    manager = AutostartManager(mock_app_name)
    assert manager._app_name == mock_app_name
    assert manager._platform == sys.platform
    assert "python" in manager.exe_path.lower() or manager.exe_path != ""

@mock.patch("sys.platform", "darwin")
def test_autostart_macos(mock_app_name, tmp_path):
    manager = AutostartManager(mock_app_name)
    # mock home directory to temp
    with mock.patch("pathlib.Path.home", return_value=tmp_path):
        plist_path = manager._macos_plist_path
        
        # Test register
        assert manager.register() is True
        assert plist_path.exists()
        content = plist_path.read_text(encoding="utf-8")
        assert f"com.{mock_app_name}" in content
        assert manager.exe_path in content
        
        # Test is_registered
        assert manager.is_registered() is True
        
        # Test remove
        assert manager.remove() is True
        assert not plist_path.exists()
        assert manager.is_registered() is False


@mock.patch("sys.platform", "linux")
def test_autostart_linux(mock_app_name, tmp_path):
    manager = AutostartManager(mock_app_name)
    with mock.patch("pathlib.Path.home", return_value=tmp_path):
        desktop_path = manager._linux_desktop_path
        
        # Test register
        assert manager.register() is True
        assert desktop_path.exists()
        content = desktop_path.read_text(encoding="utf-8")
        assert f"Name={mock_app_name}" in content
        assert f"Exec={manager.exe_path}" in content
        
        # Test is_registered
        assert manager.is_registered() is True
        
        # Test remove
        assert manager.remove() is True
        assert not desktop_path.exists()
        assert manager.is_registered() is False

@mock.patch("sys.platform", "win32")
@mock.patch("winreg.OpenKey")
@mock.patch("winreg.SetValueEx")
@mock.patch("winreg.DeleteValue")
@mock.patch("winreg.QueryValueEx")
def test_autostart_win32(mock_query, mock_delete, mock_set, mock_open, mock_app_name):
    manager = AutostartManager(mock_app_name)
    
    # Test register
    assert manager.register() is True
    mock_set.assert_called_once()
    
    # Test is_registered (matches)
    mock_query.return_value = (manager.exe_path, 1)
    assert manager.is_registered() is True
    
    # Test remove
    assert manager.remove() is True
    mock_delete.assert_called_once()
