import pytest
from src.utils.updater import AutoUpdater

@pytest.fixture
def updater():
    return AutoUpdater()

@pytest.mark.parametrize("remote, local, expected", [
    ("1.0.1", "1.0.0", True),
    ("1.1.0", "1.0.0", True),
    ("2.0.0", "1.9.9", True),
    ("1.0.0", "1.0.0", False),
    ("0.9.9", "1.0.0", False),
    ("1.0", "1.0.0", False), # Python lists: [1, 0] > [1, 0, 0] is False
    ("1.0.1.1", "1.0.1", True),
    ("2.0", "1.0.0", True), # [2, 0] > [1, 0, 0] is True
])
def test_is_newer(updater, remote, local, expected):
    """Test the semantic version comparison logic."""
    assert updater._is_newer(remote, local) == expected

def test_is_newer_fallback(updater):
    """Test the fallback string comparison when versions aren't pure integers."""
    assert updater._is_newer("1.0.0-beta", "1.0.0-alpha") is True
