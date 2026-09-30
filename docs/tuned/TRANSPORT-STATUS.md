# REC/LOOP LCD feedback — 2026-09-30

The temporary REC and LOOP status pages now read FL's current state on every display refresh. Previously each page
saved a single value immediately after requesting a toggle, which could be the previous value. The page still expires
after one second and returns to the selected channel and pattern. Existing LED mappings and output limits are retained.

Claude stopped after the user confirmed a working LCD, DAW Live mode, and inverted REC/LOOP text. Its firmware-research
and code-tracing workers hit the session limit. This continuation recovered that handoff from the actual session log.

## Evidence on tom

The existing FL session remained responsive. Before the fix, the live LOOP probe printed:

```text
LOOP_PROBE before 0 request None after 0 page LoopOff
```

The FL loop-record toolbar button was lit by the time the screenshot arrived. The immediate state query was stale:
`transport.globalTransport(midi.FPT_LoopRecord, 1)` had queued the toggle while `ui.isLoopRecEnabled()` still returned zero.
The script then held the wrong LCD value for the whole temporary page. This is sufficient to explain the LOOP inversion
without attributing it to firmware.

A command-box REC probe returned the new recording state immediately (`before 0`, `after 1`, `RecordOn`). REC latency
was not independently reproduced in a physical MIDI callback. The same live rendering change covers delayed REC updates
and state changes made through FL while either page is visible. Physical REC behavior still needs the user's confirmation.

These probes armed recording while playback stayed stopped and toggled loop recording; both settings were restored.
No project was closed or reopened.

## Change and regression

`scripts/KeyLab mkII tuned/KLTNavigation.py` supplies callable ON/OFF text to the existing `KeyLabPagedDisplay` for REC
and LOOP. Its normal `OnIdle` refresh re-reads `transport.isRecording()` or `ui.isLoopRecEnabled()`. It displays the
reported FL state rather than predicting a successful toggle. Getter failures retain the existing guarded page behavior.

`tests/test_transport_feedback.py` covers deferred toggles in both directions for REC and LOOP, updates from another
controller while the page is visible, a single toggle per press, and expiry back to the main page. All six cases failed
before the change and pass after it; the stock scripts produce six expected strict xfails.

The [FL scripting reference](https://www.image-line.com/fl-studio-learning-content/fl-studio-online-manual/html/midi_scripting.htm)
defines `record()` as a toggle and `isRecording()` as the current state. The delayed LOOP observation above is a measurement
on this installed build, not an assumption about every FL version. The controller's LOOP function remains FL's loop-record
toggle, as in the existing script; song/pattern mode is a separate state.

## Acceptance

Full Python 3.12 suite: **1,108 passed, 1 skipped, 6 existing expected xfails**. The six new transport cases passed;
their separate stock run produced six strict xfails. The hygiene checks and `git diff --check` passed.

Only `KLTNavigation.py` was copied to tom. Local and deployed SHA-256:

```text
62501255875bdce876abd6a0be8abc4779a5da790f0c68ddf0035fea8f9e7c97
```

Reloading Navigation and Process helpers, then the DAW entry script, loaded the new navigation class into the existing
FL session. A temporary, non-blocking idle probe called the real transport handlers and checked the rendered display
about 100 ms later. The probe restored the original idle method and left REC/LOOP off and playback stopped.

```text
LIVE_SOURCE True
LIVE_REQUEST loop-on immediate 0 0
LIVE_CHECK loop-on ok True state/lcd (0, 1, ('Loop Mode', 'ON'))
LIVE_REQUEST loop-off immediate 0 1
LIVE_CHECK loop-off ok True state/lcd (0, 0, ('Loop Mode', 'OFF'))
LIVE_REQUEST rec-on immediate 1 0
LIVE_CHECK rec-on ok True state/lcd (1, 0, ('Record', 'ON'))
LIVE_REQUEST rec-off immediate 0 0
LIVE_CHECK rec-off ok True state/lcd (0, 0, ('Record', 'OFF'))
LIVE_PROBE_DONE True
```

FL's process remained responsive (PID 8196), and output counters continued reporting zero errors after the reload.
These are actual FL state/rendering checks; they do not capture the physical keyboard's screen or substitute for button
input. The remaining physical check is REC twice, then LOOP twice, about three seconds apart while FL is stopped:
LCD ON/OFF should agree with FL's corresponding state, then return to channel/pattern text. Dim backlights are distinct
from active LED brightness. Raw input capture remains enabled in the live process for this check; it is not a saved
configuration change.
