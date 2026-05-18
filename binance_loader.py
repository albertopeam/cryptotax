import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from loaders import Loader
from models import Reward, Trade

_EARN_OPS = {"Simple Earn Flexible Interest", "Pool Distribution"}
_TXN_OPS  = {"Transaction Sold", "Transaction Revenue", "Transaction Fee"}


def _parse_txn_group(tiempo: str, rows: list[dict]) -> list[Trade]:
    """
    Builds canonical Trade records from a Transaction Sold/Revenue/Fee group.
    Returns [] if malformed, [sell] or [buy] for EUR trades, [sell, buy] for
    crypto-to-crypto (both with eur_amount=0.0 — unresolved, needs price lookup).
    """
    sold_row    = next((r for r in rows if r["Operación"] == "Transaction Sold"),    None)
    revenue_row = next((r for r in rows if r["Operación"] == "Transaction Revenue"), None)
    fee_row     = next((r for r in rows if r["Operación"] == "Transaction Fee"),     None)

    if not sold_row or not revenue_row:
        return []

    sold_asset      = sold_row["Moneda"]
    sold_amount     = abs(float(sold_row["Cambio"]))
    received_asset  = revenue_row["Moneda"]
    received_amount = float(revenue_row["Cambio"])

    fee_asset_s = fee_row["Moneda"]              if fee_row else None
    fee_amount  = abs(float(fee_row["Cambio"]))  if fee_row else 0.0

    trade_date = datetime.strptime(tiempo, "%y-%m-%d %H:%M:%S").date()

    if received_asset == "EUR":
        fee_eur       = fee_amount if fee_asset_s == "EUR"      else 0.0
        fee_asset_amt = fee_amount if fee_asset_s == sold_asset else 0.0
        return [Trade(
            date=trade_date, refid=tiempo, type="sell",
            asset=sold_asset, amount=sold_amount,
            eur_amount=received_amount, fee_eur=fee_eur,
            fee_asset=fee_asset_amt, cost_eur=0.0,
            unit_price=received_amount / sold_amount if sold_amount else 0.0,
        )]

    if sold_asset == "EUR":
        fee_eur       = fee_amount if fee_asset_s == "EUR"           else 0.0
        fee_asset_amt = fee_amount if fee_asset_s == received_asset  else 0.0
        amount = received_amount - fee_asset_amt
        return [Trade(
            date=trade_date, refid=tiempo, type="buy",
            asset=received_asset, amount=amount,
            eur_amount=sold_amount, fee_eur=fee_eur,
            fee_asset=fee_asset_amt, cost_eur=sold_amount + fee_eur,
            unit_price=sold_amount / received_amount if received_amount else 0.0,
        )]

    # Crypto-to-crypto: emit unresolved sell + buy pair
    return [
        Trade(
            date=trade_date, refid=tiempo, type="sell",
            asset=sold_asset, amount=sold_amount,
            eur_amount=0.0, fee_eur=0.0,
            fee_asset=fee_amount if fee_asset_s == sold_asset else 0.0,
            cost_eur=0.0, unit_price=0.0,
        ),
        Trade(
            date=trade_date, refid=tiempo, type="buy",
            asset=received_asset, amount=received_amount,
            eur_amount=0.0, fee_eur=0.0, fee_asset=0.0,
            cost_eur=0.0, unit_price=0.0,
        ),
    ]


def _parse_convert_pair(r1: dict, r2: dict) -> list[Trade]:
    """
    Builds canonical Trade records from a consecutive Binance Convert pair.
    Returns [] if malformed. Returns [sell] or [buy] for EUR pairs, [sell, buy]
    for crypto-to-crypto (both with eur_amount=0.0 — unresolved).
    """
    c1, c2 = float(r1["Cambio"]), float(r2["Cambio"])

    if c1 < 0 and c2 > 0:
        spent_row, received_row = r1, r2
    elif c2 < 0 and c1 > 0:
        spent_row, received_row = r2, r1
    else:
        return []

    spent_asset     = spent_row["Moneda"]
    spent_amount    = abs(float(spent_row["Cambio"]))
    received_asset  = received_row["Moneda"]
    received_amount = float(received_row["Cambio"])

    trade_date = datetime.strptime(r1["Tiempo"], "%y-%m-%d %H:%M:%S").date()
    refid = r1["Tiempo"]

    if received_asset == "EUR":
        return [Trade(
            date=trade_date, refid=refid, type="sell",
            asset=spent_asset, amount=spent_amount,
            eur_amount=received_amount, fee_eur=0.0, fee_asset=0.0,
            cost_eur=0.0,
            unit_price=received_amount / spent_amount if spent_amount else 0.0,
        )]

    if spent_asset == "EUR":
        return [Trade(
            date=trade_date, refid=refid, type="buy",
            asset=received_asset, amount=received_amount,
            eur_amount=spent_amount, fee_eur=0.0, fee_asset=0.0,
            cost_eur=spent_amount,
            unit_price=spent_amount / received_amount if received_amount else 0.0,
        )]

    # Crypto-to-crypto: emit unresolved sell + buy pair
    return [
        Trade(
            date=trade_date, refid=refid, type="sell",
            asset=spent_asset, amount=spent_amount,
            eur_amount=0.0, fee_eur=0.0, fee_asset=0.0,
            cost_eur=0.0, unit_price=0.0,
        ),
        Trade(
            date=trade_date, refid=refid, type="buy",
            asset=received_asset, amount=received_amount,
            eur_amount=0.0, fee_eur=0.0, fee_asset=0.0,
            cost_eur=0.0, unit_price=0.0,
        ),
    ]


class BinanceLoader(Loader):
    """
    Loader for the Binance 'Historial de transacciones' CSV.
    Both load_rewards() and load_trades() read the same file.

    Crypto-to-crypto trades are included in the load_trades() result with
    eur_amount=0.0 (unresolved). The caller (trades.py) detects them and
    resolves EUR values via a price provider before running FIFO.
    """

    def load_rewards(self, path: Path) -> list[Reward]:
        rewards = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["Operación"] in _EARN_OPS:
                    rewards.append(Reward(
                        date=datetime.strptime(row["Tiempo"], "%y-%m-%d %H:%M:%S").date(),
                        asset=row["Moneda"],
                        amount=float(row["Cambio"]),
                        fee=0.0,
                    ))
        return rewards

    def load_trades(self, path: Path) -> list[Trade]:
        trades: list[Trade] = []
        txn_groups: dict[str, list[dict]] = defaultdict(list)
        convert_queue: list[dict] = []

        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                op = row["Operación"]
                if op in _TXN_OPS:
                    txn_groups[row["Tiempo"]].append(row)
                elif op == "Binance Convert":
                    convert_queue.append(row)

        for tiempo, group in txn_groups.items():
            trades.extend(_parse_txn_group(tiempo, group))

        i = 0
        while i < len(convert_queue) - 1:
            records = _parse_convert_pair(convert_queue[i], convert_queue[i + 1])
            if records:
                trades.extend(records)
                i += 2
            else:
                i += 1

        return sorted(trades, key=lambda t: t.date)
