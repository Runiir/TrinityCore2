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

Flat landing points now use MMAP detail triangles, reject slopes above 40
degrees and reject ground covered by another surface. Archaeology landings must
also share a complete ground path with the current site floor. This excludes
the disconnected Bonechewer building roof that previously allowed Survey casts
but produced no reachable instrument or find. Entire local walk corridors and
mounted survey segments must stay inside the assigned public polygon.

For red or yellow instruments the controller mounts and flies to a farther
public bearing waypoint. Green instruments use ground paths. Find collection
uses the normal tooltip to locate a right-click. If the character overlaps the
visible find, it first backpedals about 3.5 yards along an in-site ground path;
standing directly over the artifact previously produced no interaction packet.

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

## Validation and experiment history

The authentication, world, observation, terrain, collection and combat suite
passes 85 tests. The first observation-refactor check failed collection because
of an indentation error; the repaired full suite passed. Both its failed XML
and the final XML are retained. Earlier missing-Pillow collection and mock-route
fixture failures are retained with their corrected results.

Episodes 07 through 31 preserve unsuccessful steps, including missing portal
hotfixes, realm-connection transfer rejection, an orphan return trigger, portal
contact mismatch, steep landing cycles, overlapping loot clicks, disconnected
roof surveying, and unsuccessful combat retreats. Successful outcomes do not
erase these failures. One manual Tab/Attack protocol probe occurred outside
the closed model trials and is retained as diagnostic evidence.

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
