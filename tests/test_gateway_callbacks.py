from akquant.gateway.miniqmt import MiniQMTTraderGateway
from akquant.gateway.models import UnifiedOrderRequest
from akquant.gateway.ptrade import PTradeTraderGateway


def test_miniqmt_callbacks_and_ingest() -> None:
    """Emit callbacks for local and broker-mapped events."""
    gateway = MiniQMTTraderGateway()
    orders: list[str] = []
    trades: list[str] = []
    reports: list[str] = []
    gateway.on_order(lambda o: orders.append(o.broker_order_id))
    gateway.on_trade(lambda t: trades.append(t.trade_id))
    gateway.on_execution_report(lambda r: reports.append(r.broker_order_id))

    broker_order_id = gateway.place_order(
        UnifiedOrderRequest(
            client_order_id="c1",
            symbol="000001.SZ",
            side="Buy",
            quantity=100.0,
        )
    )
    gateway.ingest_trade_event(
        {
            "trade_id": "t1",
            "broker_order_id": broker_order_id,
            "client_order_id": "c1",
            "symbol": "000001.SZ",
            "side": "Buy",
            "quantity": 100.0,
            "price": 10.2,
            "timestamp_ns": 1,
        }
    )
    gateway.ingest_order_event(
        {
            "client_order_id": "c1",
            "broker_order_id": broker_order_id,
            "symbol": "000001.SZ",
            "status": "filled",
            "filled_quantity": 100.0,
            "avg_fill_price": 10.2,
            "timestamp_ns": 2,
        }
    )

    assert orders[0] == broker_order_id
    assert trades == ["t1"]
    assert reports[-1] == broker_order_id


def test_ptrade_callbacks_and_cancel() -> None:
    """Emit callbacks when placing and cancelling orders."""
    gateway = PTradeTraderGateway()
    orders: list[str] = []
    reports: list[str] = []
    gateway.on_order(lambda o: orders.append(o.broker_order_id))
    gateway.on_execution_report(lambda r: reports.append(r.broker_order_id))

    broker_order_id = gateway.place_order(
        UnifiedOrderRequest(
            client_order_id="c2",
            symbol="000002.SZ",
            side="Sell",
            quantity=50.0,
        )
    )
    gateway.cancel_order(broker_order_id)

    assert orders[0] == broker_order_id
    assert reports[0] == broker_order_id
    assert reports[-1] == broker_order_id


def test_miniqmt_deduplicates_place_order_by_client_order_id() -> None:
    """Return existing broker order id when client order id is duplicated."""
    gateway = MiniQMTTraderGateway()
    req = UnifiedOrderRequest(
        client_order_id="dup-c1",
        symbol="000001.SZ",
        side="Buy",
        quantity=100.0,
    )
    first = gateway.place_order(req)
    second = gateway.place_order(req)

    assert first == second
    assert gateway.client_to_broker_order_ids["dup-c1"] == first
    assert len(gateway.orders) == 1


def test_ptrade_deduplicates_place_order_by_client_order_id() -> None:
    """Return existing broker order id when client order id is duplicated."""
    gateway = PTradeTraderGateway()
    req = UnifiedOrderRequest(
        client_order_id="dup-c2",
        symbol="000002.SZ",
        side="Sell",
        quantity=50.0,
    )
    first = gateway.place_order(req)
    second = gateway.place_order(req)

    assert first == second
    assert gateway.client_to_broker_order_ids["dup-c2"] == first
    assert len(gateway.orders) == 1


def test_miniqmt_allows_resubmit_after_terminal_status() -> None:
    """Allow same client order id after previous order is cancelled."""
    gateway = MiniQMTTraderGateway()
    req = UnifiedOrderRequest(
        client_order_id="retry-c1",
        symbol="000003.SZ",
        side="Buy",
        quantity=10.0,
    )
    first = gateway.place_order(req)
    gateway.cancel_order(first)
    second = gateway.place_order(req)

    assert second != first
    assert gateway.client_to_broker_order_ids["retry-c1"] == second
    assert first not in gateway.broker_to_client_order_ids


def test_ptrade_allows_resubmit_after_terminal_status() -> None:
    """Allow same client order id after previous order is cancelled."""
    gateway = PTradeTraderGateway()
    req = UnifiedOrderRequest(
        client_order_id="retry-c2",
        symbol="000004.SZ",
        side="Sell",
        quantity=20.0,
    )
    first = gateway.place_order(req)
    gateway.cancel_order(first)
    second = gateway.place_order(req)

    assert second != first
    assert gateway.client_to_broker_order_ids["retry-c2"] == second
    assert first not in gateway.broker_to_client_order_ids


def test_miniqmt_gateway_rejects_explicit_position_effect() -> None:
    """MiniQMT should reject explicit open/close position effects."""
    gateway = MiniQMTTraderGateway()
    try:
        gateway.place_order(
            UnifiedOrderRequest(
                client_order_id="effect-c1",
                symbol="000001.SZ",
                side="Buy",
                quantity=10.0,
                position_effect="close",
            )
        )
    except RuntimeError as exc:
        assert "does not support explicit position_effect" in str(exc)
    else:
        raise AssertionError("expected MiniQMT to reject explicit position_effect")
