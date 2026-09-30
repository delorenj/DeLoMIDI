"""Replay one identical seeded event stream through the stock scripts and the folder under test
(tests/flsim/diffreplay.py) and fail on regressions: an exception where stock had none, or more FLCrash than stock.

Intended behaviour changes (fixes) never make this fail; a broken characterization does."""
from __future__ import annotations

import pytest

from tests.conftest import STOCK_DIR
from tests.flsim import diffreplay


@pytest.mark.parametrize("assigned", [True, False], ids=["output-assigned", "output-unassigned"])
def test_no_regression_against_the_stock_scripts_on_a_replayed_stream(target, capsys, assigned):
    if target.is_stock:
        pytest.skip("comparing the stock folder with itself")
    if not STOCK_DIR.is_dir():
        pytest.skip("stock folder not found: %s" % STOCK_DIR)
    argv = [str(STOCK_DIR), str(target.path), "--events", "4000", "--seed", "11", "--fail-on-regression", "--show", "8"]
    if not assigned:
        argv.append("--unassigned")
    code = diffreplay.main(argv)
    out = capsys.readouterr().out
    assert code == 0, "tuned behaves worse than stock somewhere:\n" + out[-3500:]
