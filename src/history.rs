use crate::model::Bar;
use rust_decimal::prelude::ToPrimitive;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};

#[derive(Debug, Clone)]
pub struct SymbolHistory {
    pub timestamps: VecDeque<i64>,
    pub opens: VecDeque<f64>,
    pub highs: VecDeque<f64>,
    pub lows: VecDeque<f64>,
    pub closes: VecDeque<f64>,
    pub volumes: VecDeque<f64>,
    pub extras: HashMap<String, VecDeque<f64>>,
    pub capacity: usize,
}

impl SymbolHistory {
    pub fn new(capacity: usize) -> Self {
        SymbolHistory {
            timestamps: VecDeque::with_capacity(capacity),
            opens: VecDeque::with_capacity(capacity),
            highs: VecDeque::with_capacity(capacity),
            lows: VecDeque::with_capacity(capacity),
            closes: VecDeque::with_capacity(capacity),
            volumes: VecDeque::with_capacity(capacity),
            extras: HashMap::new(),
            capacity,
        }
    }

    pub fn push(&mut self, bar: &Bar) {
        if self.capacity == 0 {
            return;
        }

        if self.timestamps.len() >= self.capacity {
            self.timestamps.pop_front();
            self.opens.pop_front();
            self.highs.pop_front();
            self.lows.pop_front();
            self.closes.pop_front();
            self.volumes.pop_front();
            for v in self.extras.values_mut() {
                v.pop_front();
            }
        }

        let cur_len = self.timestamps.len();
        for (k, _) in bar.extra.iter() {
            if !self.extras.contains_key(k) {
                let mut dq = VecDeque::with_capacity(self.capacity);
                for _ in 0..cur_len {
                    dq.push_back(f64::NAN);
                }
                self.extras.insert(k.clone(), dq);
            }
        }
        for (k, dq) in self.extras.iter_mut() {
            let val = bar.extra.get(k).cloned().unwrap_or(f64::NAN);
            dq.push_back(val);
        }
        self.timestamps.push_back(bar.timestamp);
        self.opens.push_back(bar.open.to_f64().unwrap_or(0.0));
        self.highs.push_back(bar.high.to_f64().unwrap_or(0.0));
        self.lows.push_back(bar.low.to_f64().unwrap_or(0.0));
        self.closes.push_back(bar.close.to_f64().unwrap_or(0.0));
        self.volumes.push_back(bar.volume.to_f64().unwrap_or(0.0));
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SymbolHistorySnapshot {
    pub timestamps: VecDeque<i64>,
    pub opens: VecDeque<f64>,
    pub highs: VecDeque<f64>,
    pub lows: VecDeque<f64>,
    pub closes: VecDeque<f64>,
    pub volumes: VecDeque<f64>,
    pub extras: HashMap<String, VecDeque<f64>>,
    pub capacity: usize,
}

impl From<&SymbolHistory> for SymbolHistorySnapshot {
    fn from(history: &SymbolHistory) -> Self {
        Self {
            timestamps: history.timestamps.clone(),
            opens: history.opens.clone(),
            highs: history.highs.clone(),
            lows: history.lows.clone(),
            closes: history.closes.clone(),
            volumes: history.volumes.clone(),
            extras: history.extras.clone(),
            capacity: history.capacity,
        }
    }
}

impl From<SymbolHistorySnapshot> for SymbolHistory {
    fn from(snapshot: SymbolHistorySnapshot) -> Self {
        Self {
            timestamps: snapshot.timestamps,
            opens: snapshot.opens,
            highs: snapshot.highs,
            lows: snapshot.lows,
            closes: snapshot.closes,
            volumes: snapshot.volumes,
            extras: snapshot.extras,
            capacity: snapshot.capacity,
        }
    }
}

#[derive(Debug)]
pub struct HistoryBuffer {
    pub data: HashMap<String, SymbolHistory>,
    pub previous_data: HashMap<String, SymbolHistory>,
    pub default_capacity: usize,
}

impl HistoryBuffer {
    pub fn new(default_capacity: usize) -> Self {
        HistoryBuffer {
            data: HashMap::new(),
            previous_data: HashMap::new(),
            default_capacity,
        }
    }

    pub fn set_capacity(&mut self, capacity: usize) {
        self.default_capacity = capacity;
        self.data.clear();
        self.previous_data.clear();
    }

    pub fn set_capacity_preserve_existing(&mut self, capacity: usize) {
        self.default_capacity = capacity;
        self.previous_data.clear();
        if capacity == 0 {
            self.data.clear();
            return;
        }

        for history in self.data.values_mut() {
            history.capacity = capacity;
            while history.timestamps.len() > capacity {
                history.timestamps.pop_front();
                history.opens.pop_front();
                history.highs.pop_front();
                history.lows.pop_front();
                history.closes.pop_front();
                history.volumes.pop_front();
                for values in history.extras.values_mut() {
                    values.pop_front();
                }
            }
        }
    }

    pub fn update(&mut self, bar: &Bar) {
        if self.default_capacity == 0 {
            return;
        }

        let symbol = bar.symbol.clone();
        let history = self
            .data
            .entry(symbol.clone())
            .or_insert_with(|| SymbolHistory::new(self.default_capacity));
        if history.timestamps.is_empty() {
            self.previous_data.remove(&symbol);
        } else {
            self.previous_data.insert(symbol, history.clone());
        }

        history.push(bar);
    }

    pub fn get_history(&self, symbol: &str) -> Option<&SymbolHistory> {
        self.data.get(symbol)
    }

    pub fn get_previous_history(&self, symbol: &str) -> Option<&SymbolHistory> {
        self.previous_data.get(symbol)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryBufferSnapshot {
    pub data: HashMap<String, SymbolHistorySnapshot>,
    pub default_capacity: usize,
}

impl From<&HistoryBuffer> for HistoryBufferSnapshot {
    fn from(buffer: &HistoryBuffer) -> Self {
        Self {
            data: buffer
                .data
                .iter()
                .map(|(symbol, history)| (symbol.clone(), SymbolHistorySnapshot::from(history)))
                .collect(),
            default_capacity: buffer.default_capacity,
        }
    }
}

impl From<HistoryBufferSnapshot> for HistoryBuffer {
    fn from(snapshot: HistoryBufferSnapshot) -> Self {
        Self {
            data: snapshot
                .data
                .into_iter()
                .map(|(symbol, history)| (symbol, SymbolHistory::from(history)))
                .collect(),
            previous_data: HashMap::new(),
            default_capacity: snapshot.default_capacity,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{HistoryBuffer, HistoryBufferSnapshot};
    use crate::model::Bar;
    use rust_decimal::Decimal;
    use std::collections::HashMap;

    fn make_bar(timestamp: i64, close: i64, extra: Option<(&str, f64)>) -> Bar {
        let mut extra_map = HashMap::new();
        if let Some((key, value)) = extra {
            extra_map.insert(key.to_string(), value);
        }
        Bar {
            timestamp,
            open: Decimal::from(close),
            high: Decimal::from(close),
            low: Decimal::from(close),
            close: Decimal::from(close),
            volume: Decimal::from(1000),
            symbol: "TEST".to_string(),
            extra: extra_map,
        }
    }

    #[test]
    fn test_history_buffer_snapshot_roundtrip_preserves_history() {
        let mut buffer = HistoryBuffer::new(4);
        buffer.update(&make_bar(1, 10, Some(("factor", 1.0))));
        buffer.update(&make_bar(2, 11, None));
        buffer.update(&make_bar(3, 12, Some(("factor", 3.0))));

        let snapshot = HistoryBufferSnapshot::from(&buffer);
        let encoded = rmp_serde::to_vec(&snapshot).expect("serialize history snapshot");
        let decoded: HistoryBufferSnapshot =
            rmp_serde::from_slice(&encoded).expect("deserialize history snapshot");
        let restored = HistoryBuffer::from(decoded);

        assert_eq!(restored.default_capacity, 4);
        let history = restored.get_history("TEST").expect("history for TEST");
        assert_eq!(history.capacity, 4);
        assert_eq!(
            history.timestamps.iter().copied().collect::<Vec<_>>(),
            vec![1, 2, 3]
        );
        assert_eq!(
            history.closes.iter().copied().collect::<Vec<_>>(),
            vec![10.0, 11.0, 12.0]
        );
        let extras = history.extras.get("factor").expect("factor extra history");
        assert_eq!(extras.len(), 3);
        assert_eq!(extras[0], 1.0);
        assert!(extras[1].is_nan());
        assert_eq!(extras[2], 3.0);
    }

    #[test]
    fn test_set_capacity_preserve_existing_keeps_tail_window() {
        let mut buffer = HistoryBuffer::new(4);
        for (timestamp, close) in [(1, 10), (2, 11), (3, 12), (4, 13)] {
            buffer.update(&make_bar(timestamp, close, Some(("factor", close as f64))));
        }

        buffer.set_capacity_preserve_existing(2);

        assert_eq!(buffer.default_capacity, 2);
        let history = buffer.get_history("TEST").expect("history for TEST");
        assert_eq!(history.capacity, 2);
        assert_eq!(
            history.timestamps.iter().copied().collect::<Vec<_>>(),
            vec![3, 4]
        );
        assert_eq!(
            history.closes.iter().copied().collect::<Vec<_>>(),
            vec![12.0, 13.0]
        );
        let extras = history.extras.get("factor").expect("factor extra history");
        assert_eq!(extras.iter().copied().collect::<Vec<_>>(), vec![12.0, 13.0]);
    }
}
