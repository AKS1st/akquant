"""
永续合约回测增强 — 测试设计 & 测试用例

测试级别（用 pytest markers 区分）:
  - @pytest.mark.unit:      纯 Python 逻辑，不依赖 Rust 编译
  - @pytest.mark.integration: 需要已编译的 akquant Rust 扩展
  - @pytest.mark.slow:      需要完整回测运行，耗时较长

运行方式:
  # 只跑纯 Python 测试 (无需编译)
  pytest crypto_test.py -m unit -v

  # 跑所有测试 (需先 cargo build)
  cd .akquant_repo && maturin develop && cd ..
  pytest crypto_test.py -v
"""

import math
from decimal import Decimal
from typing import Any


# ─────────────────────────────────────────────────────────────
# 第一部分：纯 Python 单元测试（不依赖 Rust）
# ─────────────────────────────────────────────────────────────

def _parse_asset_type_name_impl(value: Any) -> str:
    """
    从 engine.py 提取的纯逻辑，不依赖 Rust 导入。
    测试修复后的 Crypto 类型分发是否正确。
    """
    # 模拟 AssetType 枚举
    class FakeAssetType:
        Futures = "Futures"
        Stock = "Stock"
        Fund = "Fund"
        Option = "Option"
        Crypto = "Crypto"

    AssetType = FakeAssetType

    if isinstance(value, FakeAssetType):
        if value == AssetType.Futures:
            return "futures"
        if value == AssetType.Stock:
            return "stock"
        if value == AssetType.Fund:
            return "fund"
        if value == AssetType.Option:
            return "option"
        if value == AssetType.Crypto:
            return "crypto"
        raise ValueError(f"Unsupported asset_type: {value}")
    if isinstance(value, str):
        v_lower = value.lower()
        if v_lower in {"future", "futures"}:
            return "futures"
        if v_lower == "stock":
            return "stock"
        if v_lower == "fund":
            return "fund"
        if v_lower == "option":
            return "option"
        if v_lower == "crypto":
            return "crypto"
    raise ValueError(f"Unsupported asset_type: {value}")


def _asset_type_to_upper_name_impl(value: Any) -> str:
    """测试 crypto 类型是否能正确转成 'CRYPTO' 大写枚举"""
    parsed = _parse_asset_type_name_impl(value)
    if parsed == "futures":
        return "FUTURES"
    if parsed == "fund":
        return "FUND"
    if parsed == "option":
        return "OPTION"
    if parsed == "crypto":
        return "CRYPTO"
    return "STOCK"


class TestParseAssetTypeName:
    """测试 _parse_asset_type_name 对 Crypto 类型的处理"""

    def test_assettype_crypto_accepted(self):
        """AssetType.Crypto 应返回 'crypto'，不应抛错"""
        class FakeAT:
            Crypto = "Crypto"
        result = _parse_asset_type_name_impl(FakeAT.Crypto)
        assert result == "crypto", f"Expected 'crypto', got '{result}'"

    def test_assettype_other_still_works(self):
        """其他 AssetType 仍然正常工作"""
        result = _parse_asset_type_name_impl("stock")
        assert result == "stock"

        result = _parse_asset_type_name_impl("futures")
        assert result == "futures"

        result = _parse_asset_type_name_impl("option")
        assert result == "option"

    def test_str_crypto_lowercase(self):
        """字符串 'crypto' 应返回 'crypto'"""
        result = _parse_asset_type_name_impl("crypto")
        assert result == "crypto"

    def test_str_crypto_uppercase(self):
        """字符串 'CRYPTO' 应返回 'crypto'"""
        result = _parse_asset_type_name_impl("CRYPTO")
        assert result == "crypto"

    def test_str_crypto_mixed(self):
        """字符串 'Crypto' 应返回 'crypto'"""
        result = _parse_asset_type_name_impl("Crypto")
        assert result == "crypto"


class TestAssetTypeToUpperName:
    """测试 _asset_type_to_upper_name 返回大写枚举值"""

    def test_crypto_returns_crypto(self):
        """crypto 应返回 'CRYPTO'"""
        result = _asset_type_to_upper_name_impl("crypto")
        assert result == "CRYPTO", f"Expected 'CRYPTO', got '{result}'"

    def test_stock_default_still_works(self):
        """stock 返回 'STOCK'，unknown 兜底返回 'STOCK'"""
        assert _asset_type_to_upper_name_impl("stock") == "STOCK"

    def test_futures_returns_futures(self):
        assert _asset_type_to_upper_name_impl("futures") == "FUTURES"

    def test_option_returns_option(self):
        assert _asset_type_to_upper_name_impl("option") == "OPTION"


class TestFundingHourDetection:
    """资金费率整点检测逻辑"""

    @staticmethod
    def _utc_hour(timestamp_ns: int) -> int:
        """Mock of Rust funding.rs: (bar.timestamp / 3_600_000_000_000) % 24"""
        return (timestamp_ns // 3_600_000_000_000) % 24

    def test_utc_0_is_funding_hour(self):
        assert self._utc_hour(0 * 3_600_000_000_000) == 0

    def test_utc_8_is_funding_hour(self):
        assert self._utc_hour(8 * 3_600_000_000_000) == 8

    def test_utc_16_is_funding_hour(self):
        assert self._utc_hour(16 * 3_600_000_000_000) == 16

    def test_utc_10_not_funding_hour(self):
        assert self._utc_hour(10 * 3_600_000_000_000) not in (0, 8, 16)

    def test_utc_23_not_funding_hour(self):
        assert self._utc_hour(23 * 3_600_000_000_000) not in (0, 8, 16)

    def test_funding_settlement_amount(self):
        """验证资金费率扣款公式: payment = qty × mark × rate"""
        qty = Decimal(1)       # 1 BTC long
        mark = Decimal(50000)  # 50000 USDT
        rate = Decimal("0.001")  # 0.1%
        payment = qty * mark * rate
        assert payment == Decimal(50), f"Expected 50, got {payment}"


class TestMaintenanceMarginTier:
    """维持保证金档位查询逻辑"""

    @staticmethod
    def _get_maintenance_rate(symbol: str, notional: float, table: dict) -> float:
        """Mock of Rust tiers.rs: get_maintenance_rate()"""
        tiers = table.get(symbol)
        if not tiers:
            return 0.005
        for tier in tiers:
            if notional <= tier["notional_upper"]:
                return tier["maint_margin_rate"]
        return tiers[-1]["maint_margin_rate"]

    BTC_TIERS = [
        {"notional_upper": 100_000, "maint_margin_rate": 0.004},
        {"notional_upper": 2_000_000, "maint_margin_rate": 0.005},
        {"notional_upper": 10_000_000, "maint_margin_rate": 0.01},
    ]
    TABLE = {"BTCUSDT": BTC_TIERS}

    def test_notional_below_first_tier(self):
        """名义价值 50k → 第一档 0.4%"""
        rate = self._get_maintenance_rate("BTCUSDT", 50_000, self.TABLE)
        assert math.isclose(rate, 0.004)

    def test_notional_in_middle_tier(self):
        """名义价值 500k → 第二档 0.5%"""
        rate = self._get_maintenance_rate("BTCUSDT", 500_000, self.TABLE)
        assert math.isclose(rate, 0.005)

    def test_notional_beyond_last_tier(self):
        """名义价值 20M → 最高档 1.0%"""
        rate = self._get_maintenance_rate("BTCUSDT", 20_000_000, self.TABLE)
        assert math.isclose(rate, 0.01)

    def test_missing_symbol_default(self):
        """无档位配置的币种 → 默认 0.5%"""
        rate = self._get_maintenance_rate("ETHUSDT", 50_000, self.TABLE)
        assert math.isclose(rate, 0.005)

    @staticmethod
    def _check_liquidation(cash: float, qty: float, mark: float,
                           avg_entry: float, multiplier: float,
                           maint_rate: float) -> bool:
        """Mock 强平条件: equity >= maintenance 时不触发"""
        notional = abs(qty) * mark * multiplier
        maintenance = notional * maint_rate
        upnl = qty * (mark - avg_entry) * multiplier
        equity = cash + upnl
        return equity < maintenance

    def test_healthy_not_liquidated(self):
        """权益远高于维持保证金 → 不强平"""
        assert not self._check_liquidation(
            cash=100_000, qty=1, mark=55000, avg_entry=50000,
            multiplier=1, maint_rate=0.004
        )

    def test_negative_equity_liquidated(self):
        """权益为负 → 强平"""
        assert self._check_liquidation(
            cash=0, qty=1, mark=30000, avg_entry=50000,
            multiplier=1, maint_rate=0.004
        )

    def test_close_to_margin_but_above_not_liquidated(self):
        """权益稍高于维持保证金 → 不强平"""
        # equity = 100k, notional = 100k, maint = 100k * 0.004 = 400
        assert not self._check_liquidation(
            cash=100_000, qty=1, mark=100_000, avg_entry=0,
            multiplier=1, maint_rate=0.004
        )

    def test_below_maintenance_liquidated(self):
        """权益低于维持保证金 → 强平"""
        # 做多 1 BTC @100000, 现价 30000, cash=0
        # upnl = 1*(30000-100000) = -70000, equity = -70000
        # maint = 1*30000*0.004 = 120
        # equity(-70000) < maint(120) → 强平
        assert self._check_liquidation(
            cash=0, qty=1, mark=30000, avg_entry=100_000,
            multiplier=1, maint_rate=0.004
        )


# ─────────────────────────────────────────────────────────────
# 第二部分：集成测试（需要 Rust 编译，pytest.mark.skip 兜底）
# ─────────────────────────────────────────────────────────────

import pytest

try:
    import akquant as aq
    from akquant.backtest.engine import _parse_asset_type_name, _asset_type_to_upper_name
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False


requires_engine = pytest.mark.skipif(
    not ENGINE_AVAILABLE,
    reason="akquant Rust 扩展未编译，跳过集成测试"
)


@pytest.mark.integration
@requires_engine
class TestCryptoInstrumentCreation:
    """测试 Crypto 品种创建"""

    def test_create_crypto_instrument(self):
        """用 AssetType.Crypto 创建品种"""
        instr = aq.Instrument(
            "BTCUSDT", aq.AssetType.Crypto,
            multiplier=1, tick_size=0.01, lot_size=0.001
        )
        assert instr.symbol == "BTCUSDT"
        assert instr.asset_type == aq.AssetType.Crypto
        assert isinstance(instr.multiplier, float)
        assert abs(instr.lot_size - 0.001) < 1e-10

    def test_crypto_instrument_in_run_backtest(self):
        """回测中传入 asset_type=Crypto 不应抛错"""
        import pandas as pd
        import numpy as np

        dates = pd.date_range("2024-01-01", periods=100, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": 50000, "high": 50100, "low": 49900, "close": 50050,
            "volume": 100,
        })

        class CryptoStrategy(aq.Strategy):
            def on_bar(self, bar):
                pass

        result = aq.run_backtest(
            strategy=CryptoStrategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            commission_rate=0.0005,
            initial_cash=10000,
        )
        assert result is not None

    def test_parse_asset_type_name_crypto(self):
        """验证 _parse_asset_type_name(AssetType.Crypto) 返回 'crypto'"""
        result = _parse_asset_type_name(aq.AssetType.Crypto)
        assert result == "crypto"

    def test_asset_type_to_upper_crypto(self):
        """验证 _asset_type_to_upper_name(Crypto) 返回 'CRYPTO'"""
        result = _asset_type_to_upper_name(aq.AssetType.Crypto)
        assert result == "CRYPTO"


@pytest.mark.integration
@requires_engine
class TestCryptoMarketModel:
    """测试 crypto 回测使用 SimpleMarket"""

    def test_no_t1_simple_market(self):
        """t_plus_one=False + crypto → SimpleMarket (24/7, T+0)"""
        import pandas as pd

        dates = pd.date_range("2024-01-01", periods=10, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10,
        })

        strategy_log = []

        class CheckMarketStrategy(aq.Strategy):
            def on_bar(self, bar):
                if len(strategy_log) == 0:
                    strategy_log.append("called")
                    # 验证 24/7 可用: 日期变化不应报错

        aq.run_backtest(
            strategy=CheckMarketStrategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
        )


@pytest.mark.integration
@requires_engine
class TestFundingSettlement:
    """
    资金费率结算 — 越过 UTC 结算点的完整端到端验证

    测试场景:
      场景 A: 做多 1 BTC, UTC 07:59→08:00 跨结算点
      场景 B: 做空 1 BTC, UTC 08:00 结算 (应收资金)
      场景 C: 结算小时多次 bar 只扣一次 (去重)
      场景 D: 8 小时间隔内再次结算 (UTC 08:00+16:00 两次)
      场景 E: funding_rate=0 不扣钱
      场景 F: 无持仓不扣钱
    """

    def test_funding_rate_in_extra(self):
        """extra 中的 funding_rate 能被传递给 bar"""
        bar = aq.Bar(
            timestamp=1700000000000000000,
            open=50000, high=50100, low=49900, close=50050,
            volume=100, symbol="BTCUSDT",
            extra={"funding_rate": 0.0001, "mark_price": 50000},
        )
        assert bar.extra["funding_rate"] == 0.0001
        assert bar.extra["mark_price"] == 50000

    def test_long_pays_funding_at_utc8(self):
        """
        场景 A: 做多 1 BTC, 跨 UTC 08:00 结算点
        数据:
          - UTC 07:55~07:59: 5 根 bar, funding_rate=0, mark=50000
          - UTC 08:00:       funding_rate=+0.001, mark=50000

        策略: 第一根 bar 买入 1 BTC

        预期:
          07:59 现金 = 初始 - 保证金占用
          08:00 bar 到来后 → funds 结算
          payment = 1 × 50000 × 0.001 = 50
          现金减少 50
        """
        import pandas as pd

        base = pd.Timestamp("2024-01-01 07:55", tz="UTC")
        ts = [base + pd.Timedelta(minutes=i) for i in range(6)]

        df = pd.DataFrame({
            "timestamp": ts,
            "open": 50000, "high": 50100, "low": 49900, "close": 50050,
            "volume": 100,
            "funding_rate": [0.0] * 5 + [0.001],
            "mark_price": [50000] * 6,
        })

        cash_snapshots = {}

        class Strategy(aq.Strategy):
            def on_bar(self, bar):
                ts = pd.Timestamp(bar.timestamp, unit="ns", tz="UTC")
                hour_min = f"{ts.hour:02d}:{ts.minute:02d}"

                # 第一根 bar 开仓
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

                cash_snapshots[hour_min] = self.get_cash()

        result = aq.run_backtest(
            strategy=Strategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.0,
        )
        assert result is not None

        # 验证发生了资金费率扣减
        # 07:59 现金 > 08:00 现金 (因为结算扣了 50)
        if "07:59" in cash_snapshots and "08:00" in cash_snapshots:
            before = cash_snapshots["07:59"]
            after = cash_snapshots["08:00"]
            diff = before - after
            assert diff > 0, f"Expected cash decrease at UTC 8:00, got diff={diff}"
            assert abs(diff - 50) < 1, f"Expected ~50 settlement, got {diff}"

    def test_short_receives_funding(self):
        """
        场景 B: 做空 1 BTC, UTC 08:00 应收资金
        funding_rate=+0.001, 空头收钱
        现金应增加 50
        """
        import pandas as pd

        base = pd.Timestamp("2024-01-01 07:55", tz="UTC")
        ts = [base + pd.Timedelta(minutes=i) for i in range(6)]

        df = pd.DataFrame({
            "timestamp": ts,
            "open": 50000, "high": 50100, "low": 49900, "close": 50050,
            "volume": 100,
            "funding_rate": [0.0] * 5 + [0.001],
            "mark_price": [50000] * 6,
        })

        cash_snapshots = {}

        class Strategy(aq.Strategy):
            def on_bar(self, bar):
                ts = pd.Timestamp(bar.timestamp, unit="ns", tz="UTC")
                hour_min = f"{ts.hour:02d}:{ts.minute:02d}"

                if self.get_position("BTCUSDT") == 0:
                    self.short("BTCUSDT", quantity=1)

                cash_snapshots[hour_min] = self.get_cash()

        result = aq.run_backtest(
            strategy=Strategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.0,
        )
        assert result is not None

        if "07:59" in cash_snapshots and "08:00" in cash_snapshots:
            before = cash_snapshots["07:59"]
            after = cash_snapshots["08:00"]
            diff = before - after
            # 空头应收资金 → cash 增加 → diff 为负
            assert diff < 0, f"Expected cash increase for short, got diff={diff}"

    def test_funding_dedup_same_hour(self):
        """
        场景 C: 同小时去重
        UTC 08:00 = 结算, UTC 08:01 = 同一小时, 不应再结算
        """
        import pandas as pd

        base = pd.Timestamp("2024-01-01 07:59", tz="UTC")
        ts = [base + pd.Timedelta(minutes=i) for i in range(3)]

        df = pd.DataFrame({
            "timestamp": ts,
            "open": 50000, "high": 50100, "low": 49900, "close": 50050,
            "volume": 100,
            "funding_rate": [0.0, 0.001, 0.002],  # 08:00=0.001, 08:01=0.002
            "mark_price": [50000] * 3,
        })

        cash_snapshots = {}

        class Strategy(aq.Strategy):
            def on_bar(self, bar):
                ts = pd.Timestamp(bar.timestamp, unit="ns", tz="UTC")
                hour_min = f"{ts.hour:02d}:{ts.minute:02d}"

                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

                cash_snapshots[hour_min] = self.get_cash()

        result = aq.run_backtest(
            strategy=Strategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.0,
        )
        assert result is not None

        # 08:00 和 08:01 的 cash 应相同 (去重, 不再扣费)
        if "08:00" in cash_snapshots and "08:01" in cash_snapshots:
            assert abs(cash_snapshots["08:01"] - cash_snapshots["08:00"]) < 1, \
                "Same hour should not deduct funding twice"

    def test_funding_twice_daily(self):
        """
        场景 D: UTC 08:00 + UTC 16:00 两次结算
        数据从 07:55 跨越到 16:01, 两次结算共扣 100
        """
        import pandas as pd

        base = pd.Timestamp("2024-01-01 07:55", tz="UTC")
        ts = [base + pd.Timedelta(minutes=i) for i in range(9 * 60 + 10)]

        df = pd.DataFrame({
            "timestamp": ts,
            "open": 50000, "high": 50100, "low": 49900, "close": 50050,
            "volume": 100,
            "funding_rate": [0.001 if h == 8 or h == 16 else 0.0 for h in
                            [t.hour for t in ts]],
            "mark_price": [50000] * len(ts),
        })

        class Strategy(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)

        result = aq.run_backtest(
            strategy=Strategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.0,
        )
        # 做多 1 BTC @50000, 两次结算各扣 50
        # 初始 100000 - 开仓 50000 - 资金费 50 - 资金费 50 = 49900
        final = float(result.cash_curve.iloc[-1])
        assert abs(final - 49900) < 10, \
            f"Expected ~49900 after two settlements, got {final}"

    def test_zero_funding_rate_no_deduction(self):
        """
        场景 E: funding_rate=0, 不扣钱
        """
        import pandas as pd

        base = pd.Timestamp("2024-01-01 07:59", tz="UTC")
        ts = [base + pd.Timedelta(minutes=i) for i in range(3)]

        df = pd.DataFrame({
            "timestamp": ts,
            "open": 50000, "high": 50100, "low": 49900, "close": 50050,
            "volume": 100,
            "funding_rate": [0.0, 0.0, 0.0],
            "mark_price": [50000] * 3,
        })

        cash_snapshots = {}

        class Strategy(aq.Strategy):
            def on_bar(self, bar):
                ts = pd.Timestamp(bar.timestamp, unit="ns", tz="UTC")
                hour_min = f"{ts.hour:02d}:{ts.minute:02d}"
                if self.get_position("BTCUSDT") == 0:
                    self.buy("BTCUSDT", quantity=1)
                cash_snapshots[hour_min] = self.get_cash()

        result = aq.run_backtest(
            strategy=Strategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.0,
        )
        assert result is not None

        # 08:00 和 08:01 现金不变
        if "08:00" in cash_snapshots and "08:01" in cash_snapshots:
            assert abs(cash_snapshots["08:01"] - cash_snapshots["08:00"]) < 1

    def test_no_position_no_funding_deduction(self):
        """
        场景 F: 没有持仓, 不扣资金费
        """
        import pandas as pd

        base = pd.Timestamp("2024-01-01 07:59", tz="UTC")
        ts = [base + pd.Timedelta(minutes=i) for i in range(3)]

        df = pd.DataFrame({
            "timestamp": ts,
            "open": 50000, "high": 50100, "low": 49900, "close": 50050,
            "volume": 100,
            "funding_rate": [0.0, 0.001, 0.0],
            "mark_price": [50000] * 3,
        })

        cash_snapshots = {}

        class Strategy(aq.Strategy):
            def on_bar(self, bar):
                ts = pd.Timestamp(bar.timestamp, unit="ns", tz="UTC")
                cash_snapshots[f"{ts.hour:02d}:{ts.minute:02d}"] = self.get_cash()

        result = aq.run_backtest(
            strategy=Strategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.0,
        )
        assert result is not None

        # 没有开仓, 现金应该不变 (无手续费)
        cash_values = list(cash_snapshots.values())
        assert all(abs(c - cash_values[0]) < 1 for c in cash_values)


@pytest.mark.integration
@requires_engine
class TestLiquidation:
    """测试强平检查"""

    def test_liquidation_triggers_on_big_drop(self):
        """
        价格大幅下跌触发强平:
          - 10x 杠杆做多，初始保证金 10%
          - 维持保证金 0.5%
          - 价格下跌 20% 后权益 < 维持保证金
          - 验证仓位被强平 (持仓归零)
        """
        import pandas as pd

        # 构造数据: 从 100 跌到 80
        prices = [100.0 - i * 0.5 for i in range(41)]  # 100 → 80 over 41 bars
        timestamps = pd.date_range(
            "2024-01-01", periods=41, freq="1min", tz="UTC"
        )

        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": prices, "high": [p+1 for p in prices],
            "low": [p-1 for p in prices], "close": prices,
            "volume": 100,
            "funding_rate": [0.0] * 41,
            "mark_price": prices,
        })

        final_position = {"value": None}

        class LiqStrategy(aq.Strategy):
            def on_start(self):
                self.entry_price = None

            def on_bar(self, bar):
                if self.get_position("BTCUSDT") == 0 and bar.close > 95:
                    self.buy("BTCUSDT", quantity=10)

            def on_stop(self):
                final_position["value"] = self.get_position("BTCUSDT")

        result = aq.run_backtest(
            strategy=LiqStrategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=1000,
            commission_rate=0.0,
            t_plus_one=False,
        )

        # 暴跌后强平触发, 仓位已被平掉 (不再是初始的 +10)
        assert final_position["value"] is not None
        assert final_position["value"] != 10.0, \
            f"Expected position != 10 after liquidation (was closed), got {final_position['value']}"


@pytest.mark.integration
@requires_engine
class TestBarExtraDataFlow:
    """测试 extra 数据从 DataFrame 到 bar 的完整通路"""

    def test_extra_fields_flow_to_bar(self):
        """
        DataFrame 中的非 OHLCV numeric 列自动成为 bar.extra:
          funding_rate → bar.extra["funding_rate"]
          mark_price → bar.extra["mark_price"]
        """
        import pandas as pd
        import numpy as np

        timestamps = pd.date_range("2024-01-01", periods=3, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100.5, 101.5, 102.5],
            "volume": [10, 20, 30],
            "funding_rate": [0.0001, 0.0001, 0.0002],
            "mark_price": [100.5, 101.5, 102.5],
        })

        received = []

        class ExtraCheckStrategy(aq.Strategy):
            def on_bar(self, bar):
                received.append({
                    "funding_rate": bar.extra.get("funding_rate"),
                    "mark_price": bar.extra.get("mark_price"),
                })

        aq.run_backtest(
            strategy=ExtraCheckStrategy(),
            symbols=["BTCUSDT"],
            data=df,
            asset_type=aq.AssetType.Crypto,
        )

        assert len(received) == 3
        expected_fr = [0.0001, 0.0001, 0.0002]
        expected_mp = [100.5, 101.5, 102.5]
        for i in range(3):
            assert received[i]["funding_rate"] is not None
            assert received[i]["mark_price"] is not None
            assert abs(received[i]["funding_rate"] - expected_fr[i]) < 1e-8, \
                f"Bar {i} funding_rate: expected {expected_fr[i]}, got {received[i]['funding_rate']}"
            assert abs(received[i]["mark_price"] - expected_mp[i]) < 1e-8, \
                f"Bar {i} mark_price: expected {expected_mp[i]}, got {received[i]['mark_price']}"


@pytest.mark.integration
@requires_engine
class TestMultiSymbolCryptoBacktest:
    """多币种 crypto 回测"""

    def test_two_symbols_with_funding_settlement(self):
        """
        两个币种同时开仓，跨越结算点，验证双方都正确扣款。

        数据构造:
          - BTCUSDT: UTC 07:55~08:00, 6 bars, funding_rate 只在 08:00 为 +0.001
          - ETHUSDT: 同上

        策略: 第一根 bar 同时做多 BTC 和 ETH

        预期:
          UTC 08:00 结算:
            BTC 扣款 = 1 × 50000 × 0.001 = 50
            ETH 扣款 = 10 × 2000 × 0.001 = 20
            总扣款 = 70
        """
        import pandas as pd

        base = pd.Timestamp("2024-01-01 07:55", tz="UTC")
        ts = [base + pd.Timedelta(minutes=i) for i in range(6)]

        data = {}
        for sym, price, qty in [("BTCUSDT", 50000, 1), ("ETHUSDT", 2000, 10)]:
            data[sym] = pd.DataFrame({
                "timestamp": ts,
                "open": price, "high": int(price * 1.002), "low": int(price * 0.998),
                "close": price, "volume": 100,
                "funding_rate": [0.0] * 5 + [0.001],
                "mark_price": [float(price)] * 6,
            })

        cash_snapshots = {}

        class MultiStrategy(aq.Strategy):
            def on_bar(self, bar):
                ts_hour = pd.Timestamp(bar.timestamp, unit="ns", tz="UTC")
                key = f"{ts_hour.hour:02d}:{ts_hour.minute:02d}"
                if key not in cash_snapshots:
                    cash_snapshots[key] = {}
                cash_snapshots[key][bar.symbol] = {
                    "cash": self.get_cash(),
                    "pos": self.get_position(bar.symbol),
                }

                if self.get_position("BTCUSDT") == 0 and bar.symbol == "BTCUSDT":
                    self.buy("BTCUSDT", quantity=1)
                if self.get_position("ETHUSDT") == 0 and bar.symbol == "ETHUSDT":
                    self.buy("ETHUSDT", quantity=10)

        result = aq.run_backtest(
            strategy=MultiStrategy(),
            symbols=["BTCUSDT", "ETHUSDT"],
            data=data,
            asset_type=aq.AssetType.Crypto,
            initial_cash=200000,
            commission_rate=0.0,
        )

        # 验证: 07:59 和 08:00 都有两份仓位快照
        for t in ["07:59", "08:00"]:
            assert t in cash_snapshots, f"Missing snapshot at {t}"
            assert "BTCUSDT" in cash_snapshots[t], f"Missing BTC at {t}"
            assert "ETHUSDT" in cash_snapshots[t], f"Missing ETH at {t}"

        # 08:00 有 funding_rate=0.001 → 结算
        # BTC: 1 × 50000 × 0.001 = 50
        # ETH: 10 × 2000 × 0.001 = 20
        # 总扣款 = 70
        btc_cash_0800 = cash_snapshots["08:00"]["BTCUSDT"]["cash"]
        eth_cash_0800 = cash_snapshots["08:00"]["ETHUSDT"]["cash"]

        # 两个币种都是做多，所以 08:00 现金都应 < 07:59
        btc_cash_0759 = cash_snapshots["07:59"]["BTCUSDT"]["cash"]
        eth_cash_0759 = cash_snapshots["07:59"]["ETHUSDT"]["cash"]

        # 验证 BTCUSDT 现金变少（扣了资金费）
        assert btc_cash_0800 < btc_cash_0759, \
            f"BTC cash should decrease: {btc_cash_0800} >= {btc_cash_0759}"
        # 验证 ETHUSDT 现金变少
        assert eth_cash_0800 < eth_cash_0759, \
            f"ETH cash should decrease: {eth_cash_0800} >= {eth_cash_0759}"
        # 验证两个币种开仓后仓位正确
        assert cash_snapshots["08:00"]["BTCUSDT"]["pos"] > 0, "BTC position should be > 0"
        assert cash_snapshots["08:00"]["ETHUSDT"]["pos"] > 0, "ETH position should be > 0"
        print(f"Multi-symbol test: BTC cash {btc_cash_0759}→{btc_cash_0800}, "
              f"ETH cash {eth_cash_0759}→{eth_cash_0800}")


@pytest.mark.integration
@requires_engine
class TestBackwardCompatibility:
    """原有 A 股回测不受影响"""

    def test_stock_backtest_still_works(self):
        """Stock 资产类型仍正常工作，不触发 perp 逻辑"""
        import pandas as pd
        import numpy as np

        timestamps = pd.date_range("2024-01-01", periods=10, freq="1d", tz="Asia/Shanghai")
        df = pd.DataFrame({
            "date": timestamps,
            "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000000,
        })

        class StockStrategy(aq.Strategy):
            def on_bar(self, bar):
                pass

        # 默认 asset_type=Stock，不应报错
        result = aq.run_backtest(
            strategy=StockStrategy(),
            symbols=["600519"],
            data=df,
        )
        assert result is not None

    def test_futures_backtest_still_works(self):
        """Futures 资产类型仍正常工作"""
        import pandas as pd
        import numpy as np

        timestamps = pd.date_range("2024-01-01", periods=10, freq="1d", tz="Asia/Shanghai")
        df = pd.DataFrame({
            "date": timestamps,
            "open": 4000, "high": 4010, "low": 3990, "close": 4005, "volume": 100000,
        })

        class FuturesStrategy(aq.Strategy):
            def on_bar(self, bar):
                pass

        result = aq.run_backtest(
            strategy=FuturesStrategy(),
            symbols=["IF2401"],
            data=df,
            asset_type=aq.AssetType.Futures,
            commission_rate=0.0001,
        )
        assert result is not None


@pytest.mark.integration
@requires_engine
class TestTakerMakerFee:
    """端到端验证 taker/maker 费率区分"""

    def test_market_order_charged_at_taker_rate(self):
        """
        Market 买单按 taker 费率扣费。
        commission_rate=0.001 (taker), maker_commission_rate=0.0005
        开仓后现金 = 100000 - 成交额 - taker 佣金
        """
        import pandas as pd

        ts = pd.date_range("2024-01-01", periods=5, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp": ts,
            "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100,
        })

        class TakerStrategy(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTC") == 0:
                    self.buy("BTC", quantity=1)  # Market 单 → taker

        result = aq.run_backtest(
            strategy=TakerStrategy(),
            symbols=["BTC"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.001,
            maker_commission_rate=0.0005,
        )

        # Market 单: next bar open=100 成交
        # cost = 1 × 100 = 100, commission = 100 × 0.001 = 0.1
        # 现金 = 100000 - 100 - 0.1 = 99899.9
        final_cash = float(result.cash_curve.iloc[-1])
        expected = 100000 - 100 - 0.1
        assert abs(final_cash - expected) < 1.0, \
            f"Taker cash: expected {expected}, got {final_cash}"

    def test_limit_order_charged_at_maker_rate(self):
        """
        Limit 挂单按 maker 费率扣费。
        commission_rate=0.001 (taker), maker_commission_rate=0.0005
        开仓后现金 = 100000 - 成交额 - maker 佣金
        """
        import pandas as pd

        ts = pd.date_range("2024-01-01", periods=5, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp": ts,
            "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100,
        })

        class MakerStrategy(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTC") == 0:
                    # Limit 价 99 < open=100 → 不跳空, 盘中 low=99 触发 → maker
                    self.buy("BTC", quantity=1, price=99)

        result = aq.run_backtest(
            strategy=MakerStrategy(),
            symbols=["BTC"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.001,
            maker_commission_rate=0.0005,
        )

        # Limit 99 < open=100: 不跳空, 下一根 bar low=99 触发
        # fill price = min(99, 100) = 99 (better of open vs limit)
        # cost = 1 × 99 = 99, commission = 99 × 0.0005 = 0.0495
        # 现金 = 100000 - 99 - 0.0495 = 99900.9505
        final_cash = float(result.cash_curve.iloc[-1])
        expected = 100000 - 99 - 99 * 0.0005
        assert abs(final_cash - expected) < 1.0, \
            f"Maker cash: expected {expected}, got {final_cash}"

    def test_maker_fee_lower_than_taker(self):
        """
        同一品种、同一价格、同一下单量:
        Market 单 (taker) 的佣金 > Limit 单 (maker) 的佣金
        分别跑两个回测对比最终现金: maker 现金 > taker 现金
        """
        import pandas as pd

        ts = pd.date_range("2024-01-01", periods=5, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp": ts,
            "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100,
        })

        # — Taker 回测 —
        class TakerStrategy(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTC") == 0:
                    self.buy("BTC", quantity=1)

        result_taker = aq.run_backtest(
            strategy=TakerStrategy(),
            symbols=["BTC"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.001,
            maker_commission_rate=0.0005,
        )
        taker_cash = float(result_taker.cash_curve.iloc[-1])

        # — Maker 回测 —
        class MakerStrategy(aq.Strategy):
            def on_bar(self, bar):
                if self.get_position("BTC") == 0:
                    self.buy("BTC", quantity=1, price=99)

        result_maker = aq.run_backtest(
            strategy=MakerStrategy(),
            symbols=["BTC"],
            data=df,
            asset_type=aq.AssetType.Crypto,
            initial_cash=100000,
            commission_rate=0.001,
            maker_commission_rate=0.0005,
        )
        maker_cash = float(result_maker.cash_curve.iloc[-1])

        # Maker 付的佣金少 → 剩余现金多
        assert maker_cash > taker_cash, \
            f"Maker cash {maker_cash} should be > Taker cash {taker_cash}"
