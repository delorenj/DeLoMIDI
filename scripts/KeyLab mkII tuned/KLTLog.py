"""
Crash-proof diagnostics for the tuned KeyLab mkII scripts.

Everything here swallows its own errors: logging must never be the reason a callback fails. Each line is
appended with open/close so the last line on disk survives an FL crash.
"""
import os
import time
import traceback

import KLTConfig as CFG

_t0 = time.monotonic()
_dead = False           # set after the first unrecoverable I/O failure so we stop retrying
_sec = 0
_count = 0
_dropped = 0
_once = set()


def _ts():
    return '%9.3f' % (time.monotonic() - _t0)


def _write(line):
    global _dead
    if _dead:
        return
    try:
        try:
            if os.path.getsize(CFG.LOG_PATH) > CFG.LOG_MAX_BYTES:
                with open(CFG.LOG_PATH, 'rb') as f:
                    f.seek(-CFG.LOG_MAX_BYTES // 2, os.SEEK_END)
                    tail = f.read()
                with open(CFG.LOG_PATH, 'wb') as f:
                    f.write(tail)
        except OSError:
            pass
        with open(CFG.LOG_PATH, 'a', encoding='utf-8', errors='replace') as f:
            f.write(line + '\n')
    except Exception:
        _dead = True


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
