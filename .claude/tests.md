---
paths:
  - "tests/**/*"
---

# Tests

## Framework
Use `unittest` from the standard library. Do not add pytest — it would violate the no-unnecessary-dependencies rule.

## Where tests live
`tests/test_staking.py` and `tests/test_trades.py`. Fixture CSVs in `tests/fixtures/`.

## How to test each layer
- Pure functions (`nearest_price`, `build_summary`, `apply_fifo`): construct input data inline in the test file, no file I/O needed.
- I/O functions (`load_rewards`, `load_trades`): use the small crafted fixture CSVs in `tests/fixtures/` — do not use the real Kraken CSV.
- Do not mock the price provider; the business logic under test does not call it.

## Fixture CSV design
Fixtures must be small and hand-verifiable. Include both rows that must be included and rows that must be excluded (allocations, deposits, non-matching subtypes) so the filter logic is always exercised.

## When to run
Run `python -m unittest discover -s tests -p "test_*.py" -v` after any change to business logic in `staking.py` or `trades.py`.
