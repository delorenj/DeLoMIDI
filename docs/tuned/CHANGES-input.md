# Input side of the tuned KeyLab mkII scripts: what changed, why, how to switch it, how it is tested

Scope: everything the keyboard sends TO FL Studio (buttons, faders, encoders, jog, pads, the keyboard port's wheels and
Analog Lab CC forwarding). Findings are the ids of `docs/analysis/02-input-audit.md` (F-xx). Output side (LEDs, LCD,
lifecycle): `CHANGES-output.md`. Nothing here was run on FL 26.1.6 or on the keyboard (host `tom` is offline): every claim
is a claim about the strict simulator in `tests/flsim/`, see `TESTING.md` for what it does not model.

Files owned: `KLTProcess.py`, `KLTNavigation.py`, `KLTPlugin.py`, `KLTSeqParam.py`, `KLTCrossKeyboard.py`, `KLTVCOL.py`,
`device_ForwardCCsPort10KeyLabMk2Tuned.py`, and the `--- input side` section of `KLTConfig.py`. Every change against
Arturia's file carries a `# KLT <finding-id>: why` comment (checked by `tests/test_hygiene.py`).

## Design principles applied

1. **No FL API call at import time, none in the Forward script's `OnInit`.** `OnInit` only writes a line to `klt.log`.
2. **The input side never reads `midiId` / `midiChan`.** Everything is derived from `status` / `data1` / `data2`, so it works
   whichever of H1 (FL fills `midiId` in `OnMidiIn`) or H2 (it reads 0 there) is true. The PROBE lines in `klt.log` record
   which one it is, per callback and per port, as diagnostics only.
3. **Nothing raises into FL.** `ProcessEvent` and every Forward callback catch `Exception` (never `FLCrash`, which is a
   `BaseException` in the simulator) and put the traceback in `klt.log`; every `device.*` call (`forwardMIDICC`,
   `processMIDICC`) is inside try/except. They are deliberately **not** gated on `device.isAssigned()`: that query is
   about the MIDI *output* (the crash hypothesis), forwarding to plugins is input-side and must keep working for an
   input-only script assignment. Nothing on the input side ever calls `device.midiOutSysex`/`midiOutMsg`
   (`test_no_input_event_needs_a_midi_output_or_touches_one_when_none_is_assigned`).
4. **Unknown hardware facts are switches whose default is the safest behaviour, and the run logs what it saw.**
5. **A control Arturia documents keeps working** (the guide's tables 2.1-2.11 are pinned by `test_input_mapping.py`).

## Finding -> change -> switch -> test

"tf" = `@pytest.mark.tuned_fix` (fails on the stock scripts by design, xfail strict with `--stock`).

| Finding | Change | Switch (`KLTConfig`, default) | Tests |
|---|---|---|---|
| **F-01** (high) Forward script ran the full processor from `OnMidiIn` | The Forward script's default path is raw `status/data1/data2` filtering in `OnMidiIn`: V Collection CC + pitch-bend forwarding, pads, CC1/28/29. Keybed traffic makes no FL call at all. The DAW command processor on the keyboard port is opt-in and runs from `OnMidiMsg`, for chosen kinds only. `ProcessEvent` dispatches on the raw status, so H1/H2 cannot matter. Full PROBE/RAW logging (below) | `FORWARD_USE_PROCESSOR` (False), `FORWARD_PROCESSOR_KINDS` (`('cc',)`; `'note'` is the H1 footgun), `FORWARD_PADS` (True), `FORWARD_PLUGIN_CCS` (True), `FORWARD_TARGET_PORT` (10), `FORWARD_MODE` (2), `PROBE_MIDI_FIELDS` (True), `PROBE_SAMPLES_PER_KIND` (3), shared `LOG_RAW_EVENTS` (False) | tf: `test_forward.py` (keybed/held keys under H1), `test_input_forward.py` (keybed, pads, CCs, processor path, fault injection), `test_input_hardening.py::test_the_processor_dispatches_on_the_raw_status_not_on_midiid`, `test_a_random_sweep_of_input_events...`; `test_input_probe.py` |
| **F-02** (high) Analog Lab CC handlers bound with the wrong signature | `_plugin_dispatcher`, `OnPluginEvent`'s table and the unreachable `status 176` entry are gone. `handle_keyboard_cc()` (raw fields): CC28/29 = previous/next preset of the focused plugin (press only), CC1 = mod wheel -> the plugin database row, absolute (stock treated its value as a relative tick count, and in mixer mode computed track -14). The 17 Analog Lab CCs are logged as unmapped and passed to FL. Optional translation of them into the database (knob i -> encoder i, fader j -> fader j, absolute). LCD label check `clef != 1` (stock tested the pitch-bend LSB) | `ANALOG_LAB_CC_TO_PLUGIN_DB` (False: a guess, needs the hardware) | tf: `test_forward.py::test_analog_lab_ccs_never_raise_on_the_keyboard_port`, `::test_mod_wheel_never_reaches_a_mixer_track_pan_with_a_negative_index`, `test_input_forward.py` (17 CCs x 3 plugins, mod wheel absolute, translation table, V Collection precedence), `test_fuzz.py` |
| **F-03** (high) unmapped events swallowed silently | `_consume()`: an event is consumed only if a handler exists for it (a mapped control's ignored phase stays consumed). Unmapped ones are logged once per distinct (port, status, data1), again at x10/x100/x1000, with what really happens to them (`swallowed` / `passed to FL`). What happens is **per port since review round 1 (RA-01, RA-04)**: on the DAW port `PASS_UNMAPPED` decides, default **False** = stock (swallowed; a panel button nobody claims must not be a note on the selected channel); on the keyboard port (the Forward script's processor path) an unmapped event is never swallowed. A note-off is never swallowed | `PASS_UNMAPPED` (**False**, DAW port only), `LOG_UNMAPPED` (True), `LOG_UNMAPPED_MAX_KEYS` (300) | tf: `test_input_unmapped.py` (ids 32..112, 9 CCs, pitch bend ch10+, with `PASS_UNMAPPED=True`; log once/x10/x100, bounded, off, `PASS_UNMAPPED=False` = stock); `test_review_fix_unmapped.py` (the default, per port) |
| **F-04** (high) song-mode pad release ignored, `EDIT_MODE` stuck | The release is always routed in Sequencer mode (`release_bit`); the step toggle stays pattern-mode only. Held-pad state is cleared on every Save toggle, and a release whose press was forgotten does nothing | - | tf: `test_pads.py` (2), `test_input_hardening.py` (song-mode state, forgotten press) |
| **F-05** (high) pad velocity clobbered with 144/128 | Both `event.data2 = ...` lines deleted; only `data1` is remapped | - | tf: `test_pads.py::test_drum_pad_velocity_is_preserved`, `::test_a_range_checked_event_does_not_raise_on_pads`, `test_fuzz.py`, `test_input_forward.py` (keyboard port) |
| **F-06** `FPC_MAP.get()` -> `None` | Notes outside 36..51 are left alone in drum mode and are not step buttons in Sequencer mode (not consumed, no `processMIDICC`); `hold_bit`/`release_bit` range-guarded | - | tf: `test_pads.py` (2), `test_input_hardening.py::test_notes_outside_the_pad_range_are_not_step_buttons`, `test_fuzz.py` |
| **F-07** FPC remap for every instrument | Remap only when the selected channel's plugin is FPC (`plugins.getPluginName`, focused plugin window as fallback) | `PADS_REMAP_ONLY_FOR_FPC` (True; False = stock) | tf: `test_pads.py`, `test_input_forward.py`; switch and name matching in `test_input_hardening.py` |
| **F-08** `handled` leaked by helpers | Helpers are pure (`AKLmk2.SetVolumeTrack(track, value)` / `SetPanTrack(track, ticks)`, `KLTPlugin.Plugin` no longer assigns `handled`); the event is never rewritten into a CC-shaped body; `KLTNavigation.VolumeMixerRefresh/PanMixerRefresh` take the track (the master showed as "Pan - 9") | - | tf: `test_input_fixes.py` (2), `test_input_hardening.py` (event not rewritten, master LCD) |
| **F-09** mixer track 126..128 | `AKLmk2.track_ok()` guards every mixer index the input side addresses (0..125 and `< trackCount()`), for pan, volume, Select, Solo, Mute, arm and a channel that routes to no track (`getTargetFxTrack() == -1`); `clamp_banks()` runs before every event | - | tf: `test_banking.py` (2), `test_input_hardening.py` (2), `test_fuzz.py` |
| **F-10** relative encoders | `AKLmk2.rel_ticks()`: sign-magnitude decode by magnitude (0 and 64 = none), capped per event. Jog steps that many times (any value, browser popup too); pan = `ticks/20`, clamped to [-1, 1]; plugin knobs move the live value by `ticks * 2/127` (no `int()` re-seed), clamped to [0, 1]; step edit per tick. Mod wheel/faders stay absolute. A database parameter beyond `plugins.getParamCount` is skipped and logged once | `ENCODER_USE_TICKS` (True; False = stock +-1 per event, jog only exact 1/65), `ENCODER_MAX_TICKS` (4) | tf: `test_input_hardening.py` (jog rows, browser, pan, mixer pan, plugin knob, stale parameter); pinned: `test_input_mapping.py`, `test_plugin_db.py` |
| **F-11** step edit | `STEP_PARAMS` table (documented ranges/defaults): each held step changes relative to its own value; pitch clockwise = up; MOD Y not doubled; fine pitch reaches 240; **Shift (encoder 8, guide p.15 Fig.31) = step parameter 7, 0..24 ticks (PPQN 96)**; graph editor shown/updated once per event; empty `INDEX_PRESSED` and a failing `getCurrentStepParam` (-1) handled | - | tf: `test_pads.py` (3), `test_input_hardening.py` (Shift, per-step, fine pitch, graph editor, -1), `test_fuzz.py` |
| **F-12** desync | Faders/encoders/banks follow the focused window (`sync_mode_from_focus()`: Mixer focus -> mixer mode, Channel Rack focus -> rack mode; plugin windows/Browser/Playlist leave it); bank offsets clamped to the live channel/track count before each event; `RECT_OFFSET` bounded 0..31; `reset_state()` | `MODE_FOLLOWS_FOCUS` (True) | tf: `test_input_fixes.py::test_mixer_mode_follows...`, `test_input_hardening.py` (mouse focus both ways, stale bank, RECT bound, reset), `test_lifecycle.py` (output side) |
| **F-13** global vs group-relative channel index | `AKLmk2.sel_channel()` = `channels.selectedChannel()` (group-relative, like every `channels.*` default) and -1 for an empty rack, used everywhere `channelNumber()` was; **the same switch as the output side**. The simulator has no groups, so the test asserts the call, not the outcome | `GROUP_RELATIVE_CHANNELS` (output section, True) | tf: `test_input_hardening.py::test_controls_ask_for_the_group_relative_selection...` (10 controls), `test_input_forward.py` (wheel, empty rack) |
| **F-14** `_hideAll` = 300 calls per jog tick | Closes the selected channel's editor plus the ones this script opened (`_editors`); at most 3 `showEditor` per call. Behaviour change: an editor the user opened for another channel by mouse is no longer closed by the jog | - | tf: `test_input_fixes.py`, `test_input_hardening.py` (2) |
| **F-15** Forward hot path and wheel | No FL call for keybed traffic (V Collection test only for CC, set lookup); wheel uses all 14 bits as a fraction of the channel's own pitch range (`setChannelPitch(..., mode 0)`); an Arturia instrument is recognised by channel name **or** hosted plugin | - | tf: `test_input_forward.py` (3) |
| **F-16** unmapped slots | `-1`/unknown row decided before any `plugins.*` call; parameter must exist. The database and its known duplicate parameters are unchanged (pinned by `test_plugin_db.py`: the intended parameters are unknown) | - | tf: `test_input_fixes.py`, `test_fuzz.py` |
| **F-17** second processor / shared state | The Forward script no longer calls `KL.init()` (it replaced the DAW script's display and processor objects); `KLTProcess` is imported lazily by it; the processor path reads `device_KeyLabmk2Tuned._processor` with `getattr` and skips (log once) if the DAW script has not created it. PROBE-VERDICT lines carry an interpreter id: equal ids in the DAW-port and keyboard-port lines = one shared interpreter | - | tf: `test_input_forward.py::test_the_forward_oninit_does_not_replace...`, `test_lifecycle.py` (output side); `test_input_probe.py` |
| **F-18** `ui.cut()` | Documented behaviour kept; can be turned off | `CUT_ENABLED` (True) | `test_input_hardening.py::test_the_cut_button_can_be_disabled` |
| **F-21** pattern buttons | Previous stops at pattern 1; Next never passes `patterns.patternMax()`; creating a pattern with Next on the last one stays (stock) | `PATTERN_NEXT_CREATES` (True) | tf: `test_input_fixes.py`, `test_input_hardening.py` |
| **F-22** Undo value | `globalTransport(FPT_Undo, 2, event.pmeFlags)`: Image-Line's MackieCU passes `int(pressed) * 2` (stock passed 20) | - | tf: `test_input_hardening.py::test_undo_uses_the_press_value...` |
| **F-23** releases | A note-off (0x80) is a release whatever its velocity, and routed; `<<`/`>>` remember that their press started a scrub, so the release stops it even if Save was toggled meanwhile; a press is any non-zero velocity (stock: exactly 127 for the bar offset); a pad note-on with velocity 0 is a release | `NOTE_OFF_IS_RELEASE` (True; False = stock: note-offs not routed), `PADS_NOTE_ON_ZERO_IS_RELEASE` (True) | tf: `test_input_fixes.py` (2), `test_input_hardening.py` (3); switch test |
| **F-27** `processMIDICC(note)` | Behaviour kept (it lets FL's link system see a Sequencer-mode pad), call guarded | - | fault injection: `test_no_forward_callback_raises...`, `test_no_exception_escapes_the_processor...` |
| G12 | `PORT_MIDICC_ANALOGLAB` (unused, 10) replaced by `FORWARD_TARGET_PORT` | | `test_the_forward_target_port_and_mode_are_switches` |

Other guard rails (no finding id): `ProcessEvent` never raises; a mapped control whose handler failed stays consumed and
its traceback lands in `klt.log` (`test_a_caught_handler_failure_is_logged...`); the FL API surface used stays inside the
modelled set (`test_api_usage.py`); seeded sweeps of 2,500 events x 3 seeds x H1/H2 (`test_a_random_sweep...`) also fail on
exceptions a handler *caught* (klt.log `EXC in`) and on every violation kind the strict fakes know.

### Findings not implemented, and why

| Finding | Why |
|---|---|
| F-19 `FakeMIDImsg` (`FPT_Punch` per event) | Vendor pattern (also Arturia's mk3); purpose unknown, no test can tell what removing it does in FL. Kept as is. |
| F-20 `pmeFlags` gating | Would silence every control if a real event carries other flags than the simulator's; unverified, upside small. The catch-all in `ProcessEvent` is the safety net instead. |
| F-24 jog yanks focus to the Channel Rack from Playlist/Piano roll | The guide is silent; the first tick acting as "back to the rack" may be intended. Kept. |
| F-25, F-26 | Output side. |
| Section 7 gaps (fader pickup, automation recording from faders, generic plugin fallback, Solo/Mute + Select, `setLoopMode`, undo hint on the LCD) | Design work, not defects; each needs a decision or the hardware. `mixer.automateEvent` and pickup modes are the pointers in the audit. |
| Plugin database duplicates (FL Keys knobs 6/7, DX10, Harmless) | The intended parameter is unknown without `plugins.getParamName` dumps from `tom`. |

## Every input-side switch

All live in `KLTConfig.py` under `--- input side ---` (plus `GROUP_RELATIVE_CHANNELS` in the output section, shared). A
switch is read at event time, so `host.set_config(...)` in a test or a Reload in FL picks it up.

| Switch | Default | Stock-equivalent | Meaning |
|---|---|---|---|
| `PASS_UNMAPPED` | False | False | **DAW port only.** False = an unmapped ch1 note/CC/fader event is swallowed like stock (a panel button nobody claims - Next/Previous with Bank off, Category, Preset, the 9th Select button, fader touch, encoder pushes - would otherwise be a note on the selected channel). True = it goes on to FL (`UNMAPPED` lines then name what FL received). The keyboard port never swallows an unmapped event, whatever this says |
| `LOG_UNMAPPED`, `LOG_UNMAPPED_MAX_KEYS` | True, 300 | - | log each distinct unmapped id once |
| `PROBE_MIDI_FIELDS`, `PROBE_SAMPLES_PER_KIND` | True, 3 | - | PROBE / PROBE-VERDICT lines |
| `FORWARD_USE_PROCESSOR`, `FORWARD_PROCESSOR_KINDS` | False, `('cc',)` | True for everything | DAW command table on the keyboard port |
| `FORWARD_PADS` | True | (True) | pads on the keyboard port |
| `FORWARD_PLUGIN_CCS` | True | (H2 only, crashed) | mod wheel / preset buttons |
| `ANALOG_LAB_CC_TO_PLUGIN_DB` | False | - | Analog Lab CC translation |
| `FORWARD_TARGET_PORT`, `FORWARD_MODE` | 10, 2 | 10, 2 | `forwardMIDICC` target |
| `PADS_REMAP_ONLY_FOR_FPC` | True | False | FPC layout remap |
| `PADS_NOTE_ON_ZERO_IS_RELEASE` | True | False | pad running-status release |
| `NOTE_OFF_IS_RELEASE` | True | False | 0x80 = release |
| `ENCODER_USE_TICKS`, `ENCODER_MAX_TICKS` | True, 4 | False | relative decode |
| `MODE_FOLLOWS_FOCUS` | True | False | mixer/rack mode follows real focus |
| `PATTERN_NEXT_CREATES` | True | True | Next on the last pattern creates one |
| `CUT_ENABLED` | True | True | the "Off" button |

## How to read `klt.log` after the first run on `tom` (what settles the open questions)

Assign the DAW script to the DAW port and the Forward script to the keyboard port (guide p.4-5, ports 0 and 1), touch
one key, one pad, one fader, one encoder, one button, the jog and both wheels, then open `klt.log`:

| Line | Settles |
|---|---|
| `PROBE-VERDICT Forward.OnMidiIn port=1: midiId is POPULATED (H1)` / `NOT populated, reads 0x00 (H2)` | F-01 H1 vs H2. Nothing in the scripts depends on it; it only says whether stock's Forward script acted on keybed keys. |
| `PROBE-VERDICT DAW.OnMidiMsg port=0 ...` and `Forward.OnMidiMsg port=1 ...` | expected POPULATED (Image-Line's MackieCU relies on it) |
| `[interpreter X, module Y]` in the two ports' verdicts | equal `X` = one shared Python interpreter (F-17). Different = the Forward script's copy of `SEQ_MODE`, banks, held pads is separate from the DAW script's (pads on the keyboard port then always behave as in drum mode) |
| `PROBE ... pad ... midiChan=9 (want 9)`, `PROBE ... pitch-bend ... midiChan=3 (want 3)` | `midiChan` is decisive on channels 2..16; on channel 1 the line says "ambiguous" |
| `PROBE <cb> port=N note-on/note-off/cc/pitch-bend ...` per callback and port | which port carries buttons, pads, faders, encoders, jog (guide open question 1); whether releases are note-on velocity 0 or note-off; the real encoder values (jog: 1/65 only, or 2..63/66..127) |
| `UNMAPPED <where> port=N <kind> st=0x.. d1=.. d2=..` | every id the scripts do not know: the real DAW preset's extra buttons (encoder pushes, fader touch, Bank), the 17 Analog Lab CCs, stray CCs. Decide `PASS_UNMAPPED` and whether to add handlers |
| `Forward: the DAW script has not created its processor yet` | processor path enabled but the DAW script is not initialised (wrong port assignment, or init order) |
| `EXC in ...` | a caught exception with traceback: a bug, please keep the file |
| `plugin database: X parameter N does not exist on this plugin` | a stale database index (F-16 / audit 5.3) |

Set `LOG_RAW_EVENTS = True` for a full capture of everything that reaches the input side (both ports).

## Behavioural proof: diffreplay

`diffreplay` compares two folders on one seeded stream. Stock against tuned mixes the output side's changes in, so the
input side was isolated: the tuned folder with the seven input files put back to their baseline (commit `3d493d8`)
against the tuned folder.

```bash
BASE=$(mktemp -d); cp "scripts/KeyLab mkII tuned/"*.py $BASE/
for f in KLTProcess KLTNavigation KLTPlugin KLTSeqParam KLTCrossKeyboard KLTVCOL device_ForwardCCsPort10KeyLabMk2Tuned; do
  git show 3d493d8:"scripts/KeyLab mkII tuned/$f.py" > $BASE/$f.py; done
uv run --python 3.12 python -m tests.flsim.diffreplay $BASE "scripts/KeyLab mkII tuned" --events 20000 --seed 1 --show 400
uv run --python 3.12 python -m tests.flsim.diffreplay <stock dir> "scripts/KeyLab mkII tuned" --events 20000 --seed 1 --fail-on-regression
```

Result (20,000 events, seed 1, 21,946 ops): escaping exceptions 261 -> 0 (all `Dispatch.Dispatch` TypeError from the
Analog Lab dispatcher, `OnDrumSeqEvent`, `ReleaseBit`), FLCrash 0 -> 0, no `REGRESSION` or "both raise" group, violation
kinds only disappear (`event-range` 1,393 pad ops, `index`, `value`, `param-index`), never appear. The full stock-vs-tuned
run with `--fail-on-regression` exits 0 for seeds 1 and 7, both boot orders and the unassigned-output replay.

Every differing group of the isolated run maps to a finding:

| Group (op class) | What differs | Finding |
|---|---|---|
| ids nobody maps (note-on ch1, 799 ops) | `handled True -> False` | F-03 (until review round 1: now swallowed like stock, the group is gone) |
| other CCs on the DAW port (343) | `handled True -> False` | F-03 (as above) |
| pitch bend on ch10..16 (24) | `handled True -> False` | F-03 (as above) |
| note-off 0x80 of mapped ids (~250 `handled False -> True`, release handlers firing) | routed and consumed | F-23 |
| pads (1,393 ops) | `data2` no longer 144/128, `event-range` violations gone; remap only for FPC | F-05, F-07 |
| pads (83 `True -> False`, 68 `False -> True`, `processMIDICC`, `setGridBit` differences) | notes outside 36..51 pass; song-mode release consumed; a release without a held press does not toggle | F-06, F-04 |
| faders/encoders `handled False -> True` (489 + 373) | mixer and plugin controls consumed | F-08 |
| fader/encoder call sets (`setTrackVolume` vs none, `setTrackPan`, `setStepParameterByIndex`, `updateGraphEditor`) | mode follows focus; stuck `EDIT_MODE` of stock gone; per-event graph editor; track guard; ticks | F-12, F-04, F-11, F-09, F-10 |
| encoder 8 (`setStepParameterByIndex(..., 7, ...)`, ~24 ops) | Shift | F-11 |
| jog CC60 (~170 ops) | values 2..63 / 66..127 now move the selection by the tick count; `showEditor` per tick 300 -> 1 | F-10, F-14 |
| Save / Bank / Select / jog push (`showEditor` x N removed) | editors closed without a 300-call loop | F-14 |
| Undo (21) | `globalTransport(20, 20, ...)` -> `(20, 2, ...)` | F-22 |
| Previous pattern (37) | `jumpToPattern(0)` and its `index` violation gone | F-21 |
| keyboard port CC (211 exceptions, 211 `handled True -> False`) | Analog Lab CCs no longer raise/swallow | F-02 |
| keyboard port keybed notes under H1 (~100 ops of actions removed) | transport/window/pattern/mute actions gone | F-01 |
| keyboard port pitch bend (439 argument changes, 28 without a bend) | 14-bit, mode 0; empty rack | F-15, F-13 |
| non-MIDI ops (idle, refresh, sysex...) | LEDs follow the diverged FL state | consequence of the above |

Because one differing op changes FL state and the runs then diverge, the first divergence of each of the 80 episodes was
checked separately (78 diverge; each is one of: jog ticks/editors F-10/F-14, keybed notes under H1 F-01, note-off
releases F-23, mode following focus F-12, Save clearing pad state F-04, lone pad release F-04/F-06). None is unexplained.

## What the output side can use (and must know)

* `KLTProcess.sync_mode_from_focus()` and `KLTCrossKeyboard.clamp_banks()`: cheap, exception-safe; call them from
  `OnRefresh` so LEDs follow a mouse click on the Mixer/Channel Rack before the next input event. Otherwise the input side
  resyncs on every event (LEDs lag until then). `KLTProcess.reset_state()` returns modes, banks, held pads and the step
  window to power-on (for `RESET_HELPER_STATE_ON_INIT`); the module globals it resets (`SEQ_MODE`, `MIXER_MODE`,
  `RECT_OFFSET`, `EDIT_MODE`, `STATE_MATRIX`, `INDEX_PRESSED`, `AKLmk2.MX_OFFSET/CH_OFFSET`) keep their names.
* `KeyLabMidiProcessor.ProcessEvent(event, where='DAW.OnMidiMsg')` still takes one argument from the entry script; it never
  raises and needs no `midiId`.
* The Forward script no longer calls `device_KeyLabmk2Tuned.init()` and only touches the entry module in the opt-in
  processor path (`getattr(module, '_processor', None)`). Keep the module-level name `_processor`.

## Risks and things only the hardware can settle

* Which DAW preset the keyboard is in, which port carries which control, real note numbers, release form, encoder value
  encoding, and whether `midiId` is populated in `OnMidiIn` are all UNVERIFIED. The scripts log them; none is assumed
  beyond Arturia's own contract (docs/analysis/02 section 2).
* `PASS_UNMAPPED = False` (the default since review round 1) means an id the DAW port sends that the scripts do not know is dropped, as in
  stock; the `UNMAPPED` lines in `klt.log` name each one, which is how a real button gets a handler later. If the DAW script is
  wired to the keyboard port by mistake (wrong FL settings), unmapped keybed notes on channel 1 are swallowed too: the wiring
  table in `CHANGES-output.md` section 8 is the fix.
* `MODE_FOLLOWS_FOCUS`: if FL does not report `ui.getFocused(widMixer)` right after `ui.setFocused(widMixer)`, the Bank
  button would toggle back on the next event; set it False then.
* The pitch wheel is forwarded to the plugin port AND applied to the channel pitch (stock did both); whether that double
  bends a native instrument is unverified and unchanged.
* Nothing here has run in FL 26.1.6; `plugins.getParamCount`, `patterns.patternMax`, `channels.selectedChannel`,
  `plugins.getPluginName` are new input-side calls (all in the API stubs and modelled by `tests/flsim`).

## Review round 1 (guide acceptance): unmapped events per port

Applied from the first adversarial review (details, tests and the other eight findings: `CHANGES-output.md` section 8).

| review id | severity | what was wrong | decision | test(s) |
|---|---|---|---|---|
| **RA-01** | medium | `PASS_UNMAPPED = True` (default) left 77 of the 128 channel-1 note ids on the DAW port to FL, where each is a note on the selected channel (audible, recorded when record is armed). Panel buttons without a handler: Next/Previous with the Bank button off, Category, Preset, the 9th Select button, possibly Bank itself (guide p.12, manual 4.6); stock swallowed them all | Default **`PASS_UNMAPPED = False`** on the DAW port = stock behaviour. The finding's "better" split (swallow notes, pass CCs) was **not** taken: which unmapped CCs the DAW preset sends is UNVERIFIED, stock swallowed all of them without anyone noticing, and a phantom mod wheel/volume/sustain on the instrument is as real as a phantom note; the log names every id, so the hardware run can decide per id. Claiming notes 48/49 as "bank +-1" (the manual's Bank-off behaviour, MCU ids) was not done either: the ids are unverified | `test_review_fix_unmapped.py`; the reviewer's `test_c_ra01_*` (plain asserts now), `test_b_the_default_swallows_every_stray_on_the_daw_port`, `test_b_no_channel_1_note_id_on_the_daw_port_is_left_to_fl_by_default` |
| **RA-04** | low | one global for two ports with opposite needs: the natural first-session sequence (`PASS_UNMAPPED = False` for the phantom notes, then `FORWARD_USE_PROCESSOR = True`) swallowed sustain, expression, volume and the mod wheel on the keyboard port, and the `UNMAPPED` line said `swallowed` for a keyboard-port CC the Forward script never swallows | The Forward script never swallows an unmapped event: `_consume` knows which port it serves (`ProcessEvent(..., where='Forward.OnMidiMsg')`) and hard-passes there. The `UNMAPPED` line prints the real disposition (`note_unmapped(..., swallowed=)`). The switch keeps its name (`PASS_UNMAPPED`, documented as DAW-port only) instead of the finding's `PASS_UNMAPPED_DAW`: with the keyboard port never consulting it there is nothing left to disambiguate, and the existing tests and docs keep working | `test_review_fix_unmapped.py`; the reviewer's `test_c_ra04*`, `test_c_ra06*` (plain asserts now) |

`diffreplay` (stock vs tuned, 20,000 events, seed 1): ops whose `handled` flag differs from stock 4,054 -> 2,888 (the F-03 groups are gone);
no regression, no `FLCrash`, no escaping exception.
