# 第 5 章：策略开发实战 (Strategy Implementation)

在理解了事件驱动引擎的原理后，我们来动手构建一个真正可用的交易策略。本章将详细拆解策略代码的结构，重点介绍**策略生命周期 (Lifecycle)**、**交易接口 (Trading API)** 以及如何实现复杂的**风控逻辑**。

## 本章实践入口

- 主示例：[examples/textbook/ch05_strategy.py](https://github.com/akfamily/akquant/blob/main/examples/textbook/ch05_strategy.py)
- 进阶示例：[examples/23_functional_callbacks_demo.py](https://github.com/akfamily/akquant/blob/main/examples/23_functional_callbacks_demo.py)
- 框架钩子示例：[examples/50_framework_hooks_demo.py](https://github.com/akfamily/akquant/blob/main/examples/50_framework_hooks_demo.py)
- 类风格 Tick 示例：[examples/51_class_tick_callbacks_demo.py](https://github.com/akfamily/akquant/blob/main/examples/51_class_tick_callbacks_demo.py)
- 对应指南：[策略指南](../guide/strategy.md)

建议学习路径：

1. 先运行 `examples/textbook/ch05_strategy.py`，掌握 `on_start -> on_bar -> on_stop` 的主骨架。
2. 再看 `examples/08_event_callbacks.py`，把订单、成交、拒单、定时器放到一张图里理解。
3. 需要框架边界钩子时，运行 `examples/50_framework_hooks_demo.py`。
4. 需要 Tick 级策略时，运行 `examples/51_class_tick_callbacks_demo.py`。

## 快速运行与验收

```bash
python examples/textbook/ch05_strategy.py
```

验收要点：

1. 脚本可完成策略初始化、信号生成、下单与回测统计输出。
2. 日志中可观察到订单状态变化与关键风控触发信息。
3. 调整均线参数后，回测结果会出现可解释的变化。

## 5.1 策略类结构与继承

一个标准的 `AKQuant` 策略通常继承自 `AKQuant.Strategy` 基类，并重写以下几个核心回调方法 (Callbacks)：

1.  `__init__`: **构造函数**。定义策略参数和内部变量。
2.  `on_start`: **初始化钩子**。回测开始前触发，常用于订阅数据、设置风控参数。
3.  `on_bar`: **事件处理钩子**。每根 K 线走完时触发，这是策略逻辑的核心入口。
4.  `on_stop`: **结束钩子**。回测结束时触发，常用于清理资源或统计结果。

这 4 个回调构成了最常见的策略主骨架，但并不是全部。AKQuant 还提供了热启动、框架边界、定时器、账户快照、拒单、ML 训练信号等扩展回调。本章后续会给出一张完整的教材级速查表，帮助你知道“应该把逻辑写进哪个 `on_xxx`”。

### 5.1.1 示例代码：带止损的双均线策略

我们以一个增强版的双均线策略为例，增加了**固定比例止损**逻辑。

```python
--8<-- "examples/textbook/ch05_strategy.py"
```

## 5.2 深入理解生命周期 (Lifecycle Management)

### 5.2.1 `__init__` vs `on_start`

*   `__init__`: 此时策略实例刚被创建，回测引擎尚未完全启动，你无法访问 `self.ctx` (Context) 或账户信息。只能做一些纯 Python 层面的变量初始化（如 `self.ma_window = 20`）。
*   `on_start`: 此时引擎已就绪 (Ready State)。你可以安全地调用 `self.log()`, `self.get_position()` 等依赖引擎上下文的 API。

### 5.2.2 `on_bar` 的执行流 (Execution Flow)

`on_bar` 是策略的心脏。它的标准执行流程如下：

1.  **数据获取 (Data Ingestion)**：使用 `self.get_history()` 获取所需的历史数据窗口。
2.  **信号计算 (Signal Generation)**：基于历史数据计算技术指标 (如 MA, RSI)。
3.  **状态检查 (State Inspection)**：获取当前持仓 (`self.get_position`) 和账户资金。
4.  **决策逻辑 (Decision Making)**：根据指标和持仓状态，判断是否买入或卖出。
5.  **订单执行 (Order Routing)**：调用下单函数 (`self.buy`, `self.sell` 等)。

### 5.2.3 类风格与函数式入口边界

`AKQuant` 同时支持两种策略入口：

1.  **类风格**：`strategy=MyStrategy`，适合中长期维护、复杂状态管理。
2.  **函数式**：`strategy=on_bar` + `initialize=...`，适合快速原型、脚本化调试。

函数式入口示例：

```python
import akquant as aq

def initialize(ctx):
    ctx.counter = 0

def on_bar(ctx, bar):
    ctx.counter += 1
    if ctx.get_position(bar.symbol) == 0:
        ctx.buy(bar.symbol, 1)
    else:
        ctx.sell(bar.symbol, 1)

result = aq.run_backtest(
    data=data_feed,
    strategy=on_bar,
    initialize=initialize,
    symbols="TEST",
)
```

当你需要 `on_start/on_stop/on_order/on_trade` 等完整生命周期并封装为可复用组件时，优先使用类风格；当你需要快速验证交易逻辑和参数时，函数式入口更轻量。

### 5.2.4 全量 `on_xxx` 回调速查表

如果把 `AKQuant` 的策略接口只理解为 `on_start -> on_bar -> on_stop`，很容易在盘前准备、日终归档、拒单处理、恢复续跑等场景里把逻辑塞错地方。更好的做法是按“事件来源”来理解回调族：

1.  **生命周期回调**：控制策略启动、恢复、停止。
2.  **主数据事件回调**：处理 Bar、Tick、Timer 这三类用户最常见的决策入口。
3.  **订单与成交回调**：跟踪订单流转、拒单与实际成交。
4.  **框架边界回调**：处理交易日、session 和账户快照这类“不是行情、但很关键”的事件。
5.  **专项回调**：处理到期结算、ML 训练信号、异常治理等高级场景。

下表给出教材中建议掌握的完整接口：

| 回调 | 类型 | 典型用途 | 推荐示例 |
| :--- | :--- | :--- | :--- |
| `on_start` | 生命周期 | 订阅标的、注册指标、初始化运行态资源 | `examples/textbook/ch05_strategy.py` |
| `on_resume` | 生命周期 | 热启动恢复、打印快照续跑状态、恢复外部连接 | `examples/21_warm_start_demo.py` |
| `on_stop` | 生命周期 | 汇总统计、资源释放、输出最终摘要 | `examples/textbook/ch05_strategy.py` |
| `on_bar` | 主数据事件 | K 线策略、指标更新、主交易逻辑 | `examples/textbook/ch05_strategy.py` |
| `on_tick` | 主数据事件 | Tick 级监控、盘口驱动、高频响应 | `examples/51_class_tick_callbacks_demo.py` |
| `on_timer` | 主数据事件 | 定时任务、盘前检查、固定时点调仓 | `examples/strategies/07_stock_momentum_rotation_on_timer.py` |
| `on_order` | 订单事件 | 跟踪订单状态流转、联动撤单或重置状态 | `examples/08_event_callbacks.py` |
| `on_trade` | 订单事件 | 记录成交、成交后风控、累计成交统计 | `examples/08_event_callbacks.py` |
| `on_reject` | 订单事件 | 记录拒单原因、发告警、触发降级策略 | `examples/50_framework_hooks_demo.py` |
| `on_session_start` | 框架边界 | 日盘/夜盘切换、session 级状态重置 | `examples/50_framework_hooks_demo.py` |
| `on_session_end` | 框架边界 | 收盘后清理、session 结束打点与归档 | `examples/50_framework_hooks_demo.py` |
| `on_before_trading` | 框架边界 | 盘前检查、生成交易日级信号、盘前风控 | `examples/50_framework_hooks_demo.py` |
| `on_daily_rebalance` | 框架边界 | 横截面选股、每天最多一次的统一调仓 | `examples/strategies/05_stock_momentum_rotation_timer.py` |
| `on_after_trading` | 框架边界 | 日终统计、收盘后归档、落盘或报表输出 | `examples/50_framework_hooks_demo.py` |
| `on_portfolio_update` | 框架边界 | 账户权益变化监控、推送 UI 或风控告警 | `examples/50_framework_hooks_demo.py` |
| `on_expiry` | 专项回调 | 期货/期权到期结算、换月、移除失效合约 | `examples/49_on_expiry_demo.py` |
| `on_error` | 专项回调 | 统一处理用户回调异常、选择继续或中断 | `examples/22_strategy_runtime_config_demo.py` |
| `on_train_signal` | 专项回调 | ML 滚动训练窗口触发时更新模型 | `examples/10_ml_walk_forward.py` |

有两个实践判断非常重要：

*   当逻辑依赖**价格数据本身**时，优先考虑 `on_bar` / `on_tick` / `on_timer`。
*   当逻辑依赖**交易阶段边界**时，优先考虑 `on_before_trading` / `on_after_trading` / `on_session_*`，不要强行塞进 `on_bar`。

如果你想系统理解这些回调的触发顺序、类风格与函数式的能力差异，以及每个回调是否有公开示例，请继续参考：[策略指南](../guide/strategy.md)。

## 5.3 交易接口详解 (Trading API)

`AKQuant` 提供了多种便捷的下单接口，底层会自动处理报单验证和资金冻结。

### 5.3.1 `order_target_percent(symbol, target)`

这是最常用的接口，实现了**目标仓位管理**。它会自动计算需要买入或卖出的数量，使持仓达到目标比例。

*   `target=0.5`: 买入直到持仓占总资产的 50%。
*   `target=0.0`: 清仓卖出所有持仓。
*   `target=-0.5`: (期货/融券) 卖空直到空头仓位占 50%。

### 5.3.2 `buy(symbol, quantity)` / `sell(symbol, quantity)`

最基础的原子接口，直接指定买卖数量。

*   `quantity`: 必须为正数。
*   对于股票，数量通常需要是 100 的倍数 (手数)，引擎会自动向下取整。

### 5.3.3 `close_position(symbol)`

一键平仓。无论当前持有多头还是空头，都会发出相反方向的市价单将其平掉。

### 5.3.4 信用账户参数与账户快照

当你在股票场景做融资/融券回测时，需要在 `RiskConfig` 中显式启用信用账户模式：

```python
from akquant.config import RiskConfig

risk_config = RiskConfig(
    account_mode="margin",
    enable_short_sell=True,
    initial_margin_ratio=0.5,
    maintenance_margin_ratio=0.3,
    financing_rate_annual=0.08,
    borrow_rate_annual=0.10,
    allow_force_liquidation=True,
    liquidation_priority="short_first",
)
```

策略内可通过 `get_account()` 读取信用账户专有字段：

- `borrowed_cash`: 融资负债
- `short_market_value`: 空头市值
- `maintenance_ratio`: 维持担保比例
- `accrued_interest` / `daily_interest`: 累计与当日计息

```python
snap = self.get_account()
print(
    snap["account_mode"],
    snap["borrowed_cash"],
    snap["short_market_value"],
    snap["maintenance_ratio"],
    snap["accrued_interest"],
    snap["daily_interest"],
)
```

## 5.4 高级策略模式 (Advanced Patterns)

在实际开发中，简单的双均线往往不够用。我们需要更复杂的策略模式。

### 5.4.1 多因子选股 (Multi-Factor Selection)

在多标的回测中（例如全市场选股），我们需要遍历所有标的，计算因子得分，然后构建组合。

**设计模式**：

1.  **每日定时任务**：使用 `schedule_function` 或在 `on_bar` 中检查是否是每日收盘。
2.  **横截面计算**：获取所有标的当日收盘价。
3.  **排序与筛选**：根据因子值排序，选出 Top N。
4.  **调仓**：卖出不在 Top N 的标的，买入新进入 Top N 的标的。

```python
def on_bar(self, bar):
    # 仅在每日收盘前执行 (假设日线数据)
    # 遍历所有关注的标的
    scores = {}
    for symbol in self.universe:
        # 计算因子...
        score = ...
        scores[symbol] = score

    # 排序选股
    target_symbols = sorted(scores, key=scores.get, reverse=True)[:10]

    # 调仓逻辑...
```

### 5.4.2 状态机策略 (Finite State Machine)

对于复杂的择时策略，使用状态机可以清晰地管理逻辑。

*   **State 0 (空仓)**: 等待入场信号。
*   **State 1 (持有)**: 监控止损/止盈。
*   **State 2 (加仓)**: 盈利加仓。
*   **State 3 (冷却)**: 止损后暂停交易一段时间。

```python
class FSMStrategy(Strategy):
    def __init__(self):
        self.state = "EMPTY"
        self.cooldown_counter = 0

    def on_bar(self, bar):
        if self.state == "EMPTY":
            if self.signal_buy():
                self.buy(bar.symbol, 100)
                self.state = "HOLDING"

        elif self.state == "HOLDING":
            if self.check_stop_loss():
                self.close_position(bar.symbol)
                self.state = "COOLDOWN"
                self.cooldown_counter = 5

        elif self.state == "COOLDOWN":
            self.cooldown_counter -= 1
            if self.cooldown_counter <= 0:
                self.state = "EMPTY"
```

## 5.5 自定义指标开发 (Custom Indicators)

`AKQuant` 目前已经提供了 `AKQuant.talib` 兼容层，并支持 `python/rust` 双后端；但在实战中，我们仍会频繁遇到需要开发私有指标或策略专用信号的场景。

### 5.5.1 继承 `Indicator` 基类

所有的指标都应继承自 `AKQuant.Indicator`，并实现 `update` 方法。这种设计支持**增量计算 (Incremental Calculation)**，避免了每次重算整个历史序列的浪费。

```python
class MyMomentum(Indicator):
    def __init__(self, period=10):
        super().__init__()
        self.period = period
        self.history = []

    def update(self, value):
        self.history.append(value)
        if len(self.history) > self.period:
            self.history.pop(0)

        if len(self.history) < self.period:
            return float('nan')

        return self.history[-1] - self.history[0]
```

### 5.5.2 在策略中使用

```python
def __init__(self):
    self.my_mom = MyMomentum(period=10)

def on_bar(self, bar):
    mom_value = self.my_mom.update(bar.close)
    if not math.isnan(mom_value) and mom_value > 0:
        # Do something...
```

### 5.5.3 使用 `AKQuant.talib` 双后端

当策略从 TA-Lib 迁移时，建议先保持函数签名不变，再通过 `backend` 参数切换执行后端。

- `backend="auto"` 默认走 `rust`。
- 需要与历史策略逐步对齐时，建议显式使用 `backend="python"`。
- 如需全局覆盖 `auto`，可设置环境变量 `AKQUANT_TALIB_AUTO_BACKEND=python|rust`。

```python
from akquant import talib as ta

close = df["close"].to_numpy()
high = df["high"].to_numpy()
low = df["low"].to_numpy()

# python 后端（兼容基线）
rsi_py = ta.RSI(close, timeperiod=14, backend="python")

# rust 后端（高性能）
rsi_rs = ta.RSI(close, timeperiod=14, backend="rust")
adx_rs = ta.ADX(high, low, close, timeperiod=14, backend="rust")
slowk_rs, slowd_rs = ta.STOCH(
    high,
    low,
    close,
    fastk_period=5,
    slowk_period=3,
    slowd_period=3,
    backend="rust",
)
```

当前 `rust` backend 已覆盖：

- 单输出：`SMA/EMA/RSI/ATR/ROC/WILLR/CCI/ADX/MFI/OBV/TRIX/MOM/DEMA/TEMA/KAMA/NATR/SAR`
- 多输出：`MACD/BBANDS/STOCH`

批次 B/C 的常见调用示例：

```python
volume = df["volume"].to_numpy()

mfi_rs = ta.MFI(high, low, close, volume, timeperiod=14, backend="rust")
obv_rs = ta.OBV(close, volume, backend="rust")
trix_rs = ta.TRIX(close, timeperiod=15, backend="rust")
mom_rs = ta.MOM(close, period=10, backend="rust")
dema_rs = ta.DEMA(close, timeperiod=20, backend="rust")

tema_rs = ta.TEMA(close, timeperiod=20, backend="rust")
kama_rs = ta.KAMA(close, period=10, backend="rust")
natr_rs = ta.NATR(high, low, close, timeperiod=14, backend="rust")
sar_rs = ta.SAR(high, low, acceleration=0.02, maximum=0.2, backend="rust")
```

在策略里使用时，建议显式处理 warmup 区段：

```python
import numpy as np

signal = ta.TEMA(close, timeperiod=20, backend="rust")
last_signal = signal[-1]
if np.isnan(last_signal):
    return
```

在工程实践中，推荐流程是：

1. 先用 `backend="python"` 与原策略对齐结果；
2. 对齐完成后切 `backend="auto"`（默认 `rust`）或显式 `backend="rust"` 做性能提速；
3. 用固定数据集回归验证 warmup 与输出形态（单值或 tuple）一致。
4. 对支持 `period` 别名的指标优先沿用旧参数命名，降低迁移成本。

### 5.5.4 指标选型与组合模板

实战里不建议“单指标决策”，更推荐“趋势 + 动量 + 波动率/风险”组合。

| 场景 | 推荐组合 | 起步参数（可回测微调） | 说明 |
| :--- | :--- | :--- | :--- |
| 趋势跟随 | `EMA` + `ADX` + `NATR` | `EMA(20/60)`, `ADX(14)`, `NATR(14)` | 用 ADX 过滤震荡，用 NATR 控制仓位 |
| 均值回归 | `BBANDS` + `RSI` | `BBANDS(20,2,2)`, `RSI(14)` | 价格触带 + RSI 极值联合触发 |
| 量价确认 | `OBV` + `MFI` + `ROC` | `MFI(14)`, `ROC(10)` | 方向信号由价给出，量能决定是否放行 |
| 跟踪止损 | `SAR` + `ATR` | `SAR(0.02,0.2)`, `ATR(14)` | 用 SAR 跟踪趋势，用 ATR 定义止损宽度 |

组合模板示例（趋势跟随）：

```python
ema_fast = ta.EMA(close, timeperiod=20, backend="rust")
ema_slow = ta.EMA(close, timeperiod=60, backend="rust")
adx = ta.ADX(high, low, close, timeperiod=14, backend="rust")
natr = ta.NATR(high, low, close, timeperiod=14, backend="rust")

if np.isnan(ema_fast[-1]) or np.isnan(adx[-1]) or np.isnan(natr[-1]):
    return

trend_up = ema_fast[-1] > ema_slow[-1]
trend_strong = adx[-1] >= 20
risk_ok = natr[-1] < 4.0

if trend_up and trend_strong and risk_ok:
    self.buy(symbol, 100)
```

组合模板示例（均值回归）：

```python
upper, middle, lower = ta.BBANDS(close, timeperiod=20, backend="rust")
rsi = ta.RSI(close, timeperiod=14, backend="rust")

if np.isnan(lower[-1]) or np.isnan(rsi[-1]):
    return

long_signal = close[-1] < lower[-1] and rsi[-1] < 30
exit_signal = close[-1] > middle[-1]
```

延伸阅读：
- [指标组合实战手册](../guide/talib_indicator_playbook.md)
- [可运行示例：45_talib_indicator_playbook_demo.py](https://github.com/akfamily/akquant/blob/main/examples/45_talib_indicator_playbook_demo.py)
- 可选真实数据模式：`python examples/45_talib_indicator_playbook_demo.py --data-source akshare --symbol sh600000 --start-date 20240101 --end-date 20260301`

## 5.6 高级风控管理 (Risk Management)

风控是量化交易的生命线。除了基本的止损，我们还需要更高级的仓位管理技术。

> **提示**：本节讨论的是**策略层**的风控（如根据波动率动态调整仓位）。如果你需要**引擎层**的硬性风控（如限制单股持仓不超过 10%、总杠杆不超过 1.5倍），请参考 **[4.8 风控引擎](04_backtest_engine.md#48-risk-engine)**。

### 5.6.1 凯利公式 (Kelly Criterion)

凯利公式用于计算在胜率和赔率已知的情况下，最优的下注比例。

$$ f^* = \frac{bp - q}{b} = \frac{p(b+1) - 1}{b} $$

其中：

*   $f^*$：最优仓位比例。
*   $b$：赔率（盈亏比）。
*   $p$：胜率。
*   $q$：败率 ($1-p$)。

**实战应用**：
通常使用**半凯利 (Half-Kelly)**，即只使用凯利公式计算出仓位的一半，以应对参数估计的不确定性。

### 5.6.2 波动率目标 (Volatility Targeting)

这是对冲基金最常用的风控手段。目标是保持组合的年化波动率恒定（例如 15%）。

$$ Weight_t = \frac{\text{Target Vol}}{\text{Realized Vol}_t} $$

*   当市场波动率低时，加杠杆，提高资金利用率。
*   当市场波动率高时，降仓位，控制风险暴露。

```python
# 示例：波动率目标仓位管理
current_vol = np.std(returns[-20:]) * np.sqrt(252) # 年化波动率
target_vol = 0.15 # 目标 15% 波动率

leverage = target_vol / current_vol
# 限制最大杠杆
leverage = min(leverage, 1.5)

self.order_target_percent(symbol, leverage)
```

### 5.6.3 止损逻辑 (Stop-Loss)

本章示例展示了一个简单的**固定比例止损**：

```python
# 计算浮动盈亏比例
pnl_pct = (bar.close - self.entry_price) / self.entry_price

# 止损检查
if pnl_pct < -self.stop_loss_pct:
    self.log(f"触发止损! 当前亏损: {pnl_pct:.2%}")
    self.close_position(symbol) # 清仓
```

## 5.7 事件回调处理 (Event Handling)

除了 `on_bar`，`AKQuant` 还提供了丰富的事件回调，让你能精确控制交易流程。

### 5.7.1 `on_order`

当订单状态发生变化时（如从 `Submitted` 到 `Filled`，或被风控/交易所 `Rejected`）触发。

```python
def on_order(self, order):
    if str(order.status) == "Filled":
        self.log(f"订单成交: {order.symbol} {order.filled_quantity} @ {order.average_filled_price}")
    elif str(order.status) == "Rejected":
        self.log(f"订单被拒: {order.reject_reason}", level="ERROR")
        # 可以在这里实现重试逻辑
```

### 5.7.2 `on_trade`

当发生实际成交时触发。与 `on_order` 的区别在于，一笔大单可能会分多次成交，每次成交都会触发 `on_trade`，而 `on_order` 更关注订单状态流转。

### 5.7.3 `on_expiry`

当引擎实际执行 `expiry_date` 驱动的到期结算或到期移除后触发。这个回调适合处理移仓换月、到期后重建仓位、期权到期后的后续逻辑等场景。

```python
def on_expiry(self, event):
    self.log(
        "到期结算: "
        f"{event['symbol']} "
        f"closed={event['quantity_closed']} "
        f"cash_flow={event['cash_flow']} "
        f"type={event.get('settlement_type')}"
    )
```

回调触发时，账户和持仓状态已经更新，因此你可以直接读取最新持仓。最小可运行示例见：`examples/49_on_expiry_demo.py`。

### 5.7.4 框架边界回调：把逻辑放在“正确阶段”

很多初学者会把盘前准备、日终归档、交易日调仓都写进 `on_bar`。这在简单脚本里能跑，但一旦进入多标的、多 session、live/backtest 复用的场景，就容易变得难维护。更稳妥的做法是把逻辑写在对应的框架边界回调里：

*   `on_before_trading(trading_date, timestamp)`: 本地交易日首次进入 `Normal` 会话时触发，适合做盘前检查、生成交易日级候选池。
*   `on_daily_rebalance(trading_date, timestamp)`: 与 `on_before_trading` 同阶段，但每个交易日最多一次，适合横截面统一调仓。
*   `on_after_trading(trading_date, timestamp)`: 离开 `Normal` 会话时触发，适合做日终归档、统计与报告。
*   `on_session_start(session, timestamp)` / `on_session_end(session, timestamp)`: 适合夜盘/日盘切换、session 级状态管理。
*   `on_portfolio_update(snapshot)`: 当账户权益、现金或持仓相关估值发生变化时增量触发，适合驱动监控面板。
*   `on_reject(order)`: 当订单首次进入 `Rejected` 时触发，适合做拒单分类、重试和人工告警。
*   `on_error(error, source, payload)`: 当用户回调抛异常时触发，可统一记录来源并决定是否继续。

最小可运行示例见：`examples/50_framework_hooks_demo.py`。如果你只需要理解“哪个阶段该做什么”，可以先记住这条经验：

1.  **盘前信号、当日候选池、统一调仓**：放 `on_before_trading` / `on_daily_rebalance`。
2.  **日终汇总、落盘、报表**：放 `on_after_trading`。
3.  **日盘夜盘切换、session 内状态重置**：放 `on_session_start` / `on_session_end`。
4.  **账户权益变化通知**：放 `on_portfolio_update`。
5.  **拒单与异常治理**：分别放 `on_reject` 和 `on_error`。

### 5.7.5 `on_event`：策略外的统一事件流

如果你需要把回测事件推送到日志系统、监控看板或告警服务，可在 `run_backtest` 入口直接传入 `on_event`，统一消费事件流。

```python
events = []
result = aq.run_backtest(
    data=data_feed,
    strategy=MyStrategy,
    symbols="AAPL",
    on_event=events.append,
)
```

该方式不要求改动策略类内部代码，适合将“交易逻辑”和“可观测性管道”分层维护。

---

## 5.8 调试与日志 (Debugging & Logging)

策略开发中最痛苦的莫过于逻辑不符合预期。`AKQuant` 提供了完善的日志系统。

*   `self.log(msg)`: 会自动打上当前回测时间的标签 `[2023-01-05 15:00:00] msg`。
*   **断点调试**: 由于 `AKQuant` 是纯 Python/Rust 混合，你完全可以在 PyCharm/VSCode 中打断点调试 `on_bar` 逻辑。

---

## 本章小结

1. 生命周期回调是策略执行的主骨架，`on_bar` 是核心决策入口。
2. 下单接口与风控规则必须协同设计，才能避免策略“能跑但不可交易”。
3. 事件回调与日志体系是策略调试和可观测性的基础设施。

## 课后练习

1. 给双均线策略新增一个成交量过滤条件并对比结果。
2. 在 `on_order` 中增加拒单分类统计，输出拒单原因分布。
3. 增加一个策略级最大回撤止损并验证触发逻辑。

## 常见错误与排查

1. 无交易发生：检查信号条件是否过严或数据窗口不足。
2. 订单被拒绝：核对现金、持仓、最小交易单位和交易方向约束。
3. 回测结果异常抖动：确认是否存在未来函数或未对齐的数据字段。
