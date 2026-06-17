# 加密货币回测快速上手

## 数据准备

```python
from akquant.crypto_exchange_info import fetch_binance_klines

df = fetch_binance_klines("BTCUSDT", interval="5m", start_time="2026-06-01", end_time="2026-06-02")
```

返回字段：

| 列名 | 说明 |
|---|---|
| `timestamp` | UTC 时区 |
| `open`, `high`, `low`, `close`, `volume` | OHLCV |
| `trades` | 成交笔数 |
| `taker_buy_vol`, `taker_buy_quote_vol` | 主动买卖量 |
| `mark_price` | 标记价格，来自 Binance `markPriceKlines` |
| `funding_rate` | 资金费率，来自 Binance `fundingRate` 历史数据，按结算小时对齐 |
| `symbol` | 币种标识 |

---

## 精度配置

```python
from akquant.crypto_exchange_info import get_default_crypto_instruments

# 从 Binance API 拉取实时参数
instruments = get_default_crypto_instruments(["BTCUSDT"], online=True, margin_ratio=0.1)

# 或使用本地默认值（约 60 个主流币种）
instruments = get_default_crypto_instruments(["BTCUSDT"], margin_ratio=0.1)
```

返回格式：

```python
{
    "BTCUSDT": {
        "tick_size": 0.1,       # 最小价格变动
        "step_size": 0.001,     # 数量步长
        "min_qty": 0.001,       # 最小数量
        "min_notional": 50.0,   # 最小名义价值
    }
}
```

**精度规则：** 订单不满足以下条件时被拒绝：

1. **`min_qty`** — 下单数量不得小于此值
2. **`step_size`** — 下单数量必须为此值的整数倍
3. **`tick_size`** — 限价单价格必须为此值的整数倍
4. **`min_notional`** — 名义价值（价格 × 数量 × 乘数）不得小于此值

辅助函数：

```python
from akquant.strategy_trading_api import round_qty, round_price

aligned_qty = round_qty(0.123456, 0.001)     # → 0.123
aligned_price = round_price(50000.123, 0.01)  # → 50000.12
```

---

## 基本回测

```python
import akquant as aq
from akquant import Strategy, AssetType
from akquant.config import BacktestConfig, StrategyConfig
from akquant.crypto_exchange_info import fetch_binance_klines, get_default_crypto_instruments

df = fetch_binance_klines("BTCUSDT", interval="5m", start_time="2026-06-01", end_time="2026-06-02")

instruments = get_default_crypto_instruments(["BTCUSDT"], online=True, margin_ratio=0.1)

class MyStrategy(Strategy):
    def on_bar(self, bar):
        if self.get_position("BTCUSDT") == 0:
            self.buy("BTCUSDT", quantity=0.001)

config = BacktestConfig(
    strategy_config=StrategyConfig(
        commission_rate=0.0005,
        maker_commission_rate=0.0002,
    ),
)
result = aq.run_backtest(
    strategy=MyStrategy,
    symbols=["BTCUSDT"],
    data=df,
    config=config,
    asset_type=AssetType.Crypto,
    initial_cash=10000,
    margin_ratio=0.1,
    instruments=instruments,
)
```

**参数说明:**

| 参数 | 值 | 说明 |
|---|---|---|
| `asset_type` | `AssetType.Crypto` | 启用加密货币模式 |
| `commission_rate` | 0.0005（通过 `StrategyConfig`） | taker（吃单）费率 |
| `maker_commission_rate` | 0.0002（通过 `StrategyConfig`） | maker（挂单）费率，不传时默认等于 taker |
| `margin_ratio` | 0.1 | `1/杠杆倍数`，10x = 0.1 |
| `instruments` | 见上 | 币种精度参数，不传时精度检查不生效 |

---

## 完整示例

```python
from akquant.crypto_exchange_info import get_default_crypto_instruments
import akquant as aq
from akquant import Strategy, AssetType
from akquant.config import BacktestConfig, StrategyConfig
import pandas as pd

# 1. 数据
ts = pd.date_range("2026-06-01", periods=6, freq="5min", tz="UTC")
df = pd.DataFrame({
    "timestamp": ts, "symbol": "BTCUSDT",
    "open": [100, 110, 120, 130, 140, 150],
    "high": [105, 115, 125, 135, 145, 155],
    "low":  [95,  99,  115, 125, 135, 145],
    "close":[102, 112, 122, 132, 142, 152],
    "volume":[1000.0]*6,
})
df["mark_price"] = df["close"]
df["funding_rate"] = float("nan")

# 2. 精度配置
instruments = get_default_crypto_instruments(["BTCUSDT"], margin_ratio=1.0)

# 3. 策略
class MyStrategy(Strategy):
    n = 0
    def on_bar(self, bar):
        self.n += 1
        if self.n == 1:
            self.buy("BTCUSDT", quantity=1)               # Taker: 市价单
            self.buy("BTCUSDT", quantity=1, price=99)     # Maker: 限价单
        elif self.n == 4:
            self.sell("BTCUSDT", quantity=1)               # 平 1 单

# 4. 回测
result = aq.run_backtest(
    strategy=MyStrategy(),
    symbols=["BTCUSDT"],
    data=df,
    config=BacktestConfig(
        strategy_config=StrategyConfig(
            commission_rate=0.001,
            maker_commission_rate=0.0005,
        ),
    ),
    asset_type=AssetType.Crypto,
    initial_cash=100000,
    margin_ratio=1.0,
    instruments=instruments,
    show_progress=False,
)

# 5. 输出
orders = result.orders_df.sort_values("created_at").reset_index(drop=True)
print("=== 订单明细 ===")
for _, o in orders.iterrows():
    print(f"  {o['side']:5s} type={o['order_type']:11s} qty={o['quantity']:.2f} "
          f"filled={o['filled_quantity']:.2f} price={o['avg_price']:.2f} "
          f"comm={o['commission']:.4f} status={o['status']}")

print(f"\n=== 平仓交易 ===")
for t in result.trades:
    print(f"  {t.side:5s} entry={t.entry_price:.2f} exit={t.exit_price:.2f} "
          f"qty={t.quantity:.2f} pnl={t.pnl:.2f} net_pnl={t.net_pnl:.2f} "
          f"comm={t.commission:.2f} bars={t.duration_bars}")

m = result.metrics
print(f"\n=== 综合指标 ===")
print(f"  初始现金: {result.initial_cash:.2f}")
print(f"  最终现金: {float(result.cash_curve.iloc[-1]):.2f}")
print(f"  最终权益: {m.end_market_value:.2f}")
print(f"  总收益率: {m.total_return_pct:.2f}%")
print(f"  最大回撤: {m.max_drawdown_pct:.2f}%")
```

**运行输出:**

```
=== 订单明细 ===
  buy   type=market      qty=1.00 filled=1.00 price=110.00 comm=0.1100 status=filled
  buy   type=limit       qty=1.00 filled=1.00 price=99.00  comm=0.0495 status=filled
  sell  type=market      qty=1.00 filled=1.00 price=140.00 comm=0.1400 status=filled

=== 平仓交易 ===
  Long  entry=110.00 exit=140.00 qty=1.00 pnl=30.00 net_pnl=29.75 comm=0.25 bars=3

=== 综合指标 ===
  初始现金: 100000.00
  最终现金: 99930.70
  最终权益: 100082.70
  总收益率: 0.08%
  最大回撤: 0.00%
```

---

## 回测结果解读

### 订单明细字段

| 字段 | 说明 |
|---|---|
| `side` | 买卖方向：`buy` 或 `sell` |
| `order_type` | 订单类型：`market`（市价单）、`limit`（限价单） |
| `quantity` | 下单数量 |
| `filled_quantity` | 成交数量（部分成交时小于 quantity） |
| `avg_price` | 平均成交价 |
| `commission` | 该笔订单支付的佣金 |
| `status` | 订单状态：`filled`（全部成交）、`rejected`（被拒）、`cancelled`（撤销） |

### 订单成交过程

上例中 3 笔订单的成交过程：

1. **市价买单（Taker）** — bar 0 提交，bar 1 以 `open=110` 成交
   - 佣金 = 110 × 0.001 = 0.11（使用 taker 费率 0.1%）

2. **限价买单（Maker）** — bar 0 提交限价 99，bar 1 `low=99` 盘中触底成交
   - 不开空跳空（bar 1 `open=110 > 99`），盘中被动成交 → maker
   - 佣金 = 99 × 0.0005 = 0.0495（使用 maker 费率 0.05%）

3. **市价卖单（Taker）** — bar 3 提交，bar 4 以 `open=140` 成交
   - 佣金 = 140 × 0.001 = 0.14（使用 taker 费率 0.1%）

### 平仓交易字段

| 字段 | 说明 |
|---|---|
| `side` | 持仓方向：`Long`（多头）或 `Short`（空头） |
| `entry_price` | 开仓均价（FIFO：先开先平） |
| `exit_price` | 平仓成交价 |
| `qty` | 平仓数量 |
| `pnl` | 盈亏 = qty × (exit - entry) = 1 × (140 - 110) = 30 |
| `net_pnl` | 净盈亏 = pnl - 开仓佣金 - 平仓佣金 = 30 - 0.11 - 0.14 = 29.75 |
| `comm` | 该笔交易关联的佣金 |
| `bars` | 持仓 bar 数（从开仓到平仓） |

### 综合指标

| 指标 | 值 | 说明 |
|---|---|---|
| `initial_cash` | 100000.00 | 初始现金 |
| 最终现金 | 99930.70 | 平仓后账户可用现金 |
| `end_market_value` | 100082.70 | 最终权益 = 现金 + 未平仓市值（含 1 持仓 @ 当前价 152 + 未实现盈亏） |
| `total_return_pct` | 0.08% | 总收益率 = (权益 - 初始现金) / 初始现金 |
| `max_drawdown_pct` | 0.00% | 最大回撤（本例价格单边上涨，无回撤） |

### 现金流水追踪

```
初始:     100000.00
买 1 @ 110 (taker):  −110 − 0.11 =    99889.89
买 1 @ 99  (maker):  −99 − 0.0495 =   99790.84
卖 1 @ 140 (taker):  +140 − 0.14 =    99930.70  ← 最终现金
持仓市值:   +1 × 152 =                100082.70  ← 最终权益 (现金 + 持仓 × 当前价)
```

```python
config = BacktestConfig(
    strategy_config=StrategyConfig(
        commission_rate=0.0005,       # taker 费率
        maker_commission_rate=0.0002, # maker 费率
    ),
)
result = aq.run_backtest(config=config, ...)
```

| 订单类型 | 角色 | 使用的费率 |
|---|---|---|
| `Market`（市价单） | taker | `commission_rate` |
| `StopMarket` / `StopLimit` | taker | `commission_rate` |
| `Limit`（限价单） | maker | `maker_commission_rate` |
| `LimitMaker`（Post-Only） | maker | `maker_commission_rate` |

`maker_commission_rate` 不传时默认等于 `commission_rate`。

---

## 资金费率结算

`fetch_binance_klines` 已自动包含 `funding_rate` 列。数据中包含该列时结算自动启用。

- 结算时刻：**UTC 0:00 / 8:00 / 16:00**（每 8 小时）
- 公式：`payment = 持仓量 × 标记价格 × 资金费率`
- 正值：多头付空头；负值：空头付多头
- 同小时自动去重

```python
# 关闭资金费率
config = BacktestConfig(
    crypto=CryptoConfig(enable_funding=False),
)
```

---

## 强平检查

使用杠杆后自动检查强平条件。权益低于维持保证金时自动减仓。

- 使用 `mark_price` 计算未实现盈亏
- 维持保证金档位使用内置默认表（BTC/ETH/SOL 等 8 个主流币种）

```python
# 关闭强平
config = BacktestConfig(
    crypto=CryptoConfig(enable_liquidation=False),
)
```

---

## 订单成交时机

```python
# 默认：下一根 bar 以开盘价成交
result = aq.run_backtest(..., fill_policy={
    "price_basis": "open",
    "bar_offset": 1,
    "temporal": "same_cycle",
})

# 当前 bar 收盘成交
result = aq.run_backtest(..., fill_policy={
    "price_basis": "close",
    "bar_offset": 0,
    "temporal": "same_cycle",
})
```

| 模式 | 成交时机 | 成交价 |
|---|---|---|
| `open/1`（默认） | 下一根 bar 开盘 | next bar open |
| `close/0` | 当前 bar 收盘 | same bar close |
| `close/1` | 下一根 bar 收盘 | next bar close |

---

## 注意事项

1. **`asset_type` 必须设为 `AssetType.Crypto`**，否则使用默认股票模型
2. **不使用 `instruments` 时精度检查不生效**。建议使用 `get_default_crypto_instruments(..., online=True)`
3. **数字货币没有 `lot_size` 概念**，数量精度由 `step_size` 决定
4. **`min_notional` 设为 0 时不检查**，默认值为 0
5. **`maker_commission_rate` 仅通过 `BacktestConfig(StrategyConfig(...))` 设置**，不传时默认等于 `commission_rate`
6. **默认成交时机是下一根 bar 开盘**。如需当前 bar 收盘成交，设置 `fill_policy={"price_basis": "close", "bar_offset": 0}`
