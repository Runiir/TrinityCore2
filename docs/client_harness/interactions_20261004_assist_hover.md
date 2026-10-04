# Assist, target-of-target and world hover

UI61 qualifies four operations in both clients: assist, select target-of-target,
world-player mouseover and the stock player tooltip. The checklist moves from
328 to 332 of 916 scoped operations.

The first assist precheck found a native peer target with an empty public
target-of-target. The bridge now translates UnitData.Target on object creation
and public updates. Packed GUIDs use the pinned parent 0, index 21 and payload
order. Either native GUID word triggers an update, including clearing to zero.
Both live clients now report the exact native peer target and select it through
the observed F binding and ordinary targettarget command. All 28 selection
checks, six attribution checks and 20 full restoration checks pass.

Both world hovers use a point chosen from a freshly reviewed scene and bound
to its SHA256. The stock tooltips visibly show the exact peer name, native
level, human race and warrior class. Public mouseover GUIDs agree. All 14 hover
checks and 20 full restoration checks pass. Original positions, party, targets,
resources, stats, spells/actions, pose/AFK and bars restore in both cohorts;
each removes four temporary teleport rows. Earlier party-frame hover failures
remain open. Their cause is not established by the passing world hover.

The initial wire regression selection failed 10 checks and passed one. After
the repair, four public-visibility checks failed because I reused an owner-only
test reader. The corrected selection passes all 43 tests. All failures are
retained. The single-job bridge build took 4.64 seconds and peaked at
358080 KiB RSS. Only the bridge restarted; the native worldserver and both
game client lifetimes stayed unchanged.

Two later fixture failures are also retained. The client autocompleted an
invitation with its realm suffix, so the exact-text guard refused submission.
A separate recovery cancelled that exact entry and passed 24 restoration
checks. The fixture now sends the observed full same-realm name. I also removed
a redundant selection of an already staged target, which correctly emitted no
new client request. The fresh corrected assist04 cohort passes in both clients.

DVC61 verifies 46 JSON receipts and 218 attributed images. Its archive is
592279728 bytes, SHA256
a1eae4b959f5a4166117b853bc951b114ef7bd4e652c0919989767ba871f8a73.
About 16.29 GiB of RAM was available at closure, with no recent memory pressure.
Both clients remain on HDMI-1. These checks cover idle owned party players at
levels 85 and 1; combat, enemy, raid and other target variants remain open.
