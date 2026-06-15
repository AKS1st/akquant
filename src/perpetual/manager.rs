use super::config::CryptoPerpConfig;
use super::funding::FundingManager;
use super::liquidation::LiquidationManager;
use super::tiers::TierTable;

/// 加密货币永续合约管理器
///
/// 统一管理资金费率结算和强平检查两个子系统。
#[derive(Clone)]
pub struct CryptoPerpManager {
    pub funding: FundingManager,
    pub liquidation: LiquidationManager,
}

impl CryptoPerpManager {
    pub fn new() -> Self {
        Self::default()
    }

    /// 从配置初始化
    pub fn from_config(config: &CryptoPerpConfig) -> Self {
        Self {
            funding: FundingManager {
                enabled: config.enable_funding,
                ..FundingManager::new()
            },
            liquidation: LiquidationManager {
                enabled: config.enable_liquidation,
                tier_table: config.maint_tiers.clone(),
                ..LiquidationManager::new()
            },
        }
    }

    /// 启用/禁用
    pub fn set_enabled(&mut self, enabled: bool) {
        self.funding.enabled = enabled;
        self.liquidation.enabled = enabled;
    }
}

impl Default for CryptoPerpManager {
    fn default() -> Self {
        Self {
            funding: FundingManager::new(),
            liquidation: LiquidationManager::new(),
        }
    }
}
