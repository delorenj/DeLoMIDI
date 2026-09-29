| `channels.channelCount` | 4 | 0 | `(globalCount)` req 0 | 1 | OK | Group-respecting count by default (globalCount=False). | Process:294, Process:423, Process:435 +1 |
| `channels.channelNumber` | 27 | 0 | `(canBeNone, offset)` req 0 | 1 | OK+ | Returns the GLOBAL index; every other channels.*/plugins.* index parameter is group-relative by default (F5). Stubs: "replaces channelNumber"; mk3 uses selectedChannel(). | VCOL:50, Nav:170, Plugin:382 +24 |
| `channels.closeGraphEditor` | 2 | 1 | `(index)` req 1 | 33 | UNDOC | Not in manual; stub "closeGraphEditor(index, /)" documented as ???; engine has it; mk3 also calls it. Stock passes literal 1 (F9). | Process:738, Seq:33 |
| `channels.getChannelName` | 3 | 1 | `(index, uGI)` req 1 | 1 | OK | index group-relative; useGlobalIndex added API 33. See F5 for the two sites that pass channelNumber(). | VCOL:50, fwd:71, main:64 |
| `channels.getCurrentStepParam` | 2 | 3 | `(index, step, param, uGI)` req 3 | 1 | OK | Returns int; API 1 (note-repeat support added 25.1.1 without signature change). | Return:230, Seq:40 |
| `channels.getGridBit` | 2 | 2 | `(index, position, uGI)` req 2 | 1 | OK | position/step index; group-relative channel index. | Process:745, Return:229 |
| `channels.getTargetFxTrack` | 3 | 1 | `(index, uGI)` req 1 | 1 | OK | Returns mixer track index; fed to mixer.setTrackNumber. | Process:394, Process:399, Process:437 |
| `channels.isChannelMuted` | 9 | 1 | `(index, uGI)` req 1 | 1 | OK | Returns bool (manual says int). | Return:133, Return:204, Return:206 +6 |
| `channels.isChannelSelected` | 8 | 1 | `(index, uGI)` req 1 | 1 | OK | Returns bool. | Return:204, Return:206, Return:208 +5 |
| `channels.isChannelSolo` | 1 | 1 | `(index, uGI)` req 1 | 1 | OK | Returns bool. | Return:118 |
| `channels.isGraphEditorVisible` | 7 | 0 | `()` req 0 |  | OK | In the manual (row has no version cell); engine has it; mk3 uses it. | Process:668, Seq:56, Seq:65 +4 |
| `channels.muteChannel` | 1 | 1 | `(index, value, uGI)` req 1 | 1 | OK | 1-arg toggle. | Process:573 |
| `channels.selectOneChannel` | 1 | 1 | `(index, uGI)` req 1 | 8 | OK | API 8; group-relative index (bank math uses group indexes). | Process:436 |
| `channels.selectedChannel` | 1 | 0 | `(canBeNone, offset, indexGlobal)` req 0 | 5 | OK | Modern replacement (API 5); group-relative, matches getChannelName(). | main:63 |
| `channels.setChannelPitch` | 1 | 3 | `(index, value, mode, pickupMode, uGI)` req 2 | 8 | OK+ | Stock mode=1 with +-200: stub says mode 1 = cents (sane), manual says pitchUnit 1 = semitones (would be +-200 semitones). Conflict, UNVERIFIED (fwd:72). | fwd:72 |
| `channels.setGridBit` | 2 | 3 | `(index, position, value, uGI)` req 3 | 1 | OK | Group-relative channel index (F5). | Process:746, Process:749 |
| `channels.setStepParameterByIndex` | 7 | 6 | `(index, patNum, step, param, value, uGI)` req 5 | 1 | OK | useGlobalIndex passed as 0 with a global channelNumber() index (F5). | Seq:41, Seq:55, Seq:64 +4 |
| `channels.showEditor` | 2 | 1/2 | `(index, value, uGI)` req 1 | 1 | OK | value default -1 toggles; _hideAll() calls it for every channel on many button presses. | Process:295, Process:322 |
| `channels.showGraphEditor` | 7 | 5 | `(temporary, param, step, index, uGI)` req 4 | 1 | OK+ | Stock passes explicit useGlobalIndex=0; stub default is True, manual default False (drift). channelNumber() index (F5). | Seq:42, Seq:57, Seq:66 +4 |
| `channels.soloChannel` | 1 | 1 | `(index, uGI)` req 1 | 1 | OK | Stock passes 1 arg. Stub lacks the `value` param that manual (API 30) documents (drift). | Process:565 |
| `channels.updateGraphEditor` | 6 | 0 | `()` req 0 | 20 | UNDOC | Not in manual; stub (API 20?) undocumented; engine has it. | Seq:60, Seq:69, Seq:78 +3 |
| `device.forwardMIDICC` | 1 | 2 | `(message, mode)` req 1 | 7 | OK | fwd:66 msg=status+(d1<<8)+(d2<<16)+(10<<24), forwardTo=2 (selected channel). Stub param name `mode`, manual `forwardTo` (positional use unaffected). | fwd:42 |
| `device.midiOutSysex` | 1 | 1 | `(message)` req 1 | 1 | OK+ | Takes bytes (manual says string). 2026.1.4 fixed a crash when scripts send sysex (22414). See F1/F3. | Disp:66 |
| `device.processMIDICC` | 1 | 1 | `(eventData)` req 1 | 1 | OK | Process.py:258. | Process:258 |
| `mixer.armTrack` | 1 | 1 | `(index)` req 1 | 1 | OK | Toggle. | Process:303 |
| `mixer.getCurrentTempo` | 2 | 1 | `(asInt)` req 0 | 1 | OK+ | Used as BPM but FL returns tempo*1000 (mk3 evidence) (F6). asInt=1. | Nav:203, Return:285 |
| `mixer.getSongStepPos` | 2 | 0 | `()` req 0 | 1 | OK | int. | Return:270, Return:289 |
| `mixer.getSongTickPos` | 2 | 0 | `(mode)` req 0 | 1 | OK | Default mode ST_Int; used as a playing heuristic (!= 0). | Return:108, Return:280 |
| `mixer.getTrackPan` | 13 | 1 | `(index)` req 1 | 1 | OK | float -1..1. | Cross:41, Cross:43, Cross:45 +10 |
| `mixer.getTrackVolume` | 3 | 1 | `(index, mode)` req 1 | 1 | OK | Normalised 0..1 (0.8 = 0 dB). mode omitted. | Process:595, Process:604, Process:614 |
| `mixer.isTrackArmed` | 1 | 1 | `(index)` req 1 | 1 | OK | bool. | Nav:346 |
| `mixer.isTrackMuted` | 9 | 1 | `(index)` req 1 | 2 | OK+ | Track index up to 8*bank+8; dynamic mixer (F4). | Return:140, Return:178, Return:180 +6 |
| `mixer.isTrackSelected` | 8 | 1 | `(index)` req 1 | 1 | OK+ | Track index up to 8*bank+8; dynamic mixer (F4). | Return:178, Return:180, Return:182 +5 |
| `mixer.isTrackSolo` | 1 | 1 | `(index)` req 1 | 1 | OK | bool. | Return:125 |
| `mixer.muteTrack` | 1 | 1 | `(index, value)` req 1 | 2 | OK | 1-arg toggle. | Process:575 |
| `mixer.setTrackNumber` | 4 | 2 | `(trackNumber, flags)` req 1 | 1 | OK+ | Flags 3 = ScrollToMakeVisible|CancelSmoothing. Stub default 0, manual default -1, param name trackNumber vs index (drift). Arg may exceed dynamic track count (F4). | Process:394, Process:399, Process:431 +1 |
| `mixer.setTrackPan` | 10 | 2 | `(index, pan, pickupMode)` req 2 | 1 | OK+ | Track index may exceed dynamic track count (F4). | Cross:41, Cross:43, Cross:45 +7 |
| `mixer.setTrackVolume` | 10 | 2 | `(index, volume, pickupMode)` req 2 | 1 | OK+ | Track index may exceed dynamic track count (F4). 0.8*value scaling correct. | Cross:16, Cross:18, Cross:20 +7 |
| `mixer.soloTrack` | 1 | 1 | `(index, value, mode)` req 1 | 1 | OK | 1-arg toggle. | Process:567 |
| `mixer.trackNumber` | 13 | 0 | `()` req 0 | 1 | OK | Selected track index. | Nav:28, Nav:38, Process:302 +10 |
| `patterns.getPatternName` | 1 | 1 | `(index)` req 1 | 1 | OK |  | main:66 |
| `patterns.jumpToPattern` | 2 | 1 | `(index)` req 1 | 1 | OK+ | pattern+-1 is unbounded: stubs note jumping past the last pattern CREATES patterns; pattern-1 at pattern 1 targets index 0 (effect UNVERIFIED). | Process:447, Process:455 |
| `patterns.patternNumber` | 5 | 0 | `()` req 0 | 1 | OK |  | Nav:171, Process:446, Process:454 +2 |
| `playlist.getVisTimeBar` | 2 | 0 | `()` req 0 | 1 | OK |  | Nav:127, Nav:137 |
| `playlist.getVisTimeStep` | 2 | 0 | `()` req 0 | 1 | OK |  | Nav:128, Nav:138 |
| `plugins.getParamName` | 1 | 2 | `(paramIndex, index, slotIndex, uGI)` req 2 | 8 | OK | group-relative channel index (F5); paramIndex first. | Plugin:393 |
| `plugins.getParamValue` | 2 | 2 | `(paramIndex, index, slotIndex, uGI)` req 2 | 8 | OK | Returns float 0..1 (manual says int). group-relative index (F5). | Plugin:382, Plugin:394 |
| `plugins.nextPreset` | 1 | 1 | `(index, slotIndex, uGI)` req 1 | 10 | OK | group-relative index (F5). | Process:465 |
| `plugins.prevPreset` | 1 | 1 | `(index, slotIndex, uGI)` req 1 | 10 | OK | group-relative index (F5). | Process:470 |
| `plugins.setParamValue` | 1 | 3 | `(value, paramIndex, index, slotIndex, pickupMode, uGI)` req 3 | 8 | OK | Arg order (value, paramIndex, index); group-relative index (F5). | Plugin:391 |
| `transport.continuousMove` | 4 | 2 | `(speed, startStop)` req 2 | 1 | OK | SS_START=2 / SS_STOP=0 match real midi.py. | Process:511, Process:514, Process:531 +1 |
| `transport.getLoopMode` | 4 | 0 | `()` req 0 | 1 | OK | pattern=0, song=1. | Process:272, Return:227, Return:265 +1 |
| `transport.globalTransport` | 7 | 2/3 | `(command, value, pmeflags, flags)` req 2 | 1 | OK+ | 7 sites + FakeMIDImsg(FPT_Punch). Crash bug 22359 fixed 26.1.3; commands delayed bug 22298 fixed 26.1.2 (F1). Same idioms used by Arturia mk3 2024. | Process:313, Process:540, Process:550 +4 |
| `transport.isPlaying` | 1 | 0 | `()` req 0 | 1 | OK |  | Nav:89 |
| `transport.isRecording` | 3 | 0 | `()` req 0 | 1 | OK |  | Nav:112, Return:101, Return:254 |
| `transport.record` | 1 | 0 | `()` req 0 | 1 | OK |  | Process:486 |
| `transport.start` | 1 | 0 | `()` req 0 | 1 | OK |  | Process:491 |
| `transport.stop` | 1 | 0 | `()` req 0 | 1 | OK |  | Process:496 |
| `ui.crDisplayRect` | 2 | 5 | `(left, top, right, bottom, duration, flags)` req 5 | 1 | OK | (left, top, width, height, ms). 1000 ms is under the 2000 ms cap (26.1.5). Stub names right/bottom but documents width/height. | Process:507, Process:527 |
| `ui.cut` | 1 | 0 | `()` req 0 | 1 | OK |  | Process:546 |
| `ui.down` | 1 | 0 | `(value)` req 0 | 1 | OK |  | Process:372 |
| `ui.getFocused` | 24 | 1 | `(index)` req 1 | 1 | OK | Window ids 0,1,4,5 match real midi.py (widPlugin=5 valid only inside getFocused). | Nav:47, Process:289, Process:299 +21 |
| `ui.getFocusedNodeCaption` | 2 | 0 | `()` req 0 | 20 | OK |  | Process:373, Process:379 |
| `ui.getFocusedNodeFileType` | 1 | 0 | `()` req 0 | 20 | OK | -1 none; <=-100 folder-like. | Process:309 |
| `ui.getFocusedPluginName` | 2 | 0 | `()` req 0 | 5 | OK+ | Compared with hard-coded native plugin names; FL 2026 rebuilt FLEX (F10, UNVERIFIED). | Plugin:14, fwd:33 |
| `ui.getHintMsg` | 1 | 0 | `()` req 0 | 1 | OK |  | Nav:326 |
| `ui.getProgTitle` | 1 | 0 | `()` req 0 | 1 | OK |  | main:96 |
| `ui.getSnapMode` | 1 | 0 | `()` req 0 | 1 | OK | Modes 0,1,3..14 match manual Snap constants. | Nav:226 |
| `ui.getVisible` | 1 | 1 | `(index)` req 1 | 1 | OK |  | Process:287 |
| `ui.isInPopupMenu` | 3 | 0 | `()` req 0 | 1 | OK |  | Nav:316, Process:316, Process:368 |
| `ui.isLoopRecEnabled` | 2 | 0 | `()` req 0 | 1 | OK |  | Nav:147, Return:94 |
| `ui.isMetronomeEnabled` | 2 | 0 | `()` req 0 | 1 | OK |  | Nav:188, Return:80 |
| `ui.isPrecountEnabled` | 1 | 0 | `()` req 0 | 1 | OK |  | Return:87 |
| `ui.next` | 3 | 0 | `()` req 0 | 1 | OK |  | Process:378, Process:388, Process:398 |
| `ui.previous` | 3 | 0 | `()` req 0 | 1 | OK |  | Process:376, Process:384, Process:393 |
| `ui.selectBrowserMenuItem` | 1 | 0 | `()` req 0 | 20 | OK |  | Process:315 |
| `ui.setFocused` | 3 | 1 | `(index)` req 1 | 2 | OK |  | Process:290, Process:439, main:159 |
| `ui.showWindow` | 1 | 1 | `(index)` req 1 | 1 | OK |  | Process:288 |
| `ui.snapMode` | 1 | 1 | `(value)` req 1 | 1 | OK | Increment (+1). | Process:585 |
| `ui.up` | 1 | 0 | `(value)` req 0 | 1 | OK |  | Process:370 |
