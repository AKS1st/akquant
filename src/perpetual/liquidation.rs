use rust_decimal::Decimal;
use rust_decimal::prelude::*;
use std::collections::HashMap;
use uuid::Uuid;

use crate::event::Event;
use crate::model::{
    Bar, Instrument, Order, OrderRole, OrderSide, OrderStatus, OrderType, PositionEffect, TimeInForce,
    Trade,
};
use crate::portfolio::Portfolio;
use crate::analysis::TradeTracker;

use super::tiers::{calculate_maintenance, TierTable};

/// 强平管理器
///
/// 每个 bar 后检查持仓是否满足维持保证金要求。
/// 使用标记价格 (mark_price) 计算权益，非成交价。
///
/// 强平时直接生成已成交的 ExecutionReport（同期货强平做法），
/// 走现有 ChannelProcessor 处理链路，自动记录到 trade_tracker、
/// closed_trades、cash_curve。
#[derive(Clone)]
pub struct LiquidationManager {
    pub enabled: bool,
    /// 标记价格: symbol -> mark_price
    pub mark_prices: HashMap<String, Decimal>,
    /// 档位表
    pub tier_table: TierTable,
}

impl LiquidationManager {
    pub fn new() -> Self {
        Self {
            enabled: true,
            mark_prices: HashMap::new(),
            tier_table: HashMap::new(),
        }
    }

    /// 更新标记价格 (从 bar.extra 取)
    pub fn update_mark_price(&mut self, bar: &Bar) {
        if let Some(mp) = bar.extra.get("mark_price") {
            self.mark_prices
                .insert(bar.symbol.clone(), Decimal::from_f64(*mp).unwrap_or(Decimal::ZERO));
        }
    }

    /// 检查并执行强平
    ///
    /// 对每个持仓品种:
    ///   名义价值 = |qty| × mark_price × multiplier
    ///   维持保证金 = 名义价值 × 档位维持保证金率
    ///   未实现盈亏 = qty × (mark_price - avg_entry_price) × multiplier
    ///   权益 = cash + unrealized_pnl
    ///
    ///   如果权益 < 维持保证金 → 触发强平
    ///
    /// 强平方式：直接生成已填充的 Event::ExecutionReport，
    /// 走 SettlementManager 相同路径，不经过撮合引擎。
    pub fn check_liquidations(
        &self,
        portfolio: &Portfolio,
        instruments: &HashMap<String, Instrument>,
        trade_tracker: &TradeTracker,
        timestamp: i64,
        bar_index: usize,
    ) -> Vec<Event> {
        if !self.enabled {
            return vec![];
        }

        let mut events = vec![];

        for (symbol, qty) in portfolio.positions.iter() {
            if qty.is_zero() {
                continue;
            }
            let qty_dec = *qty;

            let Some(mark) = self.mark_prices.get(symbol).copied() else {
                continue;
            };
            let Some(instr) = instruments.get(symbol) else {
                continue;
            };
            let multiplier = instr.multiplier();

            // 未实现盈亏 (基于标记价格)
            let avg_entry = trade_tracker.get_average_price(symbol);
            let upnl = qty_dec * (mark - avg_entry) * multiplier;

            // 名义价值 → 查档位计算维持保证金
            let notional = qty_dec.abs() * mark * multiplier;
            let maintenance = calculate_maintenance(symbol, notional, &self.tier_table);

            let equity = portfolio.cash + upnl;

            // 权益 >= 维持保证金 → 健康，跳过
            if equity >= maintenance {
                continue;
            }

            // 破产价: equity = cash + qty × (bankrupt - avg_entry) × mult = 0
            let position_notional = qty_dec * multiplier;
            let bankrupt_price = if !position_notional.is_zero() {
                avg_entry - portfolio.cash / position_notional
            } else {
                mark
            };

            // 清算价（模拟滑点 + 保险基金折价）
            let liquidation_price = if qty_dec > Decimal::ZERO {
                mark.min(bankrupt_price) * Decimal::from_f64(0.95).unwrap_or(Decimal::ONE)
            } else {
                mark.max(bankrupt_price) * Decimal::from_f64(1.05).unwrap_or(Decimal::ONE)
            };

            let side = if qty_dec > Decimal::ZERO {
                OrderSide::Sell
            } else {
                OrderSide::Buy
            };
            let quantity = qty_dec.abs();
            let order_id = Uuid::new_v4().to_string();
            let trade_id = Uuid::new_v4().to_string();

            // 构造已成交订单（同 SettlementManager 做法）
            let mut filled_order = Order {
                id: order_id.clone(),
                symbol: symbol.clone(),
                side,
                order_type: OrderType::Market,
                quantity,
                price: Some(liquidation_price),
                time_in_force: TimeInForce::Day,
                trigger_price: None,
                trail_offset: None,
                trail_reference_price: None,
                fill_policy_override: None,
                slippage_type_override: None,
                slippage_value_override: None,
                commission_type_override: None,
                commission_value_override: None,
                graph_id: None,
                parent_order_id: None,
                order_role: OrderRole::Standalone,
                position_effect: PositionEffect::Close,
                status: OrderStatus::Filled,
                filled_quantity: quantity,
                average_filled_price: Some(liquidation_price),
                created_at: timestamp,
                updated_at: timestamp,
                commission: Decimal::ZERO,
                tag: "__forced_liquidation__".to_string(),
                reject_reason: String::new(),
                owner_strategy_id: None,
                allow_quantity_auto_resize: false,
                reduce_only: true,
            };

            let trade = Trade {
                id: trade_id,
                order_id,
                symbol: symbol.clone(),
                side,
                position_effect: PositionEffect::Close,
                quantity,
                price: liquidation_price,
                commission: Decimal::ZERO,
                timestamp,
                bar_index,
                owner_strategy_id: None,
                is_maker: false,
            };

            events.push(Event::ExecutionReport(filled_order, Some(trade)));
        }

        events
    }
}

impl Default for LiquidationManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::instrument::{CryptoInstrument, InstrumentEnum};
    use crate::model::AssetType;
    use rust_decimal_macros::dec;
    use std::collections::HashMap;
    use std::sync::Arc;

    fn btc_instrument() -> Instrument {
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

    fn make_bar(mark_price: f64) -> Bar {
        let mut extra = HashMap::new();
        extra.insert("mark_price".to_string(), mark_price);
        Bar {
            timestamp: 1_700_000_000_000_000_000,
            open: dec!(50000),
            high: dec!(50100),
            low: dec!(49900),
            close: dec!(50050),
            volume: dec!(100),
            symbol: "BTCUSDT".to_string(),
            extra,
        }
    }

    fn make_entry_trade() -> Trade {
        Trade {
            id: "entry".to_string(),
            order_id: "entry-order".to_string(),
            symbol: "BTCUSDT".to_string(),
            side: OrderSide::Buy,
            position_effect: PositionEffect::Open,
            quantity: dec!(1),
            price: dec!(50000),
            commission: Decimal::ZERO,
            timestamp: 0,
            bar_index: 0,
            owner_strategy_id: None,
            is_maker: false,
        }
    }

    #[test]
    fn test_mark_price_update() {
        let mut mgr = LiquidationManager::new();
        let bar = make_bar(48000.0);
        mgr.update_mark_price(&bar);
        assert_eq!(
            mgr.mark_prices.get("BTCUSDT").copied().unwrap(),
            Decimal::from(48000)
        );
    }

    #[test]
    fn test_no_position_no_liquidation() {
        let mgr = LiquidationManager::new();
        let portfolio = Portfolio {
            cash: dec!(100_000),
            positions: Arc::new(HashMap::new()),
            available_positions: Arc::new(HashMap::new()),
        };
        let instruments = HashMap::new();
        let tracker = TradeTracker::new();
        let events = mgr.check_liquidations(&portfolio, &instruments, &tracker, 0, 0);
        assert!(events.is_empty());
    }

    #[test]
    fn test_liquidation_emits_execution_report() {
        let mut mgr = LiquidationManager::new();
        mgr.update_mark_price(&make_bar(30000.0)); // price dropped from ~50000

        let mut positions = HashMap::new();
        positions.insert("BTCUSDT".to_string(), dec!(1)); // 1 BTC long
        let portfolio = Portfolio {
            cash: dec!(0),
            positions: Arc::new(positions),
            available_positions: Arc::new(HashMap::new()),
        };
        let mut instruments = HashMap::new();
        instruments.insert("BTCUSDT".to_string(), btc_instrument());

        let mut tracker = TradeTracker::new();
        tracker.process_trade(&make_entry_trade(), dec!(1), None, None, dec!(100_000));

        let events = mgr.check_liquidations(&portfolio, &instruments, &tracker, 1000, 1);
        assert_eq!(events.len(), 1);

        if let Event::ExecutionReport(order, Some(trade)) = &events[0] {
            assert_eq!(order.side, OrderSide::Sell);
            assert_eq!(order.quantity, dec!(1));
            assert_eq!(order.position_effect, PositionEffect::Close);
            assert_eq!(order.status, OrderStatus::Filled);
            assert!(order.reduce_only);
            assert_eq!(trade.position_effect, PositionEffect::Close);
            assert!(!trade.is_maker);
        } else {
            panic!("Expected ExecutionReport with trade");
        }
    }

    #[test]
    fn test_healthy_position_no_liquidation() {
        let mut mgr = LiquidationManager::new();
        mgr.update_mark_price(&make_bar(51000.0)); // price up

        let mut positions = HashMap::new();
        positions.insert("BTCUSDT".to_string(), dec!(1));
        let portfolio = Portfolio {
            cash: dec!(50_000),
            positions: Arc::new(positions),
            available_positions: Arc::new(HashMap::new()),
        };
        let mut instruments = HashMap::new();
        instruments.insert("BTCUSDT".to_string(), btc_instrument());

        let mut tracker = TradeTracker::new();
        tracker.process_trade(&make_entry_trade(), dec!(1), None, None, dec!(100_000));

        let events = mgr.check_liquidations(&portfolio, &instruments, &tracker, 1000, 1);
        assert!(events.is_empty());
    }
}
