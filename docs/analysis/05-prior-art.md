# 05 - Prior art and field reports: why "the KeyLab mkII script doesn't work at all" on Windows 11 + FL Studio 2025/2026

Analyst role: "prior art / field reports". Question: what does the internet actually know about the
Arturia KeyLab mkII (49/61/88) failing with FL Studio 2023-2026 on Windows 10/11, what have people
forked or fixed, what changed in FL's scripting since 2021, and how did Arturia restructure its
scripts for the mk3? Then: rank the most likely REAL-WORLD causes for the user's symptom and say how
each can be tested or mitigated in code versus in setup.

Nothing here was run on FL Studio or on the keyboard (host "tom" is unreachable). Every statement is
one of: read from a cited source, read from a local file (file:line), measured locally (labelled
MEASURED), or marked UNVERIFIED. Today is 2026-09-29; FL Studio 2026 = build 26.1.x (26.1 shipped
2026-07-02, latest build in the changelog is 26.1.6 dated 2026-09-02).

## 0. Executive summary

1. The stock set is not a "lost cause" script. It works only when four things line up, and none of
   them is checked by the script itself: (a) the keyboard is in DAW mode with the right DAW program,
   (b) the DAW port (`MIDIIN2`/`MIDIOUT2 (KeyLab mkII 88)`) is assigned the `KeyLab mkII` script with
   matching input/output port numbers, (c) the main port is assigned the "Forward CCs Port 10" script,
   (d) nothing else holds those ports and Windows exposes them. Arturia's own screenshot uses port 0 for
   the DAW port and port 1 for the main port, not 10 (guide p.4-5).
2. The internet has almost no field reports of the mkII script itself breaking on FL 2025/2026. What it
   does have is (i) a very clear 2026 Windows-side story (Windows MIDI Services, Arturia and
   Image-Line both document it), (ii) an Image-Line changelog that shows several 2026.1.x fixes to
   script/sysex/device-scan crashes, and (iii) community forks that confirm the same ports and DAW-mode
   requirements and that also work on FL 2026.1.6 on Windows (one, AI-assisted, single-author).
3. The prior assistant's hypothesis (missing import) is ruled out statically: every helper file exists;
   the only non-FL stdlib import in the stock set is `time`; FL 2025's embedded Python 3.12.1 has `time`
   built in (MEASURED); all 12 stock files compile under it with warnings promoted to errors (MEASURED).
4. Two of the prior assistant's setup claims are contradicted by Arturia's own guide (C1 "port 10",
   C3 "leave the main port Generic") and one is imprecise (C5 "FL Studio option": there is none in the
   manual). See section 6.
5. Best action with the host unreachable: ship a tiny diagnostic script (section 8) that prints FL
   build, Python version, device name, port number, `device.isAssigned()`, and the first raw events, so
   the user can answer in one minute which of R1-R6 is real.

## 1. Evidence grading and access limits

Confidence labels: High = vendor or FL documentation plus at least one independent report, or a local
measurement; Medium = one authoritative source or several weak ones; Low = inference.

Sources I could NOT read (all probably relevant to (b), so absence of evidence is not evidence of absence):

| Source | Why not | Effect |
|---|---|---|
| Image-Line forum thread "Arturia Keylab 49/61/88 Essential/mkII [SCRIPT]" (t=243170), rjuang's discussion thread | Server 302s to a login page (also for curl) | Cannot see user reports on that thread |
| Image-Line forum "Arturia : MiniLab mkII / KeyLab mkII / KeyLab Essential [OFFICIAL SCRIPT]" (t=262947) | Login-gated | The stock script's own support thread is unreadable |
| legacy-forum.arturia.com topics 102015, 107883, 108775 | HTTP 503 (Retry-After 3600) | Arturia's old forum posts unread |
| Reddit r/FL_Studio, KVR | Search returned no relevant threads | No field reports found there |
| Microsoft MIDI Discord (#workarounds) | Not reachable | Linked workarounds not read |

Read successfully (via WebFetch, curl, or Arturia's help-center JSON API): Arturia FAQ articles, Arturia
downloads page and mkII manual v2.2.0, FL online manual (scripting, MIDI settings, What's New), FL
release threads (public parts), several Image-Line forum threads (public parts), GitHub repos and issues,
Microsoft MIDI docs and dev blog. Cached copies live in the scratchpad `research/` directory.

## 2. What is the stock script, where does it come from, who maintains it

- Author string in the file: "Developer: Farès MEZDOUR, Version: Beta 1.0" (device_KeyLabmkII.py:5-8).
  The same developer name is on Arturia's mk3 script (device_KL3.py:7-9), so the mkII and mk3 sets are
  by the same Arturia author, three years apart.
- The user's folder `Arturia KeyLab MKII` sits next to `Arturia KeyLab MKII.ini` (contents
  `[Ini] Version=1`). MEASURED: folder birth time 2025-06-12 06:04, file mtimes preserved from the
  package (2021-11-15). The same pattern exists for `Arturia KeyLab Essential`, `Arturia KeyLab mk3`,
  `Arturia MiniLab MKII`, `MackieCU` (downloaded 2026-01-29, Version=2) and others. The FL manual
  describes exactly this: "In the Hardware folder there will be a device-named .ini file and
  device-named folder for each supported device... If you want to force a clean install you must delete
  the .ini file and folder for target devices. Then click Update MIDI Scripts"
  (https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_midi.htm).
  Conclusion (High, MEASURED + FL manual): the stock mkII script is an Image-Line-server-distributed
  script that FL manages itself. Edits inside that folder can be overwritten by "Update MIDI Scripts"
  or a server-side version bump. Keep our tuned copy in a separate folder.
- Arturia's own current FAQ for FL Studio does NOT tell mkII users to use this script. It says: set the
  keyboard's "DAW map" to "Default MCU" in the MIDI Control Center, then in FL set the MIDI port as
  Generic controller on Port 1 and the DAW port to "Mackie Control Universal" on Port 2 and the DAW
  output to Port 2; "the ports are called MIDIIN2 and MIDIOUT2 on Windows"
  (https://support.arturia.com/hc/en-us/articles/4405748362002-KeyLab-MkII-Tips-Tricks, article updated
  2026-09-13). The script route is documented only in the guide PDF that ships inside the script folder.
  So there are two official, incompatible recipes (MCU vs script) and it is easy to mix them.
- Arturia's FAQ "General Questions" (updated 2026-08-26) lists DAW-mode support as "the scripts for
  Ableton Live, Logic Pro X, Pro Tools, Cubase, Studio One and Reaper, or the standard MCU / HUI protocols",
  i.e. FL Studio is not in the list
  (https://support.arturia.com/hc/en-us/articles/4405741178770-KeyLab-MkII-General-Questions).
- Firmware: latest published is 1.3.1.1492 dated 2021-11-16; MIDI Control Center 1.23.0.134 dated
  2026-06-10; mkII manual v2.2.0 dated 2021-11-15
  (https://www.arturia.com/support/downloads-manuals/product/keylab-88-mkII). Nothing on that page
  mentions FL Studio or release notes. So the hardware side has been frozen since 2021 while FL and Windows
  moved on for five years.
- Image-Line staff position in 2019 (thread t=213999, "saif.sameer", 2019-12-08): "Currently, if the controller
  is set to DAW => MCU then it will work fine with FL Studio" and "the MCU mode doesn't allow permanent
  mapping / linking" (https://forum.image-line.com/viewtopic.php?t=213999). This is the ancestor of
  Arturia's "Default MCU" FAQ.

## 3. Ranked real-world causes (Windows 11 + FL 2025/2026)

Ranking is likelihood x impact for the user's exact symptom ("doesn't work at all" with the stock mkII script
on FL 2026, Windows 11). "critical" is used only where multiple independent sources report it.

### R1 - Port wiring in FL's MIDI Settings does not match what the script needs  (severity: critical, confidence: High that it is required, Medium that it is the user's problem)

What the sources say the wiring must be:
- Arturia guide (local PDF) p.4 Fig.2 (Windows) and p.5 (macOS): two entries are configured. DAW port
  (`MIDIIN2 (KeyLab mkII 88)` / `MIDIOUT2 (KeyLab mkII 88)`; macOS `KeyLab mkII 88 DAW`) = the main script,
  enabled, port **0**, input and output the same. Main port (`KeyLab mkII 88`; macOS `... MIDI`) = the
  "Forward CCs Port 10 KEYLAB MKII" script, enabled, port **1**, input and output the same. Text p.5:
  "Select a MIDI port for each Input as long as the input port and the output port of the same instance
  match".
- FL manual (MIDI settings): "Specially supported controllers may require their Port number be set to the
  same number in the Input and Output lists... Any number between 0 and 255 can be used. Avoid using the same
  Port number for different devices or they will conflict"
  (https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_midi.htm).
  `device.getPortNumber()` "is same number as interface port number set in FL Studio Midi settings" and
  returns -1 when unassigned; `device.isAssigned()` "Returns True if (linked) output interface is assigned";
  `device.midiOutSysex` sends to "the (linked) output interface"
  (https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm). Every LCD
  and LED write in the stock set goes through `device.midiOutSysex` (KeyLabmk2Dispatch.py:65-66), so an
  unassigned or mismatched output means a silent, dark keyboard while the script still "loads".
- Arturia mk3 FAQ, same convention: "Make sure that the KeyLab mk3 DAW has the same port selected for both
  Input and Output sections" (https://support.arturia.com/hc/en-us/articles/15637916754204-KeyLab-mk3-DAW-Integration).
- Community: rjuang README says "select your Arturia device (the DAW one)" under Input and pick the DAW script
  (https://github.com/rjuang/flstudio-arturia-keylab-mk2). The IcedRooibos fork adds "make sure under the Output
  section of midi settings, the port for 'Keylab mkII 61' device is set to unassigned" for its own script
  (https://github.com/IcedRooibos/flstudio-arturia-keylab-49-essential).
- Field report: rjuang issue #1 (2021-01-24) - FW 1.2.4, Windows 10, FL 20.7.2, script assigned to `MIDIIN2 (KeyLab mkII 61)`,
  "there is no sign 'Connected to FL Studio' on the screen"; with Mackie Control Universal it "works". The real cause
  was a missing `plugins` module in 20.7.2 (fixed in the script), not the ports, but the visible symptom is
  identical (https://github.com/rjuang/flstudio-arturia-keylab-mk2/issues/1).

Failure modes inside R1 that no one warns about:
1. Assigning the script to the first port (`KeyLab mkII 88`) instead of `MIDIIN2`.
2. Enabling the input but leaving `MIDIOUT2` unassigned or on another port number.
3. Assigning "KeyLab mkII" but never assigning the "Forward CCs Port 10" script on the main port: the DAW port carries
   the DAW-mode controls, the main port carries plugin/Analog Lab CCs and pads (UNVERIFIED which physical controls
   use which port; see the sibling analysis of the stock code).
4. Using port 10 for the DAW port (prior assistant's advice). Port 10 is the routing number Arturia plugins listen on
   (guide p.6, Analog Lab MIDI input 10; the Forward script forwards with `(10 << 24)`,
   device_Forward CCs Port 10 KEYLAB MKII.py:38-42; FL doc for `forwardMIDICC`: "midi input port of plugin must be equal
   to port specified in message"). FL says to avoid sharing port numbers between devices. Inference (Low): an unhandled
   event from a DAW port also numbered 10 could be delivered to plugins listening on 10.
5. FL keys these assignments by the port NAME. If Windows renames or re-orders the ports (R6, R8), the assignment is
   silently lost. (Microsoft: "applications which remember ports by name will need to be pointed at them again",
   https://microsoft.github.io/MIDI/tools/settings/.)

Test: diagnostic script (section 8) prints `device.getName()`, `device.getPortNumber()`, `device.isAssigned()` in
`OnInit` for each assigned instance.
Code mitigation: (a) in `OnInit`, if `not device.isAssigned()` or `device.getPortNumber() < 0`, print a loud line and
`ui.setHintMsg(...)`; (b) never assume sysex reaches the device. Setup mitigation: copy Arturia's Fig.2 exactly, using
0/1 (or any two unique numbers that are not 10), and re-check after every Windows update.

### R2 - Keyboard not in the DAW mode/program the script expects  (severity: high, confidence: Medium-High)

- Guide p.4 "Memory Selection": "set the *Live* program by long pressing on the *DAW* button ... At the end, there
  will be an update to create an FL Studio memory slot." Guide p.7: "You can enter the DAW Mode by pressing the 'DAW'
  button". Manual v2.2.0 printed p.34 (PDF p.39) lists nine DAW presets: Standard MCU, Standard HUI, Ableton Live,
  Logic Pro X, Pro Tools, Cubase, Studio One, Reaper, MMC. There is no FL Studio preset. Manual printed p.80 (PDF
  p.85): "DAW Map: This lets you use the MCC to select which DAW preset your KeyLab mkII will use"
  (https://dl.arturia.net/products/keylab-49-mkII/manual/keylab-mkii_Manual_2_2_0_EN.pdf).
- Community: rjuang README "IMPORTANT ... make sure that you set it to use the DAW mode (i.e., the DAW button is selected
  as opposed to the User or Analog Lab buttons)"; same in the IcedRooibos fork. Arturia FAQ says MCC DAW map = "Default MCU".
- Code fact: the stock processor treats faders as Mackie-style pitch-bend (status 0xE0-0xE8), translating
  `event.data1 = 2 + event.status - event.midiId` and treating 0xE8 (232) as master (KeyLabmk2Process.py:591-600).
  Both the "Live" and MCU presets are Mackie-protocol presets per the manual (printed p.34 "Using the industry standard
  Mackie HUI or MCU protocols"), which is why either can work; a User preset, or a DAW map set for another DAW, would not.
- UNVERIFIED: whether firmware 1.3.1 (2021-11-16, one day after the guide's 2021-11-15 files) ever added an FL Studio slot.
  The manual v2.2.0 dated 2021-11-15 does not list one, and no source found says one exists.
- The firmware version and active DAW program on the user's keyboard are unknown to us.

Test: diagnostic script logs the first 20 raw events (status, data1, data2, port, sysex). Moving fader 1 should
produce status 0xE0 (224) on the DAW port if a Mackie-based preset is active.
Code mitigation: a "mode probe" that infers the preset from observed message types and prints a hint. Setup: DAW button
(long-press) -> pick "Ableton Live" (guide) or "Standard MCU"; do not use User/Analog Lab for the DAW controls.

### R3 - Windows 11 24H2/25H2 "Windows MIDI Services" stack  (severity: high, confidence: High that it is real, Low-Medium that it hits this device)

Independent sources (Arturia, Image-Line, Microsoft, a third-party vendor) all document 2026 breakage of MIDI
devices/ports on Windows 11 caused by the new stack:
- Arturia, "Compatibility with Windows 11" (updated 2026-09-24): "Since the release of Windows 11 24H2 and 25H2 ... a new
  MIDI Service was introduced and my possibly prevent correct communication from our devices with MIDI applications ...
  'Failed to open the device' ... In case the device would be identified via the Windows Device manager but device ports
  not available or displayed via applications": set the "Windows MIDI Service"/`midisrv` startup to Automatic, toggle it,
  else run Arturia's `midifixreg` utility (admin prompt), reboot, replug
  (https://support.arturia.com/hc/en-us/articles/4407871884818-Compatibility-with-Windows-11; repeated in
  https://support.arturia.com/hc/en-us/articles/6878166158108-Troubleshoot-USB-detection-Communication-issues).
- Image-Line forum, moderator sticky "Windows MIDI Services / 'New MIDI Stack'" (Yearofthegoat, 2026-03-25, updated
  2026-04-12): "several posts of problems with MIDI controllers ... related to the new Windows MIDI Services which were
  rolled out via Windows Update in late February/early March"; drivers for certain controllers are "broken"
  (Korg, Akai/inMusic) (https://forum.image-line.com/viewtopic.php?t=339802). And a user tip 2026-07-26: "Windows
  Tools/Services and then disable Windows MIDI Services. You may need to restart FL studio or Reboot"
  (https://forum.image-line.com/viewtopic.php?p=2068443).
- Microsoft: rollout began end of January 2026 (KB5074105 preview), announced 2026-02-17 as "phased enablement" to in-support
  retail Windows 11; known issues list includes apps that hang or list devices slowly, dynamic ports invisible, identical device
  names, inMusic driver lock-ups, timestamps in the future (fixes "rolling out April 30")
  (https://blogs.windows.com/windowsexperience/2026/02/17/making-music-with-midi-just-got-a-real-boost-in-windows-11/,
  https://devblogs.microsoft.com/windows-music-dev/windows-midi-services-rollout-known-issues-and-workarounds/,
  https://learn.microsoft.com/en-us/answers/questions/5732319/after-windows-26220-7653-update-midi-ports-disappe -
  Ableton "can only read the first ten midi devices", ports lost after Insider build 26220.7653).
- inMusic KB: "real-time MIDI messages do not pass correctly from the device to the application", KB5074105/5077181/5077241,
  workaround uninstall the update, "class-compliant MIDI devices are generally unaffected"
  (https://support.inmusicstore.com/en/support/solutions/articles/69000876838-midi-devices-not-working-after-windows-update).
- Arturia lists KeyLab MKI/MKII as class-compliant (needs no vendor driver) - the least affected class in Microsoft's notes
  (https://support.arturia.com/hc/en-us/articles/6878166158108-Troubleshoot-USB-detection-Communication-issues). That lowers the
  likelihood for the mkII, but Arturia's own 2026 article says its hardware can be affected (it names the MIDI Control Center
  "Failed to open the device").
- FL Studio very likely still talks to the legacy WinMM interface (a search-result summary of the FL forum thread
  https://forum.image-line.com/viewtopic.php?t=306447 says an Image-Line developer had not implemented anything for MIDI 2.0 as of June 2023;
  I did not open that thread, so UNVERIFIED for 2026 builds). Microsoft says WinMM is "repointed to the new Windows Service"
  (https://microsoft.github.io/MIDI/), so a WinMM app such as FL sees the new stack through translation.
- Positive for the user: they report the generic controller "sucks", implying the main port enumerates and delivers notes, so
  total port loss is unlikely; a broken SECOND port, or a renamed one (R8), is the scenario that would kill only the DAW script.

Test: MIDI-OX or Arturia MCC "MIDI Console" (Arturia FAQ points to it) while FL is closed: do both USB ports appear and pass
data? `sc query midisrv` / services.msc. In FL, check whether `MIDIIN2 (KeyLab mkII 88)` and `MIDIOUT2 (...)` are listed.
Code mitigation: none can fix enumeration; scripts can only report. Setup: service Automatic, `midifixreg`, update MCC (1.23.0.134),
plug the keyboard in before starting FL, or as a last resort disable Windows MIDI Services (Image-Line forum tip; UNVERIFIED for this device).

### R4 - Ports held by another program (single-client class driver) or by FL itself  (severity: high, confidence: Medium-High)

- Arturia: "Class Compliant 'Plug & Play' devices on Windows (without dedicated drivers) can only communicate with one application at a
  time, so make sure ... to close any other running applications"; "'Plug & Play' devices on Windows are currently Mono-Client" and
  KeyLab MKII is on that class list (https://support.arturia.com/hc/en-us/articles/19499946683932-Common-MIDI-issues-Troubleshoot,
  https://support.arturia.com/hc/en-us/articles/6878166158108-Troubleshoot-USB-detection-Communication-issues).
- FL Studio message when this happens: "The MIDI input device couldn't be opened. It may be in use by another application." Recent
  threads: t=333361 (2025-04-22, FL Mini), t=337036 (2025-10-17, Akai MPK and a KeyLab 61 Essential mentioned, unresolved)
  (https://forum.image-line.com/viewtopic.php?t=333361, https://forum.image-line.com/viewtopic.php?t=337036). FL 2024.2.2 changelog:
  "Show slightly better error messages when a MIDI device can't be opened".
- rjuang commit 2021-03-23: "Refactoring plugin so that an output MIDI port is no longer required for the MIDI script portion. This frees
  up the output port on windows for analog lab" - independent evidence that on Windows an FL-held output port starves Arturia software of it
  (https://github.com/rjuang/flstudio-arturia-keylab-mk2). The stock Fig.2 wiring assigns BOTH outputs (main port and DAW port) to FL.
- The user must have used MIDI Control Center to set the DAW map (Arturia FAQ). If MCC, Analog Lab standalone, or a browser tab with Web MIDI
  is still open, FL cannot open the port (pre-MIDI-Services behaviour; with Windows MIDI Services active the ports are multi-client, which
  is the reverse problem: R3).

Test: close MCC/Analog Lab/other DAWs, restart FL, watch for the "couldn't be opened" pop-up; the diagnostic script never gets `OnInit` if
the port is not opened (absence of `init ok` in Script output is itself the tell). Setup: run only one MIDI client at a time on Windows without
MIDI Services. Code: none.

### R5 - FL Studio 2026.1.x script/sysex/device-scan regressions in older builds  (severity: high, confidence: Medium; depends on the exact build)

From the Image-Line changelog (https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/WhatsNew.htm), mapped to builds:

| Build (date) | Item | Why it matters to the stock set |
|---|---|---|
| 26.1.3 (2026-07-24) | 22368 "Freezes when MIDI scripts call functions in FL Studio"; 22367 "Crash when reading the list of MIDI scripts at startup"; 22359 "crash when using GlobalTransport commands" | Stock calls FL API constantly from `OnIdle` and `OnRefresh`; script list read at startup |
| 26.1.4 (2026-08-06) | 22414 "MIDI scripting: crash when processing sysex messages from a script"; 22416 "mixer functions don't work correctly with 'current' track"; 22438 "Crash when scanning midi devices" | Every stock LCD/LED update is a script-originated sysex (KeyLabmk2Dispatch.py:65-66); stock also uses `mixer.trackNumber()` |
| 26.1.5 (2026-08-18) | 22496 "Crash finding MIDI scripts if the user data folder is cloud-based"; 22483/22523 device-scan crashes; 22544 "limit the duration of DisplayRect functions to maximum 2 seconds" | See R7. The stock set calls `ui.crDisplayRect(left, top, 16, 1, 1000)` (KeyLabmk2Process.py:507, 527) with a 1000 ms duration, which is under the new 2 s cap, so no effect expected |
| 26.1.6 (2026-09-02) | 11872 "Show a notification when a new controller is connected" | See R11 |
| 2024.1 RC1/RC2 (2024-06) | 17881 "Crash when disconnecting Arturia Keylab 66 Essential controller" | Only Arturia-specific item in the whole changelog; the Essential script is the mkII's sibling |

So a user on 26.1 to 26.1.3 who runs the stock script (many sysex per idle tick) is exposed to a documented crash class; the
fix landed 2026-08-06. The user said "FL Studio 2026" without a build number: UNVERIFIED.

Test: Help > About in FL; `ui.getVersion()` in the diagnostic. Code mitigation: sysex de-duplication and throttling (the prior
assistant's 100 ms throttle is in the right spirit; the mk3 script also skips refresh work for flags 4 and 4096, section 5).
Setup: update FL to 26.1.6 or newer.

### R6 - Port names change or the ports are not where the guide says  (severity: medium, confidence: Medium; rising)

- Naming background (Microsoft): WinMM names the first port with the device name and later ports `MIDIIN2 (Device)` / `MIDIOUT2 (Device)`;
  the ordinal is a WinMM enumeration index (https://microsoft.github.io/MIDI/kb/midi1-name-mapping/). Arturia's `MIDIIN2`/`MIDIOUT2` are exactly
  this pattern, and the guide screenshot (p.4) shows `MIDIIN2 (KeyLab mkII 88)`.
- Windows MIDI Services keeps "classic API names" by default per endpoint: "A device that supplies no port names of its own has nothing to
  gain from a new-style name, so it keeps its WinMM-compatible names" (same KB). A naming rework ("Midi1PortNamingApproach.UseAutomatic",
  jack names first) is marked "Fixed in the November 2026 11D release" (https://github.com/microsoft/MIDI/issues/1202), and Image-Line users
  are already discussing the November 2026 update (https://forum.image-line.com/viewtopic.php?t=342586, 2026-09-23). Microsoft's own warning:
  "New style ... will make applications that remember port names by string ask you to pick the device again"
  (https://microsoft.github.io/MIDI/tools/settings/).
- UNVERIFIED: whether the KeyLab mkII's USB descriptors carry iJack strings (which decides whether its names would change), and whether the
  user's Windows already has the naming rework.

Test: read the actual names in FL's MIDI Settings on tom. Code mitigation: `# supportedDevices=` and hardware-id auto-linking (section 5) reduce
dependence on names; do not hard-code a name. Setup: re-assign after Windows feature updates.

### R7 - Script folder handling: cloud-synced user data, FL-managed folder, sys.modules collisions, script list caching  (severity: medium, confidence: Medium)

- OneDrive/cloud: Image-Line KB "Problems with cloud storage services and FL Studio": OneDrive "may sometimes be installed during a Windows
  update"; disable cloud services for folders FL needs (https://support.image-line.com/action/knowledgebase?ans=732). Changelog 22496 (26.1.5)
  fixed a crash finding MIDI scripts when the user data folder is cloud-based. Windows 11 commonly redirects Documents into OneDrive (UNVERIFIED for tom).
- FL-managed folders: section 2. Editing inside `Arturia KeyLab MKII` risks overwrite; deleting the `.ini` plus folder and clicking "Update MIDI Scripts"
  is FL's documented clean-install path. Our tuned copy must live in its own folder with its own `# name=`.
- Loading rules (FL manual): `Documents\Image-Line\FL Studio\Settings\Hardware\devicename\device_devicename.py`; the `device_` prefix is "mandatory";
  first-line `#name=` is "required"; folder name arbitrary; scripts directly in `Hardware\` are ignored (rjuang README: "Make sure the scripts are in a subfolder
  within the Hardware folder. Otherwise, FL Studio will ignore the files."). New scripts appear in the Controller type list after "Update MIDI Scripts" or an FL
  restart (Arturia mk3 guide p.2 tells users to press "Update MIDI scripts").
- Module-name collisions (Low, UNVERIFIED): stock helpers have generic names (`KeyLabmk2Process`, `ArturiaVCOL`). If both the stock folder and a tuned copy are
  enabled or were loaded in the same FL session, FL's single interpreter could resolve `import KeyLabmk2Process` from the wrong folder. I found no source that
  documents FL's per-script module isolation either way. Mitigation: give tuned helper modules unique names and never enable both sets at once.

### R8 - FL API drift 2024.1 to 2026.1 against a script that hard-codes the old mixer and has no error handling  (severity: medium-low, confidence: Low)

- 2024.1 (Feb-Jun 2024): "The scripting engine now uses Python 3.12" (16611); "added support for keyword arguments" (15040); "changed some parameter names to be
  more descriptive" (17108); "API errors raise the wrong type of exception" (17588, fixed 2024-05-14 beta) - i.e. exceptions changed type, so `except` clauses had
  to be revised; "OnDeInit is not called" (17468) and "crash when there is an error in a script" (17511).
- 2025.1 (mid-2025): "scripting functions have been updated for the dynamic mixer" (19548, 25.1 beta 4), "crash when an invalid mixer track number is used" (19997, fixed in
  beta 7), "added a function to check how many mixer tracks exist" (19862), `OnInitAll` (19777). FL 2025 lets users add and delete mixer tracks, so the old assumption
  "tracks 1-125 exist" no longer holds.
- Stock code: hard-coded track indices `mixer.setTrackVolume(1 + 8*MX_OFFSET, ...)` up to 8 + 8 per bank (ArturiaCrossKeyboardKLmk2.py:11-33) and a `MAX_TRACKS = 125`
  bound (KeyLabmk2Process.py:56, used at :412); no `try/except` anywhere in the stock set (MEASURED by grep: zero matches; mk3 has none either).
- Ruled out: Python 3.12 syntax/library removals. All 12 stock files compile under FL's own 3.12.1 with warnings-as-errors; the only stdlib import is `time`.
- No field report ties any of this to the mkII script. Treat as a robustness backlog, not as the root cause.

Test: sim harness replaying fader/encoder events against a stub with a small mixer. Code mitigation: `mixer.trackCount()` guard; catch `RuntimeError`.

### R9 - Port 10 collisions and Analog Lab routing  (severity: medium-low, confidence: Low-Medium)

Covered in R1 item 4. Independent of the DAW port, the Forward script requires each Arturia plugin's MIDI input to be set to port 10 (guide p.6; rjuang README: "you'll
still need to configure Analog Lab plugin's MIDI In port to 10. This needs to be done for each plugin"). If the user tests with plugin channels not set to 10, controls appear
dead even though the script works. FL doc for `forwardMIDICC`: "midi input port of plugin must be equal to port specified in message".

### R10 - FL 2026 replaced built-in MCU with a script (matters if the user falls back to Arturia's MCU recipe)  (severity: low-medium, confidence: Medium)

- 26.1 beta 1 (2026-03-24): "MIDI scripting: replaced the built-in MCU support with the script" (20506); 26.1.4: "Remove Mackie Control Universal from the legacy list of supported MIDI devices" (22403).
  MEASURED: the user's `Hardware\MackieCU\` (device_MackieCU.py, dated 2026-01-13, `.ini` Version=2) was fetched on 2026-01-29.
- Arturia's FAQ recipe still says "Mackie Control Universal". So the fallback path now depends on a downloaded script, which needs "Update MIDI Scripts" and network access.
  I found no field report of it failing for KeyLab (UNVERIFIED).

### R11 - New in FL 26.1.6: "Show a notification when a new controller is connected" (auto-detect)  (severity: low, confidence: Low)

FL now offers to enable newly connected controllers. Auto-detect uses `supportedDevices`/`supportedHardwareIds` headers (FL manual) which the stock mkII script does not have; the mk3 script has
`supportedHardwareIds` (device_KL3.py:2). Older changelog: "Autodetected controllers can't be set to the 'genericcontroller' type" (12378, 20.9). Risk: FL may create default assignments the user
then edits by hand. UNVERIFIED that it has any effect on the mkII.

### R12 - "Missing import / script died in OnInit" hypothesis  (severity: low, confidence: High that it is not the cause for the stock set)

- All helper files exist in the user's stock folder (`ls`: ArturiaCrossKeyboardKLmk2.py, ArturiaVCOL.py, KeyLabmk2*.py, both `device_*.py`).
- Only non-FL stdlib import: `time` (KeyLabmk2Display.py, KeyLabmk2Return.py, device_KeyLabmkII.py:12). MEASURED under `wine python.exe` from FL 2025's Shared\Python (3.12.1):
  `'time' in sys.builtin_module_names` -> True (also `_heapq`, `_random`).
- MEASURED: `compile()` with `warnings.simplefilter('error')` succeeds for all 12 stock files under 3.12.1.
- The community failures that were import-related do not transfer: rjuang #1 (20.7.2 lacked the `plugins` module), #4 (FL 21 on macOS, `_heapq`), #5 (same root cause; comment
  "fl swallows errors so often the root cause is obscured by a module loading error") all concern rjuang's own script, which imports `_heapq`, `_random` and a binary `pykeys.cp39-win_amd64.pyd`
  (built for Python 3.9) - none of which the Arturia stock set uses (arturia_scheduler.py:1-3; macro_actions.py:25-30).
- Lesson worth keeping: FL reports script errors poorly, so check View > Script output for `init ok` before believing any theory.

### R13 - Hardware/firmware  (severity: low, confidence: Medium)

Firmware 1.3.1.1492 (2021-11-16) is the latest; rjuang's report used FW 1.2.4 (2021) and other users FW 1.3.1 (issue #5, 2023, macOS). No source ties any firmware to a scripting regression. Factory
reset (hold "Octave up" + "Octave down" at power-up, then press the jog wheel) and MCC are documented by Arturia.

## 4. Ecosystem of forks and prior fixes

| Project | What it is | Relevance |
|---|---|---|
| https://github.com/rjuang/flstudio-arturia-keylab-mk2 (67 stars, last push 2022-05-18, MIT) | Independent rewrite for mkII and Essential; two scripts `Arturia Keylab mkII DAW (MIDIIN2/MIDIOUT2)` and `Arturia Keylab mkII (MIDI)`; needs DAW mode; Analog Lab port 10 | Confirms port names, DAW mode, subfolder rule. Not maintained since 2022; open issues #4, #2. Uses Python-3.9-era binaries and `_heapq` |
| https://github.com/IcedRooibos/flstudio-arturia-keylab-49-essential | Fork of rjuang (56 commits, last push 2021-03-23) | Windows note: leave main output unassigned |
| https://github.com/mchelmb/flstudio-arturia-keylab-essential (created 2026-09-14) | AI-assisted fork of rjuang "working for FL Studio 2025 and up"; README table: tested on Essential 61 mk2, FL 2026 build 26.1.6, Windows, Python 3.12.1; "KeyLab mkII (same underlying script family)" untested | Only public evidence a KeyLab-family script runs on FL 2026 on Windows. Single author, no external users (0 stars). It states the AI "did not have access to a running FL Studio instance" - treat as weak but useful |
| https://github.com/yanncharlou/ArturiaEssentialForFLStudio (2020) | KeyLab Essential script | Historical |
| Arturia forum thread "MIDI script for KeyLab MK2 and FL Studio" (https://forum.arturia.com/t/midi-script-for-keylab-mk2-and-fl-studio/2782) | 2024-01-05 EranH: a downloaded script "improved connectivity ... however brought undesired functionality. Pushbuttons are blinking"; reply LBH: "I don't think Arturia have made any scripts for Keylab MK2" and "remove" it | Shows users cannot tell which script they run; blinking buttons = LED return writes (probably rjuang's) |

rjuang's git history is a compact list of FL-behaviour lessons that also apply to our tuning work: "OnIdle being absent in several versions of FL and present in others" (2021-12-19); "In 20.8.4,
AnalogLab starts triggering new refresh controls which breaks the analog lab display" (2021-10-02); "Fix issue with midi events for sliders/knobs being suppressed. This enables midi learn for FL
plugins" (2021-12-30); "Enable passing release note for pad release to avoid weird sustain issues" (2022-04-22); "Fix potential crash that can be caused by multiple tasks being scheduled at the same time"
(2022-04-25). Nobody has maintained a KeyLab mkII script for FL 2024-2026 in public that I could find, apart from the untested AI fork.

## 5. Arturia's own restructure: mkII (2021) vs mk3 (2024)

Both sets are by the same author (Farès MEZDOUR) and share the dispatcher class (both copy Ray Juang's MIT dispatcher: KeyLabmk2Dispatch.py:1-2, KL3Dispatch.py:3-4) and the sysex header
`F0 00 20 6B 7F 42` (KeyLabmk2Dispatch.py:66, KL3Dispatch.py:65).

| Aspect | mkII stock (2021) | mk3 (2024) | Consequence for us |
|---|---|---|---|
| Auto-link header | none | `# supportedHardwareIds=00 20 6B 02 00 0A 02 7F 7F 7F 7F,...` (device_KL3.py:2) | mk3 auto-detects; mkII needs manual assignment. We can add `# supportedDevices=` (FL manual); hardware ids for mkII are UNVERIFIED |
| Connection handshake | none; DAW mode is entered on the keyboard | explicit: `Connexion.DAWConnexion()` sends `[0x00, eDaw(2), eConnection(5), 0x01]` in `OnInit`, `DAWDisconnection()` in `OnDeInit` (device_KL3.py:87, 124; KL3Connexion.py:25-31; IntegrationPatchId.py, ParamId.py auto-generated) | mkII protocol has no such message (UNVERIFIED); not a missing feature |
| Ports | DAW port + "Forward CCs Port 10 KEYLAB MKII" on the main port; forward script imports the main script (`import device_KeyLabmkII as KL`, Forward:19) and calls `KL.init()` in its own `OnInit` (Forward:26-27) | DAW script `device_KL3.py` + "KeyLab mk3 MIDI" script (`device_KeyLab mk3 MIDI.py`) that only forwards CCs to port 10, no VCOL check, no processor coupling (lines 26-35). Guide p.2: DAW port needs matching input/output; MIDI port "input only" | mkII's Forward script is heavier and couples both scripts' state; mk3 decoupled them |
| `OnMidiMsg` | `_processor.ProcessEvent(event)` (device_KeyLabmkII.py:84-85) | same, then `if processed: event.handled = False` (device_KL3.py:75-77) | mk3 explicitly un-handles processed events so FL's own linking still sees them |
| `OnRefresh` | always `Sync()` + 3 LED returns (device_KeyLabmkII.py:131-135) | skips when `flags in [4, 4096]` (Mixer_Controls, ControlValues), else 10 return calls (device_KL3.py:137-153); midi.py:79,87 | mk3 avoids re-sending LED/LCD state on every fader value change |
| `OnIdle` | 10 calls each tick: paged-display refresh, time, metronome, loop, LED blink, solo/mute x4, selected channel (device_KeyLabmkII.py:141-151) | 2 calls: `IdleSequencer`, `IdleTimeline` (device_KL3.py:157-160) | mkII is the chattier design; matches the prior assistant's throttling advice |
| `OnSysEx` | handler for one exact sysex `F0 00 20 6B 7F 42 02 00 00 15 00 F7` ("memory switch") -> `ui.setFocused(1)` and refresh (device_KeyLabmkII.py:157-160) | none | mk3 has no memory-switch listener |
| Minimum FL | not stated (guide 2021) | Arturia FAQ: FL 24.1.1 has it built in; manual install min FL 20.9.2 (https://support.arturia.com/hc/en-us/articles/15637916754204-KeyLab-mk3-DAW-Integration) | mk3 script is tested with 2024-era FL |
| Mixer calls | `mixer.setTrackVolume(idx, 0.8*value)` (ArturiaCrossKeyboardKLmk2.py:16-32) | `mixer.setTrackVolume(idx, value, 0)` with pickup argument (ArturiaCrossKeyboardKL3.py) | mk3 adopts FL's newer 3-argument form |
| Error handling | none | none (no try/except in either set; MEASURED) | neither set is defensive |
| Naming | `# name= KeyLab mkII` (leading space) | `# name=KeyLab mk3` | cosmetic |

Take-away: the mk3 script is the best template for what Arturia considers current practice for FL (handshake, decoupled forward script, refresh filtering, hardware-id auto-link), but
its handshake is mk3-specific and must not be copied to the mkII without evidence.

## 6. Claim verdicts (C1-C6)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| C1 | DAW port must be assigned controller type "KeyLab mkII", enabled, with a port number such as 10 | partially-correct | Assignment, enable, and matching in/out port numbers are documented (guide p.4-5; FL manual). But the guide's DAW port is **0** (main port **1**); 10 is the plugin-routing port (guide p.6; forwardMIDICC docs) and FL says not to reuse a port number across devices. Any unique 0-255 number is allowed by FL; 10 is inadvisable (collision inference is Low confidence) |
| C2 | On Windows the DAW input port is "MIDIIN2 (KeyLab mkII 88)" (macOS "KeyLab mkII 88 DAW") | correct | Guide p.4 Fig.2 shows `MIDIIN2 (KeyLab mkII 88)` and `MIDIOUT2 (KeyLab mkII 88)`; p.5 macOS screenshot shows `KeyLab mkII 88 DAW`; Arturia FAQ "The ports are called MIDIIN2 and MIDIOUT2 on Windows". Caveat: names are WinMM-derived and can change under Windows MIDI Services naming options (R6) |
| C3 | Main keyboard port should be left as "Generic controller" (not assigned the Forward CCs script) | incorrect | Arturia's guide assigns the main port to "Forward CCs Port..AB mkII V2 (user)", port 1, input and output (p.4 Fig.2 and p.5). rjuang and IcedRooibos describe different, optional secondary scripts. Arturia's MCU FAQ does use Generic on port 1, but that is the MCU recipe, not the script recipe. Generic is a valid minimal fallback (UNVERIFIED for feature loss), not the documented setup |
| C4 | Matching DAW OUTPUT port (MIDIOUT2/DAW) must have the same port number, else LCD and LEDs stay dark | correct (requirement); symptom inferred | Guide p.5 "input port and the output port of the same instance match"; Fig.2 shows MIDIOUT2 with port 0; FL manual: `midiOutSysex` targets the "(linked) output interface", `isAssigned`; mk3 FAQ same rule. No source states the "dark LCD/LEDs" symptom verbatim; it follows from the code path (all display/LED writes use `midiOutSysex`) |
| C5 | Keyboard must be in a DAW mode / "FL Studio" option (firmware / MCC / front panel) | partially-correct | DAW mode is required (guide p.7; rjuang README IMPORTANT). But there is no "FL Studio" preset: manual v2.2.0 printed p.34 lists nine presets (MCU, HUI, Ableton Live, Logic, Pro Tools, Cubase, Studio One, Reaper, MMC); guide p.4 says to long-press DAW and pick the "Live" program and promises a future FL memory slot; Arturia FAQ says MCC DAW Map "Default MCU" for the MCU route. Whether firmware 1.3.1 added an FL slot: UNVERIFIED |
| C6 | Script file name must start with `device_` and live in `Documents/Image-Line/FL Studio/Settings/Hardware/<folder>/` next to all helper files | correct | FL manual: path `...\Hardware\devicename\device_devicename.py`, "prefix is mandatory", `#name=` "required", folder name arbitrary; rjuang README: subfolder required. "Next to helper files": FL's manual only documents Shared\Python\Lib for custom modules, but the stock and mk3 sets both import sibling modules from their own folder, and rjuang's works that way, so it works in practice; separate caution about module-name collisions (R7) |

## 7. Timeline: FL and Windows changes that touch this set

| Date | Event | Source |
|---|---|---|
| 2019-12 | Image-Line: mkII works via DAW -> MCU only | t=213999 |
| 2020-07/08 | FL 20.7.2: "new controller script Forward all Midi CC" (9219); autodetect of Python devices (9023, 20.7.1 RC1) | What's New |
| 2020-12-25 | rjuang: forward script "built-in to FL Studio 20.8" | rjuang commits |
| 2021-11-15/16 | Arturia mkII FL guide and files; firmware 1.3.1.1492 | Arturia downloads |
| 2022-12 | FL 21 on macOS: `_heapq` missing for rjuang | rjuang #4 |
| 2024-02-28 to 2024-06 | FL 2024.1: Python 3.12; kwargs; renamed parameters; exception-type fix | What's New 16611, 15040, 17108, 17588 |
| 2024-06 | 2024.1 RC: crash disconnecting KeyLab 66 Essential | What's New 17881 |
| 2025-04 to 2025-07 | FL 2025.1: dynamic-mixer API; invalid-track crash fixed; `OnInitAll`; trackCount | What's New 19548, 19997, 19777, 19862 |
| 2026-01-29 | Windows MIDI Services stack starts rolling out (KB5074105 preview, 2026-01); announced 2026-02-17; phased enablement | inMusic KB, Windows blog |
| 2026-03-24 | FL 26.1 beta 1: built-in MCU replaced by script | What's New 20506 |
| 2026-03-25 | Image-Line mod sticky about Windows MIDI Services | t=339802 |
| 2026-04-30 | Microsoft fixes (dynamic ports, timestamps, duplicate names) rolling out | MS dev blog |
| 2026-06-10 | Arturia MCC 1.23.0.134 | Arturia downloads |
| 2026-07-02 | FL 2026 (26.1) released | What's New |
| 2026-07-24 / 08-06 / 08-18 / 09-02 | 26.1.3 / .4 / .5 / .6 fixes listed in R5 | What's New |
| 2026-09-22 to 09-24 | Arturia updates its Windows 11 MIDI service articles | Arturia FAQ |
| 2026-11 (announced) | Windows "11D" MIDI naming rework | MS issue 1202, FL t=342586 |

## 8. What to do next (code versus setup), prior-art driven

Setup checklist for tom, in the order that eliminates the most causes per minute:
1. FL build: Help > About; update to 26.1.6 or newer (R5). Then MIDI Settings > Update MIDI Scripts (R7, R10).
2. Close MIDI Control Center, Analog Lab standalone, other DAWs (R4). Confirm `midisrv` is Automatic; if ports vanish run Arturia's `midifixreg` (R3).
3. Keyboard: DAW button, long-press, pick the "Ableton Live" program (guide p.4) - or set MCC DAW Map to Standard MCU only for the MCU recipe (R2).
4. MIDI Settings, Windows, exactly Arturia's Fig.2: `MIDIIN2` -> KeyLab mkII (or our tuned name), enabled, port 0; `MIDIOUT2` -> same port 0 (assigned); `KeyLab mkII 88` in/out -> Forward CCs script, port 1 (R1). Do not use 10.
5. Plugins: Arturia plugins' MIDI input = 10 (R9).
6. Check the Windows user-data path is not under OneDrive (R7).

Code items we can do without the host (each maps to a cause above):
- Diagnostic probe script (`device_KeyLabProbe.py`, its own folder, `# name=KeyLab Probe`): in `OnInit` print `ui.getVersion()` (FL manual documents `getVersion (int mode = 4)`), `sys.version`, `device.getName()`, `device.getPortNumber()`, `device.isAssigned()`; log the first N raw events (status, data1, data2, port, sysex); try one harmless LCD sysex; `ui.setHintMsg` with the result. Answers R1-R5 in one session.
- Tuned main script: `OnInit` port/assignment warning (R1); sysex dedupe and throttle plus `OnRefresh` flag filter `[4, 4096]` as in mk3 (R5); `mixer.trackCount()` guard and `except RuntimeError` around API calls (R8); unique module names and unique `# name=` (R7); optional `# supportedDevices=` header (R6, R11).
- Linux-side simulation: replay recorded event traces against FL API stubs and assert on `device.midiOutSysex` byte streams and call counts per idle tick.
- Do not copy the mk3 DAW handshake (section 5) into the mkII script without a captured mkII trace.

## 9. Corrections to the previous assistant's claims (THREAD.md)

- "import ArturiaCrossKeyboardKLmk2 is the main suspect": that module exists in the stock folder; the failure mode only applies to an incomplete copy. Ruled out for the stock set (R12).
- "About every 20 ms" for `OnIdle`: FL doc says only "Called from time to time" (UNVERIFIED rate).
- "crashes when no channel is selected": FL doc for `channels.selectedChannel(canBeNone=0)`: "When there is no selection, function will return 0 (or -1 if canBeNone is 1)". The stock call uses the default, so it returns 0, not -1 (device_KeyLabmkII.py:63). A crash would need zero channels (UNVERIFIED).
- "You should see `init OK (processor=yes)`": that string is the previous assistant's own print; FL itself prints `init ok` in the Script tab on successful compile (FL manual).
- Port 10 and "Generic controller" advice: see C1 and C3.

## 10. Open questions

1. Exact FL build on tom (26.1 to 26.1.3 would be exposed to R5 crashes).
2. Whether Windows MIDI Services is active on tom, and whether `MIDIIN2 (KeyLab mkII 88)` and `MIDIOUT2 (KeyLab mkII 88)` both enumerate in FL.
3. Whether Documents on tom is OneDrive-redirected.
4. Which DAW program is active on the keyboard, and whether firmware is 1.3.1.1492.
5. What the Image-Line official-script thread (t=262947) says about Windows; login-gated for me.
6. Whether KeyLab mkII USB descriptors carry iJack strings (port renaming risk after the November 2026 Windows update).

## 11. Source index

Arturia: https://support.arturia.com/hc/en-us/articles/4405748362002-KeyLab-MkII-Tips-Tricks ,
https://support.arturia.com/hc/en-us/articles/4405741178770-KeyLab-MkII-General-Questions ,
https://support.arturia.com/hc/en-us/articles/4407871884818-Compatibility-with-Windows-11 ,
https://support.arturia.com/hc/en-us/articles/6878166158108-Troubleshoot-USB-detection-Communication-issues ,
https://support.arturia.com/hc/en-us/articles/19499946683932-Common-MIDI-issues-Troubleshoot ,
https://support.arturia.com/hc/en-us/articles/15637916754204-KeyLab-mk3-DAW-Integration ,
https://support.arturia.com/hc/en-us/articles/18547778386588-MIDI-Controllers-DAW-Integration ,
https://www.arturia.com/support/downloads-manuals/product/keylab-88-mkII ,
https://dl.arturia.net/products/keylab-49-mkII/manual/keylab-mkii_Manual_2_2_0_EN.pdf ,
https://forum.arturia.com/t/midi-script-for-keylab-mk2-and-fl-studio/2782 .

Image-Line: https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm ,
https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_midi.htm ,
https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/WhatsNew.htm ,
https://forum.image-line.com/viewtopic.php?t=342331 (2026.1.6 notes),
https://forum.image-line.com/viewtopic.php?t=339802 ,
https://forum.image-line.com/viewtopic.php?p=2068443 ,
https://forum.image-line.com/viewtopic.php?t=342586 ,
https://forum.image-line.com/viewtopic.php?t=333361 ,
https://forum.image-line.com/viewtopic.php?t=337036 ,
https://forum.image-line.com/viewtopic.php?t=213999 ,
https://support.image-line.com/action/knowledgebase?ans=732 .

Community: https://github.com/rjuang/flstudio-arturia-keylab-mk2 (+ /issues/1, /issues/4, /issues/5),
https://github.com/IcedRooibos/flstudio-arturia-keylab-49-essential ,
https://github.com/mchelmb/flstudio-arturia-keylab-essential ,
https://github.com/yanncharlou/ArturiaEssentialForFLStudio .

Windows/Microsoft/third party: https://blogs.windows.com/windowsexperience/2026/02/17/making-music-with-midi-just-got-a-real-boost-in-windows-11/ ,
https://devblogs.microsoft.com/windows-music-dev/windows-midi-services-rollout-known-issues-and-workarounds/ ,
https://devblogs.microsoft.com/windows-music-dev/troubleshooting-recent-midi-issues-in-windows-11/ ,
https://microsoft.github.io/MIDI/ , https://microsoft.github.io/MIDI/kb/midi1-name-mapping/ ,
https://microsoft.github.io/MIDI/tools/settings/ , https://github.com/microsoft/MIDI/issues/1202 ,
https://learn.microsoft.com/en-us/answers/questions/5732319/after-windows-26220-7653-update-midi-ports-disappe ,
https://support.inmusicstore.com/en/support/solutions/articles/69000876838-midi-devices-not-working-after-windows-update ,
https://sideshowfx.kb.help/windows-midi-interim-solution-loopmidi-failure/ (low-grade: general list of affected DAWs incl. FL Studio).

Local files cited: `/home/delorenj/Documents/Image-Line/FL Studio/Settings/Hardware/Arturia KeyLab MKII/` (device_KeyLabmkII.py, device_Forward CCs Port 10 KEYLAB MKII.py,
KeyLabmk2Dispatch.py, KeyLabmk2Process.py, ArturiaCrossKeyboardKLmk2.py, guide PDF), `.../Arturia KeyLab mk3/` (device_KL3.py, device_KeyLab mk3 MIDI.py, KL3Connexion.py,
KL3Dispatch.py, ArturiaCrossKeyboardKL3.py, IntegrationPatchId.py, ParamId.py, mk3 guide PDF), `/home/delorenj/.wine/drive_c/Program Files/Image-Line/FL Studio 2025/Shared/Python/`
(python.exe 3.12.1, Lib/midi.py).
