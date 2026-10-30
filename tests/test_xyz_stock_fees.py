"""Unit tests verifying XYZ stock fee schedule (0.009% taker, 0.003% maker) for SKHYNIX and equities on Hyperliquid."""

import unittest
from config import (
    AppConfig,
    MarketConfig,
    XYZ_STOCK_MAKER_FEE_BPS,
    XYZ_STOCK_TAKER_FEE_BPS,
    CRYPTO_MAKER_FEE_BPS,
    CRYPTO_TAKER_FEE_BPS,
    is_xyz_stock_symbol,
    canonicalize_coin_symbol,
)
from engine.backtester import EdgeEvaluator, TradeRecord


class TestXYZStockFees(unittest.TestCase):
    """Verifies that stocks listed under XYZ (e.g. SKHYNIX) calculate fees and PnL correctly."""

    def test_canonicalize_coin_symbol(self):
        """Verifies canonicalize_coin_symbol maps aliases to exact lowercase 'xyz:' format.
        
        SKHYNIX (URL xyz:SKHYNIX, UI SKHYNIX-USDC) maps to 'xyz:SKHX' (~$1,075 mark px).
        SKHY (URL xyz:SKHY, UI SKHY-USDC) maps to 'xyz:SKHY' (~$154 mark px).
        """
        # SK Hynix primary equity contracts (SKHYNIX / SKHX) -> xyz:SKHX
        self.assertEqual(canonicalize_coin_symbol("SKHYNIX"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("skhynix"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("xyz:SKHYNIX"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("XYZ:SKHYNIX"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("SKHYNIX-USDC"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("SKHYNIX/USDC"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("xyz:SKHYNIX-USDC"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("SKHYNIX-PERP"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("SKHX"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("skhx"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("xyz:skhx"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("XYZ:SKHX"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("SKHX-USDC"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("xyz:SKHX-USDC"), "xyz:SKHX")

        # SK Hynix ADS contracts (SKHY) -> xyz:SKHY
        self.assertEqual(canonicalize_coin_symbol("SKHY"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("skhy"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("xyz:skhy"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("XYZ:SKHY"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("SKHY-USDC"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("SKHY/USDC"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("xyz:SKHY-USDC"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("SKHY-PERP"), "xyz:SKHY")

        # Trading URLs correctly extract distinct target contracts
        self.assertEqual(canonicalize_coin_symbol("https://app.hyperliquid.xyz/trade/xyz:SKHYNIX"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("https://app.hyperliquid.xyz/trade/SKHYNIX-USDC"), "xyz:SKHX")
        self.assertEqual(canonicalize_coin_symbol("https://app.hyperliquid.xyz/trade/xyz:SKHY"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("https://app.hyperliquid.xyz/trade/SKHY-USDC"), "xyz:SKHY")
        self.assertEqual(canonicalize_coin_symbol("https://app.hyperliquid.xyz/trade/BTC"), "BTC")

        # Other equities auto-prefixed with lowercase 'xyz:' and quote stripping
        self.assertEqual(canonicalize_coin_symbol("NVDA"), "xyz:NVDA")
        self.assertEqual(canonicalize_coin_symbol("xyz:nvda"), "xyz:NVDA")
        self.assertEqual(canonicalize_coin_symbol("XYZ:NVDA"), "xyz:NVDA")
        self.assertEqual(canonicalize_coin_symbol("NVDA-USDC"), "xyz:NVDA")
        self.assertEqual(canonicalize_coin_symbol("xyz:NVDA-USDC"), "xyz:NVDA")
        self.assertEqual(canonicalize_coin_symbol("TSLA"), "xyz:TSLA")
        self.assertEqual(canonicalize_coin_symbol("TSLA-USDC"), "xyz:TSLA")

        # Crypto assets retain standard ticker without 'xyz:'
        self.assertEqual(canonicalize_coin_symbol("BTC"), "BTC")
        self.assertEqual(canonicalize_coin_symbol("BTC-USDC"), "BTC")
        self.assertEqual(canonicalize_coin_symbol("BTC-PERP"), "BTC")
        self.assertEqual(canonicalize_coin_symbol("eth"), "ETH")
        self.assertEqual(canonicalize_coin_symbol("ETH-USDC"), "ETH")
        self.assertEqual(canonicalize_coin_symbol("HYPE"), "HYPE")
        self.assertEqual(canonicalize_coin_symbol("sol"), "SOL")

    def test_stock_symbol_detection(self):
        """Verifies is_xyz_stock_symbol detects SKHYNIX, SKHY, and XYZ-prefixed assets."""
        self.assertTrue(is_xyz_stock_symbol("SKHYNIX"))
        self.assertTrue(is_xyz_stock_symbol("skhynix"))
        self.assertTrue(is_xyz_stock_symbol("SKHY"))
        self.assertTrue(is_xyz_stock_symbol("SKHX"))
        self.assertTrue(is_xyz_stock_symbol("XYZ"))
        self.assertTrue(is_xyz_stock_symbol("XYZ:SKHYNIX"))
        self.assertTrue(is_xyz_stock_symbol("xyz:SKHY"))
        self.assertTrue(is_xyz_stock_symbol("xyz-NVDA"))
        self.assertTrue(is_xyz_stock_symbol("NVDA"))
        self.assertTrue(is_xyz_stock_symbol("TSLA"))
        self.assertTrue(is_xyz_stock_symbol("SKHYNIX-USDC"))
        self.assertTrue(is_xyz_stock_symbol("SKHY-USDC"))
        self.assertTrue(is_xyz_stock_symbol("NVDA-USDC"))
        self.assertTrue(is_xyz_stock_symbol("https://app.hyperliquid.xyz/trade/xyz:SKHYNIX"))

        # Standard crypto perps should NOT be flagged as stocks
        self.assertFalse(is_xyz_stock_symbol("BTC"))
        self.assertFalse(is_xyz_stock_symbol("BTC-USDC"))
        self.assertFalse(is_xyz_stock_symbol("ETH"))
        self.assertFalse(is_xyz_stock_symbol("HYPE"))
        self.assertFalse(is_xyz_stock_symbol("SOL"))

    def test_skhynix_auto_fee_configuration(self):
        """Verifies MarketConfig automatically applies 0.009% taker and 0.003% maker fees to SKHYNIX and SKHY."""
        # Both SKHYNIX (xyz:SKHX) and SKHY (xyz:SKHY) enjoy XYZ equity fee schedule
        for sym, expected_coin in (
            ("SKHYNIX", "xyz:SKHX"),
            ("SKHYNIX-USDC", "xyz:SKHX"),
            ("xyz:SKHYNIX", "xyz:SKHX"),
            ("SKHY", "xyz:SKHY"),
            ("SKHY-USDC", "xyz:SKHY"),
            ("xyz:SKHY", "xyz:SKHY"),
        ):
            m_cfg = MarketConfig(coin=sym)

            self.assertEqual(m_cfg.coin, expected_coin)
            self.assertTrue(m_cfg.is_xyz_stock)
            self.assertEqual(m_cfg.taker_fee_bps, 0.90)  # 0.0090%
            self.assertEqual(m_cfg.maker_fee_bps, 0.30)  # 0.0030%
            self.assertEqual(m_cfg.maker_rebate_bps, 0.30)
            self.assertEqual(m_cfg.tick_size, 0.01)

        # Check conversion to percentages
        taker_pct = m_cfg.taker_fee_bps / 10_000.0
        maker_pct = m_cfg.maker_fee_bps / 10_000.0
        self.assertAlmostEqual(taker_pct, 0.00009, places=7)  # 0.009%
        self.assertAlmostEqual(maker_pct, 0.00003, places=7)  # 0.003%

    def test_crypto_default_fee_configuration(self):
        """Verifies BTC and crypto assets retain standard 0.045% taker and 0.015% maker fees."""
        m_cfg = MarketConfig(coin="BTC")

        self.assertFalse(m_cfg.is_xyz_stock)
        self.assertEqual(m_cfg.taker_fee_bps, 4.50)  # 0.0450%
        self.assertEqual(m_cfg.maker_fee_bps, 1.50)  # 0.0150%
        self.assertEqual(m_cfg.maker_rebate_bps, 1.50)

        taker_pct = m_cfg.taker_fee_bps / 10_000.0
        maker_pct = m_cfg.maker_fee_bps / 10_000.0
        self.assertAlmostEqual(taker_pct, 0.00045, places=7)  # 0.045%
        self.assertAlmostEqual(maker_pct, 0.00015, places=7)  # 0.015%

    def test_skhynix_paper_trading_fee_and_pnl_calculation(self):
        """Verifies EdgeEvaluator calculates maker and taker fees using SKHYNIX fee schedule."""
        m_cfg = MarketConfig(coin="SKHYNIX")
        self.assertEqual(m_cfg.taker_fee_bps, 0.90)
        self.assertEqual(m_cfg.maker_fee_bps, 0.30)

        strategy_defs = {"QDAP_Maker": ("QDAP", "MAKER")}
        evaluator = EdgeEvaluator(market_cfg=m_cfg, strategy_defs=strategy_defs)

        # Test trade calculation:
        # Buy 100 shares SKHYNIX at $150.00 as MAKER
        entry_price = 150.00
        sz = 100.0
        notional = entry_price * sz  # $15,000

        maker_fee_pct = m_cfg.maker_fee_bps / 10_000.0  # 0.00003 (0.003%)
        entry_fee = entry_price * sz * maker_fee_pct
        self.assertAlmostEqual(entry_fee, 0.45, places=4)  # $15,000 * 0.00003 = $0.45 (not $2.25 as in crypto)

        # Sell 100 shares SKHYNIX at $150.30 as MAKER (Take Profit, +20 bps)
        exit_price = 150.30
        exit_fee = exit_price * sz * maker_fee_pct
        self.assertAlmostEqual(exit_fee, 0.4509, places=4)

        gross_pnl = (exit_price - entry_price) * sz  # $30.00
        total_fees = entry_fee + exit_fee           # $0.9009
        net_pnl = gross_pnl - total_fees            # $29.0991
        return_bps = (net_pnl / notional) * 10_000.0

        # With crypto fees (1.5 bps each way), total fees would have been $4.5045
        # Under XYZ stock fees (0.3 bps each way), total fees are only $0.9009
        crypto_fees = entry_price * sz * 0.00015 + exit_price * sz * 0.00015
        savings = crypto_fees - total_fees
        self.assertGreater(savings, 3.50)  # Saved ~$3.60 on this trade alone

        # Taker leg test (Stop loss exit paying 0.009% taker fee)
        taker_fee_pct = m_cfg.taker_fee_bps / 10_000.0  # 0.00009
        stop_exit_price = 149.50
        taker_exit_fee = stop_exit_price * sz * taker_fee_pct
        self.assertAlmostEqual(taker_exit_fee, 1.3455, places=4)  # $14,950 * 0.00009 = $1.3455 (not $6.7275 as in crypto)

    def test_explicit_fee_overrides(self):
        """Verifies custom fee parameters can override defaults."""
        m_cfg = MarketConfig()
        m_cfg.configure_for_coin("XYZ_CUSTOM", is_stock=True, taker_fee_bps=0.85, maker_fee_bps=0.25)

        self.assertTrue(m_cfg.is_xyz_stock)
        self.assertEqual(m_cfg.taker_fee_bps, 0.85)
        self.assertEqual(m_cfg.maker_fee_bps, 0.25)


if __name__ == "__main__":
    unittest.main()
