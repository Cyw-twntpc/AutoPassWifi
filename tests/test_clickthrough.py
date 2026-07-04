"""Tests for ClickthroughProvider."""

from unittest.mock import MagicMock, patch

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from src.providers.clickthrough import (
    ClickthroughProvider,
    _verify_open_internet,
    _CAPTCHA_PATTERNS,
)
from src.utils.portal_profile_store import PortalProfileStore, RecordedStep


# ── _verify_open_internet ──────────────────────────────────────


def test_verify_open_internet_success():
    """Returns True when page contains 'Success'."""
    page = MagicMock()
    page.content.return_value = "<html>Success</html>"
    probe_urls = ["http://captive.apple.com"]
    assert _verify_open_internet(page, probe_urls) is True


def test_verify_open_internet_failure():
    """Returns False when page does not contain 'Success'."""
    page = MagicMock()
    page.content.return_value = "<html>Redirected</html>"
    probe_urls = ["http://captive.apple.com"]
    assert _verify_open_internet(page, probe_urls) is False


def test_verify_open_internet_timeout():
    """Returns False when goto raises."""
    page = MagicMock()
    page.goto.side_effect = PlaywrightTimeout("timeout")
    probe_urls = ["http://captive.apple.com"]
    assert _verify_open_internet(page, probe_urls) is False


# ── _is_captcha_field / _classify_steps ────────────────────────


def test_is_captcha_field_positive():
    """Fields containing 'captcha' or '驗證' pattern are detected."""
    provider = ClickthroughProvider(browser=MagicMock())
    assert provider._is_captcha_field("input#captcha") is True
    assert provider._is_captcha_field("#verification_code") is True
    assert provider._is_captcha_field("input[name='驗證碼']") is True
    assert provider._is_captcha_field("#sms_code") is True


def test_is_captcha_field_negative():
    """Non-captcha fields return False."""
    provider = ClickthroughProvider(browser=MagicMock())
    assert provider._is_captcha_field("#username") is False
    assert provider._is_captcha_field("#password") is False
    assert provider._is_captcha_field("#agree") is False


def test_classify_steps_marks_captcha(mock_playwright):
    """_classify_steps sets must_interact=True and clears value for captcha fields."""
    provider = ClickthroughProvider(browser=MagicMock())
    steps = [
        RecordedStep(type="fill", selector="#username", value="user"),
        RecordedStep(type="fill", selector="#captcha_input", value="1234"),
        RecordedStep(type="click", selector="#agree"),
    ]
    result = provider._classify_steps(MagicMock(), steps)
    # username: not captcha
    assert result[0].must_interact is False
    assert result[0].value == "user"
    # captcha_input: captcha
    assert result[1].must_interact is True
    assert result[1].value == ""  # cleared
    # click: not fill, so skipped
    assert result[2].must_interact is False


# ── Phase 2: auto-detect ───────────────────────────────────────


def test_auto_detect_success(mock_playwright):
    """_auto_detect clicks an agree button and verifies."""
    provider = ClickthroughProvider(browser=mock_playwright["browser"])
    # Make _find_button return the first locator.
    provider._find_button = MagicMock(return_value=mock_playwright["locator"])
    provider._last_matched_index = 0
    mock_playwright["locator"].inner_text.return_value = "同意"

    success, selector = provider._auto_detect("http://portal.example.com")
    assert success is True
    assert selector is not None


def test_auto_detect_no_button(mock_playwright):
    """_auto_detect returns False when no agree button found."""
    provider = ClickthroughProvider(browser=mock_playwright["browser"])
    provider._find_button = MagicMock(return_value=None)

    success, selector = provider._auto_detect("http://portal.example.com")
    assert success is False
    assert selector is None


def test_auto_detect_playwright_timeout(mock_playwright):
    """_auto_detect returns False on PlaywrightTimeout."""
    provider = ClickthroughProvider(browser=mock_playwright["browser"])
    mock_playwright["page"].goto.side_effect = PlaywrightTimeout("timeout")

    success, selector = provider._auto_detect("http://portal.example.com")
    assert success is False


# ── Phase 1: replay ────────────────────────────────────────────


def test_replay_profile_success(mock_playwright):
    """Full replay of non-captcha steps succeeds."""
    steps = [
        RecordedStep(type="click", selector="#agree", wait_after=0),
    ]
    profile = MagicMock()
    profile.steps = steps

    provider = ClickthroughProvider(browser=mock_playwright["browser"])
    result = provider._replay_profile("http://portal.example.com", "TestNet", profile)
    assert result is True


def test_replay_profile_captcha_triggers_interactive(mock_playwright):
    """Step with must_interact=True triggers interactive mode."""
    steps = [
        RecordedStep(type="click", selector="#agree", wait_after=0),
        RecordedStep(type="fill", selector="#captcha", must_interact=True),
    ]
    profile = MagicMock()
    profile.steps = steps

    provider = ClickthroughProvider(browser=mock_playwright["browser"])
    # _interactive_login will be called — mock it to return True.
    provider._interactive_login = MagicMock(return_value=True)

    result = provider._replay_profile("http://portal.example.com", "TestNet", profile)
    assert result is True  # _interactive_login returns True


def test_replay_profile_failed_step(mock_playwright):
    """Failed step returns False."""
    mock_playwright["locator"].wait_for.side_effect = PlaywrightTimeout("timeout")
    steps = [RecordedStep(type="click", selector="#missing", wait_after=0)]
    profile = MagicMock()
    profile.steps = steps

    provider = ClickthroughProvider(browser=mock_playwright["browser"])
    result = provider._replay_profile("http://portal.example.com", "TestNet", profile)
    assert result is False


@patch('src.providers.clickthrough.keyring')
def test_replay_profile_with_password(mock_keyring, mock_playwright):
    """Replay fetches password from keyring."""
    mock_keyring.get_password.return_value = "mysecret"

    steps = [
        RecordedStep(type="fill", selector="#pwd", value="<SECURE_CREDENTIAL>", wait_after=0, is_password=True),
    ]
    profile = MagicMock()
    profile.steps = steps

    provider = ClickthroughProvider(browser=mock_playwright["browser"])
    result = provider._replay_profile("http://portal.example.com", "TestNet", profile)
    assert result is True

    mock_keyring.get_password.assert_called_once_with("AutoPassWiFi", "TestNet_#pwd")
    mock_playwright["locator"].fill.assert_called_once_with("mysecret")


# ── Phase 3: interactive ───────────────────────────────────────


def test_interactive_login_success(mock_playwright):
    """Interactive login records steps and returns True."""
    fake_steps = [
        {"type": "click", "selector": "#agree", "text": "同意", "url": "http://portal.example.com/"},
    ]
    mock_playwright["page"].evaluate.return_value = fake_steps

    provider = ClickthroughProvider(
        browser=mock_playwright["browser"],
        playwright=mock_playwright["playwright"],
        profile_store=PortalProfileStore(data_file=":memory:"),
    )
    provider._poll_captive_status = MagicMock(return_value=True)

    result = provider._interactive_login("http://portal.example.com", "TestNet")
    assert result is True


def test_interactive_login_timeout(mock_playwright):
    """Interactive login returns False when _poll_captive_status times out."""
    provider = ClickthroughProvider(
        browser=mock_playwright["browser"],
        playwright=mock_playwright["playwright"],
    )
    provider._poll_captive_status = MagicMock(return_value=False)

    result = provider._interactive_login("http://portal.example.com", "TestNet")
    assert result is False


def test_interactive_login_with_start_idx(mock_playwright):
    """Interactive login with start_idx replays pre-steps before recording."""
    fake_steps = [
        {"type": "click", "selector": "#captcha_submit", "text": "Submit"},
    ]
    mock_playwright["page"].evaluate.return_value = fake_steps

    profile = MagicMock()
    profile.steps = [
        RecordedStep(type="fill", selector="#username", value="user"),
        RecordedStep(type="fill", selector="#captcha"),  # must_interact
    ]

    provider = ClickthroughProvider(
        browser=mock_playwright["browser"],
        playwright=mock_playwright["playwright"],
        profile_store=PortalProfileStore(data_file=":memory:"),
    )
    provider._poll_captive_status = MagicMock(return_value=True)

    result = provider._interactive_login(
        "http://portal.example.com", "TestNet", start_idx=1, profile=profile,
    )
    assert result is True


@patch('src.providers.clickthrough.keyring')
def test_interactive_login_records_password(mock_keyring, mock_playwright):
    """Interactive login uses keyring for all non-captcha steps."""
    fake_steps = [
        {"type": "fill", "selector": "#username", "value": "secret123"},
    ]
    mock_playwright["page"].evaluate.return_value = fake_steps

    profile_store = PortalProfileStore(data_file=":memory:")
    provider = ClickthroughProvider(
        browser=mock_playwright["browser"],
        playwright=mock_playwright["playwright"],
        profile_store=profile_store,
    )
    provider._poll_captive_status = MagicMock(return_value=True)

    result = provider._interactive_login("http://portal.example.com", "TestNet")
    assert result is True

    # Verify keyring was called
    mock_keyring.set_password.assert_called_once_with("AutoPassWiFi", "TestNet_#username", "secret123")

    # Verify profile store got the placeholder
    profile = profile_store.get_profile("TestNet")
    assert profile.steps[0].value == "<SECURE_CREDENTIAL>"
    assert profile.steps[0].is_password is True


# ── `authenticate` (three-phase entry point) ───────────────────


def test_authenticate_replay_success(mock_playwright):
    """authenticate calls Phase 1 first and returns on success."""
    profile_store = PortalProfileStore(data_file=":memory:")
    profile_store.save_profile("TestNet", [
        RecordedStep(type="click", selector="#agree"),
    ])

    provider = ClickthroughProvider(
        browser=mock_playwright["browser"],
        profile_store=profile_store,
    )
    provider._replay_profile = MagicMock(return_value=True)

    result = provider.authenticate("http://portal.example.com", "TestNet")
    assert result is True
    provider._replay_profile.assert_called_once()


def test_authenticate_fallback_to_auto_detect(mock_playwright):
    """authenticate falls back to Phase 2 when replay fails."""
    profile_store = PortalProfileStore(data_file=":memory:")
    profile_store.save_profile("TestNet", [RecordedStep(type="click", selector="#agree")])

    provider = ClickthroughProvider(
        browser=mock_playwright["browser"],
        profile_store=profile_store,
    )
    provider._replay_profile = MagicMock(return_value=False)
    provider._auto_detect = MagicMock(return_value=(True, "#agree"))

    result = provider.authenticate("http://portal.example.com", "TestNet")
    assert result is True
    provider._replay_profile.assert_called_once()
    provider._auto_detect.assert_called_once()


def test_authenticate_fallback_to_interactive(mock_playwright):
    """authenticate falls back to Phase 3 when auto-detect fails."""
    profile_store = PortalProfileStore(data_file=":memory:")
    profile_store.save_profile("TestNet", [RecordedStep(type="click", selector="#agree")])

    provider = ClickthroughProvider(
        browser=mock_playwright["browser"],
        profile_store=profile_store,
    )
    provider._replay_profile = MagicMock(return_value=False)
    provider._auto_detect = MagicMock(return_value=(False, None))
    provider._interactive_login = MagicMock(return_value=True)

    result = provider.authenticate("http://portal.example.com", "TestNet")
    assert result is True
    provider._interactive_login.assert_called_once()
