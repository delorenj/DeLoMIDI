import channels
import general
import mixer
import patterns
import transport
import ui
import device
import plugins
import midi
import KLTCrossKeyboard as AKLmk2
import KLTSeqParam as KLmk2SQP
import KLTPlugin


from KLTDispatch import MidiEventDispatcher
from KLTDispatch import send_to_device
from KLTDisplay import KeyLabDisplay
from KLTPages import KeyLabPagedDisplay
from KLTNavigation import NavigationMode

## CONSTANT

PORT_MIDICC_ANALOGLAB = 10
WidMixer = 0
WidChannelRack = 1
WidPlaylist = 2
WidBrowser = 4
WidPlugin = 5
ANALOGLAB_KNOB_ID = [0x4A, 0x47, 0x4C, 0x4D, 0x5D, 0x49, 0x4B]

# ABS
ABSOLUTE_VALUE = 64

# Event code indicating stop event
SS_STOP = 0

# Event code indicating start start event
SS_START = 2

# SEQUENCER
SEQ_MODE = 0

# MIXER
MIXER_MODE = 0

# RECTANGLE OFFSET
RECT_OFFSET = 0

# EDIT MODE
EDIT_MODE = 0

# SEQ PARAM
SEQ_PARAM = 0

# Max Tracks
MAX_TRACKS = 125

# STATE_MATRIX
STATE_MATRIX = [
                4*[0],
                4*[0],
                4*[0],
                4*[0],
                ]
# LED_MATRIX
LED_MATRIX = [
                4*[0],
                4*[0],
                4*[0],
                4*[0],
                ]
# INDEX PRESSED
INDEX_PRESSED = []

# FPC MAP
FPC_MAP = {
            "36":49,
            "37":55,
            "38":51,
            "39":53,
            "40":48,
            "41":47,
            "42":45,
            "43":43,
            "44":40,
            "45":38,
            "46":46,
            "47":44,
            "48":37,
            "49":36,
            "50":42,
            "51":54
            }
            

# This class processes all CC coming from the controller
# The class creates new handler for each function
# The class calls the right fonction depending on the incoming CC

class KeyLabMidiProcessor:

    @staticmethod
    def _is_pressed(event):
        return event.controlVal != 0

    def __init__(self, mk2):
        def by_midi_id(event) : return event.midiId
        def by_control_num(event) : return event.controlNum
        def by_velocity(event) : return event.data2
        def by_status(event) : return event.status
        def ignore_release(event): return self._is_pressed(event)
        def ignore_press(event): return not self._is_pressed(event)

        self._mk2 = mk2

        self._midi_id_dispatcher = (
            MidiEventDispatcher(by_midi_id)
            .NewHandler(144, self.OnCommandEvent)
            .NewHandler(176, self.OnKnobEvent)
            .NewHandler(224, self.OnSliderEvent)
            )
 
 
        self._status_dispatcher = (
            MidiEventDispatcher(by_status)
            .NewHandler(176, self.OnPluginEvent)
            .NewHandler(153, self.OnDrumSeqEvent)
            .NewHandler(137, self.OnDrumSeqEvent)
            )
  
  
        self._midi_command_dispatcher = (
            MidiEventDispatcher(by_control_num)
            
            
            .NewHandler(95, self.Record, ignore_release)
            .NewHandler(94, self.Start, ignore_release)
            .NewHandler(93, self.Stop, ignore_release)
            .NewHandler(89, self.SetClick, ignore_press)
            .NewHandler(74, self.DrumSeqToggle, ignore_release)
            .NewHandler(56, self.TapTempo, ignore_release)
            .NewHandler(88, self.Overdub, ignore_press)
            .NewHandler(86, self.Loop, ignore_release)
            .NewHandler(81, self.Undo, ignore_press)
            .NewHandler(57, self.Cut, ignore_press)
            .NewHandler(0x5B, self.RewindORprevBar)
            .NewHandler(0x5C, self.FastForwardORnextBar)
            .NewHandler(84, self.SwitchWindow, ignore_release)
            .NewHandler(46, self.BankSelect, ignore_release)
            .NewHandler(47, self.BankSelect, ignore_release)
            .NewHandler(98, self.previousPattern, ignore_release)
            .NewHandler(99, self.nextPattern, ignore_release)
            .NewHandler(87, self.ToggleBrowserChannelRack, ignore_release)
            .NewHandler(51, self.ToggleMixerChannelRack, ignore_release)
            .NewHandlerForKeys(range(8, 16), self.SoloChannel, ignore_press)
            .NewHandlerForKeys(range(16, 24), self.MuteChannel, ignore_press)
            .NewHandlerForKeys(range(24, 32), self.TrackSelect,ignore_press)
            .NewHandlerForKeys(range(0, 8), self.SnapMode, ignore_release) 
            
        )
         
        self._knob_dispatcher = (
            MidiEventDispatcher(by_control_num)
            .NewHandler(60, self.OnKnobNavEvent)
            .NewHandler(60, self.OnKnobNavEvent)
            .NewHandlerForKeys(range(16,25), self.SetPanTrack)
        )      
        
        
        self._knob_nav_dispatcher = (
            MidiEventDispatcher(by_velocity)
            .NewHandler(1, self.TrackSelectMainKnob)
            .NewHandler(65, self.TrackSelectMainKnob)
        )
             
        
        self._plugin_dispatcher = (
            MidiEventDispatcher(by_control_num)
            .NewHandler(74, self.Plugin)
            .NewHandler(71, self.Plugin)
            .NewHandler(76, self.Plugin)
            .NewHandler(77, self.Plugin)
            .NewHandler(93, self.Plugin)
            .NewHandler(18, self.Plugin)
            .NewHandler(19, self.Plugin)
            .NewHandler(16, self.Plugin)
            
            .NewHandler(73, self.Plugin)
            .NewHandler(75, self.Plugin)
            .NewHandler(79, self.Plugin)
            .NewHandler(72, self.Plugin)
            .NewHandler(80, self.Plugin)
            .NewHandler(81, self.Plugin)
            .NewHandler(82, self.Plugin)
            .NewHandler(83, self.Plugin)
            .NewHandler(17, self.Plugin)
            .NewHandler(1, self.SetPanTrack)
            
            
            .NewHandler(28, self.previousPreset, ignore_release)
            .NewHandler(29, self.nextPreset, ignore_release)
        )
        
        self._sequencer_dispatcher = (
            MidiEventDispatcher(by_control_num)
            .NewHandlerForKeys(range(36,52), self.PressSequencer)
        )
      
            # MAPPING SLIDERS
        
        self._slider_dispatcher = (
            MidiEventDispatcher(by_status)
            .NewHandlerForKeys(range(224,233), self.SetVolumeTrack)
        )
        
            # NAVIGATION
        
        self._navigation = NavigationMode(self._mk2.paged_display())




    # DISPATCH
  


    def ProcessEvent(self, event) :
        if event.status == event.midiId or event.midiId == 224 :
            #print("Midi Id","\t",event.status,"\t",event.data1,"\t",event.controlNum,"\t",event.data2,"\t",event.midiId,"\t",event.midiChan,'\t',event.timestamp,'\t',event.handled)
            return self._midi_id_dispatcher.Dispatch(event)
        else :
           #print("Status","\t",event.status,"\t",event.data1,"\t",event.controlNum,"\t",event.data2,"\t",event.midiId,"\t",event.midiChan,'\t',event.timestamp,'\t',event.handled)
            return self._status_dispatcher.Dispatch(event)
    
    def OnCommandEvent(self, event):
        event.handled = True
        self._midi_command_dispatcher.Dispatch(event)


    def OnKnobEvent(self, event):
        event.handled = True
        self._knob_dispatcher.Dispatch(event)
        
    def OnKnobNavEvent(self, event) :
        event.handled = True
        self._knob_nav_dispatcher.Dispatch(event)


    def OnSliderEvent(self, event):
        event.handled = True
        self._slider_dispatcher.Dispatch(event)
        
    def OnPluginEvent(self, event):
        event.handled = True
        self._plugin_dispatcher.Dispatch(event)
        
    def OnSeqEvent(self, event):
        device.processMIDICC(event)
        self._sequencer_dispatcher.Dispatch(event)

    def OnDrumSeqEvent(self, event) :
        if event.status == 153 :
            if SEQ_MODE == 1 :
                event.handled = True
                self.OnSeqEvent(event)
            else :
                event.data1 = FPC_MAP.get(str(event.data1))
                event.data2 = midi.MIDI_NOTEON
                event.handled = False
        elif event.status == 137 :
            if SEQ_MODE == 1 :
                if not transport.getLoopMode() :
                    event.handled = True
                    self.ReleaseBit(event)
            else :
                event.data1 = FPC_MAP.get(str(event.data1))
                event.data2 = midi.MIDI_NOTEOFF
                event.handled = False             
            
           
  
  # WINDOW



    def _show_and_focus(self, window):
        if not ui.getVisible(window):
            ui.showWindow(window)
        if not ui.getFocused(window):
            ui.setFocused(window)


    def _hideAll(self, event) :
        for i in range (channels.channelCount()) :
            channels.showEditor(i,0)

    
    def SwitchWindow(self, event) :
        if (ui.getFocused(WidChannelRack) or ui.getFocused(WidPlugin)) :
            self.showPlugin(event)
        elif ui.getFocused(WidMixer) :
            track = mixer.trackNumber()
            mixer.armTrack(track)
            self._navigation.ArmRefresh(track)
            #plugin = channels.channelNumber()
            # for i in range(plugins.getParamCount(plugin)) :
                # print(i, plugins.getParamName(i,plugin), plugins.getParamValue(i,plugin))
        elif ui.getFocused(WidBrowser) :
            nodeFileType = ui.getFocusedNodeFileType()
            if nodeFileType == -1:
                return
            if nodeFileType <= -100:
                transport.globalTransport(midi.FPT_Enter, 1)
            else:
                ui.selectBrowserMenuItem()
                if not ui.isInPopupMenu() :
                    self._navigation.PressRefresh()
            
    
    
    def showPlugin(self, event) :
        channels.showEditor(channels.channelNumber())

    
    def ToggleBrowserChannelRack(self, event) :
        self.FakeMIDImsg()
        if ui.getFocused(4) != True :
            self._show_and_focus(4)
            self._navigation.BrowserRefresh()
        else :
            self._show_and_focus(1)
            self._navigation.ChannelRackRefresh()

    
    def ToggleMixerChannelRack(self, event) :
        self.FakeMIDImsg()
        self._hideAll(event)
        global MIXER_MODE
        if MIXER_MODE == 0 :
            MIXER_MODE = 1
            self._show_and_focus(WidMixer)
        else :
            MIXER_MODE = 0
            self._show_and_focus(WidChannelRack)
        self._navigation.MixerToggleRefresh()

    def DrumSeqToggle(self, event) :
        self.FakeMIDImsg()
        self._hideAll(event)
        global SEQ_MODE 
        if SEQ_MODE == 0 :
            SEQ_MODE = 1
        else :
            SEQ_MODE = 0
        self._navigation.DrumSeqToggleRefresh()



    # NAVIGATION



    def TrackSelectMainKnob(self, event):
        if ui.getFocused(WidPlugin) :
            self._hideAll(event)
            self._show_and_focus(WidChannelRack)
        elif ui.getFocused(WidBrowser) :
            if ui.isInPopupMenu() :  
                if event.data2 == 65 :
                    ui.up()
                elif event.data2 == 1 :
                    ui.down()
                self._navigation.HintRefresh(ui.getFocusedNodeCaption())
            else :
                if event.data2 == 65 :
                    ui.previous()
                elif event.data2 == 1 :
                    ui.next()
                self._navigation.HintRefresh(ui.getFocusedNodeCaption())
        elif ui.getFocused(WidMixer) :
            if event.data2 == 65 :
                self._show_and_focus(WidMixer)
                self._hideAll(event)
                ui.previous()
            elif event.data2 == 1 :  
                self._show_and_focus(WidMixer)
                self._hideAll(event)
                ui.next()
        elif ui.getFocused(WidChannelRack) :
            if event.data2 == 65 :
                self._hideAll(event)
                self._show_and_focus(WidChannelRack)
                ui.previous()
                mixer.setTrackNumber(channels.getTargetFxTrack(channels.channelNumber()),3)
            elif event.data2 == 1 :  
                self._hideAll(event)
                self._show_and_focus(WidChannelRack)
                ui.next()
                mixer.setTrackNumber(channels.getTargetFxTrack(channels.channelNumber()),3)
        else :
            self._show_and_focus(WidChannelRack)
    
    def BankSelect(self, event) :
        if MIXER_MODE == 1 :
            self.FakeMIDImsg()
            if event.controlNum == 46 :
                AKLmk2.MX_OFFSET -= 1
                if AKLmk2.MX_OFFSET < 0 :
                    AKLmk2.MX_OFFSET = 0
                self._navigation.BankMixRefresh()
            elif event.controlNum == 47 :
                if (AKLmk2.MX_OFFSET + 1)*8 < MAX_TRACKS :
                    AKLmk2.MX_OFFSET += 1
                    self._navigation.BankMixRefresh()
        else :
            self.FakeMIDImsg()
            if event.controlNum == 46 :
                AKLmk2.CH_OFFSET -= 1
                if AKLmk2.CH_OFFSET < 0 :
                    AKLmk2.CH_OFFSET = 0
                self._navigation.BankChanRefresh()
            elif event.controlNum == 47 :
                if (AKLmk2.CH_OFFSET + 1)*8 < channels.channelCount() :
                    AKLmk2.CH_OFFSET += 1
                    self._navigation.BankChanRefresh()


    def TrackSelect(self, event):
        if MIXER_MODE :
            track = (event.controlNum - 23) + 8*AKLmk2.MX_OFFSET
            mixer.setTrackNumber(track,3)
            self._hideAll(event)
        else :
            channel = (event.controlNum - 24) + 8*AKLmk2.CH_OFFSET
            if channel < channels.channelCount():
                channels.selectOneChannel(channel)
                mixer.setTrackNumber(channels.getTargetFxTrack(channels.channelNumber()),3)
                self._hideAll(event)
                ui.setFocused(WidChannelRack)

    
    def previousPattern(self, event) :
        if ui.getFocused(5) :
            self.previousPreset(event)
        else :
            pattern = patterns.patternNumber()
            patterns.jumpToPattern(pattern - 1)
            
     
    def nextPattern(self, event) :
        if ui.getFocused(5) :
            self.nextPreset(event)
        else :
            pattern = patterns.patternNumber()
            patterns.jumpToPattern(pattern + 1)
        
        
        
    # PLUGIN
  

    
    def nextPreset(self, event) :
        if ui.getFocused(5) :
            plugins.nextPreset(channels.channelNumber())


    def previousPreset(self, event) :
        if ui.getFocused(5) :
            plugins.prevPreset(channels.channelNumber())


    def Plugin(self, event, clef) :
        if ui.getFocused(5) :
            param, value = KLTPlugin.Plugin(event,clef)
            if event.controlNum != 1 :
                self._navigation.PluginRefresh(param, value)



    # FUNCTIONS



    def Record(self, event) :
        transport.record()
        self._navigation.RecordRefresh()
    
    
    def Start(self, event) :
        transport.start()
        self._navigation.PlayRefresh()
    
    
    def Stop(self, event) :
        transport.stop()
        self._navigation.StopRefresh()
     
     
    def FastForwardORnextBar(self, event) :
        if SEQ_MODE == 1 and event.controlVal == 127 :
            global RECT_OFFSET
            self.FakeMIDImsg()
            RECT_OFFSET += 1
            top = channels.channelNumber()
            left = RECT_OFFSET*16
            ui.crDisplayRect(left,top,16,1,1000)
            self._navigation.BarRefresh()
        elif SEQ_MODE == 0 :
            if self._is_pressed(event):
                transport.continuousMove(1, SS_START)
                self._navigation.FastForwardRefresh()
            else:
                transport.continuousMove(1, SS_STOP)
                self._navigation.FastForwardRefresh()
        
    
    def RewindORprevBar(self, event) :
        if SEQ_MODE == 1 and event.controlVal == 127 :
            global RECT_OFFSET
            self.FakeMIDImsg()
            RECT_OFFSET -= 1
            if RECT_OFFSET < 0 :
                RECT_OFFSET = 0
            top = channels.channelNumber()
            left = RECT_OFFSET*16
            ui.crDisplayRect(left,top,16,1,1000)
            self._navigation.BarRefresh()
        elif SEQ_MODE == 0 :
            if self._is_pressed(event):
                transport.continuousMove(-1, SS_START)
                self._navigation.RewindRefresh()
            else:
                transport.continuousMove(-1, SS_STOP)
                self._navigation.RewindRefresh()
            
    
    
    def Loop(self, event) :
        transport.globalTransport(midi.FPT_LoopRecord,1)
        self._navigation.LoopRefresh()
    

    def Cut(self, event) :
        self._show_and_focus(midi.widChannelRack)
        ui.cut()
        self._navigation.CutRefresh()
        
    def Undo(self, event) :
        transport.globalTransport(midi.FPT_Undo, midi.FPT_Undo, event.pmeFlags)
        self._navigation.UndoRefresh()

    def Overdub(self, event) :
        transport.globalTransport(midi.FPT_Overdub,1)
        self._navigation.OverdubRefresh()
    

    def SetClick(self, event) :
        transport.globalTransport(midi.FPT_Metronome,1)
        self._navigation.MetronomeRefresh()
          
      
    def SoloChannel(self, event) :
        if ui.getFocused(WidChannelRack) :
            channels.soloChannel(channels.channelNumber())
        elif ui.getFocused(WidMixer) :
            mixer.soloTrack(mixer.trackNumber())
        self.FakeMIDImsg()
     
     
    def MuteChannel(self, event) :
        if ui.getFocused(WidChannelRack) :
            channels.muteChannel(channels.channelNumber())
        elif ui.getFocused(WidMixer) :
            mixer.muteTrack(mixer.trackNumber())
        self.FakeMIDImsg()
      
      
    def TapTempo(self, event) :
        transport.globalTransport(midi.FPT_TapTempo,1)
        self._navigation.TapTempoRefresh()
       
       
    def SnapMode(self, event) :
        ui.snapMode(1)
        self._navigation.SnapModeRefresh()
    
 
    def SetVolumeTrack(self, event) :
        if MIXER_MODE == 1 :
            if event.status == 232 and event.midiId == 224  :
                event.data1 = 1
                event.midiId = midi.MIDI_CONTROLCHANGE
                AKLmk2.SetVolumeTrack(event) 
                value = round(mixer.getTrackVolume(0)*100)
                perc = str(value)
                self._navigation.VolumeMixerRefresh(event, perc)
            else :
                event.data1 = 2 + event.status - event.midiId
                event.midiId = midi.MIDI_CONTROLCHANGE
                track = (event.controlNum - 1) + (8*AKLmk2.MX_OFFSET)
                if track < 126 :
                    AKLmk2.SetVolumeTrack(event)
                    value = round(mixer.getTrackVolume(event.data1 - 1 + (8*AKLmk2.MX_OFFSET)) * 100)
                    perc = str(value)
                    self._navigation.VolumeMixerRefresh(event, perc)
        else :
            if event.status != 232 :
                self.Plugin(event, clef = event.status)
                self._navigation.NoPlugin()
            else :
                value = event.data2/127
                mixer.setTrackVolume(mixer.trackNumber(),0.8*value)
                value = round(mixer.getTrackVolume(mixer.trackNumber())*100)
                perc = str(value)
                self._navigation.VolumeChRefresh(perc)
                
            
    def SetPanTrack(self, event) :
        
        if EDIT_MODE == 1 :
            global SEQ_PARAM
            global INDEX_PRESSED
            INDEX_PRESSED = []    
            for i in range(4) :
                for j in range(4) :
                    if STATE_MATRIX[i][j] == 1 :
                        INDEX_PRESSED += [4*i+j]
            KLmk2SQP.Param(event)
            self.FakeMIDImsg()
            SEQ_PARAM = 1
        
        else :
            if MIXER_MODE == 1 :
                if event.controlNum == 24 :
                    AKLmk2.SetPanTrack(event)
                    value = round(mixer.getTrackPan(0) * 100)
                    perc = str(value)
                    self._navigation.PanMixerRefresh(event, perc)
                else :
                    track = (event.controlNum - 15) + (8*AKLmk2.MX_OFFSET)
                    AKLmk2.SetPanTrack(event)
                    value = round(mixer.getTrackPan(track) * 100)
                    perc = str(value)
                    self._navigation.PanMixerRefresh(event, perc)
            else :
                if event.controlNum != 24 :
                    self.Plugin(event, clef = event.controlNum)
                    self._navigation.NoPlugin()
                else :
                    data = 0
                    if event.data2 > 0x40 : data = -1
                    elif event.data2 < 0x40 : data = 1
                    mixer.setTrackPan(mixer.trackNumber(),mixer.getTrackPan(mixer.trackNumber())+ (data/20))
                    value = round(mixer.getTrackPan(mixer.trackNumber()) * 100)
                    perc = str(value)
                    self._navigation.PanChRefresh(perc)

  
  
    # SEQUENCER

   
   
    def PressSequencer(self, event) :
        global SEQ_PARAM
        SEQ_PARAM = 0
        if channels.isGraphEditorVisible() :
            SEQ_PARAM = 1
        self.HoldBit(event) 
        
            
    def HoldBit(self, event) :
        global STATE_MATRIX
        global EDIT_MODE
        EDIT_MODE = 1
        
        # State Matrix Init
        BIT_MAP = {
        '36':0,
        '37':1,
        '38':2,
        '39':3,
        '40':4,
        '41':5,
        '42':6,
        '43':7,
        '44':8,
        '45':9,
        '46':10,
        '47':11,
        '48':12,
        '49':13,
        '50':14,
        '51':15
        }
        cle = str(event.controlNum)
        STATE_MATRIX[BIT_MAP.get(cle)//4][BIT_MAP.get(cle)%4] = 1


        
    def ReleaseBit(self, event) :
        global STATE_MATRIX
        global EDIT_MODE
        
        # State Matrix Init
        EDIT_MODE = 0
        BIT_MAP = {
        '36':0,
        '37':1,
        '38':2,
        '39':3,
        '40':4,
        '41':5,
        '42':6,
        '43':7,
        '44':8,
        '45':9,
        '46':10,
        '47':11,
        '48':12,
        '49':13,
        '50':14,
        '51':15
        }
        cle = str(event.controlNum)
        STATE_MATRIX[BIT_MAP.get(cle)//4][BIT_MAP.get(cle)%4] = 0
                
        # While at least one pad is pressed, stay in edit mode
        hold_num = 0
        for i in STATE_MATRIX :
            for j in i :
                if j == 1 :
                    hold_num += 1
        if hold_num != 0 :
            EDIT_MODE = 1
        else :
            channels.closeGraphEditor(1)
        
        # If a parameter changed, let the pad on
        step = event.controlNum - 36
        if SEQ_PARAM == 1 :
            return
        else :    
            if channels.getGridBit(channels.channelNumber(),step+(16*RECT_OFFSET)) == 0 :
                channels.setGridBit(channels.channelNumber(),step+(16*RECT_OFFSET),1)
                LED_MATRIX[step//4][step%4] = 1
            else :
                channels.setGridBit(channels.channelNumber(),step+(16*RECT_OFFSET),0)
                LED_MATRIX[step//4][step%4] = 0    
        

    # UTILITY
   
   
        
    def FakeMIDImsg(self) :
        transport.globalTransport(midi.FPT_Punch,1)

        
  
  
        
    
        