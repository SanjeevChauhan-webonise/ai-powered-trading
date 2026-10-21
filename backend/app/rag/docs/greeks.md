# Option Greeks

*Educational material, not financial advice.*

Greeks measure how an option's price responds to changes in its inputs. The backtest engine in this project uses the **market premiums in the data** and never computes Greeks. They are useful for reasoning about why a strategy behaves the way it does.

## Delta
The change in option price for a 1-point move in the underlying. Calls have delta between 0 and +1, puts between -1 and 0. ATM options have delta near 0.5 (calls) or -0.5 (puts). Deep ITM options move almost one-for-one with the underlying, while far OTM options barely react. Delta is also a rough market-implied probability of finishing ITM.

## Gamma
The rate of change of delta. Gamma is highest for ATM options close to expiry. High gamma means delta shifts quickly, so profits and losses can accelerate. Near expiry, a small underlying move can turn a cheap OTM option into a large winner or leave an ATM option worthless within minutes.

## Theta
The daily loss of option value from time passing, all else equal. It hurts buyers and benefits sellers. Theta is largest for ATM options and accelerates into expiry. A buyer needs the underlying to move enough, soon enough, to outrun theta.

## Vega
The change in option price for a 1-percentage-point change in implied volatility (IV). It is largest for ATM, longer-dated options. Buyers benefit from rising IV and are hurt by falling IV. **IV crush** after events (results, policy announcements) can make an option lose value even when the underlying moves in the expected direction.

## Rho
Sensitivity to interest rates. It is small for short-dated index options and is usually ignored in intraday work.

## Practical implications for strategy design
- Buying near-expiry ATM options: high gamma, very high theta. Wins are fast and losses are fast. Use tight stops and short holding periods.
- Buying options in low-IV, trending markets is generally more favourable than in high-IV, range-bound markets.
- Selling options collects theta but accepts tail risk. Always use a stop loss and size positions conservatively.
- The same entry signal can behave very differently on weekly versus monthly expiries because gamma and theta differ.
