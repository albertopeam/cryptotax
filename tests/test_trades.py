import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import trades
from binance_loader import BinanceLoader
from kraken_loader import KrakenLoader
from models import Trade

FIXTURES = Path(__file__).parent / "fixtures"


def _make_buy(refid, d, asset, amount, cost_eur, eur_fee=0.0):
    eur_amount = cost_eur - eur_fee
    return Trade(
        date=d, refid=refid, type="buy", asset=asset,
        amount=amount, eur_amount=eur_amount, fee_eur=eur_fee,
        fee_asset=0.0, cost_eur=cost_eur,
        unit_price=eur_amount / amount if amount else 0.0,
    )


def _make_sell(refid, d, asset, amount, eur_amount, fee_eur=0.0):
    return Trade(
        date=d, refid=refid, type="sell", asset=asset,
        amount=amount, eur_amount=eur_amount, fee_eur=fee_eur,
        fee_asset=0.0, cost_eur=0.0,
        unit_price=eur_amount / amount if amount else 0.0,
    )


class TestLoadTrades(unittest.TestCase):

    def _loaded(self):
        return KrakenLoader().load_trades(FIXTURES / "trades_ledger.csv")

    def test_count_of_trades(self):
        # 4 BTC trades + 2 ETH trades; earn and allocation rows excluded
        self.assertEqual(len(self._loaded()), 6)

    def test_all_types_are_buy_or_sell(self):
        self.assertTrue(all(t.type in ("buy", "sell") for t in self._loaded()))

    def test_sorted_by_date(self):
        result = self._loaded()
        dates = [t.date for t in result]
        self.assertEqual(dates, sorted(dates))

    def test_buy_detected_correctly(self):
        btc_buy = next(t for t in self._loaded() if t.refid == "TBTCBUY1")
        self.assertEqual(btc_buy.type, "buy")
        self.assertEqual(btc_buy.asset, "BTC")

    def test_sell_detected_correctly(self):
        btc_sell = next(t for t in self._loaded() if t.refid == "TBTCSELL1")
        self.assertEqual(btc_sell.type, "sell")
        self.assertEqual(btc_sell.asset, "BTC")

    def test_buy_amount_is_asset_gross_minus_asset_fee(self):
        # TBTCBUY1: asset_gross=1.0, asset_fee=0 → amount=1.0
        btc_buy = next(t for t in self._loaded() if t.refid == "TBTCBUY1")
        self.assertAlmostEqual(btc_buy.amount, 1.0)

    def test_buy_cost_eur_is_eur_amount_plus_eur_fee(self):
        # TBTCBUY1: eur_amount=20000, eur_fee=0 → cost_eur=20000
        btc_buy = next(t for t in self._loaded() if t.refid == "TBTCBUY1")
        self.assertAlmostEqual(btc_buy.cost_eur, 20000.0)

    def test_sell_cost_eur_is_zero(self):
        btc_sell = next(t for t in self._loaded() if t.refid == "TBTCSELL1")
        self.assertAlmostEqual(btc_sell.cost_eur, 0.0)

    def test_sell_amount_is_asset_gross_plus_asset_fee(self):
        # TBTCSELL1: asset_gross=-0.4, asset_fee=0 → amount=0.4
        btc_sell = next(t for t in self._loaded() if t.refid == "TBTCSELL1")
        self.assertAlmostEqual(btc_sell.amount, 0.4)

    def test_unit_price_computed_from_eur_gross_and_asset_gross(self):
        # TETHBUY1: eur_amount=6000, asset_gross=2.0 → unit_price=3000
        eth_buy = next(t for t in self._loaded() if t.refid == "TETHBUY1")
        self.assertAlmostEqual(eth_buy.unit_price, 3000.0)

    def test_sell_fee_eur_stored_as_positive(self):
        # TBTCSELL1: fee in CSV = -10.0 → stored as 10.0
        btc_sell = next(t for t in self._loaded() if t.refid == "TBTCSELL1")
        self.assertAlmostEqual(btc_sell.fee_eur, 10.0)


class TestApplyFifo(unittest.TestCase):

    # ── Single lot: partial sell ──────────────────────────────────────────────

    def test_buy_row_has_acquisition_cost_set(self):
        result = trades.apply_fifo([_make_buy("B1", date(2025, 1, 15), "BTC", 1.0, 20000.0)])
        buy = result[0]
        self.assertAlmostEqual(buy.acquisition_cost, 20000.0)
        self.assertIsNone(buy.net_income_eur)
        self.assertIsNone(buy.gain_eur)

    def test_single_lot_partial_sell_gain(self):
        # Buy 1 BTC @ 20000, sell 0.4 BTC (gross 10000, fee 10)
        result = trades.apply_fifo([
            _make_buy("B1",  date(2025, 1, 15), "BTC", 1.0, 20000.0),
            _make_sell("S1", date(2025, 2,  1), "BTC", 0.4, 10000.0, fee_eur=10.0),
        ])
        sell = next(r for r in result if r.type == "sell")
        self.assertAlmostEqual(sell.net_income_eur,   9990.0)   # 10000 - 10
        self.assertAlmostEqual(sell.acquisition_cost, 8000.0)   # 0.4 * 20000
        self.assertAlmostEqual(sell.gain_eur,         1990.0)   # 9990 - 8000
        self.assertEqual(sell.note, "")

    # ── Cross-lot sell (critical FIFO path) ──────────────────────────────────

    def test_first_partial_sell_uses_only_first_lot(self):
        result = trades.apply_fifo([
            _make_buy("B1",  date(2025, 1, 10), "BTC", 1.0, 20000.0),
            _make_sell("S1", date(2025, 1, 20), "BTC", 0.4, 10000.0, fee_eur=10.0),
            _make_buy("B2",  date(2025, 2,  1), "BTC", 0.5, 15000.0),
            _make_sell("S2", date(2025, 3,  1), "BTC", 0.7, 21000.0, fee_eur=21.0),
        ])
        s1 = next(r for r in result if r.refid == "S1")
        self.assertAlmostEqual(s1.acquisition_cost, 8000.0)   # 0.4 * 20000
        self.assertAlmostEqual(s1.gain_eur,         1990.0)

    def test_cross_lot_sell_consumes_residual_first_then_second_lot(self):
        # After partial sell: lot A=[0.6, 20000], lot B=[0.5, 30000]
        # Cross sell 0.7: use all 0.6 from A (12000) + 0.1 from B (3000) = 15000
        result = trades.apply_fifo([
            _make_buy("B1",  date(2025, 1, 10), "BTC", 1.0, 20000.0),
            _make_sell("S1", date(2025, 1, 20), "BTC", 0.4, 10000.0, fee_eur=10.0),
            _make_buy("B2",  date(2025, 2,  1), "BTC", 0.5, 15000.0),
            _make_sell("S2", date(2025, 3,  1), "BTC", 0.7, 21000.0, fee_eur=21.0),
        ])
        s2 = next(r for r in result if r.refid == "S2")
        self.assertAlmostEqual(s2.acquisition_cost, 15000.0)
        self.assertAlmostEqual(s2.net_income_eur,   20979.0)   # 21000 - 21
        self.assertAlmostEqual(s2.gain_eur,          5979.0)   # 20979 - 15000
        self.assertEqual(s2.note, "")

    # ── Missing cost basis ───────────────────────────────────────────────────

    def test_sell_with_no_prior_buy_adds_note(self):
        result = trades.apply_fifo([
            _make_sell("SORPHAN", date(2025, 1, 15), "ETH", 1.0, 5000.0, fee_eur=5.0),
        ])
        sell = result[0]
        self.assertAlmostEqual(sell.acquisition_cost, 0.0)
        self.assertAlmostEqual(sell.net_income_eur,   4995.0)
        self.assertAlmostEqual(sell.gain_eur,         4995.0)
        self.assertIn("no cost basis for 1.00000000 ETH", sell.note)

    def test_sell_exceeding_available_lots_adds_note_with_remaining(self):
        # Buy 0.3 BTC, sell 1.0 → basis covers 0.3, note for 0.7
        result = trades.apply_fifo([
            _make_buy("B1",  date(2025, 1, 10), "BTC", 0.3, 6000.0),
            _make_sell("S1", date(2025, 2,  1), "BTC", 1.0, 25000.0, fee_eur=25.0),
        ])
        sell = next(r for r in result if r.type == "sell")
        self.assertAlmostEqual(sell.acquisition_cost, 6000.0)
        self.assertIn("no cost basis for 0.70000000 BTC", sell.note)

    # ── Multiple assets are independent ──────────────────────────────────────

    def test_btc_and_eth_fifo_queues_are_independent(self):
        result = trades.apply_fifo([
            _make_buy("BBTC",  date(2025, 1, 10), "BTC", 1.0, 20000.0),
            _make_buy("BETH",  date(2025, 1, 11), "ETH", 2.0, 6000.0),
            _make_sell("SBTC", date(2025, 2,  1), "BTC", 1.0, 25000.0, fee_eur=25.0),
            _make_sell("SETH", date(2025, 2,  2), "ETH", 1.0, 3500.0,  fee_eur=3.5),
        ])
        btc = next(r for r in result if r.refid == "SBTC")
        eth = next(r for r in result if r.refid == "SETH")

        self.assertAlmostEqual(btc.acquisition_cost, 20000.0)
        self.assertAlmostEqual(btc.net_income_eur,   24975.0)  # 25000 - 25
        self.assertAlmostEqual(btc.gain_eur,          4975.0)

        # ETH unit_cost = 6000 / 2 = 3000 per ETH
        self.assertAlmostEqual(eth.acquisition_cost, 3000.0)
        self.assertAlmostEqual(eth.net_income_eur,   3496.5)   # 3500 - 3.5
        self.assertAlmostEqual(eth.gain_eur,          496.5)

    # ── Output fields ────────────────────────────────────────────────────────

    def test_amount_is_float(self):
        result = trades.apply_fifo([_make_buy("B1", date(2025, 1, 15), "BTC", 1.0, 20000.0)])
        self.assertAlmostEqual(result[0].amount, 1.0)

    def test_eur_fields_are_float(self):
        result = trades.apply_fifo([_make_buy("B1", date(2025, 1, 15), "BTC", 1.0, 20000.0)])
        self.assertAlmostEqual(result[0].eur_amount, 20000.0)
        self.assertAlmostEqual(result[0].acquisition_cost, 20000.0)

    def test_date_is_date_object(self):
        result = trades.apply_fifo([_make_buy("B1", date(2025, 1, 15), "BTC", 1.0, 20000.0)])
        self.assertEqual(result[0].date, date(2025, 1, 15))

    # ── Integration smoke test ───────────────────────────────────────────────

    def test_full_pipeline_on_fixture(self):
        loaded = KrakenLoader().load_trades(FIXTURES / "trades_ledger.csv")
        result = trades.apply_fifo(loaded)
        sells = [r for r in result if r.type == "sell" and r.gain_eur is not None]
        self.assertTrue(len(sells) > 0)
        for r in sells:
            self.assertIsNotNone(r.gain_eur)


class TestBinanceLoadTrades(unittest.TestCase):
    """
    Fixture (transactions CSV format):
      - BNB→BTC via Transaction Sold/Fee/Revenue (crypto-to-crypto, unresolved)
        → type=sell, asset=BNB, amount=0.019, eur_amount=0.0
        → type=buy,  asset=BTC, amount=0.00018135, cost_eur=0.0
      - USDT→BTC via Binance Convert (crypto-to-crypto, unresolved)
        → type=sell, asset=USDT, amount=10.6118213, eur_amount=0.0
        → type=buy,  asset=BTC,  amount=0.00011669, cost_eur=0.0
      - BTC→EUR via Transaction Sold/Fee/Revenue (EUR SELL, resolved)
        sold=0.01 BTC, revenue=550 EUR, fee=2.75 EUR
        → type=sell, asset=BTC, amount=0.01, eur_amount=550, fee_eur=2.75
      - Simple Earn row (excluded)
    Total: 5 trades
    """

    def _loader_and_trades(self):
        loader = BinanceLoader()
        result = loader.load_trades(FIXTURES / "binance_trades_ledger.csv")
        return loader, result

    def _eur_sell(self, result):
        return next(t for t in result if t.type == "sell" and t.eur_amount > 0)

    def test_total_trades_count(self):
        # 1 EUR sell + 2 unresolved crypto sells + 2 unresolved crypto buys
        _, result = self._loader_and_trades()
        self.assertEqual(len(result), 5)

    def test_unresolved_sells_present(self):
        _, result = self._loader_and_trades()
        unresolved = [t for t in result if t.type == "sell" and t.eur_amount == 0.0]
        self.assertEqual(len(unresolved), 2)
        assets = {t.asset for t in unresolved}
        self.assertIn("BNB", assets)
        self.assertIn("USDT", assets)

    def test_crypto_to_crypto_buys_emitted(self):
        _, result = self._loader_and_trades()
        unresolved_buys = [t for t in result if t.type == "buy" and t.cost_eur == 0.0]
        self.assertEqual(len(unresolved_buys), 2)
        assets = {t.asset for t in unresolved_buys}
        self.assertIn("BTC", assets)

    def test_sell_type_and_asset(self):
        _, result = self._loader_and_trades()
        sell = self._eur_sell(result)
        self.assertEqual(sell.type, "sell")
        self.assertEqual(sell.asset, "BTC")

    def test_sell_amount(self):
        _, result = self._loader_and_trades()
        self.assertAlmostEqual(self._eur_sell(result).amount, 0.01)

    def test_sell_eur_amount(self):
        _, result = self._loader_and_trades()
        self.assertAlmostEqual(self._eur_sell(result).eur_amount, 550.0)

    def test_sell_fee_eur(self):
        _, result = self._loader_and_trades()
        self.assertAlmostEqual(self._eur_sell(result).fee_eur, 2.75)

    def test_sell_fee_asset_is_zero(self):
        _, result = self._loader_and_trades()
        self.assertAlmostEqual(self._eur_sell(result).fee_asset, 0.0)

    def test_sell_cost_eur_is_zero(self):
        _, result = self._loader_and_trades()
        self.assertAlmostEqual(self._eur_sell(result).cost_eur, 0.0)

    def test_unit_price_sell(self):
        # 550 EUR / 0.01 BTC = 55000
        _, result = self._loader_and_trades()
        self.assertAlmostEqual(self._eur_sell(result).unit_price, 55000.0)

    def test_date_parsed_correctly(self):
        _, result = self._loader_and_trades()
        self.assertEqual(self._eur_sell(result).date, date(2025, 1, 20))

    def test_sorted_by_date(self):
        _, result = self._loader_and_trades()
        dates = [t.date for t in result]
        self.assertEqual(dates, sorted(dates))

    def test_result_has_expected_fields(self):
        _, result = self._loader_and_trades()
        for t in result:
            self.assertIsInstance(t.date, date)
            self.assertIsInstance(t.refid, str)
            self.assertIsInstance(t.type, str)
            self.assertIsInstance(t.asset, str)
            self.assertIsInstance(t.amount, float)
            self.assertIsInstance(t.eur_amount, float)
            self.assertIsInstance(t.fee_eur, float)
            self.assertIsInstance(t.fee_asset, float)
            self.assertIsInstance(t.cost_eur, float)
            self.assertIsInstance(t.unit_price, float)


if __name__ == "__main__":
    unittest.main()
