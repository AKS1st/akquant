# 加密货币回测快速上手

## 总览

加密货币回测在 AKQuant 中是一种独立的市场模式，通过 `asset_type=AssetType.Crypto` 启用。启用后提供以下功能：

- 小数精度检查 — 订单不合规时自动拒单
- 最小名义价值检查 — 防止过小订单
- 资金费率结算 — UTC 0/8/16 自动结算
- 强平检查 — 权益不足时自动减仓
- 逐币种独立参数 — 每个币种可单独设置

---

## 数据准备

构造 DataFrame，包含 OHLCV 和币种标识：

```python
import pandas as pd
import numpy as np

n = 1000
ts = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
prices = np.linspace(50000, 45000, n)

df = pd.DataFrame({
    "timestamp": ts,
    "open": prices,
    "high": prices * 1.002,
    "low": prices * 0.998,
    "close": prices,
    "volume": np.full(n, 100.0),
    "symbol": "BTCUSDT",
})
```

**字段说明:**

| 字段 | 必须 | 说明 |
|---|---|---|
| `timestamp` | 是 | UTC 时区，支持 `pd.Timestamp` 或纳秒整数 |
| `open`, `high`, `low`, `close`, `volume` | 是 | OHLCV 标准字段 |
| `symbol` | 是 | 币种标识，多币种数据时必须 |
| `funding_rate` | 否 | 启用资金费率结算时传入 |
| `mark_price` | 否 | 强平和资金费率使用的标记价格，不传则用 close |

---

## 基本回测

```python
import akquant as aq
from akquant import Strategy, AssetType

class MyStrategy(aq.Strategy):
    def on_bar(self, bar):
        if self.get_position("BTCUSDT") == 0:
            self.buy("BTCUSDT", quantity=0.001)

result = aq.run_backtest(
    strategy=MyStrategy,
    symbols=["BTCUSDT"],
    data=df,
    asset_type=AssetType.Crypto,     # 启用加密货币模式
    initial_cash=10000,
    commission_rate=0.0005,          # 手续费率 0.05%
    margin_ratio=0.1,                # 10x 杠杆 (0.1 = 1/10)
)
```

### 查看结果

```python
# 订单明细
print(result.orders_df.head())
# 字段: symbol, side, quantity, filled_quantity, avg_price,
#       commission, status, reject_reason, created_at, updated_at

# 成交明细
for t in result.executions:
    print(f"{t.side} {t.quantity} @ {t.price}")

# 已平仓交易
for t in result.trades:
    print(f"{t.symbol} entry={t.entry_price} exit={t.exit_price} "
          f"pnl={t.pnl} net_pnl={t.net_pnl}")

# 现金曲线 / 权益曲线 / 保证金曲线
result.cash_curve
result.equity_curve
result.margin_curve

# 综合指标
print(result.metrics)
```

---

## 精度配置

每个加密货币有独立的精度参数。通过 `instruments` 参数传入：

```python
result = aq.run_backtest(
    ...,
    instruments={"BTCUSDT": {
        "asset_type": "CRYPTO",
        "multiplier": 1.0,
        "margin_ratio": 0.1,          # 杠杆倒数，10x=0.1
        "tick_size": 0.1,             # 最小价格变动
        "step_size": 0.001,           # 数量步长，下单量对齐至此
        "min_qty": 0.001,             # 最小订单数量
        "min_notional": 50.0,         # 最小开仓名义价值
        "slippage": 0.0002,           # 逐币种滑点
    }},
)
```

> 数字货币的数量精度完全由 `step_size` 决定。没有 `lot_size` 概念。

### 精度规则

订单进入引擎后依次执行以下检查，不满足则拒绝：

1. **`min_qty`** — 下单数量不得小于此值
2. **`step_size`** — 下单数量必须为此值的整数倍
3. **`tick_size`** — 限价单价格必须为此值的整数倍
4. **`min_notional`** — 名义价值（价格 × 数量 × 乘数）不得小于此值

> `min_notional` 不设置或设为 0 时不检查。

### 使用默认参数快速配置

内置约 60 个主流币种的 Binance USDⓈ-M 永续合约参数：

```python
from akquant.crypto_exchange_info import get_default_crypto_instruments

instruments = get_default_crypto_instruments(["BTCUSDT", "ETHUSDT"])
# 返回:
# {"BTCUSDT": {"step_size": 0.001, "min_qty": 0.001, ..., "min_notional": 50.0},
#  "ETHUSDT": {"step_size": 0.001, "min_qty": 0.001, ..., "min_notional": 20.0}}

result = aq.run_backtest(
    ...,
    instruments=instruments,
    commission_rate=0.0005,
)
```

无需网络请求。

### 下单辅助函数

推荐在策略中使用以下函数对齐下单参数：

```python
from akquant.strategy_trading_api import round_qty, round_price

aligned_qty = round_qty(0.123456, 0.001)     # → 0.123
aligned_price = round_price(50000.123, 0.01)  # → 50000.12
```

---

## 手续费

### 全局费率

通过 `run_backtest` 的显式参数设置：

```python
result = aq.run_backtest(
    ...,
    commission_rate=0.0007,           # taker 费率 0.07%
)
```

若需区分 taker 和 maker，通过 `BacktestConfig` 设置：

```python
from akquant.config import BacktestConfig, StrategyConfig

config = BacktestConfig(
    strategy_config=StrategyConfig(
        commission_rate=0.0007,          # taker 费率
        maker_commission_rate=0.0002,    # maker 费率
    ),
)
result = aq.run_backtest(config=config, commission_rate=0.0007, ...)
```

| 订单类型 | 角色 | 使用的费率 |
|---|---|---|
| `Market`（市价单） | taker | `commission_rate` |
| `StopMarket` / `StopLimit` | taker | `commission_rate` |
| `Limit`（限价单） | maker | `maker_commission_rate` |
| `LimitMaker`（Post-Only） | maker | `maker_commission_rate` |

> `maker_commission_rate` 不设置时默认等于 taker 费率。
> 回测启动时若未设置会输出 warning 提醒。

### 逐订单费率

下单时临时指定费率，覆盖全局设置：

```python
self.buy("BTCUSDT", quantity=1, commission={"type": "fixed", "value": 5.0})
self.buy("BTCUSDT", quantity=1, commission={"type": "percent", "value": 0.001})
self.buy("BTCUSDT", quantity=1, commission={"type": "per_unit", "value": 0.01})
```

---

## 滑点

全局滑点：

```python
result = aq.run_backtest(
    ...,
    slippage=0.0002,    # 0.02%，买方价上浮，卖方价下浮
)
```

逐币种滑点：

```python
instruments={"BTCUSDT": {
    "slippage": 0.0002,
}}
```

滑点优先级：逐订单 > 逐币种 > 全局。

---

## 资金费率结算

数据中包含 `funding_rate` 和 `mark_price` 列时自动启用。

### 结算规则

- 结算时刻：**UTC 0:00 / 8:00 / 16:00**（每 8 小时）
- 公式：`payment = 持仓量 × 标记价格 × 资金费率`
- 正值：多头付空头；负值：空头付多头
- 同小时自动去重

### 数据构造

每根带 `funding_rate` 的 bar 都会触发检查，非结算小时必须设为 0：

```python
funding = []
for t in ts:
    if t.hour in (0, 8, 16) and t.minute == 0:
        funding.append(0.001)    # 0.1%
    else:
        funding.append(0.0)      # 非结算小时

df["funding_rate"] = funding
df["mark_price"] = prices
```

### 关闭资金费率

通过 `BacktestConfig` 控制：

```python
from akquant.config import BacktestConfig, CryptoConfig

config = BacktestConfig(
    crypto=CryptoConfig(
        enable_funding=False,      # 关闭资金费率结算
    ),
)
result = aq.run_backtest(config=config, ...)
```

---

## 强平检查

启用条件：`margin_ratio < 1.0`（即使用了杠杆）。

- 使用 `mark_price` 列计算未实现盈亏，无此列时用 `close` 代替
- 维持保证金档位使用内置默认表，覆盖主流币种
- 权益低于维持保证金时自动发出减仓订单

```python
result = aq.run_backtest(
    ...,
    margin_ratio=0.1,        # 10x 杠杆
    asset_type=AssetType.Crypto,
)
```

### 自定义维持保证金档位

```python
config = BacktestConfig(
    crypto=CryptoConfig(
        perp_maint_tiers={
            "BTCUSDT": [
                {"notional_upper": 100000, "maint_margin_rate": 0.004, "maint_amount": 0},
                {"notional_upper": 2000000, "maint_margin_rate": 0.005, "maint_amount": 100},
            ],
        },
    ),
)
result = aq.run_backtest(config=config, ...)
```

### 关闭强平

```python
config = BacktestConfig(
    crypto=CryptoConfig(
        enable_liquidation=False,
    ),
)
```

---

## 订单成交时机

通过 `fill_policy` 控制订单在哪个时点以什么价格成交：

```python
# 默认：下一根 bar 以开盘价成交（bar N 下单 → bar N+1 open 成交）
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

## 完整示例

```python
import pandas as pd
import numpy as np
import akquant as aq
from akquant import Strategy
from akquant.crypto_exchange_info import get_default_crypto_instruments

# 1. 构造 500 根 5 分钟 bar，价格从 50000 跌到 46000
n = 500
ts = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
prices = np.linspace(50000, 46000, n)

funding = [0.001 if (t.hour in (0, 8, 16) and t.minute == 0) else 0.0 for t in ts]

df = pd.DataFrame({
    "timestamp": ts, "open": prices, "high": prices * 1.002,
    "low": prices * 0.998, "close": prices, "volume": np.full(n, 100.0),
    "symbol": "BTCUSDT", "funding_rate": funding, "mark_price": prices,
})

# 2. 获取币种精度配置
instruments = get_default_crypto_instruments(["BTCUSDT"], margin_ratio=0.1)

# 3. 策略
class MyStrategy(Strategy):
    def on_bar(self, bar):
        if self.get_position("BTCUSDT") == 0:
            self.buy("BTCUSDT", quantity=0.01)

# 4. 回测
result = aq.run_backtest(
    strategy=MyStrategy(),
    symbols=["BTCUSDT"],
    data=df,
    asset_type=aq.AssetType.Crypto,
    initial_cash=5000,
    commission_rate=0.0005,
    margin_ratio=0.1,
    instruments=instruments,
)

# 5. 输出
orders = result.orders_df[["symbol", "side", "quantity", "status", "avg_price", "commission"]]
print(orders)

final_cash = float(result.cash_curve.iloc[-1])
print(f"\n最终现金: {final_cash:.2f}")
print(f"成交笔数: {len(result.trades)}")
```

---

## 注意事项

1. **`asset_type` 必须设为 `AssetType.Crypto`**，否则使用默认的股票模型，精度检查和资金费率结算均不生效
2. **不使用 `instruments` 时精度检查不生效**。建议始终使用 `get_default_crypto_instruments()` 或手动配置
3. **数字货币没有 `lot_size` 概念**，数量精度由 `step_size` 决定
4. **`min_notional` 不设置或为 0 时不检查**。建议始终设置交易所实际值（BTC=50，ETH=20，其他多数=5）
5. **资金费率在每根带 `funding_rate` 的 bar 上触发**，非结算小时必须设为 `0.0`
6. **默认成交时机是下一根 bar 开盘**。如需当前 bar 收盘成交，设置 `fill_policy={"price_basis": "close", "bar_offset": 0}`
