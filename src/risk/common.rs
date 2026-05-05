use crate::error::AkQuantError;
use crate::model::{AssetType, Order, OrderSide, project_position_after};
use rust_decimal::Decimal;
use rust_decimal::prelude::*;
use std::collections::HashMap;

use super::rule::{RiskCheckContext, RiskRule};

const RISK_OVERFLOW_PREFIX: &str = "AKQ-RISK-OVERFLOW";

fn risk_overflow_error(symbol: &str, field: &str) -> AkQuantError {
    AkQuantError::OrderError(format!(
        "[{RISK_OVERFLOW_PREFIX}] overflow while calculating margin for {symbol} at {field}",
    ))
}

fn checked_sub_or_zero(lhs: Decimal, rhs: Decimal) -> Decimal {
    lhs.checked_sub(rhs).unwrap_or(Decimal::ZERO)
}

fn checked_mul_or_err(
    lhs: Decimal,
    rhs: Decimal,
    symbol: &str,
    field: &str,
) -> Result<Decimal, AkQuantError> {
    lhs.checked_mul(rhs)
        .ok_or_else(|| risk_overflow_error(symbol, field))
}

fn checked_sub_or_err(
    lhs: Decimal,
    rhs: Decimal,
    symbol: &str,
    field: &str,
) -> Result<Decimal, AkQuantError> {
    lhs.checked_sub(rhs)
        .ok_or_else(|| risk_overflow_error(symbol, field))
}

/// Check restricted list
#[derive(Debug, Clone)]
pub struct RestrictedListRule;

impl RiskRule for RestrictedListRule {
    fn name(&self) -> &'static str {
        "RestrictedListRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if ctx.config.restricted_list.contains(&order.symbol) {
            return Err(AkQuantError::OrderError(format!(
                "Risk: Symbol {} is restricted",
                order.symbol
            )));
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

/// Check max order size
#[derive(Debug, Clone)]
pub struct MaxOrderSizeRule;

impl RiskRule for MaxOrderSizeRule {
    fn name(&self) -> &'static str {
        "MaxOrderSizeRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if let Some(max_size) = ctx.config.max_order_size
            && order.quantity > max_size
        {
            return Err(AkQuantError::OrderError(format!(
                "Risk: Order quantity {} exceeds limit {}",
                order.quantity, max_size
            )));
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

/// Check max order value
#[derive(Debug, Clone)]
pub struct MaxOrderValueRule;

impl RiskRule for MaxOrderValueRule {
    fn name(&self) -> &'static str {
        "MaxOrderValueRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if let Some(max_value) = ctx.config.max_order_value {
            let price = if let Some(p) = order.price {
                Some(p)
            } else {
                ctx.current_prices.get(&order.symbol).copied()
            };

            if let Some(p) = price {
                let value = p * order.quantity;
                if value > max_value {
                    return Err(AkQuantError::OrderError(format!(
                        "Risk: Order value {value} exceeds limit {max_value}",
                    )));
                }
            }
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

/// Check max position size
#[derive(Debug, Clone)]
pub struct MaxPositionSizeRule;

impl RiskRule for MaxPositionSizeRule {
    fn name(&self) -> &'static str {
        "MaxPositionSizeRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if let Some(max_pos) = ctx.config.max_position_size {
            let current_pos = ctx
                .portfolio
                .positions
                .get(&order.symbol)
                .copied()
                .unwrap_or(Decimal::ZERO);
            let new_pos = project_position_after(
                order.side,
                order.position_effect,
                current_pos,
                order.quantity,
            );
            if new_pos.abs() > max_pos {
                return Err(AkQuantError::OrderError(format!(
                    "Risk: Resulting position {new_pos} exceeds limit {max_pos}",
                )));
            }
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

/// Check cash / margin sufficiency
#[derive(Debug, Clone)]
pub struct CashMarginRule;

impl RiskRule for CashMarginRule {
    fn name(&self) -> &'static str {
        "CashMarginRule"
    }

    fn check(&self, order: &Order, ctx: &RiskCheckContext) -> Result<(), AkQuantError> {
        if ctx.config.check_cash {
            let order_price = if let Some(p) = order.price {
                p
            } else if let Some(p) = ctx.current_prices.get(&order.symbol) {
                *p
            } else {
                return Ok(());
            };

            let mut prices_for_order = ctx.current_prices.clone();
            prices_for_order.insert(order.symbol.clone(), order_price);

            let mut projected_portfolio = ctx.portfolio.clone();
            for o in ctx.active_orders {
                if o.status != crate::model::OrderStatus::New {
                    continue;
                }
                let active_price = if let Some(p) = o.price {
                    p
                } else if let Some(p) = ctx.current_prices.get(&o.symbol) {
                    *p
                } else {
                    continue;
                };
                if let Some(instr) = ctx.instruments.get(&o.symbol) {
                    let cost = active_price * o.quantity * instr.multiplier();
                    let current_pos = projected_portfolio
                        .positions
                        .get(&o.symbol)
                        .copied()
                        .unwrap_or(Decimal::ZERO);
                    let next_pos =
                        project_position_after(o.side, o.position_effect, current_pos, o.quantity);
                    let delta = next_pos - current_pos;
                    match o.side {
                        OrderSide::Buy => {
                            projected_portfolio.adjust_cash(-cost);
                            projected_portfolio.adjust_position(&o.symbol, delta);
                        }
                        OrderSide::Sell => {
                            projected_portfolio.adjust_cash(cost);
                            projected_portfolio.adjust_position(&o.symbol, delta);
                        }
                    }
                }
            }

            let required_margin =
                calc_required_margin_delta(order, ctx, &prices_for_order, &projected_portfolio)?;

            if required_margin.is_zero() {
                return Ok(());
            }

            let free_margin =
                projected_portfolio.calculate_free_margin_with_stock_ratio(
                    ctx.current_prices,
                    ctx.instruments,
                    if ctx.config.is_margin_account() {
                        Some(ctx.config.stock_initial_margin_ratio())
                    } else {
                        None
                    },
                );
            let safety_margin = ctx.config.safety_margin;
            let safety_factor = Decimal::from_f64(1.0 - safety_margin)
                .unwrap_or(Decimal::from_f64(0.9999).unwrap());
            let available_margin = free_margin
                .checked_mul(safety_factor)
                .unwrap_or(Decimal::ZERO)
                .max(Decimal::ZERO);

            if required_margin > available_margin {
                return Err(AkQuantError::OrderError(format!(
                    "Risk: Insufficient margin. Required: {required_margin}, Available: {available_margin} (Free: {free_margin}, Safety: {safety_margin})",
                )));
            }
        }
        Ok(())
    }

    fn clone_box(&self) -> Box<dyn RiskRule> {
        Box::new(self.clone())
    }
}

fn stock_margin_delta(
    order: &Order,
    current_pos: Decimal,
    price: Decimal,
    multiplier: Decimal,
    initial_margin_ratio: Decimal,
) -> Result<Decimal, AkQuantError> {
    let current_abs = current_pos.abs();
    let safe_price = price.abs();
    let safe_multiplier = multiplier.abs();
    let safe_initial_margin_ratio = initial_margin_ratio.abs();
    let next_pos = project_position_after(
        order.side,
        order.position_effect,
        current_pos,
        order.quantity,
    );
    let next_abs = next_pos.abs();
    let current_notional = checked_mul_or_err(
        current_abs,
        safe_price,
        &order.symbol,
        "current_abs * price",
    )?;
    let current_gross = checked_mul_or_err(
        current_notional,
        safe_multiplier,
        &order.symbol,
        "current_notional * multiplier",
    )?;
    let current_margin = checked_mul_or_err(
        current_gross,
        safe_initial_margin_ratio,
        &order.symbol,
        "current_gross * initial_margin_ratio",
    )?;

    let next_notional =
        checked_mul_or_err(next_abs, safe_price, &order.symbol, "next_abs * price")?;
    let next_gross = checked_mul_or_err(
        next_notional,
        safe_multiplier,
        &order.symbol,
        "next_notional * multiplier",
    )?;
    let next_margin = checked_mul_or_err(
        next_gross,
        safe_initial_margin_ratio,
        &order.symbol,
        "next_gross * initial_margin_ratio",
    )?;

    Ok(checked_sub_or_zero(next_margin, current_margin).max(Decimal::ZERO))
}

fn calc_required_margin_delta(
    order: &Order,
    ctx: &RiskCheckContext,
    prices: &HashMap<String, Decimal>,
    portfolio: &crate::portfolio::Portfolio,
) -> Result<Decimal, AkQuantError> {
    if let Some(instr) = ctx.instruments.get(&order.symbol) {
        if ctx.config.is_margin_account()
            && (instr.asset_type == AssetType::Stock || instr.asset_type == AssetType::Fund)
        {
            let price = prices
                .get(&order.symbol)
                .copied()
                .unwrap_or_else(|| order.price.unwrap_or(Decimal::ZERO));
            if price <= Decimal::ZERO {
                return Ok(Decimal::ZERO);
            }
            let current_pos = portfolio
                .positions
                .get(&order.symbol)
                .copied()
                .unwrap_or(Decimal::ZERO);
            return stock_margin_delta(
                order,
                current_pos,
                price,
                instr.multiplier(),
                ctx.config.stock_initial_margin_ratio(),
            );
        }
    }

    let mut projected_portfolio = portfolio.clone();
    let base_used = projected_portfolio.calculate_used_margin_with_stock_ratio(
        prices,
        ctx.instruments,
        if ctx.config.is_margin_account() {
            Some(ctx.config.stock_initial_margin_ratio())
        } else {
            None
        },
    );
    if base_used == Decimal::MAX {
        return Err(risk_overflow_error(&order.symbol, "base_used_margin"));
    }
    {
        let positions = std::sync::Arc::make_mut(&mut projected_portfolio.positions);
        let entry = positions
            .entry(order.symbol.clone())
            .or_insert(Decimal::ZERO);
        *entry = project_position_after(
            order.side,
            order.position_effect,
            *entry,
            order.quantity,
        );
    }
    let next_used = projected_portfolio.calculate_used_margin_with_stock_ratio(
        prices,
        ctx.instruments,
        if ctx.config.is_margin_account() {
            Some(ctx.config.stock_initial_margin_ratio())
        } else {
            None
        },
    );
    if next_used == Decimal::MAX {
        return Err(risk_overflow_error(&order.symbol, "next_used_margin"));
    }
    let delta = checked_sub_or_err(next_used, base_used, &order.symbol, "next_used - base_used")?;
    Ok(delta.max(Decimal::ZERO))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::margin::MarginEngine;
    use crate::model::instrument::{InstrumentEnum, OptionInstrument, StockInstrument};
    use crate::model::{Instrument, OptionMarginModel, OptionType, OrderType, TimeInForce};
    use crate::portfolio::Portfolio;
    use crate::risk::RiskConfig;
    use rust_decimal_macros::dec;
    use std::sync::Arc;

    fn create_stock_instrument(symbol: &str) -> Instrument {
        Instrument {
            asset_type: AssetType::Stock,
            inner: InstrumentEnum::Stock(StockInstrument {
                symbol: symbol.to_string(),
                lot_size: dec!(100),
                tick_size: dec!(0.01),
                expiry_date: None,
            }),
        }
    }

    fn create_china_short_put(symbol: &str, underlying_symbol: &str) -> Instrument {
        Instrument {
            asset_type: AssetType::Option,
            inner: InstrumentEnum::Option(OptionInstrument {
                symbol: symbol.to_string(),
                multiplier: dec!(100),
                margin_ratio: dec!(0.2),
                tick_size: dec!(0.01),
                option_margin_model: OptionMarginModel::ChinaSingleLeg,
                option_type: OptionType::Put,
                strike_price: dec!(100),
                expiry_date: 20260101,
                underlying_symbol: underlying_symbol.to_string(),
                settlement_type: None,
                implied_volatility: None,
                reference_volatility: None,
            }),
        }
    }

    fn create_order(symbol: &str, side: OrderSide, quantity: Decimal, price: Decimal) -> Order {
        let mut order = Order::test_new("test", symbol, side, OrderType::Limit, quantity);
        order.price = Some(price);
        order.time_in_force = TimeInForce::Day;
        order.status = crate::model::OrderStatus::New;
        order
    }

    #[test]
    fn required_margin_delta_for_china_short_put_matches_margin_engine() {
        let option = create_china_short_put("OPT_P", "510050.SH");
        let mut instruments = HashMap::new();
        instruments.insert("OPT_P".to_string(), option.clone());

        let mut prices = HashMap::new();
        prices.insert("OPT_P".to_string(), dec!(4));
        prices.insert("510050.SH".to_string(), dec!(110));

        let portfolio = Portfolio {
            cash: dec!(100000),
            positions: Arc::new(HashMap::new()),
            available_positions: Arc::new(HashMap::new()),
        };
        let instrument_ref = instruments.get("OPT_P").unwrap();
        let config = RiskConfig::new();
        let ctx = RiskCheckContext {
            portfolio: &portfolio,
            instrument: instrument_ref,
            instruments: &instruments,
            active_orders: &[],
            current_prices: &prices,
            current_time: 0,
            config: &config,
        };
        let order = create_order("OPT_P", OrderSide::Sell, dec!(1), dec!(4));

        let required = calc_required_margin_delta(&order, &ctx, &prices, &portfolio).unwrap();
        let expected =
            MarginEngine::position_margin(dec!(-1), dec!(4), instrument_ref, &prices, None);

        assert_eq!(required, dec!(1100));
        assert_eq!(required, expected);
    }

    #[test]
    fn cash_margin_rule_matches_execution_resize_boundary_for_stock_buys() {
        let stock = create_stock_instrument("AAPL");
        let mut instruments = HashMap::new();
        instruments.insert("AAPL".to_string(), stock.clone());

        let mut prices = HashMap::new();
        prices.insert("AAPL".to_string(), dec!(100));

        let portfolio = Portfolio {
            cash: dec!(50000),
            positions: Arc::new(HashMap::new()),
            available_positions: Arc::new(HashMap::new()),
        };
        let instrument_ref = instruments.get("AAPL").unwrap();
        let config = RiskConfig::new();
        let ctx = RiskCheckContext {
            portfolio: &portfolio,
            instrument: instrument_ref,
            instruments: &instruments,
            active_orders: &[],
            current_prices: &prices,
            current_time: 0,
            config: &config,
        };
        let rule = CashMarginRule;

        let rejected = create_order("AAPL", OrderSide::Buy, dec!(500), dec!(100));
        let accepted = create_order("AAPL", OrderSide::Buy, dec!(400), dec!(100));

        let rejected_result = rule.check(&rejected, &ctx);
        let accepted_result = rule.check(&accepted, &ctx);

        assert!(rejected_result.is_err());
        assert!(
            rejected_result
                .unwrap_err()
                .to_string()
                .contains("Insufficient margin")
        );
        assert!(accepted_result.is_ok());
    }
}
