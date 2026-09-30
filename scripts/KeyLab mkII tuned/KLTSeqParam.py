import channels
import patterns
import KLTProcess as KLmk2Pr
import KLTCrossKeyboard as AKLmk2      # KLT F-13: sel_channel(), rel_ticks()

# This script contains fonctions that modify Bit parameter in Step Sequencer

# KLT F-11: stock's one accumulator (ABSOLUTE_VALUE) is gone, see STEP_PARAMS
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

# KLT F-11: encoder CC -> (FL step parameter, lowest, highest, default when FL cannot say, change per encoder tick).
# The ranges are the documented ones (FL API stubs, channels.setStepParameterByIndex); stock kept ONE accumulator
# (0..127, seeded 64) for every step and parameter, wrote MOD Y as twice the accumulator (up to 254), and never wrote
# fine pitch above 127 (range 0..240) or the documented Shift parameter (encoder 8, guide p.15 Fig.31).
SHIFT_MAX_TICKS = 24        # "0 - PPQN / 4" with FL's default PPQN of 96
STEP_PARAMS = {
        16 : (0, 0, 127, 60, 1),
        17 : (1, 0, 127, 100, 3),
        18 : (2, 0, 127, 64, 3),
        19 : (3, 0, 240, 120, 3),
        20 : (4, 0, 127, 64, 3),
        21 : (5, 0, 127, 64, 3),
        22 : (6, 0, 127, 64, 3),
        23 : (7, 0, SHIFT_MAX_TICKS, 0, 1)
        }


def Param(event) :
    channel = AKLmk2.sel_channel()      # KLT F-13, O-08: group-relative index; -1 = empty rack
    pressed = KLmk2Pr.INDEX_PRESSED
    if channel < 0 or not pressed :     # KLT F-11: edit mode with no pad held made min([]) raise
        return
    pattern = patterns.patternNumber()
    center = min(pressed)+(16*KLmk2Pr.RECT_OFFSET)

    global PAGE
    temp = event.controlNum
    if PAGE != temp :
        channels.closeGraphEditor(1)

    spec = STEP_PARAMS.get(temp)
    if spec is None :
        return                          # encoder 9: nothing to edit (as before, it only closes the graph editor)
    param, low, high, default, per_tick = spec
    ticks = AKLmk2.rel_ticks(event.data2)   # KLT F-10, F-11: clockwise raises every parameter, pitch included (stock inverted it)
    if ticks == 0 :
        return

    for i in pressed :
        step = i+(16*KLmk2Pr.RECT_OFFSET)
        # KLT F-11: start from the step's own value (stock: one global accumulator seeded at 64), stay inside the range
        value = channels.getCurrentStepParam(channel, step, param)
        if value < 0 :
            value = default             # FL could not answer (-1)
        value = min(high, max(low, value + ticks*per_tick))
        channels.setStepParameterByIndex(channel, pattern, step, param, value, 0)

    if temp == PAGE_MAP["PITCH"] :
        channels.showGraphEditor(0,0,center,channel,0) # PITCH
        PAGE = temp
    elif not channels.isGraphEditorVisible() :
        # KLT F-11: the graph editor is shown / updated once per event, not once per held step
        channels.showGraphEditor(1,param,center,channel,0)  # VELOCITY .. MOD Y, SHIFT
        PAGE = temp
    else :
        # KLT F-11: the six unrolled per-parameter branches and RelativeToAbsolute() of stock are STEP_PARAMS and Param() above
        channels.updateGraphEditor()
