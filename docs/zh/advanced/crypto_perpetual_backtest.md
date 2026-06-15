# 数字货币永续合约回测系统设计

## 概述

基于 akquant 框架扩展的 USDⓈ-M 永续合约回测系统，覆盖从数据接入到策略运行的完整链路。核心设计原则：**数据与计算分离**——引擎不替数据层做判断，数据层保证输入的正确性。

---

## 一、整体架构

```
┌──────────────────────────────────────────────────────────┐
│                   数据准备层（AIAIGO）                      │
│                                                          │
│  perp_kline_1m   ──┐                                     │
│  mark_price_1m   ──┤── asof join ──→ DataFrame ──→ Bar   │
│  funding_rate_1m ──┘                    extra             │
│                                       funding_rate       │
│                                       mark_price         │
└────────────────────────────────┬─────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────┐
│                   回测引擎层（akquant）                     │
│                                                          │
│  Pipeline:                                                │
│    DataProcessor                                          │
│      → CryptoPerpProcessor                                │
│        ├─ mark_price 更新                                  │
│        ├─ funding_rate 结算                                │
│        └─ liquidation 检查                                 │
│      → ExecutionProcessor(Pre)                            │
│      → StrategyProcessor                                  │
│      → ExecutionProcessor(Post)                           │
│      → ChannelProcessor                                   │
│      → StatisticsProcessor                                │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 二、数据接入

### 2.1 数据表映射

| 引擎字段 | AIAIGO DDB 表 | 说明 |
|---------|--------------|------|
| `open/high/low/close/volume` | `perp_kline_1m` | 1 分钟 K 线 |
| `bar.extra["mark_price"]` | `mark_price_1m.close` | 标记价格 |
| `bar.extra["funding_rate"]` | `funding_rate_1m.funding_rate` | 资金费率 |

### 2.2 数据准备方式

引擎**只认一张 DataFrame**，列名映射自动完成：

```python
# from AIAIGO DDB
bars = ddb.sql("""
    select
        k.timestamp,
        k.open, k.high, k.low, k.close, k.volume,
        m.close as mark_price,
        f.funding_rate
    from perp_kline_1m as k
    asof join mark_price_1m as m on k.timestamp = m.timestamp
    asof join funding_rate_1m as f on k.timestamp = f.timestamp
    where k.symbol = 'BTCUSDT'
    order by k.timestamp
""")

# 直接喂给引擎
result = aq.run_backtest(
    strategy=MyStrategy(),
    data={"BTCUSDT": bars},
    asset_type=aq.AssetType.Crypto,
    margin_ratio=0.1,  # 10x
)
```

**自动映射规则：**
- `timestamp`, `open`, `high`, `low`, `close`, `volume` → Bar 标准字段
- 其他 numeric 列（如 `funding_rate`、`mark_price`）→ 自动进 `bar.extra`
- 多币种传入 `Dict[str, pd.DataFrame]`

### 2.3 数据约定

- **时间戳**: UTC 纳秒，回测中全部按 UTC 处理
- **资金费率**: `bar.extra["funding_rate"]` — 有值就触发结算，费率为 0 也触发（支付为 0，记录结算事件）
- **标记价格**: `bar.extra["mark_price"]` — 引擎用于强平权益计算，不参与撮合成交价
- **插针防护**: 标记价格来自交易所多加权指数，天然抗插针。数据层喂什么引擎就用什么

### 2.4 内存估算

8 币种 × 365 天 × 1440 分钟 × ~200 字节 ≈ **840 MB（引擎层）+ 350 MB（数据层）≈ 1.2 GB**

单币种逐次跑则 ~150 MB/次。

---

## 三、账户模型

### 3.1 全仓模式（Cross Margin）

```python
# 一次 run_backtest = 一个 Portfolio
# 所有品种共享 portfolio.cash
result = aq.run_backtest(
    strategy=strategy,
    symbols=["BTCUSDT", "ETHUSDT"],
    data=bars,
    asset_type=aq.AssetType.Crypto,
    margin_ratio=0.1,
    initial_cash=100000,
)
```

**行为：**
- 所有品种共用一个现金池
- 一个品种的亏损减少全仓可用资金
- 强平从总现金扣除亏损

### 3.2 逐仓模式（Isolated Margin）

```python
# 每个币种独立跑一次，各自分配资金
for sym, cash in [("BTCUSDT", 5000), ("ETHUSDT", 5000)]:
    result = aq.run_backtest(
        strategy=strategy,
        symbols=[sym],
        data={sym: bars[sym]},
        asset_type=aq.AssetType.Crypto,
        margin_ratio=0.1,
        initial_cash=cash,
    )
```

**不需要改引擎**——外部拆品种跑，等价于币安逐仓的独立资金池。

---

## 四、杠杆与保证金

### 4.1 初始化保证金

杠杆由 `Instrument.margin_ratio` 控制：

| 杠杆倍数 | `margin_ratio` | 含义 |
|---------|---------------|------|
| 1x | 1.0 | 全额保证金 |
| 10x | 0.1 | 10% 保证金 |
| 100x | 0.01 | 1% 保证金 |

```python
run_backtest(
    ...,
    margin_ratio=0.1,     # 全局默认 10x
)
```

**固定杠杆设计：** 量化开始后不允许动态调节杠杆，保证算法稳定可复现。

### 4.2 维持保证金（Maintenance Margin）

公式（对齐 Binance USDⓈ-M）：

```
维持保证金 = max(0, 名义价值 × 维持保证金率 − Maint Amount)
```

**Maint Amount 的作用：** 保证档位边界平滑过渡无跳变。

```
Tier 1: 0~300k,   rate=0.4%,  amount=0     → 300k×0.4% = 1200
Tier 2: 300k~800k, rate=0.5%,  amount=300   → 300k×0.5%-300 = 1200 ✅ 平滑
```

### 4.3 档位表（8 币种内置）

数据源：Binance API `/fapi/v1/leverageBracket`，同步自 freqtrade。

| 币种 | 最大杠杆 | Tier1 上限 | Tier1 维持保证金率 |
|------|---------|-----------|-------------------|
| BTCUSDT | 150x | 300,000 | 0.4% |
| ETHUSDT | 150x | 300,000 | 0.4% |
| SOLUSDT | 100x | 50,000 | 0.5% |
| BNBUSDT | 75x | 10,000 | 0.5% |
| XRPUSDT | 100x | 40,000 | 0.5% |
| ADAUSDT | 75x | 10,000 | 0.5% |
| DOGEUSDT | 75x | 80,000 | 0.65% |
| AVAXUSDT | 75x | 25,000 | 0.5% |

```python
# 档位表在 python/akquant/backtest/engine.py 中 DEFAULT_CRYPTO_MAINT_TIERS
# asset_type=AssetType.Crypto 时自动加载

# 也可手动传入覆盖
run_backtest(
    ...,
    perp_maint_tiers={
        "BTCUSDT": [
            {"notional_upper": 500_000, "maint_margin_rate": 0.005, "maint_amount": 0},
        ],
    },
)
```

---

## 五、订单系统

### 5.1 订单类型

| 类型 | 用法 | 说明 |
|------|------|------|
| Market | `self.buy(sym)` | 市价单，默认下一根 bar 开盘成交 |
| Limit | `self.buy(sym, price=100)` | 限价单 |
| StopMarket | `self.buy(sym, trigger_price=105)` | 止损市价单 |
| StopLimit | `self.buy(sym, price=98, trigger_price=100)` | 止损限价单 |
| LimitMaker | `self.buy(sym, price=99, order_type="limit_maker")` | 仅挂单不吃单 |

### 5.2 成交价格策略（Fill Policy）

| `fill_policy` | 含义 | 场景 |
|-------------|------|------|
| `{price_basis:"open", bar_offset:1}`（默认） | 下一根 bar 开盘成交 | 标准回测，无前视偏差 |
| `{price_basis:"close", bar_offset:0}` | 当前 bar 收盘成交 | 高频近似 |
| `{price_basis:"close", bar_offset:1}` | 下一根 bar 收盘成交 | 保守场景 |

### 5.3 Taker / Maker 费率

**引擎自动根据订单类型判断：**

| 订单类型 | 判定 | 费率 |
|---------|------|------|
| Market | Taker | `commission_rate` |
| StopMarket (触发后) | Taker | `commission_rate` |
| StopLimit (触发后) | Taker | `commission_rate` |
| Limit | Maker | `maker_commission_rate` |
| LimitMaker | Maker | `maker_commission_rate` |

```python
run_backtest(
    asset_type=aq.AssetType.Crypto,
    commission_rate=0.001,          # taker: 0.1%
    maker_commission_rate=0.0005,   # maker: 0.05%
)
# 不传 maker_commission_rate 则默认等于 commission_rate（向后兼容）
```

---

## 六、资金费率结算

### 6.1 触发机制

**数据驱动**——不在引擎内硬编码 UTC 0/8/16：

```rust
if bar.extra 中存在 "funding_rate" 字段 {
    if 与上次结算同小时 { 跳过（去重） }
    if 距上次结算不足 7h { log::error!(警告) }
    结算: cash -= qty × mark_price × rate
}
```

### 6.2 结算公式

```
payment = position_qty × mark_price × funding_rate
```

| 场景 | 方向 | 结果 |
|------|------|------|
| 做多, rate > 0 | 多头付空头 | cash 减少 |
| 做多, rate < 0 | 多头收钱 | cash 增加 |
| 做空, rate > 0 | 空头收钱 | cash 增加 |
| 做空, rate < 0 | 空头付钱 | cash 减少 |
| rate = 0 | 无收付 | cash 不变 |

### 6.3 数据层注意事项

```python
# 数据层只需保证：结算时刻的 bar 有 funding_rate 字段
# 其他 bar 可以没有该字段，引擎会自动跳过
bars["funding_rate"] = [
    0.0, 0.0, 0.0,       # 非结算时间 → 不触发
    0.001,                # UTC 08:00 → 结算触发
    0.0, 0.0,             # 继续不触发（同小时去重）
    0.002,                # UTC 16:00 → 再次结算
]
```

---

## 七、强平

### 7.1 触发条件

```
equity(cash + mark_to_market_upnl) < maintenance(档位表计算)
```

- **标记价格**算 upnl，不用成交价
- **维持保证金**查档位表，不是固定比例
- **全仓权益** = cash + 所有品种的未实现盈亏

### 7.2 清算价

```
破产价 = avg_entry - cash / (qty × multiplier)

多头清算价 = min(mark, 破产价) × 0.95  (模拟滑点+保险基金折价)
空头清算价 = max(mark, 破产价) × 1.05
```

### 7.3 账务处理

强平**不经过撮合引擎**，直接生成已成交的 ExecutionReport，走既有账务链路：

```
1. 创建 Order { status: Filled, filled_quantity, price: 清算价 }
2. 创建 Trade { position_effect: Close }
3. → Event::ExecutionReport → ChannelProcessor
   → process_trades()
     ├── Portfolio.cash 调整（扣亏损）
     ├── Portfolio.positions 归零
     ├── TradeTracker 更新（入场均价、已实现盈亏）
     └── closed_trades 记录（可在 BacktestResult.trades_df 查询）
```

**强平后不回测结束，仓位归零后继续运行。**

---

## 八、架构决策记录

| 决策 | 方案 | 理由 |
|------|------|------|
| 资金费率结算点 | 数据驱动，引擎不硬编码 0/8/16 | 避免与 Binance API 变更耦合 |
| 标记价格强平 | 用 bar.extra["mark_price"] | 与交易所规则对齐，避免插针 |
| 强平账务 | 直接生成 ExecutionReport，不走撮合 | 复用 trade_tracker/closed_trades 链路，避免 overshoot |
| Maker/Taker 判断 | 撮合层根据 `order.order_type` 判断 | 策略不需要标记，引擎自动区分 |
| Maker/Taker 费率 | `SimpleMarketConfig` 拆两字段 | 只需改一处，不涉及 A 股路径 |
| 杠杆 | 静态固定 | 动态杠杆不利于量化分析的稳定性 |
| 逐仓 | 外部拆品种跑 N 次 `run_backtest` | 不改引擎，逻辑最清晰 |
| 多表 join | 数据层做，引擎只吃一张 DataFrame | 数据准备不是引擎责任 |

---

## 九、快速上手

```python
import akquant as aq
import pandas as pd

class MovingAverageCross(aq.Strategy):
    def on_start(self):
        self.set_history_depth(30)

    def on_bar(self, bar):
        if len(self.get_history(20)) < 20:
            return
        ma_short = self.get_history(10).mean()
        ma_long = self.get_history(20).mean()

        pos = self.get_position("BTCUSDT")
        if ma_short > ma_long and pos == 0:
            self.buy("BTCUSDT", quantity=0.1)
        elif ma_short < ma_long and pos > 0:
            self.sell("BTCUSDT", quantity=0.1)

bars = pd.DataFrame({
    "timestamp": [...],
    "open": [...], "high": [...], "low": [...], "close": [...], "volume": [...],
    "funding_rate": [...],
    "mark_price": [...],
})

result = aq.run_backtest(
    strategy=MovingAverageCross(),
    symbols=["BTCUSDT"],
    data=bars,
    asset_type=aq.AssetType.Crypto,
    commission_rate=0.0005,
    maker_commission_rate=0.0002,
    margin_ratio=0.1,  # 10x
    initial_cash=10000,
)
print(result.summary())
print(result.trades_df.head())
```
