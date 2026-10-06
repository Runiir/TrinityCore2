-- Public flight-menu fares refine the helper's instant-travel origin choice.
-- This file reads UI state and plans routes. It never selects a taxi or casts.
local _, A = ...
local N = A.nav
if not N then return end
local choose, capture = N.Choose, N.CaptureTaxi
local quotes = {[23] = {[531] = 900}, [652] = {[531] = 10000}}

local function fare(origin, exit)
    local book = A.db and A.db.liveTaxiFares
    local entry = book and book[tostring(origin)]
    local observed = entry and entry.costs[tostring(exit)]
    if type(observed) == 'number' then return observed, 'observed public flight menu' end
    local supplied = quotes[origin] and quotes[origin][exit]
    if supplied then return supplied, 'Runiir supplied fare quote; confirm at the flight master' end
end
N.LiveFare = fare

function N.CaptureTaxi(...)
    local result = capture(...)
    local origin = N.currentTaxi
    if not origin or not A.db then return result end
    local costs = {}
    local rows = A.Call(C_TaxiMap and C_TaxiMap.GetAllTaxiNodes, A.KALIMDOR) or {}
    if #rows == 0 then
        local names = {}
        for _, node in ipairs(N.nodes or {}) do
            if names[node.name] ~= nil then names[node.name] = false else names[node.name] = node.id end
        end
        for slot = 1, math.min(256, A.Call(NumTaxiNodes) or 0) do
            local id = names[A.Call(TaxiNodeName, slot)]
            if id and A.Call(TaxiNodeGetType, slot) == 'REACHABLE' then
                rows[#rows + 1] = {nodeID = id, slotIndex = slot, state = 1}
            end
        end
    end
    local count = 0
    for _, node in ipairs(rows) do
        if node.nodeID and node.slotIndex and node.state == 1 and count < 256 then
            local cost = A.Call(TaxiNodeCost, node.slotIndex)
            if type(cost) == 'number' and cost >= 0 then
                costs[tostring(node.nodeID)] = cost
                count = count + 1
            end
        end
    end
    A.db.liveTaxiFares = A.db.liveTaxiFares or {}
    local book = A.db.liveTaxiFares
    if count > 0 then
        book[tostring(origin)] = {costs = costs, at = time(), master_name = A.Call(UnitName, 'npc')}
    end
    local keys = {}
    for key, value in pairs(book) do keys[#keys + 1] = {key = key, at = value.at or 0} end
    table.sort(keys, function(a, b) return a.at > b.at end)
    for index = 33, #keys do book[keys[index].key] = nil end
    N.dirty = true
    return result
end

local function journeys(player, shortcuts, portals)
    local result = {{world = player and player.world}}
    for _, shortcut in ipairs(shortcuts or {}) do result[#result + 1] = {world = shortcut.world, shortcut = shortcut} end
    local function extend(journey)
        if journey.portals and #journey.portals >= 2 then return end
        for _, portal in ipairs(portals or {}) do
            local seen = false
            for _, old in ipairs(journey.portals or {}) do if old.key == portal.key then seen = true end end
            local distance = not seen and N.Distance(journey.world, portal.from.world)
            if distance then
                local path = {}
                for _, old in ipairs(journey.portals or {}) do path[#path + 1] = old end
                path[#path + 1] = portal
                local nextJourney = {world = portal.to.world, shortcut = journey.shortcut, portals = path,
                    key = (journey.key and journey.key .. ':' or '') .. portal.key,
                    distance = (journey.distance or 0) + distance,
                    interactions = (journey.interactions or 0) + 150,
                    approximate = journey.approximate or portal.approximate}
                result[#result + 1] = nextJourney
                extend(nextJourney)
            end
        end
    end
    local initial = #result
    for index = 1, initial do extend(result[index]) end
    return result
end

function N.Choose(player, sites, nodes, shortcuts, mode, prepared, portals)
    local best = choose(player, sites, nodes, shortcuts, mode, prepared, portals)
    if not best or mode ~= 'instant' or not best.origin or not best.exit then return best end
    local cost, source = fare(best.origin.id, best.exit.id)
    best.fareCopper, best.fareSource = cost, source
    best.farePolicy = 'lower known fare between origins for the same site and taxi exit; approach distance breaks ties'
    if cost == nil then return best end
    local site, exit = best.site, best.exit
    for _, journey in ipairs(journeys(player, shortcuts, portals)) do
        for _, origin in ipairs(nodes) do
            local links = A.db and A.db.taxiLinks and A.db.taxiLinks[tostring(origin.id)]
            local price, evidence = fare(origin.id, exit.id)
            local approach = N.Distance(journey.world, origin.world)
            -- Match the live controller's supported approach range. A fare
            -- quote does not establish discovery or a reachable connection.
            local finalDistance = N.Distance(exit.world, site.world)
            if links and links[tostring(exit.id)] and price and approach and approach <= 1500 and finalDistance then
                local distance = (journey.distance or 0) + approach + finalDistance
                local score = distance + (journey.shortcut and 300 or 0) + (journey.interactions or 0) + 150
                if price < best.fareCopper or price == best.fareCopper and score < (best.score or math.huge) then
                    best = {site = site, exit = exit, origin = origin, shortcut = journey.shortcut,
                        portals = journey.portals, portalKey = journey.key,
                        approximate = journey.shortcut and journey.shortcut.approximate,
                        portalEstimated = journey.approximate, distance = distance, score = score,
                        fareCopper = price, fareSource = evidence, farePolicy = best.farePolicy}
                end
            end
        end
    end
    return best
end
