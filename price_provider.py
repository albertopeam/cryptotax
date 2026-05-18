"""
price_provider.py — Abstract base class for historical price providers.

To switch APIs:
  1. Create a new class that inherits from PriceProvider and implements get_daily_prices()
  2. Replace the instance in staking.py (one line)

Included implementations:
  - CoinGeckoProvider  (requires free Demo key from coingecko.com/en/api)
"""

import json
import time
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests


COINGECKO_IDS: dict[str, Optional[str]] = {
    "ADA":   "cardano",
    "ATOM":  "cosmos",
    "BTC":   "bitcoin",
    "DOT":   "polkadot",
    "EIGEN": "eigenlayer",
    "ETH":   "ethereum",
    "EUR":   None,
    "JUNO":  "juno-network",
    "KAVA":  "kava",
    "SOL":   "solana",
    "TIA":   "celestia",
    "USDC":  "usd-coin",
    "USDT":  "tether",
}


class PriceProvider(ABC):
    """
    Interface that all price providers must implement.

    get_daily_prices() receives the exact set of dates needed and returns
    {date: eur_price}. Only dates with actual rewards are requested,
    minimizing API calls.
    """

    @abstractmethod
    def get_daily_prices(self, asset: str, dates: set[date]) -> dict[date, float]:
        """
        Returns {day: eur_price} for each date in the received set.
        If the asset has no mapping, returns {}.
        """


class CoinGeckoProvider(PriceProvider):
    """
    Implementation using CoinGecko's /coins/{id}/history endpoint.

    - Requires a free Demo key (coingecko.com/en/api)
    - Local cache in .price_cache.json: already-fetched dates are never
      re-requested, neither in the same run nor in future runs
    - Request delay lives here, not in the main scripts
    """

    BASE_URL = "https://api.coingecko.com/api/v3"
    DELAY_SECONDS = 1.0       # Demo plan: 100 req/min → ~0.6 s minimum
    CACHE_FILE = Path(__file__).parent / ".price_cache.json"

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key
        self._ids = COINGECKO_IDS
        self._cache = self._load_cache()

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _load_cache(self) -> dict[str, dict[date, float]]:
        if not self.CACHE_FILE.exists():
            return {}
        raw = json.loads(self.CACHE_FILE.read_text(encoding="utf-8"))
        return {
            asset: {date.fromisoformat(d): p for d, p in prices.items()}
            for asset, prices in raw.items()
        }

    def _save_cache(self) -> None:
        raw = {
            asset: {d.isoformat(): p for d, p in prices.items()}
            for asset, prices in self._cache.items()
        }
        self.CACHE_FILE.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── API call ──────────────────────────────────────────────────────────────

    def _fetch_price(self, coin_id: str, day: date) -> Optional[float]:
        url = f"{self.BASE_URL}/coins/{coin_id}/history"
        params = {"date": day.strftime("%d-%m-%Y"), "localization": "false"}
        headers = {"x-cg-demo-api-key": self._api_key} if self._api_key else {}

        resp = requests.get(url, params=params, headers=headers, timeout=15)

        if resp.status_code == 401:
            raise RuntimeError(
                "CoinGecko: invalid API key or missing permissions. "
                "Check the key in .env (coingecko.com/en/api)"
            )
        resp.raise_for_status()
        time.sleep(self.DELAY_SECONDS)

        data = resp.json()
        return data.get("market_data", {}).get("current_price", {}).get("eur")

    # ── Public interface ──────────────────────────────────────────────────────

    def get_daily_prices(self, asset: str, dates: set[date]) -> dict[date, float]:
        coin_id = self._ids.get(asset)
        if coin_id is None:
            return {}

        if asset not in self._cache:
            self._cache[asset] = {}

        cached = self._cache[asset]
        missing = sorted(dates - set(cached.keys()))
        total_missing = len(missing)
        n_cached = len(dates) - total_missing

        if missing:
            for i, day in enumerate(missing, 1):
                _bar = _progress_bar(i, total_missing)
                print(f"    {_bar} {i}/{total_missing} new, {n_cached} cached",
                      end="\r", flush=True)
                price = self._fetch_price(coin_id, day)
                if price is not None:
                    cached[day] = price
            self._save_cache()
            print(f"    {_progress_bar(total_missing, total_missing)} "
                  f"{total_missing} new, {n_cached} cached  ")
        else:
            print(f"    {n_cached} dates cached  ")

        return {d: cached[d] for d in dates if d in cached}


def _progress_bar(current: int, total: int, width: int = 20) -> str:
    filled = int(width * current / total) if total else width
    return f"[{'█' * filled}{'░' * (width - filled)}]"


# ---------------------------------------------------------------------------
# To add a new provider:
#
# class MyProvider(PriceProvider):
#     def get_daily_prices(self, asset: str, dates: set[date]) -> dict[date, float]:
#         ...
# ---------------------------------------------------------------------------
