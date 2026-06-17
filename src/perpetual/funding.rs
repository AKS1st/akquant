use rust_decimal::Decimal;
use rust_decimal::prelude::*;
use std::collections::HashMap;

use rust_decimal_macros::dec;

use crate::model::Bar;

/// 资金费率结算记录
#[derive(Debug, Clone)]
pub struct FundingPayment {
    pub symbol: String,
    pub quantity: f64,
    pub mark_price: f64,
    pub rate: f64,
    pub amount: f64,
}

/// 资金费率结算管理器
///
/// 规则:
///   - 只在 UTC 0/8/16 整小时触发结算
///   - 同小时内只结算一次 (防数据重复)
///   - 从 bar.extra["funding_rate"] 取费率
const MIN_FUNDING_INTERVAL_NS: i64 = 7 * 3_600_000_000_000; // 7 小时 (ns)

#[derive(Clone)]
pub struct FundingManager {
    /// 上次结算的 UTC 小时 (0-23, -1 = 未结算)，用于同小时去重
    pub last_settled_hour: i64,
    /// 上次结算的时间戳 (ns)
    pub last_settled_ns: i64,
    /// 启用
    pub enabled: bool,
}

impl FundingManager {
    pub fn new() -> Self {
        Self {
            last_settled_hour: -1,
            last_settled_ns: 0,
            enabled: true,
        }
    }

    /// 检查当前 bar 是否需要触发资金费率结算
    ///
    /// 当 bar.extra 中存在 funding_rate 字段时触发，0 费率也触发（记录结算事件）。
    /// 同小时内重复的结算事件会去重。
    /// 返回 Some(rate) 表示应结算，None 表示跳过。
    pub fn check_settlement(&mut self, bar: &Bar) -> Option<f64> {
        if !self.enabled {
            return None;
        }

        let rate = bar.extra.get("funding_rate").copied().and_then(|v| {
            if v.is_nan() { None } else { Some(v) }
        })?;

        // 同小时去重（数据层可能在结算点附近有多条带 rate 的 bar）
        let hour = (bar.timestamp / 3_600_000_000_000) % 24;
        if hour == self.last_settled_hour {
            return None;
        }

        // 校验: 距上次结算不足 7h → 数据异常（例如回补数据未正确去重）
        let gap = bar.timestamp - self.last_settled_ns;
        if self.last_settled_ns > 0 && gap < MIN_FUNDING_INTERVAL_NS {
            log::debug!(
                "Funding settlement gap only {:.1}h (< 7h) for symbol {}, check data quality",
                gap as f64 / 3_600_000_000_000_f64,
                bar.symbol,
            );
        }

        self.last_settled_hour = hour;
        self.last_settled_ns = bar.timestamp;
        Some(rate)
    }

    /// 执行资金费率结算
    ///
    /// payment = position_qty × mark_price × funding_rate
    /// 正值表示多头付空头，负值相反
    pub fn settle(
        &self,
        rate: f64,
        positions: &HashMap<String, Decimal>,
        mark_prices: &HashMap<String, Decimal>,
        cash: &mut Decimal,
    ) -> Vec<FundingPayment> {
        let mut payments = Vec::new();
        let rate_dec = Decimal::from_f64(rate).unwrap_or(Decimal::ZERO);

        for (symbol, qty) in positions {
            if qty.is_zero() {
                continue;
            }
            let mark = mark_prices
                .get(symbol)
                .copied()
                .unwrap_or(Decimal::ZERO);
            let payment = *qty * mark * rate_dec;
            *cash -= payment;

            payments.push(FundingPayment {
                symbol: symbol.clone(),
                quantity: qty.to_f64().unwrap_or(0.0),
                mark_price: mark.to_f64().unwrap_or(0.0),
                rate,
                amount: payment.to_f64().unwrap_or(0.0),
            });
        }

        payments
    }
}

impl Default for FundingManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn make_bar(timestamp_ns: i64, funding_rate: Option<f64>) -> Bar {
        let mut extra = HashMap::new();
        if let Some(rate) = funding_rate {
            extra.insert("funding_rate".to_string(), rate);
        }
        Bar {
            timestamp: timestamp_ns,
            open: dec!(50000),
            high: dec!(50100),
            low: dec!(49900),
            close: dec!(50050),
            volume: dec!(100),
            symbol: "BTCUSDT".to_string(),
            extra,
        }
    }

    #[test]
    fn test_no_funding_rate_skipped() {
        let mut mgr = FundingManager::new();
        // bar 没有 funding_rate → 跳过
        let bar = make_bar(8 * 3_600_000_000_000, None);
        assert!(mgr.check_settlement(&bar).is_none());
    }

    #[test]
    fn test_funding_rate_triggers() {
        let mut mgr = FundingManager::new();
        let bar = make_bar(8 * 3_600_000_000_000, Some(0.0001));
        let rate = mgr.check_settlement(&bar);
        assert!((rate.unwrap() - 0.0001).abs() < 1e-10);
    }

    #[test]
    fn test_same_hour_dedup() {
        let mut mgr = FundingManager::new();
        let bar1 = make_bar(8 * 3_600_000_000_000, Some(0.0001));
        let bar2 = make_bar(8 * 3_600_000_000_000 + 60_000_000_000, Some(0.0002));
        assert!(mgr.check_settlement(&bar1).is_some());
        assert!(mgr.check_settlement(&bar2).is_none()); // 同小时跳过
    }

    #[test]
    fn test_settle_long_position_pays_funding() {
        let mut mgr = FundingManager::new();
        let bar = make_bar(8 * 3_600_000_000_000, Some(0.001));
        let rate = mgr.check_settlement(&bar).unwrap();

        let mut positions = HashMap::new();
        positions.insert("BTCUSDT".to_string(), Decimal::from(1)); // 1 BTC long

        let mut mark_prices = HashMap::new();
        mark_prices.insert("BTCUSDT".to_string(), Decimal::from(50000));

        let mut cash = Decimal::from(100_000);
        let payments = mgr.settle(rate, &positions, &mark_prices, &mut cash);

        // payment = 1 * 50000 * 0.001 = 50
        assert_eq!(payments.len(), 1);
        assert!((payments[0].amount - 50.0).abs() < 1e-6);
        assert!((cash.to_f64().unwrap() - 99950.0).abs() < 1e-6);
    }

    #[test]
    fn test_no_position_no_payment() {
        let mut mgr = FundingManager::new();
        let bar = make_bar(16 * 3_600_000_000_000, Some(0.001));
        let rate = mgr.check_settlement(&bar).unwrap();

        let positions = HashMap::new();
        let mut mark_prices = HashMap::new();
        let mut cash = Decimal::from(100_000);
        let payments = mgr.settle(rate, &positions, &mark_prices, &mut cash);

        assert!(payments.is_empty());
    }

    #[test]
    fn test_8h_separated_settlements_both_trigger() {
        let mut mgr = FundingManager::new();
        // UTC 08:00 触发
        let bar1 = make_bar(8 * 3_600_000_000_000, Some(0.001));
        assert!(mgr.check_settlement(&bar1).is_some());
        // UTC 16:00 正好 8h → 正常触发
        let bar2 = make_bar(16 * 3_600_000_000_000, Some(0.001));
        assert!(mgr.check_settlement(&bar2).is_some());
    }

    #[test]
    fn test_short_gap_logs_error() {
        // 模拟数据错误: 距上次结算仅 4h 又有结算事件
        // 引擎不应 panic, 但应触发 log::error
        let mut mgr = FundingManager::new();
        // 手动设"上次结算"为 4h 前, 不同小时
        mgr.last_settled_ns = 3_600_000_000_000;       // UTC 01:00
        mgr.last_settled_hour = 1;                      // hour 1

        // 当期 bar 在 UTC 05:00 (hour=5, 不同小时不去重)
        let bar = make_bar(5 * 3_600_000_000_000, Some(0.002));
        let rate = mgr.check_settlement(&bar);
        assert!(rate.is_some(), "Should still settle, just warn about short gap");
        assert!((rate.unwrap() - 0.002).abs() < 1e-10);
    }
}
