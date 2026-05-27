from types import SimpleNamespace
from typing import Any

from akquant.gateway.broker_recovery import BrokerRecovery


def _build_recovery(
    gateway: Any,
    *,
    recovery_mode: str = "compatible",
) -> tuple[
    BrokerRecovery, list[tuple[str, Any]], list[tuple[str, Any]], list[dict[str, Any]]
]:
    queued_events: list[tuple[str, Any]] = []
    strategy_errors: list[tuple[str, Any]] = []
    observed_events: list[dict[str, Any]] = []
    last_error_key = ""

    def _set_last_error_key(value: str) -> None:
        nonlocal last_error_key
        last_error_key = value

    recovery = BrokerRecovery(
        get_trader_gateway=lambda: gateway,
        queue_broker_event=lambda event_name, payload: queued_events.append(
            (event_name, payload)
        ),
        notify_strategy_error=lambda strategy, error, source, payload: (
            strategy_errors.append((source, payload))
        ),
        get_on_broker_event=lambda: observed_events.append,
        get_recovery_mode=lambda: recovery_mode,
        get_last_error_key=lambda: last_error_key,
        set_last_error_key=_set_last_error_key,
    )
    return recovery, queued_events, strategy_errors, observed_events


def test_recovery_contract_syncs_orders_trades_and_account_snapshots() -> None:
    """Recovery should enqueue open orders, trades and account snapshots."""

    class _DummyTraderGateway:
        def heartbeat(self) -> bool:
            return True

        def sync_open_orders(self) -> list[Any]:
            return [SimpleNamespace(broker_order_id="b-sync-1", status="Submitted")]

        def sync_today_trades(self) -> list[Any]:
            return [SimpleNamespace(trade_id="t-sync-1", broker_order_id="b-sync-1")]

        def query_account(self) -> Any:
            return SimpleNamespace(account_id="acct-sync-1", equity=100000.0)

    recovery, queued_events, _, _ = _build_recovery(_DummyTraderGateway())

    recovery.run_cycle()

    assert [event_name for event_name, _ in queued_events] == [
        "order",
        "trade",
        "account",
    ]
    assert getattr(queued_events[0][1], "broker_order_id") == "b-sync-1"
    assert getattr(queued_events[1][1], "trade_id") == "t-sync-1"
    assert getattr(queued_events[2][1], "account_id") == "acct-sync-1"


def test_recovery_contract_reports_strict_errors_once() -> None:
    """Strict recovery should notify strategy and observer with deduplication."""

    class _DummyTraderGateway:
        def heartbeat(self) -> bool:
            return True

        def sync_open_orders(self) -> list[Any]:
            return []

        def sync_today_trades(self) -> list[Any]:
            raise RuntimeError("sync trades failed")

    recovery, _, strategy_errors, observed_events = _build_recovery(
        _DummyTraderGateway(),
        recovery_mode="strict",
    )

    recovery.run_cycle(strategy=object(), handle_error=recovery.handle_error)
    recovery.run_cycle(strategy=object(), handle_error=recovery.handle_error)

    assert strategy_errors == [
        ("broker_recovery.sync_today_trades", {"stage": "sync_today_trades"})
    ]
    assert len(observed_events) == 1
    assert observed_events[0]["event_type"] == "recovery_error"
    assert (
        observed_events[0]["payload"]["source"] == "broker_recovery.sync_today_trades"
    )
    assert observed_events[0]["payload"]["error_message"] == "sync trades failed"


def test_recovery_contract_keeps_compatible_failures_silent() -> None:
    """Compatible recovery should suppress sync failures from strategy and observer."""

    class _DummyTraderGateway:
        def heartbeat(self) -> bool:
            return True

        def sync_open_orders(self) -> list[Any]:
            return []

        def sync_today_trades(self) -> list[Any]:
            raise RuntimeError("sync trades failed")

    recovery, queued_events, strategy_errors, observed_events = _build_recovery(
        _DummyTraderGateway(),
        recovery_mode="compatible",
    )

    recovery.run_cycle(strategy=object(), handle_error=recovery.handle_error)

    assert queued_events == []
    assert strategy_errors == []
    assert observed_events == []
