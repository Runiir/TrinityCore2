# Whitemane 60895 archaeology compatibility trial

## Current repair and adapted-model trials

The later trials use a fine-tuned Laya decision head at
`http://127.0.0.1:8002/v1/systemone`, with the original encoder frozen.
The v2 adapter SHA-256 is
`c9d97c846d8ff7c7b4c072c5bb8a61e95ea89c6755f368d9341c32f71c4d05b9`.
Its synthetic held-out test score is 418/420. This measures agreement with the
explicit survey control policy, not independent travel or quest competence.
All seven actions remain available to the model. The controller converts a
chosen action into bounded keyboard or mouse input.

`laya_archaeology_fixed_01` collected one find in 19 actions and 57.7 seconds
without supplied mouse coordinates. `fixed_02` collected another find during a
two-find trial, then stopped after repeated turns caused by stale rendered
facing. The ordinary owned movement packets now supply fresh facing.
Automatic mouse localization uses normal archaeology-find tooltips.
The awards were **5 and 6 Night Elf fragments**, with balances 13 and 19.
The old immutable episodes recorded those balances as quantities;
`collection_scoring_corrections.json` preserves the corrected interpretation
from native loot amounts, removed currency slots and currency updates.

The native sampler previously returned 12,568 outside points in 184,000
samples against legacy perimeters. Ordered polygon containment and rejection
sampling repaired that failure. Comparing public DB2 records extracted from the
installed 4.4.2.60895 CASC storage found another difference: 36 vertices across
14 sites shift by one yard. All 180 isolated database site mappings match.
Twilight Grove (163) has identical client/backend perimeters, and all five
recorded artifact creates are inside both versions of its polygon.

Only the lab now uses a private legacy-layout QuestPOIPoint DBC with the modern
coordinates. Shared native map data is linked read-only. All 183 usable client
polygons match this corrected DBC. The corrected native sampler returned zero
outside points in 184,000 samples, including the concave fixture.
Local survey walks also check the entire MMAP corridor against the active site
observed through the addon. They clip outward telescope bearings and reject
paths leaving a concave boundary. A telescope bearing has normal uncertainty;
following it indefinitely can leave a site even when the hidden target is valid.

Ground routing reads public static native MMAP geometry, including elevations,
without blind jumping or exposing hidden next-find coordinates. The native
server also rejects hidden targets without a connected ground path. These
changes do not establish that every modern-client tree or rock has identical
collision geometry. Earlier ground trials stopped for no Survey object outside
the site and for no useful connected ground displacement. Multi-site autonomous
flight, taxi travel and portal travel remain unproven.

Character selection now visibly renders the equipped gear. The client window
is owned and verified on HDMI-1. The 54 authentication, world and boundary tests
pass. The first direct `pytest` invocation failed to import `tools`; invoking
`python -m pytest` in the same Pixi environment repaired test discovery.

Two further bounded live trials passed. `laya_archaeology_boundary_01` took
30 actions and 89.5 seconds to collect 6 fragments; all ten walks and the
artifact position were inside the client polygon. It also reproduced early
site replacement: the backend removed Twilight Grove at artifact spawn, before
the model's loot click. That left the final artifact visible after its outline
disappeared.

The native server now retains the site and its find until all owned loot has
been removed. A repeated Survey cannot duplicate a pending artifact, and an
expired unlooted find consumes no dig. The ordinary currency/item loot handlers
settle that pending find, without changing Player's public class layout.
`archaeology_loot_lifecycle_v1.json` declares a final-find test that sets only
slot zero to site 163 with two collected finds, preserving position and gear.
In `laya_archaeology_lifecycle_01`, Laya collected 7 fragments in 49 actions and
141.6 seconds. All sixteen walks stayed inside the polygon. Addon-visible site
163 remained assigned before the click, the artifact was inside that still
visible boundary, and the client replaced it with site 207 after collection.
Neither trial used teacher click coordinates or private next-find coordinates.

The native build passed with existing G3D `ciso646` warnings. Client restart
initially exposed a Gamescope reaper left behind after its parent exited;
cleanup now verifies and removes only that leftover owned helper. Evidence for
the boundaries, failed ground trials, successful live digs and lifecycle repair
is checkpointed with DVC and DVCLive in
`artifacts/client_harness/442_archaeology_boundaries_20261001.tar.gz.dvc`.

The following sections retain the earlier assisted baseline and its evaluation.

## Earlier assisted baseline

The isolated 4.4.2 client now renders its native equipment, opens its 16-slot
backpack, displays a Survey cast bar, mounts, flies, follows survey instruments and collects
archaeology currency through the native 4.3.4 worldserver. The trial collected
8 Night Elf fragments. All changes are in the `codex/442-compatibility-audit`
worktree and the `client442_*` databases. The running mainline boss experiment
was not restarted or edited.

## Character and observations

`Harnessone` is a normal-permission level 85 warrior with 16 equipped epic items
and all 15 profession skills at 525. The setup uses a temporary native GM
session and restores account security to zero. The two-handed weapon needs no
offhand. Gems and enchants from the gear reference are not applied.
Master Riding is 375 and Flight Master's License is learned. A separate
`--flight-only` setup adds those without resetting the trial position or gear.

Learning every crafting recipe also learned all three mutually exclusive
Alchemy specializations. The 4.4.2 profession frame then entered an invalid
branch and stopped drawing the remaining professions. Removing Potion and
Transmutation mastery while retaining Elixir mastery repaired that interface.

The text-only local Laya model is exposed at `http://127.0.0.1:8000/v1/systemone`,
model `convaiinnovations/laya-typed-decisions`, revision
`c5d78730f3493e4fe16d61507ef4b78eef7318cf`. No weights were fine tuned. It chose
finite keyboard/mouse actions from options constrained by the controller.
Recorded confidence was low. This trial demonstrates an integrated controller,
not a generally trained archaeology or questing policy.

Screenshots supply addon-visible position, facing, speed and health. With the
user's explicit authorization, the observer also reads telescope colour and
heading from the owned character's decoded visible-object TCP packets. The
heading includes the game's normal survey uncertainty. It never reads the
server's private next-find coordinates. Native session identity and object
creator checks prevent mixing another character's instruments into the trial.

Steps 3 through 25 used Laya for turning, walking and resurveying until a find
was visible. A teacher supplied screen coordinates for the final artifact click
and loot row. Earlier manual movement and unsuccessful clicks are retained in
the episode, so they cannot be mistaken for autonomous success.

## Laya decision evaluation

The successful live find took 23 navigation actions: eight Surveys, eight turns
and seven walks, over approximately 73 seconds before looting. It produced eight
Night Elf fragments. This is one assisted find, not a measured completion rate.
The harness supplied `next_instruction` and constrained the choices. Sixteen of
the 23 navigation decisions offered only the correct progress action and waiting;
the remaining seven offered short walking, long walking and waiting. Code also
computed the turn duration and colour-dependent walking distances. A teacher
supplied both artifact and loot-row mouse coordinates.

The frozen shadow evaluation at code commit `0bcde2f3da` replays those 23
observations and adds 21 synthetic cases covering telescope colours, opposing
headings, stale/missing instruments, casting and unavailable characters. It makes
111 requests to the same pinned local model across three variants. No game input
or weight training occurs. Raw observations contain ordinary telescope readings
and action history; the fact summary replaces numeric heading errors with
left/right/aligned facts. Both variants offer all six navigation actions, with
general task rules but no supplied next action.

| Variant | Recorded navigation | Synthetic cases | All cases |
| --- | ---: | ---: | ---: |
| Original instructions and constrained choices | 23/23 (100%) | Not evaluated | 23/23 |
| Raw observations, all actions | 8/23 (35%) | 10/21 (48%) | 18/44 (41%) |
| Relative-heading facts, all actions | 5/23 (22%) | 10/21 (48%) | 15/44 (34%) |

Labels follow the explicit public-telescope control policy. Either bounded walk
counts as progress when aligned, even if its distance differs from the preferred
choice; in this run preferred-action and progress scores are identical. These
are correlated recorded states and synthetic checks, not independent live digs
or estimates of general archaeology ability.

With raw observations Laya chose Survey on 39 of 44 cases. Both unrestricted
variants failed both casting/unavailable wait checks. Those requests remained
in shadow; the live controller's safety guards were not removed. Neither variant
meets the predeclared 90% preferred-action, 95% progress-action and 100% unsafe-wait
criteria, so no controller promotion occurred. Simplifying numeric angles into
relative-heading facts did not improve this configuration. Reported confidence
is not used as a substitute for measured action correctness.

The evidence supports a working guided archaeology controller. It does not yet
support reliable independent Laya action selection. Repeated live digs, automatic
artifact mouse localization, and a comparison with the same controller without
Laya remain necessary to measure completion reliability and the model's added
value. The evaluation code and configuration are committed; full requests,
responses, labels, source episode and DVCLive metrics are checkpointed in
`artifacts/client_harness/442_laya_archaeology_eval_20261001.tar.gz.dvc`.

To reproduce the shadow evaluation with a new output directory:

```sh
pixi run --manifest-path /home/runiir/Games/trinity-cata/pixi.toml python -m tools.client_compatibility.evaluate_archaeology --output /path/to/new/evaluation
```

## Protocol repairs

- Initialize known spells, action buttons, proficiency, equipment, inventory,
  profession skill arrays, archaeology sites and research projects.
- Translate Survey and archaeology gathering spell 73979, with visible-object
  target ownership checks, client/server cast GUID acknowledgement, completion,
  cancellation and failures.
- Use the 60895 **single visual ID** spell layout. The newer Trinity writer's
  extra script visual shifted cast time and prevented the cast bar. The incoming
  request contains three crafting counts; zero fields initially hid that error.
- Translate visible game-object creation, queries, destruction and removal.
  Previously expired instruments remained visible in the client.
- Translate native loot, currency collection and release. An artifact right
  click is a gathering cast, not simply a game-object-use request.
- Advertise the native 16 backpack slots instead of the modern field's default
  zero. Forward mouse-facing heartbeats to the native facing handler.
- Forward ongoing owned-player mount display/state fields with both CGObject
  fragment bits set. Translate visible auras, cancellation, run/flight speeds,
  flight permission and the client's matching acknowledgements. Translate
  pitch, ascent/descent and flight-state transitions into native movement.

The [Trinity packet parser's 4.4.x spell definitions](https://github.com/TrinityCore/WowPacketParser/blob/28fc3d194b22063ce8e94d2ed7235ca98ca51ef2/WowPacketParserModule.V4_4_0_54481/Parsers/SpellHandler.cs)
provide the 60895 wire-layout reference. Parser SHA-256 is
`19ceb7ed9d2b39a59b9c7eb657a2b954bf1ccd9fcbcb53141c2a161fdc4b137d`.
The existing generated field/opcode reference remains pinned to Trinity revision
`6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2`. Captured ordinary client requests
and native responses are regression fixtures.

## Validation and remaining scope

The 39 combined authentication/world tests pass, including captured Survey and
gather requests, cast ownership, destination handling, interrupted casts,
currency loot ownership, duplicate-slot rejection, object destruction and the
first newly populated research project. Live screenshots verify the backpack,
Survey bar and currency receipt. A fresh login after fragment collection also
works. Live tests also verify mounting/dismounting without relogging, mounted
run speed 14 yards/second, flight permission acknowledgement, takeoff and
landing. Moving interrupts Survey and a subsequent Survey completes. The game
window is verified on HDMI-1.

Intermediate failures are retained in the experiment receipt. These include
incorrect cast visual/count assumptions, missing gathering targets and cast
acknowledgement, zero backpack capacity, missing object destruction, mutually
exclusive Alchemy recipes, and a research serializer that failed when the first
project became nonempty. The interruption test initially used an incorrect
expected failure number; the native-to-modern mapping itself was correct.
Mount testing exposed the missing CGObject active bit and missing flight
license. Test fixture metadata/mask expectations and an existing MSG-only
movement opcode assertion were corrected. Running tests through the main Pixi
manifest initially failed collection because its environment lacks the auth
dependencies; the auth manifest is the correct test environment.
An airborne dismount initially disconnected the client because modern extra
movement flags differ from native bits. Swim-to-flight is mapped explicitly;
the observed Whitemane `0x8000` hint is accepted only with a falling state and
fall data, then omitted from the native 12-bit field. This is a captured
compatibility rule, not a known semantic definition of that undocumented bit.

This remains a bounded compatibility slice. NPC creation and broad ongoing
unit fields beyond the implemented player subset, inventory/research updates,
general targeted combat, crafting, transports,
vehicles and quests are not complete. Character selection equipment preview is
still empty even though equipped items render after login. New research projects
currently refresh on login. The controller can find one fragment using telescope
data but still needs a screenshot annotation for accurate mouse looting.

## Run

From the compatibility worktree with the owned services and character in-world:

```sh
pixi exec --spec pillow --spec python-xlib --spec pymysql python -m tools.client_compatibility.archaeology_controller --steps 12
pixi exec --spec pillow --spec python-xlib --spec pymysql python -m tools.client_compatibility.archaeology_controller --visual '{"fragment_pixel":[640,350]}'
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m pytest tools/client_compatibility/auth/tests tools/client_compatibility/world/tests -q --import-mode=importlib
```

The completed episode refuses additional model actions. The example pixel must
be supplied from the current screenshot, not reused blindly. The lightweight
launcher remains at `http://127.0.0.1:18081/launcher`; direct and SSO login share
the same native-authoritative gameplay adapter.

The DVC checkpoint `artifacts/client_harness/442_archaeology_20261001.tar.gz.dvc`
contains the episode, setup and validation receipts, screenshots, safe decoded
world packet trace, JUnit output, code identities and DVCLive metrics. It excludes
authentication bodies, tickets, keys, credentials, client logs and registries.
