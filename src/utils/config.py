"""Configuration — hardcoded defaults, no external YAML file."""

from dataclasses import dataclass, field

from src.utils.paths import resolve_app_path


@dataclass
class LogConfig:
    """Logging settings passed directly to loguru.add()."""
    level: str = "INFO"
    file: str = "logs/service.log"
    rotation: str = "10 MB"
    retention: str = "30 days"


@dataclass
class SessionConfig:
    default_interval: float = 60.0   # Check interval (s) when no history
    overrun_interval: float = 20.0   # Check interval (s) past recorded duration
    stable_threshold: float = 18000.0  # do not change
    data_file: str = "session_history.json"  # Session records path (relative to app dir)
    cubic_k: float = 0.001  # do not change


@dataclass
class AppConfig:
    """Top-level application configuration."""
    probe_url: str = "http://captive.apple.com"
    session: SessionConfig = field(default_factory=SessionConfig)
    log: LogConfig = field(default_factory=LogConfig)

    @classmethod
    def load(cls) -> "AppConfig":
        """Return a new AppConfig with relative paths resolved against app directory."""
        result = cls()
        result.log.file = resolve_app_path(result.log.file)
        result.session.data_file = resolve_app_path(result.session.data_file)
        return result
