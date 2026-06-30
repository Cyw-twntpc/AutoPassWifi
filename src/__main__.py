"""Entry point: default system tray, --debug for foreground CLI."""

import argparse
import sys

import ctypes
from loguru import logger
from playwright.sync_api import sync_playwright

from src.main import Engine
from src.tray.tray_app import TrayApp
from src.utils.config import AppConfig
from src.utils.autostart import AutostartManager


def _ensure_single_instance() -> None:
    """Exit silently if another instance is already running."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "AutoPassWiFi")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
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
    parser.add_argument(
        "--autostart",
        choices=["register", "remove", "status"],
        help="Manage HKCU\\...\\Run autostart entry",
    )

    args = parser.parse_args()

    config = AppConfig.load()
    _setup_logging(config)

    # Autostart management commands.
    if args.autostart:
        manager = AutostartManager("AutoPassWiFi")
        if args.autostart == "register":
            ok = manager.register()
            print(f"Autostart {'registered' if ok else 'failed'}: {manager.exe_path}")
        elif args.autostart == "remove":
            ok = manager.remove()
            print(f"Autostart {'removed' if ok else 'not found'}")
        elif args.autostart == "status":
            print(f"Registered: {manager.is_registered()}")
            if manager.is_registered():
                print(f"Path: {manager.exe_path}")
        return

    # Debug mode: foreground Engine without tray.
    if args.debug:
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
