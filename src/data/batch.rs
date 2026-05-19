use crate::log_context::{AkqLogContext, format_event_time_nanos, render_log_message};
use crate::model::Bar;
use numpy::PyReadonlyArray1;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_stub_gen::derive::*;
use rust_decimal::prelude::*;
use std::collections::HashMap;

/// 从数组批量创建 Bar 列表 (Python 优化用 - Zero Copy).
///
/// :param timestamps: 时间戳数组
/// :param opens: 开盘价数组
/// :param highs: 最高价数组
/// :param lows: 最低价数组
/// :param closes: 收盘价数组
/// :param volumes: 成交量数组
/// :param symbol: 标的代码 (可选)
/// :param symbols: 标的代码数组 (可选)
/// :param extra: 额外数据 (可选)
#[gen_stub_pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
pub fn from_arrays(
    timestamps: &Bound<'_, PyAny>,
    opens: &Bound<'_, PyAny>,
    highs: &Bound<'_, PyAny>,
    lows: &Bound<'_, PyAny>,
    closes: &Bound<'_, PyAny>,
    volumes: &Bound<'_, PyAny>,
    symbol: Option<String>,
    symbols: Option<Vec<String>>,
    extra: Option<HashMap<String, Py<PyAny>>>,
    py: Python<'_>,
) -> PyResult<Vec<Bar>> {
    fn warn_invalid_numeric(field_name: &str, value: f64, symbol: &str, timestamp_ns: i64) {
        log::warn!(
            "{}",
            render_log_message(
                format!("Invalid {field_name} {value}, defaulting to 0.0"),
                AkqLogContext::new()
                    .phase("data")
                    .symbol(symbol)
                    .event_time_str(format_event_time_nanos(timestamp_ns)),
            )
        );
    }

    let timestamps: PyReadonlyArray1<i64> = timestamps.extract()?;
    let opens: PyReadonlyArray1<f64> = opens.extract()?;
    let highs: PyReadonlyArray1<f64> = highs.extract()?;
    let lows: PyReadonlyArray1<f64> = lows.extract()?;
    let closes: PyReadonlyArray1<f64> = closes.extract()?;
    let volumes: PyReadonlyArray1<f64> = volumes.extract()?;

    let timestamps = timestamps.as_array();
    let opens = opens.as_array();
    let highs = highs.as_array();
    let lows = lows.as_array();
    let closes = closes.as_array();
    let volumes = volumes.as_array();

    let len = timestamps.len();
    if opens.len() != len
        || highs.len() != len
        || lows.len() != len
        || closes.len() != len
        || volumes.len() != len
    {
        return Err(PyValueError::new_err(
            "All arrays must have the same length",
        ));
    }

    if let Some(ref syms) = symbols
        && syms.len() != len
    {
        return Err(PyValueError::new_err(
            "symbols array must have the same length as other arrays",
        ));
    }

    // Check extra arrays length
    // Need to collect extra arrays into a more usable format for iteration
    let mut extra_arrays = HashMap::new();
    // Use a temporary vec to hold the readonly arrays to keep them alive
    let mut extra_guards = Vec::new();

    if let Some(ref extra_data) = extra {
        for (key, val) in extra_data {
            let arr: PyReadonlyArray1<f64> = val.extract(py)?;
            let array_view = arr.as_array();
            if array_view.len() != len {
                return Err(PyValueError::new_err(format!(
                    "Extra array '{}' must have the same length as other arrays",
                    key
                )));
            }
            // We need to extend the lifetime or copy the data if we want to store views
            // But since we process in loop below, we can't easily store views in HashMap referring to local vars in loop
            // unless we structure this differently.
            // For simplicity and safety with PyO3 lifetimes, let's just push to a list and index
            // OR simpler: collect all guards first.
            extra_guards.push((key.clone(), arr));
        }
    }

    // Re-build map of views
    for (k, guard) in &extra_guards {
        extra_arrays.insert(k.clone(), guard.as_array());
    }

    let mut bars = Vec::with_capacity(len);

    for i in 0..len {
        let sym = if let Some(ref syms) = symbols {
            syms[i].clone()
        } else if let Some(ref s) = symbol {
            s.clone()
        } else {
            "UNKNOWN".to_string()
        };

        let ts = timestamps[i];
        // Timestamps from Python/Pandas are already in nanoseconds (int64)
        // No normalization needed (and normalization can be buggy for dates near 1970)
        let normalized_ts = ts;

        let mut bar_extra = HashMap::new();
        for (k, arr) in &extra_arrays {
            bar_extra.insert(k.clone(), arr[i]);
        }

        bars.push(Bar {
            timestamp: normalized_ts,
            open: Decimal::from_f64(opens[i]).unwrap_or_else(|| {
                warn_invalid_numeric("open price", opens[i], sym.as_str(), normalized_ts);
                Decimal::ZERO
            }),
            high: Decimal::from_f64(highs[i]).unwrap_or_else(|| {
                warn_invalid_numeric("high price", highs[i], sym.as_str(), normalized_ts);
                Decimal::ZERO
            }),
            low: Decimal::from_f64(lows[i]).unwrap_or_else(|| {
                warn_invalid_numeric("low price", lows[i], sym.as_str(), normalized_ts);
                Decimal::ZERO
            }),
            close: Decimal::from_f64(closes[i]).unwrap_or_else(|| {
                warn_invalid_numeric("close price", closes[i], sym.as_str(), normalized_ts);
                Decimal::ZERO
            }),
            volume: Decimal::from_f64(volumes[i]).unwrap_or_else(|| {
                warn_invalid_numeric("volume", volumes[i], sym.as_str(), normalized_ts);
                Decimal::ZERO
            }),
            symbol: sym,
            extra: bar_extra,
        });
    }

    Ok(bars)
}
