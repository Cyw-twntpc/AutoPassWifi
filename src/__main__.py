"""Entry point: default system tray, --debug for foreground CLI."""

import argparse
import os
import sys

import ctypes
from loguru import logger
from playwright.sync_api import sync_playwright

from src.main import Engine
from src.tray.tray_app import TrayApp
from src.utils.config import AppConfig


def _ensure_single_instance() -> None:
    """Exit silently if another instance is already running."""
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateMutexW = _kernel32.CreateMutexW
    _CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    _CreateMutexW.restype = ctypes.c_void_p

    _CreateMutexW(None, False, "AutoPassWiFi")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)


def _setup_logging(config: AppConfig) -> None:
    """Configure loguru — file only (no stderr in tray mode)."""
    logger.remove()
    logger.add(
        config.log.file,
        level=config.log.level,
        rotation=config.log.rotation,
        retention=config.log.retention,
        enqueue=True,
    )


def main() -> None:
    _ensure_single_instance()
    parser = argparse.ArgumentParser(description="AutoPassWiFi — Public WiFi Auto-Authenticator")
    parser.add_argument("--debug", action="store_true", help="Run in foreground (no tray icon)")

    args = parser.parse_args()

    config = AppConfig.load()
    _setup_logging(config)

    # Debug mode: foreground Engine without tray.
    if args.debug:
        if getattr(sys, "frozen", False):
            from src.utils.paths import get_app_dir
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(get_app_dir())

        logger.add(sys.stderr, level=config.log.level)
        logger.info("Debug mode — running Engine in foreground")
        pw = sync_playwright()
        pw_instance = pw.start()
        try:
            engine = Engine(config, playwright_instance=pw_instance)
            engine.run()
        except KeyboardInterrupt:
            logger.info("Interrupted, stopping...")
            engine.stop()
        finally:
            pw_instance.stop()
            pw.__exit__(None, None, None)
        return

    # Default: system tray.
    app = TrayApp()
    app.run()


if __name__ == "__main__":
    main()
