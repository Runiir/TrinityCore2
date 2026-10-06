function CreateFrame() return {RegisterEvent=function()end,SetScript=function()end} end
assert(loadfile('tools/live_whitemane/addon/WhitemaneLiveObserver/Activity.lua'))()
local facts=WhitemaneLiveActivity().terrain_environment
assert(facts.schema=='public_environment_v1' and facts.indoors==nil and facts.submerged==nil)
IsIndoors=function() return false end
IsOutdoors=function() return true end
IsSubmerged=function() return false end
facts=WhitemaneLiveActivity().terrain_environment
assert(facts.indoors==false and facts.outdoors==true and facts.submerged==false)
IsIndoors=function() error('unsupported environment query') end
assert(WhitemaneLiveActivity().terrain_environment.indoors==nil)
print('public environment facts preserve false and unsupported values')
