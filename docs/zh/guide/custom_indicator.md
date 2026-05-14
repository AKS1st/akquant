# 自定义指标指南

本页聚焦一个问题：当 AKQuant 内置指标不够用时，如何安全地编写、注册并维护你自己的指标。

适用场景：

- 私有因子或策略专用信号；
- 需要在 pandas 上快速验证的原型指标；
- 需要在事件流里逐 Bar 更新状态的增量指标；
- 需要配合热启动一起恢复的状态型指标。

## 先做判断

在 AKQuant 中，常见有三种“指标扩展”需求，它们不是同一件事：

| 需求 | 推荐路径 | 典型用法 |
| :--- | :--- | :--- |
| 给策略增加一个私有信号 | 自定义 `Indicator` / 自定义增量对象 | 在 `Strategy` 中注册 |
| 用 pandas 一次性计算整段历史 | `indicator_mode="precompute"` | `register_precomputed_indicator(...)` |
| 逐 Bar / 逐 Tick 维护状态 | `indicator_mode="incremental"` | `register_incremental_indicator(...)` |
| 给 `akquant.talib` 增加一个新函数名 | 修改 Python/Rust 兼容层源码 | 不属于运行时动态注册 |

如果你的目标只是“在策略里用一个自己的指标”，通常不需要修改 `akquant.talib`。

## 路径一：预计算指标

当你的指标更适合一次性对完整 `DataFrame` 计算时，优先使用 `precompute` 模式。

### 最小示例

```python
from akquant import Indicator, Strategy


class PrecomputeMomentumStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.indicator_mode = "precompute"
        self.mom10 = Indicator(
            "mom10",
            lambda df: df["close"] - df["close"].shift(10),
        )
        self.register_precomputed_indicator("mom10", self.mom10)

    def on_bar(self, bar):
        value = self.mom10.get_value(bar.symbol, bar.timestamp)
        if value == value and value > 0:
            self.buy(bar.symbol, 100)
```

### 何时适合

- 指标天然可向量化；
- 主要依赖 pandas `rolling` / `shift` / `ewm`；
- 更关心回测开发效率，而不是在线增量更新；
- 同一个 `symbol` 的整段历史可以提前准备好。

### 注意事项

- `Indicator(name, fn, **kwargs)` 的核心输入是一个返回 `pd.Series` 的函数；
- `get_value(symbol, timestamp)` 会从缓存序列中按时间取值；
- 指标会按 `symbol` 缓存结果，适合同一回测里重复访问。

## 路径二：增量指标

如果你希望指标在事件流中逐步更新，推荐使用 `incremental` 模式。

### 最小示例

```python
from collections import deque

import pandas as pd
from akquant import Indicator, Strategy


class MyMomentum(Indicator):
    def __init__(self, period: int = 10):
        super().__init__("my_momentum", lambda df: df["close"] - df["close"].shift(period))
        self.period = period
        self.buffer: deque[float] = deque(maxlen=period)
        self._current_value = float("nan")

    def update(self, value: float) -> float:
        if pd.isna(value):
            return self._current_value
        self.buffer.append(float(value))
        if len(self.buffer) < self.period:
            self._current_value = float("nan")
        else:
            self._current_value = self.buffer[-1] - self.buffer[0]
        return self._current_value

    @property
    def value(self) -> float:
        return self._current_value


class IncrementalMomentumStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.indicator_mode = "incremental"

    def on_start(self):
        self.register_incremental_indicator(
            "mom10",
            indicator_factory=lambda: MyMomentum(period=10),
            source="close",
            symbols=["AAPL", "MSFT"],
            warmup_bars=10,
        )

    def on_bar(self, bar):
        value = self.mom10.value
        if value == value and value > 0:
            self.buy(bar.symbol, 100)
```

### 为什么推荐 `indicator_factory`

多标的策略里，增量指标通常都有内部状态。如果多个 `symbol` 共用同一个实例，状态很容易串线。

因此，推荐写法是：

```python
self.register_incremental_indicator(
    "mom10",
    indicator_factory=lambda: MyMomentum(period=10),
    source="close",
    symbols=["AAPL", "MSFT"],
)
```

而不是：

```python
self.mom10 = MyMomentum(period=10)
self.register_incremental_indicator("mom10", self.mom10, source="close")
```

后者更适合单标的或临时实验。

### `source` 代表什么

`source` 指定框架从行情对象里拿哪个字段喂给指标。最常见的是：

- `source="close"`
- `source="open"`
- `source="high"`
- `source="low"`
- `source="volume"`

如果你的指标需要多输入，建议优先参考策略手册中的增量接口约定，并确保你的 `update(...)` 参数顺序与框架喂入顺序一致。

## `warmup_bars` 怎么用

`warmup_bars` 用于在正式事件流开始前，先使用 `start_time` 之前的历史 Bar 预热指标。

适合以下场景：

- 你希望第一根有效 Bar 就拿到完整指标值；
- 指标依赖窗口历史，如 `period=20`；
- 你不想在 `on_bar` 里手工跳过前 N 根。

推荐示例可参考：

- [58_incremental_bootstrap_demo.py](https://github.com/akfamily/akquant/blob/main/examples/58_incremental_bootstrap_demo.py)
- [60_custom_indicator_demo.py](https://github.com/akfamily/akquant/blob/main/examples/60_custom_indicator_demo.py)

## 热启动与序列化

如果你的策略会使用 `run_warm_start`，自定义指标需要考虑状态持久化。

原则如下：

- 纯 Python 简单对象通常可直接 `pickle`；
- 如果指标里持有文件句柄、网络连接、线程锁等对象，需自行处理；
- 必要时实现 `__getstate__` 和 `__setstate__`，只保存必要状态。

例如：

```python
def __getstate__(self):
    state = self.__dict__.copy()
    return state


def __setstate__(self, state):
    self.__dict__.update(state)
```

更多背景见：[热启动指南](../advanced/warm_start.md)。

## 与 `akquant.talib` 的边界

很多用户会把“自定义策略指标”和“扩展 `akquant.talib`”混在一起。建议按下面理解：

- `akquant.talib`：内置 TA-Lib 风格兼容层，主要服务于已有函数式指标调用；
- 自定义策略指标：服务于你的具体策略，可直接注册到 `Strategy`；
- 新增 Rust 高性能指标：需要改源码、重新编译，不是运行时热插拔。

如果你只是要一个策略内的私有信号，优先写自定义指标，而不是去扩展 `akquant.talib`。

## 常见误区

- 误区 1：所有自定义指标都必须继承 `Indicator`
  - 不是。预计算场景可以直接用 `Indicator(name, fn)`；增量场景也可以注册自定义对象，只要接口契合。
- 误区 2：多标的一定可以共用一个增量实例
  - 不建议。正式策略优先 `indicator_factory`。
- 误区 3：`warmup_bars=20` 会重复消费第一根正式 Bar
  - 不会。预热只使用正式开始前的历史数据。
- 误区 4：自定义指标自然支持热启动
  - 不一定。需要确认对象可 `pickle`。
- 误区 5：策略自定义指标和 `akquant.talib` 扩展是一回事
  - 不是，二者面向的层级不同。

## 选择建议

| 你的目标 | 建议方案 |
| :--- | :--- |
| 先快速验证一个想法 | `Indicator(name, fn)` + `precompute` |
| 单标的逐 Bar 更新 | `incremental` + 单实例 |
| 多标的正式策略 | `incremental` + `indicator_factory` |
| 首根有效 Bar 就要有值 | 增量模式 + `warmup_bars` |
| 需要断点续跑 | 确保指标状态可序列化 |
| 需要极致性能 | 再考虑 Rust 指标实现 |

## 推荐阅读

- [策略开发手册](./strategy.md)
- [热启动指南](../advanced/warm_start.md)
- [AKQuant 指标全量说明](./rust_indicator_reference.md)
- [指标组合实战手册](./talib_indicator_playbook.md)
- [可运行示例：60_custom_indicator_demo.py](https://github.com/akfamily/akquant/blob/main/examples/60_custom_indicator_demo.py)
