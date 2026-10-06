local A = {liveBoundaryData={sites={}},direction={Import=function() end,Route=function() end}}
assert(loadfile("tools/live_whitemane/addon/Boundary.lua"))("CanopicHelper",A)
local square={{0,0},{20,0},{20,20},{0,20}}
assert(math.abs(A.liveClipDistance(square,{north=10,west=10},0,100)-2)<0.00001)
assert(A.liveClipDistance(square,{north=10,west=10},0,5)==5)
assert(A.liveClipDistance(square,{north=30,west=10},0,5)==nil)
local concave={{0,0},{20,0},{20,5},{5,5},{5,20},{0,20}}
assert(A.liveClipDistance(concave,{north=2,west=2},math.pi/4,100)==0)
local u={{0,0},{100,0},{100,100},{70,100},{70,30},{30,30},{30,100},{0,100}}
assert(A.liveClipDistance(u,{north=15,west=70},0,70)==7)
print("5 boundary checks passed, including an inside endpoint after a concave exit/reentry")
