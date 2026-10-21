# Strike and expiry selection

*Educational material, not financial advice.*

Choosing which contract to trade often matters as much as the entry signal. The strategy spec controls this under `instrument`.

## Strike selection (`instrument.strike`)
- **`atm`:** the strike closest to the underlying price at the fill candle's open. It has the highest sensitivity to direction per unit of premium and also the highest theta. This is the default and the most liquid choice.
- **`offset` (ATM +/- N strikes):** `offset: 2` is two strikes above ATM, `offset: -1` is one strike below. The offset is in raw strikes for both CE and PE, so +N is a higher strike. For a call, +N is OTM. For a put, +N is ITM.
  - OTM options are cheaper and have lower probability but bigger percentage payoffs. Their stop-loss percentages trigger on small absolute moves.
  - ITM options behave more like the underlying (higher delta), cost more, and have less time value to lose.
- **`nearest_premium`:** pick the strike whose open price at the fill candle is closest to a target premium. This keeps capital at risk per trade roughly constant regardless of how volatile the market is.

If the requested strike falls outside the strikes present in the data, the entry is skipped and logged.

## Expiry selection (`instrument.expiry`)
- **`nearest_weekly`:** the first available expiry on or after the trade date. On expiry day itself this is the same-day contract.
- **`monthly`:** the last available expiry of the month (the first such date on or after the trade date).

## Trade-offs
- **Nearest weekly** gives the cheapest premiums and the highest gamma, so big percentage moves are possible but time decay is brutal. On the expiry day, spreads can be wide and premiums can collapse to near zero.
- **Monthly** costs more but decays more slowly and reacts less violently. It is usually better for strategies that need time to be right.
- Avoid assuming a contract is liquid just because it exists in the data. Missing candles are skipped by the engine and reported as events.

## Interaction with risk rules
A percentage stop loss on a cheap OTM weekly option is hit by tiny moves. A wider percentage or a different strike might be needed. Compare different strike and expiry choices on the same data and date range rather than judging a signal on one contract choice.
