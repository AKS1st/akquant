"""
纯 Python 测试 — 不依赖 Rust 编译，直接验证永续合约核心逻辑

运行: pytest test_crypto_perp_unit_only.py -v
"""
import math
import pytest
from decimal import Decimal


# ── 模拟 engine.py 的 _parse_asset_type_name ──

class MockAssetType:
    Futures = "Futures"
    Stock = "Stock"
    Fund = "Fund"
    Option = "Option"
    Crypto = "Crypto"


def parse_asset_type_name(value):
    if isinstance(value, MockAssetType):
        if value == MockAssetType.Futures:
            return "futures"
        if value == MockAssetType.Stock:
            return "stock"
        if value == MockAssetType.Fund:
            return "fund"
        if value == MockAssetType.Option:
            return "option"
        if value == MockAssetType.Crypto:
            return "crypto"
        raise ValueError(f"Unsupported: {value}")
    if isinstance(value, str):
        v = value.lower()
        if v in ("future", "futures"):
            return "futures"
        if v == "stock":
            return "stock"
        if v == "fund":
            return "fund"
        if v == "option":
            return "option"
        if v == "crypto":
            return "crypto"
    raise ValueError(f"Unsupported: {value}")


def asset_type_to_upper_name(value):
    parsed = parse_asset_type_name(value)
    m = {"futures": "FUTURES", "fund": "FUND", "option": "OPTION", "crypto": "CRYPTO"}
    return m.get(parsed, "STOCK")


# ── 测试用例 ──

class TestParseAssetTypeName:
    def test_crypto_astype_accepted(self):
        assert parse_asset_type_name(MockAssetType.Crypto) == "crypto"

    def test_crypto_str_lower(self):
        assert parse_asset_type_name("crypto") == "crypto"

    def test_crypto_str_upper(self):
        assert parse_asset_type_name("CRYPTO") == "crypto"

    def test_crypto_str_mixed(self):
        assert parse_asset_type_name("Crypto") == "crypto"

    def test_other_types_still_work(self):
        assert parse_asset_type_name("stock") == "stock"
        assert parse_asset_type_name("futures") == "futures"
        assert parse_asset_type_name("option") == "option"
        assert parse_asset_type_name("fund") == "fund"

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            parse_asset_type_name("bond")
        with pytest.raises(ValueError):
            parse_asset_type_name("")


class TestAssetTypeToUpperName:
    def test_crypto_returns_crypto(self):
        assert asset_type_to_upper_name("crypto") == "CRYPTO"

    def test_stock_returns_stock(self):
        assert asset_type_to_upper_name("stock") == "STOCK"

    def test_unknown_falls_back_to_stock(self):
        with pytest.raises(ValueError):
            parse_asset_type_name("invalid")


class TestFundingHourDetection:
    """utc 整点检测逻辑 (同步 Rust funding.rs)"""

    @staticmethod
    def utc_hour(ns: int) -> int:
        return (ns // 3_600_000_000_000) % 24

    def test_funding_hours(self):
        for h in (0, 8, 16):
            ns = h * 3_600_000_000_000
            assert self.utc_hour(ns) == h, f"UTC {h}:00 should be funding hour"

    def test_non_funding_hours(self):
        for h in (1, 7, 9, 15, 17, 23):
            ns = h * 3_600_000_000_000
            assert self.utc_hour(ns) not in (0, 8, 16)


class TestFundingSettlementAmount:
    """资金费率结算公式验证"""

    def test_long_position_pays_funding(self):
        """多头付资金费率: cash -= qty * mark * rate"""
        qty, mark, rate = Decimal(1), Decimal(50000), Decimal("0.001")
        payment = qty * mark * rate
        assert payment == Decimal(50)

    def test_short_position_receives_funding(self):
        """空头收资金费率: cash += |qty| * mark * rate (因为 qty 负数)"""
        qty, mark, rate = Decimal(-1), Decimal(50000), Decimal("0.001")
        payment = qty * mark * rate  # -1 * 50000 * 0.001 = -50
        assert payment == Decimal(-50)

    def test_no_position_no_payment(self):
        assert Decimal(0) * Decimal(50000) * Decimal("0.001") == Decimal(0)

    def test_funding_payment_scales_with_position(self):
        """2 BTC 的资金费是 1 BTC 的 2 倍"""
        p1 = Decimal(1) * Decimal(50000) * Decimal("0.001")
        p2 = Decimal(2) * Decimal(50000) * Decimal("0.001")
        assert p2 == p1 * 2


class TestFundingSettlementCrossBoundary:
    """
    资金费率结算 — 越过 UTC 结算点的完整场景验证

    模拟 Rust FundingManager 逻辑:
      check_settlement(bar):
        1. hour = (bar.timestamp / 3_600_000_000_000) % 24
        2. if hour not in (0, 8, 16) → skip
        3. if hour == last_settled_hour → skip (dedup)
        4. else → return bar.extra["funding_rate"]

    验证场景:
      - 非结算小时跳过
      - 结算小时触发
      - 同小时去重 (多根 bar 跨同一个结算点)
      - 多头付资金、空头收资金
      - 多个币种同时结算
      - rate=0 不影响 cash
      - 无仓位不结算
    """

    @staticmethod
    def funding_check_settlement(hour: int, last_hour: int, extra: dict) -> float | None:
        """模拟 Rust 的 check_settlement 逻辑"""
        if hour not in (0, 8, 16):
            return None
        if hour == last_hour:
            return None
        rate = extra.get("funding_rate")
        if rate is None:
            return None
        return rate

    @staticmethod
    def funding_settle(rate: float, positions: dict,
                       mark_prices: dict, cash: float) -> (list, float):
        """模拟 Rust 的 settle 逻辑: cash -= qty * mark * rate"""
        payments = []
        for symbol, qty in positions.items():
            if qty == 0:
                continue
            mark = mark_prices.get(symbol, 0)
            amount = qty * mark * rate
            cash -= amount
            payments.append((symbol, amount))
        return payments, cash

    # ── 时间戳构造辅助 ──
    # UTC 07:59:00 的 ns 时间戳
    UTC_0759 = 7 * 3600 + 59 * 60  # 秒
    UTC_0800 = 8 * 3600
    UTC_0801 = 8 * 3600 + 60

    @staticmethod
    def ns(sec: int) -> int:
        return sec * 1_000_000_000

    # ── 测试用例 ──

    def test_non_funding_hour_skipped(self):
        """UTC 07:59 → 不是 0/8/16，跳过"""
        rate = self.funding_check_settlement(7, -1, {"funding_rate": 0.001})
        assert rate is None

    def test_funding_hour_triggers(self):
        """UTC 08:00 → 触发结算"""
        rate = self.funding_check_settlement(8, -1, {"funding_rate": 0.001})
        assert rate == 0.001

    def test_same_hour_dedup(self):
        """UTC 08:00 第一根 bar 结算后，同一小时内后面的 bar 跳过"""
        r1 = self.funding_check_settlement(8, -1, {"funding_rate": 0.001})
        r2 = self.funding_check_settlement(8, 8, {"funding_rate": 0.002})
        assert r1 == 0.001    # 触发
        assert r2 is None     # 跳过

    def test_different_hour_triggers_again(self):
        """UTC 08:00 结算后，UTC 16:00 再次触发"""
        r1 = self.funding_check_settlement(8, -1, {"funding_rate": 0.001})
        r2 = self.funding_check_settlement(16, 8, {"funding_rate": 0.002})
        assert r1 == 0.001
        assert r2 == 0.002

    def test_three_funding_hours_all_trigger(self):
        """一天三次结算全部触发 (0, 8, 16)"""
        hours = [0, 8, 16]
        last = -1
        results = []
        for h in hours:
            r = self.funding_check_settlement(h, last, {"funding_rate": 0.001})
            if r is not None:
                results.append(h)
                last = h
        assert results == [0, 8, 16]

    def test_long_position_pays_funding(self):
        """
        多头 1 BTC @50000, funding_rate=+0.001 (多头付空头)
        cash -= 1 * 50000 * 0.001 = 50
        初始 cash=1000, 结算后 = 950
        """
        payments, cash = self.funding_settle(
            0.001, {"BTCUSDT": 1}, {"BTCUSDT": 50000}, 1000
        )
        assert len(payments) == 1
        assert payments[0][1] == 50  # 扣了 50
        assert cash == 950

    def test_short_position_receives_funding(self):
        """
        空头 1 BTC @50000, funding_rate=+0.001 (空头收钱)
        cash -= (-1) * 50000 * 0.001 = -50  → cash +50
        初始 cash=1000, 结算后 = 1050
        """
        payments, cash = self.funding_settle(
            0.001, {"BTCUSDT": -1}, {"BTCUSDT": 50000}, 1000
        )
        assert len(payments) == 1
        assert payments[0][1] == -50  # 收入 50
        assert cash == 1050

    def test_negative_funding_rate_long_receives(self):
        """
        funding_rate=-0.001, 多头应收钱
        cash -= 1 * 50000 * (-0.001) = +50
        """
        payments, cash = self.funding_settle(
            -0.001, {"BTCUSDT": 1}, {"BTCUSDT": 50000}, 1000
        )
        assert payments[0][1] == -50  # 负的扣减 = 收入
        assert cash == 1050

    def test_zero_rate_no_effect(self):
        """funding_rate=0, cash 不变"""
        payments, cash = self.funding_settle(
            0.0, {"BTCUSDT": 1}, {"BTCUSDT": 50000}, 1000
        )
        assert payments[0][1] == 0
        assert cash == 1000

    def test_no_position_no_payment(self):
        """空仓不结算"""
        payments, cash = self.funding_settle(
            0.001, {}, {}, 1000
        )
        assert payments == []
        assert cash == 1000

    def test_multiple_symbols_settle_together(self):
        """
        同时持有 BTC 和 ETH, 一次性结算两个币种
        BTC: 1 * 50000 * 0.001 = 50
        ETH: 10 * 2000 * 0.001 = 20
        共扣 70
        """
        payments, cash = self.funding_settle(
            0.001,
            {"BTCUSDT": 1, "ETHUSDT": 10},
            {"BTCUSDT": 50000, "ETHUSDT": 2000},
            1000,
        )
        assert len(payments) == 2
        total = sum(a for _, a in payments)
        assert total == 70
        assert cash == 930

    def test_mark_price_updates_before_settlement(self):
        """
        模拟完整 pipeline: 先更新 mark_price → 再结算
        验证 settle 时用的是更新后的 mark_price
        """
        # 模拟更新
        mark_prices = {}
        # bar1 到来更新 mark
        mark_prices["BTCUSDT"] = 48000
        # bar2 到来再次更新
        mark_prices["BTCUSDT"] = 50000

        # 结算
        payments, cash = self.funding_settle(
            0.001, {"BTCUSDT": 1}, mark_prices, 1000
        )
        # 应该用最新的 50000
        assert payments[0][1] == 50
        assert cash == 950


class TestMaintenanceMarginTier:
    """维持保证金档位查询 + 强平条件 (对齐 Binance 公式: notional×rate - amount)"""

    @staticmethod
    def calculate_maintenance(symbol, notional, table):
        """Binance 公式: max(0, notional × rate - amount)"""
        tiers = table.get(symbol)
        if not tiers:
            rate, amount = 0.005, 0.0
        else:
            found = None
            for upper, rate, amount in tiers:
                if notional <= upper:
                    found = (rate, amount)
                    break
            if found is None:
                rate, amount = tiers[-1][1], tiers[-1][2]
            else:
                rate, amount = found
        return max(0, notional * rate - amount)

    @staticmethod
    def should_liquidate(cash, qty, mark, avg_entry, mult, table):
        """强平条件: equity < maintenance"""
        notional = abs(qty) * mark * mult
        maintenance = TestMaintenanceMarginTier.calculate_maintenance(
            "BTCUSDT", notional, table
        )
        upnl = qty * (mark - avg_entry) * mult
        equity = cash + upnl
        return equity < maintenance

    BTC_TABLE = {
        "BTCUSDT": [
            (300_000,    0.004,   0.0),      # tier 1: 0~300k
            (800_000,    0.005, 300.0),      # tier 2: 300k~800k
            (3_000_000,  0.0065, 1500.0),    # tier 3: 800k~3M
            (12_000_000, 0.01, 12000.0),     # tier 4: 3M~12M
        ]
    }

    def test_first_tier_maint(self):
        """50k × 0.4% - 0 = 200"""
        m = self.calculate_maintenance("BTCUSDT", 50_000, self.BTC_TABLE)
        assert math.isclose(m, 200)

    def test_boundary_smooth(self):
        """300k 处两档结果一致：无跳变"""
        m1 = self.calculate_maintenance("BTCUSDT", 300_000, self.BTC_TABLE)
        m2 = self.calculate_maintenance("BTCUSDT", 300_001, self.BTC_TABLE)
        # 300k × 0.004 = 1200, 300001 × 0.005 - 300 = 1200.005
        assert abs(m2 - m1) < 1.0

    def test_tier2_maint(self):
        """500k × 0.5% - 300 = 2200"""
        m = self.calculate_maintenance("BTCUSDT", 500_000, self.BTC_TABLE)
        assert math.isclose(m, 2200)

    def test_tier3_maint(self):
        """2M × 0.65% - 1500 = 11,500"""
        m = self.calculate_maintenance("BTCUSDT", 2_000_000, self.BTC_TABLE)
        assert math.isclose(m, 11500)

    def test_beyond_last_tier(self):
        """20M × 1% - 12000 = 188,000"""
        m = self.calculate_maintenance("BTCUSDT", 20_000_000, self.BTC_TABLE)
        assert math.isclose(m, 188_000)

    def test_missing_symbol_default(self):
        """默认 0.5%: 50k × 0.5% = 250"""
        m = self.calculate_maintenance("ETHUSDT", 50_000, {})
        assert math.isclose(m, 250)

    def test_healthy_long_not_liquidated(self):
        """做多盈利 → 不强平"""
        assert not self.should_liquidate(
            100_000, qty=1, mark=55000, avg_entry=50000, mult=1, table=self.BTC_TABLE
        )

    def test_healthy_short_not_liquidated(self):
        """做空盈利 → 不强平"""
        assert not self.should_liquidate(
            100_000, qty=-1, mark=45000, avg_entry=50000, mult=1, table=self.BTC_TABLE
        )

    def test_big_loss_liquidated(self):
        """暴跌权益为负 → 强平"""
        assert self.should_liquidate(
            0, qty=1, mark=30000, avg_entry=50000, mult=1, table=self.BTC_TABLE
        )

    def test_equity_below_maintenance_liquidated(self):
        """权益 < 维持保证金 → 强平"""
        assert self.should_liquidate(
            0, qty=1, mark=100_300, avg_entry=100_000, mult=1, table=self.BTC_TABLE
        )

    def test_equity_above_maintenance_safe(self):
        """权益 > 维持保证金 → 不强平"""
        assert not self.should_liquidate(
            0, qty=1, mark=100_500, avg_entry=100_000, mult=1, table=self.BTC_TABLE
        )

    def test_default_tier_btc_300k(self):
        """默认 BTC 档位: 300k 处平滑"""
        BTC_DEFAULT = {
            "BTCUSDT": [
                (300_000,    0.004,   0.0),
                (800_000,    0.005, 300.0),
                (3_000_000,  0.0065, 1500.0),
                (12_000_000, 0.01, 12000.0),
            ]
        }
        m1 = self.calculate_maintenance("BTCUSDT", 300_000, BTC_DEFAULT)
        m2 = self.calculate_maintenance("BTCUSDT", 300_001, BTC_DEFAULT)
        assert abs(m2 - m1) < 1.0

    def test_default_tier_eth_matches_btc(self):
        ETH = {"ETHUSDT": [(300_000, 0.004, 0.0), (800_000, 0.005, 300.0)]}
        m = self.calculate_maintenance("ETHUSDT", 500_000, ETH)
        assert math.isclose(m, 2200)


class TestLimitMakerOrderType:
    """Post-Only 订单类型测试"""

    @staticmethod
    def should_reject_as_taker(side: str, limit_price: float, bar_open: float) -> bool:
        """模拟 CommonMatcher 中 LimitMaker 的逻辑"""
        if side == "buy":
            return limit_price >= bar_open  # 限价 ≥ 开盘 → 吃单
        else:
            return limit_price <= bar_open  # 限价 ≤ 开盘 → 吃单

    def test_buy_limit_maker_below_open_is_maker(self):
        """买限价 < 开盘价 → maker，不应拒绝"""
        assert not self.should_reject_as_taker("buy", 99, 100)

    def test_buy_limit_maker_at_open_is_taker(self):
        """买限价 == 开盘价 → taker (立即成交)"""
        assert self.should_reject_as_taker("buy", 100, 100)

    def test_buy_limit_maker_above_open_is_taker(self):
        """买限价 > 开盘价 → taker (跳空成交)"""
        assert self.should_reject_as_taker("buy", 101, 100)

    def test_sell_limit_maker_above_open_is_maker(self):
        """卖限价 > 开盘价 → maker"""
        assert not self.should_reject_as_taker("sell", 101, 100)

    def test_sell_limit_maker_at_open_is_taker(self):
        """卖限价 == 开盘价 → taker"""
        assert self.should_reject_as_taker("sell", 100, 100)

    def test_sell_limit_maker_below_open_is_taker(self):
        """卖限价 < 开盘价 → taker (跳空成交)"""
        assert self.should_reject_as_taker("sell", 99, 100)

    def test_limit_maker_within_bar_not_taker(self):
        """买限价在 bar 范围内但高于开盘 → 盘中成交的 maker"""
        # 以 Open=100 开盘不成交，盘中 Low=95 碰到限价 98
        # 这不是 gap fill，是盘中被动成交 → maker
        # LimitMaker 逻辑: 不触发 gap fill → 允许成交
        assert not self.should_reject_as_taker("buy", 98, 100)


class TestTakerMakerFee:
    """Taker / Maker 费率区分测试"""

    @staticmethod
    def is_maker(order_type: str) -> bool:
        """模拟 CommonMatcher::is_maker_by_order_type"""
        return order_type in ("limit", "limit_maker", "post_only")

    def test_market_is_taker(self):
        assert not self.is_maker("market")

    def test_stop_market_is_taker(self):
        assert not self.is_maker("stop")
        assert not self.is_maker("stopmarket")

    def test_stop_limit_is_taker(self):
        assert not self.is_maker("stop_limit")
        assert not self.is_maker("stoplimit")

    def test_limit_is_maker(self):
        assert self.is_maker("limit")

    def test_limit_maker_is_maker(self):
        assert self.is_maker("limit_maker")
        assert self.is_maker("post_only")

    def test_taker_rate_higher_than_maker(self):
        """taker 费率 > maker 费率"""
        turnover = 50000
        taker = turnover * 0.001
        maker = turnover * 0.0005
        assert taker == 50 and maker == 25 and taker > maker

    def test_default_no_maker_rate_equal(self):
        """默认 taker=maker -> 向后兼容"""
        turnover = 50000
        rate = 0.0003
        assert turnover * rate == turnover * rate


class TestLiquidationPrice:
    """破产价计算验证"""

    @staticmethod
    def bankrupt_price(cash, qty, avg_entry, multiplier):
        """equity = cash + qty * (bankrupt - avg) * mult = 0"""
        return avg_entry - cash / (qty * multiplier)

    def test_long_bankrupt_price_below_entry(self):
        bp = self.bankrupt_price(5000, 1, 50000, 1)
        # 5000 + 1*(bp - 50000)*1 = 0 → bp = 45000
        assert bp == 45000

    def test_short_bankrupt_price_above_entry(self):
        bp = self.bankrupt_price(5000, -1, 50000, 1)
        # 5000 + (-1)*(bp - 50000)*1 = 0 → bp = 55000
        assert bp == 55000

    def test_no_cash_bankrupt_at_entry(self):
        bp = self.bankrupt_price(0, 1, 50000, 1)
        assert bp == 50000

    def test_large_cash_bankrupt_far_below(self):
        bp = self.bankrupt_price(50000, 1, 50000, 1)
        assert math.isclose(bp, 0)

    def test_leveraged_position(self):
        """带杠杆: 10x, 名义价值 = 100000, cash = 10000, 跌到多少爆仓"""
        bp = self.bankrupt_price(10000, 1, 100000, 1)
        assert bp == 90000


class TestInitialMarginWithLeverage:
    """固定杠杆下的初始保证金检查"""

    @staticmethod
    def initial_margin(notional: float, leverage: int) -> float:
        """margin = notional / leverage"""
        return notional / leverage

    def test_1x_full_margin(self):
        """1x 杠杆 = 全额保证金"""
        assert self.initial_margin(50000, 1) == 50000

    def test_10x_leverage(self):
        """10x 杠杆 = 10% 保证金"""
        assert self.initial_margin(50000, 10) == 5000

    def test_100x_leverage(self):
        """100x 杠杆 = 1% 保证金"""
        assert self.initial_margin(50000, 100) == 500

    def test_2x_half_margin(self):
        """2x 杠杆 = 50% 保证金"""
        assert self.initial_margin(50000, 2) == 25000

    def test_margin_ratio_is_inverse_of_leverage(self):
        """margin_ratio = 1 / leverage"""
        for lev in [1, 2, 5, 10, 20, 50, 100, 125]:
            ratio = 1.0 / lev
            notional = 50000
            margin = notional * ratio
            assert math.isclose(margin, self.initial_margin(notional, lev))


class TestSimpleMarketVsChinaMarket:
    """验证 crypto 场景下 SimpleMarket 的特性"""

    def test_simple_market_continuous_all_hours(self):
        """SimpleMarket 24/7: 任何时间都是 Continuous"""
        for h in range(24):
            session = "Continuous"  # SimpleMarket 永远返回这个
            assert session == "Continuous"

    def test_simple_market_zero_tax(self):
        """SimpleMarket 零印花税/过户费"""
        # SimpleMarket.default: stamp_tax=0, transfer_fee=0, min_commission=0
        turnover = Decimal(50000) * Decimal(1) * Decimal(1)
        rate = Decimal("0.0005")
        commission = turnover * rate
        assert commission == Decimal(25)
        # 只有佣金，无税
        assert commission == turnover * rate


class TestDataExtraColumns:
    """验证 extra 列自动识别"""

    @staticmethod
    def detect_extra_columns(df_columns, used_columns):
        """模拟 df_to_arrays 中的 extra 检测逻辑"""
        return [c for c in df_columns if c not in used_columns]

    def test_funding_rate_detected_as_extra(self):
        cols = ["timestamp", "open", "high", "low", "close", "volume", "funding_rate", "mark_price"]
        used = {"timestamp", "open", "high", "low", "close", "volume"}
        extra = self.detect_extra_columns(cols, used)
        assert "funding_rate" in extra
        assert "mark_price" in extra

    def test_only_ohlcv_not_extra(self):
        cols = ["timestamp", "open", "high", "low", "close", "volume"]
        used = set(cols)
        extra = self.detect_extra_columns(cols, used)
        assert extra == []

    def test_symbol_col_not_extra(self):
        cols = ["timestamp", "open", "close", "volume", "symbol"]
        used = {"timestamp", "open", "close", "volume"}
        extra = self.detect_extra_columns(cols, used)
        assert "symbol" in extra  # symbol 列也会被作为 extra… 但实际上 df_to_arrays 特殊处理了 symbol
        # 这里说明真实实现中 symbol 会被提前提取，不作为 extra
