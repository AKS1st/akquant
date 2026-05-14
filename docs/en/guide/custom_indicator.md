# Custom Indicator Guide

This page answers one practical question: when built-in indicators are not enough, how do you write, register, and maintain your own indicators in AKQuant?

Typical use cases:

- private factors or strategy-specific signals;
- rapid prototypes built on pandas;
- stateful indicators updated bar by bar in the event stream;
- indicators that must survive warm-start resume.

## Start With The Right Scope

In AKQuant, these are related but different tasks:

| Goal | Recommended path | Typical API |
| :--- | :--- | :--- |
| Add a private signal to a strategy | custom `Indicator` / custom incremental object | register on `Strategy` |
| Compute a full series from a `DataFrame` | `indicator_mode="precompute"` | `register_precomputed_indicator(...)` |
| Maintain state bar by bar | `indicator_mode="incremental"` | `register_incremental_indicator(...)` |
| Add a new name to `akquant.talib` | modify the compatibility layer source | not runtime plugin registration |

If your goal is simply "use my own indicator inside a strategy", you usually do not need to extend `akquant.talib`.

## Path 1: Precomputed Indicators

Use `precompute` mode when the indicator is naturally vectorized over the full `DataFrame`.

### Minimal example

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

### Good fit when

- the indicator is naturally vectorized;
- you want to reuse pandas `rolling`, `shift`, or `ewm`;
- development speed matters more than streaming-style updates;
- each symbol has a full history slice available up front.

### Notes

- `Indicator(name, fn, **kwargs)` expects a function returning a `pd.Series`;
- `get_value(symbol, timestamp)` reads from the cached series;
- results are cached per symbol.

## Path 2: Incremental Indicators

Use `incremental` mode when the indicator should evolve inside the event stream.

### Minimal example

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

## Why `indicator_factory` is recommended

In a multi-symbol strategy, incremental indicators usually carry internal state. Reusing one instance across multiple symbols can mix state and produce incorrect results.

Recommended:

```python
self.register_incremental_indicator(
    "mom10",
    indicator_factory=lambda: MyMomentum(period=10),
    source="close",
    symbols=["AAPL", "MSFT"],
)
```

Single-instance form, better for quick single-symbol experiments:

```python
self.mom10 = MyMomentum(period=10)
self.register_incremental_indicator("mom10", self.mom10, source="close")
```

## What `source` means

`source` tells the framework which field from the market event should be fed into the indicator. Common choices:

- `source="close"`
- `source="open"`
- `source="high"`
- `source="low"`
- `source="volume"`

If your indicator needs multiple inputs, align your `update(...)` signature with the incremental input mode expected by the framework.

## Using `warmup_bars`

`warmup_bars` bootstraps the incremental indicator with bars before `start_time`.

Use it when:

- you want a valid value on the first active bar;
- your indicator depends on a rolling window;
- you do not want to manually skip the first N bars inside `on_bar`.

Runnable example:

- [58_incremental_bootstrap_demo.py](https://github.com/akfamily/akquant/blob/main/examples/58_incremental_bootstrap_demo.py)
- [60_custom_indicator_demo.py](https://github.com/akfamily/akquant/blob/main/examples/60_custom_indicator_demo.py)

## Warm Start And Serialization

If the strategy uses `run_warm_start`, your custom indicator must preserve its internal state correctly.

Practical rules:

- simple Python objects are often pickle-compatible already;
- if the indicator stores file handles, sockets, locks, or other non-serializable objects, handle them explicitly;
- implement `__getstate__` and `__setstate__` when needed.

Example:

```python
def __getstate__(self):
    state = self.__dict__.copy()
    return state


def __setstate__(self, state):
    self.__dict__.update(state)
```

See also: [Warm Start Guide](../advanced/warm_start.md).

## Boundary With `akquant.talib`

Many users mix up "custom strategy indicators" and "extending `akquant.talib`". A practical mental model:

- `akquant.talib`: built-in TA-Lib-style compatibility layer;
- custom strategy indicators: strategy-local building blocks registered on `Strategy`;
- new Rust high-performance indicators: source-level extension plus recompilation, not runtime hot-plugging.

If you only need a private signal inside one strategy, prefer a custom strategy indicator instead of extending `akquant.talib`.

## Common Pitfalls

- Pitfall 1: every custom indicator must inherit from `Indicator`
  - Not always. `Indicator(name, fn)` is enough for many precompute cases.
- Pitfall 2: one incremental instance can be shared safely across symbols
  - Usually no. Prefer `indicator_factory` for production multi-symbol strategies.
- Pitfall 3: `warmup_bars=20` double-consumes the first active bar
  - It does not. Warmup only uses history before the active start boundary.
- Pitfall 4: custom indicators automatically work with warm start
  - Not guaranteed. Verify serialization.
- Pitfall 5: strategy-local indicators and `akquant.talib` extensions are the same thing
  - They solve different problems at different layers.

## Recommendation Matrix

| Goal | Recommended approach |
| :--- | :--- |
| Validate an idea quickly | `Indicator(name, fn)` + `precompute` |
| Single-symbol bar-by-bar state | `incremental` + single instance |
| Multi-symbol production strategy | `incremental` + `indicator_factory` |
| Need valid values on the first active bar | incremental + `warmup_bars` |
| Need resumable state | ensure the indicator is serializable |
| Need maximum performance | consider a Rust implementation later |

## Further Reading

- [Strategy Guide](./strategy.md)
- [Warm Start Guide](../advanced/warm_start.md)
- [AKQuant Indicator Reference](./rust_indicator_reference.md)
- [Indicator Playbook](./talib_indicator_playbook.md)
- [Runnable example: 60_custom_indicator_demo.py](https://github.com/akfamily/akquant/blob/main/examples/60_custom_indicator_demo.py)
