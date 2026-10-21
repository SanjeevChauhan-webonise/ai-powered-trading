from datetime import date

from app.engine.sizing import apply_money_limits, estimate_entry_premium, expiry_kind
from app.engine.templates import TEMPLATES
from tests.pipeline_helpers import synthetic

SPEC = TEMPLATES["ema_crossover"]


def test_expiry_kind():
    assert expiry_kind(date(2025, 4, 10)) == "nearest_weekly"
    assert expiry_kind(date(2025, 4, 24)) == "monthly"  # next week is in May
    assert expiry_kind(date(2025, 12, 25)) == "monthly"


def test_money_limits_set_lots_and_target():
    spec, s = apply_money_limits(SPEC, premium=100.0, lot_size=30, max_loss=2000.0, target_profit=7777.0)
    # one lot at 20% stop risks 100*30*0.2 = 600 -> 3 lots; 3 lots * 30 * 100 = 9000 premium; 7777/9000 = 86.4%
    assert s.lots == 3 and spec.lots == 3 and s.quantity == 90
    assert s.stop_loss_pct == 20 and s.target_pct == 86.4 and spec.risk.target_pct == 86.4
    assert s.est_max_loss == 1800.0 and s.est_target_profit == 7776.0
    assert SPEC.lots == 1  # the input spec is untouched


def test_tight_limit_tightens_stop_for_one_lot():
    spec, s = apply_money_limits(SPEC, premium=200.0, lot_size=30, max_loss=600.0, target_profit=None)
    assert s.lots == 1 and s.stop_loss_pct == 10.0 and s.est_max_loss == 600.0 and s.notes


def test_no_premium_keeps_spec_and_explains():
    spec, s = apply_money_limits(SPEC, premium=None, lot_size=30, max_loss=1000.0, target_profit=None)
    assert spec.lots == SPEC.lots and s.est_max_loss is None and s.notes


def test_estimate_entry_premium_from_dataset():
    under, opts = synthetic()
    p = estimate_entry_premium(under, opts, SPEC)
    assert p is not None and p > 0


def test_tightened_stop_never_exceeds_limit():
    spec, s = apply_money_limits(SPEC, premium=226.14, lot_size=75, max_loss=3000.0, target_profit=7777.0)
    assert s.lots == 1 and s.est_max_loss is not None and s.est_max_loss <= 3000.0
