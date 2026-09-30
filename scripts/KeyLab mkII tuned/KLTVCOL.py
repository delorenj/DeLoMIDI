import channels

# This script contains the strings of the V Collection software

V_COL = ['Analog Lab V',
         'Analog Lab 4',
         'ARP 2600 V3',
         'B-3 V2',
         'Buchla Easel V',
         'Clavinet V',
         'CMI V',
         'CS-80 V3',
         'CZ V',
         'DX7 V',
         'Emulator II V',
         'Farfisa V',
         'Jun-6 V',
         'Jup-8 V4',
         'Matrix-12 V2',
         'Mellotron V',
         'Mini V3',
         'Modular V3',
         'OB-Xa V',
         'PatchWorks',
         'Piano V2',
         'Prophet V3',
         'SEM V2',
         'Solina V2',
         'Stage-73 V2',
         'SQ80 V',
         'Synclavier V',
         'Synthi V',
         'Synthopedia',
         'Vocoder V',
         'Vox Continental V2',
         'Wurli V2'
         ]
         

class ArturiaVCOLLECTION() :
    
    def __init__(self) :
        self._v_col = []
    
    def v_col_aff(self) :
        print(self._v_col)
        return self._v_col
   
    def AddVST(self) :
        string = channels.getChannelName(channels.channelNumber())
        present = False
        for i in self._v_col :
            if string == i :
                present = True
        if present == False and string in V_COL :
            self._v_col.append(string)

    