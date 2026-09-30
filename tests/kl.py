"""Facts about the KeyLab mkII protocol shared by the tests (docs/analysis/02 section 4 and 03 section 2).

These are what the stock script assumes; the hardware contract itself is UNVERIFIED (docs/analysis/02, F-03)."""

# ---- buttons: note-on channel 1, velocity 127 = press, velocity 0 = release ------------------------------------
BTN_SNAP = range(0, 8)          # "Record" -> change snap mode (fires on press)
BTN_SOLO = range(8, 16)         # fires on release
BTN_MUTE = range(16, 24)        # fires on release
BTN_SELECT = range(24, 32)      # 8 RGB Select buttons, fire on release
BTN_PREV, BTN_NEXT = 46, 47     # bank -8 / +8
BTN_MIXER_TOGGLE = 51           # Channel Rack <-> Mixer mode
BTN_TAP_TEMPO = 56
BTN_CUT = 57                    # fires on release
BTN_SEQ_TOGGLE = 74             # "Save": drum <-> step-sequencer mode
BTN_UNDO = 81                   # fires on release
BTN_JOG_PUSH = 84
BTN_LOOP = 86
BTN_BROWSER = 87                # "In"
BTN_OVERDUB = 88                # "Out", fires on release
BTN_METRO = 89                  # fires on release
BTN_REWIND, BTN_FORWARD = 91, 92
BTN_STOP, BTN_PLAY, BTN_RECORD = 93, 94, 95
BTN_PATTERN_PREV, BTN_PATTERN_NEXT = 98, 99

# ---- windows (midi.wid*) ---------------------------------------------------------------------------------------------
WID_MIXER, WID_CHANNEL_RACK, WID_PLAYLIST, WID_PIANO_ROLL, WID_BROWSER, WID_PLUGIN = 0, 1, 2, 3, 4, 5

# ---- pads --------------------------------------------------------------------------------------------------------------
PAD_NOTES = list(range(36, 52))
# pad note -> FPC note (docs/analysis/02 4.5, guide p.14 Fig.27)
FPC_MAP = dict(zip(PAD_NOTES, [49, 55, 51, 53, 48, 47, 45, 43, 40, 38, 46, 44, 37, 36, 42, 54]))
PAD_LEDS = list(range(0x70, 0x80))
SELECT_LEDS = list(range(0x22, 0x2A))
LED_MULTI = 0x2A

# ---- mono LED ids -------------------------------------------------------------------------------------------------------
LED_SOLO, LED_MUTE = 0x60, 0x61
LED_METRO, LED_STOP, LED_PLAY, LED_RECORD, LED_LOOP = 0x68, 0x6C, 0x6D, 0x6E, 0x6F
LED_ON, LED_OFF = 0x7F, 0x09
# backlights the stock script keeps at 7F (Save 0x65 is left out: O-17 may make it follow the sequencer mode)
LED_STEADY = [0x1A, 0x1B, 0x62, 0x63, 0x64, 0x66, 0x67, 0x69, 0x6A, 0x6B]

# ---- RGB colours (R, G, B) -------------------------------------------------------------------------------------------
RED, YELLOW, PURPLE, BLUE, WHITE, MAGENTA, OFF = (0x7F, 0, 0), (0x7F, 0x7F, 0), (0x7F, 0, 0x7F), (0, 0, 0x7F), (0x7F,) * 3, (0x7F, 0, 0x7F), (0, 0, 0)

# ---- plugin names of the stock parameter database ------------------------------------------------------------------
DB_PLUGINS = ["FLEX", "FPC", "FL Keys", "Sytrus", "GMS", "Harmless", "Harmor", "Morphine", "3x Osc", "Fruity DX10",
              "BASSDRUM", "Fruit kick", "MiniSynth", "PoiZone", "Sakura"]

V_COL_SAMPLE = ["Analog Lab V", "Mini V3", "Piano V2", "Wurli V2"]

SYSEX_MEMORY_SWITCH = b"\xf0\x00 k\x7fB\x02\x00\x00\x15\x00\xf7"     # entry OnSysEx: focus Channel Rack + full refresh


def forward_cc_message(status, d1, d2):
    """What Forward.OnMidiIn passes to device.forwardMIDICC for the Analog Lab plugin (port 10)."""
    return status + (d1 << 8) + (d2 << 16) + (10 << 24)
