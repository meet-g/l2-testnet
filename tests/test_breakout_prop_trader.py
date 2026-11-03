"""Unit tests for Breakout Prop Firm trader configuration and risk supervisor.

Verifies:
1. BreakoutPropConfig defaults, dollar metrics, circuit breaker thresholds, and asymmetric payoff properties.
2. BreakoutRiskSupervisor state tracking, high-water mark trailing drawdown, and status transitions.
3. Daily UTC 00:00 calendar rollover and daily loss halt behavior.
4. Dynamic leverage ratchets and finish-line de-risking.
5. Calibrated coin unit sizing across BTC, ETH, HYPE, and SOL.
6. Challenge simulation sequencer and Monte Carlo probability evaluator.
"""

from datetime import datetime, timezone
import unittest

from breakout_prop_trader import (
    BreakoutPropConfig,
    BreakoutRiskSupervisor,
    ChallengeStatus,
    simulate_breakout_challenges,
    run_monte_carlo_pass_probability,
)
from engine.backtester import TradeRecord


class TestBreakoutPropConfig(unittest.TestCase):
    """Verifies BreakoutPropConfig parameter constraints and dollar thresholds."""

    def test_default_breakout_parameters(self):
        cfg = BreakoutPropConfig()
        # $5,000 account size, $20 purchase fee
        self.assertEqual(cfg.account_size_usd, 5000.0)
        self.assertEqual(cfg.challenge_fee_usd, 20.0)

        # 9% profit target (+$450.00)
        self.assertEqual(cfg.profit_target_pct, 9.0)
        self.assertEqual(cfg.profit_target_usd, 450.0)
        self.assertEqual(cfg.target_equity_usd, 5450.0)

        # 3% max daily loss (-$150.00)
        self.assertEqual(cfg.max_daily_loss_pct, 3.0)
        self.assertEqual(cfg.max_daily_loss_usd, 150.0)

        # 3% max drawdown (-$150.00)
        self.assertEqual(cfg.max_drawdown_pct, 3.0)
        self.assertEqual(cfg.max_drawdown_usd, 150.0)

        # Defensive Circuit Breakers
        self.assertEqual(cfg.defensive_daily_loss_pct, 2.0)
        self.assertEqual(cfg.defensive_daily_loss_usd, 100.0)
        self.assertEqual(cfg.defensive_drawdown_pct, 2.2)
        self.assertEqual(cfg.defensive_drawdown_usd, 110.0)

        # Leverage & Rules
        self.assertEqual(cfg.target_leverage, 1.5)
        self.assertEqual(cfg.max_leverage, 2.0)
        self.assertEqual(cfg.min_leverage, 0.4)
        self.assertTrue(cfg.mandatory_stop_loss)

    def test_custom_account_size(self):
        cfg = BreakoutPropConfig(account_size_usd=10000.0, challenge_fee_usd=40.0)
        self.assertEqual(cfg.account_size_usd, 10000.0)
        self.assertEqual(cfg.profit_target_usd, 900.0)
        self.assertEqual(cfg.target_equity_usd, 10900.0)
        self.assertEqual(cfg.max_drawdown_usd, 300.0)
        self.assertEqual(cfg.defensive_drawdown_usd, 220.0)
        self.assertEqual(cfg.max_daily_loss_usd, 300.0)
        self.assertEqual(cfg.defensive_daily_loss_usd, 200.0)


class TestBreakoutRiskSupervisor(unittest.TestCase):
    """Verifies stateful risk supervision, drawdown ratchet, and challenge gates."""

    def setUp(self):
        self.cfg = BreakoutPropConfig()
        self.supervisor = BreakoutRiskSupervisor(self.cfg)

    def test_initial_state(self):
        self.assertEqual(self.supervisor.current_equity, 5000.0)
        self.assertEqual(self.supervisor.peak_equity, 5000.0)
        self.assertEqual(self.supervisor.max_drawdown_usd, 0.0)
        self.assertEqual(self.supervisor.status, ChallengeStatus.IN_PROGRESS)
        self.assertTrue(self.supervisor.is_active)
        self.assertEqual(self.supervisor.remaining_to_target, 450.0)
        self.assertEqual(self.supervisor.remaining_drawdown_buffer, 110.0)
        self.assertEqual(self.supervisor.hard_drawdown_buffer, 150.0)
        # 3% of account value: $150 on $5k, defensive: $100 and $110
        self.assertEqual(self.supervisor.daily_loss_limit_usd, 150.0)
        self.assertEqual(self.supervisor.defensive_daily_loss_limit_usd, 100.0)
        self.assertEqual(self.supervisor.max_drawdown_limit_usd, 150.0)
        self.assertEqual(self.supervisor.defensive_drawdown_limit_usd, 110.0)

    def test_dynamic_limits_on_equity_growth(self):
        """Verifies 3% daily loss and max DD limits scale dynamically with account equity."""
        # When equity grows to $5,200
        self.supervisor.current_equity = 5200.0
        self.supervisor.peak_equity = 5200.0
        self.supervisor.daily_start_equity = 5200.0

        # 3% of $5,200 = $156.00, 2% = $104.00, 2.2% = $114.40
        self.assertEqual(self.supervisor.daily_loss_limit_usd, 156.0)
        self.assertEqual(self.supervisor.defensive_daily_loss_limit_usd, 104.0)
        self.assertEqual(self.supervisor.max_drawdown_limit_usd, 156.0)
        self.assertEqual(self.supervisor.defensive_drawdown_limit_usd, 114.4)

    def test_dynamic_leverage_ratchet(self):
        # 1. Healthy buffer: remaining drawdown buffer = 110.0 (>= 80.0) -> target_leverage (1.5x)
        self.assertEqual(self.supervisor.get_dynamic_leverage(), 1.5)

        # 2. Moderate buffer: simulate $40 drawdown -> rem buffer = 110 - 40 = 70.0 (in [50, 80))
        # Expected leverage: 1.5 * 0.75 = 1.125
        self.supervisor.current_equity = 4960.0
        self.assertAlmostEqual(self.supervisor.get_dynamic_leverage(), 1.125)

        # 3. Caution buffer: simulate $70 drawdown -> rem buffer = 110 - 70 = 40.0 (in [25, 50))
        # Expected leverage: 1.5 * 0.50 = 0.75
        self.supervisor.current_equity = 4930.0
        self.assertAlmostEqual(self.supervisor.get_dynamic_leverage(), 0.75)

        # 4. Critical buffer: simulate $95 drawdown -> rem buffer = 110 - 95 = 15.0 (in (0, 25))
        # Expected leverage: min_leverage = 0.40
        self.supervisor.current_equity = 4905.0
        self.assertAlmostEqual(self.supervisor.get_dynamic_leverage(), 0.40)

        # 5. Breached defensive buffer: rem buffer <= 0 -> 0.0 leverage
        self.supervisor.current_equity = 4880.0
        self.assertEqual(self.supervisor.get_dynamic_leverage(), 0.0)

    def test_finish_line_derisking(self):
        # When equity is within $40 of target ($5,410 to $5,450), leverage scales down smoothly
        self.supervisor.current_equity = 5430.0  # $20 to target ($5,450 - $5,430)
        self.supervisor.peak_equity = 5430.0
        # finish_factor = max(0.25, 20.0 / 40.0) = 0.50
        # lev = min(1.5, 1.5 * 0.50) = 0.75
        expected_lev = 1.5 * 0.50
        self.assertAlmostEqual(self.supervisor.get_dynamic_leverage(), expected_lev)

        # When equity is $10 to target
        self.supervisor.current_equity = 5440.0
        self.supervisor.peak_equity = 5440.0
        # finish_factor = max(0.25, 10.0 / 40.0) = 0.25
        # min allowed is min_leverage (0.4)
        self.assertAlmostEqual(self.supervisor.get_dynamic_leverage(), 0.4)

    def test_order_sizing_by_coin(self):
        # At 1.5x leverage and $5,000 equity, notional is $7,500.00
        # BTC (4 decimal places)
        btc_size = self.supervisor.calculate_order_size("BTC", 80000.0)
        self.assertEqual(btc_size, round(7500.0 / 80000.0, 4))  # 0.0938

        # ETH (3 decimal places)
        eth_size = self.supervisor.calculate_order_size("ETH", 3000.0)
        self.assertEqual(eth_size, round(7500.0 / 3000.0, 3))   # 2.500

        # HYPE (2 decimal places)
        hype_size = self.supervisor.calculate_order_size("HYPE", 25.0)
        self.assertEqual(hype_size, round(7500.0 / 25.0, 2))    # 300.00

        # SOL (2 decimal places)
        sol_size = self.supervisor.calculate_order_size("SOL", 150.0)
        self.assertEqual(sol_size, round(7500.0 / 150.0, 2))    # 50.00

        # Invalid price returns 0.0
        self.assertEqual(self.supervisor.calculate_order_size("BTC", 0.0), 0.0)
        self.assertEqual(self.supervisor.calculate_order_size("BTC", -100.0), 0.0)

    def test_utc_midnight_day_rollover(self):
        # 2026-10-08 23:50:00 UTC = 1791503400000 ms
        t1_ms = int(datetime(2026, 10, 8, 23, 50, tzinfo=timezone.utc).timestamp() * 1000)
        self.supervisor.update_timestamp(t1_ms)
        self.assertEqual(self.supervisor.current_day_str, "2026-10-08")

        # Record a trade on 2026-10-08
        trade1 = TradeRecord(
            strategy_name="Queue_Replenishment",
            entry_time_ms=t1_ms,
            exit_time_ms=t1_ms + 1000,
            side="BUY",
            entry_price=80000.0,
            exit_price=80100.0,
            size_btc=0.1,
            gross_pnl_usd=10.0,
            fees_usd=1.0,
            net_pnl_usd=9.0,
            return_bps=12.5,
            exit_reason="TAKE_PROFIT",
            execution_type="MAKER",
        )
        self.supervisor.record_trade(trade1)
        self.assertEqual(self.supervisor.daily_pnl_usd, 9.0)
        self.assertEqual(self.supervisor.current_equity, 5009.0)

        # Next timestamp crosses midnight: 2026-10-09 00:05:00 UTC
        t2_ms = int(datetime(2026, 10, 9, 0, 5, tzinfo=timezone.utc).timestamp() * 1000)
        self.supervisor.update_timestamp(t2_ms)

        # Verifies day rollover resets daily counters
        self.assertEqual(self.supervisor.current_day_str, "2026-10-09")
        self.assertEqual(self.supervisor.daily_start_equity, 5009.0)
        self.assertEqual(self.supervisor.daily_pnl_usd, 0.0)
        self.assertEqual(self.supervisor.daily_loss_usd, 0.0)
        self.assertFalse(self.supervisor.daily_halted)

    def test_profit_target_passed_gate(self):
        t_ms = 1791500000000
        self.supervisor.update_timestamp(t_ms)

        # Large win pushing equity to $5,455.00 (above +$450 target)
        trade = TradeRecord(
            strategy_name="Queue_Replenishment",
            entry_time_ms=t_ms,
            exit_time_ms=t_ms + 5000,
            side="BUY",
            entry_price=80000.0,
            exit_price=84550.0,
            size_btc=0.1,
            gross_pnl_usd=460.0,
            fees_usd=5.0,
            net_pnl_usd=455.0,
            return_bps=560.0,
            exit_reason="TAKE_PROFIT",
            execution_type="MAKER",
        )
        self.supervisor.record_trade(trade)

        self.assertEqual(self.supervisor.status, ChallengeStatus.PASSED)
        self.assertIn("Profit Target Reached", self.supervisor.status_reason)
        self.assertFalse(self.supervisor.is_active)
        self.assertEqual(self.supervisor.get_dynamic_leverage(), 0.0)
        self.assertEqual(self.supervisor.calculate_order_size("BTC", 80000.0), 0.0)

    def test_defensive_drawdown_halt_gate(self):
        t_ms = 1791500000000
        self.supervisor.update_timestamp(t_ms)

        # Loss of $112 pushing drawdown to $112 (exceeding $110 defensive cutoff)
        trade = TradeRecord(
            strategy_name="Queue_Replenishment",
            entry_time_ms=t_ms,
            exit_time_ms=t_ms + 5000,
            side="BUY",
            entry_price=80000.0,
            exit_price=78880.0,
            size_btc=0.1,
            gross_pnl_usd=-110.0,
            fees_usd=2.0,
            net_pnl_usd=-112.0,
            return_bps=-140.0,
            exit_reason="STOP_LOSS",
            execution_type="MAKER",
        )
        self.supervisor.record_trade(trade)

        self.assertEqual(self.supervisor.status, ChallengeStatus.HALTED_DEFENSIVE_DD)
        self.assertIn("Defensive Drawdown Halt", self.supervisor.status_reason)
        self.assertFalse(self.supervisor.is_active)
        # Account is safely stopped BEFORE reaching prop firm's hard $150 limit
        self.assertLess(self.supervisor.max_drawdown_usd, self.cfg.max_drawdown_usd)

    def test_trailing_drawdown_from_high_water_mark(self):
        t_ms = 1791500000000
        self.supervisor.update_timestamp(t_ms)

        # First trade: Win +$200 -> Equity = $5,200 (Peak = $5,200)
        win_trade = TradeRecord(
            strategy_name="Queue_Replenishment",
            entry_time_ms=t_ms,
            exit_time_ms=t_ms + 1000,
            side="BUY",
            entry_price=80000.0,
            exit_price=82000.0,
            size_btc=0.1,
            gross_pnl_usd=205.0,
            fees_usd=5.0,
            net_pnl_usd=200.0,
            return_bps=250.0,
            exit_reason="TAKE_PROFIT",
            execution_type="MAKER",
        )
        self.supervisor.record_trade(win_trade)
        self.assertEqual(self.supervisor.current_equity, 5200.0)
        self.assertEqual(self.supervisor.peak_equity, 5200.0)

        # Second trade: Loss -$115 -> Equity = $5,085 (Drawdown from peak = $115)
        loss_trade = TradeRecord(
            strategy_name="Queue_Replenishment",
            entry_time_ms=t_ms + 2000,
            exit_time_ms=t_ms + 3000,
            side="BUY",
            entry_price=80000.0,
            exit_price=78850.0,
            size_btc=0.1,
            gross_pnl_usd=-113.0,
            fees_usd=2.0,
            net_pnl_usd=-115.0,
            return_bps=-145.0,
            exit_reason="STOP_LOSS",
            execution_type="MAKER",
        )
        self.supervisor.record_trade(loss_trade)

        # Current equity ($5,085) is above initial $5,000, but trailing DD from HWM ($5,200) is $115
        # Defensive cutoff ($110) must trigger!
        self.assertEqual(self.supervisor.status, ChallengeStatus.HALTED_DEFENSIVE_DD)
        self.assertEqual(self.supervisor.max_drawdown_usd, 115.0)

    def test_defensive_daily_loss_halt_gate(self):
        t_ms = 1791500000000
        self.supervisor.update_timestamp(t_ms)

        # Loss of $105 on current day (exceeds $100 defensive daily cutoff)
        trade = TradeRecord(
            strategy_name="Queue_Replenishment",
            entry_time_ms=t_ms,
            exit_time_ms=t_ms + 5000,
            side="BUY",
            entry_price=80000.0,
            exit_price=78950.0,
            size_btc=0.1,
            gross_pnl_usd=-103.0,
            fees_usd=2.0,
            net_pnl_usd=-105.0,
            return_bps=-130.0,
            exit_reason="STOP_LOSS",
            execution_type="MAKER",
        )
        self.supervisor.record_trade(trade)

        # Daily halted, but challenge remains IN_PROGRESS (can resume after midnight rollover)
        self.assertTrue(self.supervisor.daily_halted)
        self.assertFalse(self.supervisor.is_active)
        self.assertEqual(self.supervisor.status, ChallengeStatus.IN_PROGRESS)

    def test_daily_loss_buffer_derisking(self):
        """Verifies dynamic leverage throttles when approaching daily loss limit even if overall DD is small."""
        # Equity is $5,000 at start of day.
        # Suppose intraday losses hit $80 -> daily loss = $80.
        # Defensive daily loss limit is $100 -> remaining daily buffer is $20 (< 25).
        # Even though remaining drawdown buffer is $110 - $80 = $30 (which would give 0.75x if only DD checked),
        # effective_buffer = min(30, 20) = 20 (< 25) -> throttles down to min_leverage = 0.40!
        self.supervisor.current_equity = 4920.0
        self.supervisor.peak_equity = 5000.0
        self.supervisor.daily_start_equity = 5000.0

        self.assertEqual(self.supervisor.remaining_drawdown_buffer, 30.0)
        self.assertEqual(self.supervisor.remaining_daily_loss_buffer, 20.0)
        self.assertEqual(self.supervisor.hard_daily_loss_buffer, 70.0)
        self.assertEqual(self.supervisor.hard_drawdown_buffer, 70.0)

        # Dynamic leverage must be throttled to 0.4x because daily loss is only $20 from cutoff!
        self.assertEqual(self.supervisor.get_dynamic_leverage(), 0.40)


class TestChallengeSimulationAndMonteCarlo(unittest.TestCase):
    """Verifies continuous challenge sequencing and Monte Carlo pass evaluation."""

    def test_cross_midnight_trade_realization(self):
        """Verifies trade spanning across 00:00 UTC rollover realizes on new day and halts trading."""
        t_entry_day1 = int(datetime(2026, 10, 8, 23, 59, 0, tzinfo=timezone.utc).timestamp() * 1000)
        t_exit_day2 = int(datetime(2026, 10, 9, 0, 1, 0, tzinfo=timezone.utc).timestamp() * 1000)
        t_trade2_entry = int(datetime(2026, 10, 9, 0, 5, 0, tzinfo=timezone.utc).timestamp() * 1000)
        t_trade2_exit = int(datetime(2026, 10, 9, 0, 6, 0, tzinfo=timezone.utc).timestamp() * 1000)

        trades = [
            {
                "strategy": "Hedged_Convexity",
                "entry_time_ms": t_entry_day1,
                "exit_time_ms": t_exit_day2,
                "side": "BUY",
                "entry_price": 80000.0,
                "exit_price": 78900.0,
                "size": 0.1,
                "gross_pnl": -103.0,
                "fees": 2.0,
                "net_pnl": -105.0,
                "return_bps": -130.0,
                "exit_reason": "STOP_LOSS",
                "exec_type": "MAKER",
            },
            {
                "strategy": "Hedged_Convexity",
                "entry_time_ms": t_trade2_entry,
                "exit_time_ms": t_trade2_exit,
                "side": "BUY",
                "entry_price": 78900.0,
                "exit_price": 78100.0,
                "size": 0.1,
                "gross_pnl": -78.0,
                "fees": 2.0,
                "net_pnl": -80.0,
                "return_bps": -100.0,
                "exit_reason": "STOP_LOSS",
                "exec_type": "MAKER",
            },
        ]

        sim_res = simulate_breakout_challenges(trades, BreakoutPropConfig())
        # First trade exits on Day 2 with -$105 loss -> triggers daily halt on Day 2
        # Second trade on Day 2 is skipped! Total loss is kept at $105, strictly below $150 limit!
        self.assertEqual(sim_res["hard_failures"], 0)
        self.assertEqual(len(sim_res["challenges"]), 1)
        ch = sim_res["challenges"][0]
        self.assertEqual(ch["trades"], 1)
        self.assertEqual(ch["net_pnl"], -105.0)
        self.assertEqual(ch["max_drawdown"], 105.0)
        self.assertLess(ch["max_drawdown"], 150.0)

    def test_simulate_breakout_challenges(self):
        # Create a series of synthetic trades that reach +$450
        base_time = 1791500000000
        trades = []
        for i in range(50):
            trades.append({
                "strategy": "Queue_Replenishment",
                "entry_time_ms": base_time + (i * 60000),
                "exit_time_ms": base_time + (i * 60000) + 1000,
                "side": "BUY",
                "entry_price": 80000.0,
                "exit_price": 80100.0,
                "size": 0.1,
                "gross_pnl": 10.0,
                "fees": 0.5,
                "net_pnl": 9.5,
                "return_bps": 12.0,
                "exit_reason": "TAKE_PROFIT",
                "exec_type": "MAKER",
            })

        # 48 trades * $9.5 = $456.0 > $450 profit target (hits PASSED on trade 48)
        sim_res = simulate_breakout_challenges(trades[:48], BreakoutPropConfig())
        self.assertEqual(sim_res["total_attempts"], 1)
        self.assertEqual(sim_res["passed_count"], 1)
        self.assertEqual(sim_res["pass_rate_pct"], 100.0)
        self.assertEqual(sim_res["hard_failures"], 0)
        self.assertEqual(sim_res["mean_trades_to_pass"], 48.0)

        # 50 trades: first attempt passes at trade 48, second attempt continues with remaining 2 trades
        sim_res2 = simulate_breakout_challenges(trades, BreakoutPropConfig())
        self.assertEqual(sim_res2["total_attempts"], 2)
        self.assertEqual(sim_res2["passed_count"], 1)
        self.assertEqual(sim_res2["challenges"][0]["status"], ChallengeStatus.PASSED)
        self.assertEqual(sim_res2["challenges"][1]["status"], ChallengeStatus.IN_PROGRESS)

    def test_simulate_breakout_challenges_with_dynamic_sizing(self):
        """Verifies simulation succeeds with dynamic leverage scaling enabled."""
        base_time = 1791500000000
        trades = [
            {
                "strategy": "Hedged_Convexity",
                "entry_time_ms": base_time + (i * 60000),
                "exit_time_ms": base_time + (i * 60000) + 1000,
                "side": "BUY",
                "entry_price": 80000.0,
                "exit_price": 80100.0,
                "size": 0.1,
                "gross_pnl": 10.0,
                "fees": 0.5,
                "net_pnl": 9.5,
                "return_bps": 12.0,
                "exit_reason": "TAKE_PROFIT",
                "exec_type": "MAKER",
            }
            for i in range(10)
        ]
        sim_res = simulate_breakout_challenges(trades, BreakoutPropConfig(), dynamic_sizing=True)
        self.assertEqual(sim_res["total_attempts"], 1)
        self.assertGreater(sim_res["challenges"][0]["final_equity"], 5000.0)

    def test_run_monte_carlo_pass_probability(self):
        # Provide positive return distribution
        synthetic_trades = [
            {"return_bps": 15.0 if i % 3 != 0 else -8.0}
            for i in range(100)
        ]
        mc_res = run_monte_carlo_pass_probability(synthetic_trades, iterations=500, config=BreakoutPropConfig())

        self.assertIn("pass_probability_pct", mc_res)
        self.assertIn("defensive_halt_pct", mc_res)
        self.assertIn("hard_ruin_pct", mc_res)
        self.assertIn("net_ev_usd", mc_res)
        self.assertGreater(mc_res["pass_probability_pct"], 0.0)
        self.assertEqual(mc_res["iterations"], 500)

    def test_empty_trades_handling(self):
        sim_empty = simulate_breakout_challenges([], BreakoutPropConfig())
        self.assertEqual(sim_empty, {})

        mc_empty = run_monte_carlo_pass_probability([], iterations=100, config=BreakoutPropConfig())
        self.assertEqual(mc_empty, {})


if __name__ == "__main__":
    unittest.main()

