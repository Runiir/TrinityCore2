-- Normal public addon telemetry, self-addressed only. No gameplay actions.
local prefix='WMLF1'
local status={attempts=0,sent=0,pumps=0}
if C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix then
    local ok,result=pcall(C_ChatInfo.RegisterAddonMessagePrefix,prefix)
    status.register_result=ok and tostring(result) or 'registration error'
end
function WhitemaneLiveRelayStatus()return status end
local alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
local function base64(value)
    local result={}
    for i=1,#value,3 do
        local a,b,c=value:byte(i,i+2);local n=a*65536+(b or 0)*256+(c or 0)
        for _,shift in ipairs({18,12}) do
            local index=math.floor(n/2^shift)%64+1;result[#result+1]=alphabet:sub(index,index)
        end
        local index=math.floor(n/64)%64+1;result[#result+1]=b and alphabet:sub(index,index) or '='
        index=n%64+1;result[#result+1]=c and alphabet:sub(index,index) or '='
    end
    return table.concat(result)
end
local latest,jobs,lastPayload,lastSent={},{},{},{}
local serial=math.floor(GetTime()*1000)%4294967296
local function submit(kind,value)
    serial=(serial+1)%4294967296
    latest[kind]={id=serial,value=base64(value)}
    return serial
end
function WhitemaneLiveRelayBytes(kind,bytes)
    local now=GetTime();local interval=kind=='M' and .09 or .35
    if now-(lastSent[kind] or 0)<interval then return end
    local value={};for _,byte in ipairs(bytes) do value[#value+1]=string.char(byte) end
    submit(kind,table.concat(value));lastSent[kind]=now
end
local uiVersion=0
function WhitemaneLiveRelayUI(payload,fast,encode)
    if payload~=lastPayload.U then uiVersion=submit('U',payload);lastPayload.U=payload end
    fast.ui_version=uiVersion
    local value=encode(fast);local now=GetTime()
    if value~=lastPayload.F or now-(lastSent.F or 0)>1 then
        submit('F',value);lastPayload.F=value;lastSent.F=now
    end
end
local elapsed,budget,last=0,4096,GetTime()
local cursor=0
local channels={'M','A','F','U'}
function WhitemaneLiveRelayPump(delta)
    status.pumps=status.pumps+1
    elapsed=elapsed+delta;if elapsed<.05 then return end;elapsed=elapsed%.05
    local now=GetTime();budget=math.min(4096,budget+(now-last)*4096);last=now
    local self=UnitName('player');if self~='Runiir' then return end
    for _=1,4 do
        cursor=cursor%#channels+1;local kind=channels[cursor]
        if not jobs[kind] and latest[kind] then
            local job=latest[kind];latest[kind]=nil;job.part=1;job.total=math.ceil(#job.value/200);jobs[kind]=job
        end
        local job=jobs[kind]
        if job then
            local text=table.concat({kind,job.id,job.part,job.total},'|')..'|'..job.value:sub((job.part-1)*200+1,job.part*200)
            if #text+40<=budget then
                status.attempts=status.attempts+1
                local ok,result=pcall(C_ChatInfo.SendAddonMessage,prefix,text,'WHISPER',self)
                status.last_result=ok and tostring(result) or tostring(result):sub(1,160)
                if ok and (result==nil or result==0 or result==true) then
                    status.sent=status.sent+1
                    budget=budget-#text-40;job.part=job.part+1
                    if job.part>job.total then jobs[kind]=nil end
                end
            end
        end
    end
end
