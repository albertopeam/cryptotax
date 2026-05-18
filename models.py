from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Trade:
    """Canonical trade record returned by any loader's load_trades()."""
    date: date
    refid: str
    type: str           # "buy" | "sell"
    asset: str
    amount: float
    eur_amount: float   # 0.0 = unresolved (crypto-to-crypto, needs price lookup)
    fee_eur: float
    fee_asset: float
    cost_eur: float     # 0.0 = unresolved for crypto-to-crypto buys
    unit_price: float


@dataclass
class Reward:
    """Canonical staking reward returned by any loader's load_rewards()."""
    date: date
    asset: str
    amount: float
    fee: float


@dataclass
class FifoRow:
    """FIFO-processed trade row — one per trade in trades_report.csv."""
    date: date
    refid: str
    type: str
    asset: str
    amount: float
    eur_amount: float
    fee_eur: float
    fee_asset: float
    unit_price: float
    acquisition_cost: float = 0.0
    net_income_eur: Optional[float] = None  # None for buys
    gain_eur: Optional[float] = None        # None for buys
    note: str = ""


@dataclass
class StakingRow:
    """One row in staking_summary.csv. TOTAL row uses None for per-asset amount fields."""
    asset: str
    num_rewards: int
    total_net_amount: Optional[float]
    total_gross_amount: Optional[float]
    total_platform_fee: Optional[float]
    total_net_value_eur: float
    total_gross_value_eur: float
    total_platform_fee_eur: float
