"""Create the fake accounts (otj/accounts.py) and give existing, unowned data to their owners.

Edit the SETTINGS block below, then run it where the database is reachable. With docker compose (otj/ is not mounted
into the container by default, so mount it for the run):

  docker compose run --rm -e PYTHONPATH=/app -v "$PWD/otj:/app/otj" api python otj/seed_users.py

Safe to run again: existing users are kept as they are (their password is NOT reset). Runs from before accounts
existed have no owner; the ones whose idea starts with "[Amit]" etc. go to that persona, and everything else
(strategies, backtests, runs) goes to ADOPT_UNOWNED_TO.
"""

import re
import sys
import uuid

from sqlalchemy import select, update

from app.core.db import get_session
from app.core.models import BacktestRun, PipelineRun, Strategy, User
from app.core.security import hash_password
from otj.accounts import ACCOUNTS, OWNER_EMAIL, PASSWORD

# ----------------------------------------------------------------------------- SETTINGS
ADOPT_UNOWNED_TO = OWNER_EMAIL  # the owner account (OWNER_EMAIL); None = leave unowned data alone
# -----------------------------------------------------------------------------


def main() -> int:
    session = get_session()
    try:
        users: dict[str, User] = {}
        for a in ACCOUNTS:
            user = session.scalar(select(User).where(User.email == a["email"]))
            if user is None:
                user = User(
                    id=uuid.uuid4().hex, email=a["email"], name=a["name"], level=a["level"],
                    password_hash=hash_password(PASSWORD),
                )  # fmt: skip
                session.add(user)
                print(f"created  {a['email']:30} {a['level']:9} {a['name']}")
            else:
                print(f"exists   {a['email']:30} {user.level:9} {user.name}")
            users[a["email"]] = user
        session.commit()

        by_first_name = {a["name"].split()[0].lower(): users[a["email"]].id for a in ACCOUNTS}
        tagged = 0
        for run in session.scalars(select(PipelineRun).where(PipelineRun.user_id.is_(None))):
            m = re.match(r"\[(\w+)\]", str((run.request or {}).get("idea") or ""))
            owner = by_first_name.get(m.group(1).lower()) if m else None
            if owner:
                run.user_id = owner
                tagged += 1
                if run.backtest_run_id:
                    session.execute(
                        update(BacktestRun).where(BacktestRun.id == run.backtest_run_id).values(user_id=owner)
                    )
        session.commit()
        print(f"\nassigned {tagged} tagged run(s) to their persona")

        if ADOPT_UNOWNED_TO:
            owner = users.get(ADOPT_UNOWNED_TO) or session.scalar(select(User).where(User.email == ADOPT_UNOWNED_TO))
            if owner is None:
                sys.exit(f"ADOPT_UNOWNED_TO={ADOPT_UNOWNED_TO} is not an account")
            for model in (Strategy, BacktestRun, PipelineRun):
                n = session.execute(update(model).where(model.user_id.is_(None)).values(user_id=owner.id)).rowcount
                print(f"assigned {n} unowned {model.__tablename__} row(s) to {owner.email}")
            session.commit()
        print(f"\nlogin with any of the emails above and the password: {PASSWORD}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
