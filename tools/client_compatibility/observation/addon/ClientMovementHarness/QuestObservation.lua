-- Public reward and tracking diagnostics. This file only reads stock APIs.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f=pcall(fn,...)
    if ok then return a,b,c,d,e,f end
end
local function items(kind,count)
    local rows={}
    for i=1,math.min(tonumber(count) or 0,6) do
        local name,texture,quantity,quality,usable,id=call(GetQuestItemInfo,kind,i)
        local link=call(GetQuestItemLink,kind,i)
        rows[#rows+1]={index=i,name=name,id=tonumber(type(link)=='string' and link:match('item:(%d+)')) or id,
            quantity=quantity,quality=quality,usable=usable}
    end
    return rows
end
function Client442ObserveQuestReward()
    local data={id=call(GetQuestID),title=call(GetTitleText),text=call(GetRewardText),
        money=call(GetRewardMoney),xp=call(GetRewardXP),selected=QuestInfoFrame and QuestInfoFrame.itemChoice,
        choices=items('choice',call(GetNumQuestChoices)),fixed=items('reward',call(GetNumQuestRewards)),frames={},tracking={}}
    for _,name in ipairs({'QuestFrame','QuestFrameRewardPanel','QuestRewardScrollFrame','QuestInfoRewardsFrame',
        'QuestFrameCompleteQuestButton','QuestFrameCompleteButton'}) do
        local f=_G[name]
        if f then data.frames[#data.frames+1]={name=name,visible=not not call(f.IsVisible,f),rect={call(f.GetRect,f)}} end
    end
    local count=call(C_Minimap and C_Minimap.GetNumTrackingTypes) or call(GetNumTrackingTypes) or 0
    for i=1,math.min(count,40) do
        local info=call(C_Minimap and C_Minimap.GetTrackingInfo,i)
        if type(info)=='table' then data.tracking[#data.tracking+1]={index=i,name=info.name,active=info.active}
        else
            local name,texture,active=call(GetTrackingInfo,i)
            data.tracking[#data.tracking+1]={index=i,name=name,active=active}
        end
    end
    return data
end
