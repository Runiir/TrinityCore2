from pathlib import Path
import subprocess


def test_read_only_channel_list_events_filter_foreign_and_bound_history():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/ChannelObservation.lua'
    script=r'''
local handler
function CreateFrame()
    return {RegisterEvent=function(self,event)self.events=self.events or {};self.events[event]=true end,
        SetScript=function(self,event,callback)handler=callback end,
        IsEventRegistered=function(self,event)return self.events[event]==true end}
end
ChatFrame1={IsEventRegistered=function(self,event)return false end}
dofile(SOURCE)
assert(Client442ObserveChannelList().registered)
assert(not Client442ObserveChannelList().stock_registered)
handler(nil,'CHAT_MSG_CHANNEL_LIST','foreign',nil,nil,'Private',nil,nil,nil,1,'Private')
assert(Client442ObserveChannelList().sequence==0)
assert(Client442ObserveChannelList().received_sequence==1)
for i=1,3 do
    handler(nil,'CHAT_MSG_CHANNEL_LIST',string.rep('x',170),nil,nil,'TC442UIChannel1234abcd',nil,nil,nil,5,'TC442UIChannel1234abcd')
end
local result=Client442ObserveChannelList()
assert(result.sequence==3 and #result.events==2 and result.events[1].sequence==2)
assert(result.events[2].truncated and #result.events[2].text==160 and result.events[2].text_length==170)
assert(result.events[2].index==5)
handler(nil,'CHAT_MSG_CHANNEL_LIST','Harnessone',nil,nil,'TC442UIChannel1234abcd',nil,nil,nil,5,'')
assert(Client442ObserveChannelList().sequence==4)
function GetNumDisplayChannels()return 2 end
function GetChannelDisplayInfo(id)
    if id==1 then return 'Private',false,false,4,1 end
    return 'TC442UIChannel1234abcd',false,false,5,1
end
function UnitGUID()return 'Player-1' end
C_ChatInfo={GetChannelRosterInfo=function(id,index)assert(id==2 and index==1);return 'Harnessone',true,true,'Player-1' end}
handler(nil,'CHANNEL_ROSTER_UPDATE',2)
result=Client442ObserveChannelList()
assert(result.sequence==5 and result.events[2].event=='CHANNEL_ROSTER_UPDATE')
assert(result.roster.available and #result.roster.channels==1 and result.roster.channels[1].member_count==1)
assert(result.roster.channels[1].members[1].is_player and result.roster.channels[1].members[1].owner)
function GetNumDisplayChannels()return 25 end
assert(not Client442ObserveChannelList().roster.available)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,text=True,capture_output=True,check=True)
