# 03 - Output-side audit: LEDs, 2x16 LCD, init/deinit and the entry-script lifecycle

Scope: everything FL Studio sends TO the Arturia KeyLab mkII 88 (SysEx LEDs, LCD, init/deinit messages), plus the
lifecycle of the entry script (`OnInit -> OnRefresh -> OnIdle -> OnUpdateBeatIndicator -> OnSysEx -> OnDeInit`).
Input handling (knobs, faders, buttons, plugin mapping) is out of scope except where it feeds the output path.

Date of analysis: 2026-09-29. The FL host (Windows 11 box `tom`) was unreachable, so nothing here was observed on real
hardware. Everything is static reading plus a Linux-side simulation.

Stock set under audit (Arturia 2021, byte-identical to what the user runs):
`/home/delorenj/Documents/Image-Line/FL Studio/Settings/Hardware/Arturia KeyLab MKII/`. Files are CRLF. In the
citations below `entry` = `device_KeyLabmkII.py`, `Return` = `KeyLabmk2Return.py`, `Display` = `KeyLabmk2Display.py`,
`Pages` = `KeyLabmk2Pages.py`, `Dispatch` = `KeyLabmk2Dispatch.py`, `Process` = `KeyLabmk2Process.py`.

Evidence tags used throughout:

| Tag | Meaning |
|---|---|
| [S] | Static: read directly from the source, `file:line` given |
| [SIM] | Reproduced in the Linux-side FL-host simulation (section 1.2) |
| [GUIDE p.N] | Arturia "KeyLab mkII FL Studio User Guide V1", PDF page N (1-17) |
| [DOC] | FL Studio API docs / official IL-Group stubs |
| [COMM] | Community project `rjuang/flstudio-arturia-keylab-mk2` (the ancestor of the stock display/pages code) or the Gig Performer SysEx PDF |
| UNVERIFIED | Could not be established without the real host or hardware |

---

## 0. Bottom line

1. The stock output path is **structurally sound in a healthy setup**: in simulation `OnInit` completes, every SysEx is
   correctly framed (`F0 ... F7`, all data bytes below `0x80`), and every FL API function the output files call exists in
   the official stubs / FL 2025 `midi.py`. No output-side bug I found makes the script die in a clean, configured setup.
2. There are exactly **three ways the output side goes dark or dead** that are plausible:
   (a) the DAW **output** port is not assigned/matched, and the script neither checks nor tells you (`device.isAssigned()`
   is never called, `Dispatch.py:65-66`);
   (b) a **non-ASCII character** in a channel name, pattern name or `ui.getProgTitle()` raises `UnicodeEncodeError`
   inside the LCD code and permanently poisons the display state, which silences **all** `OnIdle` LED updates and aborts
   `OnRefresh` until that text changes (`Display.py:49,58`) [SIM];
   (c) the 2.9 s blocking `OnInit` + 22-24 undeduplicated SysEx per `OnIdle` tick (~1,200 msg/s, ~15.7 KB/s at the
   documented 50 Hz idle rate) may overrun the keyboard or the Windows MIDI path. That is UNVERIFIED on hardware, but the
   community project that the stock code descends from documents that flooding the display can wedge the keyboard
   until power-cycle [COMM].
3. The prior assistant's central diagnosis ("`OnInit` throws, `_mk2`/`_processor` stay undefined, every callback
   NameErrors; the unused `import ArturiaCrossKeyboardKLmk2` is the main suspect") **does not hold for this install**:
   the module exists, and I could find no plausible trigger for an exception *inside* `init()`. Failures after `init()`
   leave `_mk2` and `_processor` **defined** (section 3.1) [SIM].
4. The prior claim that the original "showed the splash and then immediately replaced it with the main page" is wrong:
   the splash is on the LCD for ~2.9 s because `OnInit` then blocks in the LED animation [SIM].
5. Nothing in the mk3 set checks `device.isAssigned()` either, but FL's own shipped scripts (Mackie, Fire, SSL) guard every
   output with it. mk3 has several output-discipline ideas worth porting (section 4).
6. A tested minimal patch of the three output files is in Appendix B. It takes steady-state OnIdle output from
   **1,200 to 12 msg/s**, keeps the LCD alive across keyboard resets, survives non-ASCII text, never NameErrors, and warns
   once if no output is assigned. Behavior on real hardware is still to be confirmed (section 8).

---

## 1. Method and evidence

### 1.1 What was read

Fully read: `device_KeyLabmkII.py`, `KeyLabmk2Return.py`, `KeyLabmk2Display.py`, `KeyLabmk2Pages.py`,
`KeyLabmk2Dispatch.py`. Also read for context: `ArturiaCrossKeyboardKLmk2.py`, `ArturiaVCOL.py`,
`device_Forward CCs Port 10 KEYLAB MKII.py`, the head of `KeyLabmk2Process.py` (constructor, module globals, `BankSelect`),
the head of `KeyLabmk2Navigation.py`, and mk3's `device_KL3.py`, `KL3Connexion.py`, `KL3Dispatch.py`, `KL3Display.py`,
`KL3Return.py`, `KL3Pages.py`, `device_KeyLab mk3 MIDI.py`, `LedId.py`, `ParamId.py`, `IntegrationPatchId.py`.

Static checks run:

- All 91 distinct `module.attr` FL API references across the 11 stock files were resolved against the official stubs
  (`IL-Group/FL-Studio-API-Stubs`) and FL 2025's `Shared/Python/Lib/midi.py`: **0 missing**. The 27 references made by the
  five output files are all present.
- The window constants used by the output path (`WidMixer=0`, `WidChannelRack=1`, `WidPlaylist=2`, `WidBrowser=4`,
  `WidPlugin=5`, `Return.py:23-27`) match FL 2025 `midi.py:482-489`.
- The only `device.*` calls in the whole stock set are `device.midiOutSysex` (one call site, `Dispatch.py:66`),
  `device.processMIDICC` (`Process.py:258`) and `device.forwardMIDICC` (Forward script line 42). `device.dispatch`,
  `isAssigned`, `getPortNumber`, `getName` are never used.
- Only one file (`device_KeyLabmkII.py`) contains non-ASCII (a UTF-8 `e` with grave in the docstring author name, `entry:6`);
  harmless under Python 3's UTF-8 source default.
- The guide's DAW-function button order (Solo, Mute, Record, Read, Off, Save, In, Out, Metro, Undo, [GUIDE p.12]) lines up
  one-to-one with LED ids `60..69` in the Gig Performer table, which cross-validates both sources for section 2.3.
- Framing check across every mode combination (Drum/Sequencer x Channel Rack/Mixer x loop mode x bank offsets 0-2, recording
  on, all steps set, velocity 127, 26,114 messages): **0 framing or data-byte violations**.

### 1.2 The simulation

I built a small fake FL host in the scratchpad that installs stub `device/ui/channels/patterns/transport/mixer/...`
modules, records every `device.midiOutSysex` call with a virtual timestamp, patches `time.sleep` and `time.monotonic` to a
virtual clock, and then loads the **unmodified** stock files (copied out of `Documents`, which was never touched).
The real FL 2025 `midi.py` is used. The harness drives the callbacks, ticks `OnIdle` at 20 ms, injects failures, and
decodes each captured message.

Harness (ephemeral, in the session scratchpad):
`/home/delorenj/.claude/tmp/claude-1000/-home-delorenj-code-DeLoMIDI/40a31932-1502-4d43-bfe7-af142d7a75fc/scratchpad/output-audit/simharness/`
(`fl_stubs.py`, `run_sims.py`, `run_patched.py`, `sim_output.txt`, `sim_output_patched.txt`). Ask if it should be promoted
to `tests/`.

What the simulation can prove: the stock code's own logic (message counts, ordering, dedupe, exception propagation, state
poisoning). What it cannot prove: how real FL handles a `midiOutSysex` on an unassigned output, the real `OnIdle` rate,
whether the Windows MIDI stack or the keyboard drops flooded SysEx, and what the reverse-engineered bytes mean to the
firmware.

### 1.3 External references

- Arturia guide (PDF in the Hardware folder), pages cited by PDF page. Sibling report `01-official-guide.md` has the full
  guide analysis; this report only cites what the output side needs.
- "Arturia KeyLab MkII SysEx - Basic SysEx Commands" (Gig Performer community PDF, 2 pages). **Reverse-engineered from
  MkI forum posts, not an official Arturia spec.** https://community.gigperformer.com/uploads/short-url/9KTVuv6iAtD8PtBD9hXtrzubhUQ.pdf
- `rjuang/flstudio-arturia-keylab-mk2` @ `28c38f7` (MIT). The stock `Display`, `Pages` and `Dispatch` files carry
  "Copyright (c) 2020 Ray Juang" headers (`Display.py:1-2`, `Pages.py:1-2`, `Dispatch.py:1-2`), so this project is the
  ancestor. It was written against real hardware and contains the throttling knowledge that Arturia's fork dropped.
- Arturia support article "KeyLab MkII - Tips & Tricks", FL Studio section (Default MCU map, MIDIIN2/MIDIOUT2 on Windows).
- FL MIDI scripting manual and API stubs for callback semantics.

---

## 2. The protocol as implemented

### 2.1 Framing

Every output message goes through **one function**, `send_to_device` (`Dispatch.py:65-66`):

```
F0 00 20 6B 7F 42 <payload...> F7
```

| Bytes | Meaning |
|---|---|
| `F0` | SysEx start |
| `00 20 6B` | Arturia manufacturer ID |
| `7F` | Device ID field, broadcast/"all" |
| `42` | Arturia keyboard DAW-protocol family byte. Not mkII-specific: mk3 uses the identical 6-byte header (`KL3Dispatch.py:66`) with a different payload grammar |
| payload | see 2.2 |
| `F7` | SysEx end |

FL ignores a `midiOutSysex` call that lacks `F0`/`F7` [DOC: `device/__device.py:162-174`]. The stock always supplies both.
All 241 messages of a full `OnInit` and every steady-state message passed a framing check (first byte `F0`, last `F7`, every
interior byte `< 0x80`) in simulation [SIM].

### 2.2 Message catalogue

| # | Payload (after the 6-byte header) | Decoded | Emitted by | Size incl. `F0..F7` |
|---|---|---|---|---|
| 1 | `02 00 10 <id> <v>` | Set **monochrome** LED `id` to brightness `v` (0x00-0x7F) | `Return.py` transport/DAW LED routines, `NotBlinkingLed` | 12 B |
| 2 | `02 00 16 <id> <R> <G> <B> 7F` | Set **RGB** LED `id` to colour (R,G,B) plus a trailing `7F` | pads, Select 1-8, Multi | 15 B |
| 3 | `04 00 60 01 <line1> 00 02 <line2> 00 7F` | Write the **LCD**, two lines, each <= 16 ASCII bytes | `Display._refresh_display` (`Display.py:80-90`) | <= 47 B |
| 4 | `02 7D 7D 0B 00` | **Deinit** (semantics UNVERIFIED, see 2.7) | `OnDeInit` (`entry:116`) | 12 B |

Messages 1-3 match the community-documented grammar [COMM: `arturia_leds.py:76,79`; Gig Performer PDF p.1] with two
differences worth knowing:

- The Gig Performer PDF and the community project write the RGB frame **without** the trailing `7F`
  (`02 00 16 id R G B`). Arturia's own script always appends `7F`. Its meaning is undocumented (blink/mode/brightness flag?)
  UNVERIFIED. The community project notes that pad RGB "doesn't seem to be working" [COMM: `arturia_leds.py:219`]; the
  missing trailing byte is a candidate reason. **Do not "clean up" the `7F`** when porting.
- The Gig Performer PDF gives the RGB range as `00..1F` (5 bit). Arturia's script sends `0x7F` for full colour but scales
  sequencer step velocity with `//4` (`Return.py:231`), which yields 0..31. The two are consistent only if the hardware
  ignores or clamps the top bits. UNVERIFIED; harmless either way.

### 2.3 Monochrome LEDs (`02 00 10 <id> <v>`)

Values used: `0x7F` = on, `0x09` = "off" (a faint glow, never `0x00`, in steady state). LED names from the Gig Performer
table [COMM p.2]; button roles from the guide [GUIDE p.12].

| id | LED (GP table) | Guide role (p.12) | Stock behaviour | Where | Rate |
|---|---|---|---|---|---|
| `1A` | left nav arrow | - | constant `7F` | `Return.py:319` | every idle tick |
| `1B` | right nav arrow | - | constant `7F` | `Return.py:320` | every idle tick |
| `60` | Solo | Solo selected track | Channel Rack focused: `isChannelSolo(channelNumber())`; Mixer focused: `isTrackSolo(trackNumber())`; `7F`/`09`. Frozen if neither window has focus | `Return.py:116-128` | every idle tick |
| `61` | Mute | Mute selected track | same pattern with `isChannelMuted` / `isTrackMuted` | `Return.py:131-143` | every idle tick |
| `62` | Record (DAW block) | Change snap mode | constant `7F` | `Return.py:307` | every idle tick |
| `63` | Read | Tap tempo | constant `7F` | `Return.py:308` | every idle tick |
| `64` | Write (guide overlay calls it "Off") | Off: cut the pattern of the selected channel | constant `7F` | `Return.py:309` | every idle tick |
| `65` | Save | Drum mode / Step Sequencer mode | constant `7F` (so it can never show the mode). `CountdownReturn` would drive it from `isPrecountEnabled` but is **never called** | `Return.py:310`, dead code `86-90` | every idle tick |
| `66` | In | Switch Channel Rack / Browser | constant `7F` | `Return.py:311` | every idle tick |
| `67` | Out | Overdub | constant `7F` | `Return.py:312` | every idle tick |
| `68` | Marker (guide calls it Metro) | Metronome | `7F` if `ui.isMetronomeEnabled()` else `09` | `Return.py:79-83` | every idle tick |
| `69` | Undo | Undo | constant `7F` | `Return.py:313` | every idle tick |
| `6A` | `<<` | Rewind / seq offset | constant `7F` | `Return.py:314` | every idle tick |
| `6B` | `>>` | Fast-forward / seq offset | constant `7F` | `Return.py:315` | every idle tick |
| `6C` | Stop | Stop | `7F` if `mixer.getSongTickPos()==0` else `09` | `Return.py:107-113` | `OnRefresh`, `OnSysEx` |
| `6D` | Play/Pause | Play/pause | `7F` if song position != 0 else `09`; **beat-blinked** by `OnUpdateBeatIndicator` (value 0 -> `09`, else `7F`) | `Return.py:107-113,243-250` | `OnRefresh`, every beat callback |
| `6E` | Record (transport, red) | Record | `7F` if `transport.isRecording()` else `09`; blinked on beat only while recording | `Return.py:100-104,253-260` | `OnRefresh`, beat callback |
| `6F` | Loop | Loop record | `7F` if `ui.isLoopRecEnabled()` else `09` | `Return.py:93-97` | every idle tick |

### 2.4 RGB LEDs (`02 00 16 <id> <R> <G> <B> 7F`)

Channel order is R,G,B: the mixer/channel-rack colours below reproduce the guide's stated colours only under R,G,B order
[GUIDE p.13]. (The `COLOR_MAP` comments at `Return.py:38-44` label `00 00 7F` "GREEN" and `00 7F 00` "BLUE", which is
backwards; cosmetic.)

**Select 1-8, ids `22-29`** (`SELECT_MAP`, `Return.py:46`) and **Multi `2A`**:

| State | Bytes (R G B 7F) | Colour | Guide p.13 |
|---|---|---|---|
| Mixer, slot exists, not selected, not muted | `00 00 7F 7F` | blue | "Blue light: track available in Mixer" |
| Channel Rack, slot exists, not selected, not muted | `7F 00 7F 7F` | purple | "Purple light: channel available" |
| Selected, not muted | `7F 7F 00 7F` | yellow | "Yellow: available and selected" |
| Muted (selected or not) | `7F 00 00 7F` | red | "Red: track available but muted" |
| Slot beyond channel/track count | `00 00 00 7F` | off | "Offlight: no channel in this slot" |
| Multi (`2A`), constant | `7F 7F 7F 7F` | white | - |

All emitted every idle tick, 8 messages regardless of state (`Return.py:169-222`), plus `2A` from `NotBlinkingLed`
(`Return.py:324`).

**Pads 1-16, ids `70-7F`** (`PAD_MAP`, `Return.py:32-36`):

| Mode | Bytes | Colour | Where |
|---|---|---|---|
| Drum mode (`SEQ_MODE==0`, default) | `7F 00 00 7F` on all 16 | red | `Return.py:237-239` (every `OnRefresh`) |
| Sequencer, step on | `v//4 v//4 00 7F`, `v` = step velocity (param 1, 0-127) | yellow, dimmer for soft steps | `Return.py:229-231` |
| Sequencer, step off | `7F 7F 7F 7F` | white (guide p.15 says "light blue") | `Return.py:233` |
| Sequencer, loop mode | `7F 00 7F 7F` on all 16 | magenta | `Return.py:235-236` |
| Playhead inside the shown bar | `00 00 7F 7F` on pad `step%16` | blue | `Return.py:273,293,298` |
| Playhead outside the shown bar | `7F 00 00 7F` on pad `step%16` | red | `Return.py:275,295,300` |
| Init animation | black, then each of 6 colours in `COLOR_MAP`, then white, then black | - | `Return.py:50-76` |

### 2.5 Blink semantics

There is **no firmware blink command** in use. "Blinking" is done in software: `OnUpdateBeatIndicator(value)` toggles the
Play LED `6D` (and Record `6E` while recording) between `7F` and `09` on each callback, and in Sequencer mode repaints
the pads and re-highlights the playhead (`Return.py:243-275`). `RefreshTime` (`Return.py:278-300`) fakes a 16th-note
callback by counting idle ticks (`REFRESH_COUNT/22 >= (60/tempo)/4`), and only re-arms when the next real beat callback
resets `PASS`. That `/22` implies the original developer measured roughly 22 idle calls/s, not the documented ~50 (see 3.3).
The name `NotBlinkingLed` is about LEDs that must be held steady, which the script achieves by re-sending them continuously.

### 2.6 LCD payload layout

`Display._refresh_display` (`Display.py:80-90`):

```
04 00 60 | 01 <line1: <=16 ASCII> 00 | 02 <line2: <=16 ASCII> 00 | 7F
```

Verified byte-for-byte in simulation. Welcome frame for `KeyLab mkII` / `FL Studio 2025`:

```
F0 00 20 6B 7F 42 04 00 60 01 4B 65 79 4C 61 62 20 6D 6B 49 49 00 02 46 4C 20 53 74 75 64 69 6F 20 32 30 32 35 00 7F F7
                  |--cmd--| L1 K  e  y  L  a  b     m  k  I  I  NUL L2 F  L     S  t  u  d  i  o     2  0  2  5  NUL END
```

Rules of the implementation:

- Each line is sliced to 16 characters starting at a scroll offset: `bytearray(line[start:start+16], 'ascii')`
  (`Display.py:44-49,53-58`). The stock therefore **already clips to 16**; the prior claim of adding clipping is moot.
- Encoding is strict ASCII. Any code point above 127 raises `UnicodeEncodeError` (section 3.9c). The community ancestor
  used `'utf-8'` (`arturia_display.py:52,61`), which never raises but emits bytes >= 0x80, illegal in SysEx data.
- Text is not sanitised: an embedded `00` ends the line early on the hardware (UNVERIFIED), and control characters pass
  through. In simulation a name containing NUL and newline was sent verbatim [SIM].
- Change detection: a frame is sent only if it differs from `_last_payload` (`Display.py:88-90`). This is the **only**
  deduplication anywhere in the output layer.
- Scrolling: lines longer than 16 chars advance by one character every 1,500 ms with 3 chars of end padding
  (`Display.py:34,37,60-72`). A 30-character name takes ~20 s to cycle. That is slow (community: 500 ms).
- Page system (`Pages.py`): `welcome`, `main`, plus 1,000 ms ephemeral pages from `Navigation`. An ephemeral page
  overwrites the base lines and the LCD returns to `main` on the first `Refresh()` after expiry.

### 2.7 Init and deinit messages

There is **no handshake or "enter DAW mode" message** on init in the mkII script (unlike mk3, which sends
`00 <daw=2> <connection=5> 01`, `KL3Connexion.py:25-27`).

`OnInit` output sequence [SIM]:

1. `t=0`: one LCD frame, `KeyLab mkII` / `ui.getProgTitle()`.
2. `Return.init()` (`Return.py:50-76`): 16 pads to black; then for each of 6 colours 16 pads on (10 ms apart) and 16 off
   (10 ms apart); 0.5 s pause; all white; 0.5 s pause; all black.
   **240 RGB frames, 3,640 bytes total with the LCD frame, and 2.920 s of `time.sleep`** on FL's main thread.

`OnDeInit` sequence (`entry:113-117`) [SIM]: LCD frame `KeyLab mkII` / `Disconnected`, then `F0 00 20 6B 7F 42 02 7D 7D 0B 00 F7`.
The meaning of `02 7D 7D 0B 00` is UNVERIFIED: I could not find it in the Gig Performer PDF, the Arturia forum threads or
the community project. It leaves every LED as it was (no clear) and does not restore the keyboard's own display.

### 2.8 The `OnSysEx` "memory switch" message

`entry:157-160` compares `event.sysex` against the literal `b'\xf0\x00 k\x7fB\x02\x00\x00\x15\x00\xf7'`, where the
printable characters are `' '` = `0x20`, `'k'` = `0x6B`, `'B'` = `0x42`. It decodes to

```
F0 00 20 6B 7F 42 02 00 00 15 00 F7      payload 02 00 00 15 00
```

Same header, payload grammar `02 00 <type> <id> <value>` with type `00` (not an LED type). The script comment calls it a
"memory switch"; the exact firmware meaning (which memory/preset, and whether `15` is a slot number) is UNVERIFIED.
On a match the script calls `ui.setFocused(1)` (Channel Rack) then `OnRefresh(32)` (`midi.HW_Dirty_FocusedWindow`).
That re-sends the pad frames and transport LEDs but **cannot repaint the LCD** (deduped, see O-05). Every other incoming
SysEx (including any device-inquiry reply) is silently ignored.

### 2.9 Not documented anywhere I could find (UNVERIFIED)

- The meaning of the trailing `7F` in RGB frames.
- `02 7D 7D 0B 00` (deinit) and `02 00 00 15 00` (memory switch).
- Whether the hardware masks RGB to 5 bits.
- The keyboard-side effect of the "FL Studio memory slot" the guide says to create (GUIDE p.4) versus Arturia's support
  article, which instead says to set the DAW map to "Default MCU" (a different setup). Which one the user has is unknown.
- The identity-reply bytes of the mkII (needed for `supportedHardwareIds`; capture with `device.getDeviceID()`, API v25+).

---

## 3. Lifecycle trace

### 3.0 Per-callback output budget (healthy setup, Channel Rack focused, drum mode) [SIM]

| Callback | What it does | SysEx per call | Blocks? | Can raise? |
|---|---|---|---|---|
| module import | 11 imports; circular `Process <-> Navigation/SeqParam` resolves fine | 0 | no | only if a helper file is missing |
| `OnInit` (`entry:92-100`) | `init()`, `Sync`, welcome page, main page, `LightReturn().init()` | **241** (1 LCD + 240 RGB), 3,640 B | **2.92 s** | yes (3.1) |
| `OnRefresh(flags)` (`entry:131-135`) | `Sync`, `SequencerReturn`, `PlayReturn`, `RecordReturn`. **`flags` ignored** | **19** (16 RGB + 3 mono) `+1 LCD` if text changed, 276-308 B | no | yes (display text) |
| `OnIdle` (`entry:141-151`) | LCD refresh + 8 LED routines + `RefreshTime` | **24** per tick (22 if neither Channel Rack nor Mixer focused); `+17` when `RefreshTime` fires in Sequencer mode; LCD 0 unless text changed | no, but 24 sends x ~50/s | yes (display text, stale bank offset) |
| `OnUpdateBeatIndicator` (`entry:122-125`) | Play blink, Record blink, Sequencer blink | drum mode 1 (+1 recording); Sequencer mode `+17` | no | rarely |
| `OnSysEx` match (`entry:157-160`) | focus Channel Rack, `OnRefresh(32)` | 19, **0 LCD** | no | yes |
| `OnDeInit` (`entry:113-117`) | goodbye LCD, deinit frame | 2 | no | `NameError` if init never ran |
| `OnMidiMsg` (`entry:84-85`) | `_processor.ProcessEvent` | 0-1 LCD page frame per input event | no | `NameError` if init never ran |

The script defines no `OnDoFullRefresh`, `OnProjectLoad` or `OnFirstConnect`.

### 3.1 `OnInit`: what can abort it half-way

`OnInit` in order, with the failure analysis. `_mk2` and `_processor` are bound by `init()` (`entry:103-108`) **before** any
FL API or MIDI output happens.

| Step | Line | FL API / output involved | Realistic failure | State left behind |
|---|---|---|---|---|
| print | 93 | - | none | - |
| `init()` -> `MidiControllerConfig()` | 94, 106 | none: `KeyLabLightReturn()`, `KeyLabDisplay()`, `KeyLabPagedDisplay()` are pure-Python attribute setup | none realistic | if it did raise: **`_mk2` and `_processor` undefined**, all callbacks `NameError` |
| `init()` -> `KeyLabMidiProcessor(_mk2)` | 108 | none at construction; wires ~50 handler methods | none: every handler method name resolves (simulated construction succeeds) | if it raised: `_mk2` defined, `_processor` undefined; only `OnMidiMsg` NameErrors |
| `_mk2.Sync()` | 95 | `channels.selectedChannel`, `getChannelName`, `patterns.*` | an exception from those calls (behaviour for an empty channel rack is UNVERIFIED); non-ASCII name only breaks later because `main` is not yet active | **both defined**; `main` page never activated; LCD stays blank |
| welcome `SetPageLines` | 96 | `ui.getProgTitle()` | title string is later encoded to ASCII | both defined |
| `SetActivePage('welcome', expires=1500)` | 97 | first LCD `midiOutSysex` | **non-ASCII in `getProgTitle()`**; whatever `midiOutSysex` does when no output is assigned (UNVERIFIED) | both defined; `_ephemeral_page` set but `SetActivePage('main')` never runs, so `_active_page` stays `None` |
| `SetActivePage('main')` | 98 | LCD | as above | both defined |
| `LightReturn().init()` | 100 | 240 RGB sends + 2.92 s of sleeps | output exceptions | both defined; **LED init animation partially or never run** |

Conclusions [SIM]:

- The "usual cause" the prior assistant proposed (exception inside `init()`, leaving names undefined) needs a failure in
  code that touches no FL API. The only realistic route to that state is an `ImportError` at **module load**, which is a
  different failure: the script never loads, FL prints the error in Script output, and no callbacks exist at all. For this
  install that is ruled out: `ArturiaCrossKeyboardKLmk2.py` and every other helper exist (`ls`, 12 `.py` files), and
  simulation imports cleanly with the FL 2025 `midi.py`.
- The failures that **are** plausible (non-ASCII title, unassigned output if it raises) abort `OnInit` **after** `init()`.
  Both names stay defined, so later callbacks do not NameError; instead they re-raise the same poisoned-state exception
  (3.9c). Result: no LED init animation, LCD never showing the `main` page, and `OnIdle` dead.
- The log lines are misleading (O-15). `### INIT KEYLAB mkII OKAY ###` (`entry:93`) prints unconditionally first.
  `### Successfully created class objects ###` (`entry:104`) prints **before** the objects are created.
  `### Messages successfully sent to KEYLAB mkII ###` (`entry:99`) prints after the LCD writes but **before** the LED
  animation, and says nothing about delivery. Reading Script output:
  - only the first line, or a traceback after it: `OnInit` aborted (traceback names the line);
  - all three lines: no exception occurred through line 98; a dark keyboard then means the bytes are not reaching the
    hardware (port/mode/driver), not a script exception;
  - a fourth line `init ok` is FL's own compile-success message [DOC manual].

### 3.2 `OnRefresh`

`flags` is never read (`entry:131`). Every refresh, whatever changed, re-runs `Sync` and repaints the 16 pads
(`Return.py:225-239`), Play/Stop and Record: **19 SysEx (276-308 B)** [SIM]. FL raises refreshes for mixer, control-value,
colour and name changes; `HW_Dirty_ControlValues (4096)` and `HW_Dirty_Mixer_Controls (4)` fire while the user moves
faders/knobs or automation plays. mk3 filters these two (`device_KL3.py:141`). Drum mode repaints the same solid red
every time.

### 3.3 `OnIdle`: rate, budget and deduplication

Documented rate: "roughly once every 20 ms" [DOC: `callbacks/__init__.py` `OnIdle`]. Stock `RefreshTime` assumes 22 calls/s
(`Return.py:287`), so the real rate on the developer's machine may be lower. I report both.

Per tick, Channel Rack focused [SIM]:

| Source | Msgs |
|---|---|
| `MetronomeReturn` (`68`) | 1 |
| `LoopReturn` (`6F`) | 1 |
| `NotBlinkingLed` (9 mono + 2 nav + `2A` RGB) | 12 |
| `IsChannelSolo` + `IsChannelMuted` (or track versions, Mixer focused) | 2 |
| `SelectedChannel` (Select 1-8, exactly one per slot) | 8 |
| **Total** | **24** (22 when neither window is focused) |
| LCD | 0 (deduped), 1 frame only when text changes |

| Idle rate | msg/s | bytes/s |
|---|---|---|
| 50 Hz (documented) | 1,200 | 15,750 |
| 22 Hz (implied by `/22`) | 528 | 6,930 |

The 24 messages leave in a single back-to-back burst (315 B) with no spacing. For scale, a DIN MIDI cable carries 3,125 B/s;
a USB-MIDI link is far faster, so USB bandwidth is not the constraint, but the keyboard's MCU and the host driver
queue are unknown (UNVERIFIED). The community project throttles **each LED to one send per 33 ms with a 0.1 ms sleep
after every frame**, and **the LCD to 35 ms between frames** because "it's possible to overload the display and cause the
keyboard to get into a bad state where display changes are rejected until keyboard is powered off"
[COMM: `arturia_leds.py:249-259`, `arturia_display.py:5-9,122`]. The stock idle loop sends every LED at up to 1.65x that
per-LED cap, continuously, for 24 LEDs.

Deduplication: **none for LEDs.** Only the LCD has `_last_payload` (`Display.py:88-90`). One side effect of the flood is
useful: it silently **self-heals** the LEDs after a keyboard power-cycle, and any dedupe fix must add explicit resync
triggers (Appendix B does).

`SelectedChannel` also rebuilds `CHANNEL_MAP` and, through its four-way `if/elif` chains, makes dozens of
`channels.*`/`mixer.*` calls per tick (`Return.py:146-222`). Harmless but wasteful.

Sequencer-mode playback adds `RefreshTime` bursts: 16 pad frames + 1 highlight each time it fires, plus 17 per beat callback;
measured 26.8 msg/tick average (1,340 msg/s) in a 120 bpm simulation [SIM].

### 3.4 `OnUpdateBeatIndicator`

1 message per call in drum mode (`Return.py:243-250`). In Sequencer mode `ProcessSequencerBlink` also calls
`SequencerReturn()` (16 pads) plus one playhead frame, and resets the `PASS`/`REFRESH_COUNT` globals that arm
`RefreshTime` (`Return.py:263-275`). `mixer.getCurrentTempo(1)` (`Return.py:285`): the API stub says the flag returns an
int, while the Novation script (`Novation/script/fl.py:775,781`, formats it `.3f` as BPM) and the mk3 script
(`KL3Navigation.py:211-212`, compares `> 99000`) disagree with the stub and with each other. If `getCurrentTempo(1)`
returns milli-BPM, `tresh` collapses to ~0.000125 s and the fake 16th-note step highlight fires at every idle tick after a
beat instead of a 16th later. UNVERIFIED; settle by printing both `getCurrentTempo(0)` and `(1)` on `tom`.

### 3.5 `OnSysEx`

See 2.8. Note `ui.setFocused(1)` steals FL's focus to the Channel Rack on every memory switch (`entry:159`), a side effect
unrelated to output.

### 3.6 `OnDeInit`

`entry:113-117` touches `_mk2` on its first statement, so it raises `NameError` whenever `init()` never completed [SIM E1].
It also raises if `midiOutSysex` raises. It does not clear the pads or LEDs and does not `return` a status. FL may call
`OnDeInit` at shutdown when the output port is already closing; the goodbye frames may never reach the keyboard
(UNVERIFIED).

### 3.7 Re-init and reload semantics

FL may keep the script loaded after `OnDeInit` and call `OnInit` again, and the Script output **Reload** button does the
same [DOC: `callbacks/__init__.py` `OnInit`; manual "Reload"]. `init()` rebuilds the objects (good) but every module-level
global in the helper modules survives: `Process.py:41-73` (`SEQ_MODE`, `MIXER_MODE`, `RECT_OFFSET`, `EDIT_MODE`, `STATE_MATRIX`,
`INDEX_PRESSED`), `ArturiaCrossKeyboardKLmk2.py:8-9` (`MX_OFFSET`, `CH_OFFSET`), `Return.py:21-22`
(`REFRESH_COUNT`, `PASS`). A second `OnInit` replays the full 2.9 s animation [SIM]. With no `OnProjectLoad`/`OnDoFullRefresh`
handlers, loading a smaller project keeps a stale `CH_OFFSET` (O-08).

### 3.8 The second script, `device_Forward CCs Port 10 KEYLAB MKII.py`

- It does `import device_KeyLabmkII as KL` (line 19) and `KL.init()` in its own `OnInit` (line 27), then feeds
  `KL._processor.ProcessEvent(event)` (line 46). That builds a **second** `_mk2` (own `KeyLabDisplay` with its own
  `_last_payload`) and a second processor, and sends nothing at init [SIM].
- Any LCD frame produced by events processed in the Forward script goes through **its** `device.midiOutSysex`, i.e. the
  output linked to the Forward script (the guide shows it enabled on output port 1, [GUIDE p.4 Fig.2]), not the DAW output
  (port 0). Whether the keyboard displays frames received on the MIDI port is UNVERIFIED.
- FL appears to run each device script in its own Python interpreter (`device.isMidiOutAssigned` stub notes an
  "interpreter not associated with a device" [DOC]; the community project resorts to `device.dispatch` because scripts
  cannot share state [COMM: `arturia_midi.py:88`, `arturia_scheduler.py:9`]). If so, `SEQ_MODE`, `MIXER_MODE` and the bank
  offsets toggled by events arriving on the MIDI port live in the Forward script's copy of `KeyLabmk2Process` and never reach
  the DAW script's LED logic. The stock never uses `device.dispatch`, and the Forward header
  `# receiveFrom=Forward CCs Port 10 KEYLAB MKII ` (line 2) names the script itself, so nothing wires them together.
  UNVERIFIED; medium risk (O-09).

### 3.9 The specific questions

**(a) Output port unassigned.** The stock never calls `device.isAssigned()`, `getPortNumber()` or `getName()`
(`grep` over the stock set: none). FL's docs say `isAssigned()` "returns True if an output interface is linked to the
script"; the manual says `midiOutSysex` "sends to the (linked) output interface" and does not state what happens if there is
none [DOC]. Two possibilities, both simulated:

| If unassigned `midiOutSysex`... | Result [SIM] |
|---|---|
| is a silent no-op | `OnInit` completes, all callbacks run, keyboard dark, **no message anywhere** |
| raises | `OnInit` aborts at the first LCD write; every `OnIdle`, `OnRefresh`, `OnDeInit` raises each call; keyboard dark |

FL's own scripts guard output with `device.isAssigned()` (`MackieCU/device_MackieCU.py:121,134,527,591,602,620`,
`Akai FL Studio Fire/device_Fire.py:714,2334,2577,2639`), which suggests the unguarded behaviour is not something to
rely on. Either way the user gets no diagnostic. [GUIDE p.5] says input and output "of the same instance" must match. The
manual says `getPortNumber()` returns -1 when no port is assigned.

**(b) `channels.selectedChannel()` returning -1.** With the default `canBeNone=False` it returns **0** when nothing is
selected, never -1 [DOC: `channels/__properties.py:41-42`]. So `entry:63,71` cannot produce a negative index and the
prior "no longer crashes when no channel is selected" fix addresses a case the stock does not have. Forced to -1 in
simulation the stock still does not crash (`'0 - '` on the LCD) [SIM]. A genuinely empty channel rack (`getChannelName(0)`
behaviour) is UNVERIFIED. mk3 asks for `selectedChannel(1)` and shows "No Selection" (`KL3Return.py:204,459-475`).

**(c) Non-ASCII text.** Confirmed defect [SIM]:

- Strict ASCII encode at `Display.py:49` and `:58`. Sources of text: channel name (`entry:64,71`), pattern name (`entry:66,72`),
  `ui.getProgTitle()` (`entry:96`), plus parameter names/values from `Navigation`/`Plugin`.
- The bad string is stored **before** the encode (`Display.py:105-108`, `Pages.py:31-33`), so the state stays poisoned:
  `_refresh_display` raises on every subsequent call, and `OnIdle`'s first statement (`_mk2.Idle()`) raises, so **none of
  the 8 LED routines runs**.
- Rename to `Kick <heart>` after a clean init: `OnRefresh` raises at once; 100 subsequent `OnIdle` ticks: **100 exceptions, 0 SysEx**.
  Rename back to ASCII: recovers on the next `OnRefresh`.
- Non-ASCII `getProgTitle()` at `OnInit`: `OnInit` aborts at `entry:97` (`SetActivePage('welcome')`), the LED animation
  never runs, `_active_page` stays `None`, and because `_line2` holds the bad title, `OnIdle` raises **200/200 ticks forever**
  (until the script is reloaded). `OnRefresh` and `OnUpdateBeatIndicator` keep working, so Play/Record LEDs still move.
- Whether `ui.getProgTitle()` includes the project name is UNVERIFIED (the stub says "title of the FL Studio window").
  If it does, any accented project name kills `OnInit`.
- mk3 replaced this with a per-line "`.Undefined text.`" fallback and `...` truncation (`KL3Display.py:26-56`), so Arturia
  hit the same problem. That fix discards the *whole* line for one bad character; better to fold accents and replace only
  the offending characters (Appendix B).

**(d) Messages per second, dedupe, flood.** Section 3.3: 24 SysEx per idle tick, no LED dedupe, LCD deduped but not rate
limited. LCD frame rate is driven by input: a 100-step fader sweep in 1 s (`VolumeMixerRefresh` per CC) produced **100 LCD
frames/s** [SIM] versus the community's 35 ms cap (~28/s). Each step changes the text, so dedupe does not help. (Input-side
trigger, output-side flood.)

**(e) `OnDeInit` when init never completed.** `NameError: name '_mk2' is not defined` at `entry:114` [SIM E1]. If only
`_processor` is missing (E2) `OnDeInit` works. It also fails whenever `midiOutSysex` raises.

---

## 4. `device.isAssigned()`, and what mk3 does (worth porting)

**Does the stock ever check the output port?** No. No call to `isAssigned`, `getPortNumber`, `getName`, `getDeviceID` or
`isMidiOutAssigned` exists anywhere in the mkII set; all output funnels through `Dispatch.py:66`.

**mk3** (`Arturia KeyLab mk3/`, 2024) does not check either (`grep isAssigned` over the mk3 folder: no hit), has no
`try/except` anywhere, and its `OnDeInit` also dereferences `_KL3` unguarded (`device_KL3.py:124`). It does handle several
concerns better:

| mk3 practice | Where | Worth porting? |
|---|---|---|
| `# supportedHardwareIds=` header so FL auto-links the script | `device_KL3.py:2` | Yes, once the mkII identity reply is captured (`print(device.getDeviceID().hex())`). `# supportedDevices=` by name is the fallback [DOC manual lines 130-132] |
| Explicit DAW connect/disconnect frames | `KL3Connexion.py:25-31` | Concept only; the mkII equivalent is unknown |
| `OnIdle` does almost nothing: `IdleSequencer` sends only when `mixer.getSongStepPos()` changed; `IdleTimeline` sends only if the timeline page is up | `device_KL3.py:65-68`, `KL3Return.py:258-293` | **Yes.** Move all state LEDs to `OnRefresh`; idle only for the playhead |
| `OnRefresh` filters noisy flags: `if flags not in [4, 4096]` | `device_KL3.py:141` | Yes, but as a bitmask (`flags & ~(HW_Dirty_Mixer_Controls\|HW_Dirty_ControlValues)`), since the mk3 test is exact-equality and combined flags slip through |
| No blocking init animation; `Return.init` is a burst of static frames | `KL3Return.py:92-147` | Yes: drop or spread the 2.9 s animation over `OnIdle` frames |
| Non-ASCII replacement and `...` truncation | `KL3Display.py:26-56` | Yes, in the per-character form (Appendix B) |
| `selectedChannel(1) != -1` guard and "No Selection" screen | `KL3Return.py:204,459-475` | Yes |
| Removed the "fake 16th-note beat" hack | `KL3Return.py:254-256` (stub) | Yes, use the step-change edge trigger |

Not worth copying: mk3 still has no LED dedupe (it relies on being event-driven), still ignores `isAssigned`, and its
`ChannelRackReturn` compares `active_index != -1` on a value that can never be -1 (`KL3Return.py:440,459`).

---

## 5. Bug / risk list

Severity is honest: **no finding is "critical" in a correctly configured setup.** O-01 and O-03 are the plausible ways to
end up with a dark or dead keyboard; O-02 is potentially critical but needs the hardware to confirm.

| ID | Sev | Where | Problem | Suggested fix |
|---|---|---|---|---|
| O-01 | high | `Dispatch.py:65-66`; `entry:92-100` | No `device.isAssigned()` guard or port check anywhere. Unassigned/mismatched output gives a dark keyboard with no diagnostic (or raises on every callback if `midiOutSysex` errors) | Guard in the single choke point: `if not device.isAssigned(): warn once; return False`; also print `getPortNumber()`/`getName()` at init. Use `try/except` around the send |
| O-02 | high (potentially critical, UNVERIFIED on hardware) | `entry:141-151`; `Return.py:79-97,116-143,169-222,303-324` | `OnIdle` re-sends 22-24 SysEx every tick with no shadow state: 1,200 msg/s (528 at 22 Hz), 315 B bursts. Community evidence says flooding can wedge the keyboard/LCD | Shadow-state dedupe in `send_to_device`, 2 s keep-alive, explicit `resync()` on `OnInit`/`OnSysEx`, optional 100 ms LED pass. Tested: 1,200 -> 12 msg/s (App. B) |
| O-03 | high | `Display.py:49,58,105-108`; `Pages.py:31-33,52-68`; `entry:96` | Strict-ASCII encode raises on any non-ASCII channel/pattern/title text; the bad string is stored first so `Refresh()` raises every tick and the whole `OnIdle` LED pass is dead until the text changes; a non-ASCII `getProgTitle()` aborts `OnInit` and kills `OnIdle` permanently | Sanitise in `SetLines` (fold accents, `'?'` for the rest, drop control chars). Tested (App. B) |
| O-04 | medium | `entry:84-160` | No exception isolation in any callback; `OnInit` can half-abort (LCD `main` page never activated, LED init skipped); `OnDeInit`/`OnIdle`/`OnRefresh`/`OnUpdateBeatIndicator` `NameError` if `init()` failed; identical exception every 20 ms floods Script output | Module-level `_mk2 = _processor = None`; `@_safe` wrapper with log-once; early-return on `None`; reset both to `None` at the top of `init()`. Tested |
| O-05 | medium | `Display.py:88-90`; `entry:157-160` | LCD dedupe cache never invalidated. After a keyboard power-cycle, DAW-button/memory switch or reconnect, the LCD stays blank/stale for any text <= 16 chars because the payload is unchanged (assuming the keyboard clears its LCD on those events, UNVERIFIED). `OnSysEx -> OnRefresh(32)` provably cannot repaint it [SIM: 0 LCD frames] | Clear `_last_payload` (and the shadow cache) in `OnSysEx` and `OnInit`; periodic keep-alive re-send. Tested |
| O-06 | medium (UNVERIFIED on hardware) | `Display.py:80-90`; `Pages.py:38-46` | No LCD rate limit: every changed text is a frame; fader sweep gives 100 frames/s vs community's 35 ms minimum, which warns of a wedged display | 35 ms minimum gap in `send_to_device`; return `False` when throttled and only cache `_last_payload` on success so `OnIdle` retries (trailing flush for free). Tested: 25 frames/s, final value delivered |
| O-07 | medium | `entry:131-135`; `Return.py:225-239` | `OnRefresh` ignores `flags`: 19 SysEx per refresh, drum mode repaints the same red pads each time; refreshes are frequent during automation/knob moves | Mask noisy flags (see section 4) and gate pad repaint on mode/selection change; dedupe (O-02) makes the rest free |
| O-08 | medium | `Return.py:198-201`; `ArturiaCrossKeyboardKLmk2.py:8-9`; `Process.py:404-425` | Stale `CH_OFFSET`/`MX_OFFSET`/`SEQ_MODE`/... survive reload and project load. `CH_OFFSET=2` then channel count drops to 4 gives `IndexError` in `SelectedChannel` on **every** idle tick, spamming Script output [SIM] | Reset helper-module globals in `OnInit`; add `OnProjectLoad`/`OnDoFullRefresh`; clamp `CH_OFFSET` to `NB_BANK-1` inside `SelectedChannel` |
| O-09 | medium (UNVERIFIED) | Forward script lines 19, 27, 46; `Process.py` | Second `_mk2`; LCD frames triggered by MIDI-port events leave via the Forward script's output (port 1), not the DAW port; if scripts run in separate interpreters, mode/bank state diverges between the two scripts | Route all display/LED output through the DAW script (e.g. `device.dispatch` with `receiveFrom`), or make the Forward script forward only and not init the display |
| O-10 | medium (UNVERIFIED, 88-specific) | `Return.py:32-36` vs [COMM] `arturia_leds.py:202-213`, `config.py:72-73` | Community found pad LED ids are vertically flipped on 49/88 models relative to pad note numbers. Stock lights `0x70+step`, so on an 88 the Sequencer-mode step LEDs may appear on the mirrored row | Hardware test in Sequencer mode (section 8). If confirmed, map `led = 0x70 + (3 - i//4)*4 + i%4` for the 88 |
| O-11 | medium | THREAD.md advice; Forward script line 41; [GUIDE p.4] | The prior advice to number the DAW port **10** conflicts with the guide (DAW = port 0, MIDI = port 1) and collides with port 10, the input port Analog Lab plugins listen on for forwarded CCs | Use 0 (DAW) and 1 (MIDI) as in the guide; see `01-official-guide.md` C1 |
| O-12 | low | `Return.py:50-76` | `OnInit` blocks FL's main thread for 2.92 s (240 sends + sleeps); every Reload/OnInit repeats it. Older Windows Python rounds `sleep(0.01)` up to ~15.6 ms; FL 2025's 3.12 should not | Drop the animation or run it as frames from `OnIdle` |
| O-13 | low | `Return.py:118,133,199,229,230` | Global `channels.channelNumber()` is passed to functions whose default index is group-relative (API v33+: `getGridBit`, `isChannelSolo/Muted/Selected`). Wrong channel's LED/steps when a Channel Rack group filter is active | Use `channels.selectedChannel()` consistently (or pass `useGlobalIndex=True`) |
| O-14 | low | `Return.py:230-231` | `getCurrentStepParam` may return -1 (mk3 guards it, `KL3Return.py:228`); `bytes([... -1//4 ...])` then raises `ValueError` [SIM] | `if v < 0: v = 0` |
| O-15 | low | `entry:93,99,104` | Misleading log lines (section 3.1); no line says whether output is assigned | Print `isAssigned`, port, name, and a line at the true end of `OnInit` |
| O-16 | low | `entry:113-117` | `OnDeInit` unguarded, leaves LEDs/pads lit, deinit message meaning unknown | Guard; on deinit send the pad-black frames and restore LEDs (after confirming what `02 7D 7D 0B 00` does) |
| O-17 | low | `Return.py:310,86-90,18-19,38-44` | Save LED (`65`) forced on every tick so Sequencer mode has no indicator; `CountdownReturn` dead; module constants `COLOR_PLAY_*` unused and inconsistent (`OFF=00` vs local `09`); `COLOR_MAP` labels swapped | Light `65` from `SEQ_MODE`; remove dead code |
| O-18 | low | `Display.py:34,37` | Scroll speed 1 char/1.5 s (community 0.5 s) | 400-500 ms |
| O-19 | info (UNVERIFIED) | `Return.py:285` | `getCurrentTempo(1)` unit ambiguity (section 3.4) may break the fake 16th-note playhead | Print both forms on `tom`, then fix `tresh` |
| O-20 | info (UNVERIFIED) | `Return.py` RGB frames | Trailing `7F`, 5-bit vs 7-bit colour, and the two undecoded messages | Keep byte-exact until measured |

---

## 6. Claims from THREAD.md, checked

| Claim (prior assistant) | Verdict | Evidence |
|---|---|---|
| Cause is an `OnInit` exception leaving `_mk2`/`_processor` undefined, so every callback NameErrors | Partially correct mechanism, wrong for this install | True only for an exception inside `init()` (no API calls there, no plausible trigger); post-`init()` failures leave both defined [SIM E1/E2, 3.1] |
| `import ArturiaCrossKeyboardKLmk2` "kills the whole script if that module isn't in the folder" | Mechanism correct, hypothesis refuted here | Module exists; a missing helper makes the script fail to load [SIM E3]. It is also imported by `Return.py:9` and `Process.py:10` |
| "The original ran 9 LED routines on every OnIdle tick (~20 ms); that can flood the SysEx port" | Correct in direction, imprecise in count | 8 LED routines + `RefreshTime` + LCD refresh = **22-24 SysEx/tick**, 1,200 msg/s at 50 Hz [SIM]; community confirms the throttling concern [COMM] |
| "The original showed the splash and then immediately replaced it with the main page" | **Incorrect** | Welcome shows at t=0; `main` first appears at t=2.94 s, after the 2.92 s blocking LED animation [SIM] |
| "Lines are clipped to the 16-character display" (as an improvement) | Already true in stock | `Display.py:44-58` slices to 16 |
| "It no longer crashes when no channel is selected" | Addresses a non-issue | `selectedChannel()` returns 0, not -1 [DOC]; stock does not crash even forced to -1 [SIM] |
| "Nothing is sent unless an output port is assigned" (their version) | Correct as a goal; stock never checks | `grep`: no `isAssigned` in the set |
| DAW input port on Windows is `MIDIIN2 (KeyLab mkII 88)`, output `MIDIOUT2` | Correct | [GUIDE p.4 Fig.2], Arturia support article |
| Give the DAW script port "say 10" | Wrong / risky | Guide uses 0 (DAW) and 1 (MIDI); 10 is the Analog Lab input port (O-11, `01-official-guide.md` C1) |
| "Set DAW mode to the FL Studio / Arturia DAW option if firmware offers one" | Underspecified | Guide p.4: long-press DAW, select program, create the FL Studio memory slot; Arturia's support article instead says Default MCU. Unknown which applies |
| Expect `init OK (processor=yes)` | Their own print | FL's own success line is `init ok` [DOC manual] |

---

## 7. Recommended output layer design (summary of Appendix B and what remains)

Implemented and tested in the patch:

1. One guarded sender: `isAssigned` check, `try/except`, log-once warnings, returns success.
2. Shadow state keyed by frame type + LED id; send on change; **2 s keep-alive** so LEDs self-heal after keyboard resets.
3. LCD: 35 ms minimum gap with automatic retry (cache only on success); ASCII sanitising per character.
4. `resync()` on `OnInit` and on the memory-switch `OnSysEx`, clearing both the shadow and the LCD cache.
5. Callback wrappers with log-once tracebacks; `_mk2`/`_processor` default `None`; early returns.
6. `OnIdle` LED pass at 10 Hz; LCD/`RefreshTime` still every tick.

Still to do (not in the patch):

- Reset helper-module globals in `OnInit` and clamp `CH_OFFSET`/`MX_OFFSET` (O-08).
- Drop or spread the 2.9 s animation (O-12) and make `OnRefresh` flag-aware (O-07).
- Move state LEDs fully event-driven and use the step-change trigger for the playhead (mk3 pattern).
- Decide the Forward-script/DAW-script output routing (O-09), after testing on hardware.
- Fix channel-index consistency (O-13), pad LED orientation on the 88 (O-10), and the Save LED (O-17).

---

## 8. Hardware verification checklist for `tom`

Use a throwaway probe script's `OnInit`, **not** the Script output Interpreter tab, for `device.*` calls: the stub warns that
calling device functions from an interpreter not associated with a device can crash FL [DOC: `device/__device.py:45-62`].

1. Record Script output for the stock script: which of the three `###` lines appear, any traceback, and FL's `init ok`.
2. In a probe `OnInit` print `device.isAssigned()`, `device.getPortNumber()`, `device.getName()`,
   `device.getDeviceID().hex()`, `ui.getProgTitle()` (does it carry the project name?), and both
   `mixer.getCurrentTempo(0)` and `mixer.getCurrentTempo(1)`.
3. Isolate port/mode from script logic by sending single frames from the probe:
   - Play LED on: `F0 00 20 6B 7F 42 02 00 10 6D 7F F7`
   - LCD: `F0 00 20 6B 7F 42 04 00 60 01 48 45 4C 4C 4F 00 02 57 4F 52 4C 44 00 7F F7` ("HELLO" / "WORLD")
   - Pad 1 red: `F0 00 20 6B 7F 42 02 00 16 70 7F 00 00 7F F7`, and again without the trailing `7F` to see whether it matters.
4. Measure the real idle rate (count `OnIdle` calls per `time.monotonic()` second) to replace the 20 ms vs 45 ms guess.
5. Flood test: run stock for a minute, watch for LCD lag/lockup; capture with a MIDI monitor (MIDI-OX or Windows MIDI Services
   console) to count SysEx/s actually leaving. Repeat with the Appendix B patch.
6. Non-ASCII: rename the selected channel to `Caf` + e-acute and confirm the `UnicodeEncodeError` in Script output.
7. Power-cycle the keyboard (or switch memory) while FL is running and check whether the LCD stays blank (O-05).
8. In Sequencer mode press bottom-left pad and see which physical pad lights (O-10).
9. Confirm whether the OS/driver lets another app hold MIDIIN2/MIDIOUT2 (Arturia MIDI Control Center, Analog Lab standalone).
10. Identify which keyboard configuration the user has: the FL Studio memory slot (guide p.4) or Default MCU (Arturia article).

---

## 9. Open questions

- What does firmware do with the trailing `7F` of RGB frames, `02 7D 7D 0B 00`, and `02 00 00 15 00`?
- What does real FL's `midiOutSysex` do with no output assigned (no-op vs exception)?
- Real `OnIdle` rate in FL 2025 on Windows 11?
- Does `ui.getProgTitle()` include the project name?
- Do the scripts run in separate Python interpreters, and does `device_KeyLabmkII` imported by the Forward script share
  globals with the DAW script's entry module?
- Which keyboard mode is the user in (guide's FL memory vs Default MCU)?
- Does the 88's pad LED numbering match the community's "flipped" layout?

---

## Appendix A. Selected simulation results (unmodified stock)

Baseline `OnInit`: 241 SysEx, 3,640 B, 2.920 s of virtual sleep; LCD frames at t=0.00 (welcome) and t=2.94 (`1 - Kick` /
`Pattern 1`).

Steady-state `OnIdle`, 2 s window after 4 s settle:

| Scenario | SysEx/tick | msg/s | bytes/s |
|---|---|---|---|
| Channel Rack focused, drum mode, stopped | 24.0 | 1,200 | 15,750 |
| Mixer focused, drum mode | 24.0 | 1,200 | 15,750 |
| Playlist focused | 22.0 | 1,100 | 14,550 |
| `MIXER_MODE=1`, Mixer focused | 24.0 | 1,200 | 15,750 |
| `SEQ_MODE=1`, playing 120 bpm, beat callbacks | 26.8 (24-42) | 1,340 | 17,838 |

Failure injection: non-ASCII title at `OnInit` -> `UnicodeEncodeError` at `Display.py:58`, 200/200 idle ticks raise, 0 LED
frames; renamed channel -> 100/100 raise, 0 frames, recovers on rename-back; `CH_OFFSET=2` with 4 channels ->
`IndexError` at `Return.py:201`; `getCurrentStepParam == -1` -> `ValueError: bytes must be in range(0, 256)`;
constructor failure -> `NameError` on `OnIdle`/`OnRefresh`/`OnUpdateBeatIndicator`/`OnDeInit` (`_mk2`) and `OnMidiMsg`
(`_processor`); missing helper -> `ModuleNotFoundError` at import.

Patched vs stock, same harness:

| Metric | Stock | Patched |
|---|---|---|
| Steady OnIdle output (rack focused) | 1,200 msg/s, 15,750 B/s | 12 msg/s, 158 B/s |
| Sequencer mode, playing | 1,340 msg/s | 39 msg/s |
| Non-ASCII title at `OnInit` | `OnInit` aborts; 0 LED frames in 4 s | completes; animation and LEDs run; text folds to ASCII |
| Non-ASCII channel name | `OnIdle` dead | no error; LEDs continue |
| LCD after memory-switch `OnSysEx` | 0 frames | 1 frame |
| 100-step fader sweep in 1 s | 100 LCD frames | 25 (+1 trailing) |
| `init()` constructor failure | `NameError` every callback | no error, logged once |
| Output unassigned (either behaviour) | dark or raises | one warning, no exceptions |

## Appendix B. Tested patch (output layer only)

Applies to `KeyLabmk2Dispatch.py`, `KeyLabmk2Display.py` and `device_KeyLabmkII.py`. Validated only in the Linux
simulation (stub FL host); not run in FL. Unified diff against the stock files (line endings normalised for the diff):

```diff
--- a/KeyLabmk2Dispatch.py
+++ b/KeyLabmk2Dispatch.py
@@ -1,6 +1,7 @@
 # MIT License
 # Copyright (c) 2020 Ray Juang
 
+import time
 import device
 
 
@@ -62,5 +63,52 @@
 
 
 
-def send_to_device(data) :
-    device.midiOutSysex(bytes([0xF0, 0x00, 0x20, 0x6B, 0x7F, 0x42]) + data + bytes([0xF7]))
+# --- output layer (audit patch) ---------------------------------------------------------
+HEADER = bytes([0xF0, 0x00, 0x20, 0x6B, 0x7F, 0x42])
+LCD_MIN_GAP_S = 0.035  # community-tested safe LCD frame spacing (rjuang arturia_display.py:5-9)
+KEEPALIVE_S = 2.0      # an unchanged frame is re-sent at most this often (self-heals after keyboard power-cycle)
+_shadow = {}           # frame key -> (payload, time sent)
+_warned = set()
+_last_lcd = 0.0
+
+
+def _warn_once(tag, msg):
+    if tag not in _warned:
+        _warned.add(tag)
+        print("KeyLab mkII: " + msg)
+
+
+def resync():
+    """Forget what we believe the keyboard is showing (call after OnInit / memory switch / reconnect)."""
+    _shadow.clear()
+
+
+def _key(data):
+    # LED frames  02 00 10|16 <id> ...  are keyed on their first 4 bytes, LCD frames 04 00 60 ... on 3
+    return bytes(data[:4]) if data[:1] == b'\x02' else bytes(data[:3])
+
+
+def send_to_device(data):
+    """Send one Arturia SysEx payload. Returns True only if it was actually handed to FL."""
+    global _last_lcd
+    data = bytes(data)
+    try:
+        if not device.isAssigned():
+            _warn_once('noout', "no MIDI OUTPUT is assigned to this script - LEDs/LCD will stay dark. "
+                                "Give the DAW output (MIDIOUT2) the same port number as its input.")
+            return False
+        now = time.monotonic()
+        k = _key(data)
+        prev = _shadow.get(k)
+        if prev is not None and prev[0] == data and now - prev[1] < KEEPALIVE_S:
+            return False
+        if data[:3] == b'\x04\x00\x60':
+            if now - _last_lcd < LCD_MIN_GAP_S:
+                return False          # KeyLabDisplay keeps _last_payload unchanged, so OnIdle retries
+            _last_lcd = now
+        device.midiOutSysex(HEADER + data + b'\xF7')
+        _shadow[k] = (data, now)
+        return True
+    except Exception as e:
+        _warn_once('send:' + type(e).__name__, "midiOutSysex failed: %r" % (e,))
+        return False
--- a/KeyLabmk2Display.py
+++ b/KeyLabmk2Display.py
@@ -3,10 +3,17 @@
 
 
 import time
+import unicodedata
 
 from KeyLabmk2Dispatch import send_to_device
 
 
+def ascii_line(text):
+    """LCD-safe text: fold accents (Cafe), replace anything else with '?', drop control chars."""
+    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'replace').decode('ascii')
+    return ''.join(c if 0x20 <= ord(c) < 0x7F else ' ' for c in text)
+
+
 class KeyLabDisplay:
     """ Manages scrolling display of two lines so that long strings can be scrolled on each line. """
     def __init__(self):
@@ -86,8 +93,11 @@
 
         self._update_scroll_pos()
         if self._last_payload != data:
-            send_to_device(data)
-            self._last_payload = data
+            if send_to_device(data):
+                self._last_payload = data
+
+    def Invalidate(self):
+        self._last_payload = bytes()
 
     def ResetScroll(self):
         self._line1_display_offset = 0
@@ -101,6 +111,10 @@
         :param expires:  number of milliseconds that the line persists before expiring. Note that when an expiration
             interval is provided, lines are interpreted as a blank line if not provided.
         """
+        if line1 is not None:
+            line1 = ascii_line(line1)
+        if line2 is not None:
+            line2 = ascii_line(line2)
         if expires is None:
             if line1 is not None:
                 self._line1 = line1
--- a/device_KeyLabmkII.py
+++ b/device_KeyLabmkII.py
@@ -20,11 +20,34 @@
 from KeyLabmk2Return import KeyLabLightReturn
 from KeyLabmk2Display import KeyLabDisplay
 from KeyLabmk2Pages import KeyLabPagedDisplay
-from KeyLabmk2Dispatch import send_to_device
+from KeyLabmk2Dispatch import send_to_device, resync
 
 ## CONSTANT
 
 TEMP = 0.5
+_mk2 = None
+_processor = None
+_last_led_pass = 0.0
+LED_PASS_S = 0.1
+_errs = {}
+
+
+def _log_once(where):
+    import traceback
+    key = (where, traceback.format_exc().splitlines()[-1])
+    if key not in _errs:
+        _errs[key] = 1
+        print("KeyLab mkII: exception in %s (further repeats suppressed)\n%s" % (where, traceback.format_exc()))
+
+
+def _safe(fn):
+    def wrapper(*a, **k):
+        try:
+            return fn(*a, **k)
+        except Exception:
+            _log_once(fn.__name__)
+    wrapper.__name__ = fn.__name__
+    return wrapper
 HW_Flag = {"Select" : [295, 263, 256]} 
 
 
@@ -81,16 +104,20 @@
 # Function called for each event 
 
 
+@_safe
 def OnMidiMsg(event) :
-    process = _processor.ProcessEvent(event)
+    if _processor is not None:
+        _processor.ProcessEvent(event)
 
 
 
 # Functions called when FL Studio is starting
 
 
+@_safe
 def OnInit():
-    print("### INIT KEYLAB mkII OKAY ###")
+    print("### KeyLab mkII: OnInit start ###")
+    resync()
     init()
     _mk2.Sync()
     _mk2.paged_display().SetPageLines('welcome', line1='KeyLab mkII', line2=ui.getProgTitle())
@@ -101,16 +128,20 @@
     
 
 def init() :
-    print("### Successfully created class objects ###")
-    global _mk2 
+    global _mk2, _processor
+    _mk2 = None
+    _processor = None
     _mk2 = MidiControllerConfig()
-    global _processor
     _processor = KeyLabMidiProcessor(_mk2)
+    print("### KeyLab mkII: class objects created ###")
   
 
 # Handles the script when FL Studio closes
 
+@_safe
 def OnDeInit():
+    if _mk2 is None:
+        return
     _mk2.paged_display().SetPageLines('goodbye', line1='KeyLab mkII', line2='Disconnected')
     _mk2.paged_display().SetActivePage('goodbye')
     send_to_device(bytes([0x02, 0x7D, 0x7D, 0x0B, 0x00]))
@@ -119,7 +150,10 @@
   
 # Function called when Play/Pause button is ON
 
+@_safe
 def OnUpdateBeatIndicator(value):
+    if _mk2 is None:
+        return
     _mk2.LightReturn().ProcessPlayBlink(value)
     _mk2.LightReturn().ProcessRecordBlink(value)
     _mk2.LightReturn().ProcessSequencerBlink(value)
@@ -128,7 +162,10 @@
 
 # Function called at refresh, flag value changes depending on the refresh type 
 
+@_safe
 def OnRefresh(flags) :
+    if _mk2 is None:
+        return
     _mk2.Sync()
     _mk2.LightReturn().SequencerReturn()     
     _mk2.LightReturn().PlayReturn()
@@ -138,9 +175,17 @@
 
 # Function called time to time mainly to update the beat indicator
 
+@_safe
 def OnIdle():
+    global _last_led_pass
+    if _mk2 is None:
+        return
     _mk2.Idle()
     _mk2.LightReturn().RefreshTime()
+    now = time.monotonic()
+    if now - _last_led_pass < LED_PASS_S:
+        return
+    _last_led_pass = now
     _mk2.LightReturn().MetronomeReturn()
     _mk2.LightReturn().LoopReturn()
     _mk2.LightReturn().NotBlinkingLed()
@@ -154,8 +199,12 @@
     
 # Function called on a memory switch
 
+@_safe
 def OnSysEx(event) :
     if event.sysex == b'\xf0\x00 k\x7fB\x02\x00\x00\x15\x00\xf7' :
+        resync()
+        if _mk2 is not None:
+            _mk2.display()._last_payload = bytes()
         ui.setFocused(1)
         OnRefresh(32)
```

Notes on the patch:

- `unicodedata` ships with FL 2025's embedded Python 3.12 (`Shared/Python/unicodedata.pyd`, stdlib in `python312.zip`). Wrap the
  import in `try/except ImportError` with a plain `encode('ascii','replace')` fallback if it fails inside FL.
- The patch deliberately keeps every byte string identical to stock (including the RGB trailing `7F` and the deinit frame).
- It does not fix O-07, O-08, O-09, O-10, O-12, O-13 (see section 7).
