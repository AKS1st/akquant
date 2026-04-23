#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Class-style on_tick callback demo."""

from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
from akquant import Strategy, Tick
from akquant.akquant import StrategyContext


class DemoContext:
    """Minimal context object for simulating class-style tick dispatch."""

    def __init__(self) -> None:
        """Initialize the minimal fields required by internal callbacks."""
        self.canceled_order_ids: list[str] = []
        self.active_orders: list[Any] = []
        self.recent_trades: list[Any] = []
        self.recent_rejected_orders: list[Any] = []
        self.cash = 100000.0
        self.positions: dict[str, float] = {}
        self.available_positions: dict[str, float] = {}
        self.session = "normal"
        self.current_time = 0

    def get_position(self, symbol: str) -> float:
        """Return the simulated position size for one symbol."""
        return float(self.positions.get(symbol, 0.0))


class TickCallbacksStrategy(Strategy):
    """Demonstrate class-style on_tick together with adjacent callbacks."""

    def __init__(self) -> None:
        """Store the callback sequence emitted by the demo."""
        self.events: list[str] = []

    def on_tick(self, tick: Tick) -> None:
        """Record each simulated tick callback."""
        self.events.append(f"tick:{tick.symbol}:{tick.price}")
        print(f"[Callback] on_tick | symbol={tick.symbol} | price={tick.price}")

    def on_order(self, order: Any) -> None:
        """Record order callbacks adjacent to tick handling."""
        self.events.append(f"order:{order.id}")
        print(f"[Callback] on_order | id={order.id} | status={order.status}")

    def on_trade(self, trade: Any) -> None:
        """Record trade callbacks adjacent to tick handling."""
        self.events.append(f"trade:{trade.order_id}")
        print(f"[Callback] on_trade | order_id={trade.order_id}")

    def on_timer(self, payload: str) -> None:
        """Record timer callbacks in the same demo script."""
        self.events.append(f"timer:{payload}")
        print(f"[Callback] on_timer | payload={payload}")


def main() -> None:
    """Run a minimal class-style tick callback simulation."""
    strategy = TickCallbacksStrategy()
    ctx = cast(StrategyContext, DemoContext())

    ts1 = int(pd.Timestamp("2024-01-02 09:30:01", tz="Asia/Shanghai").value)
    ctx.current_time = ts1
    ctx.active_orders = cast(
        Any, [SimpleNamespace(id="o1", status="Submitted", filled_quantity=0.0)]
    )
    ctx.recent_trades = cast(Any, [SimpleNamespace(order_id="o1")])
    tick1 = Tick(timestamp=ts1, price=101.0, volume=200.0, symbol="TEST")
    strategy._on_tick_event(tick1, ctx)

    ts2 = int(pd.Timestamp("2024-01-02 09:31:01", tz="Asia/Shanghai").value)
    ctx.current_time = ts2
    ctx.active_orders = cast(
        Any, [SimpleNamespace(id="o2", status="Submitted", filled_quantity=0.0)]
    )
    ctx.recent_trades = cast(Any, [SimpleNamespace(order_id="o2")])
    tick2 = Tick(timestamp=ts2, price=101.5, volume=220.0, symbol="TEST")
    strategy._on_tick_event(tick2, ctx)

    ctx.active_orders = []
    ctx.recent_trades = []
    strategy._on_timer_event("rebalance", ctx)

    print("\n=== class tick summary ===")
    print(f"events_total={len(strategy.events)}")
    print(f"ticks={sum(1 for x in strategy.events if x.startswith('tick:'))}")
    print(f"orders={sum(1 for x in strategy.events if x.startswith('order:'))}")
    print(f"trades={sum(1 for x in strategy.events if x.startswith('trade:'))}")
    print(f"timers={sum(1 for x in strategy.events if x.startswith('timer:'))}")


if __name__ == "__main__":
    main()
