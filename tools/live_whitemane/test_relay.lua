-- Exercise the actual sender under a throttled 30 FPS clock, without a game.
local now,player,sent=10,'Runiir',{}
function GetTime()return now end
function UnitName()return player end
local frame={}
function frame:SetScript(_,fn)self.update=fn end
function CreateFrame()return frame end
C_ChatInfo={SendAddonMessage=function(prefix,text,channel,target)
    assert(prefix=='WMLF1' and channel=='WHISPER' and target=='Runiir' and #text<255)
    sent[#sent+1]={at=now,text=text};return 0
end}
local file=assert(io.open('tools/live_whitemane/addon/WhitemaneLiveObserver/Relay.lua'))
local source=file:read('*a');file:close()
assert((loadstring or load)(source))()
WhitemaneLiveRelayBytes('M',{1,2,3});WhitemaneLiveRelayPump(1);assert(#sent==0,'default relay must not send server messages')
-- Separately exercise the retained opt-in sender implementation.
source=source:gsub('local enabled=false','local enabled=true',1)
assert((loadstring or load)(source))()
local bytes={0,1,2,253,254,255}
WhitemaneLiveRelayBytes('M',bytes)
player='Other';WhitemaneLiveRelayPump(.1);assert(#sent==0)
player='Runiir';now=now+.1;WhitemaneLiveRelayPump(.1)
assert(sent[1].text:match('AAEC/f7/'))
WhitemaneLiveRelayUI(string.rep('x',12000),{},function(f)return '{"ui_version":'..f.ui_version..'}' end)
local start=now;local latestM,completedU,messages=0,false,0
for i=1,600 do
    now=start+i/30
    if i%3==0 then WhitemaneLiveRelayBytes('M',bytes) end
    if i%12==0 then WhitemaneLiveRelayBytes('A',bytes) end
    WhitemaneLiveRelayPump(1/30)
end
for _,row in ipairs(sent) do
    if row.text:sub(1,1)=='M' then latestM=row.at end
    local kind,id,part,total=row.text:match('^(%a)|(%d+)|(%d+)|(%d+)|')
    if kind=='U' and part==total then completedU=true end
end
assert(completedU,'large public UI update never completed')
assert(now-latestM<.3,'UI traffic starved movement updates')
print('Relay self-only, base64, bounded messages and movement during large UI updates passed')
