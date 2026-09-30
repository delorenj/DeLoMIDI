"""
Crash-proof diagnostics for the tuned KeyLab mkII scripts.

Everything here swallows its own errors: logging must never be the reason a callback fails. Each line is
appended with open/close so the last line on disk survives an FL crash.
"""
import collections
import os
import time
import traceback

try:                    # KLT O-15: every script imports this module: a stripped stdlib must cost the temp-folder fallback, not the log
    import tempfile
except ImportError:
    tempfile = None

import KLTConfig as CFG

_t0 = time.monotonic()
_sec = 0
_count = 0
_dropped = 0
_once = set()

# KLT H-FL-IO: measured on FL Studio 26.1.6 (tom, 2026-09-30): the embedded Python 3.12.1 cannot open() ANY file, not even to read
# C:\Windows\win.ini: it raises SystemError("<class '_io.FileIO'> returned NULL without setting an exception"), while print() and
# os.listdir() work. So the file log below can never work there. The newest lines are therefore always kept in this ring (read it from
# View > Script output > this script's tab: print('\n'.join(__import__('KLTLog').dump(60)))), and lines are printed to the Script
# output while the file log is unavailable (LOG_TO_CONSOLE = 'auto'). A SystemError from open() is a property of the interpreter, not of
# a path, so it switches file logging off for the rest of the session instead of retrying three paths every LOG_RETRY_S.
try:
    _ring = collections.deque(maxlen=max(10, int(getattr(CFG, 'LOG_RING_LINES', 500))))
except Exception:
    _ring = collections.deque(maxlen=500)
_no_file_io = False     # open() itself is blocked (SystemError): no file logging until retry_now()
_file_ok = False        # the last file write succeeded
_console_sec = 0
_console_count = 0
_console_dropped = 0

# Where lines go (review R-HS-03): the log used to latch dead for good on its first failed write (folder missing, a sharing
# violation), silently, so the crash breadcrumbs it exists for could vanish and the next hardware attempt would be blind.
# Now: LOG_PATH first (its folder is created if it is missing), then <temp>/klt.log, then the script folder. A path that
# failed is tried again after LOG_RETRY_S; if every path fails the lines are dropped until then. The first fallback in use
# and a total failure are each printed once to FL's Script output.
_where = 0              # 0 = CFG.LOG_PATH, 1 = <temp>/klt.log, 2 = <script folder>/klt.log
_retry_at = 0.0         # every path failed: no new attempt before this monotonic time
_primary_at = 0.0       # on a fallback: the next time LOG_PATH is tried again
_told = set()


def _ts():
    return '%9.3f' % (time.monotonic() - _t0)


def _retry_s():
    try:
        return max(1.0, float(CFG.LOG_RETRY_S))
    except Exception:
        return 30.0


def _script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _fallbacks():
    """The paths tried after LOG_PATH, in order (computed only when LOG_PATH failed)."""
    out = []
    try:
        out.append(os.path.join(tempfile.gettempdir(), 'klt.log'))     # None.gettempdir raises: caught, no temp fallback
    except Exception:
        out.append(None)
    try:
        out.append(os.path.join(_script_dir(), 'klt.log'))
    except Exception:
        out.append(None)
    return out


def _io_blocked(ex):
    """True for the FL 26.1.6 failure mode: open() itself is unusable (SystemError, not OSError)."""
    try:
        return isinstance(ex, SystemError) or 'returned NULL without setting an exception' in str(ex)
    except Exception:
        return False


def _append(path, line, make_dir=False):
    """Append one line to `path` (opened and closed per line, so the last line on disk survives an FL crash). True on success,
    False on any failure. With `make_dir` a missing folder is created and the write tried once more. Never raises."""
    global _no_file_io
    for attempt in (0, 1):
        try:
            if attempt:
                folder = os.path.dirname(path)
                if folder:
                    os.makedirs(folder, exist_ok=True)
            try:
                if os.path.getsize(path) > CFG.LOG_MAX_BYTES:
                    with open(path, 'rb') as f:
                        f.seek(-CFG.LOG_MAX_BYTES // 2, os.SEEK_END)
                        tail = f.read()
                    with open(path, 'wb') as f:
                        f.write(tail)
            except OSError:
                pass
            with open(path, 'a', encoding='utf-8', errors='replace') as f:
                f.write(line + '\n')
            return True
        except Exception as ex:
            if _io_blocked(ex):                 # KLT H-FL-IO: no path can work in this interpreter
                _no_file_io = True
                return False
            if not make_dir:
                return False
    return False


def _tell(key, text):
    """One line to FL's Script output per distinct problem (the log file itself is what is broken)."""
    try:
        if key in _told:
            return
        _told.add(key)
        print('KeyLab mkII (tuned): ' + text)
    except Exception:
        pass


def retry_now():
    """OnInit: a Reload (or fixing the folder and reloading) starts with a clean slate instead of waiting for the back-off."""
    global _where, _retry_at, _primary_at, _no_file_io, _file_ok
    _where, _retry_at, _primary_at = 0, 0.0, 0.0
    _no_file_io, _file_ok = False, False       # KLT H-FL-IO: one fresh attempt per attach (a newer FL may allow open())
    _told.clear()


def _console(line):
    """Print one line to FL's Script output, rate-limited (lines over the cap stay in the ring). Never raises."""
    global _console_sec, _console_count, _console_dropped
    try:
        now = int(time.monotonic())
        if now != _console_sec:
            if _console_dropped:
                print('[klt] %d log lines not printed (console flood guard, see KLTLog.dump())' % _console_dropped)
            _console_sec, _console_count, _console_dropped = now, 0, 0
        _console_count += 1
        if _console_count > max(1, int(CFG.LOG_CONSOLE_MAX_LINES_PER_SEC)):
            _console_dropped += 1
            return
        print('[klt] ' + line)
    except Exception:
        pass


def dump(n=None):
    """The newest `n` log lines (all kept ones when n is None) as a list of str. Works whether or not files can be written."""
    try:
        lines = list(_ring)
        return lines if n is None else lines[-int(n):]
    except Exception:
        return []


def status():
    """Where diagnostics are going right now (for the Script output command box)."""
    try:
        return {'file_ok': _file_ok, 'no_file_io': _no_file_io, 'where': _where, 'ring': len(_ring),
                'console_dropped': _console_dropped, 'log_path': CFG.LOG_PATH}
    except Exception:
        return {}


def _write(line):
    """Ring first (always), then the file (unless open() is blocked), then the console (per LOG_TO_CONSOLE). Never raises."""
    global _file_ok
    try:
        _ring.append(line)
    except Exception:
        pass
    ok = False
    try:
        ok = _write_file(line)
    except Exception:
        ok = False
    _file_ok = ok
    try:
        mode = getattr(CFG, 'LOG_TO_CONSOLE', 'auto')
        if mode is True or (mode == 'auto' and not ok):
            _console(line)
    except Exception:
        pass


def _write_file(line):
    """Append `line` to the first usable log path. True when a file took it. Never raises."""
    global _where, _retry_at, _primary_at
    try:
        if _no_file_io:
            return False
        now = time.monotonic()
        if now < _retry_at:
            return False
        primary = CFG.LOG_PATH
        if _where == 0 or now >= _primary_at:
            if _where != 0:
                _primary_at = now + _retry_s()
            if _append(primary, line, make_dir=True):
                _where = 0
                return True
            if _no_file_io:
                _tell('no-file-io', 'log: this FL build blocks file access from scripts (open() raises SystemError), so klt.log cannot '
                                    'be written; diagnostics go to this Script output and to an in-memory ring (KLTLog.dump())')
                return False
        # LOG_PATH is unusable: the fallback that worked last time first, then the others
        fallbacks = _fallbacks()
        order = list(range(len(fallbacks)))
        if 1 <= _where <= len(order):
            order.remove(_where - 1)
            order.insert(0, _where - 1)
        for idx in order:
            path = fallbacks[idx]
            if path is None:
                continue
            if idx + 1 != _where:
                note = 'log: cannot write %s, writing %s instead (the original is tried again every %d s)' % (
                    primary, path, _retry_s())
                if not _append(path, '%s [klt] %s' % (_ts(), note), make_dir=(idx == 0)):
                    if _no_file_io:             # KLT H-FL-IO: open() itself is blocked, trying more paths cannot help
                        break
                    continue
                _tell(('fallback', idx + 1), note)
                if _where == 0:
                    _primary_at = now + _retry_s()
                _where = idx + 1
            if _append(path, line):
                return True
            if _no_file_io:
                break
        if _no_file_io:
            _tell('no-file-io', 'log: this FL build blocks file access from scripts (open() raises SystemError), so klt.log cannot '
                                'be written; diagnostics go to this Script output and to an in-memory ring (KLTLog.dump())')
            return False
        _where = 0
        _retry_at = now + _retry_s()
        _tell('dead', 'log: no writable log path (%s, %s): diagnostics are off, trying again every %d s' % (
            primary, ', '.join(str(p) for p in fallbacks), _retry_s()))
        return False
    except Exception:
        return False


def log(msg):
    """Append one line. Flood-guarded. Never raises."""
    global _sec, _count, _dropped
    try:
        if not CFG.LOG_ENABLED:
            return
        now = int(time.monotonic())
        if now != _sec:
            if _dropped:
                _write('%s [klt] dropped %d log lines (flood guard)' % (_ts(), _dropped))
            _sec, _count, _dropped = now, 0, 0
        _count += 1
        if _count > CFG.LOG_MAX_LINES_PER_SEC:
            _dropped += 1
            return
        _write('%s %s' % (_ts(), msg))
    except Exception:
        pass


def log_once(key, msg):
    """Log a message the first time `key` is seen (e.g. a repeating failure). Never raises."""
    try:
        if key in _once:
            return
        _once.add(key)
        log(msg)
    except Exception:
        pass


def exception(where):
    """Log the current exception with traceback under a label. Call from an `except` block. Never raises."""
    try:
        log('EXC in %s:\n%s' % (where, traceback.format_exc().rstrip()))
    except Exception:
        pass


def guarded(fn):
    """Decorator for FL callbacks: an exception is logged (once per site per second) and swallowed, so one bad
    LED/LCD/control routine cannot take down the rest of the script."""
    name = getattr(fn, '__name__', repr(fn))

    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception:
            try:
                log_once((name, int(time.monotonic())), 'EXC in %s:\n%s' % (name, traceback.format_exc().rstrip()))
            except Exception:
                pass
            return None
    wrapper.__name__ = name
    wrapper.__doc__ = fn.__doc__
    return wrapper
