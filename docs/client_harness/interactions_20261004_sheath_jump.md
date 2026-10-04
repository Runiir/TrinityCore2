# Standing weapon cycle and flat-ground jump

UI59 qualifies the scout's ordinary Z sheath binding. Settled owner and peer
frames show its sword in hand in native state 1 and back in state 0. All 55
native cycle checks pass across both characters, with 20 restoration checks.
The heavy primary's precise weapon rendering remains unclaimed.

Both characters visibly jump through SPACE and land idle at the original
flat-ground position. Exact native requests and peer broadcasts agree.
Observed peer height rises by about 1.5664 yards. All 26 jump checks and
20 restoration checks pass. Positions, party, pose/AFK, bars, native resources,
stats, saved spells/actions and temporary teleport rows restore.
The checklist moves from 319 to 321 of 916 scoped operations.

The first standalone sheath retests failed because both characters were
seated/AFK and the client ignored Z without sending a request. The adapter
now requires standing. The first jump cohort failed my positive-speed
assumption: the captured client field is negative. The corrected check
requires finite nonzero speed plus actual peer height gain. Its regression
selection passes 15 tests after correcting three tuple-copy fixture errors.
All original failed trials and their restorations remain unqualified.

The DVC59 archive is 488500964 bytes, SHA256
fd3ad7ee065ef733b92f9db646c3a0d7e8a4e57305f23287a8c1f9ed4c738184.
Both clients remain on HDMI-1 at about 15 FPS, with 16.45 GiB of RAM available
at batch closure. Native worldserver, bridge and client lifetimes are unchanged.
