"""Read category ownership and default values without invoking default setters."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('change',['valid','wrong_category','missing_registry','missing_default','extra','overflow'])
def test_category_ownership_and_missing_default_are_visible_without_setters(change):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SettingsObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal change='+json.dumps(change)+'''
    local category,other={},{}
    local function setting(variable,value,default)
        return {GetVariable=function() return variable end,GetValue=function() return value end,
            GetDefaultValue=function() return default end,
            SetValueToDefault=function() error('observer invoked setter') end}
    end
    local mode=setting('colorblindMode',false,false)
    local simulator=setting('colorblindSimulator',0,0)
    local strength=setting('colorblindWeaknessFactor',.5,change~='missing_default' and .5 or nil)
    local panel={settings={[mode]=category,[simulator]=category,[strength]=category},
        GetSetting=function(self,variable) assert(variable=='colorblindMode');return mode end}
    if change=='extra' then panel.settings[setting('extra',1,2)]=category
    elseif change=='overflow' then
        for i=1,9 do panel.settings[setting('extra'..i,1,2)]=category end
    elseif change=='missing_registry' then panel.settings=nil end
    local rows=Client442ReadColorblindDefaults(panel,change=='wrong_category' and other or category)
    if change=='wrong_category' or change=='missing_registry' then assert(rows==nil)
    elseif change=='overflow' then assert(rows.invalid==true)
    else
        assert(#rows==(change=='extra' and 4 or 3))
        local seen={};for _,row in ipairs(rows) do seen[row.variable]=row end
        assert(seen.colorblindMode.value==false and seen.colorblindMode.default==false)
        assert(seen.colorblindWeaknessFactor.default==(change~='missing_default' and .5 or nil))
    end
    local button={};panel.GetSettingsList=function() return {Header={DefaultsButton=button}} end
    SettingsPanel=panel
    assert(Client442IsSettingsDefaultsButton(button))
    assert(not Client442IsSettingsDefaultsButton({}) and not Client442IsSettingsDefaultsButton(nil))
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
