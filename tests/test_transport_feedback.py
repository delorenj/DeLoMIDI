"""Transport feedback must follow FL after a command, including delayed host updates.

Measured on tom's FL 26.1.6: globalTransport(FPT_LoopRecord, 1) returns before
isLoopRecEnabled changes. An immediate snapshot then shows the previous state
for the whole temporary page. The simulator's normal transport fake is
synchronous, so these tests explicitly defer the host update past the callback.
"""
from __future__ import annotations

import pytest

from tests import kl


CONTROLS = [
    pytest.param(kl.BTN_RECORD, "recording", "Record", id="record"),
    pytest.param(kl.BTN_LOOP, "loop_rec", "Loop Mode", id="loop"),
]


@pytest.mark.tuned_fix("H-TRANSPORT-STATE")
@pytest.mark.parametrize("button,field,label", CONTROLS)
@pytest.mark.parametrize("initial", [False, True], ids=["turn-on", "turn-off"])
def test_lcd_follows_the_host_when_a_toggle_completes_after_the_callback(
    rig, monkeypatch, button, field, label, initial
):
    setattr(rig.state, field, initial)
    rig.settle()
    requests = []
    transport = rig.host.modules["transport"]

    def defer_record():
        requests.append("record")

    original_global = transport.globalTransport

    def defer_global(command, value, pmeflags=2, flags=15):
        if command == rig.host.modules["midi"].FPT_LoopRecord:
            requests.append("loop")
            return 0
        return original_global(command, value, pmeflags, flags)

    monkeypatch.setattr(transport, "record", defer_record)
    monkeypatch.setattr(transport, "globalTransport", defer_global)
    rig.tap(button)
    assert len(requests) == 1, "one press requests one toggle; release never toggles"
    assert getattr(rig.state, field) is initial
    rig.idle(0.04)  # FL has not applied the request yet; do not predict the result.
    assert rig.host.device_model().lcd == (label, "ON" if initial else "OFF")

    setattr(rig.state, field, not initial)  # Host applies the queued command.
    rig.idle(0.1)  # No OnRefresh needed to correct the LCD.
    assert rig.host.device_model().lcd == (label, "OFF" if initial else "ON")
    assert not rig.host.errors
    assert len(requests) == 1
    rig.idle(1.1)
    assert rig.host.device_model().lcd == ("1 - Kick", "Pattern 1")


@pytest.mark.tuned_fix("H-TRANSPORT-STATE")
@pytest.mark.parametrize("button,field,label", CONTROLS)
def test_a_visible_status_page_follows_external_fl_state_changes(rig, button, field, label):
    rig.settle()
    rig.tap(button)
    rig.idle(0.1)
    assert getattr(rig.state, field)
    assert rig.host.device_model().lcd == (label, "ON")

    setattr(rig.state, field, False)  # A mouse click or another controller changes FL.
    rig.idle(0.1)
    assert rig.host.device_model().lcd == (label, "OFF")
    assert not rig.host.errors
