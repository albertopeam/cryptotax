"""
trades.py — Analyses crypto buys and sells from an exchange ledger CSV.
Calculates capital gains/losses using FIFO (Spanish tax criterion,
Art. 37.2 LIRPF: first units purchased are the first units sold).

Usage:
    python trades.py <csv_path>

The platform (Kraken, Binance, …) is selected interactively at startup.

Output:
    trades_report.csv — each trade with FIFO cost basis and gain/loss
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from cryptocompare_provider import CryptoCompareProvider
from loaders import Loader, select_loader
from models import FifoRow, Trade
from utils import load_env


def _ask_tax_year(available: set[int]) -> int:
    years_str = ", ".join(str(y) for y in sorted(available))
    while True:
        raw = input(f"Tax year to declare ({years_str}): ").strip()
        if raw.isdigit() and int(raw) in available:
            return int(raw)
        print(f"Enter one of: {years_str}")


def _nearest(prices: dict[date, float], d: date) -> Optional[float]:
    if not prices:
        return None
    return prices.get(d) or prices[min(prices, key=lambda k: abs((k - d).days))]


def _resolve_crypto_prices(
    trades: list[Trade],
    unresolved_sells: list[Trade],
    provider: CryptoCompareProvider,
) -> list[Trade]:
    dates_by_asset: dict[str, set[date]] = defaultdict(set)
    for t in unresolved_sells:
        dates_by_asset[t.asset].add(t.date)

    prices: dict[str, dict[date, float]] = {}
    for asset, dates in dates_by_asset.items():
        print(f"  {asset}:")
        prices[asset] = provider.get_daily_prices(asset, dates)

    sell_map: dict[str, Trade] = {t.refid: t for t in unresolved_sells}

    for t in unresolved_sells:
        price = _nearest(prices.get(t.asset, {}), t.date)
        if price:
            t.eur_amount = price * t.amount
            t.fee_eur    = price * t.fee_asset
            t.unit_price = price

    for t in trades:
        if t.type == "buy" and t.cost_eur == 0.0 and t.eur_amount == 0.0:
            sell = sell_map.get(t.refid)
            if sell:
                t.eur_amount = sell.eur_amount
                t.cost_eur   = sell.eur_amount
                t.unit_price = t.eur_amount / t.amount if t.amount else 0.0

    return trades


def apply_fifo(trades: list[Trade]) -> list[FifoRow]:
    """
    Applies FIFO per asset to compute the acquisition cost and
    gain/loss for each sell.

    FIFO queue per asset: [[remaining_amount, unit_cost], ...]
    """
    fifo: dict[str, list[list]] = defaultdict(list)
    result = []

    for t in trades:
        asset = t.asset
        row = FifoRow(
            date=t.date,
            refid=t.refid,
            type=t.type,
            asset=asset,
            amount=t.amount,
            eur_amount=t.eur_amount,
            fee_eur=t.fee_eur,
            fee_asset=t.fee_asset,
            unit_price=t.unit_price,
        )

        if t.type == "buy":
            unit_cost = t.cost_eur / t.amount if t.amount else 0.0
            fifo[asset].append([t.amount, unit_cost])
            row.acquisition_cost = t.cost_eur

        else:  # sell
            net_income   = t.eur_amount - t.fee_eur
            sell_amount  = t.amount
            accrued_cost = 0.0
            remaining    = sell_amount
            notes        = []

            while remaining > 1e-10 and fifo[asset]:
                lot = fifo[asset][0]
                use = min(remaining, lot[0])
                accrued_cost += use * lot[1]
                lot[0]       -= use
                remaining    -= use
                if lot[0] < 1e-10:
                    fifo[asset].pop(0)

            if remaining > 1e-10:
                notes.append(f"no cost basis for {remaining:.8f} {asset}")

            row.acquisition_cost = accrued_cost
            row.net_income_eur   = net_income
            row.gain_eur         = net_income - accrued_cost
            row.note             = "; ".join(notes)

        result.append(row)

    return result


def write_csv(rows: list[FifoRow], out_path: Path) -> None:
    fieldnames = [
        "date", "refid", "type", "asset",
        "amount", "eur_amount", "fee_eur", "fee_asset",
        "unit_price", "acquisition_cost",
        "net_income_eur", "gain_eur", "note",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "date":             str(row.date),
                "refid":            row.refid,
                "type":             row.type,
                "asset":            row.asset,
                "amount":           f"{row.amount:.8f}",
                "eur_amount":       f"{row.eur_amount:.4f}",
                "fee_eur":          f"{row.fee_eur:.4f}",
                "fee_asset":        f"{row.fee_asset:.8f}",
                "unit_price":       f"{row.unit_price:.4f}",
                "acquisition_cost": f"{row.acquisition_cost:.4f}",
                "net_income_eur":   f"{row.net_income_eur:.4f}" if row.net_income_eur is not None else "",
                "gain_eur":         f"{row.gain_eur:.4f}"       if row.gain_eur is not None else "",
                "note":             row.note,
            })


def print_summary(
    trades_raw: list[Trade],
    rows: list[FifoRow],
    tax_year: Optional[int] = None,
) -> None:
    buys  = [t for t in trades_raw if t.type == "buy"]
    sells = [t for t in trades_raw if t.type == "sell"]

    print(f"\nTotal trades: {len(trades_raw)}  ({len(buys)} buys, {len(sells)} sells)")

    inv: dict[str, float] = defaultdict(float)
    for b in buys:
        inv[b.asset] += b.cost_eur

    print(f"\n{'Asset':<8} {'Total invested (EUR)':>22}")
    print("-" * 32)
    for asset in sorted(inv):
        print(f"{asset:<8} {inv[asset]:>22.2f}")
    print("-" * 32)
    print(f"{'TOTAL':<8} {sum(inv.values()):>22.2f}")

    if sells:
        total_gain = sum(
            r.gain_eur for r in rows
            if r.type == "sell" and r.gain_eur is not None
            and (tax_year is None or r.date.year == tax_year)
        )
        year_label = f" ({tax_year})" if tax_year else ""
        print(f"\nTotal capital gain/loss from sells{year_label}: {total_gain:.2f} EUR")
    else:
        print("\nNo sells in this period — no capital gains to declare.")

    no_basis = [
        r for r in rows
        if r.type == "sell" and "no cost basis" in r.note
        and (tax_year is None or r.date.year == tax_year)
    ]
    if no_basis:
        by_asset: dict[str, tuple[int, float]] = {}
        for r in no_basis:
            count, total = by_asset.get(r.asset, (0, 0.0))
            by_asset[r.asset] = (count + 1, total + (r.net_income_eur or 0.0))
        print("\nWARNING: incomplete purchase history detected")
        for asset, (count, proceeds) in sorted(by_asset.items()):
            print(f"  {asset}  {count} sell(s) — {proceeds:.2f} EUR proceeds had no matching buy record")
            print(f"       → acquisition cost treated as 0; gains overstated by up to {proceeds:.2f} EUR")
        print("\nPossible causes:")
        print("  • purchases on other platforms or prior to this CSV's date range")
        print("  • assets received from blockchain (mining, transfers, airdrops)")
        print("Check the 'note' column in trades_report.csv for the affected rows.")


def run(csv_path: Path, loader: Optional[Loader] = None) -> None:
    load_env(Path(__file__).parent / ".env")
    if loader is None:
        loader = select_loader()
    trades = loader.load_trades(csv_path)

    unresolved = [t for t in trades if t.type == "sell" and t.eur_amount == 0.0]
    if unresolved:
        api_key = os.environ.get("CRYPTOCOMPARE_API_KEY")
        if api_key:
            print("CryptoCompare API key loaded from .env")
        else:
            print("No CRYPTOCOMPARE_API_KEY in .env — proceeding without key (lower rate limits)")
        print(f"\nResolving {len(unresolved)} crypto-to-crypto trade(s) via CryptoCompare...")
        trades = _resolve_crypto_prices(trades, unresolved, CryptoCompareProvider(api_key))

    if not trades:
        print("No trades found in the CSV.")
        return

    rows = apply_fifo(trades)

    out_path = csv_path.parent / "trades_report.csv"
    write_csv(rows, out_path)
    print(f"Report saved to: {out_path}")

    sell_years = {r.date.year for r in rows if r.type == "sell" and r.gain_eur is not None}
    tax_year: Optional[int] = None
    if len(sell_years) > 1:
        print(f"\nSells span {min(sell_years)}–{max(sell_years)}.")
        print("The full CSV is preserved for cost-basis continuity.")
        tax_year = _ask_tax_year(sell_years)
    elif sell_years:
        tax_year = next(iter(sell_years))

    print_summary(trades, rows, tax_year)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python trades.py <csv_path>")
        sys.exit(1)
    run(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
