"""Mutable model of the FL Studio state that the fakes read and write.

Only what the KeyLab scripts (stock, tuned, and the fixes the analysis suggests) can observe is modelled. Tests set
fields directly (`host.state.focused = 0`) or use the helpers. This is a plain data object: the fake API modules in
flsim/fakes/ are the only code that interprets it.
"""
from __future__ import annotations

# window ids (== midi.wid* in FL's midi.py)
WID_MIXER, WID_CHANNEL_RACK, WID_PLAYLIST, WID_PIANO_ROLL, WID_BROWSER = 0, 1, 2, 3, 4
WID_PLUGIN, WID_PLUGIN_EFFECT, WID_PLUGIN_GENERATOR = 5, 6, 7
PLUGIN_WINDOWS = (WID_PLUGIN, WID_PLUGIN_EFFECT, WID_PLUGIN_GENERATOR)

# documented defaults of the step parameters (stubs: channels/__sequencer.py setStepParameterByIndex)
STEP_PARAM_DEFAULTS = {0: 60, 1: 100, 2: 64, 3: 120, 4: 64, 5: 64, 6: 64, 7: 0}
STEP_PARAM_RANGES = {0: (0, 131), 1: (0, 127), 2: (0, 127), 3: (0, 240), 4: (0, 127), 5: (0, 127), 6: (0, 127)}

DEFAULT_CHANNELS = ["Kick", "Snare", "Hat", "Clap", "Tom", "Perc", "Bass", "Lead", "Pad", "FX"]


class FLState:
    def __init__(self):
        # --- general
        self.api_version = 45
        self.prog_title = "FL Studio 2026"
        self.undo_hint = ""
        # --- ui
        self.focused = WID_CHANNEL_RACK
        self.visible = {WID_MIXER, WID_CHANNEL_RACK, WID_PLAYLIST, WID_BROWSER}
        self.focused_plugin_name = ""        # what ui.getFocusedPluginName() reports while a plugin window is focused
        self.node_file_type = 0              # ui.getFocusedNodeFileType()
        self.node_caption = "node"
        self.in_popup_menu = False
        self.snap_mode = 1
        self.hint_msg = ""
        self.metronome = False
        self.loop_rec = False
        self.precount = False
        # --- channel rack
        self.channel_names = list(DEFAULT_CHANNELS)
        self.channel_plugins = ["Sampler"] * len(DEFAULT_CHANNELS)
        self.selected_channel = 0
        self.muted_channels: set[int] = set()
        self.solo_channels: set[int] = set()
        self.channel_fx_track: dict[int, int] = {}
        self.open_editors: set[int] = set()
        self.grid: dict[tuple, int] = {}
        self.step_params: dict[tuple, int] = {}
        self.step_param_forced: int | None = None      # e.g. -1 emulates getCurrentStepParam() failing (O-14)
        self.graph_editor_visible = False
        self.channel_pitch: dict[int, float] = {}
        # --- mixer (track 0 = master, 1..125 inserts, 126 = "current" pseudo track: trackCount() == 127)
        self.track_count = 127
        self.current_track = 1
        self.track_volume: dict[int, float] = {}
        self.track_pan: dict[int, float] = {}
        self.muted_tracks: set[int] = set()
        self.solo_tracks: set[int] = set()
        self.armed_tracks: set[int] = set()
        self.tempo = 120.0
        self.song_tick_pos = 0
        self.song_step_pos = 0
        # --- transport
        self.playing = False
        self.recording = False
        self.loop_mode = 0                   # 0 = pattern mode, 1 = song mode
        # --- patterns
        self.pattern = 1
        self.pattern_count = 3
        self.pattern_names: dict[int, str] = {}
        # --- plugins (parameters live per channel index)
        self.param_values: dict[tuple, float] = {}
        self.param_names: dict[tuple, str] = {}
        self.param_count = 4240

    # ---- helpers -----------------------------------------------------------------------------------------------
    def set_channels(self, names, plugins=None, selected=None):
        self.channel_names = list(names)
        self.channel_plugins = list(plugins) if plugins is not None else ["Sampler"] * len(self.channel_names)
        while len(self.channel_plugins) < len(self.channel_names):
            self.channel_plugins.append("Sampler")
        if selected is not None:
            self.selected_channel = selected
        elif self.selected_channel >= len(self.channel_names):
            self.selected_channel = max(0, len(self.channel_names) - 1)

    def resize_channels(self, n):
        names = ["Chan %d" % (i + 1) for i in range(n)]
        for i in range(min(n, len(self.channel_names))):
            names[i] = self.channel_names[i]
        self.set_channels(names)

    def focus(self, window, plugin=None):
        """Focus a window; for a plugin window pass the plugin name ui.getFocusedPluginName() should report."""
        self.focused = window
        self.visible.add(window)
        if window in PLUGIN_WINDOWS:
            self.focused_plugin_name = plugin or ""
            if self.channel_names:
                self.open_editors.add(self.selected_channel)     # a focused plugin window is an open editor
        return self

    def select_channel_plugin(self, plugin, channel=None):
        ch = self.selected_channel if channel is None else channel
        while len(self.channel_plugins) <= ch:
            self.channel_plugins.append("Sampler")
        self.channel_plugins[ch] = plugin
        return self

    def channel_count(self):
        return len(self.channel_names)

    def step_param(self, channel, pattern, step, param):
        return self.step_params.get((channel, pattern, step, param), STEP_PARAM_DEFAULTS.get(param, 0))
