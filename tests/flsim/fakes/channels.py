"""channels: the Channel Rack (names, selection, step sequencer grid and step parameters, graph editor)."""
from __future__ import annotations

from ..state import PLUGIN_WINDOWS, STEP_PARAM_RANGES, WID_CHANNEL_RACK
from .base import Impl


class ChannelsImpl(Impl):
    # Index model: the rack is a flat list (no groups), so group-relative and global indices coincide. F-13/O-13
    # (wrong channel with Channel Rack groups) is therefore NOT reproducible here.
    def _ok(self, index, fn):
        n = self.s.channel_count()
        if 0 <= index < n:
            return True
        self.host.violation("index", "channels.%s" % fn, "channel index %d outside 0..%d" % (index, n - 1))
        return False

    def channelCount(self, globalCount=False):
        return self.s.channel_count()

    def channelNumber(self, canBeNone=False, offset=0):
        n = self.s.channel_count()
        if n == 0:
            return -1 if canBeNone else 0
        return self.s.selected_channel

    def selectedChannel(self, canBeNone=False, offset=0, indexGlobal=False):
        return self.channelNumber(canBeNone, offset)

    def getChannelName(self, index, useGlobalIndex=False):
        if not self._ok(index, "getChannelName"):
            return ""
        return self.s.channel_names[index]

    def selectOneChannel(self, index, useGlobalIndex=False):
        if self._ok(index, "selectOneChannel"):
            self.s.selected_channel = index

    def isChannelSelected(self, index, useGlobalIndex=False):
        return self._ok(index, "isChannelSelected") and index == self.s.selected_channel

    def isChannelMuted(self, index, useGlobalIndex=False):
        return self._ok(index, "isChannelMuted") and index in self.s.muted_channels

    def isChannelSolo(self, index, useGlobalIndex=False):
        return self._ok(index, "isChannelSolo") and index in self.s.solo_channels

    def soloChannel(self, index, useGlobalIndex=False):
        if self._ok(index, "soloChannel"):
            self.s.solo_channels ^= {index}

    def muteChannel(self, index, value=-1, useGlobalIndex=False):
        if self._ok(index, "muteChannel"):
            m = self.s.muted_channels
            if value == -1:
                m ^= {index}
            elif value:
                m.add(index)
            else:
                m.discard(index)

    def getTargetFxTrack(self, index, useGlobalIndex=False):
        if not self._ok(index, "getTargetFxTrack"):
            return 0
        return self.s.channel_fx_track.get(index, (index % 125) + 1)

    def showEditor(self, index, value=-1, useGlobalIndex=False):
        if not self._ok(index, "showEditor"):
            return
        s = self.s
        opening = (index not in s.open_editors) if value == -1 else bool(value)
        if opening:
            s.open_editors.add(index)
            s.focused = PLUGIN_WINDOWS[0]
            s.visible.add(s.focused)
            s.focused_plugin_name = s.channel_plugins[index] if index < len(s.channel_plugins) else ""
        else:
            s.open_editors.discard(index)
            if not s.open_editors and s.focused in PLUGIN_WINDOWS:
                s.focused = WID_CHANNEL_RACK

    def getGridBit(self, index, position, useGlobalIndex=False):
        if not self._ok(index, "getGridBit"):
            return False
        if position < 0:
            self.host.violation("index", "channels.getGridBit", "step position %d < 0" % position)
            return False
        return bool(self.s.grid.get((index, position), 0))

    def setGridBit(self, index, position, value, useGlobalIndex=False):
        if not self._ok(index, "setGridBit"):
            return
        if position < 0:
            self.host.violation("index", "channels.setGridBit", "step position %d < 0" % position)
            return
        self.s.grid[(index, position)] = 1 if value else 0

    def getCurrentStepParam(self, index, step, param, useGlobalIndex=False):
        if not self._ok(index, "getCurrentStepParam"):
            return 0
        s = self.s
        if s.step_param_forced is not None:
            return s.step_param_forced
        return s.step_param(index, s.pattern, step, param)

    def setStepParameterByIndex(self, index, patNum, step, param, value, useGlobalIndex=False):
        if not self._ok(index, "setStepParameterByIndex"):
            return
        rng = STEP_PARAM_RANGES.get(param)
        if rng is not None and not rng[0] <= value <= rng[1]:
            self.host.violation("value", "channels.setStepParameterByIndex",
                                "step param %d value %d outside documented range %d..%d" % (param, value, *rng))
        self.s.step_params[(index, patNum, step, param)] = value

    def showGraphEditor(self, temporary, param, step, index, useGlobalIndex=False):
        if self._ok(index, "showGraphEditor"):
            self.s.graph_editor_visible = True

    def isGraphEditorVisible(self):
        return self.s.graph_editor_visible

    def closeGraphEditor(self, index):
        self.s.graph_editor_visible = False

    def updateGraphEditor(self):
        pass

    def setChannelPitch(self, index, value, mode=0, pickupMode=0, useGlobalIndex=False):
        if self._ok(index, "setChannelPitch"):
            self.s.channel_pitch[index] = value
