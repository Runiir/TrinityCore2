"""Read active window size through the installed video getter, never pending proxies."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('change',['valid','fullscreen','missing_api','missing_mode','invalid_size','missing_monitor'])
def test_active_size_requires_exact_public_native_monitor_and_mode(change):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SettingsObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal change='+json.dumps(change)+'''
    local cvars={gxMonitor='0',gxMaximize=change=='fullscreen' and '1' or '0'}
    local reads=0
    GetScreenWidth=function() return 1280 end
    GetScreenHeight=function() return 720 end
    C_VideoOptions={GetCurrentGameWindowSize=function(monitor,fullscreen)
        assert(monitor==0 and fullscreen==(change=='fullscreen'));reads=reads+1
        return {x=change=='invalid_size' and 0 or 1280,y=720}
    end,SetGameWindowSize=function() error('observer called setter') end}
    if change=='missing_api' then C_VideoOptions=nil
    elseif change=='missing_mode' then cvars.gxMaximize=nil
    elseif change=='missing_monitor' then cvars.gxMonitor=nil end
    local result=Client442ReadDisplayState(cvars)
    assert(result.screen_width==1280 and result.screen_height==720)
    if change=='valid' or change=='fullscreen' then
        assert(result.window_size.width==1280 and result.window_size.height==720 and reads==1)
    else
        assert(result.window_size==nil)
        assert(reads==(change=='invalid_size' and 1 or 0))
    end
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
