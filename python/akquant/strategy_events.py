from typing import Any

import numpy as np
import pandas as pd

from .akquant import Bar, StrategyContext, Tick
from .strategy_framework_hooks import (
    call_user_callback,
    dispatch_boundary_timer,
    dispatch_daily_rebalance_timer,
    dispatch_portfolio_update,
    dispatch_pre_open_timer,
    dispatch_time_hooks,
    ensure_framework_state,
    mark_portfolio_dirty,
    register_boundary_timers,
    register_pre_open_timers,
)
from .strategy_ml import (
    activate_pending_model,
    begin_training_cycle,
    consume_training_trigger,
    finalize_training_cycle,
    should_trigger_training,
)
from .strategy_order_events import check_expiry_events
from .strategy_scheduler import flush_pending_schedules


def _is_before_active_start(strategy: Any, timestamp: int) -> bool:
    """Return whether the event timestamp is still in the preload-only window."""
    active_start_time = getattr(strategy, "_active_start_time_ns", None)
    return active_start_time is not None and timestamp < int(active_start_time)


def _flush_indicator_snapshots(strategy: Any) -> None:
    """Flush one callback cycle of pending indicator snapshot events."""
    recorder = getattr(strategy, "_indicator_recorder", None)
    if recorder is not None:
        recorder.flush_stream_snapshot()


def on_bar_event(strategy: Any, bar: Bar, ctx: StrategyContext) -> None:
    """引擎调用的 Bar 回调 (Internal)."""
    ensure_framework_state(strategy)
    strategy.ctx = ctx
    flush_pending_schedules(strategy)
    register_boundary_timers(strategy)
    register_pre_open_timers(strategy)
    strategy._last_event_type = "bar"

    strategy._check_order_events()
    check_expiry_events(strategy)

    symbol = bar.symbol
    current_pos = ctx.get_position(symbol)

    if current_pos == 0:
        strategy._hold_bars[symbol] = 0
        strategy._last_position_signs[symbol] = 0.0
    else:
        current_sign = np.sign(current_pos)
        prev_sign = strategy._last_position_signs[symbol]

        if current_sign != prev_sign:
            strategy._hold_bars[symbol] = 1
        else:
            strategy._hold_bars[symbol] += 1

        strategy._last_position_signs[symbol] = current_sign

    if not strategy._model_configured:
        strategy._auto_configure_model()

    previous_price = strategy._last_prices.get(bar.symbol)
    strategy.current_bar = None
    strategy.current_tick = None

    if _is_before_active_start(strategy, int(bar.timestamp)):
        return

    if current_pos != 0 and previous_price is not None and previous_price != bar.close:
        mark_portfolio_dirty(strategy)
    dispatch_time_hooks(strategy)
    strategy.current_bar = bar
    if hasattr(strategy, "_update_incremental_indicators"):
        strategy._update_incremental_indicators(bar)
    strategy._last_prices[bar.symbol] = bar.close
    strategy._bar_count += 1
    dispatch_portfolio_update(strategy)

    if strategy._bar_count < strategy.warmup_period:
        return

    activate_pending_model(strategy)
    should_train = should_trigger_training(strategy)

    call_user_callback(strategy, "on_bar", bar, payload=bar)
    if should_train:
        consume_training_trigger(strategy)
        training_cycle = begin_training_cycle(strategy)
        try:
            call_user_callback(strategy, "on_train_signal", strategy, payload=strategy)
        finally:
            finalize_training_cycle(strategy, training_cycle)
    analyzer_manager = getattr(strategy, "_analyzer_manager", None)
    if analyzer_manager is not None:
        try:
            analyzer_manager.on_bar(
                {
                    "strategy": strategy,
                    "bar": bar,
                    "engine": getattr(strategy, "_engine", None),
                    "ctx": ctx,
                    "owner_strategy_id": str(
                        getattr(ctx, "strategy_id", None)
                        or getattr(strategy, "_owner_strategy_id", "_default")
                    ),
                }
            )
        except Exception:
            pass
    _flush_indicator_snapshots(strategy)


def on_tick_event(strategy: Any, tick: Tick, ctx: StrategyContext) -> None:
    """引擎调用的 Tick 回调 (Internal)."""
    ensure_framework_state(strategy)
    strategy.ctx = ctx
    flush_pending_schedules(strategy)
    register_boundary_timers(strategy)
    register_pre_open_timers(strategy)
    strategy._last_event_type = "tick"
    strategy._check_order_events()
    check_expiry_events(strategy)
    previous_price = strategy._last_prices.get(tick.symbol)
    strategy.current_bar = None
    strategy.current_tick = None

    if _is_before_active_start(strategy, int(tick.timestamp)):
        return

    current_pos = ctx.get_position(tick.symbol)
    if current_pos != 0 and previous_price is not None and previous_price != tick.price:
        mark_portfolio_dirty(strategy)
    dispatch_time_hooks(strategy)
    strategy.current_tick = tick
    strategy._last_prices[tick.symbol] = tick.price
    dispatch_portfolio_update(strategy)
    call_user_callback(strategy, "on_tick", tick, payload=tick)
    _flush_indicator_snapshots(strategy)


def on_timer_event(strategy: Any, payload: str, ctx: StrategyContext) -> None:
    """引擎调用的 Timer 回调 (Internal)."""
    ensure_framework_state(strategy)
    strategy.ctx = ctx
    flush_pending_schedules(strategy)
    register_boundary_timers(strategy)
    register_pre_open_timers(strategy)
    strategy._check_order_events()

    current_time = int(getattr(ctx, "current_time", 0))
    if _is_before_active_start(strategy, current_time):
        return

    dispatch_time_hooks(strategy)
    dispatch_portfolio_update(strategy)

    if dispatch_daily_rebalance_timer(strategy, payload):
        _flush_indicator_snapshots(strategy)
        return

    if dispatch_boundary_timer(strategy, payload):
        _flush_indicator_snapshots(strategy)
        return

    if dispatch_pre_open_timer(strategy, payload):
        _flush_indicator_snapshots(strategy)
        return

    if payload.startswith("__daily__|"):
        parts = payload.split("|", 2)
        if len(parts) == 3:
            _, time_str, user_payload = parts

            call_user_callback(strategy, "on_timer", user_payload, payload=user_payload)

            if not strategy._trading_days:
                try:
                    t = pd.to_datetime(time_str).time()
                    now = pd.Timestamp.now(tz=strategy.timezone)
                    target = pd.Timestamp.combine(now.date(), t).tz_localize(
                        strategy.timezone
                    )

                    if target <= now:
                        target += pd.Timedelta(days=1)

                    strategy.schedule(target, payload)
                except Exception as e:
                    print(f"Error processing daily timer: {e}")
            _flush_indicator_snapshots(strategy)
            return

    call_user_callback(strategy, "on_timer", payload, payload=payload)
    _flush_indicator_snapshots(strategy)


def flush_pending_order_events(strategy: Any, ctx: StrategyContext) -> None:
    """Flush pending order/trade callbacks without invoking a user market callback."""
    ensure_framework_state(strategy)
    strategy.ctx = ctx
    strategy._check_order_events()
