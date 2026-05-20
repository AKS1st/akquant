use crate::event::Event;
use crate::model::Order;
use chrono::{SecondsFormat, TimeZone, Utc};
use serde::Serialize;

const RUST_CONTEXT_MARKER: &str = " [akq_ctx=";

#[derive(Default, Serialize)]
pub struct AkqLogContext {
    #[serde(skip_serializing_if = "Option::is_none")]
    phase: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    event_time: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    event_time_iso: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    strategy_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    slot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    symbol: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    order_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    client_order_id: Option<String>,
}

impl AkqLogContext {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    #[must_use]
    pub fn phase(mut self, value: impl Into<String>) -> Self {
        self.phase = Some(value.into());
        self
    }

    #[must_use]
    pub fn event_time(mut self, value: i64) -> Self {
        self.event_time = Some(value);
        self
    }

    #[must_use]
    pub fn event_time_iso(mut self, value: impl Into<String>) -> Self {
        self.event_time_iso = Some(value.into());
        self
    }

    #[must_use]
    pub fn strategy_id(mut self, value: impl Into<String>) -> Self {
        self.strategy_id = Some(value.into());
        self
    }

    #[must_use]
    pub fn slot(mut self, value: impl Into<String>) -> Self {
        self.slot = Some(value.into());
        self
    }

    #[must_use]
    pub fn symbol(mut self, value: impl Into<String>) -> Self {
        self.symbol = Some(value.into());
        self
    }

    #[must_use]
    pub fn order_id(mut self, value: impl Into<String>) -> Self {
        self.order_id = Some(value.into());
        self
    }
}

#[must_use]
pub fn execution_order_context(order: &Order, event_time: i64) -> AkqLogContext {
    let mut context = AkqLogContext::new()
        .phase("execution")
        .symbol(order.symbol.clone())
        .order_id(order.id.clone())
        .event_time(event_time)
        .event_time_iso(format_event_time_nanos(event_time));
    if let Some(strategy_id) = order
        .owner_strategy_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        context = context
            .strategy_id(strategy_id.to_string())
            .slot(strategy_id.to_string());
    }
    context
}

#[must_use]
pub fn event_time_from_event(event: &Event) -> Option<i64> {
    match event {
        Event::Bar(bar) => Some(bar.timestamp),
        Event::Tick(tick) => Some(tick.timestamp),
        Event::Timer(timer) => Some(timer.timestamp),
        _ => None,
    }
}

#[must_use]
pub fn execution_order_context_from_event(order: &Order, event: &Event) -> AkqLogContext {
    event_time_from_event(event)
        .map(|event_time| execution_order_context(order, event_time))
        .unwrap_or_else(|| {
            let mut context = AkqLogContext::new()
                .phase("execution")
                .symbol(order.symbol.clone())
                .order_id(order.id.clone());
            if let Some(strategy_id) = order
                .owner_strategy_id
                .as_deref()
                .map(str::trim)
                .filter(|value| !value.is_empty())
            {
                context = context
                    .strategy_id(strategy_id.to_string())
                    .slot(strategy_id.to_string());
            }
            context
        })
}

#[must_use]
pub fn render_log_message(message: impl Into<String>, context: AkqLogContext) -> String {
    let message = message.into();
    let Ok(payload) = serde_json::to_string(&context) else {
        return message;
    };
    if payload == "{}" {
        return message;
    }
    format!("{message}{RUST_CONTEXT_MARKER}{payload}]")
}

#[must_use]
pub fn format_event_time_nanos(timestamp_ns: i64) -> String {
    Utc.timestamp_nanos(timestamp_ns)
        .to_rfc3339_opts(SecondsFormat::AutoSi, true)
}
