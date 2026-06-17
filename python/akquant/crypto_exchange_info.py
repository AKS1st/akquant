"""
加密货币交易所交易对信息工具。

提供:
- 内置常用币种默认参数表（可作为回测 fallback）
- 从 Binance API 拉取实时交易对参数
"""

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 常用币种默认值（可作 fallback，也可直接用于回测配置）
# 数据来源: Binance USDⓈ-M Futures API (fapi/v1/exchangeInfo, 2026-06-16)
# 适用于永续合约回测，与现货精度不同。用户可按需覆盖。
# ---------------------------------------------------------------------------
DEFAULT_CRYPTO_SYMBOL_INFO: Dict[str, Dict[str, float]] = {
    # 数据来源: Binance USDⓈ-M Futures API (fapi/v1/exchangeInfo, 2026-06-16 实时拉取)
    # 仅包含 status=TRADING 的 PERPETUAL 合约
    "BTCUSDT":  {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.1,     "min_notional": 50.0},
    "ETHUSDT":  {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.01,    "min_notional": 20.0},
    "SOLUSDT":  {"step_size": 0.01,  "min_qty": 0.01,  "tick_size": 0.01,    "min_notional": 5.0},
    "BNBUSDT":  {"step_size": 0.01,  "min_qty": 0.01,  "tick_size": 0.01,    "min_notional": 5.0},
    "XRPUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "ADAUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.0001,  "min_notional": 5.0},
    "DOGEUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "AVAXUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.001,   "min_notional": 5.0},
    "DOTUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.001,   "min_notional": 5.0},
    "LINKUSDT": {"step_size": 0.01,  "min_qty": 0.01,  "tick_size": 0.001,   "min_notional": 20.0},
    "ATOMUSDT": {"step_size": 0.01,  "min_qty": 0.01,  "tick_size": 0.001,   "min_notional": 5.0},
    "LTCUSDT":  {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.01,    "min_notional": 20.0},
    "BCHUSDT":  {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.01,    "min_notional": 20.0},
    "FILUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.001,   "min_notional": 5.0},
    "NEARUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.001,   "min_notional": 5.0},
    "NEOUSDT":  {"step_size": 0.01,  "min_qty": 0.01,  "tick_size": 0.001,   "min_notional": 5.0},
    "QTUMUSDT": {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.001,   "min_notional": 5.0},
    "IOTAUSDT": {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.00001, "min_notional": 5.0},
    "XLMUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "TRXUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "ETCUSDT":  {"step_size": 0.01,  "min_qty": 0.01,  "tick_size": 0.001,   "min_notional": 20.0},
    "VETUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.000001,"min_notional": 5.0},
    "ZECUSDT":  {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.01,    "min_notional": 5.0},
    "DASHUSDT": {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.01,    "min_notional": 5.0},
    "THETAUSDT":{"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "ALGOUSDT": {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "XTZUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "AAVEUSDT": {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.01,    "min_notional": 5.0},
    "CRVUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "KSMUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.001,   "min_notional": 5.0},
    "EGLDUSDT": {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.001,   "min_notional": 5.0},
    "RUNEUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.0001,  "min_notional": 5.0},
    "AXSUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.001,   "min_notional": 5.0},
    "YFIUSDT":  {"step_size": 0.001, "min_qty": 0.001, "tick_size": 1.0,     "min_notional": 5.0},
    "COMPUSDT": {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.01,    "min_notional": 5.0},
    "SUSHIUSDT":{"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.0001,  "min_notional": 5.0},
    "1INCHUSDT":{"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.0001,  "min_notional": 5.0},
    "ZILUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.000001,"min_notional": 5.0},
    "ENJUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "IOSTUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.000001,"min_notional": 5.0},
    "ICXUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "STXUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.0001,  "min_notional": 5.0},
    "HBARUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "CHZUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "SANDUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "GRTUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
    "ANKRUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.000001,"min_notional": 5.0},
    "MANAUSDT": {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.0001,  "min_notional": 5.0},
    "SNXUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "KAVAUSDT": {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.00001, "min_notional": 5.0},
    "BATUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "ZRXUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "ZENUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.001,   "min_notional": 5.0},
    "ONTUSDT":  {"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.00001, "min_notional": 5.0},
    "XMRUSDT":  {"step_size": 0.001, "min_qty": 0.001, "tick_size": 0.01,    "min_notional": 5.0},
    "ALICEUSDT":{"step_size": 0.1,   "min_qty": 0.1,   "tick_size": 0.0001,  "min_notional": 5.0},
    "SKLUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.000001,"min_notional": 5.0},
    "RSRUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.000001,"min_notional": 5.0},
    "BELUSDT":  {"step_size": 1.0,   "min_qty": 1.0,   "tick_size": 0.00001, "min_notional": 5.0},
}


def _extract_symbol_filter(info: Dict[str, Any], symbol: str) -> Optional[Dict[str, float]]:
    """从单条 Binance 交易对信息中解析出精度参数。"""
    symbol_name = info.get("symbol", "")
    if not symbol_name:
        return None
    filters: List[Dict[str, Any]] = info.get("filters", [])
    step_size: Optional[str] = None
    min_qty: Optional[str] = None
    tick_size: Optional[str] = None
    min_notional: Optional[str] = None

    for f in filters:
        ftype = f.get("filterType", "")
        if ftype == "LOT_SIZE":
            step_size = f.get("stepSize")
            min_qty = f.get("minQty")
        elif ftype == "PRICE_FILTER":
            tick_size = f.get("tickSize")
        elif ftype == "MIN_NOTIONAL":
            # fapi 返回的 key 为 "notional"，现货为 "minNotional"
            min_notional = f.get("notional") or f.get("minNotional")

    if not step_size or not tick_size:
        return None

    result: Dict[str, float] = {
        "step_size": float(step_size),
        "min_qty": float(min_qty) if min_qty else float(step_size),
        "tick_size": float(tick_size),
    }
    if min_notional:
        result["min_notional"] = float(min_notional)
    else:
        # 如果交易所未返回 MIN_NOTIONAL，保守设为 0
        result["min_notional"] = 0.0
    return result


def fetch_binance_klines(
    symbol: str,
    interval: str = "5m",
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    *,
    base_url: str = "https://fapi.binance.com",
) -> "pd.DataFrame":
    """
    从 Binance USDⓈ-M Futures API 下载 K 线数据及附属行情。

    不传 ``start_time`` / ``end_time`` 时默认下载 **2026-06-15 (UTC)** 全天数据，
    每次运行结果一致，便于新手验证配置。

    返回的 DataFrame 包含 OHLCV、``funding_rate``（资金费率）、
    ``mark_price``（标记价格）、``taker_buy_vol`` 等列。
    ``symbol`` 列自动填充为 ``symbol``。

    ``funding_rate`` 来源于 Binance 的历史资金费率接口
    (``fapi/v1/fundingRate``)，按结算小时对齐到对应 K 线。
    ``mark_price`` 来源于标记价格 K 线 (``fapi/v1/markPriceKlines``)。

    Args:
        symbol: 币种，如 "BTCUSDT"。
        interval: K 线周期，如 "5m"、"1h"、"1d"。默认 "5m"。
        start_time: 起始时间，格式 ``"2026-06-15"`` 或 ``"2026-06-15T00:00:00"``。
                    未传时使用默认日期 2026-06-15。
        end_time: 结束时间，格式同上。未传时使用默认日期 2026-06-16（即 start 次日）。
        base_url: Binance API 地址。

    Returns:
        pd.DataFrame，包含 timestamp(UTC)、OHLCV、volume、trades、
        taker_buy_vol、taker_buy_quote_vol、funding_rate、mark_price、symbol。

    Example::

        from akquant.crypto_exchange_info import fetch_binance_klines

        # 默认 2026-06-15 全天，结果可复现
        df = fetch_binance_klines("BTCUSDT")

        # 指定日期范围
        df = fetch_binance_klines("BTCUSDT", start_time="2026-06-01", end_time="2026-06-02")
    """
    import json
    import urllib.request

    _interval_map = {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h",
        "12h": "12h", "1d": "1d", "1w": "1w",
    }
    interval = _interval_map.get(interval, interval)

    headers = {"User-Agent": "akquant/1.0"}

    # ── 固定默认日期，保证结果可复现 ──
    import pandas as pd
    if start_time is None:
        start_time = "2026-06-15"
    if end_time is None:
        end_time = "2026-06-16"
    start_ms = int(pd.Timestamp(start_time, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end_time, tz="UTC").timestamp() * 1000)
    limit = 1500

    # 1. 下载标准 K 线（用时间范围代替 limit，保证结果可复现）
    url = (
        f"{base_url}/fapi/v1/klines"
        f"?symbol={symbol}&interval={interval}"
        f"&startTime={start_ms}&endTime={end_ms}&limit={limit}"
    )
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    import pandas as pd

    rows = []
    for k in raw:
        rows.append({
            "timestamp": pd.Timestamp(k[0], unit="ms", tz="UTC"),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "trades": int(k[8]),
            "taker_buy_vol": float(k[9]),
            "taker_buy_quote_vol": float(k[10]),
        })

    df = pd.DataFrame(rows)
    df["symbol"] = symbol

    # 2. 下载标记价格 K 线 (mark_price)
    # 取收盘价作为每根 bar 的标记价格
    try:
        url_mark = (
            f"{base_url}/fapi/v1/markPriceKlines"
            f"?symbol={symbol}&interval={interval}"
            f"&startTime={start_ms}&endTime={end_ms}&limit={limit}"
        )
        req_m = urllib.request.Request(url_mark, headers=headers)
        with urllib.request.urlopen(req_m, timeout=15) as resp_m:
            raw_mark = json.loads(resp_m.read().decode("utf-8"))
        mark_map: Dict[int, float] = {}
        for k in raw_mark:
            ts_ms = k[0]
            close = float(k[4])
            mark_map[ts_ms] = close
        df["mark_price"] = df["timestamp"].apply(
            lambda t: mark_map.get(int(t.value // 1_000_000), float("nan"))
        )
    except Exception:
        df["mark_price"] = float("nan")

    # 3. 下载资金费率历史 (funding_rate)
    # 取每根 bar 所在时刻最新的结算费率（未结算时为 0）
    try:
        start_ms = int(df["timestamp"].iloc[0].value // 1_000_000)
        end_ms = int(df["timestamp"].iloc[-1].value // 1_000_000) + 1
        url_fr = (
            f"{base_url}/fapi/v1/fundingRate"
            f"?symbol={symbol}&startTime={start_ms}&endTime={end_ms}&limit=100"
        )
        req_fr = urllib.request.Request(url_fr, headers=headers)
        with urllib.request.urlopen(req_fr, timeout=15) as resp_fr:
            raw_fr = json.loads(resp_fr.read().decode("utf-8"))

        # 构建 funding_time → rate 映射 (fundingTime 是结算时刻 ms)
        fr_map: Dict[int, float] = {}
        for item in raw_fr:
            if not isinstance(item, dict):
                continue
            ft = item.get("fundingTime")
            rate = item.get("fundingRate")
            if ft is not None and rate is not None:
                fr_map[ft] = float(rate)

        # 对于每根 bar，只在其所属结算小时设 funding_rate（来自 Binance API）
        # 非结算小时用 NaN，引擎会跳过（Rust check_settlement 会 filter is_nan）
        df["funding_rate"] = float("nan")
        bar_ns = df["timestamp"].values.astype("int64")  # ns
        for ft_ms, rate in fr_map.items():
            ft_ns = ft_ms * 1_000_000
            hour_ns = 3_600_000_000_000
            hour_start = (ft_ns // hour_ns) * hour_ns
            hour_end = hour_start + hour_ns
            hour_mask = (bar_ns >= hour_start) & (bar_ns < hour_end)
            df.loc[hour_mask, "funding_rate"] = rate
    except Exception:
        df["funding_rate"] = float("nan")

    return df


def fetch_binance_symbol_info(
    symbols: Optional[List[str]] = None,
    base_url: str = "https://fapi.binance.com",
) -> Dict[str, Dict[str, float]]:
    """
    从 Binance API 的 exchangeInfo 接口拉取交易对精度信息。

    Args:
        symbols: 需要拉取的币种列表 (如 ["BTCUSDT", "ETHUSDT"])。
                为 None 时拉取所有 USDT 交易对。
        base_url: Binance API 地址。

    Returns:
        Dict[symbol -> {"step_size": float, "min_qty": float,
                         "tick_size": float, "min_notional": float}]
    """
    import json
    import urllib.request

    url = f"{base_url}/fapi/v1/exchangeInfo"
    if symbols:
        sym_list = ",".join(symbols)
        url += f"?symbols={urllib.request.quote(json.dumps(sym_list.split(',')))}"

    req = urllib.request.Request(url, headers={"User-Agent": "akquant/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    result: Dict[str, Dict[str, float]] = {}
    for info in data.get("symbols", []):
        sym = info.get("symbol", "")
        if symbols and sym not in symbols:
            continue
        parsed = _extract_symbol_filter(info, sym)
        if parsed:
            result[sym] = parsed

    return result


def get_default_crypto_instruments(
    symbols: List[str],
    margin_ratio: float = 1.0,
    *,
    online: bool = False,
    base_url: str = "https://fapi.binance.com",
) -> Dict[str, Dict[str, Any]]:
    """
    获取各币种精度参数，返回可直接传入 ``run_backtest(instruments=...)`` 的 dict。

    Args:
        symbols: 币种列表，如 ``["BTCUSDT", "ETHUSDT"]``。
        margin_ratio: 保证金比率，1.0=全仓，0.1=10x。
        online: True 时从 Binance API 实时拉取，False 时使用内置默认值。
        base_url: Binance API 地址，仅在 online=True 时使用。

    Returns:
        Dict[str, dict]，key 为币种，value 为 instruments 配置 dict。

    Example::

        from akquant.crypto_exchange_info import get_default_crypto_instruments

        # 使用本地默认值（离线，约 60 个主流币种）
        instruments = get_default_crypto_instruments(["BTCUSDT", "ETHUSDT"])

        # 从 Binance API 拉取实时精度参数
        instruments = get_default_crypto_instruments(["BTCUSDT"], online=True)

        result = aq.run_backtest(
            ...,
            instruments=instruments,
        )
    """
    if online:
        try:
            info = fetch_binance_symbol_info(symbols, base_url=base_url)
        except Exception:
            info = {}
    else:
        info = {}

    result: Dict[str, Dict[str, Any]] = {}
    for sym in symbols:
        defaults = info.get(sym) or DEFAULT_CRYPTO_SYMBOL_INFO.get(sym, {})
        result[sym] = {
            "asset_type": "CRYPTO",
            "multiplier": 1.0,
            "margin_ratio": margin_ratio,
            "tick_size": defaults.get("tick_size", 0.01),
            # 数字货币无 lot_size 概念，step_size 替代了它
            "step_size": defaults.get("step_size", 0.001),
            "min_qty": defaults.get("min_qty", 0.001),
            "min_notional": defaults.get("min_notional", 5.0),
        }
    return result


def build_crypto_instrument_configs(
    symbols: List[str],
    *,
    base_url: str = "https://fapi.binance.com",
    fallback: bool = True,
    margin_ratio: float = 1.0,
    maker_commission_rate: float = 0.0002,
    taker_commission_rate: float = 0.0007,
    extra: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    """
    便捷函数: 从 Binance API 拉取参数，构建 Config 的 InstrumentConfig 列表。

    如果 API 拉取失败且有 fallback=True，使用内置默认参数表。

    Args:
        symbols: 币种列表。
        base_url: Binance API 地址。
        fallback: API 失败时是否使用内置默认值。
        margin_ratio: 保证金比率（全仓=1.0，10x=0.1）。
        maker_commission_rate: Maker 费率。
        taker_commission_rate: Taker 费率。
        extra: 额外传递给 InstrumentConfig 的关键字参数。

    Returns:
        List[InstrumentConfig]
    """
    from .config import InstrumentConfig

    if extra is None:
        extra = {}

    try:
        info = fetch_binance_symbol_info(symbols, base_url=base_url)
    except Exception:
        if fallback:
            info = {}
            for sym in symbols:
                if sym in DEFAULT_CRYPTO_SYMBOL_INFO:
                    info[sym] = dict(DEFAULT_CRYPTO_SYMBOL_INFO[sym])
                else:
                    info[sym] = {"step_size": 0.001, "min_qty": 0.001,
                                 "tick_size": 0.01, "min_notional": 5.0}
        else:
            raise

    configs: List[Any] = []
    for sym in symbols:
        params = info.get(sym, {})
        configs.append(InstrumentConfig(
            symbol=sym,
            asset_type="CRYPTO",
            multiplier=1.0,
            margin_ratio=margin_ratio,
            tick_size=params.get("tick_size", 0.01),
            step_size=params.get("step_size", 0.001),
            min_qty=params.get("min_qty", 0.001),
            min_notional=params.get("min_notional"),
            commission_rate=taker_commission_rate,
            **extra,
        ))

    return configs
