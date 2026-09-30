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
# (add switches here)

# ---- input side: controls / Forward script (owned by the input-side implementer) --------------------------
# (add switches here)
