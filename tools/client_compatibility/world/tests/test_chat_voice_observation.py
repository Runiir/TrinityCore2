from pathlib import Path
import subprocess


def test_voice_getters_preserve_false_nil_errors_and_never_invoke_setters():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChatObservation.lua'
    script=r'''
NUM_CHAT_WINDOWS=0
dofile(SOURCE)
local d=Client442ObserveChatWindows().voice
assert(not d.api_available and not d.available)
C_VoiceChat={IsMuted=function()return false end,IsDeafened=function()return true end,
    IsEnabled=function()return false end,IsLoggedIn=function()return false end,
    CanPlayerUseVoiceChat=function()return true end,GetActiveChannelID=function()return nil end,
    SetMuted=function()error('setter forbidden')end,SetDeafened=function()error('setter forbidden')end}
d=Client442ObserveChatWindows().voice
assert(d.api_available and d.available and d.muted==false and d.deafened==true)
assert(d.enabled==false and d.logged_in==false and d.can_use==true and d.active_channel_id==nil)
C_VoiceChat.IsMuted=function()return nil end
assert(not Client442ObserveChatWindows().voice.available)
C_VoiceChat.IsMuted=function()error('offline')end
C_VoiceChat.GetActiveChannelID=function()return -1 end
d=Client442ObserveChatWindows().voice
assert(not d.available and d.muted==nil and d.active_channel_id==nil)
C_VoiceChat.IsMuted=function()return 'false' end
assert(not Client442ObserveChatWindows().voice.available)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,
        text=True,capture_output=True,check=True)
