"""Menu inspection must click the current owned target frame, using passive facts."""
import json,shutil,subprocess
from pathlib import Path
import pytest
from tools.client_compatibility.interaction_pet_target import menu_target


@pytest.mark.parametrize('change',('none','name','unit','guid','visible','enabled','missing_x','outside_y','string_x'))
def test_menu_target_refuses_foreign_hidden_or_unbounded_frame(change):
    c={'name':'TargetFrame','unit':'target','guid':'owned-imp','x':20000,'y':4000,'visible':True,'enabled':True}
    if change in ('name','unit','guid'):c[change]='different'
    elif change in ('visible','enabled'):c[change]=False
    elif change=='missing_x':c.pop('x')
    elif change=='outside_y':c['y']=65535
    elif change=='string_x':c['x']='20000'
    if change=='none':assert menu_target(c,'owned-imp')==[391,44]
    else:
        with pytest.raises(RuntimeError):menu_target(c,'owned-imp')


@pytest.mark.parametrize('change',('none','hidden','foreign_unit','disabled','no_guid','outside'))
def test_passive_target_frame_reads_identity_and_scaled_point_without_input(change):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/TargetFrameObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal change='+json.dumps(change)+'''
    local function forbidden() error('passive frame probe invoked an action') end
    PetDismiss=forbidden;SetCVar=forbidden;TargetUnit=forbidden;CreateFrame=forbidden
    UnitGUID=function(unit) assert(unit=='target');return change~='no_guid' and 'owned-imp' or nil end
    UIParent={GetEffectiveScale=function() return .8 end}
    GetScreenWidth=function() return 1600 end;GetScreenHeight=function() return 900 end
    TargetFrame={Click=forbidden,SetAttribute=forbidden,
        IsVisible=function() return change~='hidden' end,IsMouseEnabled=function() return true end,
        IsEnabled=function() return change~='disabled' end,
        GetAttribute=function(_,key) assert(key=='unit');return change=='foreign_unit' and 'player' or 'target' end,
        GetCenter=function() return change=='outside' and 2000 or 320,650 end,
        GetEffectiveScale=function() return 1 end,GetName=function() return 'TargetFrame' end}
    local control=Client442ObserveTargetFrame()
    if change=='none' then
        assert(control.name=='TargetFrame' and control.unit=='target' and control.guid=='owned-imp')
        assert(control.visible and control.enabled and control.x==math.floor(320/1280*65535))
        assert(control.y==math.floor((1-650/720)*65535))
    else assert(control==nil) end
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
