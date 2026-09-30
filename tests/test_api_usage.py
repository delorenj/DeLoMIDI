"""Static check of every FL API use in the script folder: names exist, arity fits, and flsim models them.

Dynamic tests only see the paths they execute; this walks the whole AST, so a call on a path no test reaches (a
misspelt function, a wrong argument count, a constant that FL's midi.py lacks) is still caught. A function that the
scripts use but flsim does not model is flagged loudly: model it in tests/flsim/fakes/<module>.py first (docs/tuned/TESTING.md)."""
from __future__ import annotations

import ast

from tests.flsim import surface
from tests.flsim.fakes import IMPLS
from tests.flsim.fakes.pylib import load_midi, load_utils

NATIVE = set(surface.NATIVE_MODULES)


def _fl_import_names(tree):
    """Local names bound to FL modules: `import ui` and `import channels as ch`."""
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in surface.API_MODULES:
                    names[a.asname or a.name] = a.name
    return names


def collect(target):
    """[(file, line, module, attr, call node or None)] for every `<fl module>.<attr>` in the folder."""
    uses = []
    for p in sorted(target.path.glob("*.py")):
        tree = ast.parse(p.read_bytes(), str(p))
        names = _fl_import_names(tree)
        calls = {id(n.func): n for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in names:
                uses.append((p.name, node.lineno, names[node.value.id], node.attr, calls.get(id(node))))
    return uses


def test_every_fl_function_the_scripts_call_exists_in_the_api_surface(target):
    missing = []
    midi, utils = load_midi(), load_utils()
    for f, line, mod, attr, call in collect(target):
        if mod in NATIVE:
            if surface.spec(mod, attr) is None:
                missing.append("%s:%d %s.%s is not in the FL API surface" % (f, line, mod, attr))
        elif mod == "midi" and not hasattr(midi, attr):
            missing.append("%s:%d midi.%s does not exist in FL's midi.py (%s)" % (f, line, attr, midi.__flsim_source__))
        elif mod == "utils" and not hasattr(utils, attr):
            missing.append("%s:%d utils.%s does not exist (%s)" % (f, line, attr, utils.__flsim_source__))
    assert not missing, "\n".join(missing)


def test_static_call_arity_matches_the_api_surface(target):
    bad = []
    for f, line, mod, attr, call in collect(target):
        sp = surface.spec(mod, attr) if mod in NATIVE else None
        if sp is None or call is None:
            continue
        if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
            continue
        try:
            sp.check(tuple(range(len(call.args))), {k.arg: 0 for k in call.keywords}, types=False)
        except TypeError as e:
            bad.append("%s:%d %s" % (f, line, e))
    assert not bad, "\n".join(bad)


def test_every_fl_function_the_scripts_use_is_modelled_by_flsim(target):
    """NEW API use in the scripts must be modelled by the simulator before it can be trusted: an unmodelled function
    raises NotImplementedError when called (tests/flsim/fakes/base.py), and this test names them all up front."""
    unmodelled = set()
    for f, line, mod, attr, call in collect(target):
        if mod not in NATIVE:
            continue
        impl = IMPLS.get(mod)
        if impl is None or not hasattr(impl, attr):
            unmodelled.add("%s.%s (first used %s:%d)" % (mod, attr, f, line))
    assert not unmodelled, "not modelled by tests/flsim: %s" % sorted(unmodelled)


def test_callbacks_defined_by_the_device_scripts_are_real_fl_callbacks(target):
    """A misspelt callback (OnMidiMsgs, onIdle) is silently never called by FL."""
    known = set(surface.callback_names())
    from tests.flsim.loader import detect_scripts
    bad = []
    for p in detect_scripts(target.path):
        tree = ast.parse(p.read_bytes(), str(p))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.lower().startswith("on") and node.name not in known:
                bad.append("%s defines %s(), which FL never calls" % (p.name, node.name))
    assert not bad, bad
