"""ui: focus/visibility of FL windows plus the navigation calls the scripts use."""
from __future__ import annotations

from ..state import PLUGIN_WINDOWS, WID_CHANNEL_RACK, WID_MIXER, WID_PLUGIN
from .base import Impl


class UiImpl(Impl):
    def getFocused(self, index):
        f = self.s.focused
        return f == index or (index == WID_PLUGIN and f in PLUGIN_WINDOWS)

    def getVisible(self, index):
        s = self.s
        return index in s.visible or (index == WID_PLUGIN and bool(s.open_editors))

    def showWindow(self, index):
        self.s.visible.add(index)

    def hideWindow(self, index):
        s = self.s
        s.visible.discard(index)
        if s.focused == index:
            s.focused = WID_CHANNEL_RACK

    def setFocused(self, index):
        s = self.s
        s.visible.add(index)
        s.focused = index

    def getFocusedPluginName(self):
        s = self.s
        return s.focused_plugin_name if s.focused in PLUGIN_WINDOWS else ""

    def getFocusedNodeFileType(self):
        return self.s.node_file_type

    def getFocusedNodeCaption(self):
        return self.s.node_caption

    def isInPopupMenu(self):
        return self.s.in_popup_menu

    def selectBrowserMenuItem(self):
        pass

    def _step(self, delta):
        s = self.s
        if s.focused == WID_CHANNEL_RACK and s.channel_count():
            s.selected_channel = max(0, min(s.channel_count() - 1, s.selected_channel + delta))
        elif s.focused == WID_MIXER:
            s.current_track = max(0, min(s.track_count - 1, s.current_track + delta))

    def next(self):
        self._step(1)
        return 0

    def previous(self):
        self._step(-1)
        return 0

    def up(self, value=1):
        return 0

    def down(self, value=1):
        return 0

    def cut(self):
        return 0

    def snapMode(self, value):
        s = self.s
        s.snap_mode = (s.snap_mode + value) % 10
        return s.snap_mode

    def getSnapMode(self):
        return self.s.snap_mode

    def setSnapMode(self, value):
        self.s.snap_mode = value

    def crDisplayRect(self, left, top, right, bottom, duration, flags=0):
        pass

    def getProgTitle(self):
        return self.s.prog_title

    def getHintMsg(self):
        return self.s.hint_msg

    def setHintMsg(self, msg):
        self.s.hint_msg = msg

    def isLoopRecEnabled(self):
        return self.s.loop_rec

    def isMetronomeEnabled(self):
        return self.s.metronome

    def isPrecountEnabled(self):
        return self.s.precount

    def getVersion(self, mode=0):
        return "26.1.6" if mode == 0 else 26
