# 第 16 章：Rust 指标全景与工程化使用

在前面的章节中，我们已经学习了数据、回测、策略、分析与实盘主线。本章把视角重新拉回策略内部最常用的一类工具：**技术指标 (Indicators)**。与“知道某个指标名字”相比，更重要的是学会把指标当作**可迁移、可验证、可工程化复用**的组件来使用。

## 学习目标

- 理解 AKQuant Rust 指标体系的使用边界，以及 `python -> rust` 迁移的推荐路径。
- 掌握指标输入、输出、warmup 与多输出解包的统一阅读方法。
- 能将趋势、动量、波动率、量价指标组合成最小可复现实验。

## 前置知识

- 已掌握第 5 章中的策略开发基础，知道指标会被放进什么样的交易逻辑中。
- 已掌握第 10 章中的结果分析方法，能够解释指标变化如何影响策略表现。

## 本章实践入口

- 主示例：[examples/45_talib_indicator_playbook_demo.py](https://github.com/akfamily/akquant/blob/main/examples/45_talib_indicator_playbook_demo.py)
- 进阶示例：[examples/60_custom_indicator_demo.py](https://github.com/akfamily/akquant/blob/main/examples/60_custom_indicator_demo.py), [examples/62_indicator_streaming_demo.py](https://github.com/akfamily/akquant/blob/main/examples/62_indicator_streaming_demo.py), [examples/61_indicator_visualization_export_demo.py](https://github.com/akfamily/akquant/blob/main/examples/61_indicator_visualization_export_demo.py)
- 对应指南：[AKQuant 指标全量说明](../guide/rust_indicator_reference.md)

## 快速运行与验收

```bash
python examples/45_talib_indicator_playbook_demo.py
```

验收要点：

1. 脚本可正常输出至少一组指标结果或对比信息。
2. 切换 `backend="python"` 与 `backend="rust"` 后，结果方向一致且可解释。
3. 能识别 warmup 导致的空值区段，并避免直接把无效值喂给策略信号。

## 16.1 为什么单独学习 Rust 指标体系

AKQuant 的指标接口并不只是“换一个更快的 TA-Lib 后端”。它更像一个统一层：

1. **接口统一**：同一套函数签名可切换 `backend="python"` 与 `backend="rust"`。
2. **迁移友好**：你可以先让旧策略在 Python 后端上对齐，再切换到 Rust 后端提速。
3. **工程化复用**：指标可以作为主信号、过滤器、风控尺度，甚至可视化与特征工程输入。

因此，本章关注的不是“把 103 个指标背下来”，而是学会三件真正重要的事：

- 指标**吃什么输入**；
- 指标**吐什么输出**；
- 指标在前若干根 K 线上的 **warmup 行为**是什么。

## 16.2 全量覆盖范围（当前 103 个）

- Momentum：8 个
- Moving Average & Transforms：59 个
- Trend：20 个
- Volatility：11 个
- Volume：5 个

完整逐项解释、参数口径与返回说明请始终以参考页为准：

- [Rust 指标全量说明（103 个）](../guide/rust_indicator_reference.md)

这意味着本章的定位不是“把字典搬进正文”，而是帮你建立**读指标、选指标、迁移指标**的方法。

## 16.3 学会“读指标”的统一方法

无论你看到的是 `EMA`、`MACD` 还是 `ATR`，都建议按同一模板理解：

1. **输入是什么**：是 `close`，还是 `high, low, close`，还是需要 `volume`。
2. **输出是什么**：返回单序列、双序列还是三序列。
3. **warmup 多长**：前多少根 K 线不能直接用于交易判断。
4. **策略角色是什么**：主信号、过滤器、风控尺度，还是确认信号。

### 16.3.1 输入结构

最常见的输入结构有三类：

- **单输入**：例如 `EMA(close)`、`RSI(close)`。
- **三输入**：例如 `ATR(high, low, close)`、`ADX(high, low, close)`。
- **四输入**：少数量价指标还会显式使用 `volume`。

如果输入结构看错，后面的结果解释几乎一定会偏掉。

### 16.3.2 输出结构

指标的输出并不总是“一列数字”。

- **单输出**：`EMA`、`RSI`、`ATR`
- **双输出**：`AROON`
- **三输出**：`MACD`、`BollingerBands`、`STOCH`

因此，多输出指标不能只记名字，还要记**解包顺序**。

### 16.3.3 warmup 不是小细节

指标在窗口未满时，结果往往是空值或不稳定值。对策略开发而言，这不是边缘问题，而是最常见的误用来源之一。

如果你在 warmup 阶段就直接发出交易信号，往往会出现两类假象：

1. 回测“看起来能跑”，但信号并不可靠；
2. Python 与 Rust 后端的对齐误差被误判成实现错误。

## 16.4 五大类指标怎么教、怎么用

### 16.4.1 趋势类：先判断方向，再过滤强度

- 方向判别：`EMA` / `SMA` / `TEMA` / `KAMA` / `SAR`
- 强度过滤：`ADX` / `ADXR` / `DX`
- 典型组合：`EMA + ADX + NATR`

教学上可以先让学生完成一件最小任务：**均线给方向，ADX 过滤弱趋势，NATR 控制仓位尺度**。这样一来，趋势、强度、风险三个角色都被引入了。

### 16.4.2 动量类：捕捉变化速度与过热过冷

- 速度/斜率：`ROC` / `ROCP` / `ROCR` / `ROCR100` / `MOM`
- 过热过冷：`RSI` / `CMO` / `WILLR`
- 典型组合：`BBANDS + RSI + MOM`

动量类指标最容易出现的问题是“只看信号方向，不看市场状态”。把它与波动率或趋势过滤器联用，通常比单独使用更稳。

### 16.4.3 波动率类：先定风险尺度，再谈仓位

- 范围与波动：`ATR` / `NATR` / `TRANGE` / `STDDEV` / `VAR`
- 通道类：`BollingerBands`
- 价格派生：`MEDPRICE` / `TYPPRICE` / `WCLPRICE` / `AVGPRICE` / `MIDPRICE`

波动率类指标特别适合做两类任务：

1. 给止损、止盈、移动保护定义动态阈值；
2. 把“行情变快了”这件事转化为可量化的仓位调整规则。

### 16.4.4 量价类：确认而不是替代主信号

- 趋势确认：`OBV` / `AD`
- 动量确认：`MFI` / `ADOSC`
- K 线力量：`BOP`

量价类指标常见的正确用法是“做确认层”，而不是直接替代价格主信号。这样更容易解释，也更适合教学。

### 16.4.5 数学变换类：为特征工程做准备

- 对数/指数：`LN` / `LOG10` / `LOG1P` / `EXP` / `EXPM1`
- 三角与双曲：`SIN` / `COS` / `TAN` / `ASIN` / `ACOS` / `ATAN` / `SINH` / `COSH` / `TANH`
- 代数运算：`ADD` / `SUB` / `MULT` / `DIV` / `MOD` / `POW` / `MAX2` / `MIN2`
- 规整变换：`ABS` / `SIGN` / `ROUND` / `CLIP` / `CLAMP01` / `SQ` / `CUBE` / `RECIP` / `INV_SQRT` / `DEG2RAD`

这一类指标在传统技术分析里不一定显眼，但在第 12 章和第 14 章那种“把信号送入模型或表达式引擎”的任务里很有价值。

## 16.5 三个最常见的工程坑位

### 16.5.1 warmup 区段误用

- 窗口不足时的结果不能直接拿来发单。
- 教学示例和作业里应明确要求先做空值过滤。

### 16.5.2 多输出解包顺序错误

- `MACD -> (macd, signal, hist)`
- `BollingerBands -> (upper, middle, lower)`
- `STOCH -> (slowk, slowd)`
- `AROON -> (aroondown, aroonup)`

如果顺序拿错，结果通常不会报错，但策略语义会悄悄失真，这比直接报错更危险。

### 16.5.3 迁移时直接切 Rust

推荐流程不是“一上来就换 Rust”，而是：

1. 先用 `backend="python"` 与旧策略结果对齐；
2. 再切到 `backend="rust"` 观察数值与绩效差异；
3. 最后再做性能与大规模批量实验。

## 16.6 标准教学脚手架

下面这段脚手架适合直接放进实验课，用于演示“同一套输入上并行计算多类指标”的最小流程：

```python
import numpy as np
from akquant import talib as ta

close = np.asarray(df["close"], dtype=float)
high = np.asarray(df["high"], dtype=float)
low = np.asarray(df["low"], dtype=float)
volume = np.asarray(df["volume"], dtype=float)

ema_fast = np.asarray(ta.EMA(close, timeperiod=20, backend="rust"), dtype=float)
ema_slow = np.asarray(ta.EMA(close, timeperiod=60, backend="rust"), dtype=float)
adx = np.asarray(ta.ADX(high, low, close, timeperiod=14, backend="rust"), dtype=float)
natr = np.asarray(ta.NATR(high, low, close, timeperiod=14, backend="rust"), dtype=float)
rsi = np.asarray(ta.RSI(close, timeperiod=14, backend="rust"), dtype=float)

# warmup 区段不可直接参与信号判断
if np.isnan([ema_fast[-1], ema_slow[-1], adx[-1], natr[-1], rsi[-1]]).any():
    return
```

你可以把这段模板理解为一个最小实验台：

- `EMA` 负责方向；
- `ADX` 负责强度；
- `NATR` 负责风险尺度；
- `RSI` 负责状态确认。

## 16.7 三类推荐实验

### 16.7.1 趋势实验：`EMA + ADX + NATR`

目标：构建一套最小趋势框架。

- `EMA(20)` 与 `EMA(60)` 判断方向；
- `ADX(14)` 过滤掉趋势强度过弱的区间；
- `NATR(14)` 用于决定仓位大小或止损距离。

这一实验最适合作为“指标不是堆砌，而是角色分工”的第一课。

### 16.7.2 震荡实验：`BBANDS + RSI`

目标：理解区间震荡与过热过冷。

- `BollingerBands` 给出上下轨；
- `RSI` 确认是否进入超买/超卖区域；
- 观察单独使用与联合使用时的信号差异。

### 16.7.3 迁移实验：`python -> rust`

目标：验证迁移流程，而不是直接追求更快。

建议步骤：

1. 先固定参数与数据集；
2. 用 `backend="python"` 记录一份基线结果；
3. 切到 `backend="rust"` 对比数值、信号点位与最终绩效；
4. 仅在结果口径一致后再讨论性能收益。

## 16.8 推荐教学路径

1. 第 1 周：先教 `EMA` / `RSI` / `ATR` 的输入、输出与 warmup。
2. 第 2 周：加入 `MACD` / `BBANDS` / `STOCH` 的多输出处理。
3. 第 3 周：引入 `ADX` / `NATR` / `SAR` 做风险过滤。
4. 第 4 周：做一次 `python -> rust` 迁移实验与回归验证。
5. 第 5 周：把数学变换类指标接入简单特征工程实验。

## 本章小结

### 必须掌握

- Rust 指标体系已经覆盖策略开发中最常用的核心技术面能力。
- 真正决定教学效果的不是指标数量，而是输入、输出、warmup 与角色分工的结构化理解。

### 理解即可

- 数学变换类指标、流式指标处理与自定义指标开发，是从技术分析过渡到特征工程的重要桥梁。

### 实践提醒

- 做指标迁移时先对齐结果，再切后端提速。
- 完整指标字典、参数说明与返回结构请始终以参考页为准：[Rust 指标全量说明（103 个）](../guide/rust_indicator_reference.md)。

## 课后练习

### 基础题

1. 任选 `EMA`、`RSI`、`ATR` 三个指标，写出它们各自的输入、输出和 warmup 口径。

### 应用题

1. 用 `EMA + ADX + NATR` 设计一个最小趋势策略过滤框架，并解释每个指标承担的角色。

### 综合题

1. 对同一数据集分别运行 `backend="python"` 与 `backend="rust"`，比较数值、信号点位与回测结果差异，并写出迁移结论。

## 常见错误与排查

1. 指标结果全是空值：优先检查窗口长度、输入数组长度和 warmup 区段是否被误当成有效值。
2. 多输出指标结果看起来“能跑但不对”：检查解包顺序是否与文档一致。
3. 切换到 Rust 后结果变化很大：先回到 Python 后端做基线对齐，再排查数据口径、空值处理和参数设置。
