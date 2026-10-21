"""Start a multi-agent run and print its SSE progress.

  PYTHONPATH=. uv run python scripts/smoke_run.py --idea "buy CE when 9 EMA crosses above 21 EMA"
  PYTHONPATH=. uv run python scripts/smoke_run.py --idea "..." --model anthropic:claude-sonnet-5-5
  PYTHONPATH=. uv run python scripts/smoke_run.py --template rsi_reversal --model mock:demo

Needs the API running (docker compose up) and a configured provider (or ENABLE_MOCK_LLM=true for mock:demo).
Uses the newest dataset, or generates a synthetic one if there is none.
"""

import argparse
import json
import sys

import httpx


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--dataset-id")
    p.add_argument("--idea")
    p.add_argument("--template")
    p.add_argument("--model")
    a = p.parse_args()
    if not (a.idea or a.template):
        p.error("give --idea and/or --template")

    with httpx.Client(base_url=a.api, timeout=None) as c:
        dataset_id = a.dataset_id
        if not dataset_id:
            datasets = c.get("/datasets").json()
            dataset_id = datasets[0]["id"] if datasets else c.post("/datasets/synthetic", json={}).json()["id"]
        body = {"dataset_id": dataset_id, "idea": a.idea, "template_id": a.template, "model": a.model}
        r = c.post("/runs", json={k: v for k, v in body.items() if v})
        if r.status_code != 202:
            print(f"HTTP {r.status_code}: {r.text}")
            return 1
        run_id = r.json()["id"]
        print(f"run {run_id}")
        with c.stream("GET", f"/runs/{run_id}/stream") as stream:
            event = ""
            for line in stream.iter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    d = json.loads(line[6:])
                    if event == "step":
                        extra = d.get("error") or (d.get("usage") and f"usage={d['usage']}") or ""
                        print(f"  step {d['name']:9s} {d['status']:9s} {d.get('model') or '':32s} {extra}")
                    else:
                        bt, err = d.get("backtest_run_id"), d.get("error")
                        print(f"{event}: status={d['status']} backtest_run_id={bt} error={err}")
        run = c.get(f"/runs/{run_id}").json()
        if run["status"] == "completed":
            risk = run["steps"][3]["output"]["review"]
            print("\nRisk summary:", risk["summary"])
            print("Red flags:", [f"{f['severity']}: {f['title']}" for f in risk["red_flags"]])
            print(f"Open results: /results/{run['backtest_run_id']} in the frontend")
        return 0 if run["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
