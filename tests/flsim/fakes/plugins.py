"""plugins: parameters of the plugin on a channel (slotIndex -1 = the channel's generator)."""
from __future__ import annotations

from .base import Impl


class PluginsImpl(Impl):
    def _ok(self, index, fn):
        n = self.s.channel_count()
        if 0 <= index < n:
            return True
        self.host.violation("index", "plugins.%s" % fn, "channel/plugin index %d outside 0..%d" % (index, n - 1))
        return False

    def _param_ok(self, p, fn):
        n = self.s.param_count
        if 0 <= p < n:
            return True
        self.host.violation("param-index", "plugins.%s" % fn, "parameter index %d outside 0..%d" % (p, n - 1))
        return False

    def isValid(self, index, slotIndex=-1, useGlobalIndex=False):
        return 0 <= index < self.s.channel_count()

    def getPluginName(self, index, slotIndex=-1, userName=False, useGlobalIndex=False):
        if not self._ok(index, "getPluginName"):
            return ""
        s = self.s
        if slotIndex != -1:
            return ""
        if userName:
            return s.channel_names[index]
        return s.channel_plugins[index] if index < len(s.channel_plugins) else ""

    def getParamCount(self, index, slotIndex=-1, useGlobalIndex=False):
        return self.s.param_count if self._ok(index, "getParamCount") else 0

    def getParamValue(self, paramIndex, index, slotIndex=-1, useGlobalIndex=False):
        if not (self._ok(index, "getParamValue") and self._param_ok(paramIndex, "getParamValue")):
            return 0.0
        return self.s.param_values.get((index, paramIndex), 0.5)

    def setParamValue(self, value, paramIndex, index, slotIndex=-1, pickupMode=0, useGlobalIndex=False):
        if not (self._ok(index, "setParamValue") and self._param_ok(paramIndex, "setParamValue")):
            return
        if not 0.0 <= value <= 1.0:
            self.host.violation("value", "plugins.setParamValue", "value %r outside 0..1" % (value,))
            value = min(1.0, max(0.0, value))
        self.s.param_values[(index, paramIndex)] = value

    def getParamName(self, paramIndex, index, slotIndex=-1, useGlobalIndex=False):
        if not (self._ok(index, "getParamName") and self._param_ok(paramIndex, "getParamName")):
            return ""
        return self.s.param_names.get((index, paramIndex), "Param %d" % paramIndex)

    def nextPreset(self, index, slotIndex=-1, useGlobalIndex=False):
        self._ok(index, "nextPreset")

    def prevPreset(self, index, slotIndex=-1, useGlobalIndex=False):
        self._ok(index, "prevPreset")
