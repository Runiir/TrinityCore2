-- Passive public Who list and stock result labels. No query or selection calls.
local function call(fn,...)
    if type(fn)~='function' then return end
    local ok,a,b=pcall(fn,...);if ok then return a,b end
end
local function visible(frame)return frame and not not call(frame.IsVisible,frame) or false end
local function label(frame)return frame and call(frame.GetText,frame) end
local count,last=0,nil
local events=CreateFrame('Frame')
events:RegisterEvent('WHO_LIST_UPDATE')
events:SetScript('OnEvent',function()count=count+1;last=call(GetTime) end)
function Client442ObserveWho()
    local api=C_FriendList or {}
    local shown,total=call(api.GetNumWhoResults)
    local data={visible=visible(WhoFrame),ready=type(shown)=='number' and type(total)=='number',
        count=shown,total=total,event_count=count,last_event=last,rows={},
        query=label(WhoFrameEditBox),stock_total=label(WhoFrameTotals)}
    for i=1,math.min(tonumber(shown) or 0,8) do
        local info=call(api.GetWhoInfo,i)
        if info then
            local row={index=i}
            for _,key in ipairs({'fullName','fullGuildName','level','raceStr','classStr','area','filename','gender'}) do
                local value=info[key]
                row[key]=type(value)=='string' and value:sub(1,128) or value
            end
            local prefix='WhoFrameButton'..i
            row.stock={name=label(_G[prefix..'Name']),level=label(_G[prefix..'Level']),
                class=label(_G[prefix..'Class']),variable=label(_G[prefix..'Variable'])}
            data.rows[#data.rows+1]=row
        end
    end
    data.rows_truncated=(tonumber(shown) or 0)>8
    return data
end
