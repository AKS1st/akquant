# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- 策略交易日边界回调已硬切改名：`before_trading(trading_date, timestamp)` 更名为 `on_before_trading(trading_date, timestamp)`，`after_trading(trading_date, timestamp)` 更名为 `on_after_trading(trading_date, timestamp)`。
- 旧回调名不再保留兼容别名；升级到当前版本后，若策略仍实现 `before_trading` / `after_trading`，将不会再被框架触发，请同步迁移到新名称。
- 中英文策略指南现已补齐 `on_xxx` 回调总览、类风格/函数式对照、触发时序图与示例入口，覆盖 `on_resume`、`on_reject`、`on_session_*`、`on_before_trading/on_after_trading`、`on_daily_rebalance`、`on_portfolio_update`、`on_error`、`on_timer`、`on_train_signal` 等回调。
- 教材第 5 章与教材目录页现已同步补充完整 `on_xxx` 回调地图、学习路径与相关示例入口，便于用户从教材直接理解各类回调的职责边界。
- 示例体系已补充 `examples/50_framework_hooks_demo.py` 与 `examples/51_class_tick_callbacks_demo.py`，分别覆盖框架边界钩子与类风格 `on_tick` 的最小可运行案例。

### Fixed
- 修复 `on_timer` / `add_daily_timer` 场景下，订单级 `fill_policy={"price_basis":"close","bar_offset":0,"temporal":"same_cycle"}` 未在当日 timer 事件内生效的问题；相关卖单现在会按当日 timer 时间与当日 close 成交，不再延后到下一交易日。
- 修复 framework 内部 `__framework_rebalance__` / `__framework_boundary__` timer 被误参与 same-cycle 撮合与终态统计的问题，避免出现 `+1ns` 的伪成交、partial fill 被过早补满，以及权益曲线尾部多出额外采样点。

## [0.2.14] - 2026-04-21

### Added
- 新增 `on_expiry` / `on_expiry(ctx, event)` 回调与流式 `expiry` 事件；当引擎实际执行 `expiry_date` 驱动的到期结算或到期移除后，策略与 `run_backtest(..., on_event=...)` 均可收到通知。
- 新增 `examples/49_on_expiry_demo.py`，演示 `on_expiry` 回调、流式 `expiry` 事件以及结算后读取最新持仓状态。

### Changed
- 中英文 API 文档、策略指南、Quickstart、教材与示例总览已补充 `on_expiry` 的能力说明、使用边界与示例入口。

### Fixed
- 修复 `StrategyContext` / `ExpiryEvent` 类型声明错位问题，并同步完善 `BacktestStreamEvent`、函数式策略 `on_expiry` 与相关示例的类型签名，使 `mypy` / `pre-commit` 校验重新通过。

## [0.2.13] - 2026-04-20

### Fixed
- 修复日内调仓时机与行情数据跨符号排序问题，减少多标的同周期调仓时的执行顺序偏差。

## [0.2.12] - 2026-04-20

### Added
- 新增显式滑点策略写法，`run_backtest`、`StrategyConfig`、策略级 `strategy_slippage` 与订单级下单接口现支持 `{"type": "percent"|"fixed"|"ticks"|"zero", "value": ...}`。
- `short()` / `cover()` 现支持 `tag`、`fill_policy`、`slippage` 与 `commission`，与 `buy()` / `sell()` 的下单覆盖能力保持一致。

### Changed
- 期货教材示例与相关中文文档已切换为显式滑点 policy 写法，优先推荐 `percent` / `fixed` / `ticks`，并补充了成交时点与滑点语义的防踩坑说明。
- 内置 `broker_profile` 的滑点模板已迁移到显式 policy 表示，避免继续依赖裸数值语义。

### Deprecated
- 裸 `float` / `int` 形式的 `slippage` 仍保持兼容，但已进入弃用路径；当前会触发 `DeprecationWarning`，且对可疑的大滑点值给出明确提示。

### Fixed
- 为 `ticks` 滑点补充了 `tick_size` 解析与校验逻辑，避免多标的或缺少合约最小变动价位时静默使用错误滑点。

## [0.2.11] - 2026-04-16

### Fixed
- Fixed non-deterministic backtest metrics in multi-symbol runs when bars share the same timestamp.
- Ensured terminal equity/cash/margin snapshots are overwritten with the fully updated portfolio state before final metric calculation.

## [0.2.10] - 2026-04-15

### Added
- `run_backtest` now supports optional `on_event` callback and can emit stream events directly.
- Added `ChinaOptionsConfig` with prefix-level option fee configuration (`fee_by_symbol_prefix`).
- Added Engine API `set_options_fee_rules_by_prefix(symbol_prefix, commission_per_contract)`.
- Added readable time-string properties for `Trade.timestamp`, `Order.created_at`, and `Order.updated_at`.

### Changed
- `run_backtest_stream` is removed; stream scenarios should call `run_backtest(..., on_event=...)`.
- `run_backtest` always uses the unified stream core; runtime rollback flag `_engine_mode` is removed.
- Futures fee Engine API naming is standardized to `set_futures_fee_rules*`; legacy `set_future_fee_rules*` is removed.

## [0.2.9] - 2026-04-15

### Fixed
- Fixed benchmark return series index normalization and improved validation for report generation.

## [0.2.8] - 2026-04-14

### Added
- Added strategy start-time configuration support to the engine.

### Changed
- Improved futures margin risk handling.

## [0.2.7] - 2026-04-09

### Fixed
- Applied conditional open-price optimization according to the configured price-basis policy.

## [0.2.6] - 2026-04-09

### Added
- Added walk-forward model lifecycle management for the ML workflow.
- Added multi-symbol backtesting support and improved backtest window configuration.
- Added dictionary-based multi-symbol input support to the optimization workflow.

### Changed
- Improved rolling-training scheduling in parameter optimization.

## [0.2.5] - 2026-04-08

### Fixed
- Fixed missing `ctx.orders` in order-event callbacks.

## [0.2.4] - 2026-04-07

### Added
- Added same-bar cash reuse for sell-then-buy flows.

### Changed
- Distinguished automatic quantity adjustment from explicitly sized orders.

## [0.2.3] - 2026-04-06

### Fixed
- Fixed cross-category operator conflict detection in the factor-expression parser.

### Changed
- Cleaned up completed migration docs and outdated links.
- Refined examples by removing unused imports and obsolete configuration parameters.

## [0.2.2] - 2026-04-03

### Added
- Added `catalog_path` support for specifying the data directory in backtests.
- Added Top 8 rejected-order reason summaries in backtest output.

## [0.2.1] - 2026-04-02

### Added
- Added order-level execution overrides and strategy-level default execution settings.
- Added `NextClose` execution mode and unified the `symbols` parameter behavior.

### Changed
- Replaced `ExecutionMode` with `ExecutionPolicyCore`.
- Simplified the `price_basis` options under `fill_policy`.
- Updated the execution-semantics documentation and migration guidance.
