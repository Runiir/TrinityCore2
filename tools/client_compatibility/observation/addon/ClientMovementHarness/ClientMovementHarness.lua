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
end

panel:SetScript("OnUpdate", function(_, delta)
    elapsed = elapsed + delta
    if elapsed >= 0.1 then elapsed = 0; sample() end
end)
sample()
