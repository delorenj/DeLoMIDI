"""general: version and undo hint."""
from __future__ import annotations

from .base import Impl


class GeneralImpl(Impl):
    def getVersion(self):
        return self.s.api_version

    def getUndoLevelHint(self):
        return self.s.undo_hint

    def safeToEdit(self):
        return True

    def getChangedFlag(self):
        return 0
