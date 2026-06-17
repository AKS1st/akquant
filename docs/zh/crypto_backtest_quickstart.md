# 加密货币回测快速上手

## 数据准备

使用 `fetch_binance_klines` 直接下载 Binance USDⓈ-M 永续合约的真实行情。
不传时间范围时默认下载 **2026-06-15 全天 (UTC)**，每次运行结果一致：

```python
from akquant.crypto_exchange_info import fetch_binance_klines

df = fetch_binance_klines("BTCUSDT", interval="5m")
# 默认 2026-06-15 全天 289 根 5 分钟 bar，结果可复现
```

返回值已包含回测所需全部字段：

| 列名 | 说明 |
|---|---|
| `timestamp` | UTC 时区 |
| `open`, `high`, `low`, `close`, `volume` | OHLCV |
| `trades` | 成交笔数 |
| `taker_buy_vol`, `taker_buy_quote_vol` | 主动买卖量 |
| `mark_price` | 标记价格，来自 Binance `markPriceKlines` |
| `funding_rate` | 资金费率，来自 Binance `fundingRate` 历史数据，按结算小时对齐 |
| `symbol` | 币种标识 |

> `mark_price` 用于强平检查和资金费率结算。`funding_rate` 用于 UTC 0/8/16
> 的资金费率定时结算。两者均自动从 Binance API 拉取，无需手动构造。

指定时间范围：

```python
df = fetch_binance_klines("BTCUSDT", start_time="2026-06-01", end_time="2026-06-02")
```

---

## 精度配置

使用 `get_default_crypto_instruments` 获取币种的精度参数：

```python
from akquant.crypto_exchange_info import get_default_crypto_instruments

# 从 Binance API 拉取实时参数（推荐）
instruments = get_default_crypto_instruments(["BTCUSDT"], online=True, margin_ratio=0.1)

# 或使用本地默认值（离线，约 60 个主流币种）
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

### 精度规则

订单进入引擎后依次检查，不满足则拒绝：

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
from akquant.config import BacktestConfig, StrategyConfig
from akquant.crypto_exchange_info import fetch_binance_klines, get_default_crypto_instruments

# 1. 数据：Binance 真实行情，结果可复现
df = fetch_binance_klines("BTCUSDT", interval="5m")

# 2. 精度配置
instruments = get_default_crypto_instruments(["BTCUSDT"], online=True, margin_ratio=0.1)

# 3. 策略
class MyStrategy(Strategy):
    def on_bar(self, bar):
        if self.get_position("BTCUSDT") == 0:
            self.buy("BTCUSDT", quantity=0.001)

# 4. 回测
config = BacktestConfig(
    strategy_config=StrategyConfig(
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
    commission_rate=0.0005,
    margin_ratio=0.1,
    instruments=instruments,
)
```

### 查看结果

```python
# 订单明细
print(result.orders_df)

# 成交明细
for t in result.executions:
    print(f"{t.side} {t.quantity} @ {t.price}")

# 已平仓交易
for t in result.trades:
    print(f"{t.symbol} entry={t.entry_price:.2f} exit={t.exit_price:.2f} "
          f"pnl={t.pnl:.2f} net_pnl={t.net_pnl:.2f}")

# 现金曲线 / 权益曲线 / 保证金曲线
result.cash_curve
result.equity_curve
result.margin_curve

# 综合指标
print(result.metrics)
```

---

## 完整示例与期望输出

以下示例使用固定历史数据，每次运行输出一致：

```python
from akquant.crypto_exchange_info import fetch_binance_klines, get_default_crypto_instruments
import akquant as aq
from akquant import Strategy, AssetType
from akquant.config import BacktestConfig, StrategyConfig

# 1. 数据（默认 2026-06-15 全天，结果可复现）
df = fetch_binance_klines("BTCUSDT", interval="5m")
print(f"数据: {len(df)} 根 bar, {df['timestamp'].iloc[0].date()} ~ {df['timestamp'].iloc[-1].date()}")

# 2. 精度配置
instruments = get_default_crypto_instruments(["BTCUSDT"], online=True, margin_ratio=0.1)

# 3. 策略
class MyStrategy(Strategy):
    def on_bar(self, bar):
        if self.get_position("BTCUSDT") == 0:
            self.buy("BTCUSDT", quantity=0.001)

# 4. 回测
config = BacktestConfig(
    strategy_config=StrategyConfig(maker_commission_rate=0.0002),
)

result = aq.run_backtest(
    strategy=MyStrategy(),
    symbols=["BTCUSDT"],
    data=df,
    config=config,
    asset_type=AssetType.Crypto,
    initial_cash=10000,
    commission_rate=0.0005,
    margin_ratio=0.1,
    instruments=instruments,
    show_progress=False,
)

# 5. 输出
orders = result.orders_df
print(f"\n订单 ({len(orders)} 笔):")
for _, o in orders.iterrows():
    print(f"  {o['side']:5s} qty={o['quantity']:.4f} filled={o['filled_quantity']:.4f} "
          f"price={o['avg_price']:.2f} comm={o['commission']:.4f} {o['status']}")

trades = result.trades
if trades:
    print(f"\n平仓交易 ({len(trades)} 笔):")
    for t in trades:
        print(f"  {t.side:5s} entry={t.entry_price:.2f} exit={t.exit_price:.2f} "
              f"pnl={t.pnl:.2f} net_pnl={t.net_pnl:.2f}")
else:
    print("\n无平仓交易（策略未平仓）")

print(f"\n最终现金: {float(result.cash_curve.iloc[-1]):.2f}")
print(f"收益率:   {result.metrics.total_return_pct:.2f}%")
print(f"夏普比:   {result.metrics.sharpe_ratio:.3f}")
print(f"最大回撤: {result.metrics.max_drawdown_pct:.2f}%")
```

**期望输出（每次运行一致）:**

```
数据: 289 根 bar, 2026-06-15 ~ 2026-06-16

订单 (1 笔):
   buy  qty=0.0010 filled=0.0010 price=65633.80 comm=0.0328 filled

无平仓交易（策略未平仓）

最终现金: 9934.34
收益率:   0.01%
夏普比:   0.000
最大回撤: 0.01%
```

> 数据来自 Binance 固定历史日期，结果可复现。
> 实际资金费率约 0.001~0.006%，对现金影响极小。
> 如果网络不通或 Binance API 超时，请检查网络后重试。

---

## 手续费

所有币种共享同一套 taker/maker 费率，实际值由交易所账户 VIP 等级决定。

```python
result = aq.run_backtest(
    ...,
    commission_rate=0.0005,         # taker 费率
    maker_commission_rate=0.0002,   # maker 费率
)
```

| 订单类型 | 角色 | 使用的费率 |
|---|---|---|
| `Market`（市价单） | taker | `commission_rate` |
| `StopMarket` / `StopLimit` | taker | `commission_rate` |
| `Limit`（限价单） | maker | `maker_commission_rate` |
| `LimitMaker`（Post-Only） | maker | `maker_commission_rate` |

### 逐订单费率

```python
self.buy("BTCUSDT", quantity=1, commission={"type": "fixed", "value": 5.0})
self.buy("BTCUSDT", quantity=1, commission={"type": "percent", "value": 0.001})
```

---

## 资金费率结算

`fetch_binance_klines` 已自动包含 `funding_rate` 列。数据中包含该列时结算自动启用。

- 结算时刻：**UTC 0:00 / 8:00 / 16:00**（每 8 小时）
- 公式：`payment = 持仓量 × 标记价格 × 资金费率`
- 正值：多头付空头；负值：空头付多头
- 同小时自动去重

### 关闭资金费率

```python
from akquant.config import BacktestConfig, CryptoConfig

config = BacktestConfig(
    crypto=CryptoConfig(enable_funding=False),
)
result = aq.run_backtest(config=config, ...)
```

---

## 强平检查

使用杠杆后自动检查强平条件。权益低于维持保证金时自动减仓。

- 使用 `mark_price` 计算未实现盈亏，`fetch_binance_klines` 已自动包含该列
- 维持保证金档位使用内置默认表（BTC/ETH/SOL 等 8 个主流币种）

```python
result = aq.run_backtest(..., margin_ratio=0.1, ...)
```

### 关闭强平

```python
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
5. **`maker_commission_rate` 不传时默认等于 `commission_rate`**
6. **默认成交时机是下一根 bar 开盘**。如需当前 bar 收盘成交，设置 `fill_policy={"price_basis": "close", "bar_offset": 0}`
