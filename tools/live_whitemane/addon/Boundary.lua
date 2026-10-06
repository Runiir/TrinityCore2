-- Runs inside Canopic Helper's addon namespace. Public map perimeters only.
local _, A = ...
local data = A.liveBoundaryData
if not data or not A.direction then return end
A.liveBoundarySchema = 'first_exit_with_candidate_v2'
local function contains(polygon, n, w)
    local inside = false
    for i, a in ipairs(polygon) do
        local b = polygon[i % #polygon + 1]
        if (a[2] > w) ~= (b[2] > w) and n < a[1] + (w-a[2])*(b[1]-a[1])/(b[2]-a[2]) then
            inside = not inside
        end
    end
    return inside
end
local function clipped(polygon, origin, angle, length)
    if not contains(polygon, origin.north, origin.west) then return nil end
    local dn, dw = math.cos(angle)*length, math.sin(angle)*length
    local cuts = {0, 1}
    for i, a in ipairs(polygon) do
        local b = polygon[i % #polygon + 1]
        local en, ew = b[1]-a[1], b[2]-a[2]
        local determinant = dn*ew-dw*en
        if math.abs(determinant) > 0.0000001 then
            local an, aw = a[1]-origin.north, a[2]-origin.west
            local t, u = (an*ew-aw*en)/determinant, (an*dw-aw*dn)/determinant
            if t >= 0 and t <= 1 and u >= 0 and u <= 1 then cuts[#cuts+1] = t end
        end
    end
    table.sort(cuts)
    for i = 1, #cuts-1 do
        local midpoint = (cuts[i]+cuts[i+1])/2
        if not contains(polygon, origin.north+midpoint*dn, origin.west+midpoint*dw) then
            return math.max(0, cuts[i]*length-8)
        end
    end
    return length
end
A.liveClipDistance = clipped
local import = A.direction.Import
function A.direction.Import(text)
    if A.arrowFrame then A.arrowFrame.liveBoundary = nil end
    local ok, message = import(text)
    if not ok then return ok, message end
    local b = A.direction.bearing
    local site = b and data.sites[b.siteID]
    local _, build = GetBuildInfo()
    local matches = false
    for _, shown in ipairs(A.Call(C_ResearchInfo and C_ResearchInfo.GetDigSitesForMap, 1414) or {}) do
        if site and shown.researchSiteID == b.siteID and shown.poiBlobID == site.blob then matches = true end
    end
    local length = site and site.map == b.origin.instance and tonumber(build) == data.build and matches and
        clipped(site.polygon, b.origin, b.angle, b.length)
    if not length then
        A.direction.Clear()
        A.Print("Cannot verify this digsite boundary. Movement guide withheld.")
        return false, "Unverified digsite boundary."
    end
    b.boundaryVerified = true
    local lastObservation = A.db.surveyBearings and A.db.surveyBearings[#A.db.surveyBearings]
    if lastObservation then
        lastObservation.boundaryVerified = true
        lastObservation.candidateWorld = b.candidate and (b.candidate.world or A.nav.World(b.candidate))
        lastObservation.boundaryFirstExit = length < b.length
    end
    if length < b.length then
        b.boundaryClipped, b.unclippedLength, b.length = true, b.length, length
        local point = b.endpoint
        local p0 = A.nav.World({mapID=point.mapID,x=0,y=0})
        local px = A.nav.World({mapID=point.mapID,x=1,y=0})
        local py = A.nav.World({mapID=point.mapID,x=0,y=1})
        local ax, ay, bx, by = px.north-p0.north, px.west-p0.west, py.north-p0.north, py.west-p0.west
        local n, w = b.origin.north+b.north*length, b.origin.west+b.west*length
        local dn, dw, determinant = n-p0.north, w-p0.west, ax*by-ay*bx
        point.x, point.y = (dn*by-dw*bx)/determinant, (ax*dw-ay*dn)/determinant
        point.world = {instance=b.origin.instance,north=n,west=w}
        local history = A.db.surveyBearings
        local last = history and history[#history]
        if last then last.length, last.boundaryClipped, last.unclippedLength = length, true, b.unclippedLength end
    end
    if A.arrowFrame then A.arrowFrame.liveBoundary = {siteID=b.siteID,at=b.at,polygon=site.polygon,source=data.source} end
    A.nav.dirty = true
    A.PlanNavigation()
    if A.RenderNavigation then A.RenderNavigation() end
    return true
end
local route = A.direction.Route
function A.direction.Route(site, player)
    local result = route(site, player)
    if result and result.bearing.boundaryClipped then
        result.instruction = "Line capped 8 yards inside the digsite boundary.\nUse Survey again at the endpoint."
    end
    return result
end
