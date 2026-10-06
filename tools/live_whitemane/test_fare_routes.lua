local site={id=1,world={instance=1,north=100,west=0}}
local org={id=23,name='Orgrimmar',world={instance=1,north=10,west=0}}
local ram={id=652,name='Ramkahen',world={instance=1,north=90,west=0}}
local exit={id=531,name='Dawnrise',world={instance=1,north=95,west=0}}
local A={nav={},db={taxiLinks={['23']={['531']=true},['652']={['531']=true}}},KALIMDOR=1}
function A.Call(fn,...) if type(fn)=='function' then return fn(...) end end
function A.nav.Distance(a,b)
    if a and b and a.instance==b.instance then return math.sqrt((a.north-b.north)^2+(a.west-b.west)^2) end
end
local base
function A.nav.Choose(...) return base end
function A.nav.CaptureTaxi() end
time=function() return 100 end
assert(loadfile('tools/live_whitemane/addon/FareRoutes.lua'))('CanopicHelper',A)
local player={world={instance=1,north=80,west=0}}
local function choose()
    base={site=site,origin=ram,exit=exit,score=20}
    return A.nav.Choose(player,{site},{org,ram,exit},{},'instant',{}, {})
end
local result=choose()
assert(result.origin==org and result.fareCopper==900 and result.site==site and result.exit==exit)
assert(result.fareSource:find('Runiir supplied',1,true))
A.db.taxiLinks['23']=nil
assert(choose().origin==ram) -- a quote alone cannot establish a reachable link
A.db.taxiLinks['23']={['531']=true}
A.db.liveTaxiFares={['652']={costs={['531']=800},at=99}}
result=choose();assert(result.origin==ram and result.fareCopper==800)
assert(result.fareSource=='observed public flight menu')
org.world.north=2000
A.db.liveTaxiFares=nil
assert(choose().origin==ram) -- no remote origin outside the supported approach
org.world.north=10
base={site=site,score=20}
assert(A.nav.Choose(player,{site},{org,ram,exit},{},'instant',{},{}).origin==nil)
A.nav.currentTaxi=23;A.nav.nodes={org,ram,exit}
C_TaxiMap={GetAllTaxiNodes=function() return {{nodeID=531,slotIndex=2,state=1}} end}
TaxiNodeCost=function(slot) assert(slot==2);return 875 end
UnitName=function(unit) assert(unit=='npc');return 'Doras' end
A.nav.CaptureTaxi()
assert(A.db.liveTaxiFares['23'].costs['531']==875 and A.db.liveTaxiFares['23'].master_name=='Doras')
C_TaxiMap=nil
A.nav.CaptureTaxi();assert(A.db.liveTaxiFares['23'].costs['531']==875) -- unknown menu preserves known fare
NumTaxiNodes=function() return 2 end
TaxiNodeName=function(slot) return slot==1 and 'Orgrimmar' or 'Dawnrise' end
TaxiNodeGetType=function(slot) return slot==1 and 'CURRENT' or 'REACHABLE' end
TaxiNodeCost=function(slot) return slot==2 and 850 end
A.nav.CaptureTaxi();assert(A.db.liveTaxiFares['23'].costs['531']==850)
for n=1,40 do A.db.liveTaxiFares[tostring(1000+n)]={at=n,costs={}} end
A.nav.CaptureTaxi()
local count=0;for _ in pairs(A.db.liveTaxiFares) do count=count+1 end
assert(count==32)
print('fare route public UI and same-destination policy checks passed')
