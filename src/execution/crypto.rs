use crate::event::Event;
use crate::execution::common::CommonMatcher;
use crate::execution::matcher::{ExecutionMatcher, MatchContext};
use crate::log_context::{execution_order_context_from_event, render_log_message};
use crate::model::{Order, OrderStatus, OrderType};
use rust_decimal::Decimal;

pub struct CryptoMatcher;

impl CryptoMatcher {
    fn is_multiple(value: Decimal, step: Decimal) -> bool {
        if step <= Decimal::ZERO {
            return true;
        }
        value % step == Decimal::ZERO
    }

    fn reject(order: &mut Order, ctx: &MatchContext, reason: String) -> Option<Event> {
        order.status = OrderStatus::Rejected;
        order.reject_reason = reason.clone();
        match ctx.event {
            Event::Bar(b) => order.updated_at = b.timestamp,
            Event::Tick(t) => order.updated_at = t.timestamp,
            _ => {}
        }
        log::warn!(
            "{}",
            render_log_message(
                format!("Rejected crypto order because {}", reason),
                execution_order_context_from_event(order, ctx.event),
            )
        );
        Some(Event::ExecutionReport(order.clone(), None))
    }
}

impl ExecutionMatcher for CryptoMatcher {
    fn match_order(&self, order: &mut Order, ctx: &MatchContext) -> Option<Event> {
        let instrument = ctx.instrument;

        // 校验 quantity >= min_qty
        let min_qty = instrument.min_qty();
        if min_qty > Decimal::ZERO && order.quantity < min_qty {
            return Self::reject(
                order,
                ctx,
                format!(
                    "Quantity {} is less than minimum quantity {}. ",
                    order.quantity, min_qty
                ),
            );
        }

        // 校验 quantity 是否为 step_size 的整数倍
        let step = instrument.step_size();
        if step > Decimal::ZERO && !Self::is_multiple(order.quantity, step) {
            return Self::reject(
                order,
                ctx,
                format!(
                    "Quantity {} is not a multiple of step size {}. \
                     Use akquant.strategy_trading_api.round_qty() to align.",
                    order.quantity, step
                ),
            );
        }

        // 校验 price / trigger_price 是否为 tick_size 的整数倍
        let tick = instrument.tick_size();
        if tick > Decimal::ZERO {
            let mut prices_to_check: Vec<(&str, Decimal)> = Vec::new();
            match order.order_type {
                OrderType::Limit => {
                    if let Some(price) = order.price {
                        prices_to_check.push(("price", price));
                    }
                }
                OrderType::StopMarket => {
                    if let Some(trigger_price) = order.trigger_price {
                        prices_to_check.push(("trigger_price", trigger_price));
                    }
                }
                OrderType::StopLimit => {
                    if let Some(price) = order.price {
                        prices_to_check.push(("price", price));
                    }
                    if let Some(trigger_price) = order.trigger_price {
                        prices_to_check.push(("trigger_price", trigger_price));
                    }
                }
                _ => {}
            }
            for (field_name, value) in prices_to_check {
                if !Self::is_multiple(value, tick) {
                    return Self::reject(
                        order,
                        ctx,
                        format!(
                            "{} {} is not aligned with tick size {}. \
                             Use akquant.strategy_trading_api.round_price() to align.",
                            field_name, value, tick
                        ),
                    );
                }
            }
        }

        // 校验名义价值 >= min_notional
        let min_notional = instrument.min_notional();
        if min_notional > Decimal::ZERO {
            let notional_price = match order.order_type {
                OrderType::Limit => order.price,
                OrderType::StopMarket => order.trigger_price,
                OrderType::StopLimit => order.price.or(order.trigger_price),
                _ => match ctx.event {
                    Event::Bar(bar) => Some(bar.open),
                    Event::Tick(tick) => Some(tick.price),
                    _ => None,
                },
            };
            if let Some(price) = notional_price {
                let notional = price * order.quantity * instrument.multiplier();
                if notional < min_notional {
                    return Self::reject(
                        order,
                        ctx,
                        format!(
                            "Order notional value {} is less than minimum notional {}. \
                             Increase quantity or price.",
                            notional, min_notional
                        ),
                    );
                }
            }
        }

        CommonMatcher::match_order(order, ctx, false)
    }
}
