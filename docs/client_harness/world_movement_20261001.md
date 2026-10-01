# Whitemane 60895 world-entry and movement trial

The actual Whitemane 4.4.2 client can now enter Northshire as the native Trinity character `Harnessone` and move through keyboard inputs. Both launcher SSO and username/password login reached the world. Turning and walking changed Trinity's saved facing and position; jump, airborne heartbeat and landing packets reached the backend. The addon reported an alive character, matching facing, and zero speed after stopping.

All implementation work is in `/home/runiir/Games/trinity-442-compatibility`, branch `codex/442-compatibility-audit`. It uses the existing dedicated `trinity-client442-db` instance and the private client on HDMI-1. No mainline code, running boss-server configuration or boss database was changed by this work.

## Implementation

`tools/client_compatibility/world` is a compatibility frontend on `127.0.0.1:18087`. The frozen native worldserver remains the gameplay authority on `127.0.0.1:18085`, speaking build 15595. The frontend authenticates a real native session, asks Trinity to enumerate/login the character, translates its player snapshot, and submits translated movement through Trinity's normal packet handlers. It does not insert movement into the database. The movement trial asks the isolated server to `saveall` only to measure the resulting state.

The frontend implements the V2 initializer, build-specific authentication proof, Ed25519 encryption enablement, AES-GCM packet integrity/counters, a signed instance redirect and continued-session proof. Join tickets expire after 60 seconds and are consumed once. The native account is checked again for bans and IP locks at world authentication. Character login and movement are restricted to the authenticated account and active instance connection.

The client requires the **Win/x64/WoW** build-key variant. Its actual realm-join metadata and valid world proof established this; the WoWC proof is rejected. Modern GUIDs, character enumeration, race/class availability, initial data queries, the active player create layout, movement and time synchronization are translated semantically. Authenticated native enumeration must arrive before the modern character list is sent.

The reference is official TrinityCore `cata_classic` commit `6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2`. Opcode IDs, create-field definitions and native movement sequences retain their source identities and GPL-2.0-or-later attribution. The bundled RSA signing identity is the publicly published upstream development identity, not a private account or deployment credential. Relevant reference implementations are [world authentication](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/WorldSocket.cpp), [authentication packets](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/AuthenticationPackets.cpp), [object creation](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Entities/Object/Object.cpp) and [movement](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/MovementPackets.cpp).

## Validation and repairs

The launcher movement sequence changed facing from `5.13806` to `5.94231` radians, then moved approximately `2.71` world units horizontally. After landing, the saved position stayed unchanged across the stop check. The client emitted a jump, an airborne heartbeat at Z `83.1151`, and a landing at Z `81.5503`. An independent direct-login movement also changed the native saved position. Normal logout completed and returned to character selection without losing the realm connection.

The read-only addon under `tools/client_compatibility/observation` renders checksummed position/facing/speed/health observations into screenshot pixels. It does not call movement, spell or interaction APIs. The current 1280x720 capture decodes its panel at `(15,15)`, with a measured cell size of `3.75` pixels. UI scaling is reflected in this measured size. Facing matched Trinity within `0.002` radians. Input was delivered only to the owned nested Gamescope X display.

Eighteen focused tests pass across login and world protocols. The world tests cover build-proof rejection, packet tampering, replay and direction counters, signed instance continuation and expiry, movement ownership, invalid coordinates, entry-state gating and foreign-character rejection. The first combined test run hit a pytest module-name collision; renaming the world test module repaired collection. The previous twelve login tests continued to pass.

Live attempts also exposed incorrect native column/opcode names and initializer framing, the WoW/WoWC build-key distinction, unanswered client DB queries and missing race/class unlock data. These were corrected before world entry. The first visible walking attempt was rejected by Trinity because its active mover had not been acknowledged. Translating the modern completion acknowledgement to the native `CMSG_SET_ACTIVE_MOVER` repaired it; the subsequent saved database position proved acceptance. A fresh direct-login launch exposed the client's persisted `portal "US"` value after SSO. Every lab launch now restores the private loopback endpoints before starting the client, and direct world entry was rerun.

The [DVC checkpoint](../../artifacts/client_harness/442_world_movement_20261001.tar.gz.dvc) contains screenshots, addon/server samples, bounded safe packet/event records, code identities, JUnit results, monitor receipts and DVCLive metrics. Authentication bodies, tickets, session keys, verifiers, client logs, registry files and live database/Wine/CASC storage are excluded.

## Scope and next implementation work

This is a working **login-to-movement** compatibility slice. It is not a complete Classic gameplay port. The client currently receives its active player and terrain, while nearby NPC/item/gameobject creation, ongoing value updates, inventory/appearance, action bars, spell execution, combat and archaeology are still missing. Transport, vehicle and spline movement are rejected rather than encoded speculatively. UI character creation is not implemented; `Harnessone` was created through the native character-create handler for this trial.

Before an archaeology trial, implement gameobject/NPC updates and interaction, survey/cast/loot packets and the corresponding native archaeology behavior, then validate one complete survey loop. A bounded keyboard/mouse controller and screenshot/addon observer can already use this movement connection. No decision model was called or trained during this work.

## Run

From the compatibility worktree, with its owned native worldserver running:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.world.control start
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.auth.control launch-sso
# Or start a blank username/password login:
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.auth.control launch-direct
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m pytest tools/client_compatibility/auth/tests tools/client_compatibility/world/tests -q
```

`world.control status` and `world.control stop` inspect or stop only the recorded frontend process group. The lightweight launcher remains at [127.0.0.1:18081/launcher](http://127.0.0.1:18081/launcher). Its direct and SSO launch paths both use the restored private portal and second-monitor placement. Realm discovery advertises build 60895 only while the owned frontend and native worldserver are running; otherwise it reports the native build mismatch.

Regenerate the pinned definitions using `world.generate_opcodes` and `world.generate_fields` with the extracted reference tree, and `world.generate_native` with this checkout, through the locked auth Pixi environment.
