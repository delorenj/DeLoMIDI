"""
Tunable switches for the tuned KeyLab mkII scripts.

Defaults keep Arturia's stock behaviour except where the stock behaviour is a demonstrated bug or a crash
risk (see docs/analysis and docs/tuned). Add a switch only with a comment saying what it changes and which
finding (docs/analysis F-/O-/G- id) it belongs to. Sections are owned by the side that uses them.
"""

# ---- shared: diagnostics (KLTLog) -------------------------------------------------------------------------
LOG_ENABLED = True                              # write klt.log; never raises, never blocks FL
LOG_PATH = r'C:\ProgramData\DeLoMIDI\klt.log'   # the folder must exist and be writable by the FL user
LOG_MAX_BYTES = 512 * 1024                      # log is truncated (keeps the tail) beyond this size
LOG_MAX_LINES_PER_SEC = 50                      # flood guard; dropped lines are counted and reported
LOG_RAW_EVENTS = False                          # log every raw MIDI event (chatty; for protocol capture)

# ---- output side: LEDs / LCD / lifecycle (owned by the output-side implementer) ---------------------------
# --- output side --- (docs/tuned/CHANGES-output.md lists every switch with its finding id and test)

# Safety gate (O-01): nothing is ever sent to the keyboard unless FL says the script has a MIDI output.
OUT_ENABLED = True                  # master kill switch: False = the scripts never call device.midiOutSysex
OUT_REQUIRE_MIDIOUT_ASSIGNED = True # also require device.isMidiOutAssigned() (undocumented) after isAssigned() is True;
                                    # False = trust isAssigned() alone. Either way an unanswerable query = not assigned
OUT_UNASSIGNED_RECHECK_S = 0.5      # while unassigned, ask FL again at most this often (assigned is asked before every send)
OUT_FAIL_BACKOFF_S = 5.0            # midiOutSysex raised 5 times in a row: stop sending for this long

# Rate limits (O-02, O-06): the stock OnIdle sent ~1,200 SysEx/s; the community project warns a flooded keyboard can wedge.
OUT_MAX_SYSEX_PER_SEC = 100         # HARD cap over any sliding second, for everything incl. init and keep-alives
OUT_MAX_SYSEX_PER_TICK = 8          # at most this many frames inside one OUT_TICK_S window (one OnIdle period)
OUT_TICK_S = 0.02                   # FL documents OnIdle as "roughly once every 20 ms"
OUT_LCD_MIN_GAP_S = 0.035           # minimum spacing of LCD frames (community-tested; unchanged text is never re-sent)
OUT_LED_PASS_S = 0.1                # how often OnIdle re-evaluates the polled LEDs (stock: every tick)
OUT_TRICKLE_S = 1.0                 # keep-alive: re-send ONE known LED frame this often when idle (0 = off); heals a
                                    # keyboard that lost its LEDs (power cycle, memory switch) without FL telling us
OUT_LCD_KEEPALIVE_S = 10.0          # keep-alive for the LCD frame (0 = off)
OUT_HOLD_TIMEOUT_S = 5.0            # LEDs are held back while the init sequence runs; released after this long even
                                    # if OnIdle never advanced it
OUT_STATS_LOG_S = 60.0              # one klt.log line with the output counters this often when anything was sent (0 = off)

# Init sequence (O-12): a small state machine advanced from OnIdle; OnInit itself never sleeps or sends a burst.
INIT_ANIMATION = 0                  # 0 = none (LEDs just paint), 1 = short pad chase (32 frames), 2 = stock (240 frames)
INIT_FRAMES_PER_TICK = 4            # frames of the animation advanced per OnIdle tick
SPLASH_MS = 1500                    # welcome page "KeyLab mkII" / <FL window title> (stock: 1500; 0 = no splash)
SPLASH_TAG_MS = 1000                # second splash "KeyLab mkII" / "tuned <version>" so you can tell which script is
                                    # running (0 = skip)

# LCD (O-03, O-18)
LCD_SCROLL_MS = 500                 # scroll step for text longer than 16 characters (stock: 1500 = 20 s per name)

# OnRefresh / project events (O-07, O-08)
REFRESH_IGNORE_NOISY_FLAGS = False  # True = an OnRefresh whose flags are only HW_Dirty_Mixer_Controls / HW_Dirty_ControlValues
                                    # does nothing (they fire while faders/knobs move). Default False: what FL signals with
                                    # them is unverified (Mackie updates mixer LEDs on HW_Dirty_Mixer_Controls), and with the
                                    # shadow state a repeated refresh costs no SysEx anyway
RESET_HELPER_STATE_ON_INIT = True   # OnInit resets bank offsets and modes of the helper modules (stale after Reload)

# LED semantics that are hardware-dependent and unverified: the defaults are stock's
PAD_LED_FLIP_ROWS = False           # O-10: True = map pad i to the vertically flipped LED id (community: 49/88 models)
SAVE_LED_FOLLOWS_MODE = False       # O-17: True = Save LED (65) lit only in Sequencer mode (stock: always lit)
GROUP_RELATIVE_CHANNELS = True      # O-13: use channels.selectedChannel() (group-relative, like the calls it feeds);
                                    # False = stock channels.channelNumber() (global index)

# Shutdown (O-16)
SEND_DEINIT_FRAME = True            # stock's "02 7D 7D 0B 00" at OnDeInit (meaning UNVERIFIED); False = LCD goodbye only
CLEAR_LEDS_ON_DEINIT = False        # True = also black out the pads/select LEDs at OnDeInit (stock leaves them lit)

# Diagnostics (O-15). Every native device.* call is announced in klt.log BEFORE it is made ("probe ...", "gate: ..."), and the
# log is appended line by line, so if FL ever dies inside one the last line on disk names it.
LOG_DEVICE_DETAILS = True           # the init banner also asks device.isMidiOutAssigned / getPortNumber / getName (only when the
                                    # script has an output). Set False, with OUT_REQUIRE_MIDIOUT_ASSIGNED = False, to make
                                    # device.isAssigned() the only device query of the whole script (crash bisecting)
LOG_DEVICE_ID = False               # also log device.getDeviceID() in the init banner (API 25+, unverified on FL 26.1.6)

# ---- input side: controls / Forward script (owned by the input-side implementer) --------------------------
# --- input side --- (docs/tuned/CHANGES-input.md lists every switch with its finding id and test)
# The keyboard's DAW preset and its real event shapes are UNVERIFIED until run on hardware (docs/analysis/02, F-03):
# every switch below whose default differs from Arturia's script says so. Read klt.log first (PROBE / UNMAPPED lines).

# Unmapped events (F-03): a note/CC/pitch-bend nobody claims used to be swallowed silently.
PASS_UNMAPPED = True                # True = leave event.handled False so FL processes it normally (safest); False = swallow
                                    # it like Arturia's script did for ch1 notes / CCs / faders. A note-off (0x80) is never swallowed
LOG_UNMAPPED = True                 # log each distinct unmapped (port, status, data1) once (and again at x10/x100/x1000)
LOG_UNMAPPED_MAX_KEYS = 300         # remember at most this many distinct unmapped ids (flood guard)

# Which MIDI fields FL fills in which callback (F-01, hypotheses H1/H2 of docs/analysis/02 3.3): PROBE lines in klt.log
# show, per callback and per port, whether midiId/midiChan are populated. The input side never relies on them: it
# derives everything from status/data1/data2.
PROBE_MIDI_FIELDS = True            # log the first PROBE_SAMPLES_PER_KIND events of each (callback, port, kind)
PROBE_SAMPLES_PER_KIND = 3

# Forward (keyboard-port) script (F-01, F-02, F-15, F-17)
FORWARD_TARGET_PORT = 10            # port number stamped on CC/pitch-bend forwarded to Arturia's plugins (guide p.6, p.16)
FORWARD_MODE = 2                    # device.forwardMIDICC mode: 0 = all plugins, 1 = focused plugin, 2 = selected channels (stock)
FORWARD_PADS = True                 # pads (0x99/0x89) arriving on the keyboard port act as drum/step pads (stock did, via
                                    # the processor); raw status/data1/data2 only, so H1/H2 do not matter
FORWARD_PLUGIN_CCS = True           # mod wheel CC1 -> focused plugin's database param, CC28/CC29 -> previous/next preset
                                    # (stock's Analog-Lab CC path, which crashed; H2-only there) on the keyboard port
FORWARD_USE_PROCESSOR = False       # True = also run the DAW command processor (buttons/jog/encoders) from OnMidiMsg for the
                                    # kinds below. Stock ran it from OnMidiIn for EVERYTHING, so under H1 15 keybed keys acted as
                                    # transport/window buttons. Default False = raw filtering/forwarding only
FORWARD_PROCESSOR_KINDS = ('cc',)   # subset of 'note' (ch1 note on/off = buttons, DANGEROUS on a keybed), 'cc' (ch1 CCs =
                                    # jog/encoders), 'bend' (pitch bend = faders; the wheel is a pitch bend on this port)
ANALOG_LAB_CC_TO_PLUGIN_DB = False  # F-02: translate Analog Lab's 17 knob/fader CCs (74,71,76,77,93,18,19,16 / 73,75,79,72,
                                    # 80,81,82,83,17) into the focused FL plugin's database controls (knob i -> encoder i,
                                    # fader j -> fader j, absolute). Arturia's own attempt never worked. Guess: default off

# Pads (F-05..F-07, F-27)
PADS_REMAP_ONLY_FOR_FPC = True      # F-07: the FPC layout remap only when the selected channel's plugin is FPC; False = stock
                                    # (every instrument's pads scrambled)
PADS_NOTE_ON_ZERO_IS_RELEASE = True # a pad note-on with velocity 0 is a release (running-status note-off)

# Buttons (F-23)
NOTE_OFF_IS_RELEASE = True          # a note-off (0x80) is the same as note-on velocity 0 (release); stock routed only the latter

# Relative encoders and the jog (F-10)
ENCODER_USE_TICKS = True            # decode sign-magnitude relative values (1..63 = CW, 65..127 = CCW, 0/64 = none) by
                                    # magnitude; False = stock (+-1 per event, jog only reacts to exactly 1 / 65)
ENCODER_MAX_TICKS = 4               # cap per event, so an unexpected encoding cannot make a control jump

# Modes and banks (F-09, F-12)
MODE_FOLLOWS_FOCUS = True           # Mixer/Channel-Rack mode of faders/encoders follows the window FL really has focused (a
                                    # mouse click no longer desyncs it); False = only the Bank button changes it
PATTERN_NEXT_CREATES = True         # F-21: Next past the last pattern creates a new one (stock); False = stop at the last pattern
CUT_ENABLED = True                  # F-18: the "Off" button = ui.cut() (documented, destructive, effect UNVERIFIED); False = ignore it
