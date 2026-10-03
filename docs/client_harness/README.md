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
historical receipts remain on disk. New UI trials use the code controller with
ordinary keyboard and mouse inputs. Earlier October 2–3 interaction receipts
retain their actual Laya identities; they do not authorize new model calls under
the updated instructions. The user's October 3 desktop-isolation request explicitly
authorizes a new bounded two-client Laya UI trial. It requires the separate
`--use-laya` cohort flag; other new regression trials continue using the code
controller. Code checks qualify client behavior, not model autonomy.
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
The [October 3 auction report](interactions_20261003_auctions.md) records stock
auction opening, complete empty browse/bid/owned catalogs and the city vehicle-create
repair. That auction suite passes 659 regression checks; the transaction bridge
also passes 77 selected sanitizer checks. The empty Sell catalog and price entry
work. UI21 posts and cancels one plain auction, collects the same original item,
then fully restores native resources in separate recovery episodes. The stock
price-column center absorbs row clicks; the runner uses the measured item end.
After deploying the isolated opt-in native deposit correction, UI22 passes all
14 inputs in one uninterrupted posting/cancellation/item-return round trip.
The zero quote, native deposit and charge agree for the cheap one-day pants
auction, and complete resources and poses are restored without a money refund.
Other fee values, bids, buyouts and broader auction variants remain open.
Captured failures, observer corrections and cleanup receipts are retained.
The later bank batch passes 411 regression tests, including nine bank packet tests;
46 selected bank, peer-service and inventory tests also pass ASan/UBSan. Bank open,
deposit, withdrawal and close have live evidence. Inspect gear samples and a real
item trade round trip are also qualified; broader variants remain in the workqueue.
The merchant catalog displays all nine native fixture items. The merchant transaction
adapter and subsequent quest/mail work pass 578 regression tests (561 world and
17 authentication checks). The quest batch
passes 101 selected ASan/UBSan tests; the later self-target correction passes
26 selected sanitizer checks and the login-read followup passes 32. This counts
protocol checks. A live seven-choice trial sells an existing item, buys it back,
restores its slot and closes the merchant with exact native inventory/money
restoration. A four-choice purchase trial buys a five-item water bundle with exact
price/quantity and received-item chat agreement, then restores the fixture. Individual/guild repair
and broader purchase variants remain open. Repair-all is qualified with exact
quote/charge agreement after the opt-in native rounding fix. A four-choice warrior
trainer trial learns Parry with native/client spell, price and notification
agreement. The alchemy trainer's Already Known filter is qualified against all
141 native known recipes; new profession learning and broader training variants
remain open. Mailbox opening and closure now display all three existing reward
letters with correct sender names, subjects and attachment counts. The mail and
login followup passes 35 selected sanitizer checks. A later disposable-letter
trial qualifies reading its displayed body, native read marking and deletion;
its 52 selected mail/login sanitizer checks pass. Two subsequent trials qualify
collecting five water items and 12,345 copper, each with full fixture restoration;
62 selected sanitizer checks pass. Later player send/return and send/reply trials
pass 14 and 17 code-controlled choices with exact postage, native delivery,
rendered-body agreement and complete two-character fixture restoration. The final
mail suite passes 114 selected sanitizer checks. COD, text-copy, invoices,
attachment limits and broader variants remain pending. See the
[player mail report](interactions_20261003_mail.md) for retained failures,
qualification boundaries and reproduction commands.
Questgiver details and the native 0/6 kill objective display correctly in the
latest trial. Its initial cleanup exposes a dropped self-selection request,
which is fixed. A five-choice quest-log trial expands the zone, reads the
accepted quest and confirms abandonment with exact native quest/inventory/money
restoration. The later [manual quest report](interactions_20261003_quests.md)
records normal acceptance/decline, zone collapse and cancelled abandonment,
plus repaired public creature-name lookup for both kill objectives. The latest
full suite passes 673 world/auth tests; 41 selected public-template/mail/quest
checks pass ASan/UBSan. Objective progress, completion/rewards, sharing,
persistence and travel remain open.

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

One task owns each actor. Each actor has its own Gamescope X display and input
lock. Keyboard/mouse input goes directly to the owned game window on that private
display. Monitor checks only read the host window's position; task inputs never
activate or reposition it. The user can work in another desktop application while
both actors run. Cohort preflight rejects shared character GUIDs, client processes
or private displays. `cohort stop` interrupts its owned
workers, leaving clients and servers running. This first probe observes the primary
and briefly moves the scout; it is explicitly a code-driven diagnostic, not a
two-model autonomy claim. Fleet restart/recovery and long-duration scheduling need
additional validation.

The user-requested two-client Laya UI check uses the existing local model endpoint
and opens bags, equipment and friends separately on each actor. It preserves
resources, equipment and group state. Run the committed config with a fresh output:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.cohort start --use-laya --config experiments/configs/client_harness/442_two_actor_isolated_ui_v1.json --output ~/.local/share/trinity-client442-lab/evidence/<batch>/isolated_laya_ui
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.host_desktop_watch --output ~/.local/share/trinity-client442-lab/evidence/<batch>/isolated_laya_ui
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.cohort status --output ~/.local/share/trinity-client442-lab/evidence/<batch>/isolated_laya_ui
```

The optional read-only desktop watcher records opaque focus handles and pointer
coordinates while the workers run. It captures no desktop screenshots or keys.
An actor's focused nested window is verified through the Wine process's parent
chain to its owned Gamescope supervisor. Input adapters reject actor changes and
client PID reuse. Both visible Gamescope windows must remain on HDMI-1.

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

The [interaction checklist](interaction_checklist_442.md) now preserves completed
fixture variants as checked boxes with explicit evidence and remaining limits.
Its reviewed mappings live in
`experiments/configs/client_harness/442_interaction_qualifications_v1.json`;
`interaction_inventory write` reconciles them when regenerating the human checklist
and machine inventory. Unmapped operations stay pending. Current reconciled evidence
qualifies 190 operations out of 907 across 45 families. This is a count of qualified
fixture variants, not a percentage of complete game compatibility. Eight raid/party
controls, the known-trainer filter and plain-item auction posting were added to the
original 891-operation plan because they were missing individual contracts. Six NPC marker variants are now explicit checks. The talent/glyph and available-marker repairs are documented in [the UI24 report](interactions_20261003_talents_markers.md).

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

Start each interaction batch with the owned native server identity, then place
standalone trial outputs underneath it. Mail examples use the existing visible
mailbox at the verified 1280x720 point `(640,248)`; review staging after camera or
UI layout changes. Run physical-input trials one at a time across both actors.

New mail and auction runners use the code controller under the current
AGENTS.md retirement of Laya and Jev. Historical receipts retain their actual
model identities. Code checks qualify client behavior through ordinary inputs;
they do not evaluate a decision model.

```bash
pixi run python -m tools.client_compatibility.checkpoint_interactions --initialize --directory ~/.local/share/trinity-client442-lab/evidence/<new-batch>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_mail_actions --point 640 248 --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/mail_read_delete_01
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_mail_collect --point 640 248 --resource item --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/mail_collect_item_01
```

Use `--resource money` for the separate money trial. These runners create a
uniquely tagged native console letter, use ordinary UI inputs and verify
restoration. Temporary item/money command permissions are revoked afterward.
They require clean fixtures and preserve failures; resolve a leftover disposable
letter before creating another. Player-to-player send, return and reply use the
separate `interaction_mail_roundtrip` runner documented in the player mail report.
COD, copied text, invoices and broader attachment variants remain open.

After every run in a batch is closed, commit its code/configuration, checkpoint,
prune only verified frames, and evict only the named remote-verified archive:

```bash
pixi run python -m tools.client_compatibility.checkpoint_interactions --directory ~/.local/share/trinity-client442-lab/evidence/<closed-batch> --name 442_<unique-checkpoint>
pixi run python -m tools.client_compatibility.prune_checkpoint_frames --directory ~/.local/share/trinity-client442-lab/evidence/<closed-batch>
pixi run python -m tools.client_compatibility.evict_checkpoints 442_<unique-checkpoint>.tar.gz --receipt ~/.local/share/trinity-client442-lab/evidence/<unique-eviction-receipt>.json
```

Commit the generated `.dvc` pointer and `artifacts/client_harness/.gitignore`.
The checkpoint and eviction helpers run scoped DVC status/push and remote
verification. Missing local cache after deliberate eviction is expected. Keep
small receipts, active journals, required builds and client/model assets. Use
`checkpoint_run_frames --episode <explicit-closed-episode>` for older closed
frames or `--evidence-frame <explicit-old-basename>` for historical loose frames;
those paths retain provenance and require stable sources and verified remote data.
Never run global DVC cache collection to clean this worktree.
