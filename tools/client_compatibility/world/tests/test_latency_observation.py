"""The stock tooltip event must retain both latency returns and expose failures."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_stock_tooltip_event_retains_home_world_and_never_invents_missing_values():
    lua=shutil.which('lua')
    if lua is None:pytest.skip('Lua interpreter is unavailable')
    module=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/TooltipObservation.lua'
    script="""
local eventHook
function hooksecurefunc(name,callback)
    assert(name=='MainMenuBarPerformanceBarFrame_OnEnter')
    assert(eventHook==nil)
    eventHook=callback
end
function MainMenuBarPerformanceBarFrame_OnEnter() end
function GetNetStats() return 1,2,23,47 end
function GetTime() return 123 end
function SetCVar() error('observation must never call a setter') end
MAINMENUBAR_LATENCY_LABEL='Latency: %d home, %d world'
dofile(arg[1])
Client442HookPerformanceTooltip()
Client442HookPerformanceTooltip()
eventHook({GetName=function() return 'MainMenuMicroButton' end})
local event=Client442ObserveTooltip().performance_event
assert(event.owner=='MainMenuMicroButton')
assert(event.home==23 and event.world==47)
assert(event.expected_line=='Latency: 23 home, 47 world')
GetNetStats=function() error('API unavailable') end
eventHook({GetName=function() return 'MainMenuMicroButton' end})
event=Client442ObserveTooltip().performance_event
assert(event.home==nil and event.world==nil and event.expected_line==nil)
"""
    subprocess.run([lua,'-',str(module)],input=script,text=True,check=True,capture_output=True,timeout=3)
