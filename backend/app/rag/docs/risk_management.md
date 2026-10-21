# Risk management

*Educational material, not financial advice.*

## Why it matters
A positive-expectancy idea can still fail through oversized positions, no stop, or a few bad days. Options add leverage and time decay, so discipline matters even more.

## Stop loss (`risk.stop_loss_pct`)
Exit when the premium falls by a percentage from the entry price (for sold options, when it rises). In backtests the stop is checked on every candle using the candle low (or high for sold options). If the candle opens beyond the stop (a gap), the exit fills at the open, which is worse than the stop price.

## Target (`risk.target_pct`)
Exit when the premium reaches a profit percentage. If a single candle could have hit both the stop and the target, the engine assumes the **stop was hit first**, which is the conservative assumption because intrabar order is unknown.

## Trailing stop (`risk.trailing_sl_pct`)
Follows the best premium since entry (measured on candle closes) and exits if price retreats by the given percentage. It locks in profits on runners but can exit early in choppy moves.

## Risk-reward and break-even win rate
If you risk R to make T, the break-even win rate is R / (R + T) before costs. A 20% stop with a 40% target needs about 33% winners. A 20% stop with a 20% target needs about 50%. Costs push the required win rate higher. Check win rate together with average win, average loss, and profit factor.

## Position sizing (`lots`)
Size so that a stopped-out trade loses a small fraction of capital (commonly 0.5% to 2%). Quantity = lots x lot size. Never size from the potential profit. Size from the loss you can accept.

## Frequency and time controls
- `max_trades_per_day` limits overtrading and bad-day damage.
- `entry_start` / `entry_end` avoid the noisy open and the final minutes.
- `square_off` forces an intraday exit so no position is carried overnight. Gap risk is the biggest hidden risk of holding options.

## Drawdown
Maximum drawdown is the largest peak-to-trough fall of equity. Judge a strategy by whether you could tolerate its drawdown, not only by its total profit. A deep drawdown relative to total profit is a warning sign.

## Costs
Brokerage, taxes and slippage are paid on every order. Strategies with many small trades are the most cost-sensitive. Always compare results with and without costs, and test with higher slippage than you expect.

## Red flags in results
- Very few trades (results are statistical noise).
- Profits concentrated in one or two trades or days.
- Results that vanish with slightly higher slippage.
- Performance that depends on a very specific parameter value.
