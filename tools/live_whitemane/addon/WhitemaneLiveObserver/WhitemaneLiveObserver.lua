-- Public API reads only. No movement, spells, targeting, or network commands.
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
    local ok, a, b, c = pcall(fn, ...)
    if ok then return a, b, c end
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
    for i = 1, #bytes * 8 do
        local value = math.floor(bytes[math.floor((i - 1) / 8) + 1] / (2 ^ (7 - ((i - 1) % 8)))) % 2
        pixels[i]:SetColorTexture(value, value, value, 1)
    end
    status:SetText("Live observer: " .. (call(UnitName, "player") or "unavailable"))
end
panel:SetScript("OnUpdate", function(_, delta)
    elapsed = elapsed + delta
    if elapsed >= 0.2 then elapsed = 0; sample() end
end)
