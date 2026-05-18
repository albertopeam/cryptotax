import os
from pathlib import Path


def load_env(env_path: Path) -> None:
    """Loads KEY=VALUE pairs from an .env file into os.environ (no-op if file absent)."""
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
