from pathlib import Path
import subprocess


def test_read_only_channel_list_events_filter_foreign_and_bound_history():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChannelObservation.lua'
    script=r'''
local handler
function CreateFrame()
    return {RegisterEvent=function(self,event)self.event=event end,
        SetScript=function(self,event,callback)handler=callback end,
        IsEventRegistered=function(self,event)return self.event==event end}
end
ChatFrame1={IsEventRegistered=function(self,event)return false end}
dofile(SOURCE)
assert(Client442ObserveChannelList().registered)
assert(not Client442ObserveChannelList().stock_registered)
handler(nil,'CHAT_MSG_CHANNEL_LIST','foreign',nil,nil,'Private',nil,nil,nil,1,'Private')
assert(Client442ObserveChannelList().sequence==0)
for i=1,3 do
    handler(nil,'CHAT_MSG_CHANNEL_LIST',string.rep('x',170),nil,nil,'TC442UIChannel1234abcd',nil,nil,nil,5,'TC442UIChannel1234abcd')
end
local result=Client442ObserveChannelList()
assert(result.sequence==3 and #result.events==2 and result.events[1].sequence==2)
assert(result.events[2].truncated and #result.events[2].text==160 and result.events[2].text_length==170)
assert(result.events[2].index==5)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,text=True,capture_output=True,check=True)
