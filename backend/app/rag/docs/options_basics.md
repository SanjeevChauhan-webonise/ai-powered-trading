# Options basics

*Educational material, not financial advice.*

## What an option is
An option is a contract giving the buyer the right, but not the obligation, to trade an underlying at a fixed price (the **strike**) on or before a fixed date (the **expiry**). A **call (CE)** gains value when the underlying rises. A **put (PE)** gains value when it falls. The price paid for the contract is the **premium**.

## Buyer vs seller
- **Buyer (long option):** pays the premium up front. The maximum loss is the premium paid. The profit is theoretically large for calls and bounded by the underlying going to zero for puts.
- **Seller (short option, "writer"):** receives the premium. The profit is capped at the premium received, while the loss can be very large (unlimited for short calls). Sellers need margin and are exposed to gap moves.

In this system `direction: buy` buys the option matching the signal (bullish signal buys CE, bearish buys PE). `direction: sell` sells the opposite side (bullish signal sells PE, bearish sells CE), which keeps the position directionally aligned with the signal.

## Moneyness
- **ATM (at the money):** strike is closest to the current underlying price.
- **ITM (in the money):** a call with strike below spot, or a put with strike above spot. It has intrinsic value.
- **OTM (out of the money):** a call with strike above spot, or a put with strike below spot. Its premium is all time value.

## Premium components
Premium = **intrinsic value** (how far ITM, never below zero) + **time value** (the price of remaining uncertainty). Time value depends on time to expiry, implied volatility, and how close the strike is to spot. Time value decays to zero at expiry (this is **theta decay**), and the decay speeds up in the last days.

## Index options specifics
- Index options (NIFTY, BANKNIFTY, FINNIFTY) are typically **cash settled** and **European style** (exercised only at expiry).
- Each contract trades in **lots**: quantity = lots x lot size. Lot sizes and weekly expiry weekdays have changed over time and differ by index, so always use the lot size of the data you are testing.
- Weekly and monthly expiries coexist. Near-expiry contracts are cheap but extremely sensitive to small underlying moves.

## Liquidity and spreads
Deep OTM and far-dated contracts can have wide bid-ask spreads and missing candles. Backtests that ignore this overstate results. Use slippage and brokerage assumptions that reflect real trading.
