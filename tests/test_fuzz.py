"""Seeded fuzz: random MIDI events (both ports) x random FL states x idle/refresh/beat/SysEx callbacks, over many
script reloads; `--fuzz-n` sets the events per configuration (default 100000), `--fuzz-seed` the seed.

The stream is generated from the seed alone (tests/flsim/streams.py), so a failure is reproducible with
    python -m tests.flsim.fuzz "<script dir>" --events N --seed S
which also prints one reproducer per unique exception site."""
from __future__ import annotations

import pytest

from tests.flsim.fuzz import run_fuzz

pytestmark = pytest.mark.fuzz

_CACHE = {}


@pytest.fixture
def fuzz(request, target):
    n = request.config.getoption("--fuzz-n")
    seed = request.config.getoption("--fuzz-seed")

    def get(output_assigned: bool):
        events = n if output_assigned else max(n // 4, 1000)     # the unassigned run only needs to reach every path once
        key = (str(target.path), events, seed, output_assigned)
        if key not in _CACHE:
            _CACHE[key] = run_fuzz(target.path, events, seed, output_assigned)
        return _CACHE[key]
    return get


def _ran_enough(res, requested):
    """An episode aborted by FLCrash stops early; a fuzz that never got past OnInit proves nothing."""
    return res.events >= 0.9 * requested


MIN_EVENTS_FOR_VIOLATION_SWEEPS = 20_000       # rare violation kinds need a long stream to show up on the baseline


def _sweep(res):
    if res.n_events < MIN_EVENTS_FOR_VIOLATION_SWEEPS:
        pytest.skip("--fuzz-n %d is too small for a violation sweep (needs %d)" % (res.n_events, MIN_EVENTS_FOR_VIOLATION_SWEEPS))
    return res


def _violations(res, kind, where_prefix=""):
    return {w: n for (k, w), n in res.violations.items() if k == kind and w.startswith(where_prefix)}


# ================================================================================================ characterization

def test_fuzz_runs_the_requested_number_of_events_and_loads_every_time(fuzz, request):
    res = fuzz(True)
    assert res.load_errors == []
    assert res.events >= request.config.getoption("--fuzz-n") - 300
    assert res.sysex_sent > 0


def test_fuzz_every_sysex_sent_is_well_framed(fuzz):
    """F0 ... F7 with every interior byte below 0x80, whatever the FL state or the text on the LCD."""
    res = fuzz(True)
    assert _violations(res, "sysex-framing") == {}


# ================================================================================================ tuned fixes

@pytest.mark.tuned_fix("F-02", "F-06", "O-03", "O-04", "O-08", "O-14")
def test_fuzz_no_exception_escapes_any_callback(fuzz):
    """No exception may escape OnInit/OnDeInit/OnMidiIn/OnMidiMsg/OnSysEx/OnRefresh/OnIdle/OnUpdateBeatIndicator/
    OnPitchBend, for any event in any FL state (FL prints the traceback and the callback's work is lost)."""
    res = fuzz(True)
    assert res.exceptions == {}, "\n" + res.report()
    assert _ran_enough(res, res.n_events)


@pytest.mark.tuned_fix("O-01", "F-02", "F-06", "O-03", "O-04", "O-08", "O-14")
def test_fuzz_no_exception_escapes_when_no_output_is_assigned(fuzz):
    res = fuzz(False)
    assert res.exceptions == {}, "\n" + res.report()
    assert _ran_enough(res, res.n_events), "only %d of %d events ran: %d episodes aborted by FLCrash" % (
        res.events, res.n_events, len(res.flcrashes))


@pytest.mark.tuned_fix("O-01")
def test_fuzz_never_raises_flcrash_with_the_output_unassigned(fuzz):
    """FLCrash = FL would have crashed (device.midiOutSysex with no output assigned, or a device.* call outside a
    script context). Not an Exception: a script cannot swallow it by accident."""
    res = fuzz(False)
    assert res.flcrashes == [], "%d episodes crashed FL, e.g. %s" % (len(res.flcrashes), res.flcrashes[:2])


def test_fuzz_never_raises_flcrash_with_the_output_assigned(fuzz):
    assert fuzz(True).flcrashes == []


@pytest.mark.tuned_fix("F-09", "F-12", "O-08")
def test_fuzz_no_mixer_or_channel_index_out_of_range(fuzz):
    res = _sweep(fuzz(True))
    v = _violations(res, "index")
    assert v == {}, "out-of-range FL indices: %s" % dict(sorted(v.items(), key=lambda kv: -kv[1])[:6])


@pytest.mark.tuned_fix("F-16")
def test_fuzz_no_plugin_parameter_index_out_of_range(fuzz):
    assert _violations(_sweep(fuzz(True)), "param-index") == {}


@pytest.mark.tuned_fix("F-05")
def test_fuzz_no_event_byte_written_outside_0_127(fuzz):
    assert _violations(_sweep(fuzz(True)), "event-range") == {}


@pytest.mark.tuned_fix("F-11")
def test_fuzz_step_parameters_stay_inside_their_documented_ranges(fuzz):
    assert _violations(_sweep(fuzz(True)), "value", "channels.setStepParameterByIndex") == {}
