"""Application data directory resolution.

Returns the application base directory for storing data and logs.
- Frozen (PyInstaller): directory of the executable.
- Development: project root (parent of src/).
"""

import sys
from pathlib import Path


def get_app_dir() -> Path:
    """Return the application base directory for data/log storage."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


def resolve_app_path(path: str) -> str:
    """If *path* is relative, prepend get_app_dir(). Otherwise return as-is."""
    p = Path(path)
    if p.is_absolute():
        return path
    return str(get_app_dir() / p)
