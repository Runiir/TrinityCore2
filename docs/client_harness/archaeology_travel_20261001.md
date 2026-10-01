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

For red or yellow instruments the controller mounts and flies to a farther
public bearing waypoint. A clipped in-site survey ray supplies the flight goal;
it does not require the shallow ground-walking corridor to cross a hillside.
Flat landing and ground-component checks still apply. Episode 40 had stopped
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
fragments, including a real swim and dry Survey recovery, then flew to Bleeding
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

## Validation and experiment history

The authentication, world, observation, terrain, collection and combat suite
passes 105 tests. The first observation-refactor check failed collection because
of an indentation error; the repaired full suite passed. Both its failed XML
and the final XML are retained. Earlier missing-Pillow collection and mock-route
fixture failures are retained with their corrected results.
The first stricter-slope check also failed two old terrain expectations: a
column now deliberately rejected, and a landing displaced to a gentler point.
The fixtures were updated to test those safety outcomes; its failed XML is retained.

Episodes 07 through 52 preserve unsuccessful steps, including missing portal
hotfixes, realm-connection transfer rejection, an orphan return trigger, portal
contact mismatch, steep landing cycles, overlapping loot clicks, disconnected
roof surveying, unsuccessful combat retreats, terrain-obstructed targeting,
a ranged attacker beyond the original melee approach limit, interrupted mount
casts, changing landing goals, steering quantization, and a walking-path
prerequisite that incorrectly blocked mounted movement, replanned bank detours,
low bridge steps, unnecessarily requested melee approaches, excluded water,
and interrupted gathering followed by a missed tooltip. Successful outcomes do not
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
