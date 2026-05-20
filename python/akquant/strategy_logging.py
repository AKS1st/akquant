import logging
from typing import Any

from .log import build_log_extra, get_logger
from .strategy_time import (
    current_timestamp as _current_timestamp,
)
from .strategy_time import (
    format_time_iso_utc as _format_time_iso_utc,
)
from .strategy_time import (
    now as _now,
)

logger = get_logger("strategy")


def _extract_order_log_fields(strategy: Any) -> tuple[str, Any, Any]:
    """Extract current callback phase plus order/trade payloads."""
    current_callback = str(
        getattr(strategy, "_framework_current_callback", "") or ""
    ).strip()
    phase = "strategy"
    if current_callback in {"on_order", "on_reject"}:
        phase = "order"
    elif current_callback == "on_trade":
        phase = "trade"
    return (
        phase,
        getattr(strategy, "_framework_current_order", None),
        getattr(strategy, "_framework_current_trade", None),
    )


def _extract_symbol(strategy: Any, order_payload: Any, trade_payload: Any) -> Any:
    """Resolve the most relevant symbol for the current log call."""
    current_bar = getattr(strategy, "current_bar", None)
    current_tick = getattr(strategy, "current_tick", None)
    if current_bar is not None:
        return str(getattr(current_bar, "symbol", "") or "") or None
    if current_tick is not None:
        return str(getattr(current_tick, "symbol", "") or "") or None
    for payload in (order_payload, trade_payload):
        symbol = str(getattr(payload, "symbol", "") or "").strip()
        if symbol:
            return symbol
    return None


def _build_log_extra(
    strategy: Any, event_time_ns: int | None, event_time_iso: str | None
) -> dict[str, Any]:
    """Build structured logging metadata for strategy-side logs."""
    strategy_id_raw = getattr(strategy, "_owner_strategy_id", None)
    strategy_id = (
        str(strategy_id_raw).strip() if strategy_id_raw is not None else "_default"
    ) or "_default"
    phase, order_payload, trade_payload = _extract_order_log_fields(strategy)
    symbol = _extract_symbol(strategy, order_payload, trade_payload)
    slot = strategy_id if strategy_id != "_default" else None
    order_id = None
    client_order_id = None
    if order_payload is not None:
        order_id = getattr(order_payload, "id", None) or getattr(
            order_payload, "order_id", None
        )
        client_order_id = getattr(order_payload, "client_order_id", None)
    elif trade_payload is not None:
        order_id = getattr(trade_payload, "order_id", None) or getattr(
            trade_payload, "id", None
        )
        client_order_id = getattr(trade_payload, "client_order_id", None)
    return build_log_extra(
        phase=phase,
        event_time=event_time_ns,
        event_time_iso=event_time_iso,
        strategy_id=strategy_id,
        slot=slot,
        symbol=symbol,
        order_id=order_id,
        client_order_id=client_order_id,
    )


def log(strategy: Any, msg: str, level: int = logging.INFO) -> None:
    """输出日志 (自动添加当前回测时间)."""
    timestamp_str = ""
    event_time_ns = _current_timestamp(strategy)
    event_time_iso = (
        _format_time_iso_utc(event_time_ns) if event_time_ns is not None else None
    )
    ts = _now(strategy)
    if ts:
        timestamp_str = ts.strftime("%Y-%m-%d %H:%M:%S")

    if timestamp_str:
        final_msg = f"[{timestamp_str}] {msg}"
    else:
        final_msg = msg

    logger.log(
        level,
        final_msg,
        extra=_build_log_extra(strategy, event_time_ns, event_time_iso),
    )
