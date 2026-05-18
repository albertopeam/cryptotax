# Price APIs

## API key convention

Keys are read from `.env` via `load_env()` (defined in `utils.py`) + `os.environ.get(...)`.
Never prompt interactively. Any script that needs prices must call
`load_env(Path(__file__).parent / ".env")` near the top of its `main()`.

Keys in `.env.example`:
- `CRYPTOCOMPARE_API_KEY` — preferred; full historical data, no age restriction
- `COINGECKO_API_KEY` — fallback for `staking.py` only

---

## Active provider: CryptoCompare

**File:** `cryptocompare_provider.py` — class `CryptoCompareProvider`

**Why CryptoCompare instead of CoinGecko:**
- CoinGecko's free Demo tier restricts the `/coins/{id}/history` endpoint to roughly the last
  365 days (and historically has been as low as 3 months). For tax declarations covering prior
  years, this makes it unreliable.
- CryptoCompare's `histoday` endpoint returns full historical data with no age restriction,
  and downloads a full date range in a single call per asset.

**Endpoint:** `https://min-api.cryptocompare.com/data/v2/histoday`

**Free plan limits:** 100,000 calls/month, no strict per-minute cap.
Delay between calls: 0.5 s (configured in `DELAY_SECONDS`).

**Free key registration:** https://www.cryptocompare.com/cryptopian/api-keys

**API key:** Passed via the `CRYPTOCOMPARE_API_KEY` environment variable (read from `.env`).
Works without a key but at lower rate limits.

**Cache:** `.price_cache.json` in the project directory, shared between `staking.py` and
`trades.py` runs. Already-fetched dates are never re-requested. Format:
```json
{
  "BTC": { "2025-01-01": 95000.5, "2025-01-02": 94500.0 },
  "ETH": { "2025-01-01": 3400.0 }
}
```
Asset symbol → ISO date → EUR closing price. Read on `__init__`, skip known dates, write back after each successful fetch. Delete the file to force a full re-download.

**Adding a new asset:** Add an entry to `CRYPTOCOMPARE_SYMBOLS` in `cryptocompare_provider.py`:
```python
"XRP": "XRP",   # symbol matches CryptoCompare directly in most cases
```
Set the value to `None` for EUR (no price lookup needed).

---

## Inactive provider: CoinGecko

**File:** `price_provider.py` — class `CoinGeckoProvider`

Kept as an alternative; not used by any script by default. `staking.py` falls back to it if
`COINGECKO_API_KEY` is set in `.env` and `CRYPTOCOMPARE_API_KEY` is not. Requires a free Demo
key from coingecko.com/en/api.
