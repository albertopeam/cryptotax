"""
loaders.py — Loader base class and platform registry.

Each platform has its own loader file (kraken_loader.py, binance_loader.py, …).
To add a new platform: create a new loader file, import it here, and add it to _PLATFORMS.
"""

from pathlib import Path


class Loader:
    def load_rewards(self, path: Path) -> list[dict]:
        raise NotImplementedError

    def load_trades(self, path: Path) -> list[dict]:
        raise NotImplementedError


# Import after Loader is defined to avoid circular imports
from kraken_loader import KrakenLoader    # noqa: E402
from binance_loader import BinanceLoader  # noqa: E402

_PLATFORMS = [
    ("Kraken",  KrakenLoader),
    ("Binance", BinanceLoader),
]


def select_loader() -> Loader:
    print("\nSelect platform:")
    for i, (name, _) in enumerate(_PLATFORMS, 1):
        print(f"  {i}) {name}")
    while True:
        choice = input("Choice: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(_PLATFORMS):
            name, cls = _PLATFORMS[int(choice) - 1]
            print(f"Platform: {name}")
            return cls()
        print(f"Enter a number between 1 and {len(_PLATFORMS)}.")
