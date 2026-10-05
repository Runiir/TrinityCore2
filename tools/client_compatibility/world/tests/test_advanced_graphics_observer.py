"""Attribute only stock quality widgets bound to their initializer's setting."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('role',['base','raid'])
@pytest.mark.parametrize('control',['Slider','Back','Forward'])
def test_quality_widget_identity_and_setting_are_read_without_setters(role,control):
    check(role,control,'valid')


@pytest.mark.parametrize('failure',['unrelated','wrong_variable','no_initializer','no_setting','setter_only','too_deep',
    'initializer_type','data_type'])
def test_unattributed_or_unbound_quality_control_is_not_exposed(failure):
    check('base','Back',failure)


def check(role,control,change):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SettingsObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal role,key,change='+','.join(map(json.dumps,[role,control,change]))+'''
    local variable=role=='base' and 'PROXY_GRAPHICS_QUALITY' or 'PROXY_RAID_GRAPHICS_QUALITY'
    local reads=0
    local setting={GetVariable=function() return variable end,
        GetValue=function() reads=reads+1;return 1 end,GetName=function() return 'Graphics Quality' end,
        SetValue=function() error('observer called a setter') end}
    local steppers={Slider={},Back={},Forward={}}
    local quality={SliderWithSteppers=steppers}
    local container={GraphicsQuality=quality}
    local data=role=='base' and {settings={graphicsQuality=setting}} or {raidSettings={raidGraphicsQuality=setting}}
    local section={GetElementData=function() return {data=data} end}
    section[role=='base' and 'BaseQualityControls' or 'RaidQualityControls']=container
    for _,widget in pairs(steppers) do widget.GetParent=function() return section end end
    local widget=steppers[key]
    if change=='unrelated' then widget={GetParent=function() return section end}
    elseif change=='wrong_variable' then variable='PROXY_OTHER'
    elseif change=='no_initializer' then section.GetElementData=nil
    elseif change=='no_setting' then data.settings={}
    elseif change=='setter_only' then setting.GetVariable=nil
    elseif change=='initializer_type' then section.GetElementData=function() return true end
    elseif change=='data_type' then data=true
    elseif change=='too_deep' then
        local parent=section
        for i=1,8 do local nextParent=parent;parent={GetParent=function() return nextParent end} end
        widget.GetParent=function() return parent end
    end
    local result=Client442ObserveAdvancedQualityControl(widget)
    if change=='valid' then
        assert(result.variable==variable and result.value==1 and result.name=='Graphics Quality')
        assert(result.role==role and result.control==key and reads==1)
    else assert(result==nil and reads==0) end
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)


def test_preset_map_uses_installed_read_only_getter_and_particle_minimum():
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SettingsObservation.lua'
    program='dofile('+json.dumps(str(source))+''')
    local reads=0
    GetCVar=function(name) return '1' end
    Settings={GetValue=function(name) return name=='PROXY_GRAPHICS_QUALITY' and 1 or nil end,
        SetValue=function() error('observer called a setter') end}
    GetGraphicsCVarValueForQualityLevel=function(name,quality,raid)
        assert(name~='graphicsQuality' and quality==0 and raid==false)
        reads=reads+1;return 0
    end
    local result=Client442ObserveSettings()
    assert(reads==10 and result.lower_graphics_quality==0)
    local count=0
    for key,value in pairs(result.lower_graphics_values) do
        assert(value==(key=='PROXY_PARTICLE_DENSITY' and 1 or 0));count=count+1
    end
    assert(count==10 and result.values.PROXY_GRAPHICS_QUALITY==1)
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
