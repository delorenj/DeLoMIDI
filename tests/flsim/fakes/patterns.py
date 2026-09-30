"""patterns: pattern selection. jumpToPattern past the last pattern creates it (stubs patterns/__properties.py)."""
from __future__ import annotations

from .base import Impl


class PatternsImpl(Impl):
    MAX_PATTERNS = 999

    def patternNumber(self):
        return self.s.pattern

    def patternCount(self):
        return self.s.pattern_count

    def patternMax(self):
        return self.MAX_PATTERNS

    def getPatternName(self, index):
        s = self.s
        if not 1 <= index <= max(s.pattern_count, 1):
            self.host.violation("index", "patterns.getPatternName", "pattern %d outside 1..%d" % (index, s.pattern_count))
            return ""
        return s.pattern_names.get(index, "Pattern %d" % index)

    def jumpToPattern(self, index):
        s = self.s
        if not 1 <= index <= self.MAX_PATTERNS:
            self.host.violation("index", "patterns.jumpToPattern", "pattern %d outside 1..%d" % (index, self.MAX_PATTERNS))
            return
        s.pattern_count = max(s.pattern_count, index)     # creates the pattern if it does not exist
        s.pattern = index
