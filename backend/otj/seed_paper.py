"""Give the fake accounts (otj/accounts.py) a paper-trading history: starting balance, orders, closed trades and a few
open positions, all produced by replaying the loaded dataset with the same code the API uses.

Edit the SETTINGS block below, then run it where the database and ./storage are reachable (see otj/seed_users.py):

  docker compose exec api alembic upgrade head      # once: creates the paper_* tables (migration 0005)
  docker compose run --rm -e PYTHONPATH=/app -v "$PWD/otj:/app/otj" api python otj/seed_paper.py

It RESETS each listed user's paper account first, so run it again to start the fake history over. Needs the users
(otj/seed_users.py) and a NIFTY and a BANKNIFTY dataset with options (otj/make_fake_data.py + otj/load_csv_to_db.py).
"""

import random
import sys

import pandas as pd
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_session
from app.core.models import PaperPosition, PaperTrade, User
from app.data.models import Dataset
from app.paper import service
from app.paper.prices import get_book
from otj.accounts import OWNER_EMAIL

# ----------------------------------------------------------------------------- SETTINGS
PLAN = {  # email -> (underlying to trade, starting balance in rupees, lots per trade, trades to simulate)
    OWNER_EMAIL: ("NIFTY", 500_000, 1, 14),
    "amit@example.com": ("NIFTY", 100_000, 1, 10),
    "priya@example.com": ("BANKNIFTY", 300_000, 1, 14),
    "rahul@example.com": ("NIFTY", 500_000, 2, 16),
    "sneha@example.com": ("BANKNIFTY", 150_000, 1, 8),
}
STOP_PCT, TARGET_PCT, SQUARE_OFF = 20.0, 40.0, "15:15"
SEED = 7
# -----------------------------------------------------------------------------


def main() -> int:
    settings = get_settings()
    book = get_book(settings.storage_dir)
    db = get_session()
    try:
        for email, (underlying, balance, lots, rounds) in PLAN.items():
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                print(f"skip {email}: no such user (run otj/seed_users.py first)")
                continue
            ds = db.scalars(
                select(Dataset)
                .where(Dataset.underlying == underlying, Dataset.options_rows > 0, Dataset.underlying_rows > 0)
                .order_by(Dataset.created_at.desc())
            ).first()
            if ds is None:
                print(f"skip {email}: no {underlying} dataset with options")
                continue

            rng = random.Random(f"{SEED}:{email}")
            acct = service.reset_account(db, service.get_account(db, user.id), float(balance))
            service.start_clock(db, book, acct, ds.id, at=pd.Timestamp(book.timeline(ds.id).iloc[0]).to_pydatetime())
            placed = 0
            for i in range(rounds):
                if acct.clock_time is None:
                    break
                clock = acct.clock_time
                expiries = [e for e in book.listed_expiries(ds.id, clock) if e > clock.date()]
                chain = book.chain_at(ds.id, expiries[0], clock) if expiries else None
                spot = book.spot_at(ds.id, clock)
                if chain is None or chain.empty or spot is None:
                    break
                option_type = rng.choice(["CE", "PE"])
                side = chain[chain["option_type"] == option_type].reset_index(drop=True)
                atm = int((side["strike"] - spot).abs().to_numpy().argmin())
                strike = float(side["strike"].iloc[min(max(atm + rng.choice([-1, 0, 0, 1]), 0), len(side) - 1)])
                try:
                    service.buy(
                        db, book, acct, expiry=expiries[0], strike=strike, option_type=option_type, lots=lots,
                        stop_pct=STOP_PCT, target_pct=TARGET_PCT, square_off=SQUARE_OFF, source="manual",
                    )  # fmt: skip
                    placed += 1
                except service.PaperError as e:
                    print(f"  {email}: order skipped ({e})")
                last_round = i == rounds - 1
                _, at_end = service.advance(db, book, acct, 4 if last_round else rng.randint(25, 80))
                if at_end:
                    break
                if not last_round and rng.random() < 0.3:  # sometimes exit by hand before a rule does
                    for pos in db.scalars(select(PaperPosition).where(PaperPosition.account_id == acct.id)):
                        service.sell(db, book, acct, pos.id)
                        break

            s = service.summary(db, book, acct)
            trades = list(db.scalars(select(PaperTrade).where(PaperTrade.account_id == acct.id)))
            wins = sum(1 for t in trades if t.net_pnl > 0)
            reasons: dict[str, int] = {}
            for t in trades:
                reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
            print(
                f"{email:28} {underlying:9} orders={placed:2d} closed={len(trades):2d} wins={wins:2d} "
                f"realized=Rs {s['realized_pnl']:>10,.2f} open={s['open_positions']} equity=Rs {s['equity']:>11,.2f} "
                f"clock={s['clock_time']:%d %b %H:%M} exits={reasons}"
            )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
