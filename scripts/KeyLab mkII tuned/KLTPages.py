# MIT License
# Copyright (c) 2020 Ray Juang

from KLTDisplay import KeyLabDisplay


class KeyLabPagedDisplay:
    def __init__(self, display):
        self._display = display
        
        # String line 1
        self._line1 = {}
        
        # String line 2
        self._line2 = {}
        
        # Active page to display or None for default display
        self._active_page = None
        
        # Temporary page to display or None for default display
        self._ephemeral_page = None
        
        # Timestamp after which to switch back to active page.
        self._page_expiration_time_ms = 0
        
        # Last timestamp in milliseconds in which the text was updated.
        self._last_update_ms = 0

    def SetPageLines(self, page_name, line1=None, line2=None):
        if line1 is not None:
            self._line1[page_name] = lambda: line1
        if line2 is not None:
            self._line2[page_name] = lambda: line2
        if self._active_page == page_name:
            self._update_display(False)


    def SetActivePage(self, page_name, expires=None):
        reset_scroll = page_name != self._active_page
        if expires is not None:
            reset_scroll = page_name != self._ephemeral_page
            self._ephemeral_page = page_name
            self._page_expiration_time_ms = KeyLabDisplay.time_ms() + expires
        else:
            self._active_page = page_name
        self._update_display(reset_scroll)


    def display(self):
        return self._display

    def _update_display(self, reset_scroll):
        active_page = self._active_page
        if reset_scroll:
            self._display.ResetScroll()

        self._last_update_ms = KeyLabDisplay.time_ms()
        if self._last_update_ms < self._page_expiration_time_ms:
            active_page = self._ephemeral_page

        if active_page is not None:
            line1 = None
            line2 = None
            if active_page in self._line1:
                line1 = self._line1[active_page]()
            if active_page in self._line2:
                line2 = self._line2[active_page]()
            self._display.SetLines(line1=line1, line2=line2)

    def Refresh(self):
        self._update_display(False)
        self._display.Refresh()
