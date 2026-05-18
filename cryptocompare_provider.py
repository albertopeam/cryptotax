"""
cryptocompare_provider.py — PriceProvider implementation using CryptoCompare.

Advantages over CoinGecko Demo:
  - No historical data age restriction (full history available)
  - Returns a full year in a single call per asset (~12 calls total)
  - Free plan: 100,000 calls/month, free key at min-api.cryptocompare.com

Free registration: https://www.cryptocompare.com/cryptopian/api-keys
"""

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from price_provider import PriceProvider


# Exchange ticker → CryptoCompare symbol (most match directly)
CRYPTOCOMPARE_SYMBOLS: dict[str, Optional[str]] = {
    "ADA":   "ADA",
    "ATOM":  "ATOM",
    "BNB":   "BNB",
    "BTC":   "BTC",
    "DOT":   "DOT",
    "EIGEN": "EIGEN",
    "ETH":   "ETH",
    "EUR":   None,    # already in EUR → price is always 1.0
    "JUNO":  "JUNO",
    "KAVA":  "KAVA",
    "SOL":   "SOL",
    "TIA":   "TIA",
    "USDC":  "USDC",
    "USDT":  "USDT",
}

BASE_URL = "https://min-api.cryptocompare.com/data/v2/histoday"
DELAY_SECONDS = 0.5   # free plan: 100,000 calls/month, no strict per-minute limit
CACHE_FILE = Path(__file__).parent / ".price_cache.json"


class CryptoCompareProvider(PriceProvider):
    """
    Fetches historical daily prices in EUR via CryptoCompare (histoday).

    Downloads the full year range in a single call per asset, persists
    the result to local cache, and never re-fetches already-known dates.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key
        self._cache = self._load_cache()

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _load_cache(self) -> dict[str, dict[date, float]]:
        if not CACHE_FILE.exists():
            return {}
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return {
            asset: {date.fromisoformat(d): p for d, p in prices.items()}
            for asset, prices in raw.items()
        }

    def _save_cache(self) -> None:
        raw = {
            asset: {d.isoformat(): p for d, p in prices.items()}
            for asset, prices in self._cache.items()
        }
        CACHE_FILE.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── API call ──────────────────────────────────────────────────────────────

    def _fetch_range(self, symbol: str, start: date, end: date) -> dict[date, float]:
        """Downloads all days between start and end in a single API call."""
        limit = (end - start).days + 1
        to_ts = int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp())

        params: dict = {
            "fsym":  symbol,
            "tsym":  "EUR",
            "limit": limit,
            "toTs":  to_ts,
        }
        if self._api_key:
            params["api_key"] = self._api_key

        resp = requests.get(BASE_URL, params=params, timeout=15)

        if resp.status_code == 401:
            raise RuntimeError(
                "CryptoCompare: invalid API key. "
                "Check CRYPTOCOMPARE_API_KEY in .env"
            )
        resp.raise_for_status()
        time.sleep(DELAY_SECONDS)

        data = resp.json()
        if data.get("Response") == "Error":
            raise RuntimeError(f"CryptoCompare error for {symbol}: {data.get('Message')}")

        return {
            date.fromtimestamp(entry["time"]): entry["close"]
            for entry in data["Data"]["Data"]
            if entry["close"] > 0
        }

    # ── Public interface ──────────────────────────────────────────────────────

    def get_daily_prices(self, asset: str, dates: set[date]) -> dict[date, float]:
        symbol = CRYPTOCOMPARE_SYMBOLS.get(asset)
        if symbol is None:
            return {}

        if asset not in self._cache:
            self._cache[asset] = {}

        cached = self._cache[asset]
        missing = dates - set(cached.keys())

        if missing:
            start = min(missing)
            end   = max(missing)
            print(f"    downloading {start} → {end} ...", end="\r", flush=True)
            fetched = self._fetch_range(symbol, start, end)
            cached.update(fetched)
            self._save_cache()
            n_new    = len(fetched)
            print(f"    {n_new} days downloaded · {len(dates)} with rewards".ljust(60))
        else:
            print(f"    {len(dates)} dates cached".ljust(60))

        return {d: cached[d] for d in dates if d in cached}
