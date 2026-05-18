import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import staking
from binance_loader import BinanceLoader
from kraken_loader import KrakenLoader
from models import Reward

FIXTURES = Path(__file__).parent / "fixtures"


class TestNearestPrice(unittest.TestCase):

    def test_exact_match(self):
        prices = {date(2025, 1, 10): 5.0}
        self.assertEqual(staking.nearest_price(prices, date(2025, 1, 10)), 5.0)

    def test_nearest_fallback_prefers_closer(self):
        # Jan 9 is 1 day away, Jan 12 is 2 days away from target Jan 10
        prices = {date(2025, 1, 9): 4.0, date(2025, 1, 12): 6.0}
        self.assertEqual(staking.nearest_price(prices, date(2025, 1, 10)), 4.0)

    def test_single_entry_fallback(self):
        prices = {date(2025, 1, 5): 3.0}
        self.assertEqual(staking.nearest_price(prices, date(2025, 1, 10)), 3.0)

    def test_empty_dict_returns_none(self):
        self.assertIsNone(staking.nearest_price({}, date(2025, 1, 10)))


class TestBuildSummary(unittest.TestCase):

    def _rewards(self):
        return [
            Reward(date=date(2025, 1, 10), asset="DOT", amount=10.0, fee=2.0),
            Reward(date=date(2025, 1, 20), asset="DOT", amount=8.0,  fee=2.0),
            Reward(date=date(2025, 1, 15), asset="EUR", amount=5.0,  fee=0.0),
        ]

    def _prices(self):
        return {
            "DOT": {date(2025, 1, 10): 5.0, date(2025, 1, 20): 6.0},
        }

    def test_eur_asset_uses_fixed_price_one(self):
        rewards = [Reward(date=date(2025, 1, 15), asset="EUR", amount=5.0, fee=0.0)]
        rows = staking.build_summary(rewards, {})
        eur_row = rows[0]
        self.assertEqual(eur_row.asset, "EUR")
        self.assertAlmostEqual(eur_row.total_net_value_eur, 5.0)
        self.assertAlmostEqual(eur_row.total_gross_value_eur, 5.0)
        self.assertAlmostEqual(eur_row.total_platform_fee_eur, 0.0)

    def test_multi_reward_aggregation(self):
        rows = staking.build_summary(self._rewards(), self._prices())
        dot_row = next(r for r in rows if r.asset == "DOT")
        self.assertEqual(dot_row.num_rewards, 2)
        self.assertAlmostEqual(dot_row.total_net_amount, 18.0)
        self.assertAlmostEqual(dot_row.total_gross_amount, 22.0)   # (10+2) + (8+2)
        self.assertAlmostEqual(dot_row.total_platform_fee, 4.0)
        self.assertAlmostEqual(dot_row.total_net_value_eur, 98.0)   # 10*5 + 8*6
        self.assertAlmostEqual(dot_row.total_gross_value_eur, 120.0) # 12*5 + 10*6
        self.assertAlmostEqual(dot_row.total_platform_fee_eur, 22.0)   # 2*5 + 2*6

    def test_total_row_is_last(self):
        rows = staking.build_summary(self._rewards(), self._prices())
        self.assertEqual(rows[-1].asset, "TOTAL")

    def test_total_row_sums_eur_values(self):
        rows = staking.build_summary(self._rewards(), self._prices())
        total = rows[-1]
        self.assertEqual(total.num_rewards, 3)
        self.assertAlmostEqual(total.total_net_value_eur, 103.0)    # 98 + 5
        self.assertAlmostEqual(total.total_gross_value_eur, 125.0)  # 120 + 5
        self.assertAlmostEqual(total.total_platform_fee_eur, 22.0)

    def test_total_row_amount_columns_are_none(self):
        rows = staking.build_summary(self._rewards(), self._prices())
        total = rows[-1]
        self.assertIsNone(total.total_net_amount)
        self.assertIsNone(total.total_gross_amount)
        self.assertIsNone(total.total_platform_fee)

    def test_asset_rows_sorted_alphabetically_before_total(self):
        rows = staking.build_summary(self._rewards(), self._prices())
        asset_names = [r.asset for r in rows[:-1]]
        self.assertEqual(asset_names, sorted(asset_names))

    def test_missing_price_leaves_eur_values_at_zero(self):
        rewards = [Reward(date=date(2025, 1, 10), asset="UNKNOWN", amount=10.0, fee=1.0)]
        rows = staking.build_summary(rewards, {})
        row = rows[0]
        self.assertAlmostEqual(row.total_net_value_eur, 0.0)
        self.assertAlmostEqual(row.total_gross_value_eur, 0.0)


class TestLoadRewards(unittest.TestCase):

    def _loaded(self):
        return KrakenLoader().load_rewards(FIXTURES / "staking_ledger.csv")

    def test_filters_only_earn_reward_rows(self):
        rewards = self._loaded()
        self.assertEqual(len(rewards), 3)

    def test_result_has_expected_fields(self):
        for r in self._loaded():
            self.assertIsInstance(r.date, date)
            self.assertIsInstance(r.asset, str)
            self.assertIsInstance(r.amount, float)
            self.assertIsInstance(r.fee, float)

    def test_assets_present(self):
        assets = {r.asset for r in self._loaded()}
        self.assertIn("DOT", assets)
        self.assertIn("EUR", assets)

    def test_dot_amounts_parsed_correctly(self):
        dot = sorted(r.amount for r in self._loaded() if r.asset == "DOT")
        self.assertEqual(len(dot), 2)
        self.assertAlmostEqual(dot[0], 8.0)
        self.assertAlmostEqual(dot[1], 10.0)

    def test_fee_stored_as_positive_float(self):
        dot = next(r for r in self._loaded() if r.asset == "DOT" and r.amount == 10.0)
        self.assertAlmostEqual(dot.fee, 2.0)

    def test_allocation_and_trade_rows_excluded(self):
        # Fixture has allocation, deallocation, and tradespot rows; none should appear
        self.assertEqual(len(self._loaded()), 3)


class TestBinanceLoadRewards(unittest.TestCase):

    def _loaded(self):
        return BinanceLoader().load_rewards(FIXTURES / "binance_rewards_ledger.csv")

    def test_earn_ops_loaded(self):
        # 2 Simple Earn Flexible Interest + 1 Pool Distribution → 3 rows
        self.assertEqual(len(self._loaded()), 3)

    def test_deposit_and_redemption_excluded(self):
        # Deposit, Simple Earn Flexible Redemption, Transfer must be filtered out
        self.assertEqual(len(self._loaded()), 3)

    def test_fee_always_zero(self):
        for r in self._loaded():
            self.assertAlmostEqual(r.fee, 0.0)

    def test_date_parsed_correctly(self):
        usdt = sorted((r for r in self._loaded() if r.asset == "USDT"), key=lambda r: r.date)
        self.assertEqual(usdt[0].date, date(2025, 1, 10))

    def test_both_usdt_and_btc_present(self):
        assets = {r.asset for r in self._loaded()}
        self.assertIn("USDT", assets)
        self.assertIn("BTC", assets)

    def test_amount_parsed_correctly(self):
        first_usdt = next(r for r in self._loaded() if r.asset == "USDT" and r.date == date(2025, 1, 10))
        self.assertAlmostEqual(first_usdt.amount, 0.00017000)

    def test_result_has_expected_fields(self):
        for r in self._loaded():
            self.assertIsInstance(r.date, date)
            self.assertIsInstance(r.asset, str)
            self.assertIsInstance(r.amount, float)
            self.assertIsInstance(r.fee, float)


if __name__ == "__main__":
    unittest.main()
