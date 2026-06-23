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

# 也可通过 CryptoConfig 手动传入覆盖
from akquant.config import BacktestConfig, CryptoConfig

run_backtest(
    ...,
    config=BacktestConfig(
        crypto=CryptoConfig(
            perp_maint_tiers={
                "BTCUSDT": [
                    {"notional_upper": 500_000, "maint_margin_rate": 0.005, "maint_amount": 0},
                ],
            },
        ),
    ),
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

### 6.4 结算记录查询

每次结算的明细记录存储在回测结果中，可通过 `funding_payment_df` 属性获取：

```python
result = aq.run_backtest(...)

# 方式一：DataFrame（推荐）
df = result.funding_payment_df
print(df)
#   symbol  quantity  mark_price   rate     amount
#0  BTCUSDT     0.123   50000.00  0.001    6.1500
#1  BTCUSDT     0.123   50200.00  0.002   12.3492

# 方式二：原始 Rust dict（仅供内部使用）
# 外部统一使用 funding_payment_df
```

**返回字段说明：**

| 字段 | 类型 | 含义 |
|------|------|------|
| `symbol` | str | 交易对 |
| `quantity` | float | 结算时的持仓数量 |
| `mark_price` | float | 结算时的标记价格 |
| `rate` | float | 当期资金费率 |
| `amount` | float | 支付/收取金额（正值表示支出，负值表示收入） |

**注意：**
- 该属性不是 `result.metrics` 上的一个标量字段，而是一个独立的明细列表。因为资金费率结算需要的是逐笔记录（若干行，每行一次结算事件），不适合用标量指标表达。
- 回测过程中即使 `rate = 0` 也会触发结算并产生记录（金额为 0），便于审计结算事件是否按预期触发。
- 当前版本记录不包含结算时间戳，如需按时间维度分析请参考 `positions_df` 中的权益变化曲线推断。

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
print(result.metrics)
print(result.trades_df.head())
```

---

## 十、小数精度处理

### 10.1 问题背景：为什么 0.123456 个比特币买不了？

买比特币和买可乐不一样。可乐一瓶一瓶卖，**BTC 一次最少买 0.001 个**——也就是千分之一个。

这就带来了四个「门槛」，币安给每个交易对都定好了：

| 门槛 | 像什么 | BTCUSDT 的值 |
|------|-------|------------|
| `step_size` | **食堂打饭，师傅一勺的量**，你只能说"来几勺"，不能说"来 0.3 勺" | 0.001 |
| `min_qty` | **奶茶店"一杯起卖"**，不能买半杯 | 0.001 |
| `tick_size` | **自动售货机只收 1 角硬币**，你投 1 分钱它不认 | 0.1 USDT |
| `min_notional` | **外卖满 5 元起送**，点少了不发货 | 5.0 USDT |

更麻烦的是，计算机里的**小数天生不精确**。0.123 在电脑里其实是 `0.122999999999999...`。就像你用十进制写不精确 `1/3 = 0.333333...` 一样，电脑用二进制也写不精确很多十进制小数。

但这跟你钱包里的钱关系很大——几万次的交易累积下来，这些细微的误差会变成真金白银的偏差。所以必须有一套机制来保证每一笔数量、每一分钱都精确无误。

### 10.2 引擎怎么做？——像收银员一样较真

策略下单 → 引擎收单 → 引擎检查 → 要么成交，要么退回。

**akquant 的做法：引擎不做慈善。** 你给的数量没对齐 `step_size`？直接退回，告诉你理由。不会帮你悄悄抹掉零头。

```
你喊："老板，来 0.123456 个 BTC！"
引擎（收银员）："不好意思，我们这里最小单位是 0.001，只能按 0.001 的整数倍卖。
                 请用 round_qty() 算好再告诉我。"
```

```
你又喊："那 50000.125 USDT 一个卖不卖？"
引擎："价格最小变动是 0.1 USDT，50000.125 不对齐。
       请用 round_price() 算好再告诉我。"
```

```
你算好了："来 0.123 个 BTC，50000.1 USDT 一个。"
引擎检查 ✅ → 成交。
```

**为什么这么死板？** 因为引擎内部所有的资金计算（现金、保证金、盈亏）都是用 **128 位高精度十进制**在算，不存在浮点误差。引擎把最精确的运算留给自己，把格式校验放到最前面。你传进来的数只要过了格式校验，后面就是一路精确到底。

这和 **收银员让你付整数，找零才精确**是一个道理——入口麻烦一点，整条链路都干净。

### 10.3 工具函数：算好再下单

引擎提供了两个助手函数，帮你把数量/价格算「整齐」：

```python
from akquant.strategy_trading_api import round_qty, round_price

# 买入：数量向下凑整（宁可少买，不能超买）
round_qty(0.123456, 0.001)   # → 0.123
# 类似：你最多能买 0.123456，但只卖 0.001 的整数倍 → 只能买 0.123

# 限价单：价格四舍五入到 tick 的整数倍
round_price(50000.125, 0.1)  # → 50000.1
# 类似：50000.125 在最小变动 0.1 的世界里 → 50000.1
```

```python
class MyStrategy(aq.Strategy):
    def on_bar(self, bar):
        # ✅ 正确：先对齐再下单
        self.buy("BTCUSDT", quantity=round_qty(0.123456, 0.001))
        self.buy("BTCUSDT", quantity=1.0, price=round_price(50000.125, 0.1))

        # ❌ 错误：引擎直接退回
        # self.buy("BTCUSDT", quantity=0.123456)    # Rejected!
```

### 10.4 内置参数表：从交易所抄来的作业

你不必自己查每个币种的 `step_size` 是多少。我们从 **Binance 永续合约 API** 抄了一份现成的，内置了 60 个常用币种：

```python
from akquant.crypto_exchange_info import (
    DEFAULT_CRYPTO_SYMBOL_INFO,
    build_crypto_instrument_configs,
)

# 查一下 BTC 的参数
DEFAULT_CRYPTO_SYMBOL_INFO["BTCUSDT"]
# {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.1, "min_notional": 5.0}

# 直接生成配置
configs = build_crypto_instrument_configs(
    ["BTCUSDT", "ETHUSDT"],
    margin_ratio=0.1,       # 10x
    maker_commission_rate=0.0002,
)

# 想自己改？没问题
for cfg in configs:
    if cfg.symbol == "BTCUSDT":
        cfg.step_size = 0.0001  # 我偏要设成 0.0001

run_backtest(MyStrategy, instruments_config=configs, ...)
```

### 10.5 精度是怎么一路保持干净的——通俗版

```
你下单时写的 quantity = 0.123
         │
         │ 电脑说："0.123？我记成 0.122999999999999..."
         │（就像你写 1/3 只能写 0.333333）
         ▼
 引擎收到这个数，检查：
   "0.122999999999999... 除以 step=0.001 余数为 0 吗？"
   → 用高精度十进制算，余数正好是 0 ✅
   → 说明这个数本来就是整齐的，通过了
         │
         ▼
 后面做资金计算（保证金、盈亏、仓位）
   → 全程高精度十进制（128位，相当于带了个计算器在算）
   → 每一分钱都精确
```

**一句话总结：引擎自己算钱的时候非常精准（像会计用计算器），但它不会替你凑整下单（像收银员不收残币）。你自己算好对齐了再下单，后面的事交给引擎就好。**
