# Chapter 15: Live Trading Systems and Operations

This chapter is currently maintained in Chinese first.

- Chinese chapter: [第 15 章：实盘交易系统与运维](../../zh/textbook/15_live_trading.md)
- Textbook home: [Chinese textbook index](../../zh/textbook/index.md)
- Live execution semantics note:
  - CTP supports `execution_semantics_mode` with `strict` (default) and `compatible`.
  - In `strict`, terminal order states are confirmed by `OnRtnOrder` callbacks.
- Practice links:
  - Primary example: [examples/textbook/ch15_live_trading.py](https://github.com/akfamily/akquant/blob/main/examples/textbook/ch15_live_trading.py)
  - Extended example: [examples/textbook/ch15_strategy_loader.py](https://github.com/akfamily/akquant/blob/main/examples/textbook/ch15_strategy_loader.py)
  - Supplementary example: [examples/44_strategy_source_loader_demo.py](https://github.com/akfamily/akquant/blob/main/examples/44_strategy_source_loader_demo.py)
  - Guide: [Live Functional Quickstart Guide](../advanced/live_functional_quickstart.md)

## Operational Logging Note

Before live or paper troubleshooting, explicitly configure logging instead of relying on defaults:

```python
import akquant

akquant.configure_logging(
    akquant.LogConfig(
        profile="live",
        level="INFO",
        console=True,
        filename="logs/live.log",
        file_level="DEBUG",
        file_json=True,
        file_max_bytes=50_000_000,
        file_backup_count=5,
    )
)
```

This keeps strategy-side `on_order` / `on_trade` logs and gateway/execution warnings in the same pipeline. It is especially useful when tracing rejects, unknown cancel requests, session-close expiry, or strict-semantics cases where terminal state is not confirmed until broker callbacks arrive.
