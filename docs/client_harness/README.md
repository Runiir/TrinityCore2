# Running and developing the 4.4.2 compatibility lab

Use the `feature/442-compat` worktree at `/home/runiir/Games/trinity-442-compatibility`.
The lab root is `/home/runiir/.local/share/trinity-client442-lab`. Its database,
server processes, client prefixes, credentials and evidence are separate from the
running raid environment. Do not use `make host-world` for this lab.

## Current evidence and limits

The accepted archaeology episode 89 completed six finds at two fresh Outland sites,
awarded 44 fragments and replaced both sites. Its model actions and screenshots are
checkpointed in DVC. This proves that bounded archaeology/travel case. It does not
qualify every game feature or indefinite unattended operation.

The existing Laya archaeology and travel heads consume structured observations.
The harness also records screenshots and decodes normal addon-visible state. These
heads do not perform general screenshot reasoning or supply a questing policy.
The current checkout's AGENTS.md retires Jev/Laya from new runs. Their code and
historical receipts remain on disk. New cohort runs use diagnostic tasks until a
current controller adapter is attached. The user's explicit October 2 interaction
test request uses the retained base Laya endpoint at `127.0.0.1:8000` for bounded
normal-input choices. That exception is recorded in each run; it does not change
the standing controller policy for other experiments.
Green lantern approaches stay on foot; short recovery flights require exhausted
terrain recovery and the bounded clearance checks. A code-driven native-bridge
trial completed one such flight and then recovered a Dwarf artifact for eight
fragments. This qualifies that physical recovery case. Learned selection and wider
terrain variants still need fresh evidence.

The world packet bridge now runs as a separate C++20 service and is the default.
Its optimized build passed both login routes and the two-client probe: the primary
remained still while the scout moved through ordinary keyboard input, with native
saved positions confirming both outcomes. Both owned windows were verified on
HDMI-1. The initial suite passed 277 tests. Its 54 packet and codec tests also passed
ASan/UBSan. Python still handles modern
authentication, supervision, observations and diagnostic decisions. The bridge
does not embed Python or call the Python world translator.
See [the native bridge notes](../../tools/client_compatibility/native_bridge/README.md).
The [October 2 interaction report](interactions_20261002.md) records the later
group-frame, role and marker repairs, individual qualifications and remaining gaps.
The later bank batch passes 411 regression tests, including nine bank packet tests;
46 selected bank, peer-service and inventory tests also pass ASan/UBSan. Bank open,
deposit, withdrawal and close have live evidence. Inspect gear samples and a real
item trade round trip are also qualified; broader variants remain in the workqueue.

## Endpoints and restart

| Component | Lab endpoint |
| --- | --- |
| MySQL, container `trinity-client442-db` | `127.0.0.1:13306` |
| Native authentication | `127.0.0.1:13724` |
| Native gameplay | `127.0.0.1:18085`, instance `18086` |
| Modern authentication TLS / REST | `127.0.0.1:1119` / `18081` |
| Modern world bridge | `127.0.0.1:18087` |
| Historical archaeology / travel heads; unused in new runs | `127.0.0.1:8002` / `8003` |
| Explicit October 2 interaction trial, base Laya | `127.0.0.1:8000` |

Inspect ownership before starting services. Start only missing owned components.
Run Python commands with Pixi from this checkout:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.lab_runtime status
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.auth.control status
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.world.control status
```

The startup order is database, native auth/world, modern auth/world, then clients.
The supervisors' `start-auth`, `start-world`, `start`,
`launch-sso` and `launch-direct` actions operate on the private lab. Keep both SSO
and username/password login paths qualified. Do not run `prepare-servers` to rebuild
a binary; it copies an existing binary and does not compile this worktree.

Build and start the world bridge independently, after stopping an existing owned
bridge if needed. Reconnect affected clients after a bridge restart:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.world.control build
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.world.control start
```

The build receipt pins source/schema and executable hashes. A stale executable is
rejected. The default uses four I/O workers and a separate database pool, with a
64-connection bound (realm and instance sockets both count). This is a safety bound,
not evidence that 32 clients have been load-tested. The current real-client budget
is two. `--engine python` explicitly selects the retained reference implementation.

Every game client must launch on the physical second monitor, currently `HDMI-1`.
The owned window must be verified there before input. A missing or misplaced window
fails the input preflight.

## Actor isolation and concurrent tasks

The primary actor uses the existing root. Other actors use
`$ROOT/actors/<name>` with their own normal account, character, Wine prefix, client
directory and PID receipt. Server processes and DB schemas remain shared within the
isolated lab. Actor names have a strict allowlist; observations must match both the
native character GUID and its authenticated bridge session.

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.actors register --guid 1
CLIENT442_ACTOR=scout pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.actors provision --character Harnesstwo
CLIENT442_ACTOR=scout pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.auth.control launch-sso
```

Provisioning is a fixture setup through the native character handler. It is not
proof of the modern client character-creation UI. The new scout starts normally at
level 1. Do not give every compatibility actor archaeology's level-85 fixture;
leveling tests need genuine progression.

Commit code/configuration before running a cohort. Use a fresh output directory:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.cohort start --config experiments/configs/client_harness/442_two_actor_probe_v1.json --output /home/runiir/.local/share/trinity-client442-lab/evidence/two_actor_probe_01
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.cohort status --output /home/runiir/.local/share/trinity-client442-lab/evidence/two_actor_probe_01
```

One task owns each actor. Task processes observe concurrently; future model adapters
must preserve this ownership contract. Physical keyboard/mouse actions take a shared process lock, focus the
verified owned window, execute and release it. `cohort stop` interrupts its owned
workers, leaving clients and servers running. This first probe observes the primary
and briefly moves the scout; it is explicitly a code-driven diagnostic, not a
two-model autonomy claim. Fleet restart/recovery and long-duration scheduling need
additional validation.

## Faster repairs

| Finding | First repair and validation |
| --- | --- |
| Incorrect template, condition, vendor, loot or trainer row | Versioned SQL with rollback, the smallest supported reload, then verify the resulting native behavior through the client. |
| Client data or hotfix mismatch | Reviewed public data/hotfix changes, explicit cache handling and a client replay. |
| Packet translation mismatch | Rebuild/restart the independent bridge, reconnect affected actors and verify the packet's native effect. |
| Input, observation or model-policy problem | Restart the affected worker/model as needed; keep worldserver running. |
| Native gameplay rules, handlers or scripts | Bounded C++ patch, native build and a coordinated lab restart. |

Supported reload commands include `reload quest_template`, `reload npc_vendor`,
`reload creature_template` and `reload conditions`. A command acknowledgement alone
does not prove that existing objects or accepted quests picked up new data. Some
state requires a fresh spawn, relog or restart. One coordinator owns shared SQL
changes, reloads and restarts while concurrent actors produce attributable evidence.

## Feature, protocol and content coverage

`442_coverage_manifest_v1.json` lists feature scenarios and their acceptance oracles.
`coverage.py` inventories pinned modern/native opcode definitions and source
references. A referenced opcode is not an implemented or live-qualified handler.
Each feature must retain a fresh client observation and the corresponding native
outcome. Normal taxi timing needs its own case after instant-taxi experiments.

`content_census.py` reads native DB/DBC IDs in a read-only consistent snapshot and
records source fingerprints. This covers individual content inventory, not just
feature families. It still needs reconciliation with the installed modern client
tables, applicability review and per-content/variant evidence. Unknown, skipped and
failed cases remain visible. An inventory does not establish 100% coverage.

The initial native census found 14,991 quests, 46,627 creature templates, 29,501
gameobject templates, 73,253 spells and 64,775 item IDs, with no missing inventory
sources. The 72 feature cases and content IDs still need individual acceptance
receipts. Continue with ordinary quest interactions/progression, normal taxi and
portal transfers on the native bridge, then expand task adapters and content
variants. The diagnostic cohort supplies actor isolation and input ownership;
general learned roaming and automated whole-game qualification remain open.

## Evidence and publication

Commit experiment code/configuration first. Record source, client build, binary,
actor/account/GUID/session, data fingerprints, model adapter and oracle in each
closed run. Stop on semantic stalls, lost ownership/infrastructure, repeated failed
actions, death loops or explicit interruption. A time limit is never proof of
success. Use DVC/DVCLive for generated evidence and metrics, then run scoped
`dvc status`, `dvc push` and cloud-status verification.

Exclude credentials, tickets, session keys, live DB contents, Wine prefixes and
CASC caches from evidence. Authentication bodies are excluded from packet journals.
Verify archive contents and hashes before removing raw frames. Historical episode
89 frames have already been archived and removed locally; use its retained score
and DVC checkpoint rather than rescoring a local directory with missing frames.

The native migration checkpoint is
[`442_native_bridge_and_cohort_20261002.tar.gz.dvc`](../../artifacts/client_harness/442_native_bridge_and_cohort_20261002.tar.gz.dvc).
It includes earlier failed runs and test results, the successful two-client probe,
Survey/recovery-flight/artifact receipts, safe packet journals and inventory
fingerprints. Restore only this checkpoint when reviewing it:

```bash
pixi run dvc pull artifacts/client_harness/442_native_bridge_and_cohort_20261002.tar.gz.dvc
```

The inherited checkout has unrelated historical DVC outputs absent locally. Scoped
status/push checks verify this lab's checkpoints without downloading those datasets.
