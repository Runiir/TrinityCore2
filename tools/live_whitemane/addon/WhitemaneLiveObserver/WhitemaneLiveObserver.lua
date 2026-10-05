-- Public API reads only. No movement, spells or targeting.
-- Uses the existing TCM1 screenshot packet; no rewrite bridge is required.
local panel = CreateFrame("Frame", "WhitemaneLiveObserverPanel", UIParent)
panel:SetScale(1 / UIParent:GetEffectiveScale())
panel:SetSize(112, 32)
panel:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 16, -16)
panel:SetFrameStrata("TOOLTIP")
panel:EnableMouse(false)
local pixels = {}
for i = 1, 224 do
    local pixel = panel:CreateTexture(nil, "OVERLAY")
    pixel:SetSize(4, 4)
    pixel:SetPoint("TOPLEFT", panel, "TOPLEFT", ((i - 1) % 28) * 4,
                   -math.floor((i - 1) / 28) * 4)
    pixels[i] = pixel
end
local status = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
status:SetPoint("TOPLEFT", panel, "BOTTOMLEFT", 0, -4)
status:SetText("Live observer: public movement only")

local function call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b, c, d = pcall(fn, ...)
    if ok then return a, b, c, d end
end
local function integer(value, maximum)
    return math.max(0, math.min(maximum, math.floor(tonumber(value) or 0)))
end
local function append(bytes, value, width)
    for power = width - 1, 0, -1 do
        bytes[#bytes + 1] = math.floor(value / (256 ^ power)) % 256
    end
end
local function checksum(bytes)
    local first, second = 0, 0
    for _, value in ipairs(bytes) do
        first = (first + value) % 255
        second = (second + first) % 255
    end
    return second * 256 + first
end
local sequence, elapsed = 0, 0
local function sample()
    sequence = (sequence + 1) % 4294967296
    local map = call(C_Map and C_Map.GetBestMapForUnit, "player")
    local position = map and call(C_Map and C_Map.GetPlayerMapPosition, map, "player")
    local x, y
    if position then x, y = position:GetXY() end
    local exists = not not call(UnitExists, "player")
    local flags = exists and 1 or 0
    if map and x and y then flags = flags + 2 end
    if call(UnitAffectingCombat, "player") then flags = flags + 4 end
    if call(UnitIsDeadOrGhost, "player") then flags = flags + 8 end
    if call(UnitOnTaxi, "player") then flags = flags + 16 end
    local health, maximum = call(UnitHealth, "player"), call(UnitHealthMax, "player")
    local percent = health and maximum and maximum > 0 and health / maximum * 100 or 0
    local bytes = {84, 67, 77, 49} -- TCM1
    append(bytes, sequence, 4)
    append(bytes, integer(GetTime() * 1000, 4294967295), 4)
    append(bytes, map or 0, 4)
    append(bytes, integer((x or 0) * 65535, 65535), 2)
    append(bytes, integer((y or 0) * 65535, 65535), 2)
    append(bytes, integer((call(GetPlayerFacing) or 0) / (2 * math.pi) * 65535, 65535), 2)
    append(bytes, integer((call(GetUnitSpeed, "player") or 0) * 100, 65535), 2)
    append(bytes, integer(percent, 100), 1)
    append(bytes, flags, 1)
    append(bytes, checksum(bytes), 2)
    if WhitemaneLiveRelayBytes then
        -- Fast public world/mode facts travel with heading. The journal and
        -- marker packet can then update less often without delaying steering.
        local relay={unpack(bytes)}
        local instance,p=call(C_Map and C_Map.GetWorldPosFromMapPos,map,position)
        local north,west;if p then north,west=p:GetXY() end
        local mode=0
        for _,pair in ipairs({{IsMounted,1},{IsFlying,2},{IsFalling,16},{IsSwimming,32},{CanScanResearchSite,256}}) do
            if call(pair[1]) then mode=mode+pair[2] end
        end
        if call(UnitCastingInfo,'player') or call(UnitChannelInfo,'player') then mode=mode+4 end
        if LootFrame and LootFrame:IsShown() then mode=mode+8 end
        if instance and north and west then mode=mode+64 end
        local _,_,height,heightInstance=call(UnitPosition,'player')
        if type(height)=='number' and height==height and math.abs(height)<100000 and heightInstance==instance then
            mode=mode+128
        else height=nil end
        relay[#relay+1]=87;relay[#relay+1]=49 -- W1 extension
        for _,pair in ipairs({{mode,2},{instance or 0,2},{((north or 0)+100000)*100,4},
            {((west or 0)+100000)*100,4},{((height or 0)+100000)*100,4}}) do
            append(relay,integer(pair[1],256^pair[2]-1),pair[2])
        end
        append(relay,checksum(relay),2)
        WhitemaneLiveRelayBytes('M',relay)
    end
    for i = 1, #bytes * 8 do
        local value = math.floor(bytes[math.floor((i - 1) / 8) + 1] / (2 ^ (7 - ((i - 1) % 8)))) % 2
        pixels[i]:SetColorTexture(value, value, value, 1)
    end
    status:SetText("Live observer: " .. (call(UnitName, "player") or "unavailable"))
end
panel:SetScript("OnUpdate", function(_, delta)
    elapsed = elapsed + delta
    if elapsed >= 0.1 then elapsed = elapsed%0.1; sample() end
end)
