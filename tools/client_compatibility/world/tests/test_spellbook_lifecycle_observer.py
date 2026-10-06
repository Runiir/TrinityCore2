"""Lifecycle observation is bounded and leaves every stock script intact."""
import json,shutil,subprocess
from pathlib import Path
import pytest


def test_flyout_hooks_preserve_stock_scripts_and_bound_event_history():
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SpellBookLifecycleObservation.lua'
    program='''
    local function forbidden() error('observer invoked a gameplay setter') end
    local listener,registered={},{}
    CreateFrame=function(kind) assert(kind=='Frame');return listener end
    listener.RegisterEvent=function(_,event) registered[event]=true end
    listener.SetScript=function(_,kind,fn) assert(kind=='OnEvent');listener.event=fn end
    local parent={GetName=function() return 'SpellButton1' end}
    local stock={}
    local hooks,shown,stockHideCalls={},true,0
    SpellBookFrame={IsVisible=function() return true end}
    SpellFlyout={GetName=function() return 'SpellFlyout' end,GetParent=function() return parent end,
        IsVisible=function() return shown end,SetScript=forbidden,Hide=forbidden,Show=forbidden,
        Toggle=forbidden,HookScript=function(_,kind,fn) assert(not hooks[kind]);hooks[kind]=fn end}
    stock.OnHide=function() stockHideCalls=stockHideCalls+1 end
    GetTime=function() return 42 end
    debugstack=function(start,count,tail) assert(start==2 and count==6 and tail==0);return string.rep('s',1000) end
    CastSpellByID=forbidden;CastSpell=forbidden
    '''+'dofile('+json.dumps(str(source))+')\n'+'''
    assert(registered.SPELLS_CHANGED and registered.UPDATE_SHAPESHIFT_FORM and registered.ACTIONBAR_PAGE_CHANGED)
    assert(#Client442ObserveSpellBookLifecycle().events==0)
    Client442ObserveSpellBookLifecycle() -- hooks install only once
    hooks.OnShow(SpellFlyout)
    for i=1,12 do listener.event(listener,'SPELLS_CHANGED') end
    shown=false;stock.OnHide();hooks.OnHide(SpellFlyout)
    local rows=Client442ObserveSpellBookLifecycle()
    assert(#rows.events==4 and #rows.transitions==2 and stockHideCalls==1)
    assert(rows.events[4].kind=='SPELLS_CHANGED' and rows.transitions[2].kind=='flyout_hide')
    assert(rows.transitions[2].parent=='SpellButton1' and rows.transitions[2].visible==false and #rows.transitions[2].stack==700)
    for i=1,12 do listener.event(listener,'UPDATE_SHAPESHIFT_FORM') end
    assert(rows.transitions[2].kind=='flyout_hide' and rows.events[4].kind=='UPDATE_SHAPESHIFT_FORM')
    SpellBookFrame.IsVisible=function() return false end
    listener.event(listener,'ACTIONBAR_PAGE_CHANGED')
    assert(#rows.events==4 and rows.transitions[2].kind=='flyout_hide')
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
