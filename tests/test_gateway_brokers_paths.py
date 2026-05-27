from akquant import DataFeed
from akquant.gateway import (
    BrokerEventBridge,
    BrokerOrderSubmitter,
    BrokerRecovery,
    BrokerRuntime,
)
from akquant.gateway.broker_models import UnifiedOrderRequest
from akquant.gateway.brokers.ctp.adapter import CTPMarketAdapter, CTPTraderAdapter
from akquant.gateway.brokers.ctp.native import CTPMarketGateway, CTPTraderGateway
from akquant.gateway.brokers.miniqmt.stub import (
    MiniQMTMarketGateway,
    MiniQMTTraderGateway,
)
from akquant.gateway.brokers.ptrade.stub import PTradeMarketGateway, PTradeTraderGateway
from akquant.gateway.factory import create_gateway_bundle


def test_gateway_top_level_exports_new_runtime_components() -> None:
    """Top-level gateway package should expose the new runtime building blocks."""
    assert BrokerRuntime.__name__ == "BrokerRuntime"
    assert BrokerEventBridge.__name__ == "BrokerEventBridge"
    assert BrokerRecovery.__name__ == "BrokerRecovery"
    assert BrokerOrderSubmitter.__name__ == "BrokerOrderSubmitter"


def test_factory_uses_new_broker_stub_paths() -> None:
    """Built-in placeholder brokers should now resolve to brokers/*/stub.py modules."""
    feed = DataFeed()
    miniqmt_bundle = create_gateway_bundle(
        broker="miniqmt",
        feed=feed,
        symbols=["000001.SZ"],
    )
    ptrade_bundle = create_gateway_bundle(
        broker="ptrade",
        feed=feed,
        symbols=["000001.SZ"],
    )

    assert isinstance(miniqmt_bundle.market_gateway, MiniQMTMarketGateway)
    assert isinstance(miniqmt_bundle.trader_gateway, MiniQMTTraderGateway)
    assert miniqmt_bundle.market_gateway.__class__.__module__.endswith(
        "brokers.miniqmt.stub"
    )
    assert miniqmt_bundle.trader_gateway.__class__.__module__.endswith(
        "brokers.miniqmt.stub"
    )

    assert isinstance(ptrade_bundle.market_gateway, PTradeMarketGateway)
    assert isinstance(ptrade_bundle.trader_gateway, PTradeTraderGateway)
    assert ptrade_bundle.market_gateway.__class__.__module__.endswith(
        "brokers.ptrade.stub"
    )
    assert ptrade_bundle.trader_gateway.__class__.__module__.endswith(
        "brokers.ptrade.stub"
    )


def test_new_stub_paths_are_directly_usable() -> None:
    """Direct imports from brokers/*/stub.py should remain usable for local tests."""
    miniqmt_gateway = MiniQMTTraderGateway()
    ptrade_gateway = PTradeTraderGateway()

    miniqmt_order_id = miniqmt_gateway.place_order(
        UnifiedOrderRequest(
            client_order_id="new-path-miniqmt",
            symbol="000001.SZ",
            side="Buy",
            quantity=100.0,
        )
    )
    ptrade_order_id = ptrade_gateway.place_order(
        UnifiedOrderRequest(
            client_order_id="new-path-ptrade",
            symbol="000002.SZ",
            side="Sell",
            quantity=50.0,
        )
    )

    assert miniqmt_order_id.startswith("miniqmt-")
    assert ptrade_order_id.startswith("ptrade-")


def test_new_ctp_paths_remain_importable() -> None:
    """Direct imports from brokers/ctp should expose adapter/native classes."""
    assert CTPMarketAdapter.__name__ == "CTPMarketAdapter"
    assert CTPTraderAdapter.__name__ == "CTPTraderAdapter"
    assert CTPMarketGateway.__name__ == "CTPMarketGateway"
    assert CTPTraderGateway.__name__ == "CTPTraderGateway"
