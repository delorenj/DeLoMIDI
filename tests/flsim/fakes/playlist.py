"""playlist: only the visible-time queries the KeyLab scripts import it for."""
from __future__ import annotations

from .base import Impl


class PlaylistImpl(Impl):
    def getVisTimeBar(self):
        return 1

    def getVisTimeStep(self):
        return 1

    def getVisTimeTick(self):
        return 0
