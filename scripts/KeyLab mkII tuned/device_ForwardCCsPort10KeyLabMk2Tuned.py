# name=Forward CCs Port 10 KEYLAB MKII (tuned)
# receiveFrom=Forward CCs Port 10 KEYLAB MKII (tuned)

"""
[[
	Surface:	KeyLab mkII
	Developer:	Farès MEZDOUR
	Version:	Beta 1.0
]]
"""

# This script allows the KeyLab mkII to communicate 
# with plugins by forwarding CCs to port 10 ( Arturia's Software )

import ui
import midi
import device
import KLTVCOL
import device_KeyLabmk2Tuned as KL
import channels



class TSimple():

    def OnInit(self):
        KL.init()
        
    def OnMidiIn(self, event) :
        
        #VCol Test
        v_collection = False
        string = ui.getFocusedPluginName()
        for i in KLTVCOL.V_COL :
            if string == i :
                v_collection = True
        
        if (event.status == midi.MIDI_CONTROLCHANGE and v_collection == True ) or event.status == 224 :    
            # Manage Analog Lab Plugin
            
            msg = event.status + (event.data1 << 8) + (event.data2 << 16) + (10 << 24)
            device.forwardMIDICC(msg, 2)                    
            event.handled = False

        else :
            if KL._processor.ProcessEvent(event):
                event.handled = False
            
    def OnMidiMsg(self, event):
        event.handled = False 




Simple = TSimple()


def OnInit():
    Simple.OnInit()

def OnDeInit():
    return

def OnMidiMsg(event):
    Simple.OnMidiMsg(event)

def OnMidiIn(event):
    Simple.OnMidiIn(event)
    
def OnPitchBend(event) :
    if channels.getChannelName(channels.channelNumber()) not in KLTVCOL.V_COL :
        channels.setChannelPitch(channels.channelNumber(),(event.data2-64)*(200/64),1)
        event.handled = True
    else :
        event.handled = True

