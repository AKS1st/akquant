from akquant import DataFeed
from akquant.gateway import create_gateway_bundle


def test_create_miniqmt_gateway_bundle() -> None:
    """Create MiniQMT gateway bundle with trader gateway."""
    feed = DataFeed()
    bundle = create_gateway_bundle(
        broker="miniqmt",
        feed=feed,
        symbols=["000001.SZ"],
    )
    assert bundle.metadata is not None
    assert bundle.metadata["broker"] == "miniqmt"
    assert bundle.trader_gateway is not None
    assert bundle.trader_capabilities is not None
    assert bundle.trader_capabilities.broker_name == "miniqmt"
    assert bundle.trader_capabilities.position_details is False
    assert bundle.trader_capabilities.supported_position_effects == ("auto",)


def test_create_ptrade_gateway_bundle() -> None:
    """Create PTrade gateway bundle with trader gateway."""
    feed = DataFeed()
    bundle = create_gateway_bundle(
        broker="ptrade",
        feed=feed,
        symbols=["000001.SZ"],
    )
    assert bundle.metadata is not None
    assert bundle.metadata["broker"] == "ptrade"
    assert bundle.trader_gateway is not None
    assert bundle.trader_capabilities is not None
    assert bundle.trader_capabilities.broker_name == "ptrade"
    assert bundle.trader_capabilities.position_details is False
    assert bundle.trader_capabilities.supported_position_effects == ("auto",)
