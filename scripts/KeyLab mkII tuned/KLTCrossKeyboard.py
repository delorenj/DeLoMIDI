import midi
import channels
import mixer

# This script contains big fonctions that can be shared with other scripts


MX_OFFSET = 0
CH_OFFSET = 0

def SetVolumeTrack(event):
    value = event.data2/127
    if event.midiId == midi.MIDI_CONTROLCHANGE  :
        event.handled = False
        if event.data1 == 2 :
            mixer.setTrackVolume(1 + (8*MX_OFFSET),0.8*value)
        elif event.data1 == 3 :
            mixer.setTrackVolume(2 + (8*MX_OFFSET),0.8*value)
        elif event.data1 == 4 :
            mixer.setTrackVolume(3 + (8*MX_OFFSET),0.8*value)
        elif event.data1 == 5 :
            mixer.setTrackVolume(4 + (8*MX_OFFSET),0.8*value)
        elif event.data1 == 6 :
            mixer.setTrackVolume(5 + (8*MX_OFFSET),0.8*value)
        elif event.data1 == 7 :
            mixer.setTrackVolume(6 + (8*MX_OFFSET),0.8*value)
        elif event.data1 == 8 :
            mixer.setTrackVolume(7 + (8*MX_OFFSET),0.8*value)
        elif event.data1 == 9 :
            mixer.setTrackVolume(8 + (8*MX_OFFSET),0.8*value)
        elif event.data1 == 1 :
            mixer.setTrackVolume(0,0.8*value)

 
def SetPanTrack(event):
    event.handled = False
    data = 0
    if event.data2 > 0x40 : data = -1
    elif event.data2 < 0x40 : data = 1
    if event.data1 == 16 :
        mixer.setTrackPan(1 + (8*MX_OFFSET),(mixer.getTrackPan(1+(8*MX_OFFSET)) + (data/20)))
    elif event.data1 == 17 :
        mixer.setTrackPan(2 + (8*MX_OFFSET),(mixer.getTrackPan(2+(8*MX_OFFSET)) + (data/20)))
    elif event.data1 == 18 :
        mixer.setTrackPan(3 + (8*MX_OFFSET),(mixer.getTrackPan(3+(8*MX_OFFSET)) + (data/20)))
    elif event.data1 == 19 :
        mixer.setTrackPan(4 + (8*MX_OFFSET),(mixer.getTrackPan(4+(8*MX_OFFSET)) + (data/20)))
    elif event.data1 == 20 :
        mixer.setTrackPan(5 + (8*MX_OFFSET),(mixer.getTrackPan(5+(8*MX_OFFSET)) + (data/20)))
    elif event.data1 == 21 :
        mixer.setTrackPan(6 + (8*MX_OFFSET),(mixer.getTrackPan(6+(8*MX_OFFSET)) + (data/20)))
    elif event.data1 == 22 :
        mixer.setTrackPan(7 + (8*MX_OFFSET),(mixer.getTrackPan(7+(8*MX_OFFSET)) + (data/20)))
    elif event.data1 == 23 :
        mixer.setTrackPan(8 + (8*MX_OFFSET),(mixer.getTrackPan(8+(8*MX_OFFSET)) + (data/20)))
    elif event.data1 == 24 :
        mixer.setTrackPan(0,(mixer.getTrackPan(0) + (data/20)))