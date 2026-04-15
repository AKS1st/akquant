# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `run_backtest` now supports optional `on_event` callback and can emit stream events directly.
- Added `ChinaOptionsConfig` with prefix-level option fee configuration (`fee_by_symbol_prefix`).
- Added Engine API `set_options_fee_rules_by_prefix(symbol_prefix, commission_per_contract)`.

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
