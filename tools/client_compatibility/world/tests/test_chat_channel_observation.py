from pathlib import Path
import subprocess


def test_public_channel_tuples_empty_list_and_bounds():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChatObservation.lua'
    script=r'''
NUM_CHAT_WINDOWS=0
dofile(SOURCE)
assert(not Client442ObserveChatWindows().channels.available)
function GetChannelList()return end
local channels=Client442ObserveChatWindows().channels
assert(channels.available and #channels.rows==0)
function GetChannelList()return 1,'General',false,2,'TC442UIChannel',true end
channels=Client442ObserveChatWindows().channels
assert(channels.available and #channels.rows==2)
assert(channels.rows[2].id==2 and channels.rows[2].name=='TC442UIChannel' and channels.rows[2].disabled)
function GetChannelList()return 1,'General' end
assert(not Client442ObserveChatWindows().channels.available)
function GetChannelList()return 1,'General','false' end
assert(not Client442ObserveChatWindows().channels.available)
function GetChannelList()
    local values={};for index=1,9 do
        values[#values+1]=index;values[#values+1]='Channel'..index;values[#values+1]=false
    end
    return unpack(values)
end
assert(not Client442ObserveChatWindows().channels.available)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,
        text=True,capture_output=True,check=True)


def test_public_chat_edit_handles_closed_focus_and_text_bounds():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChatObservation.lua'
    script=r'''
dofile(SOURCE)
local d=Client442ObserveChatEdit()
assert(not d.chat_edit_open and not d.chat_edit_focused and d.chat_edit_text=='')
ChatFrame1EditBox={IsVisible=function()return true end, HasFocus=function()return false end,
    GetText=function()return string.rep('x',300) end}
d=Client442ObserveChatEdit()
assert(d.chat_edit_open and not d.chat_edit_focused and #d.chat_edit_text==255)
ChatFrame1EditBox.HasFocus=function()return true end
ChatFrame1EditBox.GetText=function()return '/tcui state' end
ChatFrame1EditBox.GetAttribute=function(self,key)assert(key=='chatType');return 'SAY' end
d=Client442ObserveChatEdit()
assert(d.chat_edit_focused and d.chat_edit_text=='/tcui state' and d.chat_edit_type=='SAY')
ChatFrame1EditBox.IsVisible=function()return false end
d=Client442ObserveChatEdit()
assert(not d.chat_edit_open and not d.chat_edit_focused and d.chat_edit_text=='' and d.chat_edit_type==nil)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,
        text=True,capture_output=True,check=True)


def test_public_languages_observe_choices_and_selected_without_setters():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChatObservation.lua'
    script=r'''
NUM_CHAT_WINDOWS=0
dofile(SOURCE)
assert(not Client442ObserveChatWindows().languages.available)
function GetNumLanguages()return 2 end
function GetLanguageByIndex(i)if i==1 then return 'Common',7 else return 'Orcish',1 end end
DEFAULT_CHAT_FRAME={editBox={languageID=7}}
local d=Client442ObserveChatWindows().languages
assert(d.available and #d.rows==2 and d.rows[2].name=='Orcish' and d.rows[2].id==1 and d.selected_id==7)
function GetLanguageByIndex()error('unavailable') end
assert(not Client442ObserveChatWindows().languages.available)
function GetNumLanguages()return 17 end
assert(not Client442ObserveChatWindows().languages.available)
function GetNumLanguages()return 0 end
assert(Client442ObserveChatWindows().languages.available)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,
        text=True,capture_output=True,check=True)


def test_pointer_reads_bound_public_foci_and_skip_forbidden_frames():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChatObservation.lua'
    script=r'''
dofile(SOURCE)
assert(#Client442ObservePointer().foci==0)
function GetCursorPosition()return 84,263 end
local allowed={IsForbidden=function()return false end,GetName=function()return 'Menu' end,
    GetObjectType=function()return 'Button' end,GetText=function()return 'Language' end}
local forbidden={IsForbidden=function()return true end,GetName=function()error('must not read') end}
function GetMouseFoci()return {allowed,forbidden,allowed,allowed} end
local d=Client442ObservePointer()
assert(d.x==84 and d.y==263 and #d.foci==2 and d.foci[1].text=='Language')
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,
        text=True,capture_output=True,check=True)
