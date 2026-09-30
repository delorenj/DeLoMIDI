"""Review round 1, host safety (R-HS-03): KLTLog must survive a folder that does not exist, a transient write failure and an
unwritable primary path, and must say so once. The crash breadcrumbs (klt.log) are the plan for the next hardware attempt: a log
that latches dead on its first failed write makes that attempt blind, and "the script crashed before it logged anything" would
then mean nothing.

Runs on the tuned folder only (the stock scripts have no KLTLog)."""
from __future__ import annotations

import os
import tempfile

import pytest

from tests.test_output_support import tuned_only  # noqa: F401  (autouse: skips the stock folder)


@pytest.fixture
def fallback(tmp_path, monkeypatch):
    """The temp folder KLTLog falls back to, redirected so no test writes into the real /tmp."""
    d = tmp_path / "fallback-temp"
    d.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(d))
    return str(d / "klt.log")


@pytest.fixture
def klt(host, scripts, fallback):
    import KLTLog
    host.set_config(LOG_ENABLED=True, LOG_PATH=host.log_path, LOG_MAX_LINES_PER_SEC=100000)
    KLTLog.retry_now()
    return KLTLog


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _blocked_path(host):
    """A LOG_PATH whose folder can never be created: its parent is a regular file."""
    blocker = os.path.join(host.tmpdir, "blocker")
    with open(blocker, "w") as f:
        f.write("x")
    return os.path.join(blocker, "sub", "klt.log")


def test_a_missing_folder_is_created_and_the_first_line_is_kept(host, klt):
    path = os.path.join(host.tmpdir, "ProgramData", "DeLoMIDI", "klt.log")
    host.set_config(LOG_PATH=path)
    klt.log("first line")
    assert "first line" in (_read(path) or "")
    assert host.script_output == []


def test_a_folder_created_later_revives_a_log_that_could_not_be_written(host, klt, fallback):
    path = _blocked_path(host)
    host.set_config(LOG_PATH=path)
    klt.log("one")                                   # falls back to the temp folder
    assert "one" in (_read(fallback) or "")
    os.remove(os.path.join(host.tmpdir, "blocker"))  # the obstacle goes away
    host.advance(31)
    klt.log("two")
    assert "two" in (_read(path) or ""), "the primary path is tried again after the back-off"
    klt.log("three")
    assert "three" in (_read(path) or "")
    assert "three" not in (_read(fallback) or "")


def test_an_unusable_primary_path_falls_back_to_the_temp_folder_and_says_so_once(host, klt, fallback, capsys):
    path = _blocked_path(host)
    host.set_config(LOG_PATH=path)
    for i in range(5):
        klt.log("line %d" % i)
    text = _read(fallback)
    assert text is not None and all(("line %d" % i) in text for i in range(5))
    assert path in text.splitlines()[0], "the first line of the fallback log names the path that failed"
    said = [l for l in capsys.readouterr().out.splitlines() if "cannot write" in l]
    assert len(said) == 1 and fallback in said[0] and path in said[0], said


def test_one_failed_write_does_not_kill_the_log(host, klt):
    """A sharing violation (an editor or a scanner holding the file) is one failed write, not the end of diagnostics."""
    klt.log("before")
    real_open = open

    def flaky(*a, **kw):
        raise PermissionError(32, "The process cannot access the file because it is being used by another process")
    klt.open = flaky
    try:
        klt.log("lost or rerouted")
    finally:
        del klt.open
    klt.log("right after")                           # inside the back-off / on the fallback: must not raise
    host.advance(31)
    klt.log("after the back-off")
    assert "after the back-off" in (_read(host.log_path) or ""), "the primary path is used again"
    assert "before" in (_read(host.log_path) or "")


def test_when_nothing_is_writable_it_backs_off_says_so_once_and_recovers(host, klt, monkeypatch, capsys):
    path = _blocked_path(host)
    host.set_config(LOG_PATH=path)
    monkeypatch.setattr(klt, "_script_dir", lambda: os.path.join(host.tmpdir, "blocker", "scripts"))
    monkeypatch.setattr(tempfile, "tempdir", os.path.join(host.tmpdir, "blocker", "tmp"))
    for i in range(20):
        klt.log("nowhere %d" % i)                    # never raises, never blocks
    said = [l for l in capsys.readouterr().out.splitlines() if "no writable log path" in l]
    assert len(said) == 1 and "again" in said[0].lower(), said
    os.remove(os.path.join(host.tmpdir, "blocker"))
    klt.log("still backing off")
    assert _read(path) is None
    host.advance(31)
    klt.log("recovered")
    assert "recovered" in (_read(path) or "")


def test_the_back_off_bounds_the_io_attempts_while_everything_fails(host, klt, monkeypatch):
    path = _blocked_path(host)
    host.set_config(LOG_PATH=path)
    monkeypatch.setattr(klt, "_script_dir", lambda: os.path.join(host.tmpdir, "blocker", "scripts"))
    monkeypatch.setattr(tempfile, "tempdir", os.path.join(host.tmpdir, "blocker", "tmp"))
    attempts = []
    real_append = klt._append
    monkeypatch.setattr(klt, "_append", lambda *a, **kw: (attempts.append(a[0]), real_append(*a, **kw))[1])
    for _ in range(1000):
        klt.log("x")
    assert len(attempts) <= 8, "%d I/O attempts for 1000 lines while every path fails" % len(attempts)


def test_a_relative_log_path_works(host, klt):
    """A relative LOG_PATH is created under the cwd and never raises."""
    host.set_config(LOG_PATH="relative-dir/klt.log")
    klt.log("rel")
    assert "rel" in (_read(os.path.join(host.tmpdir, "relative-dir", "klt.log")) or "")


def test_oninit_gives_a_dead_log_a_fresh_start(make_rig, fallback, monkeypatch):
    """A Reload (or fixing the folder and reloading) does not have to wait for the back-off."""
    rig = make_rig(boot=False)
    host = rig.host
    import KLTLog
    path = _blocked_path(host)
    host.set_config(LOG_PATH=path, LOG_MAX_LINES_PER_SEC=100000)
    monkeypatch.setattr(KLTLog, "_script_dir", lambda: os.path.join(host.tmpdir, "blocker", "scripts"))
    monkeypatch.setattr(tempfile, "tempdir", os.path.join(host.tmpdir, "blocker", "tmp"))
    KLTLog.log("dead now")
    os.remove(os.path.join(host.tmpdir, "blocker"))
    rig.scripts.boot(order=("forward", "entry"))     # no time passes: OnInit resets the back-off
    assert "KeyLab mkII (tuned) v" in (_read(path) or "")
