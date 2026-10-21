"""Four FAKE trader personas for testing the Strategy Desk end to end, each logged in as its own account.

Edit the SETTINGS block below, then run (the backend must be up, e.g. docker compose up):

  PYTHONPATH=. uv run python otj/fake_users.py                 # default model from the backend .env
  MODEL=openai:gpt-4o-mini PYTHONPATH=. uv run python otj/fake_users.py
  MODEL=mock:demo PYTHONPATH=. uv run python otj/fake_users.py  # offline scripted model, costs nothing

For each persona it shows how the query was understood (POST /runs/parse), runs the pipeline (POST /runs) or answers the
question (POST /runs/ask), and prints the trade plan. Each persona logs in with its own account
(otj/accounts.py, created by otj/seed_users.py), so its runs show up only when you log in as that user. Needs a NIFTY and a BANKNIFTY dataset with options (see otj/make_fake_data.py and
otj/load_csv_to_db.py). A report is saved to option-data/fake/users_report.json.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

from otj.accounts import PASSWORD

# ----------------------------------------------------------------------------- SETTINGS
API_URL = os.environ.get("API_URL", "http://localhost:8000")
MODEL = os.environ.get("MODEL", "")  # "" = the backend's default model
REPORT = Path("option-data/fake/users_report.json")
RUN_TIMEOUT_SECONDS = 600
USERS = [
    {
        "name": "Amit", "email": "amit@example.com", "profile": "cautious beginner, small capital, wants simple rules",
        "query": "NIFTY nearest weekly expiry. Use EMA with RSI. Capital 50k, max loss 1500 per trade, target 3000. Keep it low risk.",
        "underlying": "NIFTY", "expiry": "weekly", "capital": 50_000, "max_loss": 1_500, "target_profit": 3_000, "risk": "low",
    },
    {
        "name": "Priya", "email": "priya@example.com", "profile": "intraday trend trader, bigger capital",
        "query": "BANKNIFTY monthly expiry. Supertrend with VWAP for a trend trade. Capital 2 lakh, max loss 5000, target 12000.",
        "underlying": "BANKNIFTY", "expiry": "monthly", "capital": 200_000, "max_loss": 5_000, "target_profit": 12_000, "risk": "medium",
    },
    {
        "name": "Rahul", "email": "rahul@example.com", "profile": "aggressive, lets the agents pick the indicators",
        "query": "NIFTY weekly. Capital 1 lakh, max loss 4000, target 7777. You choose the strategy from the market, I want a good one.",
        "underlying": "NIFTY", "expiry": "weekly", "capital": 100_000, "max_loss": 4_000, "target_profit": 7_777, "risk": "high",
    },
    {
        "name": "Sneha", "email": "sneha@example.com", "profile": "learner who asks questions instead of asking for a strategy",
        "query": "What is theta decay and why does it hurt option buyers near expiry?",
        "question": True,
    },
]  # fmt: skip
# -----------------------------------------------------------------------------


def nearest_expiry(api: httpx.Client, underlying: str, kind: str) -> str | None:
    """Nearest real weekly/monthly expiry from the backend (None if the lookup fails)."""
    try:
        rows = api.get("/expiries", params={"underlying": underlying, "count": 12}).json()["expiries"]
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    return next((r["date"] for r in rows if r["kind"] == kind and r["days_to_expiry"] >= 0), None)


def show(title: str, rows: list[str]) -> None:
    print(f"\n=== {title}")
    for r in rows:
        print(f"    {r}")


def run_user(api: httpx.Client, u: dict) -> dict:
    model = {"model": MODEL or None}
    if u.get("question"):
        a = api.post("/runs/ask", json={"query": u["query"], **model}).json()
        show(
            f"{u['name']} ({u['profile']})",
            [f"Q: {u['query']}", f"A: {a.get('answer', a)}"[:600], f"sources: {a.get('sources')}"],
        )
        return {"user": u["name"], "type": "question", "answer": a}

    parsed = api.post("/runs/parse", json={"query": u["query"], **model}).json()
    expiry = parsed.get("expiry") or nearest_expiry(api, u["underlying"], u["expiry"])
    body = {
        "underlying": u["underlying"], "expiry": expiry, "capital": u["capital"], "max_loss": u["max_loss"],
        "target_profit": u["target_profit"], "idea": f"{parsed.get('idea') or u['query']} Risk appetite: {u['risk']}.",
        **model,
    }  # fmt: skip
    r = api.post("/runs", json=body)
    if r.status_code != 202:
        show(f"{u['name']}", [f"could not start the run: {r.status_code} {r.text[:200]}"])
        return {"user": u["name"], "type": "strategy", "error": r.text}
    rid = r.json()["id"]
    deadline = time.time() + RUN_TIMEOUT_SECONDS
    run = api.get(f"/runs/{rid}").json()
    while run["status"] in ("queued", "running") and time.time() < deadline:
        time.sleep(3)
        run = api.get(f"/runs/{rid}").json()
    risk = next((s for s in run["steps"] if s["name"] == "risk"), {}).get("output") or {}
    p = risk.get("trade_plan")
    rows = [f"understood: {parsed.get('underlying')} expiry={parsed.get('expiry')} indicators={parsed.get('preferred_indicators')}",
            f"run {rid[:8]} status={run['status']} error={run.get('error')}"]  # fmt: skip
    if p:
        rows += [
            f"{p['strategy']} | expiry {p['expiry_date']} ({p['expiry_type']}) | CE: {p['bullish_signal_action']} PE: {p['bearish_signal_action']}",
            f"{p['lots']} lot x {p['quantity'] // p['lots'] if p['lots'] and p['quantity'] else '?'} = qty {p['quantity']} | stop {p['stop_loss_pct']}% target {p['target_pct']}%",
            f"est max loss Rs {p['max_loss_per_trade']} (limit {u['max_loss']}) | est target Rs {p['target_profit_per_trade']} (wanted {u['target_profit']})",
            f"verifier: {p['verification']['verdict']} | backtest: {p['backtest']}",
        ]
    show(f"{u['name']} ({u['profile']})", rows)
    return {"user": u["name"], "type": "strategy", "run_id": rid, "status": run["status"], "trade_plan": p}


def main() -> int:
    with httpx.Client(base_url=API_URL, timeout=30) as probe:
        try:
            probe.get("/health").raise_for_status()
        except httpx.HTTPError as e:
            sys.exit(f"backend not reachable at {API_URL}: {e}")
    results = []
    for u in USERS:  # each persona logs in with its own account, so its runs belong to it
        with httpx.Client(base_url=API_URL, timeout=180) as api:
            login = api.post("/auth/login", json={"email": u["email"], "password": PASSWORD})
            if login.status_code != 200:
                show(u["name"], [f"login failed ({login.status_code}); run otj/seed_users.py first"])
                results.append({"user": u["name"], "error": "login failed"})
                continue
            api.headers["Authorization"] = f"Bearer {login.json()['token']}"
            results.append({**run_user(api, u), "level": login.json()["user"]["level"]})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nreport saved to {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
