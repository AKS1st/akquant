# Timezone Handling Guide

AKQuant is a backtesting framework supporting multiple markets and instruments. To ensure precise alignment of time series, the framework's core uses **UTC timestamps (nanoseconds)** uniformly. However, when dealing with specific markets (such as China A-shares), correct timezone settings are crucial for data alignment and log readability.

This document guides you on how to correctly handle data timezones, backtest configurations, and time conversions in strategies.

## 1. Core Principles

1.  **Internal UTC**: All interactions between the engine's core (`Rust`) and the Python layer are based on UTC timestamps.
2.  **Input Normalization**: Timezone-aware input is converted to UTC storage. Tz-naive input does **not** follow the configured `timezone`; it still defaults to `Asia/Shanghai` during loading unless you localize it explicitly.
3.  **Display-Layer Conversion**: Structured time fields stay in UTC by default; only strategy helpers or your own display code convert them into the configured `timezone`.

## 2. Data Preparation and Timezones

When preparing backtest data (DataFrame), you have two options:

### Method A: Use Naive Datetime - **Recommended**

If your data is local time (e.g., Beijing Time) and has no timezone information (tz-naive), AKQuant defaults it to `Asia/Shanghai` during loading.

- If the data is already Beijing time / China market data, you can usually pass it directly.
- If the data belongs to another timezone, you should localize it explicitly first; changing `run_backtest(timezone=...)` does **not** change how tz-naive input is interpreted.

**Example: Constructing A-share 1-minute bar data**

```python
import pandas as pd
from datetime import timedelta

# Generate naive time series (default is Beijing Time)
# Example: 2023-01-01 09:31:00
rng = pd.date_range(
    start="2023-01-01 09:31",
    end="2023-01-01 11:30",
    freq="1min"
)

# Create DataFrame
# Index must be datetime type
df = pd.DataFrame({
    "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1000
}, index=rng)

# At this point, df.index.tz is None
```

### Method B: Use Aware Datetime

If your data already has timezone information (e.g., data obtained from certain APIs), AKQuant will convert it directly to UTC. Please ensure the timezone information is correct.

```python
# Time series with timezone
rng = pd.date_range(
    start="2023-01-01 09:31",
    periods=100,
    freq="1min",
    tz="Asia/Shanghai"  # Explicitly specify timezone
)
```

### Important: Timestamp Setting for Daily Data

For daily data (1D), to correctly align with minute data (1m) in backtesting (avoiding look-ahead bias), **it is strongly recommended to set the daily timestamp to the closing time of the day** (15:00 for A-shares).

*   If set to 00:00, daily data might "appear" before the minute data of the day, or cause confusion during alignment.
*   Setting to 15:00 ensures the daily Bar is completed only after the day's trading ends.

```python
# Daily data index example
ts_daily = pd.Timestamp("2023-01-01 15:00:00")  # Beijing Time 15:00
```

## 3. Backtest Configuration

Specify the default timezone for backtesting via the `timezone` parameter during `run_backtest` or `BacktestEngine` initialization.

This parameter is mainly used for:

1. `self.now`, `self.to_local_time(...)`, and `self.format_time(...)`
2. Timer alignment and scheduling
3. Daily performance aggregation such as `daily_returns`, volatility, Sharpe / Sortino / VaR / CVaR, which now follows the configured timezone's local calendar day
4. It does **not** change the default interpretation of tz-naive input during loading; naive input still defaults to `Asia/Shanghai`

```python
from akquant.backtest import run_backtest

results = run_backtest(
    data=data_feed,
    strategy=MyStrategy,
    timezone="Asia/Shanghai",  # Default timezone for strategy-local time helpers
    # ...
)
```

### Structured Logging And ISO Fields

After the time-semantics refactor, AKQuant uses:

- `event_time`: UTC nanosecond timestamp
- `event_time_iso`: UTC ISO 8601 string

This means:

- structured logs and JSON output no longer default to local-time strings
- `bar.timestamp_iso`, `tick.timestamp_iso`, `trade.timestamp_iso`, `order.created_at_iso`, and `order.updated_at_iso` are all UTC ISO 8601 values
- if you want human-readable strategy-local output, format it explicitly with `self.format_time(...)`

If you print `timestamp_iso` directly, expect UTC output such as `2025-01-02T07:00:00Z`, not exchange-local or strategy-local wall-clock time.

## 4. Time Processing in Strategies

In the strategy's `on_bar` callback, `bar.timestamp` is an integer (int64) representing the **UTC nanosecond timestamp**. If you need to print the current time in logs or make logical decisions based on time (e.g., trade only in the afternoon), you need to convert it to local time.

### Method 2: Use Strategy Helper Methods (Recommended)

AKQuant provides convenient helper methods in the `Strategy` base class, automatically converting using the configured timezone.

```python
class MyStrategy(Strategy):
    def on_bar(self, bar: Bar):
        # 1. Get local time object (pd.Timestamp)
        ts = self.to_local_time(bar.timestamp)

        # 2. Directly get formatted string (default "%Y-%m-%d %H:%M:%S")
        ts_str = self.format_time(bar.timestamp)
