# 02 - Input-side audit: everything the KeyLab mkII sends TO FL Studio

Role: "input side" auditor for the stock Arturia KeyLab mkII FL Studio script set (2021, byte-identical to what the user
runs). Scope: `KeyLabmk2Process.py`, `KeyLabmk2Navigation.py`, `KeyLabmk2SeqParam.py`, `KeyLabmk2Plugin.py`,
`ArturiaCrossKeyboardKLmk2.py`, `ArturiaVCOL.py`, `KeyLabmk2Dispatch.py`, `device_Forward CCs Port 10 KEYLAB MKII.py`
(plus the entry script `device_KeyLabmkII.py` where it routes events). Output side (LEDs, LCD, init) is covered by
`03-output-audit.md`; guide facts by `01-official-guide.md`; prior art by `05-prior-art.md`. This file does not repeat them
except where the input side depends on them.

Nothing here was run on FL Studio or on the keyboard (host `tom` is unreachable). Evidence tags used throughout:

- **[STATIC]** read directly from a local file (file:line).
- **[SIM]** reproduced in the Linux-side simulation (section 1.2). Reproduces the script's own logic, not FL's.
- **[DOC]** FL API stubs (`IL-Group/FL-Studio-API-Stubs`, commit `9b4c7fa`, 2026-05-13), FL online manual text, or the real
  FL 2025 `midi.py`.
- **[VENDOR]** Image-Line's own `MackieCU` script in the same Hardware folder (mtime 2026-01-13, i.e. FL 2025-era) or Arturia's
  own 2024 `KeyLab mk3` script - used as ground truth for how FL behaves and how Arturia itself changed its approach.
- **[GUIDE p.N]** the Arturia PDF shipped in the script folder (PDF page numbers, 17 pages).
- **UNVERIFIED** could not be confirmed without the hardware or a running FL.

Paths: `KL2` = `/home/delorenj/Documents/Image-Line/FL Studio/Settings/Hardware/Arturia KeyLab MKII`. Line numbers refer to
the files as read (CRLF files; numbering unaffected).

---

## 0. Bottom line

1. **No input-side defect makes the script raise on every event.** In a fuzz of 300,000 random events x random FL states through
   `ProcessEvent` there was exactly one exception site (`ReleaseBit`, notes outside 36..51) and it needs an unusual note.
   With a strict-index API there were four more (mixer track 127/128 at the last bank). All 92 FL API symbols the set uses
   resolve in the May-2026 stubs and in FL 2025's `midi.py`; all 12 files compile under Python 3.12 with warnings as errors
   [SIM]. So the stock input path is not "dead by exception"; it is dead-by-assumption or broken in specific modes.
2. **The input side hard-codes a protocol contract nobody has verified on this hardware** (button = note-on ch1 with velocity
   127/0, encoders = CC16..24 sign-magnitude relative, jog = CC60 +-1, faders = pitch-bend ch1..9, pads = ch10 notes 36..51).
   That contract matches the Mackie Control (MCU) family, but the keyboard's DAW map decides what it really sends: the guide
   says use the "Live" program [GUIDE p.4]; Arturia's current FAQ says "Default MCU" with FL's stock Mackie script
   (`05-prior-art.md` section 2). If the DAW map differs from what the script assumes, nearly every control silently does
   nothing (everything unmapped is swallowed, see F-03). This is the top "doesn't work at all" suspect on the input side and can
   be settled in five minutes with the raw-event monitor in section 8.
3. **The Forward script runs the full command processor from `OnMidiIn`** on the keybed port (`device_Forward...:29-47`). The
   FL manual says `OnMidiIn` only carries raw fields; the script relies on `midiId`. Either outcome is bad: if `midiId` is
   populated, 15 of the 88 keys (46, 47, 51, 56, 74, 84, 86, 87, 91-95, 98, 99) fire transport/window/pattern actions while
   playing; if it is not (what the manual implies), the Analog-Lab-CC path raises `TypeError` and swallows the CC
   ([SIM], hypotheses H1/H2, section 3.3). Arturia's own 2024 mk3 script moved this logic to `OnMidiMsg`.
4. **Confirmed functional bugs [SIM]:** pad velocity is overwritten with 144/128 (`Process.py:268,277`); pads are remapped to
   FPC notes for every instrument (`:261-278`); one pad press in *song* mode leaves `EDIT_MODE=1` forever, hijacking all nine
   encoders (`:272-274,665-698`); mixer pan/select index 127/128 at bank 15 (`:412,431,641`); `handled` flag leaked by three
   helpers (event goes on to FL after being processed); Analog-Lab CC handlers registered with the wrong call signature
   (`:179-196` vs `:473`); pitch encoder direction inverted in step edit (`SeqParam.py:38`); MOD Y written up to 254
   (`SeqParam.py:100`); stale `CH_OFFSET` makes `Return.SelectedChannel` raise every idle tick (`Return.py:201`).
5. **Design gaps** (section 7): no pickup on the non-motorized faders, direct `setTrackVolume` bypasses FL's automation
   recording, a hard-coded 15-plugin parameter database with no fallback, fixed pan/step increments that ignore tick
   magnitude, no bank clamp to the real track/channel count, Shift step-parameter (documented in the guide) not implemented.
6. Claims in `THREAD.md` that touch the input side: the "missing import" hypothesis is **incorrect** (all helpers exist and
   import; the unused `import ArturiaCrossKeyboardKLmk2` at `device_KeyLabmkII.py:16` is harmless); "give the DAW port number 10"
   is **incorrect** (guide p.4-5 uses port 0 for DAW and 1 for the keyboard; 10 is the *plugin-side* input port, guide p.6).

---

## 1. Method

### 1.1 What was read

Every file in scope, in full, plus `KeyLabmk2Return.py`, `KeyLabmk2Display.py`, `KeyLabmk2Pages.py` for the code that input
handlers call into; the guide PDF pages 3-17 (text and figures); the FL manual text; the API stubs; FL 2025's `Shared/Python/Lib/midi.py`
and `utils.py`; Image-Line's `MackieCU` and Arturia's mk3 scripts for comparison; the plugin DLLs of the local FL 2025 install (wine
prefix) for plugin-name strings.

### 1.2 The simulation

Scratch code (not committed) at `.../scratchpad/sim/`:
`harness.py` (event + loader), `fakes/` (fake `device`, `ui`, `channels`, `mixer`, `patterns`, `transport`, `plugins`,
`playlist`, `arrangement`, `general`, plus FL 2025's real `midi.py`), and tests `t1_map.py` ... `t12_idle.py`.
It imports the **unmodified stock files** under Python 3.12.9 (FL embeds 3.12) and feeds them events.

Event model (`FlMidiMsg`, from the stubs `fl_classes/__init__.py`): `controlNum`/`note`/`pressure`/`progNum` are shadows of
`data1`; `controlVal`/`velocity` shadow `data2`; `midiId = status & 0xF0` and `midiChan = status & 0x0F` in the `OnMidiMsg`
context (proved by Image-Line's own `MackieCU`: faders are `event.midiId == midi.MIDI_PITCHBEND` with `event.midiChan <= 8`,
`device_MackieCU.py:281-283`; CC uses `midiChan == 0`, `:249-250`). An option models the `OnMidiIn` hypothesis (`midiId = 0`).

Limits: FL API fakes return defaults; what FL does with an event **after** the script (default note routing, link system) is not
modelled; behaviour of FL API calls on invalid indices is unknown (so those are flagged, not asserted).

### 1.3 Reproduce

```
PY=/home/delorenj/.local/share/mise/installs/python/3.12.9/bin/python3
cd .../scratchpad/sim && $PY t1_map.py && $PY t2_bugs.py && $PY t3_fwd.py && $PY t5_fuzz.py 300000 strict
```

---

## 2. The input contract the code assumes, and what corroborates it

| Control | Message the code expects | Where assumed |
|---|---|---|
| Buttons (transport, DAW commands, select, bank) | Note-on, channel 1 (`0x90`), data1 = button id, velocity 127 = press, **note-on velocity 0 = release** | `Process.py:118` (only midiId 144), `_is_pressed` `:103-104` |
| Jog (main knob) | CC 60, data2 exactly `1` (CW) or `65` (CCW) | `Process.py:164-174` |
| 9 encoders | CC 16..24, relative sign-magnitude (1..63 CW, 65..127 CCW; `0x40` = zero) | `Process.py:166`, `AKLmk2.py:38-39` |
| 9 faders | Pitch-bend on channels 1..9 (`0xE0..0xE8`), only MSB (`data2`) used | `Process.py:213`, `AKLmk2.py:12` |
| 16 pads | Note-on `0x99` / note-off `0x89` (channel 10), notes 36..51 | `Process.py:128-129,261-278,206` |
| Mod wheel, pitch wheel, keybed | Not in the DAW-port path; arrive on the *keyboard* port | Forward script |

Corroboration (all [DOC]/[VENDOR]/[GUIDE]):

- The *shape* is the Mackie-Control family's. Image-Line's `MackieCU` (Jan 2026) uses the same for: V-pots CC `0x10-0x17`
  (`device_MackieCU.py:261`), jog CC `0x3C` (`:257`), sign-magnitude relative decode `inEv >= 0x40 -> -(inEv-0x40)` (`:252-253`),
  faders as pitch bend on `midiChan <= 8` (`:281-283`), transport notes `0x5B/0x5C/0x5D/0x5E/0x5F` (`:417-434`) and mixer bank
  `0x2E/0x2F` (`:335`). Those match the Arturia script exactly.
- The *button ids beyond that differ from stock MackieCU*: Arturia uses `0x54` for the jog push (MackieCU: Shift, `:389`), `0x4A` for
  "Save"/sequencer toggle (MackieCU: focus browser, `:495`), `0x51` for Undo (MackieCU: menu, `:503`; its Undo is `0x3D`, `:513`),
  `0x59` for metronome (MackieCU: mode, `:438`; its metronome is `0x57`, `:399`), `0x56` for loop (MackieCU: snap, `:442`), `0x57`/`0x58`
  for In/Out (MackieCU: metronome/precount). So the script targets a *custom* DAW program (the guide's "Live" program,
  [GUIDE p.4]), not stock MCU, and running FL's `MackieCU` on the same keyboard would map those buttons differently. Arturia's FAQ
  for FL uses the stock MCU map (`05-prior-art.md`). **UNVERIFIED which one the keyboard is set to**, and the guide never lists the
  notes/CCs (`01-official-guide.md` section 6, question 2).
- Port wiring that matters for input routing [GUIDE p.4-5 Fig.2]: DAW input (`MIDIIN2 (KeyLab mkII 88)`) -> `KeyLab mkII`
  script, port **0**; keyboard port (`KeyLab mkII 88`) -> `Forward CCs ...` script, port **1**; outputs with matching numbers.
  "MIDI input 10" [GUIDE p.6 Fig.5-6, p.16] is the Arturia *plugin's* input port, the `10 << 24` in
  `Forward...:41`. `THREAD.md`'s "assign the DAW port number 10" contradicts this.

---

## 3. Event routing

### 3.1 Two entry points

```
DAW port  (script "KeyLab mkII")            -> device_KeyLabmkII.OnMidiMsg -> _processor.ProcessEvent(event)      [entry:84-85]
keyboard port (script "Forward CCs ...")    -> Forward.OnMidiIn -> (forward | KL._processor.ProcessEvent(event))  [Forward:29-47]
                                            -> Forward.OnMidiMsg -> handled=False                                 [Forward:49-50]
                                            -> Forward.OnPitchBend (wheel)                                        [Forward:70-75]
```

### 3.2 `ProcessEvent` decision table (`Process.py:227-233`)

`if event.status == event.midiId or event.midiId == 224` -> **id dispatcher** (key = `midiId`); else -> **status dispatcher**
(key = `status`). With `midiId = status & 0xF0` this means:

| Incoming | Branch | Handler | Notes |
|---|---|---|---|
| `0x90` note-on ch1 | id dispatcher, key 144 | `OnCommandEvent` -> `handled=True`, then command table by `controlNum` | **every** unmapped note is swallowed (`:236`) |
| `0xB0` CC ch1 | id, key 176 | `OnKnobEvent` -> `handled=True`, then knob table (CC 60, 16..24) | **every** other CC on ch1 is swallowed (CC1, CC7, CC11, CC64, 28, 29, 74 ...) [SIM] |
| `0xE0..0xE8` pitch-bend | id, key 224 (midiId is 224 for all nine channels) | `OnSliderEvent` -> `handled=True`, then `status` table 224..232 | |
| `0x99` / `0x89` (pads) | status dispatcher (status != midiId) | `OnDrumSeqEvent` | only place the status table is reachable in `OnMidiMsg` |
| `0xB0` via status dispatcher | **unreachable** in `OnMidiMsg` (status == midiId always) | `OnPluginEvent` (`:126`) | dead there; alive only if `midiId != status` (Forward `OnMidiIn`, H2) |
| `0x80`, `0xA0`, `0xC0`, `0xD0`, sysex, other channels | id/status dispatch finds no key | none, `handled` untouched | pass through to FL default handling |

### 3.3 The `OnMidiIn` problem (Forward script) - hypotheses H1 / H2

The manual [DOC, `midi_scripting.txt:183`] says of `OnMidiIn`: "Only raw data is available here: handled, timestamp, status,
data1, data2, port, sysex, pmeflags. Use this event for filtering; use OnMidiMsg for actual processing." The stub author notes
`midiChan` "always seems to be zero" ([DOC] `fl_classes` docstring), consistent with derived fields being unset at that stage.
`ProcessEvent` needs `midiId`. Results, keybed notes and CCs sent through `Forward.OnMidiIn` [SIM `t3_fwd.py`]:

| Case | H1: `midiId` populated in `OnMidiIn` | H2: `midiId == 0` in `OnMidiIn` (what the manual implies) |
|---|---|---|
| Keybed note-on ch1, keys 21..108 | **15 of 88 keys fire actions**: 46/47 `globalTransport(FPT_Punch,1)`; 51 mixer/CR toggle + `_hideAll`; 56 tap tempo; 74 seq toggle; 84 `channels.showEditor` toggle; 86 loop-record; 87 browser toggle; **91/92 `transport.continuousMove(+-1, start)` (never stopped: the release is a note-off 0x80, not routed)**; 93 stop; 94 play/pause; **95 record**; 98/99 `jumpToPattern(+-1)`. `handled=False` afterwards so the note also sounds. | none |
| Pad `0x99` note 36 (drum mode) | remapped, velocity 144 | same |
| Analog-Lab preset CC 74 with a non-Arturia plugin focused (FLEX) | goes to `OnKnobEvent`; no CC 74 handler; harmless | `OnPluginEvent` sets `handled=True`, then `_plugin_dispatcher` calls `self.Plugin(event)` with one argument -> **`TypeError: Plugin() missing 1 required positional argument: 'clef'`** (`Dispatch.py:56`), exception leaves `handled=True` -> **CC swallowed** |
| Mod wheel CC1, mixer mode | harmless | `_plugin_dispatcher[1] = SetPanTrack` -> `track = (1-15)+8*MX_OFFSET = -14` -> **`mixer.getTrackPan(-14)`** |
| CC 28/29 with plugin focused | ignored | `plugins.nextPreset/prevPreset` works |

Which one is true is **UNVERIFIED**; section 8 has a monitor that prints `midiId` in both callbacks. H2 is more consistent with
the manual and with the product having shipped; H1 is catastrophic. Either way the design is wrong (F-01/F-02).

Also, in both hypotheses `Forward:46-47` (`if ProcessEvent(event): event.handled = False`) **overrides** the deliberate
`handled=True` from `OnDrumSeqEvent` (`Process.py:264`): in Sequencer mode a pad press processed on this path also plays
the note on the selected channel [SIM `t10_fwdseq.py`].

### 3.4 Shared state between the two scripts (UNVERIFIED)

`Forward:19,27,46` does `import device_KeyLabmkII as KL; KL.init(); KL._processor.ProcessEvent(...)`. If FL runs each device
script in its own interpreter (the stubs warn that calling device functions "in an interpreter not associated with a device
causes FL Studio to crash", `device/__device.py:53`; `03-output-audit.md` section 3.8), then `SEQ_MODE`, `MIXER_MODE`,
`MX_OFFSET`, `CH_OFFSET`, `RECT_OFFSET`, `EDIT_MODE`, `STATE_MATRIX` exist **twice** and never sync. Example consequence: the
Save button (note 74) arrives on the DAW port and toggles the DAW copy of `SEQ_MODE`; if the pads arrive on the keyboard port the
Forward copy is still 0 and the step sequencer can never work. My simulation assumes a single shared copy (best case).

---

## 4. Code-derived mapping table

Hardware names in the last column are from the guide's Fig.22/25 and the overlay JPG; button-to-note pairings are inferred from
code plus those labels and are UNVERIFIED (the guide lists no note numbers).

### 4.1 State variables that change what a control does

| State | Defined | Changed by | Read by | Notes |
|---|---|---|---|---|
| **Focused window** (external, `ui.getFocused`) | FL | user, `_show_and_focus`, `ui.setFocused` | jog, note 84, solo/mute, `Plugin`, LEDs | the real "page" state machine: Browser(4) / Mixer(0) / ChannelRack(1) / any plugin(5) / other |
| `MIXER_MODE` 0/1 | `Process.py:44` | note 51 (`:335-345`) | banks, select, faders, encoders, LEDs | **not tied to the focused window** |
| `SEQ_MODE` 0/1 | `:41` | note 74 (`:347-355`) | pads, `<<`/`>>`, LEDs | |
| `AKLmk2.MX_OFFSET` 0..15 | `AKLmk2.py:8` | notes 46/47 in mixer mode | faders, encoders, select, LEDs | max 15 (`:412`) |
| `AKLmk2.CH_OFFSET` 0..n | `AKLmk2.py:9` | notes 46/47 otherwise | select, LEDs | bound by `channelCount()` at press time only |
| `RECT_OFFSET` 0..inf | `Process.py:47` | `<<`/`>>` in SEQ_MODE | pad->step index, LEDs | unbounded upward (`:504`) |
| `EDIT_MODE` 0/1 | `:50` | `HoldBit` sets 1; `ReleaseBit` clears/re-sets | encoders (`SetPanTrack:621`) | see F-04 |
| `STATE_MATRIX[4][4]`, `INDEX_PRESSED` | `:59-73` | `HoldBit`/`ReleaseBit`, `SetPanTrack:624-628` | step edit | |
| `SEQ_PARAM` 0/1 | `:53` | `PressSequencer`, `SetPanTrack:631` | `ReleaseBit:742` (suppresses step toggle after a tweak) | never reset on release |
| `SeqParam.PAGE`, `SeqParam.ABSOLUTE_VALUE` | `SeqParam.py:22,8` | `Param` | `Param` | one accumulator for all steps and params |
| `Plugin.ABSOLUTE_VALUE` | `Plugin.py:9` | `Plugin`, `RelativeToAbsolute` | same | re-seeded from the plugin each event |
| Selected channel / mixer track (FL) | FL | many | most handlers | read via `channelNumber()` (global) |

### 4.2 Buttons: status `0x90`, channel 1

Filter column: "press" = fires on velocity != 0 (`ignore_release`); "release" = fires on velocity 0 (`ignore_press`), so these need the
hardware to send a release event (note-on vel 0).

| data1 | dec | Filter | Handler (`Process.py`) | FL calls | Guide label / guide page |
|---|---|---|---|---|---|
| 0x00-0x07 | 0-7 | press | `SnapMode` `:584` | `ui.snapMode(1)`; LCD `ui.getSnapMode()` | "Record" -> change snap mode, p.12 |
| 0x08-0x0F | 8-15 | release | `SoloChannel` `:563` | ChannelRack focused: `channels.soloChannel(channelNumber())`; Mixer focused: `mixer.soloTrack(trackNumber())`; else nothing; then `FakeMIDImsg` | "Solo", p.12 (all 8 ids identical) |
| 0x10-0x17 | 16-23 | release | `MuteChannel` `:571` | same with `muteChannel` / `muteTrack` | "Mute", p.12 |
| 0x18-0x1F | 24-31 | release | `TrackSelect` `:428` | Mixer mode: `mixer.setTrackNumber((n-23)+8*MX_OFFSET, 3)`; else `ch=(n-24)+8*CH_OFFSET`, if `ch < channelCount()`: `channels.selectOneChannel(ch)`, `mixer.setTrackNumber(getTargetFxTrack(channelNumber()),3)`, `ui.setFocused(1)`; both: `_hideAll` | 8 RGB "Select" buttons, p.13 |
| 0x2E / 0x2F | 46 / 47 | press | `BankSelect` `:403` | Mixer mode: `MX_OFFSET -/+ 1` (`>= 0`, `(off+1)*8 < 125`); else `CH_OFFSET -/+ 1` (`(off+1)*8 < channelCount()`); `FakeMIDImsg`; LCD | "Previous / Next" (offset by 8), p.12-13 |
| 0x33 | 51 | press | `ToggleMixerChannelRack` `:335` | `FakeMIDImsg`; `_hideAll`; `MIXER_MODE ^= 1`; show+focus Mixer(0) or ChannelRack(1) | "Bank"? UNVERIFIED |
| 0x38 | 56 | press | `TapTempo` `:579` | `globalTransport(FPT_TapTempo, 1)` | "Read" -> tap tempo, p.12 |
| 0x39 | 57 | release | `Cut` `:544` | show+focus ChannelRack; `ui.cut()` | "Off" -> "cut the pattern of the selected channel", p.12 |
| 0x4A | 74 | press | `DrumSeqToggle` `:347` | `FakeMIDImsg`; `_hideAll`; `SEQ_MODE ^= 1` | "Save" -> Drum/Sequencer, p.12 |
| 0x51 | 81 | release | `Undo` `:549` | `globalTransport(FPT_Undo, FPT_Undo(=20), event.pmeFlags)` | "Undo", p.12 |
| 0x54 | 84 | press | `SwitchWindow` `:298` | CR or plugin focused: `channels.showEditor(channelNumber())` (toggle); Mixer: `mixer.armTrack(trackNumber())`; Browser: `ui.getFocusedNodeFileType()`: -1 nothing, <= -100 `globalTransport(FPT_Enter,1)`, else `ui.selectBrowserMenuItem()` | main knob push, p.8-9 |
| 0x56 | 86 | press | `Loop` `:539` | `globalTransport(FPT_LoopRecord, 1)` | "Loop" -> loop recording, p.12 |
| 0x57 | 87 | press | `ToggleBrowserChannelRack` `:325` | `FakeMIDImsg`; Browser not focused: show+focus(4) else show+focus(1) | "In", p.12 |
| 0x58 | 88 | release | `Overdub` `:553` | `globalTransport(FPT_Overdub, 1)` | "Out" -> overdub, p.12 |
| 0x59 | 89 | release | `SetClick` `:558` | `globalTransport(FPT_Metronome, 1)` | "Metro", p.12 |
| 0x5B | 91 | none | `RewindORprevBar` `:518` | SEQ_MODE=1 and vel==127: `RECT_OFFSET-=1` (`>=0`), `FakeMIDImsg`, `ui.crDisplayRect(off*16, channelNumber(), 16, 1, 1000)`; SEQ_MODE=0: press `transport.continuousMove(-1, 2)`, release `(-1, 0)` | "<<", p.12 |
| 0x5C | 92 | none | `FastForwardORnextBar` `:500` | mirror of the above with `+1` | ">>", p.12 |
| 0x5D | 93 | press | `Stop` `:495` | `transport.stop()` | "Stop", p.12 |
| 0x5E | 94 | press | `Start` `:490` | `transport.start()` (play/pause) | "Play/Pause", p.12 |
| 0x5F | 95 | press | `Record` `:485` | `transport.record()` (toggle) | "Record", p.12 |
| 0x62 | 98 | press | `previousPattern` `:442` | plugin window focused: `plugins.prevPreset(channelNumber())`; else `patterns.jumpToPattern(patternNumber()-1)` (no lower bound) | not in guide |
| 0x63 | 99 | press | `nextPattern` `:450` | mirror with `+1`; **creates** the pattern if it does not exist [DOC `patterns/__properties.py:165`] | not in guide |
| everything else | | | `OnCommandEvent` `:236` | none, event swallowed | e.g. 32..39 (encoder pushes?), 104..112 (fader touch, MCU) |

### 4.3 Jog and encoders: status `0xB0`, channel 1

For CC 60 every row below applies only to `data2 == 1` (CW) or `65` (CCW).

| CC | Mode (checked in this order) | Handler | FL calls |
|---|---|---|---|
| 60 | data2 not 1 or 65 | `_knob_nav_dispatcher` no entry | nothing; `handled=True` (**multi-tick values dropped**) |
| 60 | plugin window focused (`ui.getFocused(5)`) | `TrackSelectMainKnob` `:363` | `_hideAll` (closes every editor), show+focus ChannelRack |
| 60 | Browser focused | same | popup open: `ui.up()/down()`; else `ui.previous()/next()`; `HintRefresh(ui.getFocusedNodeCaption())` |
| 60 | Mixer focused | same | show+focus Mixer, `_hideAll`, `ui.previous()/next()` |
| 60 | ChannelRack focused | same | `_hideAll`, show+focus CR, `ui.previous()/next()`, `mixer.setTrackNumber(getTargetFxTrack(channelNumber()),3)` |
| 60 | anything else (Playlist, Piano roll, ...) | same | show+focus ChannelRack (`:400-401`) |
| 16..23 | `EDIT_MODE==1` | `SetPanTrack` `:619` -> `SeqParam.Param` | 16 pitch (step param 0, +-1, **inverted**), 17 velocity(1), 18 release(2), 19 fine pitch(3), 20 pan(4), 21 mod X(5), 22 mod Y(6, **x2**), 23 SHIFT: no branch; then `FakeMIDImsg`, `SEQ_PARAM=1` |
| 16..23 | `MIXER_MODE==1` | `SetPanTrack` -> `AKLmk2.SetPanTrack` | `mixer.setTrackPan(1+i+8*MX_OFFSET, getTrackPan + (+-1/20))` |
| 16..23 | Channel Rack mode | `SetPanTrack` -> `self.Plugin(event, clef=CC)` | if `ui.getFocused(5)`: `KeyLabmk2Plugin.Plugin` (DB by `ui.getFocusedPluginName()`): `plugins.getParamValue`, `plugins.setParamValue(new/127, p, channelNumber())` with `new = int(127*cur) +- 2*ticks`; LCD name/%; else LCD "No Plugin Focused" |
| 24 | `EDIT_MODE==1` | `Param` | no branch (side effects only: `closeGraphEditor`, accumulator, `SEQ_PARAM=1`) |
| 24 | `MIXER_MODE==1` | `AKLmk2.SetPanTrack` | master pan: `mixer.setTrackPan(0, ...)` |
| 24 | otherwise | `SetPanTrack:651-657` | `mixer.setTrackPan(trackNumber(), getTrackPan(...) + (+-1/20))` |
| all other | | `OnKnobEvent` `:241` | nothing, swallowed (28/29, 74, 71 ... are only in the dead `_plugin_dispatcher`) |

### 4.4 Faders: status `0xE0 + n` (n = 0..8)

| n | `MIXER_MODE==1` | `MIXER_MODE==0` |
|---|---|---|
| 0..7 | `track = 1+n+8*MX_OFFSET`; if `track < 126`: `mixer.setTrackVolume(track, 0.8*data2/127)`; LCD | `self.Plugin(event, clef=status)`: `ui.getFocused(5)` required; DB param set **absolute** `data2/127`; LCD name/%; else "No Plugin Focused" |
| 8 | `mixer.setTrackVolume(0, 0.8*data2/127)` (master) | `mixer.setTrackVolume(mixer.trackNumber(), 0.8*data2/127)` |

Resolution: only the MSB of the 14-bit pitch-bend is used (128 steps). Max fader = 0.8 = 0 dB (no boost above unity); LCD shows 80 % at the top.

### 4.5 Pads: status `0x99` / `0x89`

| `SEQ_MODE` | Press (`0x99`) | Release (`0x89`) |
|---|---|---|
| 0 (drum) | `data1 = FPC_MAP.get(str(data1))`, **`data2 = 144`**, `handled=False` (`:266-269`) | `data1 = FPC_MAP.get(...)`, **`data2 = 128`**, `handled=False` (`:275-278`) |
| 1 (seq) | `handled=True`; `device.processMIDICC(event)`; `PressSequencer`: `SEQ_PARAM = 1 if graph editor visible else 0`, `HoldBit` (`STATE_MATRIX[bit]=1`, `EDIT_MODE=1`) | pattern mode (`getLoopMode()==0`): `handled=True`, `ReleaseBit`: bit=0, `EDIT_MODE` back to 1 if another pad held else `closeGraphEditor(1)`; if `SEQ_PARAM==0` toggle `channels.setGridBit(channelNumber(), step+16*RECT_OFFSET)`. **Song mode: nothing at all** (F-04) |

`FPC_MAP` (`:76-93`): 36..51 -> 49,55,51,53,48,47,45,43,40,38,46,44,37,36,42,54 (FPC pad layout, guide p.14).

### 4.6 Forward script (keyboard port)

| Event | Behaviour (`Forward` lines) |
|---|---|
| Any event | `ui.getFocusedPluginName()` + linear scan of 32 names (`:33-36`) |
| CC ch1 and focused plugin in `V_COL`, or any `0xE0` | `device.forwardMIDICC(status + data1<<8 + data2<<16 + 10<<24, 2)`, `handled=False` (`:38-43`) |
| everything else | `KL._processor.ProcessEvent(event)`; `handled=False` if it returned True (`:45-47`) |
| `OnPitchBend` (after `OnMidiMsg`) | not V_COL: `channels.setChannelPitch(channelNumber(), (data2-64)*(200/64), 1)`; always `handled=True` (`:70-75`) |

### 4.7 Analog-Lab / plugin path (`_plugin_dispatcher`, `Process.py:177-202`)

CC 74,71,76,77,93,18,19,16,73,75,79,72,80,81,82,83,17 -> `self.Plugin` (**wrong signature**), CC1 -> `SetPanTrack`, CC28/29 ->
`previousPreset`/`nextPreset` (press only). Reachable only via the status dispatcher with `status == 176` (H2). In `OnMidiMsg`
these CCs are swallowed by `OnKnobEvent`.

---

## 5. Bug and risk list

Severity is honest: **nothing is "critical"** (nothing provably raises on every event). "High" = plausible reason for
"doesn't work" or an actual functional break; UNVERIFIED items say why.

| ID | Sev | Where | Problem | Fix (short) |
|---|---|---|---|---|
| F-01 | high (UNVERIFIED which hypothesis) | `Forward:29-47` | Full `ProcessEvent` from `OnMidiIn` on the keybed port; relies on `midiId`; H1 turns 15 keys into transport/window commands (91/92 scrub never stops), H2 raises and swallows | Move to `OnMidiMsg`; in `OnMidiIn` use raw fields only |
| F-02 | high (UNVERIFIED) | `Process.py:126,177-202,253-255`; `Dispatch.py:56` | `_plugin_dispatcher` binds `self.Plugin(event, clef)` via `callback_fn(event)` -> `TypeError` on the 17 Analog-Lab CCs; handled already `True` -> CC swallowed; dead in `OnMidiMsg` | Delete or rewrite with `clef=event.controlNum` |
| F-03 | high (UNVERIFIED) | `Process.py:116-121,235-242,249-251` | Hard-coded hardware contract; unmapped notes/CCs on ch1 are swallowed silently; no logging | Raw monitor (section 8); log-and-pass-through unknown ids |
| F-04 | high [SIM] | `Process.py:261-278,665-698,619-631` | Pad release ignored in song mode (`:272`) -> `STATE_MATRIX`/`EDIT_MODE` stuck -> all encoders edit step 0 pitch, encoder 9 pan dead | Always route 0x89 in SEQ_MODE; clear `STATE_MATRIX` on mode/loop change |
| F-05 | high [SIM] | `Process.py:268,277` | `event.data2 = MIDI_NOTEON (144)` / `MIDI_NOTEOFF (128)`: velocity destroyed, out of 0..127; a range-checking event raises `ValueError` | Delete both lines (mk3 does not have them) |
| F-06 | medium [SIM] | `Process.py:267,276,727` | `FPC_MAP.get()` -> `None` for notes outside 36..51; `event.data1 = None`; `ReleaseBit` `TypeError` (fuzz: only exception site) | `.get(n, n)`; range-guard `ReleaseBit` |
| F-07 | medium [SIM] | `Process.py:261-278` | FPC remap applied to every instrument (scrambles Sampler/Slicex/piano pads); mk3 gates on plugin name (`KL3Process.py:388`) | Remap only when selected plugin is FPC |
| F-08 | medium [SIM] | `AKLmk2.py:14,36`; `Plugin.py:392`; `Forward:46-47` | `handled` leaked after processing: every mixer pan (incl. master), mixer volume (event mutated: status `0xE2`, data1 4, midiId `0xB0`), mapped plugin faders/knobs; Forward overrides `handled=True` for seq pads | Set `handled=True` once at the top; never assign `False` in helpers |
| F-09 | medium [SIM] | `Process.py:412,431,641`; `AKLmk2.py:41-57` | Bank up to offset 15 vs 125 tracks: pan/select touch tracks 126,127,128; volume guarded at `:602`, pan/select not; H2 `CC1 -> -14` | Clamp banks to `mixer.trackCount()`; one guard helper |
| F-10 | medium | `Process.py:172-173,652-654`; `AKLmk2.py:38-39`; `SeqParam.py:38,45-50`; `Plugin.py:382-386` | Relative encoders: jog only 1/65; pan and step edit ignore tick magnitude, `0x40` = -3/0; plugin knob re-seeds with `int()`; pitch direction inverted | Decode `ticks = d2 & 0x3F`, `sign = d2 & 0x40`; use `utils.KnobAccelToRes2` |
| F-11 | medium [SIM] | `SeqParam.py:8,46-50,100,112-119` | One global accumulator not seeded from the step (first tick sets velocity 100 -> 67); MOD Y `2*value` up to 254 (range 0..127 [DOC]); fine pitch range 0..240 [DOC] only half covered; pitch unclamped; SHIFT documented [GUIDE p.15 Fig.31] but unimplemented | Seed from `getCurrentStepParam`; clamp per param; add tick-offset (param 7) |
| F-12 | medium [SIM] | `Process.py:335-345`; `Return.py:198-201`; `Process.py:504` | State desync: `MIXER_MODE` vs real focus (Solo/Mute and the jog follow `ui.getFocused`, faders/encoders/select follow `MIXER_MODE`: two sources of truth); `CH_OFFSET` stale -> `IndexError` in `SelectedChannel` every idle tick (cross-ref O-08); `RECT_OFFSET` unbounded | Derive mode from focus or resync in `OnRefresh`; clamp offsets on every use |
| F-13 | medium (UNVERIFIED consequence) | `Process.py:322,394,399,437,465,470,565,573,745-749`; `SeqParam.py:25,41,55`; `Plugin.py:382-394` | `channels.channelNumber()` (global index) passed to APIs whose default is group-relative (API v33 `useGlobalIndex=False` [DOC]) -> wrong channel when Channel Rack groups/filter are used; mk3 uses `selectedChannel()` | `channels.selectedChannel()` everywhere or `useGlobalIndex=True` |
| F-14 | medium [SIM] | `Process.py:293-296` (called `:337,349,365,383,387,391,396,432,438`) | `_hideAll` loops `showEditor(i,0)` over every channel: 300 API calls per main-knob tick at 300 channels, closes all editors on every tick | Track the open editor; close one |
| F-15 | medium (UNVERIFIED impact) | `Forward:33-36,71-72` | Per-event `getFocusedPluginName()` + 32-string scan on notes/aftertouch in `OnMidiIn`; wheel uses MSB only (3.1-cent steps, fixed +-200 cents, ignores channel pitch range), acts on `channelNumber()` only, V_COL detection by channel *name* | Cache focus; 14-bit `data1 + (data2 << 7) - 8192`, `setChannelPitch(...,mode 0)` |
| F-16 | medium [SIM] | `Plugin.py:379-394,22-375` | Unmapped `-1` slots call `getParamValue(-1)` before the check (`:382` vs `:389`); 22 unmapped slots; duplicate params (FL Keys knobs 6+7 -> 4; DX10 knob 6 + fader 4 -> 4; Harmless knob 3 + fader 8 -> 58); names matched by exact string (see 5.3) | Check `-1` first; dedupe; case-fold matching |
| F-17 | medium (UNVERIFIED) | `device_Forward...:19,27,46`; section 3.4 | Second `_mk2`/processor; possible per-script interpreter -> mode/bank state not shared | Single script, or `device.dispatch` |
| F-18 | medium (UNVERIFIED) | `Process.py:544-547` | `ui.cut()` is "cut the selection" [DOC], label says "cut the pattern of the selected channel"; destructive, no confirm | Verify on `tom`; consider `channels.deselect`+clear or drop |
| F-19 | low | `Process.py:757-758` | `FakeMIDImsg` = `globalTransport(FPT_Punch,1)`, documented "(hold) live selection" [DOC], never released; per encoder tick in edit mode (vendor pattern, also mk3 `KL3Process.py:1065`) | Use a real refresh path |
| F-20 | low | `Process.py:286-296,442-455,544-547`, no gating | No `pmeFlags` gating; Image-Line gates UI/structural calls on `PME_System_Safe` (`MackieCU:488`) and buttons on `PME_System` (`:314`) | Gate; wrap UI calls in `try/except TypeError` |
| F-21 | low | `Process.py:447,455` | `jumpToPattern(0)` at pattern 1; Next past the last pattern creates a pattern | Clamp to `[1, patternCount]` unless creation is wanted |
| F-22 | low | `Process.py:550` | `Undo` value `FPT_Undo` (20) instead of the conventional 1/2 | `globalTransport(FPT_Undo, 2, event.pmeFlags)`; show `general.getUndoLevelHint()` |
| F-23 | low | `Process.py:118,144-145,155-157,...` | Release-driven handlers and `continuousMove(...,0)` depend on note-on **velocity 0**; a note-off `0x80` release is not routed [SIM] | Treat `0x80` like `0x90` vel 0 |
| F-24 | low | `Process.py:400-401` | Any jog turn while Playlist/Piano roll is focused yanks focus to the Channel Rack | Pass through when focus is not one of the managed windows |
| F-25 (cross-cutting) | medium/high [SIM], owned by output audit | `Display.py:49,58` | ASCII-only LCD encoder: a non-ASCII channel/param name raises `UnicodeEncodeError` inside input handlers (`PluginRefresh` after the param is already applied) and in `OnRefresh`/`OnIdle` every tick once the 1.5 s welcome page expires (O-03) | Sanitise in `SetLines` |
| F-26 (cross-cutting) | medium (UNVERIFIED), owned by output audit | `Return.py:303-326`; entry `:141-151` | 24 SysEx per `OnIdle` tick (~1200/s) [SIM]; on the same USB device as the input path (O-02) | Shadow-state dedupe |
| F-27 | low | `Process.py:257-259` | `device.processMIDICC(event)` is called with a **note** event (pad press in Sequencer mode) although it is documented as "process a MIDI CC message" [DOC `device/__fl.py:8`]; intent unclear, feeds FL's controller-link system | Drop unless step-pad linking is wanted |

### 5.1 The findings that matter most, with evidence

**F-04 (song-mode stuck edit mode) [SIM `t2_bugs.py` B3].** Press pad 36 in SEQ_MODE with `getLoopMode()==1`: `OnDrumSeqEvent`
takes the 0x99 branch unconditionally (`:263-265`) and runs `HoldBit` (`STATE_MATRIX[0][0]=1`, `EDIT_MODE=1`); the 0x89 branch is
guarded by `if not transport.getLoopMode()` (`:272`), so the release does nothing. After switching back to pattern mode, encoder 1
edits step 0's pitch and encoder 9 (`CC24`) only calls `closeGraphEditor` and `FPT_Punch`: no pan.

**F-05 (velocity) [SIM B1].** `0x99 36 100` becomes `status 0x99, data1 49, data2 144`; release becomes `data2 128`. Real FL
behaviour with an out-of-range `data2` is UNVERIFIED (clamp to 127: all pads full velocity; mask: velocity 16; stub-style range
check: exception). Arturia's 2024 mk3 script only remaps `data1` (`KL3Process.py:394-406`).

**F-08 (handled semantics) [SIM B7].** After `0xE2 0 64` in mixer mode: `handled=False status=0xE2 data1=4 midiId=0xB0`, i.e. a
pitch-bend status carrying a CC-shaped body goes on to FL's link system / default routing. Same for every pan event including the
master. After a mapped plugin control, `Plugin.py:392` also leaves `handled=False`, so a fader moved in Channel Rack mode with FPC
focused is applied to the plugin **and** continues as a pitch bend to the selected channel (FL default; UNVERIFIED).

**F-09 (out-of-range mixer indices) [SIM `t8_bank.py`].** `>` pressed 30 times gives `MX_OFFSET=15` (first track 121, last 128):
volume touches 121-125 only (guarded), pan and select touch 121-128, of which 127 and 128 do not exist if `trackCount()` is 127
(master + 125 inserts + "current", [DOC `mixer/__properties.py:44-47`]) and 126 is the "current track" pseudo-track. With a strict API
(IndexError) the fuzz shows `getTrackPan(127/128)` and `setTrackNumber(127/128)` raising (`t5_fuzz.py ... strict`). H2 adds `getTrackPan(-14)`.

**F-11 (step edit) [SIM B5].** Holding pad 36 and turning: pitch `CC16 d2=1` (CW) writes 99 from 100 (decrement); first velocity tick
writes 67 although the step's velocity is 100 (accumulator seeded at 64, `SeqParam.py:8`); MOD Y writes 146 then 152 (`:100`);
encoders 8 and 9 do nothing but close the graph editor.

### 5.2 What FL actually gives the script (evidence for the fixes)

- `controlNum`/`note` are aliases of `data1`, `controlVal`/`velocity` of `data2` [DOC `fl_classes`]; writes update the shadows,
  which is why `Process.py:599-601` (`data1 = 2+status-midiId` then `controlNum`) works.
- Relative resolution: Image-Line decodes V-pots as `outEv = -(inEv-0x40)` for `inEv >= 0x40` and scales with
  `utils.KnobAccelToRes2(outEv)` (`MackieCU:250-262`; `utils.py:85`, present in `Shared/Python/Lib` of the local FL 2025).
- Fader volume: `mixer.automateEvent(SliderEventID, level, midi.REC_MIDIController, SmoothSpeed)` with
  `SliderEventID = mixer.getTrackPluginId(track,0) + midi.REC_Mixer_Vol` (`MackieCU:300,843-844`), so FL records automation and
  smooths; the stock script's `mixer.setTrackVolume` does neither.
- Undo hint: `general.getUndoLevelHint()` (`MackieCU:208,515`).

### 5.3 Plugin database (`Plugin.py`) [SIM `t4_db.py`, STATIC]

15 plugins x (8 knobs CC16-23, 8 faders 224-231, CC1). Selected facts:

| Plugin | Unmapped slots | Duplicate param ids |
|---|---|---|
| Fruit kick | knobs 1-8, faders 7-8, CC1 (11 of 17) | none |
| FLEX, FPC, Sytrus, GMS, Harmless, Harmor, Morphine, 3x Osc, Fruity DX10, BASSDRUM | CC1 only | FL Keys `{4}` (knobs 6,7), Fruity DX10 `{4}` (knob 6, fader 4), Harmless `{58}` (knob 3, fader 8) |
| MiniSynth, PoiZone, Sakura | none | none |

Plugin-name evidence from the local FL 2025 install (`strings` on the DLLs): `BASSDRUM` (in `BassDrum_x64.dll`), `Fruit kick`
(`Fruit Kick_x64.dll`), `MiniSynth`, `FLEX`, `FL Keys`, `Sytrus`, `Harmless`, `Harmor`, `Morphine`, `3x Osc`, `Fruity DX10`,
`Sakura` occur exactly as the script spells them. `PoiZone_x64.dll` contains `Poizone`/`.POIZONE` but not `PoiZone`; `GMS`'s DLL has
`gmsynth`; `FPC` only `|FPC`. So the odd casing (`BASSDRUM`, `Fruit kick`) is probably deliberate and right; PoiZone/GMS/FPC matching is
UNVERIFIED. Whether the parameter **indices** still match FL 2025/2026 builds of these plugins is UNVERIFIED (needs a
`plugins.getParamName` dump on `tom`, section 8).

### 5.4 Dead code, duplication, hygiene

- Dead: `_status_dispatcher[176]`, `_plugin_dispatcher`, `OnPluginEvent` (`Process.py:126,177-202,253-255`) in `OnMidiMsg`; duplicate
  registration of CC60 (`:164-165`); `LED_MATRIX` write-only (`:66,747,750`); unused constants/imports (`Process.py:23,26,29,32` = `PORT_MIDICC_ANALOGLAB`,
  `WidPlaylist`, `ANALOGLAB_KNOB_ID`, `ABSOLUTE_VALUE`; `import general` `:2`, `KeyLabDisplay`/`KeyLabPagedDisplay` `:17-18`; entry
  `TEMP`, `HW_Flag`, `import time`, `ArturiaCrossKeyboardKLmk2`); `ArturiaVCOLLECTION` class
  (`ArturiaVCOL.py:40-57`) never used; `Navigation.__init__` ignores `display_ms` (`:20-22`), `_modes`, `_active_index`;
  `SeqParam.PAGE_MAP["SHIFT"]` has no branch; `Plugin.py:383-386` identical `if/else`; `Forward.OnMidiMsg` redundant; `Forward:2`
  `receiveFrom` names itself with a trailing space (nothing uses `device.dispatch`).
- Duplicated: `HoldBit`/`ReleaseBit` `BIT_MAP` (`note-36`), 9 hand-unrolled branches in `AKLmk2.SetVolumeTrack/SetPanTrack`,
  six near-identical branches in `SeqParam.Param`, widget ids re-declared in Process/Navigation/Return (`midi.wid*` exist),
  two different `RelativeToAbsolute` implementations.
- Mutable module globals shared by three modules and never reset in `OnInit` (F-12).
- Performance: routing itself is cheap (0.32 us for an unmapped note [SIM]); the costs are `_hideAll` (F-14), `OnMidiIn`
  UI calls (F-15), LCD SysEx per fader event (0.63 frames per event, 81 per 0..127 sweep [SIM]).

---

## 6. Interaction with the FL 2025/2026 API (things that will "silently do nothing" vs raise)

- No removed/renamed API symbol: 92 of 92 resolve [SIM `t9_api.py`]. Failures are semantic, not `AttributeError`.
- Magic `3` in `mixer.setTrackNumber(track, 3)` = `curfxScrollToMakeVisible | (1<<1)`; FL 2025's own `midi.py` names bit 1
  `StartcurfxCancelSmoothing` (sic, typo in Image-Line's file), so use the numeric value or the sic name, not `midi.curfxCancelSmoothing`.
- `ui.getFocused(5)` = "a plugin window" (any generator or effect); `plugins.*` calls use the selected **channel**, so a focused mixer
  effect (`widPluginEffect`) is never controllable (needs `slotIndex`) [DOC `ui/__windows.py:77-118`].
- Window ids `WidMixer/ChannelRack/Playlist/Browser/Plugin` equal `midi.wid*` [DOC `midi.py:482-487`].
- Everything that changes the UI (`showWindow`, `setFocused`, `showEditor`, `jumpToPattern`) is ungated (F-20).

---

## 7. Gaps versus a great mkII integration (each tied to hardware present in the code or guide)

1. **Faders have no pickup** (9 non-motorized faders sending absolute pitch-bend, [GUIDE p.11]). After a bank change or plugin
   change the first touch jumps the parameter. `mixer.setTrackVolume(..., pickupMode)` and `plugins.setParamValue(..., pickupMode)`
   accept `midi.PIM_AlwaysPickup` / `PIM_FollowGlobal` [DOC]. Use them.
2. **No automation recording from faders** although the keyboard has Record/Play (notes 95/94): use `mixer.automateEvent` with
   `REC_MIDIController` as `MackieCU` does (F-08 evidence above).
3. **Mixer banking bound to reality**: clamp to `mixer.trackCount()`; the 8 RGB Select buttons (guide p.13 Fig.25) already
   encode "no channel in this slot = off"; make input agree (F-09, F-12). Optionally: hold Solo/Mute + Select N to solo/mute strip
   N (Solo/Mute are single buttons, ids 8/16, Fig.22; Select ids 24-31 exist).
4. **Focused-plugin mapping**: 8 encoders + 8 faders (guide p.10-11) only work for 15 stock plugins (guide p.17). Add a generic
   fallback via `plugins.getParamCount`/`getParamName` (page of 16, paged with the existing Next/Previous buttons 46/47), name and %
   on the 2x16 LCD (already shown by `PluginRefresh`), and support mixer effect plugins (`slotIndex`). Verify indices on `tom`.
5. **Encoders**: honour tick magnitude and acceleration for jog, pan and step edit (F-10). The jog currently drops any fast spin.
6. **Channel-rack pads**: keep velocity (F-05); remap only for FPC (F-07); bound `RECT_OFFSET` to the pattern length;
   implement encoder 8 = step Shift (tick offset) exactly as the guide's Fig.31 lists 8 parameters (F-11); make step editing work
   in song mode (F-04). Pad aftertouch is not handled (16 pads, [GUIDE p.14]).
7. **Transport**: Loop (86) is *loop recording* only, while `SequencerReturn` depends on pattern vs song mode; there is no way
   to switch it from the hardware (`transport.setLoopMode()` unused). `FPT_CountDown` has an LED (`Return.CountdownReturn`) but
   no input. Undo is single-step with no history display; add `getUndoLevelHint()` (F-22).
8. **Keep both windows honest**: derive `MIXER_MODE` from `ui.getFocused` in `OnRefresh`/before every fader/encoder event so
   mouse-driven window changes cannot desync (F-12); let the jog also act in Playlist/Piano roll (F-24).
9. **Default-MCU fallback**: since Arturia documents "Default MCU + Mackie Control Universal on port 2 + Generic on port 1" for
   FL, and Image-Line maintains `MackieCU` (2026-01), a documented fallback recipe belongs in the final deliverable; the tuned
   script is worth it mainly for pads/step sequencer/LCD, which MCU does not give.

---

## 8. Verification plan on `tom` (the input side needs the hardware)

Put this in its own folder (do not touch the stock folder; FL "Update MIDI Scripts" can overwrite it,
`05-prior-art.md`): `Documents/Image-Line/FL Studio/Settings/Hardware/KL2 raw monitor/device_KL2raw.py`, assign it to **both**
keyboard inputs in turn, open View > Script output.

```python
# name=KL2 raw monitor
def _dump(tag, e):
    try:
        if e.status == 0xF0:
            print(tag, "SYSEX", bytes(e.sysex).hex()); return
        print("%s st=0x%02X d1=%3d d2=%3d port=%s midiId=%s midiChan=%s ctrlNum=%s ctrlVal=%s pme=%s" % (
            tag, e.status, e.data1, e.data2, e.port, getattr(e, "midiId", "?"), getattr(e, "midiChan", "?"),
            getattr(e, "controlNum", "?"), getattr(e, "controlVal", "?"), e.pmeFlags))
    except Exception as ex:
        print(tag, "ERR", ex)
def OnMidiIn(event):  _dump("IN ", event)   # raw stage: compare midiId/midiChan/controlNum with OnMidiMsg
def OnMidiMsg(event): _dump("MSG", event)
```

Checklist, in this order:

1. Which DAW map is the keyboard in (MIDI Control Center: "Live" vs "Default MCU"), which USB port carries pads, encoders, faders,
   buttons (guide open question 1, `01-official-guide.md` section 6).
2. `IN` vs `MSG` lines for the same event: is `midiId` populated in `OnMidiIn`? (decides H1/H2, F-01).
3. Press and release of every button: note-on vel 0 or note-off 0x80 (F-23); the ids in the section 4.2 table; ids of Next/Previous/Bank,
   the two keys 98/99, encoder pushes (32..39?), Save/In/Out/Read/Off.
4. Spin the jog slowly and fast: values (1/65 only, or 2..63/66..127?) (F-10).
5. Encoders: same test; do encoders 1-8 and 9 send CC 16..24 on channel 1 in this DAW map?
6. Pads: channel, notes 36..51 on both banks, port, and velocity on note-off (F-05, F-06).
7. Faders: pitch-bend channels 1..9, LSB/MSB values at the extremes.
8. Analog Lab preset: CC list for knobs/faders (16/17/18/19 overlap the DAW encoders, F-02).
9. Dump `plugins.getPluginName(i)`, `ui.getFocusedPluginName()`, `plugins.getParamCount(i)` and every `getParamName` for one instance of
   each of the 15 database plugins to validate names and indices (section 5.3).
10. With two channel-rack groups, run the script and see whether solo/mute/param writes hit the right channel (F-13).

---

## 9. Suggested order of fixes for the tuned script (input side only)

1. Move the Forward logic out of `OnMidiIn` (F-01); delete the dead `_plugin_dispatcher` (F-02).
2. Fix pads: delete the two `data2` assignments, gate the remap on FPC, `.get(n, n)`, route `0x89` always, clear stuck state (F-04..F-07).
3. One `handled` policy; make every helper pure (F-08).
4. Clamp banks and offsets to live counts; one guarded track/channel accessor (F-09, F-12, F-13).
5. Relative-encoder decode + `KnobAccelToRes2` (F-10); seed step accumulator, clamp ranges, add Shift (F-11).
6. `pmeFlags` gating, pickup, automation, generic plugin fallback (section 7).
7. Ship the raw monitor with the tuned script behind a debug flag.

---

## Appendix A. Selected simulation output (stock, unmodified)

```
B1  0x99 36 100 -> status=0x99 data1=49 data2=144           (release: data2=128)
B2  0x99 note 35/52/60 (drum mode) -> data1 = None
B3  seq mode, pattern mode press+release: EDIT_MODE=0, grid set
    seq mode, SONG mode press+release:    EDIT_MODE=1 STATE_MATRIX[0][0]=1 (stuck)
      then CC16 d2=1 -> setStepParameterByIndex(0,1,0,0,99) ; CC24 d2=1 -> closeGraphEditor + FPT_Punch, no pan
B4  seq mode, 0x89 note 35 or 52: TypeError NoneType // int @ KeyLabmk2Process.py:727
B5  hold 36: CC16 d2=1 -> pitch 99 (from 100); CC17 d2=1 -> velocity 67 (from 100); CC22 d2=1 -> mod Y 146, then 152
B5b EDIT_MODE=1 with empty INDEX_PRESSED: ValueError min() @ KeyLabmk2SeqParam.py:28 (latent)
B6  MX_OFFSET max 15: volume tracks 121-125; pan/select tracks 121-128 (127,128 out of range)
B7  mixer mode 0xE2 0 64: handled=False status=0xE2 data1=4 midiId=0xB0; pans handled=False (incl. master)
B8  FPC knob: getParamValue(8,0) -> setParamValue(0.5118,8,0), handled=False
    Fruit kick knob1: getParamValue(-1,0) then handled=True (unmapped)
B9  CC24 (CR mode): d2 1/3/10 -> +0.05 ; 65/67/74 -> -0.05 ; 64 -> 0.0   (tick magnitude ignored)
B10 CC60 d2 1 -> ui.next ; 65 -> ui.previous ; 2,3,63,66,67,127 -> nothing (handled=True)
B11 notes 98/99 at pattern 1 / 3 -> jumpToPattern(0) / jumpToPattern(4)
B12 CH_OFFSET=4 then 5 channels: IndexError @ KeyLabmk2Return.py:201
Fuzz 300000 events (populated midiId): 1 site -> TypeError @ Process.py:727 (3429 hits)
Fuzz strict mixer index: + IndexError getTrackPan(127/128), setTrackNumber(127/128)
Forward H1: 15/88 keybed keys act; H2: 0/88; CC74 (FLEX focused) H2 -> TypeError, handled=True
Wheel: (lsb,msb)=(0,64)->0 cents ; (127,63)->-3.125 ; (0,127)->+196.875 ; (0,0)->-200
Lifecycle: OnIdle = 24 SysEx per call; 128-step fader sweep in mixer mode = 81 LCD frames
```

## Appendix B. Sources

- Local: `KL2/*.py`, `KL2/KeyLab mkII FL Studio User Guide V1 (5).pdf`, `KL2/KeyLab mkII FL Studio Overlay.jpg`;
  `.../Hardware/Arturia KeyLab mk3/*` (2024); `.../Hardware/MackieCU/device_MackieCU.py` (2026-01-13);
  `~/.wine/drive_c/Program Files/Image-Line/FL Studio 2025/Shared/Python/Lib/{midi.py,utils.py}` and `Plugins/Fruity/Generators/*`.
- FL manual (`midi_scripting`) and `https://github.com/IL-Group/FL-Studio-API-Stubs` (commit `9b4c7fa`, 2026-05-13):
  `fl_classes/__init__.py`, `callbacks/__init__.py`, `channels/*`, `mixer/*`, `transport/__init__.py`, `ui/*`, `plugins/__init__.py`,
  `device/__fl.py`, `device/__device.py`, `patterns/__properties.py`, `docs/.../script_metadata.md`, `tutorials/event_mapping.md`.
- Arturia support "KeyLab MkII - Tips & Tricks" (article 4405748362002, via `05-prior-art.md`).
- Sibling reports: `01-official-guide.md`, `03-output-audit.md`, `05-prior-art.md`.
