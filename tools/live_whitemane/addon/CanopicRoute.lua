-- Read-only adapter for the installed Canopic Helper's public navigation facts.
local _, A = ...
local function point(value)
    if not value then return end
    local world = value.world or A.nav.World(value)
    if not world then return end
    return {map_id=value.mapID,instance=world.instance,north=world.north,west=world.west}
end
function WhitemaneLiveCanopicRoute()
    local route = A.nav and A.nav.route
    if not route then return {available=false} end
    local kind = route.pendingLoot and "pending_loot" or route.digging and "dig" or
        route.shortcut and "shortcut" or route.portal and "portal" or route.origin and "taxi" or "site"
    local result = {available=true,kind=kind,text=route.text,instruction=route.instruction,
        fare_copper=route.fareCopper,fare_source=route.fareSource,fare_policy=route.farePolicy,
        route_facts_schema='instant_fare_routes_v2',boundary_facts_schema=A.liveBoundarySchema,
        target=point(route.target),taxi_open=not not A.nav.taxiOpen,current_taxi=A.nav.currentTaxi,
        site=route.site and {id=route.site.id,name=route.site.name,point=point(route.site)},
        session_finds=A.session and A.session.finds,session_sites=A.session and A.session.sites,
        known_portals={},fare_options={}}
    for _,portal in ipairs(A.nav.Portals() or {}) do
        result.known_portals[#result.known_portals+1]={key=portal.key,destination=portal.destination,
            from=point(portal.from),to=point(portal.to)}
    end
    if route.shortcut then
        result.shortcut={kind=route.shortcut.kind,id=route.shortcut.id,label=route.shortcut.label,
                         point=point(route.shortcut)}
    end
    if route.portal then
        result.portal={key=route.portal.key,destination=route.portal.destination,
                       from=point(route.portal.from),to=point(route.portal.to)}
    end
    if route.origin then
        local book=A.db.liveTaxiFares and A.db.liveTaxiFares[tostring(route.origin.id)]
        result.origin={id=route.origin.id,name=route.origin.name,master_name=book and book.master_name,point=point(route.origin)}
    end
    if route.exit then result.exit={id=route.exit.id,name=route.exit.name,point=point(route.exit)} end
    if route.exit and A.nav.LiveFare then
        for _,node in ipairs(A.nav.nodes or {}) do
            local links=A.db.taxiLinks and A.db.taxiLinks[tostring(node.id)]
            local cost,source=A.nav.LiveFare(node.id,route.exit.id)
            if links and links[tostring(route.exit.id)] and cost and #result.fare_options<32 then
                result.fare_options[#result.fare_options+1]={origin_id=node.id,origin_name=node.name,
                    origin_point=point(node),exit_id=route.exit.id,fare_copper=cost,fare_source=source}
            end
        end
    end
    return result
end
