local callback,log
function CreateFrame()return {RegisterEvent=function()end,SetScript=function(_,_,fn)callback=fn end}end
local now=100
function GetTime()return now end
UIParent={GetEffectiveScale=function()return 1 end}
function GetScreenWidth()return 800 end
function GetScreenHeight()return 600 end
local units={player={guid='player'},target={guid='neutral',combat=false,targetsPlayer=true},
    nameplate1={guid='attacker',combat=true,targetsPlayer=true},
    nameplate2={guid='neutral',combat=false,targetsPlayer=true},
    nameplate3={guid='other_combat',combat=true,targetsPlayer=false}}
function UnitGUID(unit)return units[unit] and units[unit].guid end
function UnitName(unit)return UnitGUID(unit) end
function UnitCanAttack(_,unit)return unit~='player' and units[unit]~=nil end
function UnitIsDeadOrGhost()return false end
function UnitAffectingCombat(unit)return units[unit] and units[unit].combat end
function UnitIsUnit(unit)
    local base=unit:match('^(.-)target$')
    return base and units[base] and units[base].targetsPlayer
end
local plates={}
for i=1,3 do
    plates[i]={namePlateUnitToken='nameplate'..i,IsShown=function()return true end,
        GetCenter=function()return 400,300 end,GetEffectiveScale=function()return 1 end}
end
C_NamePlate={GetNamePlates=function()return plates end}
function CombatLogGetCurrentEventInfo()return unpack(log) end
assert(loadfile('tools/live_whitemane/addon/WhitemaneLiveObserver/CombatFacts.lua'))()
local facts=WhitemaneLiveCombatFacts()
assert(not facts.target_engaged and #facts.attackers==1 and facts.attackers[1].guid=='attacker')
log={100,'SPELL_DAMAGE',false,'other_combat','Caster',0,0,'player'}
callback(nil,'COMBAT_LOG_EVENT_UNFILTERED')
facts=WhitemaneLiveCombatFacts()
assert(#facts.attackers==2 and facts.attackers[2].guid=='other_combat')
units.target={guid='other_combat',combat=true,targetsPlayer=false}
assert(WhitemaneLiveCombatFacts().target_engaged)
callback(nil,'PLAYER_REGEN_ENABLED')
assert(not WhitemaneLiveCombatFacts().target_engaged)
print('combat facts: unrelated mobs excluded; actual attackers and combat end verified')
