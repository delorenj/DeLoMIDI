"""pytest wiring for the KeyLab mkII script tests.

Targets:  default = scripts/KeyLab mkII tuned;  --script-dir PATH = any folder;  --stock = Arturia's stock folder
(read-only reference, never written: bytecode writing is disabled while a Host is active).

Two kinds of tests (see docs/tuned/TESTING.md):
  characterization         correct behaviour that must be preserved: stock and tuned must both pass
  @pytest.mark.tuned_fix("<finding-id>", ...)
                           asserts the FIXED behaviour for a documented stock bug; fails on the unfixed baseline by
                           design. With --stock it is reported xfail (strict: a tuned_fix test that passes on stock is
                           not testing a stock bug and shows up as a failure).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.flsim import Host
from tests.flsim.rig import Rig

REPO = Path(__file__).resolve().parents[1]
TUNED_DIR = REPO / "scripts" / "KeyLab mkII tuned"
# The DAW script and the Forward script are initialised by FL in an order nobody has verified; the stock Forward
# script's OnInit replaces the DAW script's display/processor objects (F-17/O-09). Characterization tests use the
# order that does not trigger that hazard; tests/test_lifecycle.py covers both orders explicitly.
BOOT_ORDER = ("forward", "entry")
STOCK_DIR = Path(os.environ.get(
    "KL_STOCK_DIR", "/home/delorenj/Documents/Image-Line/FL Studio/Settings/Hardware/Arturia KeyLab MKII"))


def pytest_addoption(parser):
    g = parser.getgroup("keylab", "KeyLab mkII script tests")
    g.addoption("--script-dir", action="store", default=None, help="script folder under test (default: tuned folder)")
    g.addoption("--stock", action="store_true", default=False,
                help="test Arturia's stock folder ($KL_STOCK_DIR); tuned_fix tests are then expected to fail (xfail)")
    g.addoption("--fuzz-n", action="store", type=int, default=100_000, help="events per fuzz configuration (default 100000)")
    g.addoption("--fuzz-seed", action="store", type=int, default=20260929, help="fuzz seed")
    g.addoption("--tuned-fix-xfail", action="store_true", default=False,
                help="report not-yet-fixed tuned_fix tests as xfail instead of failed (CI while fixes are in flight)")


def pytest_configure(config):
    config.addinivalue_line("markers", "tuned_fix(*finding_ids): asserts the fixed behaviour of a documented stock bug "
                                       "(fails on the baseline by design; xfail with --stock)")
    config.addinivalue_line("markers", "characterization: correct behaviour that must be preserved (stock and tuned pass)")
    config.addinivalue_line("markers", "harness: tests of the flsim simulator itself (independent of the target folder)")
    config.addinivalue_line("markers", "fuzz: seeded fuzz over random events x random FL states (see --fuzz-n)")


def pytest_collection_modifyitems(config, items):
    stock = config.getoption("--stock")
    soft = config.getoption("--tuned-fix-xfail")
    for item in items:
        fix = item.get_closest_marker("tuned_fix")
        if fix is None:
            if item.get_closest_marker("harness") is None:
                item.add_marker(pytest.mark.characterization)
            continue
        ids = ", ".join(fix.args) or "?"
        if stock:
            item.add_marker(pytest.mark.xfail(reason="stock bug %s: fixed only in the tuned scripts" % ids, strict=True))
        elif soft:
            item.add_marker(pytest.mark.xfail(reason="fix for %s not landed yet" % ids, strict=False))


class Target:
    def __init__(self, path: Path, is_stock: bool):
        self.path = path
        self.is_stock = is_stock

    def __str__(self):
        return "%s%s" % (self.path, " (stock)" if self.is_stock else "")


@pytest.fixture(scope="session")
def target(request) -> Target:
    opt = request.config.getoption("--script-dir")
    if request.config.getoption("--stock"):
        if opt:
            pytest.exit("--stock and --script-dir are mutually exclusive", returncode=4)
        path, stock = STOCK_DIR, True
    else:
        path, stock = (Path(opt) if opt else TUNED_DIR), False
    path = path.expanduser().resolve()
    if not path.is_dir():
        pytest.exit("script folder not found: %s" % path, returncode=4)
    return Target(path, stock)


def pytest_report_header(config):
    if config.getoption("--stock"):
        return "keylab target: STOCK %s" % STOCK_DIR
    return "keylab target: %s" % (config.getoption("--script-dir") or TUNED_DIR)


@pytest.fixture
def host_factory():
    """Create Hosts with options; every Host is closed at teardown. Only one may be active at a time: to switch
    configuration inside a test, call close(host) first."""
    made = []

    def make(**kw) -> Host:
        h = Host(**kw)
        h.__enter__()
        made.append(h)
        return h

    def close(h):
        if h in made:
            made.remove(h)
            h.__exit__(None, None, None)
    make.close = close
    yield make
    for h in reversed(made):
        h.__exit__(None, None, None)


@pytest.fixture
def host(host_factory) -> Host:
    return host_factory()


@pytest.fixture
def scripts(host, target):
    return host.load(target.path)


@pytest.fixture
def rig(host, scripts) -> Rig:
    """A booted script set in a default FL state (Channel Rack focused, 10 channels, drum mode): OnInit + the full
    OnRefresh FL sends after attaching. A boot that raises fails the test that asked for the fixture."""
    scripts.boot(order=BOOT_ORDER)
    assert not host.errors, "the baseline boot raised: %r" % [(e.callback, e.exc) for e in host.errors]
    return Rig(host, scripts)


@pytest.fixture
def make_rig(host_factory, target):
    """Factory for rigs with a non-default Host configuration: make_rig(output_assigned=False, boot=False)."""
    def make(boot=True, order=BOOT_ORDER, **kw) -> Rig:
        h = host_factory(**kw)
        s = h.load(target.path)
        if boot:
            s.boot(order=order)
        return Rig(h, s)
    return make
