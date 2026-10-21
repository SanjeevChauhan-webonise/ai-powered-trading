# Momentum indicators: RSI and MACD

*Educational material, not financial advice.*

## Relative Strength Index (`rsi`)
Measures the speed of recent gains versus losses on a 0 to 100 scale. Default `period` is 14.
Calculation (Wilder): average gain and average loss over the first `period` changes, then smoothed with avg = (previous avg x (period - 1) + current) / period. RSI = 100 - 100 / (1 + avg gain / avg loss).

**Reading it**
- Above 70 is often called overbought and below 30 oversold. In strong trends RSI can stay in these zones for a long time, so these levels are not automatic reversal signals.
- **Reversal approach:** enter long when RSI crosses back above 30, and short when it crosses back below 70, which waits for momentum to turn rather than trading the extreme itself. See the RSI Reversal strategy doc.
- **Trend approach:** RSI staying above 50 in an uptrend (or below 50 in a downtrend) is used as a trend filter.

**Weaknesses:** mean-reversion rules lose when a strong trend keeps going. Intraday RSI on 1 to 5 minute candles is noisy.

## MACD (`macd`)
Outputs: `macd` (fast EMA minus slow EMA), `signal` (an EMA of the macd line) and `hist` (macd minus signal). Defaults: fast 12, slow 26, signal 9.

**Reading it**
- `macd` crossing above `signal` is a bullish momentum signal, and crossing below is bearish.
- `macd` above zero means the fast average is above the slow one (uptrend bias).
- A shrinking histogram suggests momentum is fading before a crossover happens.

**Weaknesses:** it is built from lagging averages, so signals arrive late and whipsaw in ranges.

## Combining indicators
Combine a trend filter with a momentum trigger (for example, only take RSI long signals while close is above a slower EMA) using `all` / `any` groups in the rules. More conditions mean fewer trades, so check that the trade count stays large enough to be meaningful.
