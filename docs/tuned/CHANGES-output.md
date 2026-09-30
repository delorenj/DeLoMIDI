# Tuned KeyLab mkII scripts: output side (LEDs, LCD, init/deinit, lifecycle)

What changed against Arturia's stock scripts on the side that talks **to** the keyboard, why, which `KLTConfig.py` switch
controls it, and which test proves it. Finding ids (`O-xx`) are from `docs/analysis/03-output-audit.md`; `F-xx` from
`02-input-audit.md`. Files owned by this side: `device_KeyLabmk2Tuned.py`, `KLTDispatch.py`, `KLTDisplay.py`, `KLTPages.py`,
`KLTReturn.py` and the "output side" section of `KLTConfig.py`. Every changed line carries a `# KLT <id>: why` comment.

**Nothing here has run in FL 26.1.6 or against the keyboard.** Everything is verified in the flsim simulator
(`docs/tuned/TESTING.md`); the tom crash and every hardware-dependent choice below remain hypotheses until tom is back.

## 1. Design in one page

```
FL callbacks (all wrapped in KLTLog.guarded, routines isolated with _step)
   OnInit  OnIdle  OnRefresh  OnUpdateBeatIndicator  OnSysEx  OnDeInit  OnMidiMsg  OnDoFullRefresh  OnProjectLoad
        |
   KLTReturn (LED routines, byte-identical frames)     KLTDisplay/KLTPages (LCD text, sanitised, scroll)
        |                                                   |
        +--------------------- send_to_device(payload) -----+
                                     |
                              KLTDispatch.OutputLayer  (the ONLY caller of device.midiOutSysex)
        gate      device.isAssigned() [then device.isMidiOutAssigned()] asked before every send; unanswerable = no
        shadow    what the keyboard is believed to show, per LED id / LCD; an unchanged frame is never re-sent
        pending   newest wanted frame per LED id / LCD, latest wins; `with batch():` = final state per callback only
        budgets   hard cap per sliding second, cap per tick (20 ms window), LCD minimum gap; a deferred frame is sent later
        keep-alive one already-delivered frame re-sent per second when idle (LCD every 10 s): a keyboard that lost its state heals
```

* **OnInit** neither sleeps nor sends a burst: it logs the banner, resets state, builds the objects, sets the main page,
  starts the (non-blocking) splash and *arms* the staged init. It sends the welcome LCD frame and nothing else.
* **Staged init** (`KLTReturn.InitStep`, advanced once per `OnIdle` tick): wait for the output -> optional pad animation
  (`INIT_ANIMATION`, `INIT_FRAMES_PER_TICK` frames per tick) -> release the LEDs, which then paint what FL state says. LED frames
  requested while it runs are held (latest wins); the hold auto-releases if `OnIdle` stops advancing it for `OUT_HOLD_TIMEOUT_S`.
  With the device absent it just waits, sends nothing and blocks nothing; when the output appears it runs and repaints.
* **OnIdle** (about 50 Hz) delivers pending frames, notices the output appearing, runs the LCD refresh, and polls the LEDs at
  `OUT_LED_PASS_S` (100 ms): only changes reach the wire. Pads, Play/Stop/Record LEDs still follow `OnRefresh`/beat callbacks
  as in stock, plus a repaint of the pads when the pad layout changes (Drum/Sequencer, bar, loop mode).
* **OnDeInit** sends the goodbye LCD frame and stock's deinit frame through the same gate, then **closes** the output layer:
  a late `OnIdle`/`OnRefresh` can never touch a port FL is tearing down. The next `OnInit` reopens it.

Measured in the simulator (same scripted sessions, `docs/tuned/TESTING.md` scenarios; virtual time at FL's documented 50 Hz idle):

| | stock | tuned |
|---|---|---|
| SysEx/s, Channel Rack, FL state changing every 2 s | 1,209 avg, 1,220 worst (15.9 KB/s) | 1.8 avg, 4 worst (27 B/s) |
| SysEx/s, Mixer mode | 1,209 / 1,220 | 1.7 / 4 |
| SysEx/s, Sequencer mode playing at 120 bpm | 1,338 / 1,360 (17.8 KB/s) | 20 / 35 (294 B/s) |
| SysEx/s, nothing changes | 1,200 | 1.1 (the keep-alive) |
| `OnInit` | 261 frames incl. `OnRefresh`, `time.sleep` 2.92 s on FL's main thread | 1 frame, no sleep |
| time until the LEDs show FL's state (Select buttons, Solo/Mute, transport) | 2.92 s, after the blocking `OnInit` | 0.12 s (6 ticks of at most 8 frames) |
| hard limits | none | 100 frames in any second, 8 in any 20 ms tick, LCD frames 35 ms apart |

## 2. Findings -> change -> switch -> test

Tests are in `tests/test_output_gate.py` (gate), `_budget.py` (economy), `_display.py` (LCD), `_lifecycle.py` (callbacks,
init, splash), `_leds.py` (LED semantics, byte identity with stock), `_fuzz.py` (non-default switch sets), `_switches.py`
(housekeeping); `test_lifecycle.py`, `test_idle_budget.py` and `test_fuzz.py` are the lead's `tuned_fix` tests.

| finding | change | switch(es) | test(s) |
|---|---|---|---|
| **O-01** high: no `isAssigned` guard; unassigned output = dark keyboard, possibly the FL 26.1.6 crash | `KLTDispatch.OutputLayer` is the only caller of `device.midiOutSysex`. Before a send it asks `device.isAssigned()`, then `device.isMidiOutAssigned()` (only if the first said yes); an exception or a "no" from either means not assigned (fail safe); a missing `isMidiOutAssigned` falls back to `isAssigned`. "No" is remembered 0.5 s and logged **once** (klt.log + FL Script output) with the FL menu path to fix it. While unassigned the only device call is `isAssigned`. Nothing is sent after `OnDeInit`. 5 failing `midiOutSysex` in a row pause output for 5 s. No device call at import time. The output appearing later triggers a full repaint | `OUT_ENABLED`, `OUT_REQUIRE_MIDIOUT_ASSIGNED`, `OUT_UNASSIGNED_RECHECK_S`, `OUT_FAIL_BACKOFF_S` | gate: `no_frame_and_no_crash_when_no_output_is_assigned[crash,noop]`, `only_device_call...isassigned`, `reported_once`, `ismidioutassigned_*`, `a_query_that_raises`, `assigning_the_output_later`, `unassigning...at_run_time`, `failing_midioutsysex_backs_off`, `nothing_is_sent_after_ondeinit`; lifecycle `test_unassigned_output_is_never_written_to`, `..._checked_before_the_first_sysex`, fuzz FLCrash tests; `test_output_fuzz.py` |
| **O-02** high: 22-24 frames per idle tick, no shadow state | shadow state per LED id and LCD (send only changes); pending queue, latest wins; `with batch():` per callback (a pad repainted and then highlighted is sent once); LED routines polled every `OUT_LED_PASS_S`; hard per-second cap and per-tick cap; keep-alive of one known frame per `OUT_TRICKLE_S` (LCD per `OUT_LCD_KEEPALIVE_S`); counters logged every `OUT_STATS_LOG_S` | `OUT_MAX_SYSEX_PER_SEC`, `OUT_MAX_SYSEX_PER_TICK`, `OUT_TICK_S`, `OUT_LED_PASS_S`, `OUT_TRICKLE_S`, `OUT_LCD_KEEPALIVE_S`, `OUT_STATS_LOG_S` | budget: `per_second_cap_holds[20,60,100]`, `per_tick_cap_holds[1,4,8]`, `budgets_change_when_the_keyboard_is_told_never_what_it_ends_up_showing`, `quiet_idle_*`, `keep_alive_*`, `only_changed_leds_are_sent`, `change_that_reverts...`, `frames_of_one_callback_are_coalesced`, `polled_leds_are_evaluated_at_the_pass_interval`, `output_counters_*`; `test_idle_budget.py` (3 scenarios + quiet) |
| **O-03** high: strict-ASCII encode poisons the display | `ascii_line` in `SetLines` **before** anything is stored: accents fold (e-acute -> e), typographic punctuation maps, control characters and NUL become a space, the rest `?`; `_lcd_bytes` re-checks and clips to 16 printable bytes; `None`/bytes/numbers accepted; without `unicodedata` falls back to `?` | (none) | display: `ascii_line_returns_printable_ascii_for_anything`, `accents_fold...`, `lcd_bytes_never_exceed_16...`, `no_text_can_poison_the_display_state`, `every_lcd_frame_of_a_session_with_hostile_names...`; lifecycle `test_non_ascii_text_does_not_break_the_display[4]` |
| **O-04** medium: no exception isolation, `NameError` before init | `_mk2 = _processor = None` from import on; every FL callback wrapped in `KLTLog.guarded` (an AST test checks all `On*`); every routine inside a callback runs through `_step` (one failure logged once per 30 s + printed once, the rest still run); `init()` builds `_mk2` and `_processor` separately (a failing processor keeps LEDs/LCD alive); `Sync` fetches channel and pattern text separately, never passes an invalid index (empty rack -> `No channel`, selection outside the rack -> `No selection`, pattern 0 -> empty) and keeps the last good text when FL fails; `KLTPages` survives a page whose text cannot be produced | (none) | lifecycle: `every_on_callback...guarded`, `one_failing_fl_call_does_not_stop_the_other_leds[10]`, `persistent_failure_is_reported_once`, `processor_that_cannot_be_built...`, `display_objects_that_cannot_be_built...`; display: `main_page_*`, `failing_name_query_keeps_the_last_good_text`; leds: `empty_rack_*`; lead's `test_callbacks_before_oninit...`, `test_partial_init...` |
| **O-05** medium: LCD cache never invalidated | `KeyLabDisplay.Invalidate()`; called (with a shadow reset and a forced LED pass) on `OnInit`, the memory-switch SysEx, `OnDoFullRefresh`, `OnProjectLoad(>=100)` and when the output re-appears; keep-alive heals the rest | `OUT_TRICKLE_S`, `OUT_LCD_KEEPALIVE_S` | budget: `memory_switch_re_sends_every_led_and_the_lcd`, `full_refresh_request...`, `loaded_project_repaints...`, `keep_alive_re_sends...`; lead's `test_lcd_is_repainted_after_a_memory_switch` |
| **O-06** medium: no LCD rate limit | LCD frames at least `OUT_LCD_MIN_GAP_S` apart; a deferred frame stays pending (latest wins) so the final text always arrives | `OUT_LCD_MIN_GAP_S` | budget: `lcd_frames_keep_the_configured_gap...`, `unchanged_lcd_text_is_not_sent_again...`; lead's `test_lcd_frames_are_spaced...` |
| **O-07** medium: `OnRefresh` ignores flags, pads only follow `OnRefresh` | dedupe makes a repeated refresh free of SysEx (O-02). New: a change of pad layout (Drum/Sequencer mode, bar shown, loop mode) repaints the pads from `OnIdle` instead of relying on the fake Punch message reaching FL as an `OnRefresh`. Flag masking is implemented but **off by default** (what FL signals with `HW_Dirty_Mixer_Controls`/`HW_Dirty_ControlValues` is unverified; Mackie updates mixer LEDs on the former) | `REFRESH_IGNORE_NOISY_FLAGS` (default `False`) | budget: `noisy_refresh_flags_are_processed_by_default...`, `..._can_be_skipped`; lifecycle: `default_per_tick_cap...` (mode change repaint) |
| **O-08** medium: stale `CH_OFFSET`/modes survive Reload; `IndexError` every idle tick | LED code clamps the bank offset to the rack (`SelectedChannel` rewritten, same bytes, one FL query per slot); `OnInit` calls `KLTProcess.reset_state()` (input side) and resets `KLTReturn`'s globals and any known helper global; `OnProjectLoad`/`OnDoFullRefresh` added | `RESET_HELPER_STATE_ON_INIT` | leds: `stale_channel_bank...`, `stale_mixer_bank...`; lifecycle `oninit_resets_the_stale_state...`, `helper_reset_is_a_switch`, `reload_after_a_session...`; lead's `test_stale_bank_offset...` |
| **O-09 / F-17** medium: second `_mk2` built by the Forward script | `init(force=False)` creates only what is missing; only the DAW script's `OnInit` passes `force=True` | (none) | lifecycle `init_only_builds_what_is_missing...`, `second_init_from_another_script_does_not_blank_the_lcd`; lead's `test_daw_script_first_boot_order...`. Residual: with `FORWARD_USE_PROCESSOR=True` the Forward script drives the DAW processor and its LCD frames leave through the Forward script's own output (see 5) |
| **O-10** medium (unverified): pad LED rows may be flipped on 49/88 | `_pad_led(i)`: `0x70+i`, or the vertically flipped id when the switch is on. **Default = stock** until measured on hardware (checklist item 8 of the audit) | `PAD_LED_FLIP_ROWS` | leds: `pad_led_ids_are_stock_by_default`, `flipped_pad_rows_*` |
| **O-11** medium: port 10 advice | not code; the init banner logs a WARNING when the script reports port 10 (Analog Lab's port) | (none) | gate: `banner_warns_about_port_10` |
| **O-12** low: 2.92 s blocking init | the animation became a state machine advanced from `OnIdle`; level 0 (default) = none, 1 = 32-frame pad wipe, 2 = Arturia's 240 frames byte-identical; welcome splash without blocking: `KeyLab mkII` / FL title for `SPLASH_MS`, then `KeyLab mkII` / `tuned v0.1.0` for `SPLASH_TAG_MS` (the line is a callable, no timer), then the main page | `INIT_ANIMATION`, `INIT_FRAMES_PER_TICK`, `SPLASH_MS`, `SPLASH_TAG_MS`, `OUT_HOLD_TIMEOUT_S` | lifecycle: `stock_animation_is_a_switch_and_is_byte_identical`, `short_animation...`, `animation_frames_advance_a_few_per_tick...`, `leds_are_held_back_until...`, `init_that_never_gets_idle_ticks...`, `init_waits_for_a_late_output...`, `staged_init_completes_within_a_second...`, `splash_*`; lead's `test_oninit_does_not_sleep` |
| **O-13** low: global vs group-relative index | LED code uses `channels.selectedChannel()` (group-relative, like `isChannelSolo/Muted/Selected` and `getGridBit` in API 33+) and never passes an index outside `0..channelCount()-1` | `GROUP_RELATIVE_CHANNELS` (`False` = stock `channelNumber()`) | leds: `led_logic_uses_the_group_relative_selected_channel...`, `global_index_of_stock_is_a_switch` (the simulator has no groups: only the API used can be asserted) |
| **O-14** low: `getCurrentStepParam` = -1 | velocity clamped to 0..127 before `//4` | (none) | leds: `step_velocity_is_clamped...[8]`; lead's `test_step_parameter_query_failing...` |
| **O-15** low: misleading log lines | honest `print` lines (`OnInit start`, `OnInit done`, `FAILED`); one klt.log banner line (script name/version, python, FL API, `isAssigned`, `isMidiOutAssigned`, port, name); config summary line; every native call of the attach path is **announced in klt.log before it is made** so a crash leaves the culprit as the last line on disk; incoming SysEx logged once per distinct message; output counters | `LOG_DEVICE_DETAILS`, `LOG_DEVICE_ID` (`getDeviceID`, off) | gate: `the_init_banner_*`, `if_fl_dies_inside_a_native_call_the_last_line_of_the_log_names_it[6]`, `with_details_off...`, `gate_announces_each_native_query_once...`; lifecycle `incoming_sysex_is_logged_once...` |
| **O-16** low: unguarded deinit | `OnDeInit` safe when init never ran, when the output is unassigned, twice; goodbye frames waive the burst/LCD-gap limits (hard cap still applies); stock's deinit frame kept byte-exact; optional black-out of pads/select buttons | `SEND_DEINIT_FRAME`, `CLEAR_LEDS_ON_DEINIT` | gate: `deinit_frames_are_byte_identical_to_stock`, `deinit_frame_and_led_clearing_are_switches`, `deinit_with_the_output_unassigned...`; lifecycle `ondeinit_before_any_init...` |
| **O-17** low: Save LED constant, dead code | `COLOR_MAP` comment labels corrected (bytes untouched). Save LED (`65`) staying lit is stock; lighting it only in Sequencer mode is a switch because the hardware's polarity is unverified. `CountdownReturn` and `COLOR_PLAY_*` are left in place (dead in stock, harmless) | `SAVE_LED_FOLLOWS_MODE` | leds: `save_led_*` |
| **O-18** low: scroll 1 char / 1.5 s | 500 ms per step | `LCD_SCROLL_MS` | display: `long_names_scroll_every_lcd_scroll_ms`, `stock_scroll_speed_is_a_switch`, `broken_scroll_switch...` |
| **O-19** info: `getCurrentTempo(1)` unit, `/22` idle-rate guess | tempo normalised (`> 1000` is milli-BPM; 0 falls back to 120) and the fake-16th highlight waits real elapsed time since the beat callback instead of idle ticks / 22 | (none) | leds: `fake_sixteenth_highlight_fires_a_sixteenth_after_the_beat...[milli-bpm,bpm,zero]` |
| **O-20** info: RGB trailing `7F`, 5/7-bit colour, undecoded frames | untouched: every RGB frame keeps the trailing `7F`, deinit/memory-switch bytes are stock's | (none) | leds: `keyboard_ends_up_showing_what_the_stock_script_shows[8]`, `tuned_sends_no_led_id_or_colour_that_stock_never_sends`; lead's `test_frames_use_the_documented_byte_layouts` |
| **F-25** (cross) non-ASCII in input handlers | fixed by O-03 (sanitised in `SetLines`, so `PluginRefresh` etc. can no longer raise inside the LCD code) | | display: `every_lcd_frame...hostile_names`; lead's `test_non_ascii_text...[param_name]` |

## 3. Switch reference (output section of `KLTConfig.py`, defaults are what ships)

| switch | default | meaning |
|---|---|---|
| `OUT_ENABLED` | `True` | master kill switch: `False` = the scripts never call `device.midiOutSysex` |
| `OUT_REQUIRE_MIDIOUT_ASSIGNED` | `True` | also require `device.isMidiOutAssigned()` (undocumented) once `isAssigned()` is true |
| `OUT_UNASSIGNED_RECHECK_S` | `0.5` | while unassigned, ask FL again at most this often |
| `OUT_FAIL_BACKOFF_S` | `5.0` | pause after 5 consecutive `midiOutSysex` exceptions |
| `OUT_MAX_SYSEX_PER_SEC` | `100` | hard cap, any sliding second (a DIN-MIDI-equivalent ~1.4 KB/s; stock sent ~16 KB/s) |
| `OUT_MAX_SYSEX_PER_TICK` | `8` | frames per `OUT_TICK_S` window |
| `OUT_TICK_S` | `0.02` | one `OnIdle` period |
| `OUT_LCD_MIN_GAP_S` | `0.035` | minimum spacing of LCD frames (community-tested) |
| `OUT_LED_PASS_S` | `0.1` | polled-LED evaluation interval |
| `OUT_TRICKLE_S` | `1.0` | idle keep-alive: one known LED frame per interval (`0` = off) |
| `OUT_LCD_KEEPALIVE_S` | `10.0` | LCD keep-alive (`0` = off) |
| `OUT_HOLD_TIMEOUT_S` | `5.0` | held LEDs are released if `OnIdle` stops advancing the init |
| `OUT_STATS_LOG_S` | `60.0` | counters line in klt.log when frames were sent (`0` = off) |
| `INIT_ANIMATION` | `0` | 0 none, 1 pad wipe (32 frames), 2 stock (240 frames) |
| `INIT_FRAMES_PER_TICK` | `4` | animation frames per `OnIdle` tick |
| `SPLASH_MS` / `SPLASH_TAG_MS` | `1500` / `1000` | welcome page / "tuned v0.1.0" page (`0` = skip) |
| `LCD_SCROLL_MS` | `500` | scroll step for text longer than 16 characters (stock 1500) |
| `REFRESH_IGNORE_NOISY_FLAGS` | `False` | skip `OnRefresh` whose flags are only mixer-controls / control-values |
| `RESET_HELPER_STATE_ON_INIT` | `True` | `OnInit` resets modes, bank offsets, held pads |
| `PAD_LED_FLIP_ROWS` | `False` | pad LED ids flipped vertically (O-10, unverified) |
| `SAVE_LED_FOLLOWS_MODE` | `False` | Save LED lit only in Sequencer mode (O-17, unverified) |
| `GROUP_RELATIVE_CHANNELS` | `True` | `selectedChannel()` instead of stock `channelNumber()` (O-13) |
| `SEND_DEINIT_FRAME` | `True` | stock's `02 7D 7D 0B 00` at `OnDeInit` (meaning unverified) |
| `CLEAR_LEDS_ON_DEINIT` | `False` | black out pads/select buttons at `OnDeInit` |
| `LOG_DEVICE_DETAILS` | `True` | banner also queries `isMidiOutAssigned`/`getPortNumber`/`getName` (only when assigned) |
| `LOG_DEVICE_ID` | `False` | banner also queries `device.getDeviceID()` (API 25+, unverified on FL 26.1.6) |

A malformed value (a string where a number belongs, `None`) falls back to the default instead of raising
(`test_output_fuzz.py::broken-values`).

## 4. Native calls the output side makes, and what to do if FL crashes on attach

The FL 26.1.6 crash (`docs/incidents/2026-09-29-fl-crash-kl-probe.crash.txt`) is a native null read reached from a Python
call; the probe that crashed made several `device.*` calls in `OnInit`, so the culprit is not proven to be `midiOutSysex`.
The tuned scripts therefore make no more native calls than they need, in a fixed order, and say what they are about to do:

| when | calls |
|---|---|
| import | none |
| `OnInit` | `general.getVersion()`, `device.isAssigned()`; only if that is `True` and `LOG_DEVICE_DETAILS`: `device.isMidiOutAssigned()`, `device.getPortNumber()`, `device.getName()` (and `device.getDeviceID()` if `LOG_DEVICE_ID`) |
| before a send | `device.isAssigned()`, then (only if true, `OUT_REQUIRE_MIDIOUT_ASSIGNED`) `device.isMidiOutAssigned()`; then `device.midiOutSysex()` |
| output unassigned | `device.isAssigned()` at most every `OUT_UNASSIGNED_RECHECK_S`; nothing else |
| after `OnDeInit` | none |

The output side never calls `device.midiOutMsg`, `processMIDICC`, `dispatch` or any other output API. Each of these calls is
announced in klt.log **before** it is made (`probe: about to call ...`, `gate: about to call ...`), one line at a time,
opened and closed per line, so if FL dies inside one the **last line of klt.log names it** (tested with an emulated crash in each).
If instead the log says `isAssigned() is True but isMidiOutAssigned() is False` while the output is assigned in FL, that undocumented
query does not mean what its name suggests: set `OUT_REQUIRE_MIDIOUT_ASSIGNED = False`.
To bisect on tom: read the last line; then reduce the exposure with `LOG_DEVICE_DETAILS = False` and
`OUT_REQUIRE_MIDIOUT_ASSIGNED = False` (only `isAssigned` remains), and `OUT_ENABLED = False` (no `midiOutSysex` at all).

## 5. Behaviour differences against stock (diffreplay)

`python -m tests.flsim.diffreplay <stock> <tuned>` over 20,000 seeded events (four seeds, both boot orders, output assigned
and unassigned): no regression (`--fail-on-regression` exits 0), no `FLCrash` in the tuned scripts (stock: one per episode
without an output), zero exceptions escaping a callback (stock: 629-703 per run).

To attribute the output-side differences apart from the input-side fixes, the output side was also replayed on top of the
**baseline** input files (identical to stock) and every episode whose final keyboard state differs was classified:

| after the same stream, 3 s idle | result |
|---|---|
| final LED + LCD state identical to stock | 45-49 of 80 episodes |
| stock raised an exception somewhere in the episode (poisoned display, `IndexError`, `ValueError`; its state is stale or its handlers aborted) | 31-34 of 80 (the fixes O-03, O-04, O-08, O-14) |
| everything else | only: scroll window position (O-18: 500 ms vs 1,500 ms steps) and the position of the fake-16th playhead pad (O-19: real time instead of idle ticks). Without a final `OnRefresh` a few more differ because the tuned scripts repaint the pads when the mode changes and stock waits for an `OnRefresh` (O-07) |

`tests/test_output_leds.py::test_the_keyboard_ends_up_showing_what_the_stock_script_shows` asserts, for 8 FL states (drum,
5 channels, third bank of 40, sequencer with velocities, song mode, transport LEDs, mixer, last mixer bank), that the
final LED ids and colours are identical to stock's, and `test_tuned_sends_no_led_id_or_colour_that_stock_never_sends` that the
set of (LED id, value) is a subset of stock's.

## 6. Not done, unverified, or left to the other side

* **Hardware unknowns stay switches with stock defaults**: pad LED orientation (O-10), Save LED polarity (O-17), the noisy
  refresh flags (O-07), the deinit frame (`SEND_DEINIT_FRAME`), whether `isMidiOutAssigned` is safe to call.
* **O-09 residual**: with `FORWARD_USE_PROCESSOR = True` the Forward script runs the DAW processor from its own callbacks;
  LCD pages that produces leave through the Forward script's output, and in a single-interpreter FL they would share this
  module's shadow state. Off by default. If FL runs the scripts in separate interpreters each gets its own copy of the output
  layer and the question does not arise.
* **A stale solo/mute LED**: as in stock, `IsChannelSolo/Muted` and `IsTrackSolo/Muted` only update while the Channel Rack or
  the Mixer has focus; the polling interval (100 ms) can leave a value from just before a focus change.
* **`OnFirstConnect`, `OnSendTempMsg`, `OnUpdateMeters`** are not implemented (stock neither).
* `CountdownReturn` (dead code in stock) and `COLOR_PLAY_*` were left alone.
* The idle-rate assumption (50 Hz) only shapes how quickly pending frames drain; the budgets are in time, not ticks.
* For the input side: entry `init()` is idempotent (`init(force=True)` only from `OnInit`); `_processor` is `None` until the
  DAW script's `OnInit` ran; `OnInit` calls `KLTProcess.reset_state()` if it exists.

## 7. Run it

```bash
cd /home/delorenj/code/DeLoMIDI
uv run --python 3.12 --with pytest python -m pytest tests -q                       # everything
uv run --python 3.12 --with pytest python -m pytest tests/test_output_*.py -q      # this side's tests (about 15 s)
uv run --python 3.12 python -m tests.flsim.diffreplay "$KL_STOCK_DIR" "scripts/KeyLab mkII tuned" --events 20000 --seed 1
```

`--stock` skips the `test_output_*` tests (they exercise tuned-only features).
