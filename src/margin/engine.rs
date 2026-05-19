use crate::margin::{
    FuturesMarginCalculator, LinearMarginCalculator, MarginCalculator, OptionMarginCalculator,
};
use crate::model::{AssetType, Instrument};
use rust_decimal::Decimal;
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, Default)]
pub struct MarginEngine;

impl MarginEngine {
    fn stock_margin_ratio_override(
        instrument: &Instrument,
        stock_margin_ratio_override: Option<Decimal>,
    ) -> Option<Decimal> {
        if matches!(instrument.asset_type, AssetType::Stock | AssetType::Fund) {
            return stock_margin_ratio_override;
        }
        None
    }

    fn calculate_linear_margin(
        quantity: Decimal,
        price: Decimal,
        instrument: &Instrument,
        stock_margin_ratio_override: Option<Decimal>,
    ) -> Decimal {
        if let Some(override_ratio) =
            Self::stock_margin_ratio_override(instrument, stock_margin_ratio_override)
        {
            return quantity.abs()
                * price.abs()
                * instrument.multiplier().abs()
                * override_ratio.abs();
        }
        LinearMarginCalculator.calculate_margin(quantity, price, instrument, None)
    }

    pub fn position_margin(
        quantity: Decimal,
        price: Decimal,
        instrument: &Instrument,
        prices: &HashMap<String, Decimal>,
        stock_margin_ratio_override: Option<Decimal>,
    ) -> Decimal {
        match instrument.asset_type {
            AssetType::Option => {
                let underlying_price = instrument
                    .underlying_symbol()
                    .and_then(|symbol| prices.get(symbol.as_str()).copied());
                OptionMarginCalculator.calculate_margin(
                    quantity,
                    price,
                    instrument,
                    underlying_price,
                )
            }
            AssetType::Futures => {
                FuturesMarginCalculator.calculate_margin(quantity, price, instrument, None)
            }
            AssetType::Stock | AssetType::Fund => Self::calculate_linear_margin(
                quantity,
                price,
                instrument,
                stock_margin_ratio_override,
            ),
            _ => LinearMarginCalculator.calculate_margin(quantity, price, instrument, None),
        }
    }

    pub fn used_margin(
        positions: &HashMap<String, Decimal>,
        prices: &HashMap<String, Decimal>,
        instruments: &HashMap<String, Instrument>,
        stock_margin_ratio_override: Option<Decimal>,
    ) -> Decimal {
        let mut used_margin = Decimal::ZERO;
        for (symbol, quantity) in positions {
            if quantity.is_zero() {
                continue;
            }
            let Some(price) = prices.get(symbol) else {
                continue;
            };
            let Some(instrument) = instruments.get(symbol) else {
                continue;
            };
            let margin = Self::position_margin(
                *quantity,
                *price,
                instrument,
                prices,
                stock_margin_ratio_override,
            );
            used_margin = used_margin.checked_add(margin).unwrap_or(Decimal::MAX);
            if used_margin == Decimal::MAX {
                break;
            }
        }
        used_margin
    }
}
