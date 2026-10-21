# Strategy template: EMA Crossover

*Educational material, not financial advice.*

## Idea
A trend-following strategy. When a short-term EMA crosses above a longer-term EMA, short-term momentum has turned up relative to the trend: buy a **CE**. When it crosses below, momentum has turned down: buy a **PE**.

## Built-in template (`ema_crossover`)
- Indicators: `ema_fast` (period 9) and `ema_slow` (period 21).
- Timeframe: resampled to 5-minute candles.
- Bullish entry: `ema_fast crosses_above ema_slow` (buy ATM CE on the next candle's open).
- Bearish entry: `ema_fast crosses_below ema_slow` (buy ATM PE).
- `exit_on_opposite_signal: true`: an opposite crossover exits the position and reverses.
- Risk: stop loss 20%, target 40% of the entry premium, plus the default entry window and square-off time.

## When it tends to work
Sustained directional days where the underlying trends away from the open and pullbacks are shallow.

## When it tends to fail
- **Range-bound or choppy markets:** repeated crossovers in both directions cause a string of small losses (whipsaws), each paying brokerage and slippage.
- **Event days and fast reversals:** the lag of the EMAs means entries come after much of the move.
- **Near expiry:** time decay can erase a correct but slow move.

## Parameters to explore
- Faster pairs (for example 5 and 13) give earlier but noisier signals. Slower pairs (for example 20 and 50) give fewer, later signals.
- Timeframe: 1-minute crossovers are very noisy. 5 and 15 minutes are more common.
- Add a filter (for example a higher-timeframe trend, or VWAP side) to cut whipsaws, and check that the trade count remains meaningful.
- Stop and target percentages interact with strike and expiry choice. Cheap OTM weeklies stop out on tiny moves.

## What to check in results
Number of trades, profit factor, maximum drawdown, share of profit from the best few trades, and sensitivity to slippage. Avoid tuning the EMA periods until the past looks perfect (see backtesting pitfalls).
