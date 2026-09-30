"""Building blocks for the strict FL API fakes.

Every native FL module is a FakeModule holding one wrapper per function in tests/fl_api_surface.json:

* wrong arity / keyword / coarse type            -> TypeError (from the surface signature)
* name not in the surface                        -> AttributeError
* name in the surface but no behaviour modelled  -> NotImplementedError naming the function when it is CALLED
* modelled                                       -> the Impl method runs against host.state; the call is recorded

Impl classes define one method per modelled function, named exactly like the FL function. Helper methods must start
with an underscore (a public method that is not in the surface is a typo and fails at build time).
"""
from __future__ import annotations

import types

from .. import surface


class FakeModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        raise AttributeError("module '%s' has no attribute '%s' (not part of the FL API surface, "
                             "tests/fl_api_surface.json)" % (self.__name__, name))


class Impl:
    """Base class of the per-module behaviour."""

    def __init__(self, host):
        self.host = host

    @property
    def s(self):
        return self.host.state


def _unmodelled(host, sp):
    qual = sp.qual
    msg = ("%s is a real FL API function (tests/fl_api_surface.json) that tests/flsim does not model yet. Model it in "
           "tests/flsim/fakes/%s.py (with a harness test) before the tuned scripts rely on it." % (qual, sp.module))

    def wrapper(*args, **kwargs):
        call = host._begin_call(qual, args, kwargs)
        try:
            sp.check(args, kwargs, host.strict_types)
            raise NotImplementedError(msg)
        except BaseException as e:
            if call is not None:
                call.exc = e
            raise
    return wrapper


def _modelled(host, sp, fn):
    qual = sp.qual
    check = sp.check

    def wrapper(*args, **kwargs):
        call = host._begin_call(qual, args, kwargs)
        try:
            check(args, kwargs, host.strict_types)
            if host._faults:
                host._maybe_fail(qual)
            result = fn(*args, **kwargs)
        except BaseException as e:
            if call is not None:
                call.exc = e
            raise
        if call is not None:
            call.result = result
        return result
    return wrapper


def build_native_module(host, modname: str, impl: Impl | None) -> FakeModule:
    mod = FakeModule(modname)
    mod.__doc__ = "flsim fake of FL Studio's native module '%s'" % modname
    names = surface.function_names(modname)
    if impl is not None:
        stray = [n for n in dir(impl) if not n.startswith("_") and n not in ("host", "s") and callable(getattr(impl, n))
                 and n not in names]
        if stray:
            raise AssertionError("flsim fake %s implements functions that are not in the FL API surface: %s"
                                 % (modname, stray))
    modelled = []
    for name in names:
        sp = surface.spec(modname, name)
        fn = getattr(impl, name, None) if impl is not None else None
        if fn is None:
            w = _unmodelled(host, sp)
        else:
            w = _modelled(host, sp, fn)
            modelled.append(name)
        w.__name__ = name
        w.__qualname__ = sp.qual
        w.__signature__ = sp.signature
        mod.__dict__[name] = w
    mod.__dict__["__flsim_modelled__"] = tuple(modelled)
    return mod
