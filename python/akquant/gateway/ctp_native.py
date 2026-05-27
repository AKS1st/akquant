"""Backward-compatible exports for native CTP gateways."""

from .brokers.ctp import native as _native
from .brokers.ctp.native import CTPMarketGateway, CTPTraderGateway

HAS_OPENCTP = _native.HAS_OPENCTP
mdapi = _native.mdapi
tdapi = _native.tdapi
logger = _native.logger

__all__ = [
    "HAS_OPENCTP",
    "mdapi",
    "tdapi",
    "logger",
    "CTPMarketGateway",
    "CTPTraderGateway",
]
