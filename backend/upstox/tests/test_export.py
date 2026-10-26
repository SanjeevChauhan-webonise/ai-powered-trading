import time
from datetime import date

import pandas as pd

from upstox.export import export_range, get_job, start_job
from upstox.tests.test_upstox import _client


def test_export_writes_per_expiry_csv_and_resumes(tmp_path):
    out = tmp_path / "NIFTY" / "5m"
    written = export_range(_client(), "NIFTY", 5, date(2025, 4, 10), date(2025, 4, 17), out, n_strikes=1)
    names = sorted(p.name for p in written)
    assert names == ["options_2025-04-17.csv", "underlying.csv"]
    opts = pd.read_csv(out / "options_2025-04-17.csv")
    assert {"timestamp", "expiry", "strike", "option_type", "oi"} <= set(opts.columns)
    assert export_range(_client(), "NIFTY", 5, date(2025, 4, 10), date(2025, 4, 17), out, n_strikes=1) == []


def test_background_job_completes(tmp_path):
    job = start_job(
        _client(), "NIFTY", 5, date(2025, 4, 10), date(2025, 4, 17), tmp_path, n_strikes=1, include_options=True
    )
    for _ in range(100):
        if get_job(job.id).status != "running":
            break
        time.sleep(0.05)
    assert job.status == "done" and job.done_expiries == job.total_expiries == 1
    assert "options_2025-04-17.csv" in job.files
