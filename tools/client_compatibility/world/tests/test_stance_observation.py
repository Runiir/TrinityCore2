"""Read the actual stance observer's public tuple, button state and scaled geometry."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_stance_metadata_uses_public_spell_and_button_without_input():
    lua=shutil.which('lua')
    if lua is None:pytest.skip('Lua interpreter is unavailable')
    module=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ActionBarObservation.lua'
    script="""
function Client442HookPerformanceTooltip() end
function Client442PerformanceTooltipEvent() return nil end
function GetNumShapeshiftForms() return 2 end
function GetShapeshiftFormInfo(i) return 'icon',i==1,true,i==1 and 2457 or 71 end
function GetPhysicalScreenSize() return 1280,720 end
function UnitPower() return 0 end
function UnitPowerType() return 1 end
function CastShapeshiftForm() error('observer must not cast') end
StanceButton1={IsVisible=function() return true end,GetChecked=function() return true end,
    IsEnabled=function() return true end,GetCenter=function() return 100,50 end,
    GetEffectiveScale=function() return 2 end}
dofile(arg[1])
local result=Client442ObserveActionBars()
assert(result.power==0 and result.power_type==1)
local row=result.forms[1]
assert(row.spell==2457 and row.active and row.checked and row.visible and row.enabled)
assert(row.x==math.floor(200/1280*65535) and row.y==math.floor((1-100/720)*65535))
row=result.forms[2]
assert(row.spell==71 and not row.active and row.x==nil and row.y==nil)
"""
    subprocess.run([lua,'-',str(module)],input=script,text=True,check=True,capture_output=True,timeout=3)
