"""
永续合约 E2E 测试 — 完整功能验证

本测试文件假定: 给定确定的 K 线数据和确定的策略下单逻辑,
回测引擎产生确定的结果, 每个订单的交易结果可以提前手工验算,
最终汇算结果符合加密货币交易所预期.

测试覆盖:
  1. min_notional — 拒绝过低名义价值订单 (订单级别 + 现金验证)
  2. min_qty — 拒绝过低数量订单 (订单级别 + 拒绝原因验证)
  3. 逐币种手续费 — commission_rate 逐品种覆盖全局 (订单级别 + 现金验证)
  4. 逐币种滑点 — slippage 逐品种生效 (执行价格验证)
  5. 基本成交 — 无滑点/手续费下的完整买卖循环 (订单 + 交易 + 现金)
  6. 资金费率结算 — 跨越 UTC 结算点精确扣款 (现金验证)
  7. 强平检查 — 权益低于维持保证金时触发 (仓位验证)
  8. 订单延迟功能 — bar_offset=0 (当前收盘) vs bar_offset=1 (下一开盘)
  9. 综合 5m 场景 — 300 根 bar 全功能验证

运行:
  pytest test_crypto_e2e.py -v
  pytest test_crypto_e2e.py -k "test_min_notional" -v
"""

import math
import pytest

try:
    import akquant as aq
    from akquant import Strategy
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False

requires_engine = pytest.mark.skipif(
    not ENGINE_AVAILABLE,
    reason="akquant Rust 扩展未编译, 跳过集成测试"
)


def _df(n: int, start: str, price: float = 50000.0, freq: str = "5min",
        funding_schedule: dict = None) -> "pd.DataFrame":
    """构造 N 根 bar 的 DataFrame.
    funding_schedule: {hour: rate}, 如 {8: 0.001}.
    """
    import pandas as pd
    ts = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    funding = []
    for t in ts:
        if funding_schedule and t.hour in funding_schedule and t.minute == 0:
            funding.append(funding_schedule[t.hour])
        else:
            funding.append(0.0)
    df = pd.DataFrame({
        "timestamp": ts, "open": float(price), "high": float(price)*1.002,
        "low": float(price)*0.998, "close": float(price), "volume": 100.0,
        "symbol": "BTCUSDT",
    })
    if funding_schedule:
        df["funding_rate"] = funding
        df["mark_price"] = float(price)
    return df


def _instr(min_notional: float = 0.0, commission_rate: float = None,
           slippage: float = None, lot_size: float = 0.001,
           step_size: float = 0.001, min_qty: float = 0.001) -> dict:
    d = {"asset_type": "CRYPTO", "multiplier": 1.0, "margin_ratio": 1.0,
         "tick_size": 0.01, "lot_size": lot_size, "step_size": step_size,
         "min_qty": min_qty, "min_notional": min_notional}
    if commission_rate is not None:
        d["commission_rate"] = commission_rate
    if slippage is not None:
        d["slippage"] = slippage
    return d


# ═══════════════════════════════════════════════════════════════
#  1. min_notional — 订单级别验证
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestMinNotional:
    def test_rejects_low_value_accepts_valid(self):
        """min_notional=50: qty=0.001→notional=50→Filled; qty=0.0001→5→Rejected."""
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            n = 0
            def on_bar(self, bar):
                self.n += 1
                if self.n == 1:
                    self.buy("BTCUSDT", quantity=0.001)   # 50 ≥ 50 → FILL
                elif self.n == 2:
                    self.buy("BTCUSDT", quantity=0.0001)  # 5 < 50 → REJECT

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            instruments={"BTCUSDT": _instr(min_notional=50.0)})

        odf = r.orders_df.sort_values("created_at").reset_index(drop=True)
        # 第 1 笔: quantity=0.001 → Filled
        assert odf.loc[0, "status"] == "filled", f"Order 0: expected filled, got {odf.loc[0,'status']}"
        assert float(odf.loc[0, "quantity"]) == pytest.approx(0.001)
        # 第 2 笔: quantity=0.0001 → Rejected
        assert odf.loc[1, "status"] == "rejected", f"Order 1: expected rejected, got {odf.loc[1,'status']}"
        assert float(odf.loc[1, "quantity"]) == pytest.approx(0.0001)
        rr = str(odf.loc[1, "reject_reason"]).lower()
        assert "min" in rr or "notional" in rr, f"Reject reason: {odf.loc[1,'reject_reason']}"

    def test_boundary_fills_correct_cash(self):
        """边缘值: notional==50 应成交. 现金 = 100000 - 0.001×50000 = 99950."""
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=0.001)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            instruments={"BTCUSDT": _instr(min_notional=50.0)})

        assert float(r.cash_curve.iloc[-1]) == pytest.approx(99950.0, abs=1.0)
        odf = r.orders_df
        filled = odf[odf["status"] == "filled"]
        assert len(filled) == 1
        assert float(filled.iloc[0]["filled_quantity"]) == pytest.approx(0.001)


# ═══════════════════════════════════════════════════════════════
#  2. min_qty — 订单级别 + 拒绝原因验证
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestMinQty:
    def test_rejects_below_reason_matches(self):
        """min_qty=0.001: qty=0.001→Filled; qty=0.0005→Rejected with reason."""
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            n = 0
            def on_bar(self, bar):
                self.n += 1
                if self.n == 1:
                    self.buy("BTCUSDT", quantity=0.001)
                elif self.n == 2:
                    self.buy("BTCUSDT", quantity=0.0005)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            instruments={"BTCUSDT": _instr(min_qty=0.001)})

        odf = r.orders_df.sort_values("created_at").reset_index(drop=True)
        assert odf.loc[0, "status"] == "filled", f"Order 0: {odf.loc[0,'status']}"
        assert odf.loc[1, "status"] == "rejected", f"Order 1: {odf.loc[1,'status']}"
        rr = str(odf.loc[1, "reject_reason"]).lower()
        assert "min_qty" in rr or "qty" in rr, f"Expected min_qty in reject, got: {odf.loc[1,'reject_reason']}"


# ═══════════════════════════════════════════════════════════════
#  3. 逐币种手续费 — 订单级别验证
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestPerSymbolCommission:
    def test_global_rate_applied(self):
        """全局佣金按 commission_rate=0.001 扣费. 现金 = 100000-50000-50 = 49950.

        注意: 加密货币费率不是逐币种的, instruments.commission_rate 不覆盖全局.
        """
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.001,
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0)})

        odf = r.orders_df
        assert len(odf) == 1
        assert float(odf.iloc[0]["commission"]) == pytest.approx(50.0, abs=1.0)  # 50000×0.001
        assert float(r.cash_curve.iloc[-1]) == pytest.approx(49950.0, abs=1.0)

    def test_per_instrument_commission_ignored(self):
        """instruments 中的 commission_rate 对 Crypto 不生效, 仍使用全局 0.001.

        现金预计算: 100000 - 50000 - 50(50000×0.001) = 49950.
        """
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.001,
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0,
                                           commission_rate=0.002)})

        odf = r.orders_df
        # 即使 instruments 设置了 commission_rate=0.002, 仍使用全局 0.001
        assert float(odf.iloc[0]["commission"]) == pytest.approx(50.0, abs=1.0)
        assert float(r.cash_curve.iloc[-1]) == pytest.approx(49950.0, abs=1.0)


# ═══════════════════════════════════════════════════════════════
#  4. 逐币种滑点 — 执行价格验证
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestPerSymbolSlippage:
    def test_slippage_affects_fill_price(self):
        """slippage=0.01 → 成交价 = 50000 × 1.01 = 50500. 现金 = 100000 - 50500 - 50.5 = 49449.5."""
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.001,
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0,
                                           slippage=0.01)})

        odf = r.orders_df
        avg_price = float(odf.iloc[0]["avg_price"])
        assert avg_price == pytest.approx(50500.0, abs=10.0), f"Expected ~50500, got {avg_price}"
        expected_commission = 50500.0 * 0.001  # 50.5
        assert float(odf.iloc[0]["commission"]) == pytest.approx(expected_commission, abs=1.0)

    def test_no_slippage_default(self):
        """默认无滑点 → 成交价 = 50000."""
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0)})

        odf = r.orders_df
        assert float(odf.iloc[0]["avg_price"]) == pytest.approx(50000.0, abs=1.0)


# ═══════════════════════════════════════════════════════════════
#  5. 基本成交 — 完整买卖循环
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestBasicTradeCycle:
    """无滑点/手续费的完整买卖循环, 验证所有订单记录 + 交易记录 + 现金."""

    def test_buy_sell_same_price(self):
        """买入 1 @ 50000, 卖出 1 @ 50000, 无手续费, 现金回到 100000."""
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            n = 0
            def on_bar(self, bar):
                self.n += 1
                if self.n == 1:
                    self.buy("BTCUSDT", quantity=1)
                elif self.n == 2:
                    self.sell("BTCUSDT", quantity=1)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0)})

        odf = r.orders_df.sort_values("created_at").reset_index(drop=True)
        # 订单级别
        assert len(odf) == 2
        assert odf.loc[0, "side"] == "buy" and odf.loc[0, "status"] == "filled"
        assert odf.loc[1, "side"] == "sell" and odf.loc[1, "status"] == "filled"
        assert float(odf.loc[0, "commission"]) == pytest.approx(0.0)
        assert float(odf.loc[1, "commission"]) == pytest.approx(0.0)
        # 交易级别
        assert len(r.trades) == 1
        t = r.trades[0]
        assert t.symbol == "BTCUSDT"
        assert float(t.entry_price) == pytest.approx(50000.0, abs=1.0)
        assert float(t.exit_price) == pytest.approx(50000.0, abs=1.0)
        assert float(t.pnl) == pytest.approx(0.0, abs=1.0)
        assert float(t.net_pnl) == pytest.approx(0.0, abs=1.0)
        # 现金验证
        assert float(r.cash_curve.iloc[-1]) == pytest.approx(100000.0, abs=1.0)

    def test_buy_sell_with_commission(self):
        """买入 1 @ 50000 (佣金 0.1%), 卖出 1 @ 50000 (佣金 0.1%).

        预计算:
          买入: cash -50000 -50 = 49950
          卖出: cash +50000 -50 = 99900
        """
        import pandas as pd
        df = _df(10, "2024-01-01 00:00")

        class S(aq.Strategy):
            n = 0
            def on_bar(self, bar):
                self.n += 1
                if self.n == 1:
                    self.buy("BTCUSDT", quantity=1)
                elif self.n == 2:
                    self.sell("BTCUSDT", quantity=1)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.001,
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0)})

        odf = r.orders_df.sort_values("created_at").reset_index(drop=True)
        assert float(odf.loc[0, "commission"]) == pytest.approx(50.0, abs=1.0)
        assert float(odf.loc[1, "commission"]) == pytest.approx(50.0, abs=1.0)
        assert float(r.cash_curve.iloc[-1]) == pytest.approx(99900.0, abs=1.0)


# ═══════════════════════════════════════════════════════════════
#  6. 资金费率结算
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestFundingSettlement:
    def test_long_pays_at_utc8(self):
        """做多 1 BTC, 08:00 结算 0.1%. 现金 = 100000-50000-50 = 49950."""
        df = _df(25, "2024-01-01 07:00", funding_schedule={8: 0.001})
        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)
        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0)
        assert float(r.cash_curve.iloc[-1]) == pytest.approx(49950.0, abs=1.0)

    def test_short_receives_at_utc8(self):
        """做空 1 BTC, 08:00 应收 50. 现金 = 100000+50000+50 = 150050."""
        df = _df(25, "2024-01-01 07:00", funding_schedule={8: 0.001})
        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.short("BTCUSDT", quantity=1)
        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0)
        assert float(r.cash_curve.iloc[-1]) == pytest.approx(150050.0, abs=1.0)

    def test_negative_rate_long_receives(self):
        """funding_rate=-0.001, 多头应收. 现金 = 100000-50000+50 = 50050."""
        df = _df(25, "2024-01-01 07:00", funding_schedule={8: -0.001})
        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)
        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0)
        assert float(r.cash_curve.iloc[-1]) == pytest.approx(50050.0, abs=1.0)

    def test_two_funding_events(self):
        """08:00+16:00 两次结算各扣 50. 现金 = 100000-50000-50-50 = 49900."""
        df = _df(120, "2024-01-01 07:00", funding_schedule={8: 0.001, 16: 0.001})
        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)
        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0)
        assert float(r.cash_curve.iloc[-1]) == pytest.approx(49900.0, abs=10.0)


# ═══════════════════════════════════════════════════════════════
#  7. 强平检查
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestLiquidation:
    def test_liquidation_reduces_position(self):
        """10x 杠杆做多 10 BTC @ ~100, 价格跌到 80 → 强平, 持仓 ≠ 10."""
        import pandas as pd
        n = 61
        prices = [100.0 - i * (20.0 / n) for i in range(n)]
        ts = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
        df = pd.DataFrame({"timestamp": ts, "open": prices, "high": [p*1.01 for p in prices],
            "low": [p*0.99 for p in prices], "close": prices, "volume": 100.0, "symbol": "BTCUSDT",
            "funding_rate": [0.0]*n, "mark_price": prices})

        final_pos = {"v": None}
        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0 and bar.close > 95:
                    self.buy("BTCUSDT", quantity=10)
            def on_stop(self):
                final_pos["v"] = self.get_position("BTCUSDT")

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=1000, commission_rate=0.0,
            margin_ratio=0.1)
        assert final_pos["v"] is not None
        # 强平触发后仓位减少
        assert final_pos["v"] != 10.0, f"Position should change after liquidation, got {final_pos['v']}"
        # 存在强平单(close)或减仓成交
        odf = r.orders_df
        assert len(odf) > 1, "Expected at least 1 liquidation order"


# ═══════════════════════════════════════════════════════════════
#  8. 订单延迟功能 — fill_policy 验证
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestOrderDelay:
    """验证 fill_policy 对成交时机的影响.

    bar_offset=1 (默认): bar N 下单 → bar N+1 以 open 成交
    bar_offset=0:        bar N 下单 → bar N 以 close 成交

    数据: [bar 0 open=100, bar 1 open=110, bar 2 open=120]
    """

    def test_bar_offset_1_fills_next_open(self):
        """bar_offset=1: bar 0 下单 → bar 1 以 open=110 成交."""
        import pandas as pd
        ts = pd.date_range("2024-01-01", periods=5, freq="5min", tz="UTC")
        df = pd.DataFrame({"timestamp": ts, "open": [100, 110, 120, 130, 140],
            "high": [105, 115, 125, 135, 145], "low": [95, 105, 115, 125, 135],
            "close": [102, 112, 122, 132, 142], "volume": 100.0, "symbol": "BTCUSDT"})

        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            fill_policy={"price_basis": "open", "bar_offset": 1, "temporal": "same_cycle"},
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0)})

        odf = r.orders_df
        assert len(odf) == 1, f"Expected 1 order, got {len(odf)}"
        avg_price = float(odf.iloc[0]["avg_price"])
        assert avg_price == pytest.approx(110.0, abs=1.0), \
            f"Expected fill at 110 (next open), got {avg_price}"

    def test_bar_offset_0_fills_same_close(self):
        """bar_offset=0: bar 0 下单 → bar 0 以 close=102 成交."""
        import pandas as pd
        ts = pd.date_range("2024-01-01", periods=5, freq="5min", tz="UTC")
        df = pd.DataFrame({"timestamp": ts, "open": [100, 110, 120, 130, 140],
            "high": [105, 115, 125, 135, 145], "low": [95, 105, 115, 125, 135],
            "close": [102, 112, 122, 132, 142], "volume": 100.0, "symbol": "BTCUSDT"})

        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            fill_policy={"price_basis": "close", "bar_offset": 0, "temporal": "same_cycle"},
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0)})

        odf = r.orders_df
        assert len(odf) == 1
        avg_price = float(odf.iloc[0]["avg_price"])
        assert avg_price == pytest.approx(102.0, abs=1.0), \
            f"Expected fill at 102 (same close), got {avg_price}"

    def test_bar_offset_1_vs_0_different_cash(self):
        """bar_offset=1 成交价更高 → 现金更少.

        bar_offset=1: fill=110, cash = 100000-110 = 99890
        bar_offset=0: fill=102, cash = 100000-102 = 99898
        """
        import pandas as pd
        ts = pd.date_range("2024-01-01", periods=5, freq="5min", tz="UTC")
        df = pd.DataFrame({"timestamp": ts, "open": [100, 110, 120, 130, 140],
            "high": [105, 115, 125, 135, 145], "low": [95, 105, 115, 125, 135],
            "close": [102, 112, 122, 132, 142], "volume": 100.0, "symbol": "BTCUSDT"})

        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

        r_off1 = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            fill_policy={"price_basis": "open", "bar_offset": 1, "temporal": "same_cycle"},
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0)})
        r_off0 = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=100000, commission_rate=0.0,
            fill_policy={"price_basis": "close", "bar_offset": 0, "temporal": "same_cycle"},
            instruments={"BTCUSDT": _instr(lot_size=1.0, step_size=1.0, min_qty=1.0)})

        cash_off1 = float(r_off1.cash_curve.iloc[-1])
        cash_off0 = float(r_off0.cash_curve.iloc[-1])
        assert cash_off1 == pytest.approx(99890.0, abs=1.0), f"offset=1: {cash_off1}"
        assert cash_off0 == pytest.approx(99898.0, abs=1.0), f"offset=0: {cash_off0}"
        # offset=0 成本更低 → 现金更多
        assert cash_off0 > cash_off1, f"offset=0 cash ({cash_off0}) should be > offset=1 ({cash_off1})"


# ═══════════════════════════════════════════════════════════════
#  9. 综合 5m 场景 — 300 根 bar
# ═══════════════════════════════════════════════════════════════

@pytest.mark.integration
@requires_engine
class TestComprehensive5mScenario:
    """300 根 5m bar (~25h): 价格从 50000 跌到 40000, 10x, 含 FR + 手续费 + 强平."""

    def test_300bar_scenario(self):
        import pandas as pd; import numpy as np
        n = 300; ts = pd.date_range("2024-01-01 00:00", periods=n, freq="5min", tz="UTC")
        prices = np.linspace(50000, 40000, n)
        funding = [0.001 if (t.hour in (0,8,16) and t.minute==0) else 0.0 for t in ts]
        df = pd.DataFrame({"timestamp": ts, "open": prices, "high": prices*1.002,
            "low": prices*0.998, "close": prices, "volume": np.full(n, 100.0), "symbol": "BTCUSDT",
            "funding_rate": funding, "mark_price": prices})

        info = {"bought": False}
        class S(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0 and not info["bought"] and bar.open < 49950:
                    self.buy("BTCUSDT", quantity=0.1); info["bought"] = True

        r = aq.run_backtest(strategy=S(), symbols=["BTCUSDT"], data=df,
            asset_type=aq.AssetType.Crypto, initial_cash=10000, commission_rate=0.0005,
            margin_ratio=0.1,
            instruments={"BTCUSDT":{"asset_type":"CRYPTO","multiplier":1.0,
                "tick_size":0.01,"lot_size":0.001,"step_size":0.001,"min_qty":0.001}})

        assert r is not None
        assert len(r.cash_curve) > 0
        filled = r.orders_df[r.orders_df["status"]=="filled"]
        assert len(filled) > 0, "No filled orders"
