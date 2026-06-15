use std::collections::HashMap;

use rust_decimal::Decimal;
use rust_decimal::prelude::*;

/// 维持保证金档位 (对齐 Binance USDⓈ-M 规格)
///
/// 维持保证金 = 名义价值 × maint_margin_rate - maint_amount
/// maint_amount 保证档位边界处平滑过渡, 无跳变。
#[derive(Debug, Clone, Copy)]
pub struct MaintenanceMarginTier {
    /// 名义价值上限 (USD)
    pub notional_upper: f64,
    /// 维持保证金率
    pub maint_margin_rate: f64,
    /// 维持保证金扣减 (USD)
    pub maint_amount: f64,
}

/// 档位表: symbol -> Vec<Tier> (从小到大排列)
pub type TierTable = HashMap<String, Vec<MaintenanceMarginTier>>;

/// 根据名义价值查档位, 返回 (rate, amount)
///
/// 如果该 symbol 没有档位表配置, 返回默认 (0.005, 0.0)
/// 如果超过最高档位, 使用最高档的值
pub fn lookup_tier(symbol: &str, notional: f64, table: &TierTable) -> (f64, f64) {
    let tiers = match table.get(symbol) {
        Some(t) => t,
        None => return (0.005, 0.0),
    };
    for tier in tiers {
        if notional <= tier.notional_upper {
            return (tier.maint_margin_rate, tier.maint_amount);
        }
    }
    let last = tiers.last().unwrap();
    (last.maint_margin_rate, last.maint_amount)
}

/// 计算维持保证金: max(0, notional × rate - amount)
pub fn calculate_maintenance(
    symbol: &str,
    notional: Decimal,
    table: &TierTable,
) -> Decimal {
    let nf = notional.to_f64().unwrap_or(0.0);
    let (rate, amount) = lookup_tier(symbol, nf, table);
    let maint = notional * Decimal::from_f64(rate).unwrap_or(Decimal::ZERO)
        - Decimal::from_f64(amount).unwrap_or(Decimal::ZERO);
    maint.max(Decimal::ZERO)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn btc_tiers() -> Vec<MaintenanceMarginTier> {
        vec![
            MaintenanceMarginTier { notional_upper: 300_000.0,  maint_margin_rate: 0.004,  maint_amount: 0.0 },
            MaintenanceMarginTier { notional_upper: 800_000.0,  maint_margin_rate: 0.005,  maint_amount: 300.0 },
            MaintenanceMarginTier { notional_upper: 3_000_000.0, maint_margin_rate: 0.0065, maint_amount: 1_500.0 },
            MaintenanceMarginTier { notional_upper: 12_000_000.0,maint_margin_rate: 0.01,   maint_amount: 12_000.0 },
        ]
    }

    #[test]
    fn test_first_tier_rate() {
        let mut table = TierTable::new();
        table.insert("BTCUSDT".to_string(), btc_tiers());
        let (rate, amount) = lookup_tier("BTCUSDT", 50_000.0, &table);
        assert!((rate - 0.004).abs() < 1e-10);
        assert!((amount - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_boundary_smooth_300k() {
        let mut table = TierTable::new();
        table.insert("BTCUSDT".to_string(), btc_tiers());
        // tier 1 boundary: 300k × 0.004 = 1200
        let m1 = calculate_maintenance("BTCUSDT", Decimal::from(300_000), &table);
        assert!((m1 - Decimal::from(1200)).abs() < Decimal::ONE);
        // tier 2 just over: 300k × 0.005 - 300 = 1200 (smooth)
        let m2 = calculate_maintenance("BTCUSDT", Decimal::from(300_001), &table);
        assert!((m2 - Decimal::from(1200)).abs() < Decimal::ONE);
    }

    #[test]
    fn test_tier2_maintenance() {
        let mut table = TierTable::new();
        table.insert("BTCUSDT".to_string(), btc_tiers());
        // 500k × 0.005 - 300 = 2200
        let m = calculate_maintenance("BTCUSDT", Decimal::from(500_000), &table);
        assert!((m - Decimal::from(2200)).abs() < Decimal::ONE);
    }

    #[test]
    fn test_tier3_maintenance() {
        let mut table = TierTable::new();
        table.insert("BTCUSDT".to_string(), btc_tiers());
        // 2M × 0.0065 - 1500 = 11,500
        let m = calculate_maintenance("BTCUSDT", Decimal::from(2_000_000), &table);
        assert!((m - Decimal::from(11500)).abs() < Decimal::ONE);
    }

    #[test]
    fn test_beyond_last_tier() {
        let mut table = TierTable::new();
        table.insert("BTCUSDT".to_string(), btc_tiers());
        // 20M × 0.01 - 12000 = 188,000
        let m = calculate_maintenance("BTCUSDT", Decimal::from(20_000_000), &table);
        assert!((m - Decimal::from(188_000)).abs() < Decimal::ONE);
    }

    #[test]
    fn test_missing_symbol_default() {
        let table = TierTable::new();
        let m = calculate_maintenance("ETHUSDT", Decimal::from(50_000), &table);
        assert!((m - Decimal::from(250)).abs() < Decimal::ONE); // 50k × 0.5% = 250
    }
}
