import transport
import ui
import channels
import patterns
import mixer
import arrangement
import playlist
import KLTProcess as KLmk2Pr
import KLTCrossKeyboard as AKLmk2

# This class allows FL Studio to send hint messages to Arturia KeyLab's screen

WidMixer = 0
WidChannelRack = 1
WidPlaylist = 2
WidBrowser = 4
WidPlugin = 5

class NavigationMode:
    def __init__(self, paged_display, display_ms= 1000):
        self._paged_display = paged_display
        self._display_ms = 1000
        self._modes = []
        self._active_index = 0      
        
        
    def VolumeChRefresh(self, value) :
        track = str(mixer.trackNumber())
        self._paged_display.SetPageLines('Volume', 
                                        line1= 'Volume - ' + track, 
                                        line2= value + '%'
                                        )
        self._paged_display.SetActivePage('Volume', expires=self._display_ms)


        
    def PanChRefresh(self, value) :
        track = str(mixer.trackNumber())
        self._paged_display.SetPageLines('Pan',
                                        line1= 'Pan - ' + track,
                                        line2= value + '%'
                                        )
        self._paged_display.SetActivePage('Pan', expires=self._display_ms)
    
    
    def NoPlugin(self) :
        if not ui.getFocused(WidPlugin) :
            self._paged_display.SetPageLines('NoPlugin', 
                                            line1= 'No Plugin', 
                                            line2= 'Focused'
                                            )
            self._paged_display.SetActivePage('NoPlugin', expires=self._display_ms)
  
  
    def VolumeMixerRefresh(self, event, value) :
        track = str((event.controlNum - 1) + (8*AKLmk2.MX_OFFSET))
        self._paged_display.SetPageLines('Volume',
                                        line1= 'Volume - ' + track,
                                        line2= value + '%'
                                        )
        self._paged_display.SetActivePage('Volume', expires=self._display_ms)

        
    def PanMixerRefresh(self, event, value) :
        track = str((event.controlNum - 15) + (8*AKLmk2.MX_OFFSET))
        self._paged_display.SetPageLines('Pan',
                                        line1= 'Pan - ' + track,
                                        line2= value + '%'
                                        )
        self._paged_display.SetActivePage('Pan', expires=self._display_ms)

        
    def PluginRefresh(self, param, value) :
        if (param, value) != ("","") :
            self._paged_display.SetPageLines('Param', 
                                            line1= param, 
                                            line2= value + "%"
                                            )
            self._paged_display.SetActivePage('Param', expires=self._display_ms)
        else :
            self._paged_display.SetPageLines('Param2', 
                                            line1= "This control" ,
                                            line2= "is not mapped !"
                                            )
            self._paged_display.SetActivePage('Param2', expires=self._display_ms)
                
        
    def PlayRefresh(self) :
        if transport.isPlaying() != 0 :
            self._paged_display.SetPageLines('Play',
                                            line1= 'Play',
                                            line2= ''
                                            )
            self._paged_display.SetActivePage('Play', expires=self._display_ms)
        else :
            self._paged_display.SetPageLines('Pause',
                                            line1= 'Pause',
                                            line2= ''
                                            )
            self._paged_display.SetActivePage('Pause', expires=self._display_ms)
        
        
    def StopRefresh(self) :
        self._paged_display.SetPageLines('Stop', 
                                        line1= 'Stop',
                                        line2= ''
                                        )
        self._paged_display.SetActivePage('Stop', expires=self._display_ms)
    
    
    def RecordRefresh(self) :
        if transport.isRecording() :
            self._paged_display.SetPageLines('RecordOn',
                                            line1= 'Record',
                                            line2= 'ON'
                                            )
            self._paged_display.SetActivePage('RecordOn', expires=self._display_ms)
        else :
            self._paged_display.SetPageLines('RecordOff', 
                                            line1= 'Record',
                                            line2= 'OFF'
                                            )
            self._paged_display.SetActivePage('RecordOff', expires=self._display_ms)

            
    def RewindRefresh(self) :
        bar = str(playlist.getVisTimeBar())
        step = str(playlist.getVisTimeStep())
        self._paged_display.SetPageLines('Rewind', 
                                        line1= 'Rewind <<', 
                                        line2= '['+ bar + ':' + step + ']'
                                        )
        self._paged_display.SetActivePage('Rewind', expires=self._display_ms)
 
 
    def FastForwardRefresh(self) :
        bar = str(playlist.getVisTimeBar())
        step = str(playlist.getVisTimeStep())
        self._paged_display.SetPageLines('FastForward',
                                        line1= 'FastForward >>', 
                                        line2= '['+ bar + ':' + step + ']'
                                        )
        self._paged_display.SetActivePage('FastForward', expires=self._display_ms)
            
            
    def LoopRefresh(self) :
        if ui.isLoopRecEnabled() :
            self._paged_display.SetPageLines('LoopOn', 
                                            line1= 'Loop Mode',
                                            line2= 'ON'
                                            )
            self._paged_display.SetActivePage('LoopOn', expires=self._display_ms)
        else :
            self._paged_display.SetPageLines('LoopOff',
                                            line1= 'Loop Mode',
                                            line2= 'OFF'                             
                                            )
            self._paged_display.SetActivePage('LoopOff', expires=self._display_ms)
 
 
    def OverdubRefresh(self) :
        self._paged_display.SetPageLines('Overdub',
                                        line1= 'Overdub Mode', 
                                        line2= ''
                                        )
        self._paged_display.SetActivePage('Overdub', expires=self._display_ms)
   
            
    def CutRefresh(self) :
        channelnum = str(channels.channelNumber() + 1)
        patternnum = str(patterns.patternNumber())
        self._paged_display.SetPageLines('Cut',
                                        line1= 'Pattern ' + patternnum,
                                        line2= 'Chan ' + channelnum + ' CLEARED'
                                        )
        self._paged_display.SetActivePage('Cut', expires=self._display_ms)
   
   
    def UndoRefresh(self) :
        self._paged_display.SetPageLines('Undo', 
                                        line1= 'Undo', 
                                        line2= ''
                                        )
        self._paged_display.SetActivePage('Undo', expires=self._display_ms)
        
        
    def MetronomeRefresh(self) :
        if ui.isMetronomeEnabled() :
            self._paged_display.SetPageLines('MetroOn',
                                            line1= 'Metronome', 
                                            line2= 'ON'
                                        )
            self._paged_display.SetActivePage('MetroOn', expires=self._display_ms)
        else :
            self._paged_display.SetPageLines('MetroOff',
                                            line1= 'Metronome',
                                            line2= 'OFF'
                                            )
            self._paged_display.SetActivePage('MetroOff', expires=self._display_ms)

            
    def TapTempoRefresh(self) :
        tempo = str(mixer.getCurrentTempo(1))
        self._paged_display.SetPageLines('Tempo',
                                        line1= 'Tempo',
                                        line2= tempo + ' BPM'
                                        )
        self._paged_display.SetActivePage('Tempo', expires=self._display_ms)
        
        
    def SnapModeRefresh(self) :
        SNAP_MODE = {'0' : 'Line',
                     '1' : 'Cell',
                     '3' : 'None',
                     '4' : '1/6 Step',
                     '5' : '1/4 Step',
                     '6' : '1/3 Step',
                     '7' : '1/2 Step', 
                     '8' : 'Step',
                     '9' : '1/6 Beat',
                     '10' : '1/4 Beat',
                     '11' : '1/3 Step',
                     '12' : '1/2 Beat',
                     '13' : 'Beat',
                     '14' : 'Bar'}
        cle = str(ui.getSnapMode())
        snap = SNAP_MODE.get(cle)
        self._paged_display.SetPageLines('Snap',
                                        line1= 'Snap Mode',
                                        line2= snap
                                        )
        self._paged_display.SetActivePage('Snap', expires=self._display_ms)
        
        
    def DrumSeqToggleRefresh(self) :
        if KLmk2Pr.SEQ_MODE == 0 :
            self._paged_display.SetPageLines('DrumMode',
                                            line1= 'DRUM MODE',
                                            line2= ''
                                            )
            self._paged_display.SetActivePage('DrumMode', expires=self._display_ms)
        else :
            self._paged_display.SetPageLines('SeqMode', 
                                            line1= 'SEQUENCER MODE',
                                            line2= ''
                                            )
            self._paged_display.SetActivePage('SeqMode', expires=self._display_ms)
            
    
    def MixerToggleRefresh(self) :
        if KLmk2Pr.MIXER_MODE == 0 :
            self._paged_display.SetPageLines('CR',
                                            line1= 'CHANNEL RACK',
                                            line2= ''
                                            )
            self._paged_display.SetActivePage('CR', expires=self._display_ms)
        else :
            self._paged_display.SetPageLines('Mixer',
                                            line1= 'MIXER',
                                            line2= ''
                                            )
            self._paged_display.SetActivePage('Mixer', expires=self._display_ms)
            
    
    def BarRefresh(self) :
        bar = str(KLmk2Pr.RECT_OFFSET + 1)
        stepinf = str(KLmk2Pr.RECT_OFFSET*16)
        stepsup = str(16 + KLmk2Pr.RECT_OFFSET*16)
        self._paged_display.SetPageLines('Bar', 
                                        line1= 'Bar : ' + bar ,
                                        line2= 'Step : ' + stepinf + ' / ' + stepsup
                                        )
        self._paged_display.SetActivePage('Bar', expires=self._display_ms)
            
            
    def BrowserRefresh(self) :
        self._paged_display.SetPageLines('Browser',
                                        line1= 'BROWSER',
                                        line2= ''
                                        )
        self._paged_display.SetActivePage('Browser', expires=self._display_ms)
        
        
    def ChannelRackRefresh(self) :
        self._paged_display.SetPageLines('ChannelRack',
                                        line1= 'CHANNEL RACK',
                                        line2= ''
                                        )
        self._paged_display.SetActivePage('ChannelRack', expires=self._display_ms)

        
    def BankChanRefresh(self) :
        bankinf = str(1 + AKLmk2.CH_OFFSET*8)
        banksup = str(8 + AKLmk2.CH_OFFSET*8)
        self._paged_display.SetPageLines('Channels',
                                        line1= 'Channels',
                                        line2= bankinf + ' - ' + banksup
                                        )
        self._paged_display.SetActivePage('Channels', expires=self._display_ms)
    
    def BankMixRefresh(self) :
        bankinf = str(1 + AKLmk2.MX_OFFSET*8)
        banksup = str(8 + AKLmk2.MX_OFFSET*8)
        self._paged_display.SetPageLines('Tracks',
                                        line1= 'Tracks', 
                                        line2= bankinf + ' - ' + banksup
                                        )
        self._paged_display.SetActivePage('Tracks', expires=self._display_ms)
        
    def HintRefresh(self, string) :
        for i in range(len(string)) :
            if (ord(string[i]) not in range(0,127)) :
                str1 = string[0:i]
                str2 = string[i+1::]
                string = str1 + '?' + str2                
        if ui.isInPopupMenu() :
            LABELS = {
                    "Send to selected channel or focused plugin" : "Replace",
                    "Open in new channel" : "New Channel",
                    "Add to plugin database (flag as favorite)" : "Like",
                    "Open Windows shell menu for this file" : "Windows menu",
                    "Send file to the trash bin" : "Delete file"
                    }       
            self._paged_display.SetPageLines('Hintpopup',
                                        line1= 'Browser',
                                        line2= LABELS.get(ui.getHintMsg())
                                        )
            self._paged_display.SetActivePage('Hintpopup', expires=3000)
        else :
            self._paged_display.SetPageLines('Hint',
                                            line1= 'Browser',
                                            line2= string
                                            )
            self._paged_display.SetActivePage('Hint', expires=3000)

            
    def PressRefresh(self) :
        self._paged_display.SetPageLines('Press',
                                        line1= 'Browser',
                                        line2= "Select an option"
                                        )
        self._paged_display.SetActivePage('Press', expires=3000)
        
    
    def ArmRefresh(self, track) :
        if mixer.isTrackArmed(track) :
            self._paged_display.SetPageLines('Arm',
                                            line1= 'Track ' + str(track),
                                            line2= "Armed"
                                            )
            self._paged_display.SetActivePage('Arm', expires=self._display_ms)
        else :
            self._paged_display.SetPageLines('UnArm',
                                            line1= 'Track ' + str(track),
                                            line2= "Not Armed"
                                            )
            self._paged_display.SetActivePage('UnArm', expires=self._display_ms)