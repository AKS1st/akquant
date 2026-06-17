# 加密货币回测快速上手

## 数据准备

使用 `fetch_binance_klines` 直接下载 Binance USDⓈ-M 永续合约的真实行情：

```python
from akquant.crypto_exchange_info import fetch_binance_klines

# 下载 500 根 5 分钟 K 线
df = fetch_binance_klines("BTCUSDT", interval="5m", limit=500)
```

返回值包含：

| 列名 | 说明 |
|---|---|
| `timestamp` | UTC 时区 |
| `open`, `high`, `low`, `close`, `volume` | OHLCV 标准字段 |
| `trades` | 成交笔数 |
| `taker_buy_vol` | 主动买入量 |
| `taker_buy_quote_vol` | 主动买入额 |
| `symbol` | 币种标识 |

> 数据直接来源于 Binance 的 `fapi/v1/klines` 接口。

---

## 精度配置

使用 `get_default_crypto_instruments` 获取币种的精度参数，可直接传入 `run_backtest`。推荐开启 `online=True` 从 Binance API 拉取实时值：

```python
from akquant.crypto_exchange_info import get_default_crypto_instruments

# 从 Binance API 拉取实时精度参数（推荐）
instruments = get_default_crypto_instruments(["BTCUSDT"], online=True)

# 也可使用本地默认值（离线，约 60 个主流币种，无需网络请求）
instruments = get_default_crypto_instruments(["BTCUSDT"])
```

返回的格式：

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
from akquant.crypto_exchange_info import fetch_binance_klines, get_default_crypto_instruments

# 1. 数据
df = fetch_binance_klines("BTCUSDT", interval="5m", limit=500)

# 2. 精度配置
instruments = get_default_crypto_instruments(["BTCUSDT"], online=True)

# 3. 策略
class MyStrategy(Strategy):
    def on_bar(self, bar):
        if self.get_position("BTCUSDT") == 0:
            self.buy("BTCUSDT", quantity=0.001)

# 4. 回测
result = aq.run_backtest(
    strategy=MyStrategy,
    symbols=["BTCUSDT"],
    data=df,
    asset_type=AssetType.Crypto,
    initial_cash=10000,
    commission_rate=0.0005,         # taker 费率 0.05%
    maker_commission_rate=0.0002,   # maker 费率 0.02%
    margin_ratio=0.1,               # 10x 杠杆
    instruments=instruments,
)
```

**参数说明:**

| 参数 | 值 | 说明 |
|---|---|---|
| `asset_type` | `AssetType.Crypto` | 启用加密货币模式，否则使用默认股票模型 |
| `commission_rate` | 0.0005 | taker（吃单）费率 |
| `maker_commission_rate` | 0.0002 | maker（挂单）费率。不传时默认等于 taker |
| `margin_ratio` | 0.1 | 杠杆倒数，`1/杠杆倍数`，10x 杠杆 = 0.1 |
| `instruments` | 见上 | 币种精度参数。不传时精度检查不生效 |

### 查看结果

```python
# 订单明细
print(result.orders_df.head())

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

## 手续费

所有币种共享同一套 taker/maker 费率，实际值由交易所账户 VIP 等级决定。

### 全局设置

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

下单时临时指定，覆盖全局设置：

```python
self.buy("BTCUSDT", quantity=1, commission={"type": "fixed", "value": 5.0})
self.buy("BTCUSDT", quantity=1, commission={"type": "percent", "value": 0.001})
self.buy("BTCUSDT", quantity=1, commission={"type": "per_unit", "value": 0.01})
```

---

## 滑点

```python
# 全局滑点
result = aq.run_backtest(..., slippage=0.0002)

# 逐币种滑点
instruments = {"BTCUSDT": {"slippage": 0.0002}}
```

滑点优先级：逐订单 > 逐币种 > 全局。

---

## 资金费率结算

永续合约每 8 小时（UTC 0:00 / 8:00 / 16:00）结算一次。数据中包含 `funding_rate` 列时自动启用。

`fetch_binance_klines` 下载的 K 线不含 `funding_rate`，需单独获取并构造：

```python
import numpy as np

ts = pd.date_range(df["timestamp"].iloc[0], periods=len(df), freq="5min", tz="UTC")

# 资金费率：UTC 0/8/16 整点为结算点，其余为 0
funding = [0.001 if (t.hour in (0, 8, 16) and t.minute == 0) else 0.0 for t in ts]

df["funding_rate"] = funding
df["mark_price"] = df["close"]   # 用收盘价近似标记价格
```

> 资金费率数据可从 Binance API `fapi/v1/premiumIndex` 获取，或使用历史资金费率接口。

结算公式：`payment = 持仓量 × 标记价格 × 资金费率`。正值多头付空头，负值空头付多头。

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

- 使用 `mark_price` 列计算未实现盈亏，无此列时用 `close` 代替
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

控制订单在哪个时点以什么价格成交：

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

## 完整示例

```python
from akquant.crypto_exchange_info import fetch_binance_klines, get_default_crypto_instruments
import akquant as aq
from akquant import Strategy, AssetType
import pandas as pd
import numpy as np

# 1. 数据：从 Binance 下载
df = fetch_binance_klines("BTCUSDT", interval="5m", limit=500)

# 添加强平和资金费率需要的 mark_price / funding_rate
df["mark_price"] = df["close"]
ts = df["timestamp"]
funding = [0.001 if (t.hour in (0, 8, 16) and t.minute == 0) else 0.0 for t in ts]
df["funding_rate"] = funding

# 2. 精度配置：从 Binance 拉取实时参数
instruments = get_default_crypto_instruments(["BTCUSDT"], online=True)

# 3. 策略
class MyStrategy(Strategy):
    def on_bar(self, bar):
        if self.get_position("BTCUSDT") == 0:
            self.buy("BTCUSDT", quantity=0.001)

# 4. 回测
result = aq.run_backtest(
    strategy=MyStrategy(),
    symbols=["BTCUSDT"],
    data=df,
    asset_type=AssetType.Crypto,
    initial_cash=10000,
    commission_rate=0.0005,
    maker_commission_rate=0.0002,
    margin_ratio=0.1,
    instruments=instruments,
)

# 5. 输出
orders = result.orders_df[["symbol", "side", "quantity", "status", "avg_price", "commission"]]
print(orders)
print(f"最终现金: {float(result.cash_curve.iloc[-1]):.2f}")
print(f"成交笔数: {len(result.trades)}")
```

---

## 注意事项

1. **`asset_type` 必须设为 `AssetType.Crypto`**，否则使用默认股票模型
2. **不使用 `instruments` 时精度检查不生效**。建议使用 `get_default_crypto_instruments(..., online=True)` 获取
3. **数字货币没有 `lot_size` 概念**，数量精度由 `step_size` 决定
4. **`min_notional` 设为 0 时不检查**，默认值为 0
5. **`maker_commission_rate` 不传时默认等于 `commission_rate`**
6. **默认成交时机是下一根 bar 开盘**。如需当前 bar 收盘成交，设置 `fill_policy={"price_basis": "close", "bar_offset": 0}`
