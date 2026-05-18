# Rules

## Separate scripts
`staking.py` and `trades.py` are independent scripts. Do not merge them even though they share the same CSV input. They are launched separately and must be maintainable independently.

## Injectable price provider
All HTTP calls to price APIs go in `price_provider.py`. `staking.py` instantiates the provider in a single marked line. Do not scatter network calls across other files.

## One file per provider
Each price provider has its own file (`cryptocompare_provider.py`, …), each containing one class
implementing `get_daily_prices(asset, dates)`. `price_provider.py` holds only the abstract
`PriceProvider` base class. The ticker-to-symbol mapping lives inside each provider class.

## Output always in CSV
Output reports are `staking_summary.csv` and `trades_report.csv`, in the same directory as the input CSV. Do not change the format to Excel, JSON, or anything else without an explicit request.

## No unnecessary dependencies
The only external dependency is `requests`. Do not add pandas, numpy, or other libraries unless explicitly requested.

## Spanish tax criterion
- Staking: taxable base = `net_amount × eur_price`
- Trades: FIFO per Art. 37.2 LIRPF
- Crypto-to-crypto: always resolved automatically via CryptoCompare (every disposal is taxable under Art. 37.2 LIRPF — there is no legal "skip" option)
- Output CSV always includes both net and gross values so the tax advisor can decide

## Mandatory local cache for rate-limited API calls
Any call to an external API with usage limits (daily, monthly, or per-minute) must persist its result to a local JSON cache before making another request. The cache file (`.price_cache.json`) lives in the project directory, is excluded from the repo via `.gitignore`, and is always checked before issuing a new request. The delay between calls lives in the provider, never in the main scripts.

Cache file format — asset symbol → ISO date string → EUR closing price (float):
```json
{
  "BTC": { "2025-01-01": 95000.5, "2025-01-02": 94500.0 },
  "ETH": { "2025-01-01": 3400.0 }
}
```
The cache is shared across all providers and all scripts. A new provider must read the existing cache on init, skip already-known dates, and write back only after a successful fetch.

## Price API
See `.claude/apis.md` for the active price provider, its capabilities, and how to add new asset symbols.

## Shared utilities
Utility functions used by more than one script go in `utils.py`, not duplicated per script.
`utils.py` contains only general-purpose helpers with no business logic (e.g. `load_env`).
Business logic stays in the script that owns it.

## API key convention
API keys are always read from `.env` via `load_env()` + `os.environ.get(...)`.
Never prompt the user interactively for a key.
Every script that needs prices must call `load_env(Path(__file__).parent / ".env")` near the
top of its `main()`. See `.claude/apis.md` for the full provider and key details.

## One loader file per platform
Each platform has its own loader file (`kraken_loader.py`, `binance_loader.py`, …), each containing one class implementing `load_rewards(path)` and `load_trades(path)` and returning the canonical dict structures consumed by the business logic. `loaders.py` holds only the `Loader` base class and the `select_loader()` registry — it never contains platform logic. Platform is selected at runtime via an interactive terminal menu — never via CLI flags or hard-coded branching. To add a new platform: create `<platform>_loader.py`, import it in `loaders.py`, and add it to `_PLATFORMS`.

Canonical structures (defined as `@dataclass` in `models.py`):
- `load_rewards()` → `list[Reward]`  — fields: `date`, `asset`, `amount`, `fee`
- `load_trades()` → `list[Trade]`   — fields: `date`, `refid`, `type`, `asset`, `amount`, `eur_amount`, `fee_eur`, `fee_asset`, `cost_eur`, `unit_price`

