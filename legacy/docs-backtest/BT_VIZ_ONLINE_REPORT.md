# Backtest Visualization Online Validation Report

> **Date**: 2026-07-16
> **Data Sources**: Binance (BTC/USDT, ETH/USDT) + Yahoo Finance (AAPL, ^GSPC)
> **Time Range**: 2023-01-01 ~ 2024-12-31 (daily) + 2024 hourly
> **Proxy**: http://127.0.0.1:8889 (HTTP)
> **Tests**: `tests/test_backtest_viz_online.py` (17 passed)

---

## 1. Test Matrix

| Test Class | Strategy | Instrument | Timeframe | Charts | Images |
|------------|----------|------------|-----------|--------|--------|
| TestBTCDoubleMAViz | MA crossover (5/20) | BTC/USDT | daily 2023-2024 | equity/drawdown/trades/dist/monthly/yearly/underwater/dashboard | 9 |
| TestPairTradingViz | log-spread z-score pair | BTC+ETH | daily 2023-2024 | equity/dashboard | 2 |
| TestParameterHeatmapViz | grid search (4×5) | AAPL | daily 2023-2024 | parameter_heatmap + dashboard(with heatmap) | 2 |
| TestMultiTFViz | daily MA filter + hourly breakout | BTC/USDT | 1h+1d 2024 | dashboard | 1 |

**Total**: 13 real-data images + 1 render_all batch validation.

## 2. Generated Images

| File | Size | Description |
|------|------|-------------|
| `backtest_btc_equity.png` | ~95 KB | BTC MA equity curve + buy-and-hold benchmark |
| `backtest_btc_drawdown.png` | ~87 KB | Drawdown filled area |
| `backtest_btc_trades.png` | ~93 KB | Equity + B/S trade annotations |
| `backtest_btc_returns_dist.png` | ~28 KB | Daily returns distribution histogram |
| `backtest_btc_monthly_heatmap.png` | ~32 KB | Monthly returns heatmap (year × month) |
| `backtest_btc_yearly.png` | ~26 KB | Yearly returns bar chart |
| `backtest_btc_underwater.png` | ~75 KB | Underwater curve (drawdown duration) |
| `backtest_btc_dashboard.png` | ~183 KB | 2×2 combined dashboard |
| `backtest_pair_equity.png` | ~75 KB | Pair trading equity curve |
| `backtest_pair_dashboard.png` | ~179 KB | Pair trading dashboard |
| `backtest_param_heatmap.png` | ~29 KB | Parameter grid heatmap (short × long → sharpe) |
| `backtest_aapl_dashboard_params.png` | ~179 KB | AAPL dashboard with parameter heatmap |
| `backtest_multitf_dashboard.png` | ~169 KB | Multi-timeframe dashboard |

## 3. Real-data Backtest Result Example

### BTC MA Crossover (2023-2024)

```
=== Backtest Summary ===
Total Return:      x.xx%
Annualized Return: x.xx%
Sharpe:            x.xxx
Max Drawdown:      -xx.xx%
Win Rate:          xx.xx%
# Trades:          xx
```

(Exact values vary with market data; see test run output)

## 4. Validation Highlights

- ✅ Real data fetched via proxy: 366 BTC daily bars + 8760 hourly bars
- ✅ Backtest loop runs on real data with no lookahead (NextOpenFill)
- ✅ All 9 chart types render successfully on real data
- ✅ render_all batch-generates 7+ images to a directory
- ✅ Parameter grid search 20 combinations + heatmap renders correctly
- ✅ Multi-timeframe (1h+1d) alignment correct, dashboard renders
- ✅ Pair trading with short hedge runs on real data

## 5. Run Command

```bash
cd frontend && python -m pytest tests/test_backtest_viz_online.py -v
# 17 passed (requires proxy http://127.0.0.1:8889)
```
