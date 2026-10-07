# Whitemane 4.4.2 compatibility with the current Trinity backend

The installed Whitemane executable identifies itself as **4.4.2 build 60895**. This repository's native client protocol is **4.3.4 build 15595**. Connecting the newer client requires a protocol implementation or translation layer covering login, world entry and object state before keyboard movement can be validated. Editing a build number, realm address or port cannot supply that implementation.

This is a static audit, not a failed or successful live connection test. No server was launched, no database was queried or modified, and no client inputs were sent. Work is isolated in `/home/runiir/Games/trinity-442-compatibility` on `codex/442-compatibility-audit`. The existing boss-bot checkout, database and runtime configuration remain outside this work.

## Source and executable identities

- Local baseline: `bdd8b400df906e916aa81947083f3873f11e8001`. This clean baseline does not include the coordinator checkout's uncommitted boss work. The compared transport source belongs to this exact worktree.
- Classic reference: official TrinityCore `cata_classic`, pinned at `6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2`, dated September 28, 2026. Its base auth database explicitly lists `(60895,4,4,2,NULL)`, Windows x64 WoWC build authentication material, and a default realm build of 60895. That is source support for this build, not proof that this particular patched Whitemane executable connects successfully.
- Client: `/home/runiir/Games/_whitemane-60895_/WowClassic.exe`, 58,386,064 bytes. SHA256: `9d963af8c7ce67aa9828b834a91f59e41221767801e78a9b91d9ea81971ee796`. Its Windows version resource reports file and product version `4.4.2.60895`.
- The [DVC evidence pointer](../../artifacts/client_harness/442_compatibility_audit_20261001.tar.gz.dvc) retains selected legacy and Classic source files, file hashes, unified diffs and the generated report. All 68 retained source-file hashes were verified. The audit script reads sources and the executable only.

## Confirmed incompatibilities

| Boundary | Current backend | Classic build 60895 reference | Effect on the movement trial |
| --- | --- | --- | --- |
| Login service | `authserver`, legacy logon challenge/proof and realm-list handling | `bnetserver`, Battle.net services, login REST and realm tickets | The newer login flow is not implemented by this authserver. A separate legacy authserver alone cannot accept the modern login flow. |
| World authentication | Account-name auth packet; 20-byte SHA1 digest and shorter local challenge | Realm-join ticket; 24-byte digest, 32-byte local challenge and HMAC-SHA512-based verification | Packets and session-key derivation require different implementations. |
| Packet envelope and encryption | Legacy client size/opcode header, legacy server header; ARC4-drop1024 header crypt | Size plus integrity tag, encrypted opcode/payload, 256-bit AES-GCM packet crypt and encrypted-mode negotiation | Neither side can interpret the other's framing or ciphertext. |
| Opcode dispatch | 16-bit opcode enums and legacy IDs | 32-bit opcode enums and modern IDs | The current dispatch table cannot route modern packets. |
| Character list and login | Legacy character records and bit/byte-packed GUID handling | Modern character records, GUID representation and login fields | The client must reach character selection and world entry before a walk command can be tested. |
| Object identity | One 64-bit GUID and legacy high-GUID layout | Two 64-bit words, modern object type formats and packing | Identity translation affects character, player, creature and transport packets. |
| Object creation and updates | Flat indexed fields and legacy update masks | Generated typed fields, nested/dynamic fields, visibility-aware serializers and change masks | The client cannot render usable player/world state from legacy update blocks. |
| Movement | Opcode-specific bit/byte sequences in `MovementStructures.cpp` and native unit movement readers | Common `MovementInfo` serializers with different flags, GUIDs, movement-force data and optional blocks | Renaming movement opcodes does not fix position, facing, heartbeat, stop or acknowledgement payloads. |
| Client tables and terrain | MPQ extraction; 15595 DBC layouts and a small legacy DB2 set | CASC extraction, DB2 metadata/layouts, file-data IDs and hotfix support | Existing extracted assets and data loaders cannot be assumed compatible with the modern data path. |
| Database model | Legacy account/realm schema and this repository's bot extensions | Battle.net-linked accounts, build authentication keys, modern realm schema, character schema and hotfix database | Classic schema/updater paths must never run against the boss-bot databases. |

The static opcode comparison found **1,346 legacy entries**, **1,673 Classic entries**, and **654 identically named entries shared between them**. All 654 shared names have different numeric values. These are explicit hexadecimal enum entries, not a count of every semantic packet correspondence; renamed packets need separate mapping, and equal IDs would not establish equal payloads.

| Packet | Legacy value | Classic reference value |
| --- | --- | --- |
| `CMSG_AUTH_SESSION` | `0x0449` | `0x3A0001` |
| `SMSG_AUTH_CHALLENGE` | `0x4542` | `0x420000` |
| `CMSG_PLAYER_LOGIN` | `0x05B1` | `0x390016` |
| `SMSG_LOGIN_VERIFY_WORLD` | `0x2005` | `0x3B0030` |
| `SMSG_UPDATE_OBJECT` | `0x4715` | `0x4B0000` |
| Start forward | `MSG_MOVE_START_FORWARD = 0x7814` | `CMSG_MOVE_START_FORWARD = 0x370000` |
| Stop | `MSG_MOVE_STOP = 0x320A` | `CMSG_MOVE_STOP = 0x370002` |

The changed object representation also matters for later archaeology. Legacy research sites/projects are fixed player update fields; the Classic reference has dynamic `ResearchSites` and `ResearchSiteProgress` structures. Correct legacy gameplay logic alone cannot populate that newer UI without a serialization mapping. This audit does not establish archaeology gameplay fidelity in either backend.

## What can be reused

The game's underlying concepts remain useful: position/facing, movement validation, terrain/pathfinding, session-to-player ownership and the existing gameplay scripts. Screenshots and keyboard/mouse input are outside the world protocol, so the harness architecture can serve either client after connection works. Read-only addon observations can be version-adapted independently.

The existing encounter dossiers' 4.4.2 research targets do not make this worldserver a 4.4.2 server. They describe intended gameplay behavior; the installed transport, update-field layout and client-data loaders still target 4.3.4.

## Smallest meaningful live milestone

The first useful acceptance sequence is a real local account login, character enumeration, character login, visible world/player creation, then a key-driven forward/stop/turn/jump sequence. Capture screenshots, addon position/facing/speed and the server's matching movement receipt. Confirm that stopping ends displacement and that another client does not receive the input.

That needs compatible login/authentication, encryption, character packets, essential login initialization, GUID/object updates and movement packets. A movement decoder by itself cannot reach this milestone. Confirm correct state on both sides before involving Laya or training a policy.

## Isolation required before any trial

At the static audit checkpoint, [442_isolation_plan_v1.json](../../experiments/configs/client_harness/442_isolation_plan_v1.json) was a proposal with launch disabled. It now records the subsequently provisioned lab. The [runtime startup trial](runtime_launch_20261001.md) started isolated legacy servers and the 60895 client, confirmed a local TLS login connection, and did not establish world entry. The static findings below remain prerequisites for a playable movement trial.

Use a **dedicated MariaDB instance and new data volume**, not the existing boss-bot instance. Proposed loopback port: `13306`. Initialize fresh `client442_auth`, `client442_world`, `client442_characters`, and, if required by the chosen modern protocol/core, `client442_hotfixes`. Generate a dedicated runtime user/password. Its grants must cover only these schemas, and no existing live database import is authorized by this audit.

Use independent server config/log/capture directories, client WTF/Cache/Logs, Wine prefix and client working directory. Proposed loopback listener ports are `13724` for legacy auth if a bridge needs it, `11190` for modern Battle.net login, `18081` for login REST, `18085` for world and `18086` for a legacy instance socket if needed. Port availability still needs checking immediately before provisioning. Disable bot autostart, remote admin and SOAP. Do not launch through the existing default `make host-world`/`make host-auth` targets because they derive the shared test configuration.

## Implementation choices

1. **Port the existing backend's client boundary.** Add modern login/framing/authentication and semantic packet serializers while preserving the gameplay engine. This best preserves the current bot/script investment, but touches much more than movement. Replacing a few opcode headers is insufficient.
2. **Build a protocol bridge.** Present the Classic protocol to the client and translate to the legacy backend. This preserves the legacy server, but still needs authentication, stateful GUID/field mappings, world initialization, movement and related packet translation. No functioning 4.4.2-to-this-backend bridge was found in the inspected tooling; this is an implementation option, not an available dependency.
3. **Use the Classic core as the experimental runtime and port selected backend work.** Its pinned source already supplies the modern protocol and records build 60895. This reduces transport work, but it does not contain this repository's complete bot/runtime modifications, and it does not automatically inherit their gameplay behavior.

My assessment is to use the pinned Classic code as the reference for a bounded login-to-movement investigation, then decide between a client-boundary port and a separate experimental Classic runtime. Keep that decision separate from the ongoing boss-bot branch. This audit does not authorize migrating its database or replacing its runtime.

## Remaining uncertainties

- The Whitemane executable and launcher may modify authentication, endpoint selection or client behavior. File version alone does not establish vanilla protocol behavior. The inspected Config.wtf uses `portal "US"`; it is not a local lab profile.
- The inspected client folder has no top-level `Data` directory or `.build.info`. Its actual launcher-managed data location and completeness have not been established. This does not prove the installed client is unusable; it means a standalone modern extractor/client launch needs additional asset-location verification.
- No launcher, TLS/certificate setup, live packet exchange, account creation, terrain load, character creation, movement or addon API behavior was tested.
- A static upstream comparison establishes architectural incompatibilities, not an effort estimate or successful port. Exact client packets must be confirmed during the isolated connection milestone.

## Reproduce and inspect

Clone the official `cata_classic` reference without checkout and pin the recorded commit. Run through the existing Pixi environment:

```sh
pixi run --manifest-path /home/runiir/Games/trinity-cata/pixi.toml python tools/client_compatibility/audit.py \
  --local-root /home/runiir/Games/trinity-442-compatibility \
  --reference-root /tmp/trinity-cata-classic-compat-reference \
  --reference-commit 6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2 \
  --client /home/runiir/Games/_whitemane-60895_/WowClassic.exe \
  --output /tmp/a-new-empty-compatibility-evidence-directory
```

Primary reference files are the pinned [opcode table](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Protocol/Opcodes.h), [world socket](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/WorldSocket.cpp), [authentication packets](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/AuthenticationPackets.cpp), [movement packets](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/MovementPackets.cpp), [update fields](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Entities/Object/Updates/UpdateFields.h), and [auth schema](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/sql/base/auth_database.sql). Official [client setup documentation](https://trinitycore.info/install/Client-Setup) describes the modern portal and launcher setup; it does not certify the Whitemane executable.

## UI154 occupied stable swap persistence repair

The bridge-only deployment preserves both original offline actors, all five protected fixtures and the two HDMI-1 client lifetimes. Preparation01 and Erma open01 fail before input on an exact restoration-name guard and a stale image. Fresh sources pass. Forward swap01 passes12 checks and ordinary Call Pet restores Harnesswolf with7. Return swap_back01 remains whole failed and excluded: native SlotUpdated(4,5,6,0), result08 and public UI succeed, but both saved SQL pets receive slot0. The dependent Call Pet caption attempt rejects that failed source before input. Neither pet is deleted.

Native UpdatePetSlot queues displaced B using owner+slot, then active A's RemovePet commits A at that same slot before the queued transaction runs. The predicate updates both pets. The repair selects B by owner+petNumberB. Regression tests compile the actual C++ function, replay immediate/queued operations using the actual prepared SQL in an isolated in-memory database, reproduce the previous duplicate, and verify active A/B/no-runtime cases and unrelated owner/pet preservation. These4 checks and18 native-only continuity guards pass22. Native build01 uses one job with10,656,700 KiB available, produces SHA facd88428efae044c2ca8e442639b74f9c38399e72c31671d7a336800f59f08e, and leaves worldserver1181245 unchanged.

Two source-bound ordinary moves through an empty stable cell restore Harnesswolf4 to native5 and test Wolf6 to native0 (6 checks each). Ordinary Call Pet restores Wolf6 with7 checks. Cleanup receipts add no qualification and never rewrite the failed return. The candidate binary is included in the closed DVC checkpoint before native deployment. A fresh whole live validation is required. The count remains446/916. Scripts stay blocked; original softTargetInteract0 remains unrestored at stock1.

On the user's request, UI155 user_stop_primary01 stops only owned primary launcher1066751 and game1066985 while Harnessone is offline. Eight checks verify both processes absent, full primary/protected saved state preserved and scout/native/bridge lifetimes unchanged. Default operation now uses the scout alone; the primary is launched only when a test requires two clients. Future pair closure accepts this exact hash-bound shutdown receipt and rechecks absence and the full offline primary snapshot. Earlier two-client lifetime receipts retain their historical meaning.

## UI155 fresh occupied swap after native repair

Native1971415/51951236 runs candidate facd88428efae044c2ca8e442639b74f9c38399e72c31671d7a336800f59f08e; bridge1903647 and native configuration remain unchanged. Both original offline restoration receipts pass7. Preparation01 rejects the receipts' placement outside the deployment folder before input; fresh nested selection-only receipts and preparation02 pass13. Hunter entry passes9.

The fresh occupied forward and return swaps each pass12, including exact native/client requests, occupied updates, result08, public slots and complete saved pet rows. Each normal Call Pet recovery passes7. Named Harnesswolf4 returns to native5/inactive0 and test Wolf6 to native0/active1; both retain CreatedBySpell883 and their complete identities. Normal parking passes4 and original Harnesstwo selection passes5. Read-only close01 fails on a recorder name collision; the imported primary snapshot reader is aliased, and separate no-input close02 passes23. The failed closure is immutable and excluded. Forty-seven native/identity/checkpoint/ledger regression checks pass; they did not exercise that closure name collision.

Local full source/frame/packet proof passes, including both real Call Pet883 request/completion counters and separate native pet-load counter0 notifications. Inventory admission is false until actual remote archive review. Primary remains stopped at the user's request, with exact eight-check shutdown source; all five protected actors and the offline primary snapshot remain unchanged. Only the existing HDMI-1 scout client remains active. Count stays446/916 pending remote admission.

Remote review01 fails before admission because the saved-pet helper imports the UI runtime and its protobuf dependency into the default DVC environment. The unchanged identity functions are moved to a pure module;25 focused identity/checkpoint/ledger tests pass. Fresh remote review02 reads the actual394285937-byte compressed archive, verifies SHA5a2a4e9a31d5750a7cf584536a217c6707046f77851f8734d562142cbfe7ab01 and all67 JSON/205 PNG members, and proves both ordinary occupied swaps and Call Pet recovery tracking. Only `pets.stable_swap` is admitted, raising coverage to447/916 with469 open. Every earlier failed whole receipt remains excluded. The remote proof allows local frame/archive eviction; default operation uses the scout alone.

## UI156 disposable pet Abandon Cancel

Only the scout runs. Same-runtime retained Hunter entry passes9 and passive observer145 reads the stock PET popup without invoking a gameplay API. Dialog01 remains whole failed because this installed client uses Okay instead of the expected Yes. Cancel01 closes the dialog and preserves Wolf6 but remains whole failed on an unsupported already-selected pet restoration. Both failures are immutable and excluded. Corrected fresh dialog03 passes11 and separate Cancel02 passes12. Normal parking4, original Harnesstwo selection5 and no-input final close18 preserve both pets, all protected actors, complete owner saved state and exact user-stopped primary snapshot. Named Harnesswolf4 remains native5/inactive; disposable Wolf6 native0/active. Local complete source/frame/event proof passes and rejects all18 unsafe variants.25 focused identity/checkpoint/ledger tests pass. Inventory admission remains false until actual remote review of UI156.

A source-backed Abandon request candidate translates the pinned modern PackedGuid128 to native uint64 only after current owned Hunter/control catalog/summon/abandon permission checks. Its private raw probe is limited to owner6/test pet6/entry299/exact session and90 seconds; it cannot capture Harnesswolf. Candidate ownership/revocation and probe tests are committed but not run. Build01 rejects an incorrect CLI flag; corrected build02 stops before CMake under the existing6 GiB memory guard. Candidate remains unbuilt and undeployed; native1971415 and bridge1903647 are unchanged. Available memory dropped below the guard with swap full. The primary will stay stopped; a future bridge deployment must support the exact stopped-primary boundary instead of launching a second client to satisfy a historical lifetime check. Confirmation, fresh Tame/channel/PetAdded and the broader pending interaction inventory remain open.

Actual UI156 remote review verifies183631184 bytes, compressed SHA0133c5b076a708ae23404a765261a17cbcd8e7aedba54be973ca1b7ec1f4177d and all30 JSON/102 PNG members. Its archived event stream contains no Abandon request during the exact accepted dialog03/Cancel02 interval. Only `pets.abandon_cancel` is admitted, raising coverage to448/916 with468 open. Earlier failed whole trials remain excluded. The original client lifetimes and native/bridge are unchanged at this closed boundary; primary remains stopped.

## UI157 client resource pause

After the fully remote-verified and offloaded UI156 cancellation, scout_resource_pause01 stops only owned scout launcher1067873 and game1068121 while all six owned characters are offline. Eight checks pass; complete before/after native/saved/pet/inventory snapshots of all six actors are equal. Primary remains stopped. Native1971415/51951236 and bridge1903647 are unchanged; other experiments and the unowned user client are untouched. A harmless Xlib destructor warning follows the completed stop when the private display closes; the stop itself exits0 and passes all checks. Both owned clients are now stopped to save memory.

The UI157 one-job bridge build still rejects below6 GiB available memory before CMake. Candidate remains unbuilt, undeployed and untested. All earlier failures, including the bad CLI flag and both low-memory guards, remain recorded. Resume with a source-bound new scout client lifetime/private display and single-client deployment only when memory permits. Do not start primary to satisfy an old two-client guard or bypass the memory guard. No Abandon confirmation or fresh Tame input has been sent.

## UI158 one-client deployment preparation

UI157 actual remote integrity verifies28508022 bytes, compressed SHA7258e42d4933e9a10e5f1ca398e2def4b6aeb733604435c95c4a9c4f59156284, all8 JSON and1 PNG. Its single frame and exact local archive/cache are offloaded. Both clients stay stopped; all six offline characters and pets are unchanged. UI158 build01 retains the existing memory refusal; build02 passes with one job and6400780KiB available, source2cc0e87cbdc84fe67a1acd8d834410298845b2a6308094d574273121bded5e38 and binarydfb403b515868583c3131af673e93b2f45b63a58a5f87d5959e3175679b48188. Abandon ownership and private-probe30 guards pass.

Full suite01 has4 failures/3832 passes because older tests mock ctl.Input instead of the current native adapter and therefore try to initialize real input while clients are absent. Test-only repair mocks the production dependency and preserves the wrong-monitor/no-input assertion. Targeted24 and full suite02/3859 pass. This failure remains recorded. A separate single-scout deployment requires the whole source-bound resource pause, exact primary stop, complete six-character snapshots and successful candidate tests. Only the scout can relaunch on verified HDMI-1 with a new private display/lifetime; the primary is never manufactured as reconnected. Retained Hunter continuity across both explicit lifetime changes passes23 guards. A stock disposable-only confirmation controller preserves every named-pet field and requires one exact modern/native request pair; no live confirmation has been sent. Native and deployed bridge remain unchanged until the verified installation step.
