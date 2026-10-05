from pathlib import Path
import subprocess
import pytest
from tools.client_compatibility.interaction_chat_player_menu import owned_link_hover,reviewed_hover_points


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
    state={'pointer':{'foci':[{'kind':kind,'text':text}],
        'chat_link':{'frame':'ChatFrame1','data':'player:Harnesstwo-Client442Lab:123:WHISPER'}}}
    assert owned_link_hover(state,{'observed_sender':'Harnesstwo-Client442Lab'})==expected


@pytest.mark.parametrize('link',[None,{'frame':'ChatFrame1','data':'item:49778'},
    {'frame':'ChatFrame2','data':'player:Harnesstwo-Client442Lab:123:WHISPER'},
    {'frame':'ChatFrame1','data':'player:Other-Client442Lab:123:WHISPER'}])
def test_font_string_focus_alone_does_not_prove_the_owned_hyperlink(link):
    state={'pointer':{'foci':[{'kind':'FontString','text':'|Hplayer:Harnesstwo-Client442Lab:123:WHISPER'}],
        'chat_link':link}}
    assert not owned_link_hover(state,{'observed_sender':'Harnesstwo-Client442Lab'})


def test_hover_events_observe_enter_leave_without_replacing_existing_scripts():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChatObservation.lua'
    script=r'''
NUM_CHAT_WINDOWS=1
local hooks={}
ChatFrame1={GetName=function()return 'ChatFrame1' end,
 HookScript=function(self,name,fn)assert(hooks[name]==nil);hooks[name]=fn end}
dofile(SOURCE)
assert(Client442ObservePointer().chat_link==nil)
Client442ObservePointer()
hooks.OnHyperlinkEnter(ChatFrame1,'player:Harnesstwo-Client442Lab:123:WHISPER','[Harnesstwo]')
local d=Client442ObservePointer().chat_link
assert(d.frame=='ChatFrame1' and d.data=='player:Harnesstwo-Client442Lab:123:WHISPER' and d.text=='[Harnesstwo]')
hooks.OnHyperlinkLeave(ChatFrame1)
assert(Client442ObservePointer().chat_link==nil)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,text=True,capture_output=True,check=True)


@pytest.mark.parametrize('points',[
    [[61,576],[61,579]],[[61,576],[61,600]],[[61,576],[100,576]],
    [[61,579]],[[61,576]]*4,[[61,576],[61.5,577]],[]])
def test_reviewed_hover_probes_stay_in_the_approved_text_neighborhood(points):
    if points==[[61,576],[61,579]]:
        assert reviewed_hover_points({'point_candidates':points},[61,576])==points
    else:
        with pytest.raises(RuntimeError):reviewed_hover_points({'point_candidates':points},[61,576])
