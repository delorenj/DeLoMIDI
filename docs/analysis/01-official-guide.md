# 01 - Official guide analysis: "KeyLab mkII FL Studio User Guide V1"

Analyst role: "official spec". Scope: what Arturia's own guide and overlay say about
how the stock KeyLab mkII FL Studio script set is meant to be installed, configured and used,
and a fact-check of six claims a previous assistant made (C1-C6).

Nothing here was run against FL Studio or the keyboard (host "tom" is unreachable). Every
statement is either read from a document (cited) or marked UNVERIFIED.

## 0. Sources and citation conventions

| Tag | Source | Notes |
|---|---|---|
| GUIDE | `/home/delorenj/Documents/Image-Line/FL Studio/Settings/Hardware/Arturia KeyLab MKII/KeyLab mkII FL Studio User Guide V1 (5).pdf` | 17 pages (pdfinfo). Read in full, every page viewed as an image plus `pdftotext`. "p.N" below = PDF page index. |
| OVERLAY | `.../Arturia KeyLab MKII/KeyLab mkII FL Studio Overlay.jpg` | 1904x816 print sheet with crop marks. Viewed. |
| ARTURIA-MAN | Arturia "User Manual KeyLab MkII" v2.2.0, https://dl.arturia.net/products/keylab-49-mkII/manual/keylab-mkii_Manual_2_2_0_EN.pdf | Not part of the FL guide. Used only to corroborate hardware-side facts. "p.N" = printed page number. |
| ARTURIA-TIPS | Arturia FAQ "KeyLab MkII - Tips & Tricks", https://support.arturia.com/hc/en-us/articles/4405748362002-KeyLab-MkII-Tips-Tricks | Fetched via Arturia's help-center API (cached copy in the scratchpad `research/kl2_tips.json`). |
| FL-MAN | FL Studio manual, MIDI scripting, https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm | Sections "Script Locations and File Names" and "Device module". |
| STOCK | `/home/delorenj/Documents/Image-Line/FL Studio/Settings/Hardware/Arturia KeyLab MKII/*.py` | Only used for cross-references (file:line). |

Page-number caveat: the guide's own table of contents (p.1) drifts from the real pages
starting at "Sliders". TOC says Sliders 11, Buttons 12, Pads 14, Analog Lab Mode 17, Screen 18.
Actual PDF pages are Sliders p.10, Buttons p.11, Pads p.13, Analog Lab Mode p.16, Screen p.17
(the PDF ends at p.17). "DAW Mode 7" and "Knobs 7" are correct. All citations here use the real PDF page.

Page map of the guide:

| PDF page | Content |
|---|---|
| 1 | Cover, TOC |
| 2 | Blank |
| 3 | Fig.1 layout callouts, "2. FL Studio Setup", File Location text |
| 4 | Path breadcrumb (image), Memory Selection, FL Studio MIDI Settings - Windows (Fig.2) |
| 5 | macOS MIDI Settings screenshot, "Select the right script...", Project Setup (Fig.3) |
| 6 | Channel rack layout (Fig.4), Analog Lab V MIDI input port 10 (Fig.5, Fig.6) |
| 7 | Analog Lab controller list (Fig.7), DAW Mode, Knobs, center knob (Fig.8-9) |
| 8 | Center knob: channel rack, plugin window, browser (Fig.10-11) |
| 9 | Browser (Fig.12-13), Mixer navigation and arm (Fig.14) |
| 10 | Encoders (Fig.15-17), Sliders heading |
| 11 | Sliders (Fig.18-20), Buttons heading, transport picture |
| 12 | Transport list, DAW Functions list (Fig.22), Next/Previous/Bank text |
| 13 | Next/Prev/Bank (Fig.23-24), 9 RGB buttons (Fig.25), Pads: Drum Mode |
| 14 | Pad picture (Fig.26), FPC map (Fig.27), Sequencer Mode |
| 15 | Step grid (Fig.28-31): red rectangle, LEDs, step editing |
| 16 | Encoder labels (Fig.32), Analog Lab Mode (Fig.33-37) |
| 17 | Nav buttons (Fig.38), Screen (Fig.39), plugin database list |

## 1. The official setup procedure

### 1.1 Files

- GUIDE p.3: "Make sure you place the folder *KeyLab MkII V.1* containing the script files at
  the end of this path:" followed (p.4) by an image of the breadcrumb
  `This PC > Documents > Image-Line > FL Studio > Settings > Hardware`.
  So: `Documents\Image-Line\FL Studio\Settings\Hardware\<folder>\` with all script files inside one folder.
- The guide does not mention the `device_` filename prefix, `# name=` headers or helper modules.
  Those rules come from FL-MAN ("The 'device_devicename.py' prefix is mandatory"; "The controller
  name is required"; folder name arbitrary).
- The user's stock folder (`Arturia KeyLab MKII`) contains 2 entry scripts (`device_KeyLabmkII.py`,
  `device_Forward CCs Port 10 KEYLAB MKII.py`) plus helpers, matching the guide's "folder containing
  the script files" model.

### 1.2 Keyboard side (front panel)

GUIDE p.4, "Memory Selection", verbatim:

> The first thing to do is to set the *Live* program by long pressing on the *DAW* button on the
> hardware and then by selecting the right program.
> At the end, there will be an update to create an FL Studio memory slot.
> Now your controller is set for FL Studio.

Then GUIDE p.7: "You can enter the DAW Mode by pressing the 'DAW' button. The Daw Mode will make you
able to control the DAW functions, the plugin parameters, the mixer and the step sequencer" (Fig.8).
Analog Lab mode is entered "by pressing *Analog Lab*" (p.16, Fig.35 shows the three mode buttons ANALOG LAB | DAW | USER).

Facts the guide does NOT state:
- No Arturia MIDI Control Center (MCC) step of any kind.
- No firmware version or firmware update requirement.
- No FL Studio preset exists at the time of writing ("there will be an update to create an FL Studio
  memory slot" = future tense). The guide therefore tells you to reuse the "Live" program.
- The word "Live" is ambiguous in the guide (the hardware also prints "Live" in blue above the Bank button,
  Fig.23). Corroboration: ARTURIA-MAN section 4.2 (p.33) says "Hold the DAW mode
  button for 1 second to enter the DAW Preset selection page. Next, turn the center knob... Click the
  center knob to select that preset", and section 4.2.1 (p.34) lists exactly nine presets:
  1 Standard MCU, 2 Standard HUI, 3 Ableton Live, 4 Logic Pro X, 5 Pro Tools, 6 Cubase,
  7 Studio One, 8 Reaper, 9 MMC. So "Live" almost certainly means preset 3 "Ableton Live"
  (inference, UNVERIFIED on hardware). There is no FL Studio preset in v2.2.0.
- Alternative route not in the guide: ARTURIA-MAN section 8.16.2 (p.80) "DAW Map: This lets you use the
  MCC to select which DAW preset your KeyLab MkII will use", and ARTURIA-TIPS repeatedly says "set your
  KeyLab DAW map to X from the Midi Control Center Device settings section".

### 1.3 FL Studio MIDI Settings (Options > MIDI)

GUIDE p.4 (Windows, Fig.2) and p.5 (macOS screenshot). I zoomed both screenshots to read the rows.

Windows (p.4, Fig.2):

| Section | Port row | Controller type shown | Enabled | Port # |
|---|---|---|---|---|
| Output | Microsoft MIDI Mapper | (software) | - | - |
| Output | Microsoft GS Wavetable Synth | Software synthesizer | - | - |
| Output | ARTURIA MIDI Out | "MIDI hardware port" | - | - |
| Output | `KeyLab mkII 88` | `Forward CCs Port..AB mkII V2 (user)` (name is middle-truncated by FL) | yes | **1** |
| Output | `MIDIOUT2 (KeyLab mkII 88)` (selected) | `KeyLab mkII V2 (user)` | yes | **0** |
| Input | ARTURIA MIDI In | `(generic controller)` | yes | (none shown) |
| Input | `KeyLab mkII 88` | `Forward CCs Port..AB mkII V2 (user)` | yes | **1** |
| Input | `MIDIIN2 (KeyLab mkII 88)` (selected) | `KeyLab mkII V2 (user)` | yes | **0** |

Other visible settings: "Send master sync" unchecked, Synchronization type "MIDI clock".

macOS (p.5):

| Section | Port row | Controller type | Enabled | Port # |
|---|---|---|---|---|
| Output | `KeyLab mkII 88 MIDI` | `Forward CCs Port..LAB mkII V2 (user)` | yes | **1** |
| Output | `KeyLab mkII 88 DAW` | `KeyLab mkII V2 (user)` | yes | **0** |
| Input | `KeyLab mkII 88 MIDI` | `Forward CCs Port..LAB mkII V2 (user)` | yes | **1** |
| Input | `KeyLab mkII 88 DAW` (selected) | `KeyLab mkII V2 (user)` | yes | **0** |

Guide text on p.5, verbatim:

> Select the right script in the *Controller type* box under the "Input Section"
> Select a MIDI port for each Input as long as the input port and the output port of the same
> instance match ( see above )

Interpretation (from the screenshots plus that sentence):
1. Two scripts are used, both enabled, on the two USB MIDI ports of the keyboard.
   - DAW port (`MIDIIN2` / `MIDIOUT2` on Windows, `KeyLab mkII 88 DAW` on macOS) gets the main
     script (`KeyLab mkII V2` in the screenshot, i.e. `device_KeyLabmkII.py`), port number 0.
   - Main keyboard port (`KeyLab mkII 88`, macOS `KeyLab mkII 88 MIDI`) gets the "Forward CCs Port 10
     KEYLAB MKII" script, port number 1.
2. Each input and its matching output carry the same port number (0/0 and 1/1). The guide's port numbers
   are 0 and 1, not 10.
3. The only row left as `(generic controller)` in any screenshot is "ARTURIA MIDI In" (Windows only).
   That is not the keyboard's main USB port. What it physically is (DIN/third USB port) is UNVERIFIED.
4. The guide's screenshots show controller names `KeyLab mkII V2` and `Forward CCs Port..[KEY]LAB mkII V2`.
   The shipped files declare `# name= KeyLab mkII` (device_KeyLabmkII.py:1) and
   `# name=Forward CCs Port 10 KEYLAB MKII` (device_Forward CCs Port 10 KEYLAB MKII.py:1), so the
   dropdown entries will read `KeyLab mkII (user)` and `Forward CCs Port 10 KEYLAB MKII (user)`.
   The screenshots come from a different build than the shipped files (info only).

### 1.4 Arturia plugin side (port 10)

- GUIDE p.6: "If you use Arturia's VST like Analog Lab V ... please make sure to connect the plugin to
  the MIDI input 10" (Fig.5/6: plugin wrapper MIDI panel, Input port = 10, Output port empty,
  Event bus "Midi In", "Send note release velocity" enabled, pitch bend range 12).
- GUIDE p.6-7: "make sure you linked the correct device when you open the plugin"; Fig.7 is Analog Lab's own
  "MIDI Controller" list (checked entry "KeyLab mkII", alternative "KeyLab mkII 88").
- GUIDE p.16: Analog Lab mode "Make sure The plugin receive MIDI on the port 10".
- Where 10 comes from: the Forward script rewrites the port byte to 10 (`(10 << 24)`,
  device_Forward CCs Port 10 KEYLAB MKII.py:41) and calls `device.forwardMIDICC(msg, 2)` (line 42),
  its header says "forwarding CCs to port 10 ( Arturia's Software )" (lines 12-13).
  Port 10 is therefore the plugin-side input port for forwarded CCs, not a hardware port number.

### 1.5 Project preparation

- GUIDE p.5: "Prepare your project before using the controller exclusively. During the performance, only
  the Channel Rack, the Mixer, the plugin Windows and some functions of the general UI will be managed by
  the controller".
- GUIDE p.5-6: "Set the plugins that you want as channels to use during the performance. It can be done by
  clicking on the '+' under the last track or by drag and drop from the browser on the left." (Fig.3/4:
  Piano Plugin, Drum Plugin, FLEX Plugin, Analog Lab V, Channel 5..15 in the Channel Rack.)
- GUIDE p.7: "You are now ready to use Arturia's controller exclusively."

### 1.6 FL Studio version requirements

- The guide states none. No minimum or maximum FL version, no Python version, no API version.
- Dating hints only: Arturia calls the plugin "Analog Lab V"; the MIDI Settings screenshots show the
  FL 20.x era "Synchronization type" layout; file mtimes in the folder are 2021-11-15; the guide is titled "V1".
  Support on FL Studio 2025/2026 is therefore undocumented (UNVERIFIED).
- Cross-reference (third-party stubs, https://github.com/IL-Group/FL-Studio-API-Stubs): the stock scripts call
  `device.forwardMIDICC` (API 7), `plugins.getParam*`/`setParamValue`, `channels.selectOneChannel` (API 8),
  `plugins.nextPreset/prevPreset` (API 10). Several graph-editor and browser calls carry no version
  annotation in the stubs. Highest annotated requirement is API 10, which any current FL satisfies. This says
  nothing about whether behavior changed since.

## 2. Documented control map

Legend: "Guide" = what the guide says (page/figure). "Stock handler" = the handler the stock script
attaches to that function by name (cross-reference only). The guide gives NO MIDI message numbers, so the
physical-button-to-CC/note assignment itself is UNVERIFIED here. File for handlers:
`KeyLabmk2Process.py` (STOCK).

Mode structure used by the guide:
- Hardware modes (Fig.35, p.16): ANALOG LAB, DAW, USER. Only Analog Lab and DAW are described. USER is not described.
- Script contexts inside DAW mode: "Channel Rack Mode" vs "Mixer Mode" (p.10-11), pads "Drum Mode" vs
  "Sequencer Mode" (p.13-15), and center-knob behavior that depends on which FL window is focused
  (Channel Rack, Browser, Mixer, p.7-9).
- The guide never says how Channel Rack Mode and Mixer Mode are switched. (Stock: CC 51,
  `ToggleMixerChannelRack`, Process.py:154, 335-345.)

### 2.1 Center knob (main navigator / jog)

| Context | Documented behavior | Guide | Stock handler |
|---|---|---|---|
| Turn, Channel Rack window focused | Navigate the Channel Rack (select channel) | p.7 (Fig.10, p.8) | Process.py:164 -> 363 `TrackSelectMainKnob`, branch 389-399 |
| Push, Channel Rack, selected channel is a plugin | Show/close that plugin's window | p.8 (Fig.11) | Process.py:148 `SwitchWindow` 298-300, `showPlugin` 321 |
| Turn, Browser focused | Navigate the Browser | p.8 (Fig.12-13 on p.9) | Process.py:367-379 |
| Push, Browser focused | NOT documented | - | Process.py:308-317 (enter folder / select item) |
| Turn, Mixer focused | Navigate mixer tracks | p.9 (Fig.14) | Process.py:380-388 |
| Push, Mixer focused ("mixer mode") | Toggle arm state of selected track | p.9 | Process.py:301-304 (`mixer.armTrack`) |
| Analog Lab mode | Select the plugin window with the center knob to focus it before controlling it | p.16 | not applicable to stock scripts (plugin-side) |
| DAW mode jog (playhead) | not in the FL guide (ARTURIA-MAN 4.5, p.37 describes a generic jog use) | - | - |

### 2.2 Encoders (9)

Hardware labels (Fig.15, p.10): Cutoff/Pan 1, Resonance/Pan 2, LFO Amt/Pan 3, LFO Rate/Pan 4,
Chorus/Pan 5, Param 1/Pan 6, Param 2/Pan 7, Param 3/Pan 8, Param 4 (9th, no pan label).

| Context | Encoders 1-8 | Encoder 9 | Guide | Stock handler |
|---|---|---|---|---|
| Channel Rack Mode | Parameters of the currently focused plugin (plugin database only, see 2.11) | Pan of the currently selected mixer track | p.10 (Fig.16) | Process.py:166 -> 619 `SetPanTrack`, non-mixer branch 646-657 |
| Mixer Mode | Pan of tracks in the current 8-track bank (Fig.17: tracks 1-16 shown, second bank highlighted) | Pan of the master track | p.10 | Process.py:634-645 |
| Sequencer Mode, hold a step pad | Edit that step's parameters (list in Fig.31: Note pitch, Velocity, Release velocity, Fine pitch, Panning, Mod X, Mod Y, Shift) | not stated | p.15 (Fig.30-32) | Process.py:621-631, `KeyLabmk2SeqParam.py` |
| Analog Lab mode | Analog Lab macro knobs (Fig.36: Brightness, Timbre, Time, Movement, blank, blank, Delay Volume, Reverb Volume) | not shown | p.16 | plugin-side |

Note: whether the left-to-right order of the Analog Lab panel in Fig.36 equals the hardware encoder order is UNVERIFIED.

### 2.3 Faders (9)

Hardware labels (Fig.18, p.10-11): Attack/CH 1, Decay/CH 2, Sustain/CH 3, Release/CH 4, Attack/CH 5,
Decay/CH 6, Sustain/CH 7, Release/CH 8, Master.

| Context | Faders 1-8 | Fader 9 | Guide | Stock handler |
|---|---|---|---|---|
| Channel Rack Mode | Parameters of the currently focused plugin (Fig.19 macro panel: Filter, Vibrato, Filt Sweep, 7th Harm, Reverb, Delay, ..., ...) | Volume of the currently selected mixer track. The text says "9th encoder control the volume" (p.11): typo for slider | p.11 | Process.py:213 -> 589 `SetVolumeTrack`, non-mixer branch 607-616 |
| Mixer Mode | Volume of tracks in the current 8-track bank (Fig.20) | Master track volume | p.11 | Process.py:590-606, `ArturiaCrossKeyboardKLmk2.py:11-32` |
| Analog Lab mode | Analog Lab sliders (Fig.37: Filter Env Attack, Filter Env Decay, Filter Env Sustain, Filter Env Amount, Attack, Decay, Sustain, Release On/Off, Legato) | as listed (9 entries) | p.16-17 | plugin-side |

### 2.4 Transport row (Fig.21, p.11-12)

| Button | Documented behavior (verbatim intent) | Stock handler |
|---|---|---|
| `<<` | "Rewind / Step Seq Offset" | Process.py:146 -> 518 (`continuousMove(-1)`; in Sequencer mode moves the 16-step window) |
| `>>` | "fast Forward / Step Seq Offset" | Process.py:147 -> 500 |
| Stop | "Puts the song marker at the beginning" | Process.py:138 -> 495 (`transport.stop()`) |
| Play/Pause | "Play/Pause the Pattern/Song" | Process.py:137 -> 490 (`transport.start()`) |
| Record | "Start recording ( blink if recording, lights if ready to record )" | Process.py:136 -> 485 (`transport.record()`) |
| Loop | "Activate loop recording ( lights if activated )" | Process.py:143 -> 539 (`FPT_LoopRecord`) |

ARTURIA-MAN 4.4 (p.37): the transport buttons always send MCU/HUI and cannot be reassigned in any mode.

### 2.5 DAW Commands / User section (Fig.22, p.12, plus OVERLAY)

Hardware labels in Fig.22: Track Controls: Solo, Mute, Record, Read, Off. Global Controls: Save, In, Out,
Marker, Undo. GUIDE p.12 lists the ten functions "From top-left to bottom-right". The OVERLAY (magnetic
overlay to stick over these ten buttons) relabels them:

| Position | Hardware label (Fig.22) | GUIDE p.12 function | OVERLAY label | Stock handler |
|---|---|---|---|---|
| Track 1 | Solo | "Solo the selected track" | Solo | Process.py:155 `SoloChannel` (CC 8-15) -> 563 |
| Track 2 | Mute | "Mute the selected track" | Mute | Process.py:156 `MuteChannel` (CC 16-23) -> 571 |
| Track 3 | Record | "Change the snap Mode" | Snap | Process.py:158 `SnapMode` (CC 0-7) -> 584 |
| Track 4 | Read | "Tap Tempo" | Tap Tempo | Process.py:141 `TapTempo` -> 579 |
| Track 5 | Off | "Cut the pattern of the selected channel" | Cut | Process.py:145 `Cut` -> 544 (`ui.cut()`) |
| Global 1 | Save | "Drum Mode / Step Sequencer Mode" (also p.14 "entering Sequencer Mode by pressing Save") | Sequencer | Process.py:140 `DrumSeqToggle` -> 347 |
| Global 2 | In | "Switch Channel Rack window and Browser window" | Browser | Process.py:153 `ToggleBrowserChannelRack` -> 325 |
| Global 3 | Out | "Enable/Disable Overdub" | Overdub | Process.py:142 `Overdub` -> 553 |
| Global 4 | Marker | "Metro : Activate metronome" | Metro | Process.py:139 `SetClick` -> 558 |
| Global 5 | Undo | "Undo the last change" | Undo | Process.py:144 `Undo` -> 549 |

The OVERLAY also draws short vertical connector lines between Tap Tempo/Metro and Cut/Undo (columns 4 and 5).
Their meaning is not explained anywhere (UNVERIFIED, probably purely visual grouping).

### 2.6 Next / Previous / Bank (Fig.23-24, p.12-13)

| Control | Documented behavior | Guide | Stock handler |
|---|---|---|---|
| Next (labelled "Part 1"/"Next") | "In DAW mode, Next / Previous offset the effect of knobs and sliders by 8. It allows the user to control more than 8 tracks or channels with the keyboard." Jogs between channel pages or mixer pages depending on mode (Fig.24: mixer pages 1-8, 9-16, 17-24) | p.12-13 | Process.py:149-150 `BankSelect` 403-425 (CC 47 up, CC 46 down) |
| Previous ("Part 2"/"Previous") | same, other direction | p.12-13 | same |
| Bank ("Live"/"Bank") | "The Bank button should be on to access this function." | p.12 | no handler (button state acts in hardware: ARTURIA-MAN 4.6 p.38 says Bank ON = shift by 8, OFF = shift by 1) |

### 2.7 The 9 RGB buttons under the faders (Fig.25, p.13)

Hardware labels (Fig.25): Piano/Select, E-Piano/Select, Organ-B3/Select, Organ-Elect/Select, Bass/Select,
Lead/Select, Pad/Select, Ambient/Select, Seq-Arp/Select.

The guide documents only the LED semantics (p.13): "The lights indicate the state of the 8 current tracks
or channels depending on the mode (CR or Mixer)."

| Color | Meaning |
|---|---|
| Blue | Track available in Mixer |
| Purple | Channel available in Channel Rack |
| Yellow | Channel/Track available and selected |
| Red | Track available but muted |
| Off | No channel in this slot |

What pressing a button does is NOT documented in the FL guide (the hardware label says "Select").
Stock: CC 24-31 `TrackSelect` (Process.py:157 -> 428). The 9th button has no documented function
(ARTURIA-MAN p.39: in DAW mode Button 9 only does something in the Ableton Live preset, toggling fader
function between volume and send A).

### 2.8 Pads (16)

| Mode | Documented behavior | Guide | Stock handler |
|---|---|---|---|
| Drum Mode (default state, no entry step given) | "All pads trigger a MIDI Note that have been mapped to fit FPC GUI. They are mapped by default to the 16 pads of FPC." Fig.27 layout, reading order: Crash, Lite Crash, Lite Ride, Ride Bell / Hi Tom, Mid Tom, Lo Tom, Clav / Snare 2, Snare 1, Open HiHat, Pedal Hi Hat / SideStick, Kick Drum, Closed Hat, Tamb. Fig.26 shows the pads lit in FPC-matching colors (blue, green, yellow, white, red) | p.13-14 | Process.py:127-128 -> 261-278 `OnDrumSeqEvent`, `FPC_MAP` 76-93 (notes 36-51 remapped, layout consistent with Fig.27) |
| Sequencer Mode (enter by pressing Save) | "The 16 pads represented the 16 steps of the 1st Bar of the Sequencer" of the selected channel. `<<` / `>>` offset the red rectangle (Fig.28) to reach a longer pattern | p.14-15 | Process.py:206, 665-750 |
| Sequencer Mode LEDs | Light blue = step off, Yellow = step on, Blue/Red = metronome indicator | p.15 | Return.py:225-240, 263-300 (step off is white 7F7F7F, step on is yellow scaled by velocity; metronome cursor blue/red) |
| Sequencer Mode step edit | "You can edit each step by holding them and tweaking one of the 8 encoders" (params in Fig.31) | p.15 | Process.py:621-631 |

Pad velocity/aftertouch behavior is not addressed in the guide.

### 2.9 Analog Lab mode (p.16-17)

- Enter with the *Analog Lab* button. The plugin (Analog Lab or another Arturia V-Collection plugin)
  must receive MIDI on port 10 and be the focused window ("make sure you have focused the window by
  selecting it with the center knob").
- "The Analog Lab mode allows the user to control the focused plugin (browsing preset, change parameters etc...)".
- Fig.37/38 show the Category, Preset and left/right arrow buttons around the jog wheel and the AL
  knob/slider labels (see 2.2 and 2.3). No text explains what Category/Preset/arrows do in FL.
- Stock: the Forward script (main port) forwards CC and pitch bend to port 10 when the focused plugin is in
  `ArturiaVCOL.V_COL` (device_Forward CCs Port 10 KEYLAB MKII.py:31-43; `ArturiaVCOL.py:5-37`).

### 2.10 Controls the guide does not describe at all

| Control | Status in guide | Stock |
|---|---|---|
| Pitch wheel, mod wheel | Only named in Fig.1 legend (p.3, item 5) | Forward script `OnPitchBend` sets channel pitch for non-Arturia plugins (lines 70-75) |
| Keybed, octave buttons, transpose | Only "Keybed" in Fig.1 legend | not scripted |
| MIDI channel selector | Fig.1 legend item 4 only | not scripted |
| "Internal functions" (Global, Memory, Save on left) | Fig.1 legend item 6 only | not scripted |
| Category / Preset / left-right arrow buttons in DAW mode | not described | Process.py:151-152 CC 98/99 previous/next pattern (or preset when a plugin is focused, 442-455); CC 28/29 preset (200-201) |
| Sustain/expression pedals | not mentioned | not scripted |
| USER mode | not described | - |
| Save (as "save project") | Repurposed to Drum/Sequencer toggle | see 2.5 |
| Screen: see 2.11 | | |

### 2.11 Screen (p.17)

- "The screen returns the current pattern, the name and the number of the channel selected in DAW Mode.
  It also returns the name of the tweaked parameter and its value for all plugin mapped in the database".
- "In Plugin Mode, the screen displays the Analog Lab and Plugin parameter. It can also display the
  Analog Lab Browser." Fig.39 shows the idle screen: "ARTURIA / KeyLAB MKII".
- Plugin database implemented for the KeyLab mkII (p.17): FLEX, FPC, FL Keys, Sytrus, GMS, Harmless, Harmor,
  Morphine, 3x Osc, Fruity DX 10, BassDrum, Fruit kick, MiniSynth, Poizone, Sakura (15 plugins).
  Encoder/fader plugin control (2.2, 2.3) works only for these.
  Stock: same 15 in `KeyLabmk2Plugin.py:18-353` (spelled 'Fruity DX10', 'BASSDRUM', 'PoiZone').

## 3. Fact-check of the previous assistant's claims

Earlier assistant text is in `/home/delorenj/code/DeLoMIDI/THREAD.md` lines 178-185.

### C1. "The keyboard DAW port must be assigned controller type 'KeyLab mkII', enabled, with a port number such as 10."

Verdict: PARTIALLY CORRECT.
- Correct part: GUIDE p.4 Fig.2 and p.5 show the DAW port (`MIDIIN2 (KeyLab mkII 88)`; macOS `KeyLab mkII 88 DAW`)
  assigned the KeyLab controller script (`KeyLab mkII V2 (user)`) with the enable/power icon lit; p.5 says
  "Select the right script in the Controller type box under the 'Input Section'".
- Wrong part: the guide's DAW port number is **0**, not 10 (Fig.2 Windows Input and Output rows both 0; macOS both 0).
  Port 10 in the guide is only the Arturia plugin's MIDI input port (p.6 Fig.5-6; p.16 Fig.33-34; text "connect the
  plugin to the MIDI input 10"). The guide never says a hardware port should be 10.
- Risk (inference, UNVERIFIED): the Forward script tags forwarded CCs with port 10 (device_Forward CCs Port 10
  KEYLAB MKII.py:41), so numbering a hardware port 10 could route that port's raw events to any plugin whose input
  port is 10. The guide avoids the collision by using 0 and 1.
- Name caveat: the dropdown entry for the shipped file will be `KeyLab mkII (user)` (STOCK line 1), not "KeyLab mkII V2".

### C2. "On Windows the DAW input port is named 'MIDIIN2 (KeyLab mkII 88)' (on macOS 'KeyLab mkII 88 DAW')."

Verdict: CORRECT (screenshots only, the guide text never spells the names out).
- GUIDE p.4 Fig.2 Windows Input row `MIDIIN2 (KeyLab mkII 88)`, Output row `MIDIOUT2 (KeyLab mkII 88)`.
- GUIDE p.5 macOS Input and Output rows `KeyLab mkII 88 DAW` (the other row is `KeyLab mkII 88 MIDI`).
- Independent: ARTURIA-TIPS "The ports are called MIDIIN2 and MIDIOUT2 on Windows".

### C3. "The main keyboard port should be left as 'Generic controller' (rather than assigned the 'Forward CCs Port 10 KEYLAB MKII' script)."

Verdict: INCORRECT, contradicted by the guide.
- GUIDE p.4 Fig.2 (Windows) and p.5 (macOS): the main port (`KeyLab mkII 88`, macOS `KeyLab mkII 88 MIDI`) is
  assigned `Forward CCs Port..AB mkII V2 (user)` [`...LAB mkII V2`], enabled, port **1**, on both Input and Output.
- The only "(generic controller)" row in the guide is `ARTURIA MIDI In` (Windows, p.4), which is not the keyboard's main
  USB port.
- The guide never says the Forward script is optional. Its own name and header say it is the Arturia-plugin
  forwarder (lines 1, 12-13). It also feeds the main-port events into the same processor
  (`KL._processor.ProcessEvent(event)`, line 46) and calls `KL.init()` (line 27).
- Consequence (inference, UNVERIFIED without a MIDI monitor): the pads (status 153/137, notes 36-51) are remapped
  to FPC only inside `KeyLabMidiProcessor` (Process.py:127-128, 261-278). If the pads' port is the main port and it is
  left generic, no script sees them, so no FPC remap, no step-sequencer input. Analog Lab CC forwarding (port 10) also
  needs this script. The earlier assistant's tuned script, as described in THREAD.md line 168-176, only hardens the main
  entry script (the tuned file itself was not available to read here) and does nothing about the main-port assignment.

### C4. "The matching DAW OUTPUT port (MIDIOUT2 / DAW) must be set to the same port number, otherwise LCD and LEDs stay dark."

Verdict: CORRECT on the requirement. The stated consequence is not in the guide and rests on FL's own rules.
- GUIDE p.5: "Select a MIDI port for each Input as long as the input port and the output port of the same instance
  match ( see above )". Fig.2/p.5 show DAW output = DAW input port number (0/0) and main output = main input (1/1).
  The output rows are also set to the same script and enabled (Windows `MIDIOUT2 (KeyLab mkII 88)`, macOS `KeyLab mkII 88 DAW`).
- Mechanism: FL-MAN Device module: "MIDI scripts, assigned to an input interface, can be mapped (linked) to an Output
  interface via the Port Number. With mapped (linked) output interfaces, scripts can send midi messages to output
  interfaces by using one of the midiOut*** messages." All the LCD/LED traffic goes through
  `device.midiOutSysex` (`KeyLabmk2Dispatch.py:65-66`), so an unlinked output means nothing reaches the keyboard.
  "LCD and LEDs stay dark" is a reasonable consequence (UNVERIFIED on hardware, not written in the guide).
- The example number "10" in the earlier answer is not from the guide (guide uses 0).

### C5. "The keyboard must be put in a DAW mode / FL Studio option (via firmware / MIDI Control Center / front-panel) for the scripts to work."

Verdict: PARTIALLY CORRECT.
- DAW mode is required: GUIDE p.7 ("You can enter the DAW Mode by pressing the 'DAW' button... will make you able to
  control the DAW functions, the plugin parameters, the mixer and the step sequencer"); Analog Lab features need the Analog
  Lab button (p.16).
- The guide's documented method is the front panel only, and it is not an "FL Studio option": p.4 "set the *Live* program
  by long pressing on the *DAW* button ... and then by selecting the right program. At the end, there will be an update to
  create an FL Studio memory slot."
- The guide mentions no firmware step and no MIDI Control Center step. Those are not required by the guide.
- Corroboration outside the guide: ARTURIA-MAN 4.2/4.2.1 (p.33-34) has no FL Studio preset (nine presets: MCU, HUI, Ableton
  Live, Logic, Pro Tools, Cubase, Studio One, Reaper, MMC). The MCC does offer a "DAW Map" selector (section 8.16.2, p.80) as an
  alternative to the front panel. Firmware update only matters "If some of the features explained in this manual are not
  accessible" (section 8.18, p.82). Whether the user's firmware ever gained an "FL Studio" memory slot: UNVERIFIED.

### C6. "The script file name must start with device_ and live in Documents/Image-Line/FL Studio/Settings/Hardware/<folder>/ next to all helper files."

Verdict: CORRECT (location from the guide, the prefix from FL's manual).
- Location and "folder containing the script files": GUIDE p.3-4 (breadcrumb `Documents > Image-Line > FL Studio > Settings > Hardware`, folder named
  "KeyLab MkII V.1" in the guide; folder name is arbitrary per FL-MAN).
- `device_` prefix: not in the guide. FL-MAN: "Documents\Image-Line\FL Studio\Settings\Hardware\devicename\device_devicename.py ...
  NOTE: The 'device_devicename.py' prefix is mandatory for FL Studio to recognize the script"; the first-line `# name=` is required.
- Helpers beside the script: implied by the guide shipping one folder. FL-MAN says custom modules go in the Shared\Python\Lib
  folder, so sibling-file imports rely on FL adding the script's folder to the import path. That is how the stock set is built
  (every import is a sibling module). UNVERIFIED here.
- Related trap: the Forward script does `import device_KeyLabmkII as KL` (line 19). Any renamed or copied entry script
  (the earlier assistant's `device_KeyLabmk2.py`, THREAD.md line 168 and 213) will not be the module the Forward script imports.

## 4. Limitations and caveats stated by the guide

1. Scope: "generic scripts that handle all basic features for performance mode with visual feedback" (p.3).
2. Exclusive use: "Prepare your project before using the controller exclusively" and "You are now ready to use Arturia's controller
   exclusively" (p.5, p.7).
3. Only the Channel Rack, the Mixer, plugin windows "and some functions of the general UI" are managed (p.5). Nothing about the
   Playlist, Piano roll or arrangement.
4. Plugins must already be channels in the Channel Rack (p.5-6).
5. Arturia VSTs must have MIDI input port 10 and be linked to the right device in the plugin (p.6-7, p.16).
6. Plugin parameter control only for the 15 database plugins (p.17); the guide does not say what happens for others
   (stock: `Plugin()` returns empty param/value for an unlisted plugin, KeyLabmk2Plugin.py:398-401).
7. Next/Previous banking by 8 requires the Bank button on (p.12).
8. Analog Lab mode requires the plugin window to be focused via the center knob (p.16).
9. Pad mapping is "by default" the FPC layout (p.14); a customized FPC layout will not match.
10. Future feature stated as pending: an "FL Studio memory slot" update (p.4).
11. Internal inconsistencies of the guide itself: TOC page numbers drift (section 0); two consecutive headings
    numbered "2. FL Studio Setup" and "3. FL Studio Setup" (p.3, p.7); "9th encoder control the volume" should be slider (p.11);
    Fig.22 prints "Marker" while the text and overlay say "Metro" (p.12); the screenshots show `KeyLab mkII V2` while the shipped
    files are `KeyLab mkII`.
12. No stated FL Studio version support, no firmware requirement, no OS notes beyond Windows/macOS screenshots.

## 5. Where the guide disagrees with (or is silent about) the stock script or the prior advice

| ID | Severity | Item |
|---|---|---|
| G1 | high | Guide assigns the Forward script to the main keyboard port (port 1); prior advice leaves it generic. See C3. |
| G2 | medium | Guide port numbers are 0 (DAW) and 1 (main), not 10. Port 10 is plugin-side. See C1. |
| G3 | medium | Guide requires the "Live" DAW program (likely Arturia preset 3 "Ableton Live"), not MCU and not "FL Studio". The stock button numbers (Process.py:136-158) cannot be validated against whichever preset the user actually selected. A MIDI monitor capture is needed. UNVERIFIED. |
| G4 | medium | Tuned-script advice renames the entry file to `device_KeyLabmk2.py`, but the Forward script imports the module `device_KeyLabmkII` (device_Forward...py:19). |
| G5 | medium | Hardware settings the guide never mentions change what the FL script sees: "Track Control mode Single/Multi" (Multi turns Solo/Mute/Record into function selectors for the Select buttons, ARTURIA-MAN p.35 and p.80) and "DAW Fader mode Jump/Pickup" (p.40 and p.80). The guide's "Solo the selected track" only describes Single mode. Default unknown, UNVERIFIED. |
| G6 | info | Guide never documents the Mixer/Channel Rack mode switch, Browser push, pattern previous/next, Category/Preset/arrow buttons, RGB Select button press, button 9, wheels. See 2.10. |
| G7 | info | Arturia's own manual says "Encoder 9 does not have a function in DAW mode" (p.39); the FL guide gives encoder 9 a pan function (p.10). The FL script therefore must read the raw CC, which is not part of Arturia's DAW protocol description. |
| G8 | info | Label mismatches: "Marker" (Fig.22) vs "Metro" (text, overlay); fifth Track control shows "Off" in Fig.22 but ARTURIA-MAN 2.7.1 (p.15) calls it "Write". Which is printed on the user's 88 is UNVERIFIED. |
| G9 | low | Fig.26 shows FPC-colored pads in Drum Mode; stock sets all pads solid red (Return.py:238-239). |
| G10 | low | Plugin names: guide "BassDrum", "Poizone"; code compares 'BASSDRUM' (KeyLabmk2Plugin.py:258) and 'PoiZone' (line 329). Folder names on the FL 2025 install are `BassDrum` and `PoiZone` (`.../Plugins/Fruity/Generators/`). The string `ui.getFocusedPluginName()` actually returns is UNVERIFIED. |
| G11 | info | Forward script header `# receiveFrom=Forward CCs Port 10 KEYLAB MKII ` (line 2) points at itself with a trailing space; nothing calls `device.dispatch`, so it does nothing (FL-MAN: receiveFrom is for `device.dispatch`). |
| G12 | info | `PORT_MIDICC_ANALOGLAB = 10` (Process.py:23) is unused; the port is hardcoded in the Forward script (line 41). |

## 6. Open questions (need the hardware or a MIDI monitor)

1. Which USB port (main or DAW) carries the pads, encoders, faders, and each button in the "Live" preset? This decides whether the main-port script is mandatory.
2. Exact notes/CCs each DAW Commands button sends in preset 3 (Live) versus MCU. The guide gives none.
3. Which physical button sends the note the stock script uses for the mixer/channel-rack toggle (CC 51).
4. Real names of the controller entries in FL 2025/2026 after loading the shipped files.
5. Whether the user's firmware has a real FL Studio DAW memory slot (the guide says it was planned).
6. What "ARTURIA MIDI In/Out" is on the user's machine (probably the third USB/DIN port).

## 7. Minimal correct setup, as documented (for the implementer)

1. Folder `Documents\Image-Line\FL Studio\Settings\Hardware\<any name>\` containing all stock files (entry scripts start with `device_`).
2. Keyboard: hold DAW about 1 s, pick the "Live" program with the center knob (click to confirm), press DAW.
3. FL Options > MIDI, Input: `MIDIIN2 (KeyLab mkII 88)` -> KeyLab mkII (user), enabled, Port 0. `KeyLab mkII 88` -> Forward CCs Port 10 KEYLAB MKII (user), enabled, Port 1.
4. FL Options > MIDI, Output: `MIDIOUT2 (KeyLab mkII 88)` -> KeyLab mkII (user), enabled, Port 0 (must equal its input). `KeyLab mkII 88` -> Forward script, enabled, Port 1.
5. Any Arturia plugin: MIDI Input port 10.
6. Prepare the Channel Rack with the instruments to play; select channels with the center knob or the Select buttons.

Steps 2-4 are what the guide shows. Whether they actually work on FL 2025/2026 is UNVERIFIED (see section 1.6).
