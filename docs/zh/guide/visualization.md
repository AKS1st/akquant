# 可视化与报告

以下是 AKQuant 生成的交互式回测报告示例。您可以在此页面直接与图表进行交互，查看详细的回测数据。

<iframe src="../../assets/reports/akquant_report.html" width="100%" height="1000px" frameborder="0" style="border: 1px solid #eee; border-radius: 4px;"></iframe>

## 基准对比

`BacktestResult.report` 支持直接传入基准收益率序列：

```python
benchmark_returns = (
    benchmark_df.set_index("date")["close"].pct_change().fillna(0.0)
)
result.report(
    filename="akquant_report.html",
    benchmark=benchmark_returns,
    show=False,
)
```

报告会新增“基准对比 (Benchmark Comparison)”区块，提供累计超额收益、年化超额收益、跟踪误差、信息比率、Beta、Alpha 等指标，并展示策略/基准/超额三条累计收益曲线。
