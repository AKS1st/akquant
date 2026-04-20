# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
