"""Shared fixtures and mocks for autopasswifi tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

# Ensure the project root (parent of tests/) is on sys.path so
# ``from src.xxx`` imports work regardless of how pytest is launched.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest
from pytest_mock import MockerFixture


@pytest.fixture
def mock_httpx_success(mocker: MockerFixture):
    """Mock httpx.Client.get to return 204 (open internet)."""
    resp = MagicMock()
    resp.status_code = 204
    mock_client = mocker.patch("httpx.Client", autospec=True)
    mock_client.return_value.__enter__.return_value.get.return_value = resp
    return mock_client


@pytest.fixture
def mock_httpx_redirect(mocker: MockerFixture):
    """Mock httpx.Client.get to return 302 with a redirect Location."""
    resp = MagicMock()
    resp.status_code = 302
    resp.headers = {"location": "http://portal.example.com/login"}
    mock_client = mocker.patch("httpx.Client", autospec=True)
    mock_client.return_value.__enter__.return_value.get.return_value = resp
    return mock_client


@pytest.fixture
def mock_httpx_success_200(mocker: MockerFixture):
    """Mock httpx.Client.get to return 200 + 'Success' body (open internet)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "Success\n"
    mock_client = mocker.patch("httpx.Client", autospec=True)
    mock_client.return_value.__enter__.return_value.get.return_value = resp
    return mock_client


@pytest.fixture
def mock_httpx_modified(mocker: MockerFixture):
    """Mock httpx.Client.get to return 200 + captive portal URL via resp.url."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "<html><head><title>Portal Login</title></head></html>"
    resp.headers = {"content-length": "50"}
    type(resp).url = PropertyMock(return_value="http://portal.example.com/")
    mock_client = mocker.patch("httpx.Client", autospec=True)
    mock_client.return_value.__enter__.return_value.get.return_value = resp
    return mock_client


@pytest.fixture
def mock_httpx_error(mocker: MockerFixture):
    """Mock httpx.Client.get to raise RequestError (no network)."""
    import httpx
    mock_client = mocker.patch("httpx.Client", autospec=True)
    mock_client.return_value.__enter__.return_value.get.side_effect = (
        httpx.RequestError("No network")
    )
    return mock_client


@pytest.fixture
def mock_playwright(mocker: MockerFixture):
    """Create a complete mock Playwright browser stack."""
    mock_browser = MagicMock()
    mock_visible_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    # Browser.new_context → context
    mock_browser.new_context.return_value = mock_context
    # Context.new_page → page
    mock_context.new_page.return_value = mock_page

    # Visible browser for Phase 3.
    mock_playwright_obj = MagicMock()
    mock_playwright_obj.chromium.launch.return_value = mock_visible_browser
    mock_visible_browser.new_context.return_value = mock_context

    # Page helper
    mock_locator = MagicMock()
    mock_page.locator.return_value = mock_locator
    mock_locator.first = mock_locator

    # page.goto
    mock_page.goto.return_value = None

    # page.content for verification
    mock_page.content.return_value = "<html>Success</html>"

    # page.evaluate for recording script
    mock_page.evaluate.return_value = []

    # page.add_init_script
    mock_page.add_init_script.return_value = None

    return {
        "browser": mock_browser,
        "playwright": mock_playwright_obj,
        "context": mock_context,
        "page": mock_page,
        "locator": mock_locator,
    }
