# Strategy template: RSI Reversal

*Educational material, not financial advice.*

## Idea
A mean-reversion strategy. After the market has been pushed to an extreme, wait for momentum to turn back: when RSI crosses **back above 30** (leaving oversold), buy a **CE**. When RSI crosses **back below 70** (leaving overbought), buy a **PE**. Waiting for the cross back avoids trying to catch a falling knife the moment RSI first touches an extreme.

## Built-in template (`rsi_reversal`)
- Indicator: `rsi` (period 14).
- Timeframe: resampled to 5-minute candles.
- Bullish entry: `rsi crosses_above 30` (buy ATM CE on the next candle's open).
- Bearish entry: `rsi crosses_below 70` (buy ATM PE).
- `exit_on_opposite_signal: true`.
- Risk: stop loss 20%, target 40% of the entry premium, plus the default entry window and square-off time.

## When it tends to work
Range-bound sessions where the underlying oscillates and extremes tend to revert.

## When it tends to fail
- **Strong trends:** RSI can stay overbought or oversold for a long time, and a cross back may be only a brief pause before the trend resumes.
- **Trend days at the open:** early extremes are common and often continue.
- RSI is noisy on very short timeframes, so signals can cluster.

## Parameters to explore
- Thresholds: 20/80 gives fewer, more extreme signals. 40/60 gives many more, weaker signals.
- Period: shorter periods (7) react faster and swing more. Longer ones (21) are smoother.
- Add a trend filter so you only take reversals in the direction of the larger trend, for example long reversals only when close is above a slow EMA.
- Combine with the strike and expiry choice: a reversal that needs time is better served by a further expiry.

## What to check in results
Win rate together with average win and loss (mean-reversion strategies often have a high win rate and occasional large losses), profit factor, maximum drawdown, and how results change in trending versus ranging periods. See the backtesting pitfalls doc for overfitting and sample-size warnings.
