import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from loaders import Loader
from models import Reward, Trade


class KrakenLoader(Loader):

    def load_rewards(self, path: Path) -> list[Reward]:
        rewards = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["type"] == "earn" and row["subtype"] == "reward":
                    rewards.append(Reward(
                        date=datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").date(),
                        asset=row["asset"],
                        amount=float(row["amount"]),
                        fee=float(row["fee"]),
                    ))
        return rewards

    def load_trades(self, path: Path) -> list[Trade]:
        by_refid: dict[str, list[dict]] = defaultdict(list)
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["type"] == "trade" and row["subtype"] == "tradespot":
                    by_refid[row["refid"]].append(row)

        trades = []
        for refid, legs in by_refid.items():
            eur_leg   = next((r for r in legs if r["asset"] == "EUR"), None)
            asset_leg = next((r for r in legs if r["asset"] != "EUR"), None)

            if not eur_leg or not asset_leg:
                # crypto-to-crypto: emit unresolved sell + buy pair
                if len(legs) == 2 and not eur_leg:
                    sold_leg = next((r for r in legs if float(r["amount"]) < 0), None)
                    recv_leg = next((r for r in legs if float(r["amount"]) > 0), None)
                    if sold_leg and recv_leg:
                        trade_date = datetime.strptime(sold_leg["time"], "%Y-%m-%d %H:%M:%S").date()
                        trades.append(Trade(
                            date=trade_date, refid=refid, type="sell",
                            asset=sold_leg["asset"],
                            amount=abs(float(sold_leg["amount"])),
                            eur_amount=0.0, fee_eur=0.0,
                            fee_asset=abs(float(sold_leg["fee"])),
                            cost_eur=0.0, unit_price=0.0,
                        ))
                        trades.append(Trade(
                            date=trade_date, refid=refid, type="buy",
                            asset=recv_leg["asset"],
                            amount=float(recv_leg["amount"]),
                            eur_amount=0.0, fee_eur=0.0, fee_asset=0.0,
                            cost_eur=0.0, unit_price=0.0,
                        ))
                continue

            eur_amount  = float(eur_leg["amount"])
            eur_fee     = float(eur_leg["fee"])
            asset_gross = float(asset_leg["amount"])
            asset_fee   = float(asset_leg["fee"])

            # Buy:  EUR leaves (negative), crypto arrives (positive)
            # Sell: EUR arrives (positive), crypto leaves (negative)
            is_buy = eur_amount < 0

            if is_buy:
                amount   = abs(asset_gross) - abs(asset_fee)
                cost_eur = abs(eur_amount) + abs(eur_fee)
            else:
                amount   = abs(asset_gross) + abs(asset_fee)
                cost_eur = 0.0

            unit_price = (abs(eur_amount) / abs(asset_gross)) if asset_gross else 0.0

            trades.append(Trade(
                date=datetime.strptime(eur_leg["time"], "%Y-%m-%d %H:%M:%S").date(),
                refid=refid,
                type="buy" if is_buy else "sell",
                asset=asset_leg["asset"],
                amount=amount,
                eur_amount=abs(eur_amount),
                fee_eur=abs(eur_fee),
                fee_asset=abs(asset_fee),
                cost_eur=cost_eur,
                unit_price=unit_price,
            ))

        return sorted(trades, key=lambda t: t.date)
