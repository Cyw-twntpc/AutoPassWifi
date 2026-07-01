# AutoPassWiFi

A Windows system tray application that automatically detects public WiFi captive portals and completes authentication — no browser needed.

## Features

- **Automatic SSID monitoring** — listens for WiFi connection changes via Windows WlanAPI, no polling
- **Captive portal detection** — probes `captive.apple.com` and detects redirects, 204 responses, or 200 responses with non-"Success" body content (distinguishes Apple's success page from portal content)
- **One-click authentication** — automatically submits agreement forms for known SSIDs (e.g. TPE-Free, iTaiwan)
- **Interactive profile recording** — when an unknown SSID portal is encountered, Playwright launches a visible Chromium window for you to complete the login once; the interaction is recorded and replayed automatically next time
- **System tray** — right-click menu to enable / pause / quit; icon changes when paused
- **Single instance** — a second launch exits silently via `CreateMutexW`
- **Persistent profiles** — portal interaction profiles are saved to `portal_profiles.json` and session history to `session_history.json`

## Installation

1. Download the latest installer: `AutoPassWiFi_Setup_0.1.0.exe`
2. Run the installer — it places the executable and Chromium browser under `%LocalAppData%\AutoPassWiFi`
3. The installer automatically adds an entry to `HKCU\...\Run` for autostart on login
4. After installation, AutoPassWiFi appears in the system tray — right-click the WiFi icon to manage it

### Uninstall

Go to **Settings → Apps → AutoPassWiFi** and click **Uninstall**, or run the installer again.

The running application is terminated automatically before uninstall. All application files (executable, Chromium browser, data files, logs) are completely removed.

## Usage

- **System tray icon** — right-click to see the menu
  - **Enable** — resume monitoring after a pause
  - **Pause** — stop monitoring temporarily
  - **Quit** — exit the application
- When connected to a known SSID, AutoPassWiFi automatically detects the captive portal and submits the agreement form
- For an unknown SSID with a portal, a Chromium window opens for one-time interactive recording — the result is saved and replayed automatically on subsequent connections

## How It Works

```
┌──────────────────────────────────────────────────┐
│                   WlanAPI                         │
│   WlanRegisterNotification  (SSID change event)  │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│              SessionTracker                       │
│   Cubic exponential backoff between checks        │
│   (30s → 60s → 2m → 4m → max 1h)                │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│            PortalDetector                        │
│   HTTP GET captive.apple.com (follow_redirects=0)│
│   204 → no portal  200+Success → no portal       │
│   200+other → portal  302/418 → redirect URL     │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│       ClickthroughProvider (3 phases)            │
│                                                    │
│  ① Replay — replay saved interaction for SSID    │
│  ② Auto-detect — scan for submit buttons         │
│  ③ Interactive — open visible Chromium, record   │
└──────────────────────────────────────────────────┘
```

### Core Components

| Module | Role |
|---|---|
| `connection_monitor.py` | ctypes wrapper around `WlanRegisterNotification` — fires callback on SSID change (connect/disconnect/roam) |
| `portal_detector.py` | HTTP probe to `captive.apple.com`; detects portal presence via status codes and response body content |
| `session_tracker.py` | Tracks session state with cubic exponential backoff (90s base, 1h ceiling) to avoid hammering the network |
| `clickthrough.py` | Playwright-based three-phase portal interaction: replay saved profile → auto-detect submit button → interactive recording |
| `portal_profile_store.py` | JSON-persisted store mapping SSID → recorded interaction sequences |
| `main.py` | Engine that wires everything together: receives SSID events, invokes detection, delegates to authentication |

### Technologies

- **Python 3.12** — stdlib as much as possible (ctypes, winreg, threading, http.server, json)
- **WlanAPI (ctypes)** — `WlanOpenHandle`, `WlanRegisterNotification`, `WlanGetProfileList` for native WiFi event handling
- **httpx** — HTTP probe with `follow_redirects=False` for portal detection
- **Playwright** — headless Chromium control for portal interaction (replay/auto-detect/record)
- **pystray + Pillow** — system tray icon and menu
- **loguru** — file-based logging with rotation
- **PyInstaller** — single-file `--onefile --noconsole` packaging
- **Inno Setup** — installer that bundles Chromium alongside the executable

## Requirements

- **Windows 10 or 11** (uses Win32 API, not cross-platform)
- WiFi adapter (for WlanAPI events)
- Internet connection for captive portal detection

## License

MIT
