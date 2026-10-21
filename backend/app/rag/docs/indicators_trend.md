# Trend indicators: SMA, EMA, SuperTrend

*Educational material, not financial advice.*

## Simple moving average (`sma`)
The average of the last `period` closes. It is smooth and slow. Every price in the window has equal weight. Typical periods: 20, 50, 200.

## Exponential moving average (`ema`)
Weights recent prices more, using alpha = 2 / (period + 1) and the recurrence EMA(t) = alpha x close(t) + (1 - alpha) x EMA(t-1). It reacts faster than an SMA of the same period.
In this engine the EMA is seeded with the first close and values are reported once `period` candles exist. Different platforms seed differently, so early values can differ slightly from other charting tools, and the difference fades over time.

**Common uses**
- Price above a rising EMA suggests an uptrend, and below a falling EMA suggests a downtrend.
- **Crossovers:** a fast EMA crossing above a slow EMA is a bullish signal, and crossing below is bearish (for example 9 and 21). See the EMA Crossover strategy doc.

**Weaknesses**
Moving averages lag. In sideways markets they produce frequent false crossovers (whipsaws), each costing brokerage and slippage.

## SuperTrend (`supertrend`)
A trailing line built from the average true range (ATR). Params: `period` (default 10) and `multiplier` (default 3). Outputs:
- `value`: the line. It sits below price in an uptrend and above price in a downtrend.
- `direction`: +1 for an uptrend and -1 for a downtrend.

The trend flips when the close crosses the line. A larger multiplier gives fewer, later flips. A smaller multiplier gives more flips and more whipsaws.

**Uses:** trend-following entries when `direction` flips, or when close crosses the SuperTrend `value`. Also used as a trailing exit.
**Weaknesses:** like all trend-followers it loses in ranges and gives back profit before reversing.

## Choosing parameters
Faster settings give earlier signals and more false ones. Slower settings give fewer, later, more reliable signals. There is no universally best value, so test a range and prefer parameters where nearby values also work (a plateau) rather than a single sharp peak.
