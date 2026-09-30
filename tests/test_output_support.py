"""Shared helpers for tests/test_output_*.py (the output side of the tuned scripts: gate, budgets, LCD, lifecycle, LEDs).

This module has no tests of its own. The tests in the test_output_* files exercise features that only exist in the tuned
folder (KLTConfig switches, the output layer in KLTDispatch), so they are skipped when the target is Arturia's stock
folder; the documented stock bugs they cover are asserted as `tuned_fix` tests in test_lifecycle.py / test_idle_budget.py.
"""
from __future__ import annotations

import sys

import pytest

from tests.conftest import BOOT_ORDER
from tests.flsim.driver import sysex_per_second
from tests.flsim.sysex import decode


@pytest.fixture(autouse=True)
def tuned_only(target):
    if target.is_stock:
        pytest.skip("tuned-only feature (output layer / KLTConfig switches): not part of Arturia's stock scripts")
    if not (target.path / "KLTDispatch.py").exists() or not (target.path / "KLTConfig.py").exists():
        pytest.skip("%s has no tuned output layer" % target.path)


def boot(make_rig, cfg=None, order=BOOT_ORDER, **host_kw):
    """A rig whose scripts are loaded, configured (KLTConfig overrides) and then booted, like FL attaching the
    scripts with a customised KLTConfig.py. Returns the Rig."""
    rig = make_rig(boot=False, **host_kw)
    if cfg:
        rig.host.set_config(**cfg)
    rig.scripts.boot(order=order)
    return rig


def sent(host, since=None):
    """Decoded Frame of every SysEx since a Mark (or all)."""
    msgs = host.sysex[(since.sysex if since else 0):]
    return [decode(m.data) for m in msgs]


def per_second(host, t0, seconds):
    return sysex_per_second(host, t0, t0 + seconds)


def module(name):
    """A module of the loaded script folder (the entry script, KLTDispatch, KLTReturn, ...)."""
    return sys.modules[name]


def entry_module():
    return sys.modules["device_KeyLabmk2Tuned"]


def log_lines(host, needle=None):
    lines = host.read_log().splitlines()
    return [l for l in lines if needle in l] if needle else lines


def printed(host, needle=None):
    out = [line for _, _, line in host.script_output]
    return [l for l in out if needle in l] if needle else out
