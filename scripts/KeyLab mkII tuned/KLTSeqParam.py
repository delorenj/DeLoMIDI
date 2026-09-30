import channels
import patterns
import KLTProcess as KLmk2Pr

# This script contains fonctions that modify Bit parameter in Step Sequencer

# ABS
ABSOLUTE_VALUE = 64
# PAGE MAP
PAGE_MAP = {
        "PITCH" : 16,
        "VELOCITY" : 17,
        "RELEASE VOICE" : 18,
        "FINE PITCH" : 19,
        "PAN" : 20,
        "MOD X" : 21,
        "MOD Y" : 22,
        "SHIFT" : 23
        }

# PAGE
PAGE = 0       

def Param(event) :
    channel = channels.channelNumber()
    pattern = patterns.patternNumber()
    value = event.data2
    center = min(KLmk2Pr.INDEX_PRESSED)+(16*KLmk2Pr.RECT_OFFSET)
    
    global PAGE
    temp = event.controlNum
    if PAGE != temp :
        channels.closeGraphEditor(1)
    
    if event.controlNum == 16 :
        for i in KLmk2Pr.INDEX_PRESSED :
            step = i+(16*KLmk2Pr.RECT_OFFSET)
            if event.data2 < 64 : delta = -1
            else : delta = + 1
            value = channels.getCurrentStepParam(channel, step, 0)
            channels.setStepParameterByIndex(channel, pattern, step, 0, value + delta, 0)
        channels.showGraphEditor(0,0,center,channel,0) # PITCH
        PAGE = PAGE_MAP.get("PITCH")
    else :
        if event.data2 < 64 :
            delta = 3
            value = RelativeToAbsolute(delta)
        else :
            delta = -3
            value = RelativeToAbsolute(delta)
            
        if event.controlNum == 17 :
            for i in KLmk2Pr.INDEX_PRESSED :
                step = i+(16*KLmk2Pr.RECT_OFFSET)
                channels.setStepParameterByIndex(channel, pattern, step, 1, value, 0)
                if not channels.isGraphEditorVisible() :
                    channels.showGraphEditor(1,1,center,channel,0) # VELOCITY
                    PAGE = PAGE_MAP.get("VELOCITY")
                else : 
                    channels.updateGraphEditor()
        elif event.controlNum == 18 :
            for i in KLmk2Pr.INDEX_PRESSED :
                step = i+(16*KLmk2Pr.RECT_OFFSET)
                channels.setStepParameterByIndex(channel, pattern, step, 2, value, 0)
                if not channels.isGraphEditorVisible() :
                    channels.showGraphEditor(1,2,center,channel,0) # RELEASE VOICE
                    PAGE = PAGE_MAP.get("RELEASE VOICE")
                else : 
                    channels.updateGraphEditor()
        elif event.controlNum == 19 :
            for i in KLmk2Pr.INDEX_PRESSED :
                step = i+(16*KLmk2Pr.RECT_OFFSET)
                channels.setStepParameterByIndex(channel, pattern, step, 3, value, 0)
                if not channels.isGraphEditorVisible() :
                    channels.showGraphEditor(1,3,center,channel,0) # FINE PITCH
                    PAGE = PAGE_MAP.get("FINE PITCH")
                else : 
                    channels.updateGraphEditor()
        elif event.controlNum == 20 :
            for i in KLmk2Pr.INDEX_PRESSED :
                step = i+(16*KLmk2Pr.RECT_OFFSET)
                channels.setStepParameterByIndex(channel, pattern, step, 4, value, 0)
                if not channels.isGraphEditorVisible() :
                    channels.showGraphEditor(1,4,center,channel,0) # PAN
                    PAGE = PAGE_MAP.get("PAN")
                else : 
                    channels.updateGraphEditor()
        elif event.controlNum == 21 :
            for i in KLmk2Pr.INDEX_PRESSED :
                step = i+(16*KLmk2Pr.RECT_OFFSET)
                channels.setStepParameterByIndex(channel, pattern, step, 5, value, 0)
                if not channels.isGraphEditorVisible() :
                    channels.showGraphEditor(1,5,center,channel,0) # MOD X
                    PAGE = PAGE_MAP.get("MOD X")
                else : 
                    channels.updateGraphEditor()
        elif event.controlNum == 22 :
            for i in KLmk2Pr.INDEX_PRESSED :
                step = i+(16*KLmk2Pr.RECT_OFFSET)
                channels.setStepParameterByIndex(channel, pattern, step, 6, 2*value, 0)
                if not channels.isGraphEditorVisible() :
                    channels.showGraphEditor(1,6,center,channel,0) # MOD Y
                    PAGE = PAGE_MAP.get("MOD Y")
                else : 
                    channels.updateGraphEditor()



    # UTILITY


def RelativeToAbsolute(delta) :
        global ABSOLUTE_VALUE
        ABSOLUTE_VALUE += delta
        if ABSOLUTE_VALUE > 127 :
            ABSOLUTE_VALUE = 127
        elif ABSOLUTE_VALUE < 0 :
            ABSOLUTE_VALUE = 0
        return ABSOLUTE_VALUE