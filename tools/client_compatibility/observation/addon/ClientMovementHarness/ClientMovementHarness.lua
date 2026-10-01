-- Observation only. No movement, spell, interaction or network commands.
local panel = CreateFrame("Frame", "ClientMovementHarnessPanel", UIParent)
local cell, columns = 4, 28
panel:SetScale(1 / UIParent:GetEffectiveScale())
panel:SetSize(columns * cell, 8 * cell)
panel:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 16, -16)
panel:SetFrameStrata("TOOLTIP")
panel:EnableMouse(false)

local pixels = {}
for i = 1, 224 do
    local pixel = panel:CreateTexture(nil, "OVERLAY")
    pixel:SetSize(cell, cell)
    pixel:SetPoint("TOPLEFT", panel, "TOPLEFT", ((i - 1) % columns) * cell,
                   -math.floor((i - 1) / columns) * cell)
    pixels[i] = pixel
end

local function integer(value, max)
    return math.max(0, math.min(max, math.floor(tonumber(value) or 0)))
end

local function append(bytes, value, width)
    for power = width - 1, 0, -1 do
        bytes[#bytes + 1] = math.floor(value / (256 ^ power)) % 256
    end
end

local function position()
    if C_Map and C_Map.GetBestMapForUnit and C_Map.GetPlayerMapPosition then
        local map = C_Map.GetBestMapForUnit("player")
        local pos = map and C_Map.GetPlayerMapPosition(map, "player")
        if pos then
            local x, y = pos:GetXY()
            return map, x, y
        end
    elseif GetCurrentMapAreaID and GetPlayerMapPosition then
        -- Use the currently selected map without changing the player's map UI.
        local x, y = GetPlayerMapPosition("player")
        if x and y and (x ~= 0 or y ~= 0) then
            return GetCurrentMapAreaID(), x, y
        end
    end
    return nil
end

local sequence, elapsed = 0, 0
-- A second observation-only packet carries public map/travel state. Digsite IDs
-- come from the same map API used by Blizzard's archaeology overlay.
local travelPanel = CreateFrame("Frame", "ClientTravelHarnessPanel", UIParent)
travelPanel:SetScale(1 / UIParent:GetEffectiveScale())
travelPanel:SetSize(256, 36)
travelPanel:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -16, -16)
travelPanel:SetFrameStrata("TOOLTIP")
travelPanel:EnableMouse(false)
local travelPixels = {}
for i = 1, 576 do
    local pixel = travelPanel:CreateTexture(nil, "OVERLAY")
    pixel:SetSize(4, 4)
    pixel:SetPoint("TOPLEFT", travelPanel, "TOPLEFT", ((i-1)%64)*4, -math.floor((i-1)/64)*4)
    travelPixels[i] = pixel
end
local digsites, nextSites = {}, 0
local function travelSample()
    if GetTime() >= nextSites then
        nextSites = GetTime() + 1
        digsites = {}
        local seen = {}
        if C_ResearchInfo and C_ResearchInfo.GetDigSitesForMap then
            for _, map in ipairs({1414, 1415, 1945, 113}) do
                local ok, sites = pcall(C_ResearchInfo.GetDigSitesForMap, map)
                if ok and sites then
                    for _, site in ipairs(sites) do
                        if not seen[site.researchSiteID] then
                            seen[site.researchSiteID] = true
                            digsites[#digsites+1] = site.researchSiteID
                        end
                    end
                end
            end
        end
        table.sort(digsites)
    end
    local posX, posY, posZ, world = UnitPosition("player")
    local flags = 0
    if IsMounted() then flags = flags + 1 end
    if IsFlying() then flags = flags + 2 end
    if IsFalling() then flags = flags + 4 end
    if IsSwimming() then flags = flags + 8 end
    if UnitCastingInfo("player") or UnitChannelInfo("player") then flags = flags + 16 end
    if IsIndoors() then flags = flags + 32 end
    if IsFlyableArea() then flags = flags + 64 end
    if posX and posY and posZ and world then flags = flags + 128 end
    local bytes = {84, 67, 65, 50} -- TCA2
    append(bytes, sequence, 4)
    append(bytes, math.floor(GetTime()*1000)%4294967296, 4)
    append(bytes, world or 0, 4)
    append(bytes, math.floor((posX or 0)*100), 4)
    append(bytes, math.floor((posY or 0)*100), 4)
    append(bytes, math.floor((posZ or 0)*100), 4)
    append(bytes, flags, 1)
    append(bytes, math.min(#digsites, 16), 1)
    for i=1,16 do append(bytes, digsites[i] or 0, 2) end
    local tip = GameTooltip:IsShown() and GameTooltipTextLeft1:GetText() or ""
    local tipFirst, tipSecond = 0, 0
    for i=1,#tip do tipFirst=(tipFirst+tip:byte(i))%255; tipSecond=(tipSecond+tipFirst)%255 end
    append(bytes, tipSecond*256+tipFirst, 2)
    append(bytes, math.min(GetNumLootItems() or 0, 255), 1)
    append(bytes, integer((GetCameraZoom() or 0)*100, 65535), 2)
    local cursorX, cursorY = GetCursorPosition()
    append(bytes, integer(cursorX,4095)*4096+integer(cursorY,4095), 3)
    local first, second = 0, 0
    for _, byte in ipairs(bytes) do first=(first+byte)%255; second=(second+first)%255 end
    append(bytes, second*256+first, 2)
    for i=1,#bytes*8 do
        local byte=bytes[math.floor((i-1)/8)+1]
        local white=math.floor(byte/(2^ (7-((i-1)%8))))%2
        travelPixels[i]:SetColorTexture(white, white, white, 1)
    end
end
local function sample()
    sequence = (sequence + 1) % 4294967296
    local map, x, y = position()
    local flags = 0
    if UnitGUID("player") then flags = flags + 1 end
    if map then flags = flags + 2 end
    if UnitAffectingCombat("player") then flags = flags + 4 end
    if UnitIsDeadOrGhost("player") then flags = flags + 8 end
    if UnitOnTaxi("player") then flags = flags + 16 end
    local maxHealth = UnitHealthMax("player") or 0
    local health = maxHealth > 0 and (UnitHealth("player") / maxHealth * 100) or 0
    local bytes = {84, 67, 77, 49} -- TCM1
    append(bytes, sequence, 4)
    append(bytes, math.floor(GetTime() * 1000) % 4294967296, 4)
    append(bytes, map or 0, 4)
    append(bytes, integer((x or 0) * 65535, 65535), 2)
    append(bytes, integer((y or 0) * 65535, 65535), 2)
    append(bytes, integer((GetPlayerFacing() or 0) / (2 * math.pi) * 65535, 65535), 2)
    append(bytes, integer((GetUnitSpeed("player") or 0) * 100, 65535), 2)
    append(bytes, integer(health, 100), 1)
    append(bytes, flags, 1)
    local first, second = 0, 0
    for _, byte in ipairs(bytes) do
        first = (first + byte) % 255
        second = (second + first) % 255
    end
    append(bytes, second * 256 + first, 2)
    for i = 1, #bytes * 8 do
        local byte = bytes[math.floor((i - 1) / 8) + 1]
        local white = math.floor(byte / (2 ^ (7 - ((i - 1) % 8)))) % 2
        if pixels[i].SetColorTexture then
            pixels[i]:SetColorTexture(white, white, white, 1)
        else
            pixels[i]:SetTexture(white, white, white, 1)
        end
    end
    travelSample()
end

panel:SetScript("OnUpdate", function(_, delta)
    elapsed = elapsed + delta
    if elapsed >= 0.1 then elapsed = 0; sample() end
end)
sample()
