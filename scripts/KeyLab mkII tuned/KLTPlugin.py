import device
import plugins
import channels
import ui
import midi
# Global variable

#ABSOLUTE VALUE
ABSOLUTE_VALUE = 64

def Plugin(event, clef) :

    recognized_plugin = False
    plugin_name = ui.getFocusedPluginName()
    
    global ABSOLUTE_VALUE
    
    if plugin_name == 'FLEX' :
        recognized_plugin = True
        ## FLEX ##
    
        PARAM_MAP = {
                '16':21,
                '17':22,
                '18':25,
                '19':30,
                '20':0,
                '21':2,
                '22':3,
                '23':4,
                '224':10,
                '225':11,
                '226':12,
                '227':13,
                '228':14,
                '229':15,
                '230':16,
                '231':17,
                '1':-1 # Not Mapped Yet
                }
                
    elif plugin_name == 'FPC' :
        recognized_plugin = True
        ## FPC ##
    
        PARAM_MAP = {
                '16':8,
                '17':9,
                '18':10,
                '19':11,
                '20':12,
                '21':13,
                '22':14,
                '23':15,
                '224':0,
                '225':1,
                '226':2,
                '227':3,
                '228':4,
                '229':5,
                '230':6,
                '231':7,
                '1':-1
                }
                
    elif plugin_name == 'FL Keys' :
        recognized_plugin = True
        ## FL Keys ##
    
        PARAM_MAP = {
                '16':0,
                '17':1,
                '18':14,
                '19':13,
                '20':5,
                '21':4,
                '22':4,
                '23':8,
                '224':12,
                '225':7,
                '226':11,
                '227':10,
                '228':3,
                '229':2,
                '230':6,
                '231':9,
                '1':-1
                }
                
    elif plugin_name == 'Sytrus' :
        recognized_plugin = True
        ## SYTRUS ##
    
        PARAM_MAP = {
                '16':18,
                '17':19,
                '18':1,
                '19':11,
                '20':12,
                '21':13,
                '22':14,
                '23':15,
                '224':3,
                '225':4,
                '226':5,
                '227':6,
                '228':7,
                '229':8,
                '230':9,
                '231':10,
                '1':-1
                }
                
    elif plugin_name == 'GMS' :
        recognized_plugin = True
        ## GMS ##
    
        PARAM_MAP = {
                '16':32,
                '17':33,
                '18':46,
                '19':45,
                '20':56,
                '21':57,
                '22':58,
                '23':65,
                '224':24,
                '225':25,
                '226':26,
                '227':27,
                '228':40,
                '229':41,
                '230':42,
                '231':38,
                '1':-1
                }
                
    elif plugin_name == 'Harmless' :
        recognized_plugin = True
        ## HARMLESS ##
    
        PARAM_MAP = {
                '16':54,
                '17':59,
                '18':58,
                '19':89,
                '20':65,
                '21':79,
                '22':97,
                '23':91,
                '224':26,
                '225':27,
                '226':31,
                '227':28,
                '228':48,
                '229':49,
                '230':52,
                '231':58,
                '1':-1
                }
                
    elif plugin_name == 'Harmor' :
        recognized_plugin = True
        ## HARMOR ##
    
        PARAM_MAP = {
                '16':52,
                '17':57,
                '18':438,
                '19':443,
                '20':787,
                '21':791,
                '22':803,
                '23':810,
                '224':103,
                '225':104,
                '226':105,
                '227':106,
                '228':127,
                '229':128,
                '230':129,
                '231':130,
                '1':-1
                }
    
    elif plugin_name == 'Morphine' :
        recognized_plugin = True
        ## MORPHINE ##
    
        PARAM_MAP = {
                '16':40,
                '17':41,
                '18':1,
                '19':6,
                '20':30,
                '21':31,
                '22':32,
                '23':33,
                '224':21,
                '225':22,
                '226':23,
                '227':24,
                '228':25,
                '229':26,
                '230':27,
                '231':28,
                '1':-1
                }
                
    elif plugin_name == '3x Osc' :
        recognized_plugin = True
        ## 3X OSC ##
    
        PARAM_MAP = {
                '16':1,
                '17':2,
                '18':8,
                '19':9,
                '20':7,
                '21':15,
                '22':16,
                '23':14,
                '224':4,
                '225':5,
                '226':11,
                '227':12,
                '228':18,
                '229':19,
                '230':6,
                '231':13,
                '1':-1
                }
                
    elif plugin_name == 'Fruity DX10' :
        recognized_plugin = True
        ## FRUITY DX10 ##
    
        PARAM_MAP = {
                '16':11,
                '17':21,
                '18':13,
                '19':10,
                '20':3,
                '21':4,
                '22':14,
                '23':15,
                '224':0,
                '225':1,
                '226':2,
                '227':4,
                '228':5,
                '229':6,
                '230':7,
                '231':8,
                '1':-1
                }
    
    elif plugin_name == 'BASSDRUM' :
        recognized_plugin = True
        ## BASSDRUM ##
    
        PARAM_MAP = {
                '16':8,
                '17':7,
                '18':6,
                '19':0,
                '20':4,
                '21':3,
                '22':5,
                '23':2,
                '224':9,
                '225':10,
                '226':11,
                '227':12,
                '228':14,
                '229':13,
                '230':15,
                '231':1,
                '1':-1
                }
                
    elif plugin_name == 'Fruit kick' :
        recognized_plugin = True
        ## FRUIT KICK ##
    
        PARAM_MAP = {
                '16':-1,
                '17':-1,
                '18':-1,
                '19':-1,
                '20':-1,
                '21':-1,
                '22':-1,
                '23':-1,
                '224':0,
                '225':1,
                '226':2,
                '227':3,
                '228':4,
                '229':5,
                '230':-1,
                '231':-1,
                '1':-1
                }

    elif plugin_name == 'MiniSynth' :
        recognized_plugin = True
        ## MINISYNTH ##
    
        PARAM_MAP = {
                '16':8,
                '17':9,
                '18':20,
                '19':19,
                '20':5,
                '21':2,
                '22':25,
                '23':26,
                '224':12,
                '225':13,
                '226':14,
                '227':15,
                '228':21,
                '229':22,
                '230':23,
                '231':24,
                '1':1
                }
    elif plugin_name == 'PoiZone' :
        recognized_plugin = True
        ## POIZONE ##
    
        PARAM_MAP = {
                '16':18,
                '17':19,
                '18':26,
                '19':28,
                '20':29,
                '21':30,
                '22':15,
                '23':46,
                '224':11,
                '225':12,
                '226':13,
                '227':14,
                '228':22,
                '229':23,
                '230':24,
                '231':25,
                '1':43
                }
                
    elif plugin_name == 'Sakura' :
        recognized_plugin = True
        ## Sakura ##
    
        PARAM_MAP = {
                '16':29,
                '17':30,
                '18':33,
                '19':31,
                '20':24,
                '21':25,
                '22':9,
                '23':14,
                '224':34,
                '225':35,
                '226':36,
                '227':37,
                '228':2,
                '229':3,
                '230':4,
                '231':5,
                '1':43
                }
                
    if recognized_plugin :    
        cle = str(clef)
        PLUGIN_PARAM = PARAM_MAP.get(cle)
        
        if event.status == midi.MIDI_CONTROLCHANGE :
            ABSOLUTE_VALUE = int(127*plugins.getParamValue(PLUGIN_PARAM ,channels.channelNumber()))
            if event.data2 < 64 :
                event.data2 = RelativeToAbsolute(event)
            else :
                event.data2 = RelativeToAbsolute(event)


        if PLUGIN_PARAM != -1 :
            value = event.data2/127
            plugins.setParamValue(value,PLUGIN_PARAM ,channels.channelNumber())
            event.handled = False
            param = str(plugins.getParamName(PLUGIN_PARAM, channels.channelNumber()))
            value = str(round(100*plugins.getParamValue(PLUGIN_PARAM, channels.channelNumber())))
        else :
            param = ""
            value = "" 
    else :
        param = ""
        value = ""
        
    return param, value
    


    # UTILITY 



def RelativeToAbsolute(event) :
        global ABSOLUTE_VALUE
        if event.data2 < 64 :
            ABSOLUTE_VALUE += 2*event.data2
        else :
            ABSOLUTE_VALUE -= 2*(event.data2-64)
        if ABSOLUTE_VALUE > 127 :
            ABSOLUTE_VALUE = 127
        elif ABSOLUTE_VALUE < 0 :
            ABSOLUTE_VALUE = 0
        return ABSOLUTE_VALUE