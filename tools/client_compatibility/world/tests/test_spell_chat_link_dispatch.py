"""The installed stock click repair must never cast a chat-link click."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_chatlink_routes_once_and_normal_click_preserves_original_handler():
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter is unavailable')
    source=Path(__file__).resolve().parents[2]/'client_addon/Client442Compatibility/SpellChatLink.lua'
    script=r'''
local source=arg[1]
local handler,modified=false,false
local casts,links={},{}
Client442CompatibilityStatus={}
GetBuildInfo=function() return '4.4.2','60895' end
IsModifiedClick=function(kind) assert(kind=='CHATLINK');return modified end
CreateFrame=function(_,_,_,template)
    if template then assert(template=='SecureHandlerBaseTemplate');return {} end
    return {RegisterEvent=function() end,SetScript=function(_,_,fn) handler=fn end}
end
SecureHandlerWrapScript=function(frame,kind,header,body)
    assert(kind=='OnClick' and type(header)=='table')
    local before=assert((loadstring or load)('return function(self,button) '..body..' end'))()
    frame.CallMethod=function(self,method,button) self[method](self,button) end
    frame.click=function(self,button,...)
        if before(self,button)==false then return end
        return self.original(self,button,...)
    end
end
-- Lazy addon loading leaves the initial install pending.
dofile(source)
assert(not Client442CompatibilityStatus.spell_chat_link_dispatch)
for i=1,12 do
    local frame={index=i}
    frame.original=function(self,button,extra)
        assert(self==frame and button=='RightButton' and extra=='original argument')
        casts[i]=(casts[i] or 0)+1
    end
    frame.GetScript=function(self,kind) assert(kind=='OnClick');return self.original end
    frame.SetScript=function() error('must preserve the stock secure click script') end
    frame.OnModifiedClick=function(self,button)
        assert(self==frame and button=='LeftButton');links[i]=(links[i] or 0)+1
    end
    _G['SpellButton'..i]=frame
end
handler()
assert(Client442CompatibilityStatus.spell_chat_link_dispatch)
local installed=SpellButton1.click
handler()
assert(installed==SpellButton1.click)
modified=true
for i=1,12 do _G['SpellButton'..i]:click('LeftButton') end
assert(next(casts)==nil)
modified=false
for i=1,12 do _G['SpellButton'..i]:click('RightButton','original argument') end
for i=1,12 do assert(links[i]==1 and casts[i]==1) end
'''
    result=subprocess.run([lua,'-',str(source)],input=script,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
