# Testing the tuned KeyLab mkII scripts

Everything is verified on Linux, in a strict simulator of the FL Studio MIDI-scripting host (`tests/flsim/`). The FL host
(tom) is never contacted. **The simulator reproduces the scripts' own logic, not FL's internals: nothing here has been
run in FL 26.1.6 or against the keyboard.** See "What is NOT modelled" before trusting a green run.

## Run it

```bash
cd /home/delorenj/code/DeLoMIDI

# the suite, against scripts/KeyLab mkII tuned  (Python 3.12 = the interpreter FL embeds)
uv run --python 3.12 --with pytest python -m pytest tests -q

# other targets
uv run --python 3.12 --with pytest python -m pytest tests -q --stock                  # Arturia's stock folder
uv run --python 3.12 --with pytest python -m pytest tests -q --script-dir "/some/folder"
uv run --python 3.12 --with pytest python -m pytest tests -q --fuzz-n 20000 --fuzz-seed 7
uv run --python 3.12 --with pytest python -m pytest tests -q --tuned-fix-xfail        # unfixed tuned_fix tests as xfail

# what did the tuned scripts change, behaviourally?  (identical seeded stream through both, categorised diff)
uv run --python 3.12 python -m tests.flsim.diffreplay "<stock dir>" "scripts/KeyLab mkII tuned" --events 20000 --seed 1
#   [--unassigned] [--boot-order entry,forward] [--show K] [--fail-on-regression]

# fuzz one folder by hand (prints one reproducer per unique exception site)
uv run --python 3.12 python -m tests.flsim.fuzz "scripts/KeyLab mkII tuned" --events 100000 --seed 1 [--unassigned]
```

Stock folder: `$KL_STOCK_DIR`, default `/home/delorenj/Documents/Image-Line/FL Studio/Settings/Hardware/Arturia KeyLab MKII`
(read-only: bytecode writing is off while a Host is active, nothing is ever written there). FL's real `midi.py` /
`utils.py`: `$FL_MIDI_PY`, default `.../FL Studio 2025/Shared/Python/Lib/midi.py` in the wine prefix, read at run time and
never copied into the repo; if absent, the constants recorded in `tests/fl_api_surface.json` (`constants.midi_fl_real`,
generated from the same file) are used and `midi.__flsim_source__` says so.

Runtime: about 20 s (the default fuzz is 100,000 events for the output-assigned run plus 25,000 for the unassigned run).

## Two kinds of tests

| marker | meaning | stock | tuned baseline (== stock) | tuned after the fixes |
|---|---|---|---|---|
| `characterization` (unmarked tests get it) | correct behaviour that must be preserved | pass | pass | must pass |
| `@pytest.mark.tuned_fix("F-04", ...)` | the FIXED behaviour of a documented stock bug (finding ids from `docs/analysis`) | **xfail** (strict) | **fail, by design** | must pass |
| `harness` | tests of the simulator itself (independent of the target folder) | pass | pass | pass |

`--stock` marks every `tuned_fix` test `xfail(strict=True)`: a `tuned_fix` test that passes on stock would not be testing a
stock bug and shows up as a failure. `--tuned-fix-xfail` (non-strict) is for CI while fixes are in flight.

**Baseline result** (the tuned folder is byte-for-byte stock behaviour, `diffreplay` shows zero differences):

| target | passed | failed | xfailed | skipped |
|---|---|---|---|---|
| `scripts/KeyLab mkII tuned` (baseline) | 260 | 84 (all `tuned_fix`) | 0 | 0 |
| `--stock` | 247 | 0 | 84 | 13 (tuned-only checks: LF endings, KLT annotations, KLTLog/KLTConfig, regression-vs-stock) |

A quick, uncommitted reference implementation of all the fixes (kept in the scratchpad, only to prove the tests are
satisfiable together and that plausible fixes keep the characterization tests green) makes 343 of 344 pass; the one
failure is the annotation lint (`test_every_change_against_the_stock_scripts_carries_a_klt_comment`), which is the point of
that test.

## Findings covered by `tuned_fix` tests

| finding | test(s) (file) | asserts |
|---|---|---|
| O-01 | `test_unassigned_output_is_never_written_to[crash,noop]`, `..._checked_before_the_first_sysex`, `..._assigning_the_output_later...` (lifecycle), fuzz FLCrash | no `device.midiOutSysex` while the output is unassigned (whether FL crashes or no-ops); `isAssigned()`/`isMidiOutAssigned()` consulted first; display comes up once assigned; `FLCrash` never raised |
| O-02 | `test_sysex_per_second_stays_within_budget...[drum,mixer,sequencer-playing]`, `test_a_quiet_idle_loop_sends_almost_nothing` (idle_budget) | OnIdle at 50 Hz for 60 virtual s with FL state changing: worst second <= 150 SysEx, average <= 60/s; quiet loop <= 30/s (stock: 1,200-1,340/s) |
| O-03 | `test_non_ascii_text_does_not_break_the_display[prog_title,channel_name,pattern_name,param_name]` | non-ASCII text: no exception, ASCII-only LCD frames, LED pass keeps running |
| O-04 | callbacks/events before OnInit, partial init (`getProgTitle`/`getChannelName`/`getPatternName` fail once), one failing LED routine, empty rack | no exception escapes; display recovers |
| O-05 | `test_lcd_is_repainted_after_a_memory_switch` | LCD frame re-sent after the memory-switch SysEx |
| O-06 | `test_lcd_frames_are_spaced_and_the_last_value_still_arrives` | LCD frames >= 35 ms apart during a fader sweep, last value still delivered |
| O-08, F-12 | stale bank offset after the rack shrinks; empty channel rack; fuzz index sweep | no IndexError, no invalid channel index |
| O-12 | `test_oninit_does_not_sleep` | zero `time.sleep` in OnInit (stock: 2.92 s) |
| O-14 | `test_step_parameter_query_failing_does_not_break_the_sequencer_leds` | `getCurrentStepParam == -1` does not raise |
| F-17, O-09 | `test_daw_script_first_boot_order_also_ends_with_the_main_page_on_the_lcd` | the Forward script's `OnInit` must not replace the DAW script's display/processor objects (see Discoveries) |
| F-01 | keybed notes never act on FL under H1; held keys 91/92 never leave the transport scrubbing | keybed is never a DAW command |
| F-02 | `test_analog_lab_ccs_never_raise_on_the_keyboard_port`, mod-wheel negative track | the 17 Analog Lab CCs and CC1 do not raise / reach track -14 |
| F-04 | song-mode pad press does not stick the encoders; leaving Sequencer mode clears held pads | encoder 9 pans again, encoders do not edit step 0 |
| F-05 | `test_drum_pad_velocity_is_preserved`, `test_a_range_checked_event_does_not_raise_on_pads` | velocity untouched, no event byte written outside 0..127 |
| F-06 | pads outside 36..51 in drum and Sequencer mode | no `event.data1 = None`, no `TypeError` in `ReleaseBit` |
| F-07 | `test_pads_are_not_remapped_for_instruments_other_than_fpc` | remap only when FPC is the selected plugin (`plugins.getPluginName(selectedChannel)`) or focused (`ui.getFocusedPluginName`) |
| F-08 | mixer-mode faders/encoders and mapped plugin controls are consumed | `event.handled is True` after they were applied |
| F-09 | last mixer bank never addresses tracks beyond `mixer.trackCount()` (127) | no out-of-range mixer index |
| F-11 | step pitch direction, step parameters inside documented ranges, edit starts from the step's value | pitch up when clockwise; MOD Y <= 127; first velocity tick from 100 does not jump to 67 |
| F-12 | `test_mixer_mode_follows_the_window_the_user_focused_with_the_mouse` | after `OnRefresh(HW_Dirty_FocusedWindow)` the faders follow the real focus |
| F-14 | `test_a_jog_tick_does_not_touch_every_channel_editor` | <= 5 `channels.showEditor` per jog tick at 300 channels |
| F-16 | unmapped plugin slots | no `plugins.*` call with parameter index -1 |
| F-21 | previous pattern at pattern 1 | no `jumpToPattern(0)` |
| F-23 | note-off release of `<<`/`>>`; mode toggled while held | the scrub is always stopped |

Suggested split for two implementers: **output side** (LEDs, LCD, lifecycle, entry script: O-xx, F-17) owns
`test_lifecycle.py`, `test_idle_budget.py`, `test_klt_shared.py` and the O-xx fuzz tests; **input side** (controls, pads,
Forward script: F-xx) owns `test_pads.py`, `test_input_fixes.py`, `test_forward.py`, `test_banking.py`,
`test_plugin_db.py`. Both must keep every characterization test and `test_regression_vs_stock.py` green
(`pytest tests -q -m "not tuned_fix"`) and re-run `diffreplay` to see the whole behavioural delta.

### Deliberately NOT asserted (hardware- or design-dependent; add a `KLTConfig` switch and a test when decided)

F-03 (what to do with unmapped ids: swallowed today), F-10 (relative-encoder tick magnitude/acceleration; jog only
acts on values 1/65), F-13/O-13 (Channel Rack groups; the simulator has no groups), F-15 (14-bit wheel), F-18 (`ui.cut`),
F-19 (`FakeMIDImsg` punch), F-20 (`pmeFlags` gating), F-22 (Undo value 20 vs 1/2), F-24 (jog yanks focus to the rack),
F-01 pads via the Forward script and the `handled` override there, O-07 (flag-aware OnRefresh), O-10 (pad LED
orientation on the 88), O-11, O-17 (Save LED), O-18, O-19 (`getCurrentTempo(1)` unit), O-20 (RGB trailing byte meaning;
the byte layouts are pinned as they are), RECT_OFFSET upper bound. The 15-plugin parameter database is pinned exactly as
Arturia wrote it (`tests/data/plugin_db.json`, regenerated from stock and compared by a test), including its known
duplicate parameters.

## The simulator (`tests/flsim/`)

| module | role |
|---|---|
| `surface.py` | `tests/fl_api_surface.json` as callable specs: arity, keyword names, positional-only, coarse types |
| `fakes/*.py` | one strict fake per FL module (`device ui channels mixer patterns transport plugins playlist general` modelled; `arrangement screen launchMapPages` present but every function raises `NotImplementedError`); `midi`/`utils` are FL's real files |
| `host.py` | `Host`: mutable FL state, virtual clock, records every API call + every SysEx (virtual timestamps), violations, escaped exceptions, script `print` output; crash emulation; fault injection |
| `clock.py` | virtual `time.monotonic/time/perf_counter/sleep` while a Host is active; sleeping advances the clock and is recorded (`clock.sleeps_in("OnInit")`) |
| `events.py` | `FlEvent` per the stubs (aliases, read-only fields, `populated` switch for H1/H2) |
| `loader.py` | FL-like loader and event pipeline; auto-detects stock and tuned entry/forward files |
| `sysex.py` | decoder for the Arturia SysEx grammar and `DeviceModel` (what the keyboard is showing) |
| `driver.py` | `SessionDriver`: OnIdle at 50 Hz, playback with beat-indicator callbacks, scheduled FL state changes |
| `streams.py`, `fuzz.py`, `diffreplay.py` | seeded host-independent event streams, fuzz runner, stock-vs-tuned diff |
| `rig.py` | test convenience: `rig.button(94)`, `rig.cc(60, 1)`, `rig.fader(2, 100)`, `rig.pad_on(36)`, `Action.effects/called/...` |
| `gen_plugin_golden.py` | regenerates `tests/data/plugin_db.json` from the stock scripts |

### Strictness

* wrong arity or keyword -> `TypeError`; wrong coarse type (`None` or a float for an `int`, `str` for `bytes`) -> `TypeError`
  (`Host(strict_types=False)` relaxes types, never arity);
* name not in the surface -> `AttributeError`; a real FL function that is not modelled -> `NotImplementedError` naming it
  when it is called (after the arity check). Any NEW API use in the tuned scripts is therefore flagged loudly, and
  `tests/test_api_usage.py` lists it statically. **To model a function**: add a method with exactly the FL name and
  parameter list to the module's `Impl` in `tests/flsim/fakes/<module>.py` (a harness test checks it against the surface)
  and give it a harness test.
* rule violations are recorded, not raised (`Host(on_violation="raise")` raises): `index` (mixer track / channel outside
  its valid range, e.g. track 127 or channel 0 of an empty rack), `param-index` (plugin parameter -1), `value` (step
  parameter outside its documented range, volume/pan/parameter outside 0..1/-1..1), `event-range` (an event byte written
  outside 0..127: F-05), `sysex-framing` (not `F0 ... F7`, or a data byte >= 0x80).
* static checks: `test_api_usage.py` walks every AST for FL names, arity and callbacks; `test_hygiene.py` checks Python
  3.12 `-W error` compile, imports (stdlib + FL only), LF endings, indentation, droppings, `# name=` header, and that every
  difference from stock carries a `# KLT <finding-id>: why` comment.

### Crash emulation

`FLCrash` is a `BaseException` (a script's `except Exception` cannot swallow it). Raised when

* the script's MIDI output is unassigned (`Host(output_assigned=False)` or `host.set_output_assigned(role, False)`; the
  role is `"entry"` or `"forward"`) and it calls `device.midiOutSysex` / `device.midiOutMsg` -- the leading hypothesis for
  `docs/incidents/2026-09-29-fl-crash-kl-probe.crash.txt`. `Host(crash_on_unassigned_output=False)` models the other
  hypothesis (a silent no-op; the dropped messages are in `host.dropped_sysex`);
* any `device.*` function is called at import time or outside every script callback ("interpreter not associated with a
  device", stubs `device/__device.py:53`; `Host(crash_on_import_device_calls=False)` turns the import rule off).

`device.isAssigned()` / `isMidiOutAssigned()` / `getPortNumber()` follow the flag. Tests assert
`fuzz.flcrashes == []` and `pytest.fail` on `FLCrash`.

### Loader and event pipeline

* one interpreter for both device scripts: the script folder is on `sys.path`, the stock Forward script's
  `import device_KeyLabmkII as KL` gets the entry module, module state is shared, and every `host.load()` starts from
  fresh module state (helper modules are dropped from `sys.modules` on reload);
* each script has its own output/port; `device.*` acts for the script whose callback is running (`host.current`), so an
  LCD frame produced while the Forward script handles an event leaves through the Forward script's output (O-09);
* `script.deliver_midi(status, d1, d2)`: `OnMidiIn` -> (unless handled) `OnMidiMsg` (`OnSysEx` for SysEx) -> (unless handled)
  the typed callback (`OnNoteOn`, `OnControlChange`, `OnPitchBend`, ...), as the FL manual documents; exceptions inside a
  callback are caught and recorded in `host.errors` like FL's Script output (`invoke()` lets them propagate);
* **H1/H2**: `Host(midi_in_populated=True|False)` or `deliver_midi(..., populated=...)` decide whether `midiId`/`midiChan`
  are filled in `OnMidiIn` (docs/analysis/02 3.3). Forward-script tests run under both;
* `ScriptSet.boot(order=...)`: OnInit + a full OnRefresh (`refresh_flags=None` = none), in the given order of the two device
  scripts. **No OnIdle runs in `boot()`**: since review round 1 the tuned scripts send nothing before the first OnIdle tick
  (`OUT_DEFER_TO_IDLE`), so a test that looks at SysEx or at the output gate right after `boot` idles first.

### State model (what the fakes do)

Selected channel/track, focus and visibility of windows (`showEditor` opens a plugin window and focuses it, closing the
last editor returns focus to the Channel Rack), `ui.next()/previous()` move the channel-rack or mixer selection, mute/solo,
grid bits and step parameters (documented ranges and defaults), pattern selection (`jumpToPattern` past the last pattern
creates it), transport play/record/loop mode, metronome and loop-record toggled by `globalTransport(FPT_Metronome /
FPT_LoopRecord)`, plugin parameters per channel, tempo (`getCurrentTempo(1)` = milli-BPM), song position (driven by
`SessionDriver` during playback). The mixer always has 127 tracks (master, 125 inserts, "current track").

## What is NOT modelled / unverified

* FL itself: default routing of an unhandled event, the controller link system, threading, the real idle rate (50 Hz is
  the documented "roughly 20 ms"), real timing of anything, FL's own reaction to an invalid index (recorded as a
  violation, never asserted to crash), what `device.midiOutSysex` really does with no output (both hypotheses are
  switchable), whether FL runs the two device scripts in one interpreter (the sim assumes yes, the best case: F-17),
  which script FL initialises first (`boot(order=)`), whether `OnRefresh` follows `OnInit` (the sim sends a full one; since
  review round 1 the tuned scripts paint pads and Play/Stop/Record LEDs by themselves once the init sequence is done, and the
  `test_review_fix_paint.py` tests boot with `scripts.boot(refresh_flags=None)`, i.e. without it).
* Channel Rack groups / the group-relative index of API v33+ (F-13); `pmeFlags` semantics; plugin parameter lists of the
  real plugins (indices in the database are unverified: docs/analysis/02 5.3); FL's clamping of pan/volume values.
* The keyboard: the hardware contract (button = note-on ch1 velocity 127/0 vs note-off, encoders CC16..24, jog CC60,
  faders as pitch bend, pads on ch10 notes 36..51), which DAW preset it is in, what the firmware does with SysEx (the
  trailing `7F`, the deinit frame, LED numbering on the 88), flood tolerance.
* Assumptions made by the fakes, each easy to change: assigning `None`/a float to an `FlEvent` int field raises
  `TypeError` (a native object would); an `FlEvent` byte outside 0..127 is a recorded violation (real FL's behaviour is
  UNVERIFIED); `FlMidiMsg.pitchBend` is not modelled and raises; `ui.snapMode(n)` cycles 10 modes; the Forward script's
  keybed events arrive with `port == 1`, DAW events with `port == 0`.
* Everything in this suite passes or fails identically on tom only after a run there: the plan in
  `docs/analysis/02-input-audit.md` section 8 and `03-output-audit.md` section 8 still applies.

## Discoveries while building the suite (worth knowing)

* **Boot order hazard (F-17/O-09).** The stock Forward script's `OnInit` calls `KL.init()`, which rebuilds the DAW
  script's `_mk2`/`_processor` (module globals of the shared entry module). If FL initialises the DAW script first, the
  rebuilt display has no active page: the LCD ends blank (`(' ', ' ')`) and only ephemeral pages ever show. With the
  Forward script first everything is fine. Which order FL uses is unverified, so `ScriptSet.boot(order=)` exists;
  characterization tests use Forward-first, the `tuned_fix` test uses DAW-first. A fix: make `init()` idempotent for
  the Forward caller.
* Fuzz over both hypotheses reproduces every exception site from the audits and adds the empty-rack case (index 0 of an
  empty Channel Rack) and `getCurrentStepParam == -1`.

## Review round 1 tests

`tests/test_review_fix_gate.py` (minimal device-call profile, deferral, `isMidiOutAssigned` opt-in, wiring lines),
`test_review_fix_log.py` (KLTLog folder creation, fallback paths, back-off), `test_review_fix_paint.py` (paint without an
`OnRefresh`, keep-alive cycle and rate, settle repaints), `test_review_fix_unmapped.py` (unmapped events per port). They are
tuned-only. `tests/conftest.py` gives every test a private temp folder (`tempfile.tempdir`), because KLTLog now falls back to
`<temp>/klt.log` when its own path is unusable and a test that breaks the path on purpose must not write into the real one.
`tests/test_review_acceptance_*.py` (the reviewers' files): the strict xfails of the fixed findings became plain asserts
(RA-01, RA-03 folder half, RA-04, RA-04b, RA-06, RA-10, RA-10b); RA-02, RA-03 reload half, RA-05, RA-07 and RA-09 are still
strict xfails.

## Adding to the suite

* a new control/feature -> a characterization test using `rig` (`tests/test_input_mapping.py` is the pattern);
* a new fix -> a `@pytest.mark.tuned_fix("<finding id>")` test that FAILS on stock (`--stock` must show it xfail) and states
  in its docstring what the stock code did;
* a hardware-dependent switch -> a `KLTConfig` switch (default = the safest behaviour), `host.set_config(SWITCH=...)` in
  the test, and a test per value;
* never assert on a SysEx sequence where a device-state assertion (`host.device_model()`, LED/LCD after `rig.settle()`)
  says what matters: de-duplication and rate limiting legitimately change the sequence.
