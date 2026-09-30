"""The shared modules of the tuned folder: KLTConfig (switches) and KLTLog (crash-proof diagnostics).

Skipped for the stock folder (it has neither)."""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def klt(host, scripts, target):
    if not (target.path / "KLTLog.py").exists():
        pytest.skip("no KLTLog in %s" % target.path)
    import KLTLog
    host.set_config(LOG_ENABLED=True, LOG_PATH=host.log_path)
    return KLTLog


def test_log_appends_timestamped_lines_and_never_touches_the_fl_api(host, klt):
    klt.log("first")
    host.advance(2.5)
    klt.log("second")
    lines = host.read_log().splitlines()
    assert [l.split(None, 1)[1] for l in lines] == ["first", "second"]
    assert float(lines[1].split()[0]) - float(lines[0].split()[0]) == pytest.approx(2.5)
    assert host.calls == []


def test_log_never_raises_when_the_path_is_unusable(host, klt):
    host.set_config(LOG_PATH=os.path.join(host.tmpdir, "no", "such", "dir", "klt.log"))
    klt.log("x")
    klt.log_once("k", "y")
    klt.exception("where")
    host.set_config(LOG_PATH=host.log_path)
    klt.log("after")                                              # once dead, stays quiet instead of retrying forever
    assert host.read_log() == ""


def test_log_can_be_switched_off(host, klt):
    host.set_config(LOG_ENABLED=False)
    klt.log("nothing")
    assert host.read_log() == ""


def test_log_flood_guard_drops_lines_and_reports_them(host, klt):
    host.set_config(LOG_MAX_LINES_PER_SEC=5)
    for i in range(20):
        klt.log("line %d" % i)
    host.advance(1.0)
    klt.log("next second")
    text = host.read_log()
    assert text.count("line ") == 5 and "dropped 15 log lines" in text and "next second" in text


def test_log_once_logs_a_key_only_once(host, klt):
    for _ in range(5):
        klt.log_once("same", "only once")
    assert host.read_log().count("only once") == 1


def test_log_file_is_truncated_to_its_tail_beyond_the_size_cap(host, klt):
    host.set_config(LOG_MAX_BYTES=2000, LOG_MAX_LINES_PER_SEC=100000)
    for i in range(400):
        klt.log("padding line number %04d" % i)
        host.advance(0.001)
    size = os.path.getsize(host.log_path)
    assert size <= 2000 + 200
    assert "0399" in host.read_log()


def test_guarded_swallows_exceptions_logs_them_and_returns_none(host, klt):
    @klt.guarded
    def boom(x):
        """doc"""
        raise ValueError("bad %s" % x)

    @klt.guarded
    def fine(x):
        return x * 2
    assert boom(1) is None and fine(4) == 8
    assert boom.__name__ == "boom" and boom.__doc__ == "doc"
    assert "ValueError: bad 1" in host.read_log()


def test_guarded_does_not_swallow_an_emulated_fl_crash(host, klt):
    from tests.flsim import FLCrash

    @klt.guarded
    def crash():
        raise FLCrash("boom")
    with pytest.raises(FLCrash):
        crash()


def test_config_defaults_are_the_documented_safe_ones(host, scripts, target):
    if not (target.path / "KLTConfig.py").exists():
        pytest.skip("no KLTConfig")
    import KLTConfig as cfg
    assert cfg.LOG_ENABLED is True and cfg.LOG_RAW_EVENTS is False and cfg.LOG_MAX_LINES_PER_SEC > 0
