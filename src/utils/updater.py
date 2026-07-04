"""Auto-updater module for AutoPassWiFi."""

import json
import os
import subprocess
import tempfile
import threading
import urllib.request
from typing import Optional

from loguru import logger

from src import __version__

# Replace with the actual repository
GITHUB_REPO = "Cyw-twntpc/AutoPassWifi"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

CHECK_INTERVAL = 24 * 60 * 60  # 24 hours in seconds


class AutoUpdater:
    """Check for updates and download/install them silently in the background."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
    def start_background_task(self) -> None:
        """Start the background checking thread."""
        if self._thread is not None and self._thread.is_alive():
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop_background_task(self) -> None:
        """Stop the background checking thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        """Periodic check loop."""
        while not self._stop_event.is_set():
            try:
                self.check_and_install_update()
            except Exception as e:
                logger.error("AutoUpdater background loop error: {e}", e=e)
            
            # Wait for CHECK_INTERVAL or stop event
            self._stop_event.wait(CHECK_INTERVAL)

    def check_and_install_update(self) -> bool:
        """Check for updates and if available, download and install silently."""
        try:
            logger.info("Checking for updates...")
            req = urllib.request.Request(RELEASES_API)
            req.add_header("User-Agent", "AutoPassWiFi-Updater")
            req.add_header("Accept", "application/vnd.github.v3+json")
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    logger.warning("Failed to fetch latest release. HTTP {status}", status=response.status)
                    return False
                    
                data = json.loads(response.read().decode("utf-8"))
                
            tag_name = data.get("tag_name", "")
            if not tag_name:
                return False
                
            # Naive semantic versioning string compare (assumes format vX.Y.Z)
            remote_version = tag_name.lstrip("vV")
            
            if self._is_newer(remote_version, __version__):
                logger.info("Found newer version: {v}. Current: {c}", v=remote_version, c=__version__)
                
                # Find the setup executable asset
                download_url = None
                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    if "setup" in name and name.endswith(".exe"):
                        download_url = asset.get("browser_download_url")
                        break
                        
                if download_url:
                    return self._download_and_install(download_url)
                else:
                    logger.warning("No setup executable found in release assets.")
            else:
                logger.info("AutoPassWiFi is up to date.")
                
            return False

        except Exception as e:
            logger.error("Update check failed: {e}", e=e)
            return False

    def _is_newer(self, remote: str, local: str) -> bool:
        """Compare semver strings. True if remote is strictly greater."""
        try:
            r_parts = [int(x) for x in remote.split(".")]
            l_parts = [int(x) for x in local.split(".")]
            return r_parts > l_parts
        except ValueError:
            # Fallback to string comparison if not standard integers
            return remote > local

    def _download_and_install(self, url: str) -> bool:
        """Download the installer and execute it silently."""
        logger.info("Downloading update from {url}", url=url)
        temp_dir = tempfile.gettempdir()
        installer_path = os.path.join(temp_dir, "AutoPassWiFi_Update.exe")
        
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "AutoPassWiFi-Updater")
            with urllib.request.urlopen(req, timeout=60) as response, open(installer_path, "wb") as out_file:
                out_file.write(response.read())
                
            logger.info("Download complete. Launching installer silently...")
            # Use DETACHED_PROCESS so the installer isn't killed if the python process dies
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                [installer_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NOCANCEL"],
                creationflags=DETACHED_PROCESS,
                close_fds=True
            )
            # We don't sys.exit(0) here because the installer will kill this process
            # via `KillApp` taskkill during its InitializeSetup step.
            return True
            
        except Exception as e:
            logger.error("Failed to download or execute update: {e}", e=e)
            return False

# Global instance
updater = AutoUpdater()
