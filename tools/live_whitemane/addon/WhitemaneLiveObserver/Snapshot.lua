-- Public gameplay and displayed GatherMate frame reads only. No game actions.
local panel = CreateFrame("Frame", "WhitemaneLiveSnapshot", UIParent)
panel:SetScale(1 / UIParent:GetEffectiveScale())
panel:SetSize(288, 129)
panel:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 16, -76)
panel:SetFrameStrata("TOOLTIP")
panel:EnableMouse(false)
local pixels = {}
for i = 1, 4096 do
    local pixel = panel:CreateTexture(nil, "OVERLAY")
    pixel:SetSize(3, 3)
    pixel:SetPoint("TOPLEFT", panel, "TOPLEFT", ((i - 1) % 96) * 3, -math.floor((i - 1) / 96) * 3)
    pixel:SetColorTexture(0, 0, 0, 1)
    pixels[i] = pixel
end
local function call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b, c, d, e, f, g, h = pcall(fn, ...)
    if ok then return a, b, c, d, e, f, g, h end
end
local function append(bytes, value, width)
    value = math.max(0, math.min(256 ^ width - 1, math.floor(tonumber(value) or 0)))
    for power = width - 1, 0, -1 do bytes[#bytes + 1] = math.floor(value / (256 ^ power)) % 256 end
end
local function checksum(bytes)
    local first, second = 0, 0
    for _, v in ipairs(bytes) do first = (first + v) % 255; second = (second + first) % 255 end
    return second * 256 + first
end
local function world(map, position)
    if not map or not position then return end
    local instance, p = call(C_Map and C_Map.GetWorldPosFromMapPos, map, position)
    if p then local n, w = p:GetXY(); return instance, n, w end
end
local sequence, surveys, surveyAt, finds, previousTotal = 0, 0, 0, 0, nil
local event = CreateFrame("Frame")
event:RegisterEvent("UNIT_SPELLCAST_SUCCEEDED")
event:SetScript("OnEvent", function(_, _, unit, _, spell)
    if unit == "player" and spell == 80451 then surveys = surveys + 1; surveyAt = GetTime() end
end)
local function sample()
    sequence = (sequence + 1) % 4294967296
    local map = call(C_Map and C_Map.GetBestMapForUnit, "player")
    local p = map and call(C_Map and C_Map.GetPlayerMapPosition, map, "player")
    local instance, north, west = world(map, p)
    local flags = 0
    for _, pair in ipairs({{CanScanResearchSite, 1}, {IsMounted, 2}, {IsFlying, 4}}) do
        if call(pair[1]) then flags = flags + pair[2] end
    end
    if call(UnitCastingInfo, "player") or call(UnitChannelInfo, "player") then flags = flags + 8 end
    if LootFrame and LootFrame:IsShown() then flags = flags + 16 end
    if instance and north and west then flags = flags + 32 end
    if call(IsFalling) then flags = flags + 64 end
    if call(IsSwimming) then flags = flags + 512 end
    local _, _, altitude, altitudeInstance = call(UnitPosition, "player")
    if type(altitude) == "number" and altitude == altitude and math.abs(altitude) < 100000 and
        altitudeInstance == instance then flags = flags + 256 else altitude = nil end
    local tip = GameTooltip and GameTooltip:IsShown() and GameTooltip:GetAlpha() > 0.99 and
        GameTooltipTextLeft1 and GameTooltipTextLeft1:GetText() or ""
    local tipBytes = {}
    for j = 1, #tip do tipBytes[j] = tip:byte(j) end
    flags = flags + 1024
    local races, total = {}, 0
    for index = 1, math.min(call(GetNumArchaeologyRaces) or 0, 16) do
        local _, _, stone, fragments, cost = call(GetArchaeologyRaceInfo, index)
        local _, _, _, _, _, sockets, _, spell = call(GetActiveArtifactByRace, index)
        if fragments and cost then
            total = total + fragments
            races[#races + 1] = {index, fragments, cost, sockets or 0,
                stone and (call(GetItemCount, stone, false) or 0) or 0, spell or 0}
        end
    end
    if previousTotal and total > previousTotal then finds = finds + 1 end
    previousTotal = total
    local siteID, nearest = 0, nil
    if flags % 2 == 1 and north then
        for _, site in ipairs(call(C_ResearchInfo and C_ResearchInfo.GetDigSitesForMap, 1414) or {}) do
            local i, n, w = world(1414, site.position)
            if i == instance and n and w then
                local distance = (n - north)^2 + (w - west)^2
                if not nearest or distance < nearest then nearest = distance; siteID = site.researchSiteID or 0 end
            end
        end
    end
    local markers = {}
    if north and Minimap then
        for _, pin in ipairs({Minimap:GetChildren()}) do
            if pin.nodeType == "Archaeology" and pin:IsShown() and pin:GetAlpha() > 0 and
                pin.zone == map and pin.coords and pin.x and pin.y then
                local i, n, w = world(map, CreateVector2D(pin.x, pin.y))
                if i == instance and n and w then
                    local distance = math.sqrt((n - north)^2 + (w - west)^2)
                    if distance <= 200 then
                        markers[#markers + 1] = {pin.coords, pin.x, pin.y, distance,
                            math.atan2(w - west, n - north) % (2 * math.pi), pin.nodeID or 0}
                    end
                end
            end
        end
    end
    table.sort(markers, function(a, b) if a[4] == b[4] then return a[1] < b[1] end; return a[4] < b[4] end)
    local history = CanopicHelperDB and CanopicHelperDB.surveyBearings
    local arrow = history and history[#history]
    if arrow and arrow.siteID == siteID and arrow.at and time() - arrow.at <= 20 and
        arrow.north and arrow.west and arrow.angle and arrow.length then flags = flags + 128
    else arrow = nil end
    local boundary = CanopicHelperArrow and CanopicHelperArrow.liveBoundary
    if arrow and boundary and boundary.siteID == siteID and boundary.at == arrow.at then
        flags = flags + 2048
    end
    local bytes = {84, 67, 65, 49, 0, 0} -- TCA1 plus total length
    for _, pair in ipairs({{sequence,4},{GetTime()*1000,4},{flags,2},{instance,2},
        {((north or 0)+100000)*100,4},{((west or 0)+100000)*100,4},
        {surveys,4},{surveyAt*1000,4},{finds,4},{siteID,4},
        {call(GetItemCount,64657,false),2},{call(GetItemCount,67538,false),2},
        {#races,1},{math.min(#markers,8),1}}) do append(bytes,pair[1],pair[2]) end
    for _, race in ipairs(races) do
        for j, width in ipairs({1,2,2,1,2,4}) do append(bytes,race[j],width) end
    end
    for j = 1, math.min(#markers,8) do
        local m = markers[j]
        for _, pair in ipairs({{m[1],8},{m[2]*65535,2},{m[3]*65535,2},
            {m[4]*100,2},{m[5]/(2*math.pi)*65535,2},{m[6],2}}) do append(bytes,pair[1],pair[2]) end
    end
    if arrow then
        for _, pair in ipairs({{(arrow.north+100000)*100,4},{(arrow.west+100000)*100,4},
            {arrow.angle/(2*math.pi)*65535,2},{arrow.length*100,2},{arrow.at,4}}) do append(bytes,pair[1],pair[2]) end
    end
    if altitude then append(bytes, (altitude + 100000) * 100, 4) end
    append(bytes, checksum(tipBytes), 2)
    local length = #bytes + 2
    bytes[5], bytes[6] = math.floor(length / 256), length % 256
    append(bytes,checksum(bytes),2)
    for index, pixel in ipairs(pixels) do
        local byte = bytes[math.floor((index - 1) / 8) + 1] or 0
        local bit = math.floor(byte / (2 ^ (7 - ((index - 1) % 8)))) % 2
        pixel:SetColorTexture(bit,bit,bit,1)
    end
end
local elapsed = 0
panel:SetScript("OnUpdate", function(_, delta)
    elapsed = elapsed + delta
    if elapsed >= 0.4 then elapsed = 0; sample() end
end)
