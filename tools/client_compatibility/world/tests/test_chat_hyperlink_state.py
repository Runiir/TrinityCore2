from pathlib import Path
import subprocess
import pytest
from tools.client_compatibility.interaction_chat_player_menu import owned_link_hover


def test_chat_hyperlink_diagnostics_preserve_runtime_and_saved_flags_without_setters():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChatObservation.lua'
    script=r'''
NUM_CHAT_WINDOWS=1
GetChatWindowInfo=function()return 'General',14,1,1,1,0,true,true,1,false end
ChatFrame1={isUninteractable=true,overrideHyperlinksEnabled=false,
 GetHyperlinksEnabled=function()return false end,IsMouseClickEnabled=function()return true end,
 IsMouseMotionEnabled=function()return false end,SetHyperlinksEnabled=function()error('setter forbidden')end}
dofile(SOURCE)
local d=Client442ObserveChatWindows().windows[1]
assert(d.uninteractable==false and d.runtime_uninteractable==true)
assert(d.hyperlinks_enabled==false and d.mouse_click_enabled==true and d.mouse_motion_enabled==false)
assert(ChatFrame1.isUninteractable==true)
ChatFrame1.GetHyperlinksEnabled=function()error('unavailable')end
assert(Client442ObserveChatWindows().windows[1].hyperlinks_enabled==nil)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,text=True,capture_output=True,check=True)


@pytest.mark.parametrize('kind,text,expected',[
    ('FontString','|Hplayer:Harnesstwo-Client442Lab:123:WHISPER',True),
    ('Frame','',False),('FontString','|Hplayer:Other-Client442Lab:123',False),
    ('FontString','|Hplayer:Harnesstwo-Client442LabOther:123',False),
    ('FontString','|Hitem:49778:123',False)])
def test_sender_menu_needs_an_observed_owned_player_hyperlink(kind,text,expected):
    state={'pointer':{'foci':[{'kind':kind,'text':text}]}}
    assert owned_link_hover(state,{'observed_sender':'Harnesstwo-Client442Lab'})==expected
