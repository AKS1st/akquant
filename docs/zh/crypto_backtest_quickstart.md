# 加密货币回测快速上手

## 总览

AKQuant 对加密货币回测做了以下增强：

| 特性 | 说明 |
|---|---|
| 小数精度 | `step_size` / `tick_size` / `min_qty` — 订单不合规自动拒单 |
| 最小名义价值 | `min_notional` — 名义价值不足的订单被拒绝 |
| 资金费率 | 8 小时结算 (UTC 0/8/16), 多头付空头收 |
| 强平检查 | 权益 < 维持保证金时自动减仓 |
| 逐币种配置 | 每个币种独立设置保证金、手续费、滑点 |

---

## 基本回测

### 1. 准备数据

构造带必要字段的 DataFrame:

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
    # 可选: 启用资金费率结算时需要
    "funding_rate": np.zeros(n),
    "mark_price": prices,
})
```

**字段说明:**
- `timestamp` — UTC 时区, 支持 pd.Timestamp 或 int (纳秒)
- `open/high/low/close/volume` — 必须的 OHLCV 字段
- `symbol` — 币种标识, 多币种回测时每条数据必须携带
- `funding_rate` — (可选) 启用资金费率结算时传入, 0/8/16 整点为结算点
- `mark_price` — (可选) 强平和资金费率结算使用的标记价格, 不传则用 close

### 2. 执行回测

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
    asset_type=AssetType.Crypto,     # 必须设为 Crypto
    initial_cash=10000,
    commission_rate=0.0005,          # taker 费率 0.05%
    margin_ratio=0.1,                # 10x 杠杆 (0.1 = 1/10)
)
```

### 3. 查看结果

```python
# 订单明细
print(result.orders_df.head())
# 字段: id, symbol, side, order_type, quantity, filled_quantity,
#       avg_price, commission, status, reject_reason, created_at, updated_at

# 成交明细
for t in result.executions:
    print(f"{t.side} {t.quantity} @ {t.price}")

# 平仓交易
for t in result.trades:
    print(f"{t.symbol} {t.side} entry={t.entry_price} exit={t.exit_price} "
          f"pnl={t.pnl} net_pnl={t.net_pnl}")

# 现金曲线 / 权益曲线 / 保证金曲线
result.cash_curve
result.equity_curve
result.margin_curve

# 综合指标
print(result.metrics)
```

---

## 快速获取默认配置

无需记忆各币种的精度参数，一行获取：

```python
from akquant.crypto_exchange_info import get_default_crypto_instruments

instruments = get_default_crypto_instruments(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
# 返回 dict，可直接传入 run_backtest(instruments=...)
# {
#   "BTCUSDT": {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.1, "min_notional": 50.0, ...},
#   "ETHUSDT": {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.01, "min_notional": 20.0, ...},
#   ...
# }

result = aq.run_backtest(
    ...,
    instruments=instruments,
)
```

函数签名：

```python
def get_default_crypto_instruments(
    symbols: List[str],
    margin_ratio: float = 1.0,      # 全仓=1.0, 10x=0.1
    commission_rate: float = 0.0007, # 默认 0.07%
) -> Dict[str, dict]: ...
```

无需网络请求，使用内置的 Binance USDⓈ-M 永续合约参数表，覆盖约 60 个主流币种。

---

## 精度配置

你也可以手动传入精度参数：

```python
result = aq.run_backtest(
    ...,
    instruments={"BTCUSDT": {
        "asset_type": "CRYPTO",
        "multiplier": 1.0,
        "margin_ratio": 0.1,          # 杠杆倒数, 10x=0.1
        "tick_size": 0.1,             # 最小价格变动
        "step_size": 0.001,           # 数量步长, 下单量对齐至此
        "min_qty": 0.001,             # 最小订单数量
        "min_notional": 50.0,         # 最小开仓名义价值 (USDT)
        "commission_rate": 0.0005,    # 逐币种手续费 (覆盖全局)
        "slippage": 0.0002,           # 逐币种滑点 (覆盖全局)
    }},
)
```

**注意**: 数字货币没有 `lot_size`（最小交易单位）概念。股票有整手概念（100 股起），
期货有合约单位，但数字货币的数量单位完全由 `step_size` 决定。
引擎中 `lot_size` 仅用于股票/期货类型，对 Crypto 类型**不生效**。

不传 `instruments` 时使用全局默认值，精度检查不生效。推荐使用 `get_default_crypto_instruments()`。

### 精度规则

订单进入撮合引擎前依次检查:

1. **`min_qty`** — `quantity < min_qty` → 拒绝
2. **`step_size`** — `quantity % step_size ≠ 0` → 拒绝
3. **`tick_size`** — `limit_price % tick_size ≠ 0` → 拒绝
4. **`min_notional`** — `price × quantity × multiplier < min_notional` → 拒绝

辅助函数 (推荐下单前对齐):

```python
from akquant.strategy_trading_api import round_qty, round_price

aligned_qty = round_qty(0.123456, 0.001)     # → 0.123
aligned_price = round_price(50000.123, 0.01)  # → 50000.12
```

---

## 资金费率结算

启用条件: 数据中包含 `funding_rate` 和 `mark_price` 列 + `asset_type = Crypto`。

### 结算规则

- 结算时刻: **UTC 0:00 / 8:00 / 16:00** (每 8 小时)
- 公式: `payment = position_qty × mark_price × funding_rate`
- 正值 = 多头付空头; 负值 = 空头付多头
- 同小时内自动去重 (同一时刻存在多根 bar 不会重复扣款)
- 注意: **每根带 `funding_rate` 的 bar 都会触发检查**, 所以非结算小时必须设为 `0.0`, 否则会误触发

```python
# 正确做法: 只在结算整点设非零值
funding = []
for t in ts:
    if t.hour in (0, 8, 16) and t.minute == 0:
        funding.append(0.001)    # 0.1% 资金费率
    else:
        funding.append(0.0)      # 非结算小时必须设为 0
```

默认资金费率结算**已启用**。若不需要:

```python
df["funding_rate"] = 0.0  # 所有 bar 设零 → 不产生结算
```

---

## 强平检查

启用条件: `asset_type = Crypto` + `margin_ratio < 1.0` (即使用了杠杆)。

- 使用 `mark_price` 列计算未实现盈亏, 无则用 `close` 作为标记价格
- 维持保证金档位使用内置默认表 (BTC/ETH/SOL 等 8 个主流币种), 其他币种用默认 0.5%
- 权益低于维持保证金时自动发出减仓订单

```python
# 10x 杠杆 + 强平
result = aq.run_backtest(
    ...,
    margin_ratio=0.1,       # 10x 杠杆
    asset_type=AssetType.Crypto,
)
```

如需覆盖维持保证金档位:

```python
result = aq.run_backtest(
    ...,
    perp_maint_tiers={
        "BTCUSDT": [
            {"notional_upper": 100000, "maint_margin_rate": 0.004, "maint_amount": 0},
            {"notional_upper": 2000000, "maint_margin_rate": 0.005, "maint_amount": 100},
        ]
    }
)
```

---

## 逐币种手续费与滑点

在 `instruments` dict 中设置:

```python
instruments={"BTCUSDT": {
    "commission_rate": 0.0005,    # 0.05%, 覆盖全局 commission_rate
    "slippage": 0.0002,           # 0.02% 滑点, 覆盖全局 slippage
}}
```

- 不设置时回退到全局 `commission_rate` / `slippage`
- 手续费由 `SimpleMarket::calculate_commission` 执行, 支持 taker/maker 区分
- 滑点作为百分比作用于成交价: 买单 `price × (1 + rate)`, 卖单 `price × (1 - rate)`

---

## 订单成交时机 (fill_policy)

```python
# 默认: 下一 bar 以开盘价成交 (bar N 下单 → bar N+1 open 成交)
result = aq.run_backtest(..., fill_policy={
    "price_basis": "open",       # 可选: open / close / ohlc4 / hl2
    "bar_offset": 1,             # 1=下一 bar, 0=当前 bar
    "temporal": "same_cycle",    # 成交时机: same_cycle / next_event
})

# 常用变体: 当前 bar 收盘成交
result = aq.run_backtest(..., fill_policy={
    "price_basis": "close",
    "bar_offset": 0,
    "temporal": "same_cycle",
})
```

| 模式 | 成交时机 | 成交价 |
|---|---|---|
| `open/1` (默认) | 下一 bar 开盘 | next bar open |
| `close/0` | 当前 bar 收盘 | same bar close |
| `close/1` | 下一 bar 收盘 | next bar close |

---

## 完整示例

```python
import pandas as pd
import numpy as np
import akquant as aq
from akquant import Strategy
from akquant.crypto_exchange_info import get_default_crypto_instruments

# 1. 构造数据: 500 根 5 分钟 bar, 价格从 50000 缓慢下跌
n = 500
ts = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
prices = np.linspace(50000, 46000, n)

# funding_rate: 只在 UTC 0/8/16 整点设 0.1%
funding = [0.001 if (t.hour in (0,8,16) and t.minute==0) else 0.0 for t in ts]

df = pd.DataFrame({
    "timestamp": ts, "open": prices, "high": prices*1.002,
    "low": prices*0.998, "close": prices, "volume": np.full(n, 100.0),
    "symbol": "BTCUSDT", "funding_rate": funding, "mark_price": prices,
})

# 2. 快速获取默认配置
instruments = get_default_crypto_instruments(["BTCUSDT"], margin_ratio=0.1)

# 3. 策略: 买入并持有
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
    instruments=instruments,
)

# 5. 输出结果
orders = result.orders_df[["symbol","side","quantity","status","avg_price","commission"]]
print(orders)

final_cash = float(result.cash_curve.iloc[-1])
print(f"\n最终现金: {final_cash:.2f}")
print(f"成交笔数: {len(result.trades)}")
```

---

## 注意事项

1. **`asset_type` 必须为 `AssetType.Crypto`** (或字符串 `"crypto"`), 否则使用默认的 Stock 市场模型, 精度检查和资金费率结算都不生效
2. **数字货币没有 `lot_size` 概念**, 数量精度由 `step_size` 全权决定。`lot_size` 是股票/期货的遗留字段, 对 Crypto 不生效
3. **`min_notional=0` 表示不检查**, 不设置时默认为 0。需要检查时设为交易所实际值 (如 Binance 永续合约 BTC=50, ETH=20, 其他多数=5)。首次上手建议使用 `get_default_crypto_instruments()` 避免遗漏
4. **资金费率结算检查每根带 `funding_rate` 的 bar**, 不要在高频周期 (如 1m) 的每条 bar 都设非零值, 设 `0.0` 即可跳过
5. **默认 `fill_policy` 为 bar_offset=1** (下一 bar 成交), 如果需要当前 bar 成交, 手动设置 `fill_policy={"price_basis": "close", "bar_offset": 0}`
