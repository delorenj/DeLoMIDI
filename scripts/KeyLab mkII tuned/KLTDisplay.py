# MIT License
# Copyright (c) 2020 Ray Juang


import time

try:                                    # KLT O-03: ships with FL's embedded Python 3.12; the fallback keeps us alive without
    import unicodedata
except ImportError:
    unicodedata = None

import KLTConfig as CFG
from KLTDispatch import send_to_device


# KLT O-03: the LCD takes 7-bit ASCII. Stock encoded with strict 'ascii', so one accented channel name or project
# title raised UnicodeEncodeError inside the LCD code, left the bad text stored, and killed every later OnIdle.
LCD_COLS = 16
_PUNCT = {0x2010: '-', 0x2011: '-', 0x2012: '-', 0x2013: '-', 0x2014: '-', 0x2015: '-', 0x2018: "'", 0x2019: "'",
          0x201A: "'", 0x201B: "'", 0x201C: '"', 0x201D: '"', 0x201E: '"', 0x2022: '*', 0x2026: '...',
          0x00A0: ' ', 0x2002: ' ', 0x2003: ' ', 0x2009: ' ', 0x00D7: 'x', 0x00B7: '.', 0x2212: '-'}


def _fold_char(c):
    """One character to printable ASCII: ASCII passes, accents fold (e-acute -> e), typographic punctuation maps to its
    ASCII cousin, control characters (an embedded NUL ends the line on the hardware) become a space, the rest '?'."""
    o = ord(c)
    if 0x20 <= o < 0x7F:
        return c
    if o < 0x20 or o == 0x7F:
        return ' '
    if o in _PUNCT:
        return _PUNCT[o]
    if unicodedata is not None:
        try:
            folded = ''.join(x for x in unicodedata.normalize('NFKD', c) if 0x20 <= ord(x) < 0x7F)
        except Exception:
            folded = ''
        if folded:
            return folded
    return '?'


def ascii_line(text):
    """LCD-safe text for any input (None, bytes, numbers, non-ASCII, control characters). Never raises. Not clipped:
    the scroller windows long text to 16 characters."""
    try:
        if text is None:
            return ''
        if isinstance(text, (bytes, bytearray)):
            text = bytes(text).decode('utf-8', 'replace')
        elif not isinstance(text, str):
            text = str(text)
        return ''.join(_fold_char(c) for c in text)
    except Exception:
        return ''


def _lcd_bytes(text):
    """<= 16 printable-ASCII bytes, whatever `text` is (last line of defence before the wire)."""
    return bytearray(ord(c) for c in ascii_line(text)[:LCD_COLS])


class KeyLabDisplay:
    """ Manages scrolling display of two lines so that long strings can be scrolled on each line. """
    def __init__(self):
        # Holds the text to display on first line. May exceed the 16-char display limit.
        self._line1 = ' '
        # Holds the text to display on second line. May exceed the 16-char display limit.
        self._line2 = ' '

        # Holds ephemeral text that will expire after the expiration timestamp. These lines will display if the
        # the expiration timestamp is > current timestamp.
        self._ephemeral_line1 = ' '
        self._ephemeral_line2 = ' '
        self._expiration_time_ms = 0

        # Holds the starting offset of where the line1 text should start.
        self._line1_display_offset = 0
        
        # Holds the starting offset of where the line2 text should start.
        self._line2_display_offset = 0
        
        # Last timestamp in milliseconds in which the text was updated.
        self._last_update_ms = 0
        
        # Minimum interval before text is scrolled
        # KLT O-18: 1500 ms per character took 20 s to cycle a 30-character name; LCD_SCROLL_MS defaults to 500
        self._scroll_interval_ms = self._configured_scroll_ms()
        
        # How many characters to allow last char to scroll before starting over.
        self._end_padding = 3
        
        # Track what's currently being displayed
        self._last_payload = bytes()

    @staticmethod
    def _configured_scroll_ms():
        # KLT O-18: read from KLTConfig, a broken value falls back to the stock 1500 ms
        try:
            v = float(CFG.LCD_SCROLL_MS)
            return v if v > 0 else 1500
        except Exception:
            return 1500

    def _get_line1_bytes(self):
        # Get up to 16-bytes the exact chars to display for line 1.
        start_pos = self._line1_display_offset
        end_pos = start_pos + 16
        line_src = self._line1
        if self._expiration_time_ms > self.time_ms():
            line_src = self._ephemeral_line1
        return _lcd_bytes(line_src[start_pos:end_pos])   # KLT O-03: sanitised, <= 16 printable ASCII bytes

    def _get_line2_bytes(self):
        # Get up to 16-bytes the exact chars to display for line 2.
        start_pos = self._line2_display_offset
        end_pos = start_pos + 16
        line_src = self._line2
        if self._expiration_time_ms > self.time_ms():
            line_src = self._ephemeral_line2
        return _lcd_bytes(line_src[start_pos:end_pos])   # KLT O-03: sanitised, <= 16 printable ASCII bytes

    def _get_new_offset(self, start_pos, line_src):
        end_pos = start_pos + 16
        if end_pos >= len(line_src) + self._end_padding or len(line_src) <= 16:
            return 0
        else:
            return start_pos + 1

    def _update_scroll_pos(self):
        current_time_ms = self.time_ms()
        self._scroll_interval_ms = self._configured_scroll_ms()   # KLT O-18: honour a changed switch
        if current_time_ms >= self._scroll_interval_ms + self._last_update_ms:
            self._line1_display_offset = self._get_new_offset(self._line1_display_offset, self._line1)
            self._line2_display_offset = self._get_new_offset(self._line2_display_offset, self._line2)
            self._last_update_ms = current_time_ms

    @staticmethod
    def time_ms():
        # Get the current timestamp in milliseconds
        return time.monotonic() * 1000


    def _refresh_display(self):
        # Internally called to refresh the display now.
        data = bytes([0x04, 0x00, 0x60])
        data += bytes([0x01]) + self._get_line1_bytes() + bytes([0x00])
        data += bytes([0x02]) + self._get_line2_bytes() + bytes([0x00])
        data += bytes([0x7F])

        self._update_scroll_pos()
        if self._last_payload != data:
            # KLT O-01, O-06: remember the frame only if the output layer accepted it (no output, refused); the next
            # Refresh then tries again instead of believing the keyboard shows text it never received
            if send_to_device(data):
                self._last_payload = data

    def Invalidate(self):
        # KLT O-05: forget what the keyboard shows (memory switch, power cycle, output re-assigned): the unchanged
        # text is sent again on the next refresh. The stock cache was never invalidated, so an LCD that went blank
        # stayed blank for every text of 16 characters or less.
        self._last_payload = bytes()

    def ResetScroll(self):
        self._line1_display_offset = 0
        self._line2_display_offset = 0

    def SetLines(self, line1=None, line2=None, expires=None):
        """ Update lines on the display, or leave alone if not provided.

        :param line1:    first line to update display with or None to leave as is.
        :param line2:    second line to update display with or None to leave as is.
        :param expires:  number of milliseconds that the line persists before expiring. Note that when an expiration
            interval is provided, lines are interpreted as a blank line if not provided.
        """
        # KLT O-03: sanitise BEFORE storing. The stock stored the raw text and encoded it later, so a bad character
        # poisoned the state and every later refresh raised until the text happened to change.
        if line1 is not None:
            line1 = ascii_line(line1)
        if line2 is not None:
            line2 = ascii_line(line2)
        if expires is None:
            if line1 is not None:
                self._line1 = line1
            if line2 is not None:
                self._line2 = line2
        else:
            self._expiration_time_ms = self.time_ms() + expires
            if line1 is not None:
                self._ephemeral_line1 = line1
            if line2 is not None:
                self._ephemeral_line2 = line2

        self._refresh_display()
        return self

    def Refresh(self):
        """ Called to refresh the display, possibly with updated text. """
        if self.time_ms() - self._last_update_ms >= self._scroll_interval_ms:
            self._refresh_display()
        return self