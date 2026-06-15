use std::collections::HashMap;

use super::tiers::TierTable;

/// 加密货币永续合约配置
#[derive(Debug, Clone)]
pub struct CryptoPerpConfig {
    /// 资金费率结算间隔 (秒)，默认 28800 (8h)
    pub funding_interval_seconds: i64,
    /// 启用资金费率结算
    pub enable_funding: bool,
    /// 启用强平检查
    pub enable_liquidation: bool,
    /// 维持保证金档位表: symbol -> Vec<Tier>
    pub maint_tiers: TierTable,
}

impl Default for CryptoPerpConfig {
    fn default() -> Self {
        Self {
            funding_interval_seconds: 28800,
            enable_funding: true,
            enable_liquidation: true,
            maint_tiers: HashMap::new(),
        }
    }
}
