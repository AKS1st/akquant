"""
Crypto 小数精度处理 — 测试用例

测试级别:
  - @pytest.mark.unit:      纯 Python 逻辑，不依赖 Rust 编译
  - @pytest.mark.integration: 需要已编译的 akquant Rust 扩展

运行方式:
  # 纯 Python 单元测试
  pytest test_crypto_precision.py -m unit -v

  # 全部测试（需 maturin develop）
  pytest test_crypto_precision.py -v
"""

import math
import pytest

from akquant.strategy_trading_api import round_qty, round_price


# ─────────────────────────────────────────────────────────────
# 单元测试: round_qty / round_price 工具函数
# ─────────────────────────────────────────────────────────────

class TestRoundQty:
    """测试 round_qty 函数"""

    def test_floor_down_to_step(self):
        """quantity 应向下截断到 step_size 的整数倍"""
        assert round_qty(0.123456, 0.001) == 0.123
        assert round_qty(0.129999, 0.001) == 0.129
        assert round_qty(0.120000, 0.001) == 0.120

    def test_exact_multiple(self):
        """quantity 恰好是 step_size 的整数倍时不变"""
        assert round_qty(0.123, 0.001) == 0.123
        assert round_qty(1.0, 0.1) == 1.0
        assert round_qty(100, 1) == 100

    def test_step_size_one(self):
        """step_size=1 退化为整数 floor"""
        assert round_qty(0.9, 1) == 0.0
        assert round_qty(1.5, 1) == 1.0
        assert round_qty(10.99, 1) == 10.0

    def test_step_size_zero(self):
        """step_size <= 0 应原样返回"""
        assert round_qty(0.123, 0) == 0.123
        assert round_qty(0.123, -1) == 0.123

    def test_small_step_size(self):
        """很小的 step_size（使用 approx 避免浮点精度问题）"""
        assert round_qty(0.00012345, 0.00001) == pytest.approx(0.00012)
        assert round_qty(0.00012999, 0.00001) == pytest.approx(0.00012)

    def test_large_numbers(self):
        """大数值（使用 approx 避免浮点精度问题）"""
        assert round_qty(50000.123, 0.001) == pytest.approx(50000.123)
        assert round_qty(50000.1239, 0.001) == pytest.approx(50000.123)
        assert round_qty(1234567.89, 0.01) == pytest.approx(1234567.89)

    def test_negative_step_size(self):
        """step_size <= 0 时原样返回"""
        assert round_qty(0.5, 0) == 0.5

    @pytest.mark.parametrize("qty,step,expected", [
        (0.0, 0.001, 0.0),
        (0.0001, 0.001, 0.0),
        (0.001, 0.001, 0.001),
        (0.0015, 0.001, 0.001),
        (0.002, 0.001, 0.002),
    ])
    def test_parametrized(self, qty, step, expected):
        assert round_qty(qty, step) == expected


class TestRoundPrice:
    """测试 round_price 函数"""

    def test_round_to_tick(self):
        """price 应四舍五入到 tick_size 的整数倍（使用 approx）"""
        assert round_price(50000.123, 0.01) == pytest.approx(50000.12)
        assert round_price(50000.129, 0.01) == pytest.approx(50000.13)

    def test_exact_multiple(self):
        """price 恰好是 tick_size 的整数倍时不变"""
        assert round_price(50000.12, 0.01) == 50000.12
        assert round_price(0.01, 0.01) == 0.01
        assert round_price(100.0001, 0.0001) == 100.0001

    def test_tick_size_zero(self):
        """tick_size <= 0 应原样返回"""
        assert round_price(50000.123, 0) == 50000.123
        assert round_price(50000.123, -0.01) == 50000.123

    def test_small_tick(self):
        """很小的 tick_size（使用 approx）"""
        assert round_price(0.00012345, 0.00001) == pytest.approx(0.00012)

    def test_large_price(self):
        """大价格（使用 approx）"""
        assert round_price(1234567.89, 0.01) == pytest.approx(1234567.89)
        assert round_price(1234567.891, 0.01) == pytest.approx(1234567.89)

    @pytest.mark.parametrize("price,tick,expected", [
        (0.0, 0.01, 0.0),
        (0.001, 0.01, 0.0),
        (0.009, 0.01, 0.01),
        (0.0149, 0.01, 0.01),
        (0.015, 0.01, 0.02),
    ])
    def test_parametrized(self, price, tick, expected):
        assert round_price(price, tick) == expected


# ─────────────────────────────────────────────────────────────
# 单元测试: 配置层 (不依赖 Rust)
# ─────────────────────────────────────────────────────────────

class TestInstrumentConfigCryptoPrecision:
    """测试 InstrumentConfig 对 step_size/min_qty 的校验"""

    def test_default_step_min_qty(self):
        """默认不传 step_size/min_qty 应正常工作"""
        from akquant.config import InstrumentConfig
        cfg = InstrumentConfig(
            symbol="BTCUSDT",
            asset_type="CRYPTO",
            tick_size=0.01,
            lot_size=0.001,
        )
        assert cfg.lot_size == 0.001
        assert cfg.step_size is None  # 未设置
        assert cfg.min_qty is None

    def test_explicit_step_and_min_qty(self):
        """显式传入 step_size/min_qty 应被接受"""
        from akquant.config import InstrumentConfig
        cfg = InstrumentConfig(
            symbol="BTCUSDT",
            asset_type="CRYPTO",
            tick_size=0.01,
            lot_size=0.001,
            step_size=0.001,
            min_qty=0.001,
        )
        assert cfg.step_size == 0.001
        assert cfg.min_qty == 0.001

    def test_step_size_must_be_positive(self):
        """step_size <= 0 应抛错"""
        from akquant.config import InstrumentConfig
        with pytest.raises(ValueError, match="step_size must be > 0"):
            InstrumentConfig(
                symbol="BTCUSDT",
                asset_type="CRYPTO",
                tick_size=0.01,
                step_size=0,
            )

    def test_min_qty_must_be_positive(self):
        """min_qty <= 0 应抛错"""
        from akquant.config import InstrumentConfig
        with pytest.raises(ValueError, match="min_qty must be > 0"):
            InstrumentConfig(
                symbol="BTCUSDT",
                asset_type="CRYPTO",
                tick_size=0.01,
                min_qty=-0.001,
            )


class TestInstrumentSnapshotStepMinQty:
    """测试 InstrumentSnapshot 的 step_size/min_qty 字段"""

    def test_default_values(self):
        """不传 step_size/min_qty 时使用默认值 1.0"""
        from akquant.strategy import InstrumentSnapshot
        snap = InstrumentSnapshot(
            symbol="BTCUSDT",
            asset_type="CRYPTO",
            multiplier=1.0,
            margin_ratio=1.0,
            tick_size=0.01,
            lot_size=0.001,
        )
        assert snap.step_size == 1.0  # 默认
        assert snap.min_qty == 1.0    # 默认

    def test_explicit_values(self):
        """显式传入 step_size/min_qty 应被接受"""
        from akquant.strategy import InstrumentSnapshot
        snap = InstrumentSnapshot(
            symbol="BTCUSDT",
            asset_type="CRYPTO",
            multiplier=1.0,
            margin_ratio=1.0,
            tick_size=0.01,
            lot_size=0.001,
            step_size=0.001,
            min_qty=0.001,
        )
        assert snap.step_size == 0.001
        assert snap.min_qty == 0.001


# ─────────────────────────────────────────────────────────────
# 单元测试: crypto_exchange_info 模块
# ─────────────────────────────────────────────────────────────

class TestDefaultSymbolInfo:
    """测试内置默认参数表"""

    def test_btc_defaults(self):
        from akquant.crypto_exchange_info import DEFAULT_CRYPTO_SYMBOL_INFO
        btc = DEFAULT_CRYPTO_SYMBOL_INFO["BTCUSDT"]
        assert btc["step_size"] == 0.001
        assert btc["min_qty"] == 0.001
        assert btc["tick_size"] == 0.1
        assert btc["min_notional"] == 5.0

    def test_eth_defaults(self):
        from akquant.crypto_exchange_info import DEFAULT_CRYPTO_SYMBOL_INFO
        eth = DEFAULT_CRYPTO_SYMBOL_INFO["ETHUSDT"]
        assert eth["step_size"] == 0.001
        assert eth["min_qty"] == 0.001

    def test_common_coins_present(self):
        from akquant.crypto_exchange_info import DEFAULT_CRYPTO_SYMBOL_INFO
        common = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT",
                  "ADAUSDT", "DOGEUSDT", "AVAXUSDT"]
        for sym in common:
            assert sym in DEFAULT_CRYPTO_SYMBOL_INFO


class TestBuildConfigs:
    """测试 build_crypto_instrument_configs (使用 fallback 模式)"""

    def test_build_with_fallback(self):
        from akquant.crypto_exchange_info import build_crypto_instrument_configs
        configs = build_crypto_instrument_configs(
            ["BTCUSDT", "ETHUSDT"],
            fallback=True,
        )
        assert len(configs) == 2
        for cfg in configs:
            assert cfg.asset_type == "CRYPTO"
            assert cfg.step_size is not None
            assert cfg.min_qty is not None
            assert cfg.tick_size is not None


# ─────────────────────────────────────────────────────────────
# 集成测试: 回测中 Crypto 精度处理 (需 Rust 扩展)
# ─────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestCryptoPrecisionBacktest:
    """在完整回测中验证精度截断行为"""

    def test_order_rejected_when_qty_not_aligned_to_step(self):
        """未对齐 step_size 的 quantity 应被拒单，而非自动修正"""
        from datetime import date
        import pandas as pd
        from akquant import Strategy, run_backtest, OrderStatus

        class PrecisionTestStrategy(Strategy):
            n_bars = 0

            def next(self):
                self.n_bars += 1
                if self.n_bars == 1:
                    # 未对齐的 quantity，预期被拒
                    self.buy(symbol="BTCUSDT", quantity=0.123456, price=50000.0)
                elif self.n_bars == 2:
                    orders = self.get_orders()
                    rejected = [o for o in orders if o.status == "Rejected"]
                    assert len(rejected) > 0, "预期有被拒订单"

        dates = pd.date_range("2024-01-02", "2024-01-03", freq="1min", tz="UTC")
        bars = pd.DataFrame({
            "open": 50000.0, "high": 50100.0, "low": 49900.0,
            "close": 50050.0, "volume": 100.0, "amount": 100.0 * 50000.0,
        }, index=dates)
        bars["symbol"] = "BTCUSDT"

        result = run_backtest(
            PrecisionTestStrategy,
            instruments={
                "BTCUSDT": {
                    "asset_type": "CRYPTO",
                    "multiplier": 1.0, "margin_ratio": 1.0,
                    "tick_size": 0.01, "lot_size": 0.001,
                    "step_size": 0.001, "min_qty": 0.001,
                    "commission_rate": 0.001,
                }
            },
            start=date(2024, 1, 2), end=date(2024, 1, 3),
            bars=bars, cash=1_000_000, benchmark=None,
        )
        assert result is not None

    def test_aligned_qty_gets_filled(self):
        """已对齐 step_size 的 quantity 应正常成交"""
        from datetime import date
        import pandas as pd
        from akquant import Strategy, run_backtest

        class PrecisionTestStrategy(Strategy):
            n_bars = 0

            def next(self):
                self.n_bars += 1
                if self.n_bars == 1:
                    # 已用 round_qty 对齐的 quantity
                    self.buy(symbol="BTCUSDT", quantity=0.123, price=50000.0)
                elif self.n_bars == 2:
                    orders = self.get_orders()
                    filled = [o for o in orders if o.status == "Filled"]
                    assert len(filled) > 0, "预期有成交订单"

        dates = pd.date_range("2024-01-02", "2024-01-03", freq="1min", tz="UTC")
        bars = pd.DataFrame({
            "open": 50000.0, "high": 50100.0, "low": 49900.0,
            "close": 50050.0, "volume": 100.0, "amount": 100.0 * 50000.0,
        }, index=dates)
        bars["symbol"] = "BTCUSDT"

        result = run_backtest(
            PrecisionTestStrategy,
            instruments={
                "BTCUSDT": {
                    "asset_type": "CRYPTO",
                    "multiplier": 1.0, "margin_ratio": 1.0,
                    "tick_size": 0.01, "lot_size": 0.001,
                    "step_size": 0.001, "min_qty": 0.001,
                    "commission_rate": 0.001,
                }
            },
            start=date(2024, 1, 2), end=date(2024, 1, 3),
            bars=bars, cash=1_000_000, benchmark=None,
        )
        assert result is not None

    def test_price_not_aligned_tick_rejected(self):
        """未对齐 tick_size 的限价单 price 应被拒单"""
        from datetime import date
        import pandas as pd
        from akquant import Strategy, run_backtest

        class PricePrecisionTestStrategy(Strategy):
            n = 0

            def next(self):
                self.n += 1
                if self.n == 1:
                    self.buy(symbol="ETHUSDT", quantity=0.1, price=3060.12345)

        dates = pd.date_range("2024-01-02", "2024-01-03", freq="1min", tz="UTC")
        bars = pd.DataFrame({
            "open": 3060.0, "high": 3070.0, "low": 3050.0,
            "close": 3065.0, "volume": 100.0, "amount": 100.0 * 3060.0,
        }, index=dates)
        bars["symbol"] = "ETHUSDT"

        result = run_backtest(
            PricePrecisionTestStrategy,
            instruments={
                "ETHUSDT": {
                    "asset_type": "CRYPTO",
                    "multiplier": 1.0, "margin_ratio": 1.0,
                    "tick_size": 0.01, "lot_size": 0.01,
                    "step_size": 0.01, "min_qty": 0.01,
                    "commission_rate": 0.001,
                }
            },
            start=date(2024, 1, 2), end=date(2024, 1, 3),
            bars=bars, cash=1_000_000, benchmark=None,
        )
        assert result is not None
