# Mounted archaeology and Outland travel

## Scope and isolation

These trials use `codex/442-compatibility-audit` in
`/home/runiir/Games/trinity-442-compatibility`, private `client442_*` databases,
and the owned lab under `/home/runiir/.local/share/trinity-client442-lab`.
The mainline raid worldserver and its databases remain running independently.
Every client launch verifies the owned game window on HDMI-1.

Harnessone has normal account permissions, level 85 epic equipment, professions,
Master Riding and flying mounts. Instant taxi paths are enabled in the private
native worldserver configuration. Inputs are real keys and mouse actions sent
only to the owned game window. Trials do not inject movement packets, area
triggers, GM transfers, combat commands or private next-find coordinates.

## Decisions and observations

The frozen Laya encoder has two adapted typed decision heads:

| Task | Endpoint | Head SHA-256 | Synthetic held-out test |
| --- | --- | --- | --- |
| Archaeology v2 | `http://127.0.0.1:8002/v1/systemone` | `c9d97c846d8ff7c7b4c072c5bb8a61e95ea89c6755f368d9341c32f71c4d05b9` | 418/420 |
| Travel v3 | `http://127.0.0.1:8003/v1/systemone` | `b9a058ab4c6ea77ffffca6e40e3650da65a699a051514738f6c5472774f0eb46` | 598/600 |

All seven archaeology actions and ten travel actions are presented to their
respective heads. Code converts each selected action into bounded physical
input and applies safety checks. The model consumes text facts. Screenshot
pixels supply normal addon state and tooltips; the model does not interpret raw
scene images. Ordinary packets from the owned authenticated character supply
visible objects, telescope bearing and colour, player elevation, taxi menus,
transfers and creature state. Geometry and route arithmetic use public site
polygons, taxi graphs and static MMAP data.

Synthetic scores measure agreement with the declared policy. They do not
establish independent map discovery, questing competence, calibrated confidence
or the model's added value over the same controller with a rule policy.

## Outland repairs and live evidence

The correct Outland return trigger is 4352. Trigger 4356 has no native return
teleport. The bridge supplies the installed client's cached AreaTrigger records
through `SMSG_HOTFIX_CONNECT`. A real 60895 world-port acknowledgement arriving
on the authenticated realm connection is accepted only for its owned character
and pending native transfer.

At 4352 the physical client stopped 0.079 yards short of the original box.
The lab alone expands the matched client and native width by two yards, one on
each side. Map, phase, native trigger proximity and transfer sequencing still
apply. Shared DBC files are unchanged. `portal_contact_geometry.json` records
the source, installed hashes and exact field changes.

Episode 24 completed both real transfers with Laya-controlled physical travel:
Outland to Eastern Kingdoms through 4352, then back through 4354. The ordinary
client area-trigger and native transfer packets are retained in
`travel_portal_validation.json`. No synthetic trigger packet was submitted.

Flat landing points now use MMAP detail triangles, reject slopes above 20
degrees and reject ground covered by another surface. Archaeology landings must
also share a complete ground path with the current site floor. This excludes
the disconnected Bonechewer building roof that previously allowed Survey casts
but produced no reachable instrument or find. Entire local walk corridors and
mounted survey segments must stay inside the assigned public polygon.

For red or yellow instruments the controller mounts and flies to a progressive
public bearing waypoint. A clipped in-site survey ray supplies the flight goal;
it does not require the shallow ground-walking corridor to cross a hillside.
Flat landing and ground-component checks still apply. The search includes shorter
steps and nearby 45-degree offsets, and rejects landings without at least 1.5
yards of progress along the observed bearing. Episode 66's yellow approach
had stopped because its longer probes missed a safe shorter landing. The
revised planner passes that exact public-geometry regression.
Episode 40 had stopped
on a Coilskar slope where a connected flat destination exists 16 yards below
the character but the filtered walking path is unavailable. That exact terrain
fixture now passes the mounted-planning regression. Green instruments use unmounted walk/swim paths. Find collection
uses the normal tooltip to locate a right-click. If the character overlaps the
visible find, it first walks to a nearby dry stance at the find's elevation;
standing directly over the artifact previously produced no interaction packet.
Find clicks hold the physical mouse button for 0.2 seconds, spanning multiple
frames at the observed 15 FPS. Episode 41's two 0.05-second clicks sent no use
packet; episode 42 then collected the Draenei find for seven fragments. The
latter trial stopped on a 38.7-degree landing that kept sliding, which prompted
the stricter 20-degree standing-surface limit.

Episodes 27, 28 and 29 collected all three Hellfire Basin finds, awarding 5, 4
and 8 Orc fragments. Episode 29 observed the completed site 343 replaced by
377, automatically travelled to Honor Hold, selected the normal gossip flight
option, took the instant taxi to Allerian Stronghold (node 121), then flew to
Bonechewer Ruins. This was one continuous automatic intersite journey. The
earlier Hellfire finds occurred across repaired trials.

Bonechewer combat exposed unmapped client selection and melee attack messages.
The bridge now translates owned visible targets, native attack start/stop, and
ongoing creature health and flag updates. A bounded keyboard melee safety guard
can clear incidental low-level attackers before Survey resumes. This guard is
explicitly recorded as code-controlled recovery, not learned Laya combat.
It can type the normal local `/targetexact` command using an ordinary queried
creature name, step back from an obstructed approach, and walk a ground route
toward a genuine ranged attacker. It retains an active melee attack rather than
repeatedly toggling it. These are physical client inputs, not backend attacks.
Native monster-move start positions keep its creature observations current.
Ordinary ground chase, stop, packed path and facing splines are also translated
to the pinned Classic format, so normal client targeting follows moving mobs.
Transport, animation and parabolic spline variants remain unsupported.
The wire layout follows the pinned
[WPP Classic movement parser](https://github.com/TrinityCore/WowPacketParser/blob/28fc3d194b22063ce8e94d2ed7235ca98ca51ef2/WowPacketParserModule.V4_4_0_54481/Parsers/MovementHandler.cs).

Trace files rotate at eight MiB instead of silently stopping at sixteen MiB.
Incremental observers retain their offsets across renames, and closed evidence
includes every retained segment. Rotation preserves actual packet records;
it does not synthesize state.

Blocked descents get at most three lateral flight probes to another flat point
connected to the original floor. The actual input and observed displacement are
recorded. Aggro avoidance also requires a connected flat landing, and its goal
is frozen during descent. A mount cast interrupted by newly observed combat
returns to the combat guard instead of treating the key press as a successful
mount. Travel steering tolerates the observed 15 FPS turn quantum; the earlier
0.06-radian threshold oscillated between roughly 1.44 and 1.65 radians on a real
flight. The new 0.12-radian threshold passed the captured-state regression.

Episode 43 exposed a green-lantern wall approach whose coarse MMAP route started
1.5 yards above the actual client feet. The trial was interrupted after repeated
small, ineffective moves. Ground routing now compares that surface with observed
feet, excludes nearby raised polygons in its local query, and retains up to eight
such observations for the current find. The route approaches the lower floor
and goes around the obstruction. Episode 44 followed this detour on foot and
collected Coilskar's final find, replacing site 387 with 345. This recovery never
mounts at green and never changes shared MMAP tiles.

Episode 44 then collected all three Eclipse Point finds, awarding 6, 6 and 9
Draenei fragments, and observed site 393 replaced by 371. It automatically used
Wildhammer Stronghold's normal flight menu to take the instant taxi to Shattrath
(node 128), then flew to Grangol'var. The earlier completed Coilskar site had
only one remaining find at this trial's start, so this is one fresh full site,
not two fresh full sites.

Repeated green-bank approaches at Grangol'var exposed a detour that first went
south before returning north. Replanning each short Survey step reversed that
path. The controller now retains its public destination and corners until the
detour is finished. Episode 45 collected two Grangol'var finds for 6 and 4 Orc
fragments. A measured 1.08-yard bridge step blocked its third approach. A hop is
allowed only after failed physical displacement, on dry ground, within four
yards, with a predicted rise between 0.5 and 1.25 yards. Taller obstacles still
require a detour. The raised-obstruction filter preserves this low bridge.
Native melee reach uses its five-yard minimum and full observed XYZ distance;
episode 46 had incorrectly requested a walking path to an attacker already in
reach.

Episode 48 stopped beside water because routes excluded `NAV_WATER`. Explicit
walk/swim queries now admit ground and clean water (flags 1 and 4), excluding
magma/slime and off-mesh links. Ground and water can overlap near the shoreline,
so dry endpoints also reject adjacent water at or above their elevation. The
public Survey bearing can extend up to 56 yards to a reachable dry bank, inside
the assigned polygon. A water corridor finishes before the next Survey. The
adapter observes normal `IsSwimming()` pixels, uses bounded keyboard advances,
and stops on combat, health loss, boundary crossing or repeated blocked moves.
Mount landings and ordinary ground-only callers retain their solid-ground filter.
Regression fixtures cover the former failure position and a pond-to-shore route.

Episode 49 crossed the bridge and reached the third artifact. Its gathering
cast was interrupted by incidental combat. After clearing attackers the fixed
mouse-search area missed the find, which was left of the character. Collection
now faces the ordinary visible artifact before backpedalling and searches a
wider part of the 3D view. It clears a matching tooltip and verifies the same
cursor point again, avoiding stale names while `GameTooltip` fades.
Episode 50 showed that this fade could last longer than the original 0.7-second
clear wait. The addon now exports tooltip text only at full opacity, and the
input adapter polls for clearance before confirming a candidate point. A mouse
hover timing diagnostic outside the closed model trials is retained separately.

Episode 51 completed a real unmounted water crossing, recording two addon
swimming observations and a dry arrival before Survey resumed. Its next find
appeared on a bank. The old backward approach dropped the character about six
yards below it. Find positioning now selects a complete dry corridor no longer
than eight yards, a stance within 1.25 yards of the visible find's elevation,
and actual interaction distance at most five yards. The fixed bank fixture
passes. Survey also checks public water geometry because touching a shallow pond
floor can clear `IsSwimming()` while the feet remain submerged. A bounded shore
move completes before the selected cast, including when there is no telescope.

Episode 52 completed the previously partial Grangol'var site for five Orc
fragments, including real swimming and subsequent collection, then flew to Bleeding
Hollow. It collected that fresh site's three finds for 7, 6 and 4 Orc fragments,
observed 375 replaced by 391, and automatically flew to Laughing Skull in Nagrand.
The first Nagrand approach landed on an unmapped stone structure at Z58.388,
above the intended ground at Z46.946. The input wrapper had described this as
destination ground using horizontal proximity and not-flying state, allowing a
dismount before the final height check stopped the trial. This was an observation
mapping error, not evidence that the model independently recognized the wrong floor.

Grounded flight proximity now requires the actual landing-height condition.
Local survey flights use a two-yard height tolerance. A mounted character stopped
above its intended floor gets at most three physical lift-and-sideways probes
toward a connected flat landing inside the public site. The input, original floor
and observed elevation remain in the recovery receipt. Restarted loops also
check elevation before treating an already-in-site character as ready to Survey.
The raised-stone fixture now rejects both false destination-ground facts and
premature arrival. It verifies a connected alternative landing below Z50.

A later geometric re-audit found that episode 52's first shore check accepted
feet 0.54 yards below the mapped water surface after `IsSwimming()` cleared.
Its native fragment collection is still confirmed, but the old addon-only
"dry arrival" label was incorrect. Episode 51's arrival is above the water.
The archive remains unchanged; `water_arrival_reaudit.json` retains both exact
end positions and corrected derived labels. Arrival now checks actual elevation
within two yards of its dry goal and rejects a water surface above the feet,
so movement continues toward shore before Survey resumes.

Episode 53 collected all three fresh Laughing Skull finds for 9, 5 and 8 Orc
fragments, observing site 365 replaced by 355. Its second find landed on the
stone structure twice. The bounded mounted recovery lifted and moved sideways,
then landed at Z46.697, dismounted and resumed Survey before collecting the find.
This is a live recovery outcome, with no manual gameplay intervention. The next
automatic journey reached Telaar but stopped while locating Furgu: the old
mouse search began at y220 and spent its budget near the center of the view,
while the close NPC appeared higher. The search now covers the central vertical
strip from y160, clears and confirms the exact tooltip point, then holds its
right click for 0.2 seconds. It does not use teacher mouse coordinates.

Episode 54 found Furgu, but its clicks were outside the client's interaction
range. The flight landing's five-yard horizontal tolerance left the character
six yards from the vendor. The bounded ground approach now follows a dry public
corridor no longer than sixteen yards, verifies actual XYZ distance at most four
yards, and stops on blocked or unsafe movement. Episode 55 has already followed
that approach, opened Furgu's normal gossip and taxi menus, taken the instant
Telaar-to-Honor Hold taxi (node 100), and landed at the next assigned site.

Episode 55 collected two Hellfire Citadel finds for five and eight Orc
fragments. Its third approach first stopped on a tall pillar, recovered toward
the pit floor, then slid just outside the three-yard local arrival radius. It
stopped after three returns to ascent. Nearby floor-mismatch recovery now covers
twelve yards after descent begins. A grounded mount already on the correct floor
can finish a dry corridor of at most sixteen yards with short keyboard advances,
checking actual floor height, combat, health and the assigned polygon. This
correction is recorded as code-controlled navigation rather than a model decision.

Episode 56 collected Hellfire Citadel's remaining find for five fragments,
observed site 345 replaced by 359, and automatically used Honor Hold's normal
gossip and taxi menus to reach Area 52 (node 122), then flew to Arklon Ruins
(site 355). The first Arklon find spawned within the assigned polygon and at
the character's elevation. Its tooltip was obscured by an Artifact Seeker's
body; a separate mouse-hover-only diagnostic identified the observed NPC name
checksum, with no collection click or teacher annotation. Collection now zooms
through real mouse-wheel inputs and uses at most three distinct dry stances,
each within normal artifact reach. Each view gets a twelve-second tooltip search.
Every view, route and outcome is retained even when localization fails.

Episode 57's closer camera view localized the first Arklon find and collected
eight Draenei fragments. It then exposed an overly broad dry-Survey guard: a
legacy ground-height discrepancy at dry ruin ledges triggered unnecessary shore
moves, and the second such move stopped on an obstruction. Shore recovery now
requires observed swimming or a public `NAV_WATER` surface above the actual feet.
The helper tests both dry Arklon positions and the genuine submerged pond-floor
fixture. A ground-height discrepancy alone no longer classifies a dry ruin as wet.

The unnecessary shore move left episode 58 at a mesh corner with no connected
forward-bearing route. Nearby dry side/back corridors exist, so the walking
adapter now tries at most four short, unmounted probes toward those corridors.
Each advance is at most 0.2 seconds, with observed displacement, floor change,
health and whole-segment polygon checks. Episode 59's first probe moved 1.68
yards and stepped down 0.94 yards, then stopped on a transient falling flag.
A subsequent read-only screenshot confirmed that it settled, unmounted and dry.
The guard now waits at most 2.5 seconds for that short step to settle before
accepting it. It retains every probe and failure. It does not mount at green.

Episode 60 resumed normal unmounted green-lantern walking and exposed a separate
collection search gap. Its artifact was visibly centered above y=240 in all three
dry stances, while the old radial search spent its twelve-second budget around
y=370. The cursor now covers the central vertical strip from y=160 to y=512
before widening. It still clears and reconfirms the game's ordinary tooltip;
no human pixel annotation is supplied to the run.

Episode 61 localized the previously missed artifact on its first view and
collected it. The next find spawned after normal mounted yellow moves and
unmounted green approaches, but an Artifact Seeker engaged during the collection
stance. A healthy, in-bounds combat interruption now returns to the existing
bounded physical combat recovery and then retries the find. Death, low health,
boundary violations and other navigation failures still stop the run. An aborted
approach is recorded separately from a completed collection click; initial and
alternate loot stances retain their partial inputs and observed positions.

Episode 62 collected Arklon's last find, completed all three Farahlon finds for
20 Draenei fragments, and automatically used Area 52 to Stormspire (139) and
Stormspire to Altar of Sha'tar (140) taxis. Its first Baa'ri collection spell
failed during combat; the 60-second visible artifact expired during recovery
and the next cursor search. The adapter now checks the same ordinary owned
object-removal packets during localization and returns to Survey when the find
expires. It permits at most two such retries per find. A physical click followed
by combat without a fragment award is recorded as interrupted. The central
cursor scan also uses eight-pixel steps for small interaction shapes.

Episode 63 collected Baa'ri's first find. Its next green approach stopped with
zero accepted recovery candidates. The public dry side corridor rises only
1.37 yards across four yards, but the candidate filter's 1.25-yard limit was
stricter than the existing 1.5-yard observed probe guard. They now match.
The next trial tested short walking probes with the matching height limit.

Episode 64's first probe resumed movement, but another contour-side probe slid
roughly nine yards down. The run stopped; a read-only observation confirmed it
settled dry with full health. The small endpoint rise was misleading: the actual
detail surface is inclined 43.8 degrees sideways. Walking and recovery now sample
the specific proposed movement segment every 0.7 yards and reject detail slopes
above 35 degrees before pressing forward. Nearby edge projections may be within
two yards; detail triangles within 0.05 yards of a projected edge resolve float
rounding. Landing's existing 20-degree limit remains separate.

Episode 65 stopped at a navigation-mesh gap after several short on-foot recoveries.
The grounded player and the last ordinary telescope base were 2 yards apart and
only 0.49 yards different in height, while the old mesh had no matching column.
When no mapped recovery is accepted, the adapter may probe toward that observed
ground sample if it is at most 20 seconds old, 1 to 3 yards away, within 0.75
yards of the feet, dry and inside the assigned polygon. All actual movement,
falling, health and boundary guards remain. This uses the telescope's base,
not the unknown find. Ordinary mapped side detours are retained to their endpoint
instead of discarding them after one short probe.

## Validation and experiment history

The authentication, world, observation, terrain, collection and combat suite
passes 156 tests. A first broad slope-filter attempt failed six tests by rejecting
previously working bank/water routes and one old side-slope expectation. It was
reverted in favor of checking each actual movement segment. One later test
exposed an overly narrow surface-projection radius at Arklon's known corner;
the corrected full suite passes, including the earlier water and bridge fixtures.
Both failed XML files are retained. The combat-interruption change initially failed one older test
that expected the previous error wording; its failed XML is retained alongside
the corrected full-suite result. The new tooltip test initially failed because its test
environment lacked Pillow; the dependency was added and the full suite passed.
That failed XML is retained. The first observation-refactor check failed collection because
of an indentation error; the repaired full suite passed. Both its failed XML
and the final XML are retained. Earlier missing-Pillow collection and mock-route
fixture failures are retained with their corrected results.
The first stricter-slope check also failed two old terrain expectations: a
column now deliberately rejected, and a landing displaced to a gentler point.
The fixtures were updated to test those safety outcomes; its failed XML is retained.

Episodes 07 through 87 preserve unsuccessful steps, including missing portal
hotfixes, realm-connection transfer rejection, an orphan return trigger, portal
contact mismatch, steep landing cycles, overlapping loot clicks, disconnected
roof surveying, unsuccessful combat retreats, terrain-obstructed targeting,
a ranged attacker beyond the original melee approach limit, interrupted mount
casts, changing landing goals, steering quantization, and a walking-path
prerequisite that incorrectly blocked mounted movement, replanned bank detours,
low bridge steps, unnecessarily requested melee approaches, excluded water,
and interrupted gathering followed by a missed tooltip, raised-floor proximity
errors, a missed flight-master tooltip, an out-of-range vendor click and landing
slides outside the local arrival radius and artifact tooltip occlusion by a
creature's body, dry ledges incorrectly treated as submerged, an unavailable
forward route at a mesh corner, a premature stop during a small step down and
an artifact above the bounded cursor search's covered region and combat starting
inside a collection approach, artifact expiry during combat recovery and a
a side corridor rejected by inconsistent height limits.
Episode 64 also records the subsequent sideways slide despite a small endpoint rise.
Episode 65 records the grounded patch missing from the old mesh's column.
Episode 66 records the longer flight probes missing a shorter safe landing.
Episode 67 collected seven Draenei fragments from that formerly blocked approach.
Its next flight stopped roughly 1.8 yards short of the selected flat point,
on a 36.9-degree side surface about four yards lower. The previous recovery
handled only ground above the target, so it returned to ascent three times.
Recovery now handles either direction of floor mismatch and local survey
flights use a 1.5-yard arrival radius. The two-yard height tolerance remains.
Episode 68 collected Baa'ri's last find for nine fragments and observed its
replacement by Bonechewer (377). Its next journey stopped during planning
because Dragonmaw Fortress's arithmetic center had no accepted flat landing.
The initial site-arrival repair searched nearby public points within the polygon
on the same ground component, rejecting submerged surfaces. That first Dragonmaw
candidate was later rejected by the supporting-surface checks below. Site and survey
arrivals both use a 1.5-yard horizontal radius and two-yard height tolerance.
Episode 69 reached Dragonmaw but produced no instrument after Survey. Ordinary
packets confirm two completed Survey spells and one cooldown rejection. The
arrival's nominal flat detail face overlapped a 53.1-degree supporting surface
at the actual feet. Landing now rejects overlapping steep faces and requires a
dry 1.5-yard surrounding patch: center slope at most 20 degrees, perimeter at
most 35 degrees, and height difference at most 1.25 yards. Initial site arrivals
do not require connection to an unverified arithmetic-center surface. A broad
mesh floor fifteen yards away and roughly 38 yards below that center was the
next candidate; later raw-terrain validation rejected it as buried.
Local survey flights retain their known-floor connection requirement.
The first patch-search suite and the first overlap-filter suite each failed two
tests. One old fixture accepted a Baa'ri point whose supporting column contains a
52-degree face; it now explicitly expects rejection. The Dragonmaw search was
repaired by removing the unverified-center connection requirement. Both failed
XMLs remain alongside the corrected full-suite result.
Recent telescope ground samples cannot override a known detail slope above
35 degrees, even if the sample's elevation is close to the player's feet.
Episode 70 exposed a restart-readiness check that accepted the old steep ledge
because its elevation matched the mesh. Readiness now checks actual detail slope
and horizontal projection before resuming Survey, while preserving swimming.
Episodes 71 and 72 attempted the lower mesh floor but slid on the hillside and
remained flying. A normal Survey ground-contact probe was implemented in 72;
it never activated because the client correctly continued reporting flight.

Public raw MAPS terrain explains this contact: the proposed floor at
(-4183, 400.416656, 49.1118813) is underneath terrain at Z74.45959. After sliding
to approximately (-4177.74, 401.22, 60.72), raw terrain is Z60.19745, matching
the observed client feet. This is evidence of an unsuitable navigation-mesh
candidate, not proof that the client and server terrain versions disagree.
The adapter now interpolates the native MAPS height triangles and probes VMAP
model collision. Both are public static, read-only data. Every landing patch
must match their highest supporting surface within 1.5 yards. Initial site
arrivals and their hostile-avoidance alternatives also match raw terrain, which
excludes detached roofs. Local survey flights retain their known-floor connection.
The new regression checks both the buried floor and the raised Dragonmaw roof.
The first raw-terrain regression failed due to an invalid pytest approximation
argument; its failed XML is retained with the corrected full-suite result.
Episode 73 landed on the corrected ground, followed red/yellow instruments by
flight, approached green instruments on foot, and collected eight Orc fragments
through normal native loot/currency replies. It later stopped during the second
dig: incidental-combat recovery had moved the character under a model at Z37.916,
above feet at Z30.728. The old lateral-flight guard required ground ten yards
below the character and had no suitable exit from this settled ground position.
A grounded overhead-collision guard now selects a connected dry walking exit,
checks VMAP rays at body heights 0.5 and 1.7 yards, dismounts, and uses short
on-foot advances before the model mounts again. An already hovering mount first
descends to the nearby verified dry floor, with clear body-height collision rays,
and waits for settled ground before dismounting. It retains success and failure
receipts, actual observations, health/combat/falling guards and site boundaries.
This applies to a flight leg; green survey approaches still remain on foot.
Episode 74 descended, dismounted on settled ground and walked toward the selected
exit, then stopped with no collection when the actual arrival's surrounding patch
still touched overhead collision. Exit selection now requires a 2.5-yard clear
patch, covering the one-yard steering tolerance plus the 1.5-yard takeoff patch.
An early failed patch check continues the bounded walk toward its validated goal.
Episode 75 resumed ordinary flight from the partial ground exit, then stopped in
incidental combat after 31 failed name selections. `/targetexact Enslaved Netherwing
Drake` selected a different living drake roughly 31 yards away and 28 yards higher,
while the actual attacker was only 2.56 yards away. Names are now used only when
unique among observed units and no more than two exact-selection attempts fail.
Otherwise the physical guard clears an unsuitable target and presses Tab after
facing the ordinary observed attacker. This remains a coded combat recovery,
separate from Laya's archaeology and travel decisions.
Episode 76 cleared the duplicate-name attackers and resumed flight to the upper
terrace. It was interrupted after ordinary movement traces showed hostile
avoidance reversing one survey approach by 2.47 yards and then returning to the
previous landing area. Later approaches did make progress; this was a trace-led
interruption for repair, not a completed or accepted loop. Local flight legs now
carry their public survey origin and bearing. Avoidance must retain at least half
the selected bearing progress, with a 1.5-yard minimum and three-yard displacement.
If no clear progressive alternative exists, a healthy level-85 character may
retain the original terrain-validated goal for at most three blockers, each at
least ten levels lower and with known health at most 15,000. Existing bounded
combat recovery handles contact. Unknown health, stronger enemies and player
health below 80 percent still reject that fallback. No green flights were added.
Episode 77 landed inside a raised WMO room at height 134.42, above raw terrain
at 120.77. The addon reported indoors and the client refused the next mount.
Local survey flights now require soil-supported landing patches. Restarting
indoors routes the character outside before mounting, using normal addon
`IsIndoors()` confirmation. Initial regression attempts failed because bare
terrain had no connected walking route, and then because a narrow doorway could
not provide a 2.5-yard outdoor patch. Both failed test XML files are retained.
The repair permits a 24-yard indoor walking corridor across a missing MMAP
doorway only when public VMAP/MAPS floor samples remain continuous, with at most
35-degree steps and clear body-height collision rays. Outdoor walking floors may
be beneath an awning. The planned outdoor patch is 1.5 yards; actual arrival must
be within 0.35 yards, have a supported one-yard patch and report outdoors.
This is a coded geometry recovery; it does not add private find coordinates or
green survey flights. Live recovery remains to be validated. Restarts 78 and 79
stopped before model actions because health was below 50 percent. A respawned
shaman attacked during the idle repair interval, and the character died before
the first physical recovery selected a suitable target. Outside these closed
trials, the isolated console revived Harnessone at the same position, with no
account permission change. It restored half health. Two normal healing slash
commands did not restore health; a later physical Tab/Attack recovery killed the
nearby shaman, cleared combat and allowed ordinary regeneration above 50 percent.
All recovery receipts are retained separately. Automatic death recovery is absent.
Episode 80 stopped after bounded Tab selection failed to acquire an indoor
attacker. Indoors, after four failed cycles, the guard may try the ordinary
attacker's name twice even if duplicate names are visible. Actual selection must
still be a living visible hostile within the applicable three-dimensional range.
It then returns to cycling; no repeated exact-name loop is permitted. Indoor
backward probes are disabled because they moved the character onto room furniture.
Episode 81 stopped below the health threshold. Outside the closed trials, the
lab reset the original full-health level-85 baseline through temporary levels
84 then 85, preserving position and account permissions. Episode 82 cleared
the attacker in five bounded recovery steps, then stopped when the exit planner
rejected the small drop from a furnishing to the floor. Indoor exit sampling now
permits downward steps up to 1.25 yards, retains the 35-degree upward limit and
body-height collision checks, and allows extra settling time after short advances.
Both observed indoor start positions pass the regression with supported outdoor
floor destinations. None of episodes 77 through 82 collected an artifact.
Episode 83 stepped from the furnishing to the floor and advanced toward the
exit, then disconnected because ordinary movement included a packed
`StandingOnGameObjectGUID`. The bridge now parses that modern contact field and
accepts only static game objects already made visible to the owned native
character. Transport objects remain unsupported. The field grants no movement:
native position/flags are unchanged and the informational GUID is omitted from
the legacy packet. The exact failing packet passes a regression; unknown objects
and transport contacts still reject. Only the modern bridge needs a restart.
Episode 84 cleared combat, accepted static-object contact without a disconnect,
and stopped after two small advances hit room furniture absent from static
MMAPs. Indoor exits now retain those observed blocked advances and may plan
at most four short sideways detours (three to eight yards) on continuous public
floor, with body-height rays and both site-boundary checks. The returning leg
must avoid the recorded obstruction by at least 1.5 yards. Actual blocked motion,
health, combat, falling and the total exit budget remain stop conditions. Obstacle
size is unknown; this does not claim an exact geometry model for spawned objects.
Episode 85 completed that indoor exit in 19 observations with one sideways
detour and confirmed `IsIndoors()` cleared. It collected Dragonmaw's remaining
two finds (10 Orc fragments), flew to Coilskar Point, collected all three finds
(18 Orc fragments), observed its replacement, and used Maddix's instant taxi
to Allerian Stronghold before flying to Bonechewer Ruins. The run stopped there
when 106 Tab attempts failed to select a nearby Bonechewer Backbreaker behind
a tree. It is a failed root with one fresh full site, five finds, 28 fragments,
490 model actions, no manual gameplay interventions, no model rejections,
and no frame-hash or site-boundary failures. All observed artifacts were inside
assigned sites. The bounded normal `/targetexact` fallback now also permits
shared outdoor attacker names after four failed selections when the ordinary
attacker is within 16 yards in XYZ. It retains at most two exact-name attempts
and validates the actual selected living hostile and distance before attacking.
The failing ordinary positions have a regression. This does not infer spawned
tree geometry or claim a learned combat policy.
Episode 86 cleared that obscured attacker in six bounded recovery steps and
collected Bonechewer's first find (nine Orc fragments) using green ground
detours. Its second yellow approach stopped when a mounted retreat failed to
clear another attacker. This remains a failed root with no completed site,
60 model actions and no manual gameplay interventions. For ordinary observed
attackers meeting the existing low-threat gate (at most three, ten levels
below the player and known maximum health at most 15,000), a new physical
guard requires at least 80 percent starting health, chooses a dry public soil
patch inside the assigned site, checks a short collision-aware flight corridor,
and waits for normal addon grounding before dismounting. It then invokes
bounded normal melee recovery. Descent, health, falling, swimming, collision,
boundary and input/time budgets can stop it. Airborne dismounts remain rejected.
The receipt records actual observations; no private artifact position is used.
Episode 87 demonstrated the three-observation airborne landing and normal
dismount, but failed to acquire an attacker left far above the eventual floor.
It collected no find and had no site-boundary or frame-hash failure. The airborne
landing-to-melee fallback is therefore disabled in the live routing path; only
already grounded, verified low-threat mounted combat can use that dismount guard.
The native `Creature::CanCreatureAttack` home-distance leash uses the continent
visibility range, which the private configuration sets to 90 yards. The previous
72-yard ascent plus 45-yard horizontal retreat could remain inside that distance.
Mounted airborne withdrawal now verifies an unobstructed public vertical column
and observes a 120-yard ascent through at most eight bounded physical inputs,
then retains the existing in-site horizontal retreat and normal combat-clear
wait. Lost height progress, collision, health, falling and boundaries still stop it.
The owned client is relogged outside closed trials to reset the stranded combat
state; this setup intervention is retained separately and counts as no trial find.
Successful outcomes do not
erase these failures. One manual Tab/Attack protocol probe occurred outside
the closed model trials and is retained as diagnostic evidence.

Trials 07 through 49 are checkpointed in
`artifacts/client_harness/442_outland_navigation_repairs_20261001.tar.gz.dvc`,
following `442_travel_transport_repairs_20261001.tar.gz.dvc`. The repair archive
is 1,550,223,128 bytes with SHA-256
`19c06d0d5ea754e587286fc32610ed5d1d5c5da5d92ba28aace5e0a4c89ad79a`.
Scoped DVC status and push passed; cloud status confirmed remote synchronization.
All 1,910 closed PNG/WebP files matched the archive bytes and hashes before
1,483,211,654 bytes of local frames were removed. Receipts and the cleanup manifest
remain local. Live observation journal segments were preserved for the client.

Trials 50 through 52 follow in
`artifacts/client_harness/442_water_navigation_repairs_20261001.tar.gz.dvc`.
The archive is 489,666,922 bytes with SHA-256
`2900bc9643e24fc1986eb1bbf79f530d427a9f97c6ffe7e6c648bac512999249`.
Scoped status, push and cloud status passed. All 408 closed frames were verified
against archived bytes and hashes before removing 415,195,898 local bytes.
The next checkpoint retains `water_repairs_cleanup.json` with those hashes.

Trials 53 through 59 follow in
`artifacts/client_harness/442_navigation_collection_repairs_20261002.tar.gz.dvc`.
The archive is 1,015,398,006 bytes with SHA-256
`147de2228b459e71e24d98e9f5f73d73a486da18e945a1631f08f4383f7eebdd`.
Scoped status, push and cloud status confirmed synchronization with the remote.
All 835 closed PNG/WebP files matched archived bytes and hashes before removing
934,826,475 local bytes. The following checkpoint includes
`navigation_collection_repairs_cleanup.json` with the verification manifest.

Trials 60 through 63 follow in
`artifacts/client_harness/442_collection_recovery_repairs_20261002.tar.gz.dvc`.
The archive is 500,346,665 bytes with SHA-256
`2b74518b19e1b16cafa67cd477e7c00e68e630002150bb40ed21e789ca1efc3e`.
Scoped status, push and cloud status confirmed remote synchronization.
All 472 closed PNG/WebP files matched the archive bytes and hashes before removing
415,664,660 local bytes. The next checkpoint includes
`collection_recovery_repairs_cleanup.json` with the verification manifest.

Trials 64 through 68 follow in
`artifacts/client_harness/442_dry_shore_site_arrival_repairs_20261002.tar.gz.dvc`.
The archive is 334,727,677 bytes with SHA-256
`87b74d2fee0b71ef58e0dd5e14e0b6344997a7d406debc4518fcc979a354a087`.
Scoped status, push and cloud status confirmed remote synchronization. All 317
closed PNG/WebP files matched archived bytes and hashes before removing
246,023,366 local bytes. The next checkpoint includes
`dry_shore_site_arrival_cleanup.json` with the verification manifest.

Trials 69 through 73 follow in
`artifacts/client_harness/442_terrain_and_takeoff_repairs_20261002.tar.gz.dvc`.
The archive is 326,611,856 bytes with SHA-256
`7e090ebb51f80aa3470380ee8058474327e7bf3a2c96ca399cf8ee792e336b02`.
Scoped status, push and cloud status confirmed remote synchronization. All 265
closed PNG/WebP files matched archived bytes and hashes before removing
233,992,066 local bytes. The next checkpoint includes
`terrain_and_takeoff_cleanup.json` with the verification manifest.

Trials 74 through 82 follow in
`artifacts/client_harness/442_indoor_and_combat_repairs_20261002.tar.gz.dvc`.
The archive is 234,594,613 bytes with SHA-256
`056e73c6afd507a821efb418a55d2c996c4c7a7dd3ba4ed41fe854ad2b7b9fc2`.
Scoped status, push and cloud status confirmed remote synchronization. All 145
closed PNG/WebP files matched archived bytes and hashes before removing
130,506,775 local bytes. The next checkpoint includes
`indoor_and_combat_repairs_cleanup.json` with the verification manifest.

## Running the loop

Start the owned lab services and client using the existing auth/world controls,
then enter Harnessone. Both decision services must pass their health endpoints.
From the compatibility checkout, use a fresh output directory:

```sh
TMPDIR=/home/runiir/.local/share/trinity-client442-lab/run/tmp \
pixi exec --spec pillow --spec python-xlib --spec pymysql python \
  -m tools.client_compatibility.archaeology_loop \
  --output /home/runiir/.local/share/trinity-client442-lab/evidence/new_loop \
  --maximum-sites 2
```

`--maximum-sites 0` continues until interruption or a semantic stall. Supported
travel maps are currently Eastern Kingdoms (0) and Outland (530). Site completion
requires actual collection and addon-observed assignment replacement. Action,
landing-cycle, repeated Survey/loot, health and combat guards stop stalled runs.
Reaching a budget is not success. The native 200-fragment cap still requires
artifact-solving maintenance before an indefinitely unattended harvesting run.
