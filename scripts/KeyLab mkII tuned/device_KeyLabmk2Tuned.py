# name= KeyLab mkII (tuned)

"""
[[
	Surface:	KeyLab mkII
	Developer:	Farès MEZDOUR
	Version:	Beta 1.0
]]
"""

import ui
import time
import channels
import patterns
import midi
import KLTCrossKeyboard


from KLTProcess import KeyLabMidiProcessor
from KLTReturn import KeyLabLightReturn
from KLTDisplay import KeyLabDisplay
from KLTPages import KeyLabPagedDisplay
from KLTDispatch import send_to_device

## CONSTANT

TEMP = 0.5
HW_Flag = {"Select" : [295, 263, 256]} 


#-----------------------------------------------------------------------------------------

# This is the master class. It will run the init lights pattern 
# and call the others class to process MIDI events


class MidiControllerConfig :

    def __init__(self):
        self._lightReturn = KeyLabLightReturn()
        self._display = KeyLabDisplay()
        self._paged_display = KeyLabPagedDisplay(self._display)


    def LightReturn(self) :
        return self._lightReturn
        
    def display(self):
        return self._display

    def paged_display(self):
        return self._paged_display
        
    def Idle(self):
        self._paged_display.Refresh()
        

        
    def Sync(self):
        
        # Update display
        
        active_index = channels.selectedChannel()
        channel_name = channels.getChannelName(active_index)
        pattern_number = patterns.patternNumber()
        pattern_name = patterns.getPatternName(pattern_number)      
        
        
        self._paged_display.SetPageLines(
            'main',
            line1='%d - %s' % (active_index + 1, channel_name),
            line2='%s' % pattern_name)






#----------------------------------------------------------------------------------------

# Function called for each event 


def OnMidiMsg(event) :
    process = _processor.ProcessEvent(event)



# Functions called when FL Studio is starting


def OnInit():
    print("### INIT KEYLAB mkII OKAY ###")
    init()
    _mk2.Sync()
    _mk2.paged_display().SetPageLines('welcome', line1='KeyLab mkII', line2=ui.getProgTitle())
    _mk2.paged_display().SetActivePage('welcome', expires = 1500)
    _mk2.paged_display().SetActivePage('main')
    print("### Messages successfully sent to KEYLAB mkII ###")
    _mk2.LightReturn().init()
    

def init() :
    print("### Successfully created class objects ###")
    global _mk2 
    _mk2 = MidiControllerConfig()
    global _processor
    _processor = KeyLabMidiProcessor(_mk2)
  

# Handles the script when FL Studio closes

def OnDeInit():
    _mk2.paged_display().SetPageLines('goodbye', line1='KeyLab mkII', line2='Disconnected')
    _mk2.paged_display().SetActivePage('goodbye')
    send_to_device(bytes([0x02, 0x7D, 0x7D, 0x0B, 0x00]))
    return

  
# Function called when Play/Pause button is ON

def OnUpdateBeatIndicator(value):
    _mk2.LightReturn().ProcessPlayBlink(value)
    _mk2.LightReturn().ProcessRecordBlink(value)
    _mk2.LightReturn().ProcessSequencerBlink(value)
 


# Function called at refresh, flag value changes depending on the refresh type 

def OnRefresh(flags) :
    _mk2.Sync()
    _mk2.LightReturn().SequencerReturn()     
    _mk2.LightReturn().PlayReturn()
    _mk2.LightReturn().RecordReturn()

    

# Function called time to time mainly to update the beat indicator

def OnIdle():
    _mk2.Idle()
    _mk2.LightReturn().RefreshTime()
    _mk2.LightReturn().MetronomeReturn()
    _mk2.LightReturn().LoopReturn()
    _mk2.LightReturn().NotBlinkingLed()
    _mk2.LightReturn().IsChannelSolo()
    _mk2.LightReturn().IsChannelMuted()
    _mk2.LightReturn().IsTrackSolo()
    _mk2.LightReturn().IsTrackMuted()
    _mk2.LightReturn().SelectedChannel() 
    
    
    
# Function called on a memory switch

def OnSysEx(event) :
    if event.sysex == b'\xf0\x00 k\x7fB\x02\x00\x00\x15\x00\xf7' :
        ui.setFocused(1)
        OnRefresh(32)
        
        
