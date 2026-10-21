# Volatility and volume indicators: Bollinger Bands, ATR, VWAP

*Educational material, not financial advice.*

## Bollinger Bands (`bollinger`)
A moving average with bands at a number of standard deviations. Params: `period` (default 20) and `std` (default 2). Outputs: `mid` (SMA), `upper`, `lower`. The standard deviation here is the population standard deviation.

**Reading it**
- Bands widen when volatility rises and narrow when it falls. A narrow squeeze often precedes a larger move, but not the direction.
- **Mean reversion:** price touching the lower band in a range can bounce toward `mid`.
- **Breakout:** a close beyond the upper band during a strong trend can signal continuation ("riding the band").
Touching a band is not a signal by itself. Whether it reverts or continues depends on the regime.

## Average True Range (`atr`)
Average of the true range, where true range is the largest of high minus low, |high minus previous close|, and |low minus previous close|. It measures typical candle size including gaps. Default `period` is 14, smoothed with Wilder's method.
ATR does not give direction. Common uses: scaling stops or targets to volatility, comparing volatility across regimes, and the SuperTrend calculation. Remember that ATR is in underlying points, while stops in this system are percentages of option premium.

## VWAP (`vwap`)
Volume-weighted average price for the session: cumulative (typical price x volume) divided by cumulative volume, where typical price = (high + low + close) / 3. It **resets each trading day**. If volume is zero it falls back to typical price.
- Price above VWAP indicates intraday buyers are in control, and below indicates sellers.
- Institutions use it as a benchmark, so price often reacts around it.
- It is most meaningful on intraday data and early in the session it is very close to price.

## Notes
- Volume on index data (spot or futures) may not reflect true traded volume. Check your data source before relying on volume-based indicators.
- All indicators in this engine use only data up to the current candle. A signal on the close of candle t is acted on at the open of candle t+1.
