"""KLTLog under FL Studio 26.1.6's real restriction: the embedded Python cannot open() any file.

Measured on tom (2026-09-30) from FL's own interpreter box: open(), even for reading C:\\Windows\\win.ini, raises
SystemError("<class '_io.FileIO'> returned NULL without setting an exception"), while print() and os.listdir() work. So the
newest lines live in an in-memory ring, and lines are printed to the Script output while the file log is unavailable.

Skipped for the stock folder (it has no KLTLog)."""
from __future__ import annotations

import builtins

import pytest

FL_ERROR = SystemError("<class '_io.FileIO'> returned NULL without setting an exception")


@pytest.fixture
def klt(host, scripts, target):
    if not (target.path / "KLTLog.py").exists():
        pytest.skip("no KLTLog in %s" % target.path)
    import KLTLog
    host.set_config(LOG_ENABLED=True, LOG_PATH=host.log_path, LOG_MAX_LINES_PER_SEC=1000)
    KLTLog.retry_now()
    KLTLog._ring.clear()
    return KLTLog


@pytest.fixture
def fl_io(monkeypatch):
    """Make open() behave like FL 26.1.6 for anything that is not a Python/pytest internal read: every open() of a path the
    log would use raises the SystemError. Returns the list of attempted paths."""
    real_open = builtins.open
    attempts = []

    def fl_open(file, *a, **kw):
        if isinstance(file, str) and file.endswith("klt.log"):
            attempts.append(file)
            raise FL_ERROR
        return real_open(file, *a, **kw)

    monkeypatch.setattr(builtins, "open", fl_open)
    return attempts


def test_with_working_files_the_ring_and_the_file_agree_and_nothing_is_printed(host, klt, capsys):
    klt.log("alpha")
    klt.log("beta")
    assert [l.split(None, 1)[1] for l in klt.dump()] == ["alpha", "beta"]
    assert "alpha" in host.read_log() and "beta" in host.read_log()
    assert "[klt]" not in capsys.readouterr().out                     # 'auto': the file works, so no console noise
    assert klt.status()["file_ok"] is True


def test_when_open_raises_the_fl_systemerror_lines_are_printed_and_kept_in_memory(host, klt, fl_io, capsys):
    klt.log("first line")
    klt.log("second line")
    out = capsys.readouterr().out
    assert "[klt] " in out and "first line" in out and "second line" in out
    assert "blocks file access" in out                               # explained once, in plain words
    assert out.count("blocks file access") == 1
    assert [l.split(None, 1)[1] for l in klt.dump()] == ["first line", "second line"]
    st = klt.status()
    assert st["no_file_io"] is True and st["file_ok"] is False


def test_the_fl_systemerror_switches_file_logging_off_for_the_session_instead_of_retrying(host, klt, fl_io):
    for i in range(50):
        klt.log("line %d" % i)
        host.advance(40)                                             # well past LOG_RETRY_S every time
    assert len(fl_io) == 1, "open() must be attempted once, not %d times: it is the interpreter, not the path" % len(fl_io)


def test_retry_now_gives_a_newer_fl_one_fresh_attempt(host, klt, fl_io):
    klt.log("a")
    assert klt.status()["no_file_io"] is True
    klt.retry_now()                                                  # what OnInit does
    assert klt.status()["no_file_io"] is False
    klt.log("b")
    assert len(fl_io) == 2


def test_the_console_has_its_own_flood_guard_and_the_ring_keeps_everything(host, klt, fl_io, capsys):
    host.set_config(LOG_CONSOLE_MAX_LINES_PER_SEC=10)
    for i in range(100):
        klt.log("burst %03d" % i)
    printed = [l for l in capsys.readouterr().out.splitlines() if "burst" in l]
    assert len(printed) == 10
    assert len(klt.dump()) == 100                                    # nothing is lost from the ring
    host.advance(1.0)
    klt.log("later")
    assert any("not printed" in l for l in capsys.readouterr().out.splitlines())


def test_the_ring_is_bounded_and_dump_can_return_the_tail(host, klt, fl_io):
    host.set_config(LOG_RING_LINES=500)
    for i in range(700):
        klt.log("n %d" % i)
    assert len(klt.dump()) <= 500
    assert klt.dump(3)[-1].endswith("n 699") and len(klt.dump(3)) == 3


def test_console_modes(host, klt, capsys):
    host.set_config(LOG_TO_CONSOLE=True)
    klt.log("always printed")
    assert "always printed" in capsys.readouterr().out               # True: printed even though the file works
    host.set_config(LOG_TO_CONSOLE=False)
    klt.log("never printed")
    assert "never printed" not in capsys.readouterr().out            # False: silent (ring and file still get it)
    assert any("never printed" in l for l in klt.dump())


def test_exceptions_and_guarded_callbacks_reach_the_ring_and_console_under_the_fl_restriction(host, klt, fl_io, capsys):
    @klt.guarded
    def boom():
        raise ValueError("kaput")
    assert boom() is None
    assert any("ValueError" in l and "kaput" in l for l in klt.dump())
    assert "kaput" in capsys.readouterr().out


def test_logging_still_never_raises_if_print_and_the_ring_are_broken(host, klt, monkeypatch):
    monkeypatch.setattr(builtins, "print", lambda *a, **k: (_ for _ in ()).throw(OSError("closed stdout")))
    monkeypatch.setattr(klt, "_ring", None)
    host.set_config(LOG_TO_CONSOLE=True)
    klt.log("x")
    klt.log_once("k", "y")
    klt.exception("where")
    assert klt.dump() == []


def test_no_script_module_touches_the_filesystem_except_klt_log(target):
    """FL cannot open() files, so nothing else in the tuned folder may depend on it."""
    import re
    if not (target.path / "KLTLog.py").exists():
        pytest.skip("stock folder")
    offenders = []
    for py in sorted(target.path.glob("*.py")):
        if py.name == "KLTLog.py":
            continue
        for n, line in enumerate(py.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"(?<![\w.])open\(|pathlib|\.write_text\(|\.read_text\(|shutil\.|tempfile\.", code):
                offenders.append("%s:%d: %s" % (py.name, n, line.strip()))
    assert not offenders, "file access outside KLTLog (unusable on FL 26.1.6):\n" + "\n".join(offenders)
