# CLAUDE.md — Project context

@.claude/rules.md
@.claude/language.md
@.claude/tests.md

## What this project does

Python scripts to calculate cryptocurrency tax obligations for Kraken users in Spain.
Input is always the ledger CSV exported from Kraken.

Two completely independent calculations:
- **Staking** (`staking.py`): capital income from earn/reward rewards
- **Trades** (`trades.py`): capital gains/losses from buys and sells (FIFO, Art. 37.2 LIRPF)

## Architecture

```
price_provider.py   ← single external dependency (price API)
staking.py          ← imports PriceProvider; produces staking_summary.csv
trades.py           ← no API dependency; produces trades_report.csv
```

`trades.py` does not need external prices because the Kraken CSV already contains the EUR amount for every trade.

## Kraken CSV — relevant structure

Columns: `txid, refid, time, type, subtype, aclass, subclass, asset, wallet, amount, fee, balance`

Rows that matter:
- `type=earn, subtype=reward` → staking rewards (`staking.py`)
- `type=trade, subtype=tradespot` → buys/sells (`trades.py`)

Rows that are ignored:
- `subtype=allocation/deallocation/autoallocation` → internal staking movements, no tax impact
- `type=deposit/withdrawal/transfer` → fund flows, no tax impact

## Code conventions

- Types annotated on all public functions
- `Optional` from `typing` for Python < 3.10 compatibility in public signatures
- 4–6 decimal places for EUR amounts in CSV, 8 for asset quantities
- `nearest_price()` in staking.py covers days with no available price (holidays, late listings)
