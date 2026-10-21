import pandas as pd
import pytest

from app.data.synthetic import SyntheticConfig, generate
from app.engine.backtest import run_backtest
from app.engine.templates import TEMPLATES


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.DataFrame]:
    return generate(SyntheticConfig(trading_days=6, n_strikes=4))


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_templates_run_on_synthetic_data(name: str, data: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    under, opts = data
    res = run_backtest(TEMPLATES[name], under, opts, lot_size=75)
    assert res.metrics.num_trades == len(res.trades)
    assert res.metrics.total_pnl == pytest.approx(sum(t.net_pnl for t in res.trades), abs=0.05)
    for t in res.trades:
        assert t.entry_time < t.exit_time or t.exit_reason in ("stop_loss", "target", "trailing_sl", "square_off")
        assert t.entry_time.date() == t.exit_time.date()  # intraday only
        assert t.exit_time.time() <= pd.Timestamp("15:30").time()
        assert t.qty == 75
    again = run_backtest(TEMPLATES[name], under, opts, lot_size=75)
    assert again.model_dump() == res.model_dump()  # deterministic


def test_ema_crossover_trades_on_synthetic(data: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    res = run_backtest(TEMPLATES["ema_crossover"], *data, lot_size=75)
    assert res.metrics.num_trades > 0
