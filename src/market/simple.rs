use crate::model::{Instrument, OrderSide, TradingSession};
use chrono::NaiveTime;
use rust_decimal::Decimal;
use rust_decimal::prelude::*;
use std::collections::HashMap;

use super::core::MarketModel;
use super::stock::CommissionMode;

/// 简单市场配置
#[derive(Clone, Debug)]
pub struct SimpleMarketConfig {
    pub commission_mode: CommissionMode,
    pub commission_rate: Decimal,        // taker 费率
    pub maker_commission_rate: Decimal,  // maker 费率 (默认同 taker)
    pub stamp_tax: Decimal,
    pub transfer_fee: Decimal,
    pub min_commission: Decimal,
}

impl Default for SimpleMarketConfig {
    fn default() -> Self {
        Self {
            commission_mode: CommissionMode::Percent,
            commission_rate: Decimal::from_str("0.0003").unwrap(),
            maker_commission_rate: Decimal::from_str("0.0003").unwrap(),
            stamp_tax: Decimal::ZERO,
            transfer_fee: Decimal::ZERO,
            min_commission: Decimal::ZERO,
        }
    }
}

/// 简单市场模型 (如加密货币/外汇)
pub struct SimpleMarket {
    pub config: SimpleMarketConfig,
}

impl SimpleMarket {
    pub fn from_config(config: SimpleMarketConfig) -> Self {
        Self { config }
    }
}

impl MarketModel for SimpleMarket {
    fn get_session_status(&self, _time: NaiveTime) -> TradingSession {
        TradingSession::Continuous
    }

    fn calculate_commission(
        &self,
        instrument: &Instrument,
        side: OrderSide,
        price: Decimal,
        quantity: Decimal,
        is_maker: bool,
    ) -> Decimal {
        let turnover = price * quantity * instrument.multiplier();
        let rate = if is_maker {
            self.config.maker_commission_rate
        } else {
            self.config.commission_rate
        };
        let mut commission = match self.config.commission_mode {
            CommissionMode::Percent => turnover * rate,
            CommissionMode::Fixed => rate,
            CommissionMode::PerUnit => quantity * rate,
        };
        if commission < self.config.min_commission {
            commission = self.config.min_commission;
        }
        let tax = if side == OrderSide::Sell {
            turnover * self.config.stamp_tax
        } else {
            Decimal::ZERO
        };
        let transfer = turnover * self.config.transfer_fee;
        commission + tax + transfer
    }

    fn update_available_position(
        &self,
        available_positions: &mut HashMap<String, Decimal>,
        instrument: &Instrument,
        quantity: Decimal,
        side: OrderSide,
    ) {
        let symbol = instrument.symbol();
        match side {
            OrderSide::Buy => {
                available_positions
                    .entry(symbol.to_string())
                    .or_insert(Decimal::ZERO);
                if let Some(pos) = available_positions.get_mut(symbol) {
                    *pos += quantity;
                }
            }
            OrderSide::Sell => {
                if let Some(pos) = available_positions.get_mut(symbol) {
                    *pos -= quantity;
                }
            }
        }
    }

    fn on_day_close(
        &self,
        _positions: &HashMap<String, Decimal>,
        _available_positions: &mut HashMap<String, Decimal>,
        _instruments: &HashMap<String, Instrument>,
    ) {
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::instrument::{CryptoInstrument, InstrumentEnum};
    use crate::model::AssetType;
    use rust_decimal_macros::dec;

    fn crypto_instr() -> Instrument {
        Instrument {
            asset_type: AssetType::Crypto,
            inner: InstrumentEnum::Crypto(CryptoInstrument {
                symbol: "BTCUSDT".to_string(),
                lot_size: dec!(0.001),
                tick_size: dec!(0.01),
                step_size: dec!(0.001),
                min_qty: dec!(0.001),
                multiplier: dec!(1),
                margin_ratio: dec!(0.1),
            }),
        }
    }

    #[test]
    fn test_taker_maker_different_rates() {
        let config = SimpleMarketConfig {
            commission_mode: CommissionMode::Percent,
            commission_rate: dec!(0.001),           // taker: 0.1%
            maker_commission_rate: dec!(0.0005),    // maker: 0.05%
            stamp_tax: Decimal::ZERO,
            transfer_fee: Decimal::ZERO,
            min_commission: Decimal::ZERO,
        };
        let market = SimpleMarket::from_config(config);
        let instr = crypto_instr();

        let taker_fee = market.calculate_commission(
            &instr, OrderSide::Buy, dec!(50000), dec!(1), false,
        );
        let maker_fee = market.calculate_commission(
            &instr, OrderSide::Buy, dec!(50000), dec!(1), true,
        );

        assert_eq!(taker_fee, dec!(50));   // 50000 × 0.1%
        assert_eq!(maker_fee, dec!(25));   // 50000 × 0.05%
        assert!(taker_fee > maker_fee);
    }

    #[test]
    fn test_default_same_rate_maker_taker_equal() {
        // 不设 maker_commission_rate 时默认同 taker
        let market = SimpleMarket::from_config(SimpleMarketConfig::default());
        let instr = crypto_instr();

        let taker_fee = market.calculate_commission(
            &instr, OrderSide::Buy, dec!(50000), dec!(1), false,
        );
        let maker_fee = market.calculate_commission(
            &instr, OrderSide::Buy, dec!(50000), dec!(1), true,
        );

        assert_eq!(taker_fee, maker_fee);
    }
}
