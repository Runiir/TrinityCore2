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
d=Client442ObserveChatEdit()
assert(d.chat_edit_focused and d.chat_edit_text=='/tcui state')
ChatFrame1EditBox.IsVisible=function()return false end
d=Client442ObserveChatEdit()
assert(not d.chat_edit_open and not d.chat_edit_focused and d.chat_edit_text=='')
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,
        text=True,capture_output=True,check=True)
