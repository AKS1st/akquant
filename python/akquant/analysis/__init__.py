"""Structured analysis helpers for AKQuant results."""

from .benchmark import (
    benchmark_analysis_from_result,
    build_benchmark_analysis,
    build_daily_returns_from_equity,
    normalize_curve_freq,
    normalize_returns_series,
    normalize_returns_series_with_reason,
    resolve_benchmark_returns,
    resolve_equity_curve,
)

__all__ = [
    "benchmark_analysis_from_result",
    "build_benchmark_analysis",
    "build_daily_returns_from_equity",
    "normalize_curve_freq",
    "normalize_returns_series",
    "normalize_returns_series_with_reason",
    "resolve_benchmark_returns",
    "resolve_equity_curve",
]
