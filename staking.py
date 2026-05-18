"""
staking.py — Calculates staking reward income from a crypto exchange ledger CSV
and converts amounts to EUR using historical prices.

Usage:
    python staking.py <csv_path>

The platform (Kraken, Binance, …) is selected interactively at startup.
The API key is read from the .env file in the same directory.
See .env.example for available options.

Output:
    staking_summary.csv — one row per asset with annual totals

Tax note:
    The CSV includes both 'total_net_value_eur' (what you actually receive)
    and 'total_gross_value_eur' (before platform commission). Consult your
    tax advisor on which to use as the taxable base; net is the common practice.
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from cryptocompare_provider import CryptoCompareProvider
from loaders import Loader, select_loader
from models import Reward, StakingRow
from price_provider import CoinGeckoProvider, PriceProvider
from utils import load_env


EUR_FIXED = {"EUR"}


def nearest_price(prices: dict[date, float], target: date) -> Optional[float]:
    if target in prices:
        return prices[target]
    if not prices:
        return None
    return prices[min(prices, key=lambda d: abs((d - target).days))]


def build_summary(
    rewards: list[Reward],
    all_prices: dict[str, dict[date, float]],
) -> list[StakingRow]:
    totals: dict[str, StakingRow] = {}

    for r in rewards:
        asset = r.asset
        gross = r.amount + r.fee

        if asset in EUR_FIXED:
            price = 1.0
        else:
            price = nearest_price(all_prices.get(asset, {}), r.date)

        if asset not in totals:
            totals[asset] = StakingRow(
                asset=asset,
                num_rewards=0,
                total_net_amount=0.0,
                total_gross_amount=0.0,
                total_platform_fee=0.0,
                total_net_value_eur=0.0,
                total_gross_value_eur=0.0,
                total_platform_fee_eur=0.0,
            )

        t = totals[asset]
        t.num_rewards        += 1
        t.total_net_amount   += r.amount
        t.total_gross_amount += gross
        t.total_platform_fee += r.fee
        if price is not None:
            t.total_net_value_eur   += r.amount * price
            t.total_gross_value_eur += gross * price
            t.total_platform_fee_eur += r.fee * price

    rows: list[StakingRow] = sorted(totals.values(), key=lambda r: r.asset)

    rows.append(StakingRow(
        asset="TOTAL",
        num_rewards=sum(r.num_rewards for r in rows),
        total_net_amount=None,
        total_gross_amount=None,
        total_platform_fee=None,
        total_net_value_eur=sum(r.total_net_value_eur for r in rows),
        total_gross_value_eur=sum(r.total_gross_value_eur for r in rows),
        total_platform_fee_eur=sum(r.total_platform_fee_eur for r in rows),
    ))

    return rows


def write_summary_csv(rows: list[StakingRow], out_path: Path) -> None:
    fieldnames = [
        "asset", "num_rewards",
        "total_net_amount", "total_gross_amount", "total_platform_fee",
        "total_net_value_eur", "total_gross_value_eur", "total_platform_fee_eur",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "asset":                  row.asset,
                "num_rewards":            row.num_rewards,
                "total_net_amount":       f"{row.total_net_amount:.8f}"       if row.total_net_amount   is not None else "",
                "total_gross_amount":     f"{row.total_gross_amount:.8f}"     if row.total_gross_amount is not None else "",
                "total_platform_fee":     f"{row.total_platform_fee:.8f}"     if row.total_platform_fee is not None else "",
                "total_net_value_eur":    f"{row.total_net_value_eur:.2f}",
                "total_gross_value_eur":  f"{row.total_gross_value_eur:.2f}",
                "total_platform_fee_eur": f"{row.total_platform_fee_eur:.2f}",
            })


def print_summary(rows: list[StakingRow]) -> None:
    print(f"\n{'Asset':<8} {'Rewards':>12} {'Net value EUR':>16} {'Gross value EUR':>17} {'Fee EUR':>10}")
    print("-" * 68)
    for row in rows:
        if row.asset == "TOTAL":
            print("-" * 68)
        print(
            f"{row.asset:<8} "
            f"{row.num_rewards:>12} "
            f"{row.total_net_value_eur:>16.2f} "
            f"{row.total_gross_value_eur:>17.2f} "
            f"{row.total_platform_fee_eur:>10.2f}"
        )


def _ask_tax_year(available: set[int]) -> int:
    years_str = ", ".join(str(y) for y in sorted(available))
    while True:
        raw = input(f"Tax year to declare ({years_str}): ").strip()
        if raw.isdigit() and int(raw) in available:
            return int(raw)
        print(f"Enter one of: {years_str}")


def select_provider() -> PriceProvider:
    cc_key = os.environ.get("CRYPTOCOMPARE_API_KEY")
    cg_key = os.environ.get("COINGECKO_API_KEY")

    if cc_key:
        print("Provider: CryptoCompare")
        return CryptoCompareProvider(api_key=cc_key)
    if cg_key:
        print("Provider: CoinGecko (data limited to the last 365 days)")
        return CoinGeckoProvider(api_key=cg_key)

    print("ERROR: no API key found in .env")
    print("Set CRYPTOCOMPARE_API_KEY or COINGECKO_API_KEY in your .env file")
    print("See README for instructions on obtaining a free key.")
    sys.exit(1)


def run(csv_path: Path, loader: Optional[Loader] = None) -> None:
    load_env(Path(__file__).parent / ".env")
    if loader is None:
        loader = select_loader()
    provider: PriceProvider = select_provider()

    rewards = loader.load_rewards(csv_path)
    if not rewards:
        print("No staking rewards found in the CSV.")
        return

    all_dates = [r.date for r in rewards]
    years = {d.year for d in all_dates}
    print(f"Rewards found: {len(rewards)}")
    print(f"Date range: {min(all_dates)} → {max(all_dates)}")
    if len(years) > 1:
        print(f"Rewards span {min(years)}–{max(years)}. Filter by tax year.")
        tax_year = _ask_tax_year(years)
        rewards = [r for r in rewards if r.date.year == tax_year]
        if not rewards:
            print(f"No rewards for {tax_year}.")
            return
        all_dates = [r.date for r in rewards]
        print(f"Filtered to {tax_year}: {len(rewards)} rewards  ({min(all_dates)} → {max(all_dates)})")

    assets = sorted({r.asset for r in rewards} - EUR_FIXED)

    dates_by_asset: dict[str, set[date]] = {
        asset: {r.date for r in rewards if r.asset == asset}
        for asset in assets
    }

    print(f"\nDownloading prices for {len(assets)} assets...")

    all_prices: dict[str, dict[date, float]] = {}
    for i, asset in enumerate(assets, 1):
        print(f"  [{i}/{len(assets)}] {asset}:")
        all_prices[asset] = provider.get_daily_prices(asset, dates_by_asset[asset])

    rows = build_summary(rewards, all_prices)

    out_path = csv_path.parent / "staking_summary.csv"
    write_summary_csv(rows, out_path)
    print(f"\nSummary saved to: {out_path}")

    missing_assets = [a for a in assets if not all_prices.get(a)]
    if missing_assets:
        print(f"WARNING: no prices found for {', '.join(missing_assets)}")

    print_summary(rows)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python staking.py <csv_path>")
        sys.exit(1)
    run(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
