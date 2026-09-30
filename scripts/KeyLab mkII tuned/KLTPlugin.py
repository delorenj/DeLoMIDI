import device
import plugins
import channels
import ui
import midi
import KLTCrossKeyboard as AKLmk2      # KLT F-13: sel_channel(), rel_ticks()
import KLTLog                          # KLT F-16: one-time notes about stale database indices
# Global variable

# KLT F-10: the 8 encoders (database keys '16'..'23') are relative; everything else in the database is absolute
RELATIVE_CLEFS = ('16', '17', '18', '19', '20', '21', '22', '23')
TICK = 2/127        # one encoder tick = 2/127 of the parameter range (stock: +2 on a 0..127 scale)

def Plugin(event, clef, absolute = False) :
    # KLT F-02: `absolute` lets a caller that knows its control sends absolute values (Analog Lab's knobs) reuse the
    # encoder rows of the database

    recognized_plugin = False
    plugin_name = ui.getFocusedPluginName()
    # KLT F-10: no module-level accumulator any more (ABSOLUTE_VALUE, RelativeToAbsolute), see the tick decode at the end
    
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
                
    # KLT F-16: an unmapped slot (-1) and a control the database does not know (None) are decided BEFORE any plugins.* call
    # (stock asked for getParamValue(-1, ...) first), and the parameter must exist on the plugin
    PLUGIN_PARAM = PARAM_MAP.get(str(clef)) if recognized_plugin else None
    channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index, -1 when there is no channel to address
    if PLUGIN_PARAM is None or PLUGIN_PARAM < 0 or channel < 0 :
        return "", ""
    try :
        if PLUGIN_PARAM >= plugins.getParamCount(channel) :
            KLTLog.log_once(('plugin-param-range', plugin_name, PLUGIN_PARAM),
                            'plugin database: %s parameter %d does not exist on this plugin (stale index?)' % (plugin_name, PLUGIN_PARAM))
            return "", ""
    except Exception :
        KLTLog.exception('KLTPlugin.Plugin getParamCount')
        return "", ""

    if str(clef) in RELATIVE_CLEFS and not absolute :
        # KLT F-10: encoders are relative: move by the tick count from the plugin's live value (stock re-seeded an int()
        # copy of it every event and added 2*data2 in 1/127 steps, so nothing below 1/127 survived)
        value = plugins.getParamValue(PLUGIN_PARAM, channel) + AKLmk2.rel_ticks(event.data2) * TICK
    else :
        # KLT F-10: faders and the mod wheel are absolute (stock read the mod wheel's value as a relative tick count)
        value = event.data2/127
    value = min(1.0, max(0.0, value))
    plugins.setParamValue(value, PLUGIN_PARAM, channel)
    # KLT F-08: no event.handled = False here; whether the event is consumed is decided once by the caller
    param = str(plugins.getParamName(PLUGIN_PARAM, channel))
    value = str(round(100*plugins.getParamValue(PLUGIN_PARAM, channel)))
    return param, value

# KLT F-10: stock's RelativeToAbsolute() (an int() re-seed of the live value plus 2*data2) is replaced by the tick decode above
