# Backtesting pitfalls

*Educational material, not financial advice.*

## Lookahead bias
Using information that was not available at decision time. This engine evaluates signals on the **candle close** and fills at the **next candle's open**, and every indicator only uses past and current candles. Be wary of any result that looks too good: the first suspect is lookahead.

## Overfitting (curve fitting)
Tuning parameters until the past looks great, which captures noise instead of an edge. Warning signs: many parameters, a single very specific best value, results that collapse when parameters shift slightly, or when you move to a different period. Prefer simple rules, test on data not used for tuning, and look for parameter plateaus.

## Too few trades
Ten or twenty trades prove very little. Win rate, Sharpe ratio and profit factor have wide uncertainty on small samples. Aim for enough trades across different market conditions before drawing conclusions.

## Costs and slippage
Brokerage, taxes and slippage compound quickly for frequent traders and for cheap options. Rerun with higher slippage and look at `net` versus `gross` results. A strategy that only works with zero costs does not work.

## Intrabar ambiguity
With candle data you cannot know the order of high and low within a candle. This engine assumes the stop is hit before the target when both are reachable in one candle. Real results can differ, so treat results on coarse timeframes with extra caution.

## Liquidity and fills
Backtests fill at the candle open (plus slippage) every time. Real fills can be worse, especially for far OTM strikes, near expiry, at the open, or during fast moves. Missing option candles are skipped, but real markets may also have no usable quote.

## Regime dependence
A trend strategy tested only in a trending period will look brilliant and then fail in a range. Test across trending, ranging, high-volatility and low-volatility periods.

## Data quality
Gaps, duplicate candles, bad timestamps and stale option prices distort results. Check the dataset quality report before trusting a run.

## Synthetic data warning
The built-in synthetic dataset is a random walk with model-based option prices. It is built for testing the software, not for finding edges. Any "profitable" result on it is noise, because there is no real market structure to exploit.

## Metrics to read together
Total P&L alone is not enough. Look at number of trades, win rate with average win and loss, profit factor, expectancy per trade, maximum drawdown, and how P&L is distributed across days. Beware of a result driven by one or two outlier trades.
