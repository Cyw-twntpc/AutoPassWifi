"""Tests for detect_captive_portal."""

from src.core.portal_detector import detect_captive_portal


def test_open_internet_204(mock_httpx_success):
    """204 response means open internet → None."""
    result = detect_captive_portal("http://captive.apple.com")
    assert result is None


def test_open_internet_200(mock_httpx_success_200):
    """200 with 'Success' body means open internet → None."""
    result = detect_captive_portal("http://captive.apple.com")
    assert result is None


def test_non_redirect_portal(mock_httpx_success):
    """Non-2xx/3xx status with captured body returns the response URL."""
    from unittest.mock import PropertyMock

    resp = mock_httpx_success.return_value.__enter__.return_value.get.return_value
    resp.status_code = 418
    resp.headers = {}
    type(resp).url = PropertyMock(return_value="http://portal.example.com/")

    result = detect_captive_portal("http://captive.apple.com")
    assert result == "http://portal.example.com/"


def test_redirect_detected(mock_httpx_redirect):
    """302 with Location header returns the redirect URL."""
    result = detect_captive_portal("http://captive.apple.com")
    assert result == "http://portal.example.com/login"


def test_redirect_no_location(mock_httpx_redirect):
    """302 without Location header returns the response URL."""
    from unittest.mock import PropertyMock

    resp = mock_httpx_redirect.return_value.__enter__.return_value.get.return_value
    resp.headers = {}  # no Location
    type(resp).url = PropertyMock(return_value="http://portal.example.com/redirected")

    result = detect_captive_portal("http://captive.apple.com")
    assert result == "http://portal.example.com/redirected"


def test_request_error(mock_httpx_error):
    """httpx.RequestError (no network) returns None."""
    result = detect_captive_portal("http://captive.apple.com")
    assert result is None


def test_content_length_none(mock_httpx_success):
    """content-length header missing should not crash."""
    from unittest.mock import PropertyMock

    resp = mock_httpx_success.return_value.__enter__.return_value.get.return_value
    resp.status_code = 418
    resp.headers = {}  # no content-length at all
    type(resp).url = PropertyMock(return_value="http://portal.example.com/")

    result = detect_captive_portal("http://captive.apple.com")
    assert result == "http://portal.example.com/"


def test_content_length_invalid(mock_httpx_success):
    """content-length with non-numeric value should not crash."""
    from unittest.mock import PropertyMock

    resp = mock_httpx_success.return_value.__enter__.return_value.get.return_value
    resp.status_code = 418
    resp.headers = {"content-length": "abc"}
    type(resp).url = PropertyMock(return_value="http://portal.example.com/")

    result = detect_captive_portal("http://captive.apple.com")
    assert result == "http://portal.example.com/"
