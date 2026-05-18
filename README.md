# crypto-renta

Scripts to calculate tax obligations from cryptocurrency operations on supported exchanges (Kraken, Binance) in Spain.

Generates two independent reports from your exchange's ledger CSV export:

- **Staking** → capital income (earn/reward rewards)
- **Trades** → capital gains/losses (buys and sells)

---

## Requirements

```bash
pip install requests
```

Python 3.10 or higher.

---

## Exporting your ledger CSV

### Kraken

1. Log in to Kraken → History → Export
2. Select **Ledgers**, full annual range (e.g. 2025-01-01 to 2025-12-31)
3. Download the CSV and place it in this directory

### Binance

1. Log in to Binance → Wallet → Transaction History
2. Click **Export** → select the full annual range (e.g. 2025-01-01 to 2025-12-31)
3. Download the CSV ("Historial de transacciones") and place it in this directory

---

## Price provider configuration

The staking script needs to look up historical prices in EUR. Copy `.env.example` to `.env` and fill in the key for the provider you have. The script automatically detects which one to use:

| Provider | When used | How to get the key |
|----------|-----------|-------------------|
| **CryptoCompare** | If `CRYPTOCOMPARE_API_KEY` is set (preferred) | Free at [cryptocompare.com/cryptopian/api-keys](https://www.cryptocompare.com/cryptopian/api-keys) |
| **CoinGecko** | If only `COINGECKO_API_KEY` is set | Requires a paid plan for data older than 365 days |

> **CoinGecko note:** the free Demo plan does not allow querying data older than 365 days. If your CSV covers a tax year earlier than the last 12 months the script will fail. You need the **Analyst** plan (~€129/month) or higher.

---

## Usage

### Recommended: interactive launcher

```bash
python main.py
```

Presents a menu to choose staking, trades, or both, then asks for the CSV path:

```
crypto-renta — Spanish crypto tax calculator

What do you want to calculate?
  1) Staking rewards (capital income)
  2) Trades (capital gains / losses)
  3) Both
  q) Quit
Choice:

CSV path: /path/to/ledger.csv

Select platform:
  1) Kraken
  2) Binance
Choice:
```

Choosing **3) Both** runs staking rewards and trades in sequence — you select the CSV path and platform once, and both `staking_summary.csv` and `trades_report.csv` are generated.

### Direct script invocation

You can also run each calculation directly if you prefer:

```bash
python staking.py <ledger_file.csv>
python trades.py <ledger_file.csv>
```

Both scripts show the same interactive platform selector at startup.

#### Staking rewards

Generates `staking_summary.csv` with one row per asset and annual totals. Prices are stored in a local cache (`.price_cache.json`) — the second run is instant.

#### Buys and sells

Generates `trades_report.csv` with the detail of each trade and the FIFO gain calculation for sells.

---

## Output files

### `staking_summary.csv`

One row per asset with annual totals, plus a `TOTAL` row at the end.

| Column | Description |
|--------|-------------|
| `asset` | Asset ticker (ETH, DOT, SOL…) |
| `num_rewards` | Number of staking payments received during the year |
| `total_net_amount` | Total amount received in wallet (after platform fee, if any) |
| `total_gross_amount` | Total amount before platform fee |
| `total_platform_fee` | Total fees withheld by the platform (0 for Binance, non-zero for Kraken) |
| `total_net_value_eur` | Total taxable value of net rewards in EUR |
| `total_gross_value_eur` | Total taxable value of gross rewards in EUR |
| `total_platform_fee_eur` | EUR value of platform fees (`total_gross_value_eur − total_net_value_eur`) |

> **Tax note:** the common taxable base is `total_net_value_eur` (what actually arrives in your wallet). Consult your tax advisor.
>
> **Note on amount columns:** `total_net_amount`, `total_gross_amount`, and `total_platform_fee` track quantities in native crypto units and are left blank in the TOTAL row — summing different crypto units (ADA + ETH + SOL…) is meaningless. Only EUR columns have a TOTAL.
>
> **Tax year filtering:** if your CSV export spans multiple calendar years, the script will detect this and ask you which year to declare. For staking, only rewards from the selected year are included. For trades, all rows are written to the CSV (FIFO cost basis requires the full buy history), but the on-screen gain total is filtered to the selected year.

### `trades_report.csv`

| Column | Description |
|--------|-------------|
| `date` | Trade date |
| `refid` | Kraken trade reference ID |
| `type` | `buy` or `sell` |
| `asset` | Asset ticker |
| `amount` | Units bought/sold (net of asset fees) |
| `eur_amount` | Gross EUR paid or received |
| `fee_eur` | Commission in EUR (if any) |
| `fee_asset` | Commission in the asset (if any) |
| `unit_price` | EUR per unit at the time of the trade |
| `acquisition_cost` | FIFO cost of the units sold (sells only) |
| `net_income_eur` | EUR received net of fee (sells only) |
| `gain_eur` | Capital gain or loss (sells only) |
| `note` | Warnings (e.g. insufficient cost basis) |

The FIFO criterion is regulated by Art. 37.2 LIRPF for homogeneous assets.

---

## Switching the price provider

Providers are decoupled into separate files. To use another API:

1. Create a new file (e.g. `my_provider.py`) with a class that inherits from `PriceProvider`:

```python
# my_provider.py
from price_provider import PriceProvider

class MyProvider(PriceProvider):
    def get_daily_prices(self, asset: str, dates: set[date]) -> dict[date, float]:
        ...
```

2. Import it and change **one line** in `staking.py`:

```python
from my_provider import MyProvider
provider: PriceProvider = MyProvider(api_key="...")
```

`trades.py` does not use a price provider (prices come from the Kraken CSV).

---

## API limits

| Provider | Plan | Req/month | History | Key |
|----------|------|-----------|---------|-----|
| CryptoCompare | Free | 100,000 | No limit | Yes (free) |
| CoinGecko | Demo (free) | 10,000 | Last 365 days | Yes (free) |
| CoinGecko | Analyst (paid) | No limit | Full | Yes (paid) |

This project makes **~12 calls** per run (one per asset). The cache avoids repeating them on subsequent runs.

---

## Price cache

Historical prices are stored in `.price_cache.json` in the project directory. The cache is shared between staking and trades runs — if you run staking first, trades will reuse the prices already downloaded.

The file uses this structure:

```json
{
  "BTC": { "2025-01-01": 95000.5, "2025-01-02": 94500.0 },
  "ETH": { "2025-01-01": 3400.0 }
}
```

Asset symbol → ISO date → EUR closing price. Dates already in the cache are never re-fetched.

To force a fresh download (e.g. after adding a new asset or suspecting stale data) simply delete the file:

```bash
rm .price_cache.json
```

The file is excluded from the repository via `.gitignore`.

---

## Testing

The test suite uses only the standard library (`unittest`). No extra dependencies needed.

```bash
# Run all tests
python -m unittest discover -s tests -p "test_*.py" -v

# Run one module
python -m unittest tests.test_trades
python -m unittest tests.test_staking
```

Tests cover the pure business logic — filtering, aggregation, FIFO cost basis — using small crafted CSV fixtures in `tests/fixtures/` for both Kraken and Binance formats. No API calls are made.

---

## Project structure

```
renta/
├── main.py                     # interactive entry point (recommended)
├── staking.py                  # earn/reward rewards → staking_summary.csv
├── trades.py                   # tradespot buys/sells → trades_report.csv
├── loaders.py                  # Loader base class + select_loader() registry
├── kraken_loader.py            # Kraken CSV → canonical Reward/Trade list
├── binance_loader.py           # Binance CSV → canonical Reward/Trade list
├── models.py                   # Reward, Trade, FifoRow, StakingRow dataclasses
├── price_provider.py           # PriceProvider base class + CoinGecko implementation
├── cryptocompare_provider.py   # CryptoCompare implementation (default provider)
├── utils.py                    # load_env() helper
├── tests/
│   ├── fixtures/               # minimal CSV files for tests (Kraken and Binance)
│   ├── test_staking.py
│   └── test_trades.py
├── .env.example                # environment variable template
├── README.md
└── CLAUDE.md
```
