use chrono::{TimeZone, Utc};
use serde::Serialize;

const RUST_CONTEXT_MARKER: &str = " [akq_ctx=";

#[derive(Default, Serialize)]
pub struct AkqLogContext {
    #[serde(skip_serializing_if = "Option::is_none")]
    phase: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    event_time_str: Option<String>,
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
    pub fn event_time_str(mut self, value: impl Into<String>) -> Self {
        self.event_time_str = Some(value.into());
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
        .format("%Y-%m-%d %H:%M:%S")
        .to_string()
}
