# 第 2 章：编程生存指南 (Programming Survival Guide)

量化投资是金融与计算机的交叉学科。对于金融背景的同学来说，编程往往是最大的拦路虎。本章不求把你培养成软件工程师，只求教给你在量化战场上**生存**所需的最小技能集。

## 学习目标

- 掌握量化开发最常用的 Pandas、NumPy 与 Matplotlib 基础操作。
- 理解向量化、类型注解和最小工程规范在量化代码中的实际价值。
- 形成调试、版本控制与并行计算的入门工程化意识。

## 前置知识

- 掌握 Python 基本语法、函数与列表/字典等数据结构。
- 能读懂简单的 DataFrame 与数组示例。

## 本章实践入口

- 主示例：[examples/textbook/ch02_programming.py](https://github.com/akfamily/akquant/blob/main/examples/textbook/ch02_programming.py)
- 进阶示例：[examples/17_readme_demo.py](https://github.com/akfamily/akquant/blob/main/examples/17_readme_demo.py)
- 对应指南：[Python 基础](../guide/python_basics.md)

## 快速运行与验收

```bash
python examples/textbook/ch02_programming.py
```

验收要点：

1. 脚本完整运行，无语法错误或依赖错误。
2. 输出包含 Pandas、NumPy 或类型注解相关演示结果。
3. 能独立修改一段参数并重新运行验证结果变化。

## 2.1 Python for Quant

Python 之所以成为量化领域的霸主，归功于其强大的科学计算生态。你必须熟练掌握以下三个库：**Pandas**, **NumPy**, **Matplotlib**。

### 2.1.1 Pandas：表格处理神器

Pandas 是 Python 中的 Excel，但比 Excel 强大得多。它建立在两个核心数据结构之上：**Series** 是一列带索引的数据，而 **DataFrame** 则是一张表格，由多列数据组成，同时带有行索引和列索引。在量化中，我们通常将时间 (`datetime`) 作为索引，这样的 DataFrame 就被称为**时间序列 (Time Series)**。

**核心操作**：

1.  **索引与切片 (Slicing)**：
    *   `df.loc["2023-01-01":"2023-01-31"]`: 获取一月的所有数据。
    *   `df.iloc[-1]`: 获取最后一行数据。

2.  **重采样 (Resampling)**：
    *   `df.resample("1W").last()`: 将日线数据转换为周线数据（取每周最后一天）。
    *   `df.resample("5min").ohlc()`: 将 Tick 数据聚合为 5分钟 K 线。

3.  **滚动窗口 (Rolling)**：
    *   `df["close"].rolling(20).mean()`: 计算 20 日移动平均线 (MA20)。
    *   `df["close"].rolling(20).std()`: 计算 20 日波动率。

4.  **缺失值处理 (Handling Missing Data)**：
    *   `df.fillna(method="ffill")`: 前向填充（用昨天的数据填补今天的空缺），这是金融数据最常用的填充方式。
    *   `df.dropna()`: 直接丢弃包含空值的行。

### 2.1.2 NumPy：向量化思维

向量化是初学者最难转变的思维定势。**人类思维 (Loop)** 习惯逐行读取数据、计算、再写入下一行；而**量化思维 (Vectorization)** 则直接操作整个向量（列）。以计算 100 万个数据的平方为例，前者要写一个 100 万次的循环，既慢又代码冗余，后者只需 `arr ** 2` 一行代码，底层由 C/Fortran 优化，速度比 Loop 快 10-100 倍。

与向量化相辅相成的是**广播机制 (Broadcasting)**：NumPy 允许不同形状的数组进行数学运算，例如 `prices - 100`，会自动将 100 减去数组中的每一个元素。

### 2.1.3 Matplotlib：数据可视化

虽然现在有 Plotly 等交互式库，但 Matplotlib 依然是基础。
`AKQuant` 的 `plot_result` 就是基于 Matplotlib 开发的。

**常用功能**：

*   `plt.plot(x, y)`: 绘制折线图。
*   `plt.bar(x, y)`: 绘制柱状图。
*   `plt.subplots()`: 创建多子图（例如上图画 K 线，下图画成交量）。

## 2.2 Rust 概念入门 (Conceptual)

`AKQuant` 的底层回测引擎是由 Rust 编写的。你不需要会写 Rust，但了解其核心概念有助于你理解报错信息和 API 设计。

### 2.2.1 为什么是 Rust?

选择 Rust 主要出于两点考量。其一是**速度**：Rust 与 C++ 相当，比 Python 快 10-100 倍，这对于遍历数百万根 K 线的回测至关重要。其二是**安全**：Rust 的编译器极其严格，杜绝了“空指针异常”和“内存泄漏”，这意味着 `AKQuant` 极其稳定，很难崩溃。

### 2.2.2 内存安全与所有权 (Ownership)

在 Python 中，不仅有垃圾回收 (GC)，变量还只是对象的引用；而在 Rust 中，每个值都有一个**所有者 (Owner)**。所有权主要通过两条规则体现：**Move** 指当你把值赋给另一个变量时，所有权就转移了，原来的变量随之失效，从而避免了“悬垂指针”；**Borrow** 则允许你“借用”数据（引用），但必须遵守规则，即同一时间只能有一个可变借用。这听起来很复杂，但在 `AKQuant` 的 Python 接口中，你通常感受不到它的存在，因为底层已经处理好了。

### 2.2.3 类型系统 (Type System)

Python 是动态类型（变量可以是任何东西），Rust 则是静态类型（变量类型必须确定）。在 Rust 的类型系统中，有两个泛型容器格外值得理解。其一是 **`Option<T>`**，它代表“可能有值，也可能为空”，对应 Python 的 `Optional[T]` 或 `None`——例如在策略中，`get_position(symbol)` 返回的可能就是 `Option`，如果没持仓就返回 `None`。其二是 **`Result<T, E>`**，它代表“成功返回 T，或失败返回错误 E”——例如下单函数可能会返回 `Result`，你需要检查是否下单成功。

## 2.3 工程化思维 (Engineering Mindset)

写策略不仅仅是写数学公式，更是构建一个软件系统。

### 2.3.1 版本控制 (Git)

永远不要把文件命名为 `strategy_final_v2_really_final.py`。
学会使用 **Git** 来管理代码的历史版本。

*   `git init`: 初始化仓库。
*   `git add .` & `git commit -m "update strategy"`: 保存快照。
*   `git checkout`: 回滚到之前的版本。

### 2.3.2 调试技巧 (Debugging)

*   **Print Debugging**：最简单但最有效。在关键位置打印变量值。
*   **断点调试**：使用 VS Code 的调试功能，设置断点，单步执行，查看变量状态。这比 print 高效得多。

## 2.4 向量化进阶 (Advanced Vectorization)

在量化中，速度就是生命。除了基本的数组运算，你还需要掌握更高级的技巧。

### 2.4.1 条件选择：`np.where`

替代 Python 的 `if-else`。
```python
# 如果收益率 > 0，标记为 1 (Win)，否则为 0 (Loss)
wins = np.where(returns > 0, 1, 0)
```

### 2.4.2 快速查找：`np.searchsorted`

在一个有序数组中查找插入位置（二分查找），复杂度 $O(\log N)$。
这在回测撮合引擎中非常有用：比如查找订单价格在 LOB 中的位置。

### 2.4.3 表达式加速：`pd.eval`

Pandas 在计算复杂表达式时会产生大量中间临时变量，占用内存且拖慢速度。`pd.eval` 使用 NumExpr 后端，一次性计算整个表达式。

```python
# 传统写法
df['result'] = (df['A'] + df['B']) * (df['C'] - df['D'])

# 加速写法
df.eval('result = (A + B) * (C - D)', inplace=True)
```

## 2.5 设计模式 (Design Patterns)

虽然量化代码不像企业级软件那么庞大，但良好的设计模式能让策略更易扩展。

1.  **工厂模式 (Factory)**：用于创建不同类型的对象。
    *   例如 `IndicatorFactory.create("RSI", period=14)`，根据字符串创建具体的指标对象，避免写一堆 `if type == "RSI": ... elif ...`。
2.  **单例模式 (Singleton)**：确保全局只有一个实例。
    *   例如 `GlobalConfig` 或 `Logger`，整个回测系统中只需要一份配置。
3.  **观察者模式 (Observer)**：解耦事件源与处理逻辑。
    *   `AKQuant` 的核心架构就是观察者模式。`EventBus` 是被观察者，`Strategy` 和 `RiskManager` 是观察者。当有新行情 (`MarketEvent`) 时，总线通知所有观察者，而不是硬编码调用 `strategy.on_bar()`。

## 2.6 并行计算 (Parallel Computing)

Python 的全局解释器锁 (GIL) 限制了多线程的 CPU 密集型任务。但在参数优化 (Grid Search) 时，我们可以利用多进程 (Multiprocessing) 跑满所有 CPU 核心。

```python
from multiprocessing import Pool

def backtest_one_param(param):
    # 回测逻辑...
    return sharpe_ratio

if __name__ == '__main__':
    params = [10, 20, 30, ..., 100]
    with Pool(processes=8) as pool:
        results = pool.map(backtest_one_param, params)
```

`AKQuant` 的优化模块已内置了并行计算支持。

## 2.7 代码演练

下面的脚本演示了 Pandas 和 NumPy 的核心操作，以及如何在 Python 中使用 Type Hints 模拟强类型编程。

```python
--8<-- "examples/textbook/ch02_programming.py"
```

---

## 本章小结

### 必须掌握

- 量化代码的核心能力是数据处理、数值计算与结果可视化。
- 向量化思维、类型注解与最小工程规范能显著降低策略迭代成本。

### 理解即可

- Rust 的所有权与类型系统有助于理解 AKQuant 的接口设计与报错语义。

### 实践提醒

- 优先练熟索引、滚动窗口、缺失值处理与调试，再追求更复杂的模式。

## 主线推进

本章没有改写贯穿全书的最小双均线策略本身，而是为它备齐了“施工工具”。第 1 章跑通的那个 MA5/MA20 策略，在 `on_bar` 回调里通过 `get_history(count=self.long_window, field="close")` 取最近收盘价、计算两条均线并比较其大小来产生金叉/死叉信号——本章正是把这背后的通用能力逐一拆解：用 Pandas 的滚动窗口 `df["close"].rolling(20).mean()` 计算均线、用向量化思维一次性处理整列数据，都在 2.1 节得到系统讲解。理解了向量化、缺失值处理与时间序列索引，你才能在后续章节里读懂、修改并最终自己写出这条主线策略的信号逻辑；理解了 Rust 的所有权与 `Option`/`Result`，你也能在调用 `get_position`、下单等接口时正确处理“可能为空”和“可能失败”的返回值。至此，主线策略从“能跑通的示例”推进到了“看得懂每一行的可改造对象”。

## 延伸阅读

**经典著作**

- McKinney, W. *Python for Data Analysis*（《利用 Python 进行数据分析》，第 3 版），O'Reilly Media, 2022 —— Pandas 作者亲笔，系统讲解 Series/DataFrame、索引切片、重采样与缺失值处理，可与本章 2.1 对照精读。
- Hilpisch, Y. J. *Python for Finance: Mastering Data-Driven Finance*（第 2 版），O'Reilly Media, 2018 —— 以金融场景贯穿 NumPy 向量化与 pandas 数据处理，呼应本章 2.1 与 2.4 的向量化进阶。
- Klabnik, S., & Nichols, C. *The Rust Programming Language*（第 2 版），No Starch Press, 2023 —— Rust 官方教程，权威讲解所有权、借用与 `Option`/`Result` 类型系统，对应本章 2.2 的概念。

**官方文档与工具**

- [pandas 官方文档](https://pandas.pydata.org/docs/) —— 本章 2.1 涉及的索引、重采样、滚动窗口与 `pd.eval` 的权威参考。
- [NumPy 官方文档](https://numpy.org/doc/stable/) —— 配合本章 2.1.2 与 2.4 理解广播、`np.where`、`np.searchsorted` 等向量化操作。
- [Matplotlib 官方文档](https://matplotlib.org/stable/) —— 对应本章 2.1.3 的可视化基础。
- [Git 官方文档](https://git-scm.com/doc) —— 对应本章 2.3.1 的版本控制实践。

**本书相关**

- [Python 基础](../guide/python_basics.md) —— 巩固本章 2.1 的 Pandas/NumPy 入门操作。
- [快速开始](../start/quickstart.md) —— 把本章工程化与向量化技能落到第一个可运行的 AKQuant 策略上。

## 课后练习

### 基础题

1. 把示例中的滚动窗口从 `20` 改为 `10`，观察输出差异。

### 应用题

1. 给一个函数补充完整类型注解并运行静态检查。

### 综合题

1. 用 `multiprocessing.Pool` 改写一个小型参数扫描脚本。

## 常见错误与排查

1. 切片结果异常：优先检查 `loc` 与 `iloc` 的使用场景是否混淆。
2. 维度报错：确认 NumPy 向量形状一致后再计算。
3. 进程卡死：把多进程入口放在 `if __name__ == "__main__":` 下。
