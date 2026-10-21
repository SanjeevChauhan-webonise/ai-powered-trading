"""Run both built-in templates on freshly generated synthetic data: uv run python scripts/smoke_backtest.py"""

from app.data.synthetic import SyntheticConfig, generate
from app.engine.backtest import run_backtest
from app.engine.templates import TEMPLATES

under, opts = generate(SyntheticConfig(trading_days=10, n_strikes=5))
for spec in TEMPLATES.values():
    m = run_backtest(spec, under, opts, lot_size=75).metrics
    print(f"{spec.name:15s} trades={m.num_trades:3d} pnl={m.total_pnl:10.2f} win%={m.win_rate_pct} "
          f"pf={m.profit_factor} maxdd={m.max_drawdown:.0f} ({m.max_drawdown_pct:.1f}%) sharpe={m.sharpe}")  # fmt: skip
