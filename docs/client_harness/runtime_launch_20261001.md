# Isolated server and Whitemane client startup trial

The lab authserver, worldserver and Whitemane **4.4.2 build 60895** client are running. The client reaches its login screen, but a playable session is **not established**. No character was created, and movement was not tested.

| Component | Local endpoint or location | Verified outcome |
| --- | --- | --- |
| Dedicated database | `127.0.0.1:13306` | Clean TDB content and worktree SQL updates loaded |
| Legacy authserver | `127.0.0.1:13724` | Native 15595 challenge accepted; synthetic 60895 legacy challenge rejected with status 9 |
| Worldserver | `127.0.0.1:18085` | Initialized and responds to console `server info` |
| Instance socket | `127.0.0.1:18086` | Listener running |
| Modern login | `127.0.0.1:1119` | Client TLS ClientHello observed by a temporary diagnostic listener; no compatible login service running |
| Client | `~/.local/share/trinity-client442-lab/client/_whitemane-60895_` | Launcher patches applied; login screen and scoped keyboard/mouse input verified |

The world database contains 221,766 creature spawns, 46,627 creature templates, 78,914 gameobjects and 14,991 quests. It was imported from the clean local TDB 434.22011 distribution and updated from this compatibility worktree. It was not copied from the running boss-bot database. The auth database contains one newly generated lab account, and the characters database contains zero characters. Bot autostart, the bot runtime, remote administration and SOAP are disabled.

## Launcher and authentication result

The private client uses the installed Whitemane 2.1.51 Windows launch helper, with the `cata-windows-60895` scenario and the installed distribution's version/CDN endpoints. Its identity is pinned by SHA256. It writes only lab settings and uses a separate Wine prefix, Gamescope display and working directory. No existing Whitemane account, SSO token or saved account settings were imported. The retained client executable still matches the static audit's original SHA256; the launch helper patches its process in memory.

Game launches now target the second physical monitor, currently **HDMI-1**, as requested. The launch uses an X11 SDL window so its position can be set reliably under GNOME. The placement worker selects the exact owned Gamescope PID, moves its window to the second monitor and verifies its coordinates. The recorded client rectangle is `(2880,217,1280,720)` within the monitor at `(2560,0,1920,1080)`. Launch refuses to proceed if a second monitor is unavailable. This preference is also saved in the project's AGENTS.md.

`SET portal "127.0.0.1"` routes the modern login service to loopback. The initial profile used a host/port string pointing at legacy auth; its interactive attempt returned `BLZ51901016`. That did not establish a connection to the legacy authserver. After correcting the portal to the documented IP form, the bounded loopback probe received `16 03 03 00 c5 01`, a TLS handshake record beginning with ClientHello, on port 1119. The probe closed without authenticating, did not read credentials, and left no listener running.

The first TLS record alone cannot tell whether later encrypted application traffic would be RPC or WebSocket. The pinned upstream Classic core uses [Battle.net protobuf RPC over TLS](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/bnetserver/Server/Session.cpp), together with login REST. Its [session declaration](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/bnetserver/Server/Session.h) supplies the account/ticket/session data. The [official client setup](https://trinitycore.info/install/Client-Setup) requires a custom launcher for 4.4.x. A WebSocket endpoint by itself would not implement that service contract.

The current authserver implements legacy GRUNT authentication, not that modern service. Separate synthetic GRUNT challenge probes returned `00 00 00` for build 15595 and `00 00 09` for 60895. These are native-service checks, not packets captured from the modern client and not successful account authentication. A fresh native lab account is available, with credentials kept in the private `secrets/game_account.json`; it is not yet a modern Battle.net-linked account.

The next implementation needs compatible TLS login, REST authentication, linked account and realm ticket handling, followed by 60895 world authentication, packet encryption, character initialization and object updates. The [compatibility audit](compatibility_442_audit.md) records those world boundaries. None are supplied merely by starting this legacy authserver or changing realm build numbers.

## Runtime identity and storage

This startup trial freezes copies of the existing host binaries in the lab's private `bin` directory. It is **not a fresh build from the compatibility worktree**. The authserver reports `2f13baea1115+` from September 19; the worldserver reports `cd860ebe6c90` from October 1. Exact binary hashes and copies are retained in DVC so their differing build provenance is explicit. Database updates use this worktree's `SourceDirectory`, and every database connection is checked against the dedicated instance before launch.

Early client attempts failed because the desktop application's library environment hid NVIDIA, a bubblewrap namespace lacked device/proc mounts, Gamescope could not own its X sockets in that namespace, and nested UMU runtime startup failed. The working launch clears the desktop library overrides, selects the host NVIDIA ICD, keeps Gamescope outside the data namespace, mounts devices/proc inside Wine's namespace and runs the pinned GE-Proton10-34 directly. No system GPU configuration or shared Wine prefix was changed.

A strictly read-only CASC mount produced a container-lock/startup error. The working client therefore mounts the source installation read-only and uses a private writable overlay. CASC opens its data archives for writing, causing about 15 GiB to be copied into that layer on first initialization. This local runtime storage is necessary for the tested isolation setup and is not a training dataset. An unnecessary 2.6 GiB copy of the installed addon tree was removed; the lab has its own empty Interface directory. Logs, WTF, cache, errors and the Wine prefix remain private.

Config files and generated credentials live under `~/.local/share/trinity-client442-lab/`, outside Git and DVC, with private permissions. Server process groups are recorded with PID and `/proc` start time; stop commands check both to avoid touching another process. Source client/data mounts are read-only, the database has its own container/volume/network, and no operation connected to the existing boss-bot databases.

## Operate the lab

Run from this compatibility worktree through the existing Pixi environment:

```sh
pixi run --manifest-path /home/runiir/Games/trinity-cata/pixi.toml python -m tools.client_compatibility.lab_runtime status
pixi run --manifest-path /home/runiir/Games/trinity-cata/pixi.toml python -m tools.client_compatibility.lab_runtime command --text "server info"
pixi run --manifest-path /home/runiir/Games/trinity-cata/pixi.toml python -m tools.client_compatibility.lab_runtime screenshot
```

After stopping an owned component with `stop-auth`, `stop-world` or `stop-client`, restart it with `start-auth`, `start-world` or `start-client --launcher`. Do not use the mainline default host targets for this lab. `import-content` refuses to overwrite a populated world database. `prepare-client` requires the tested installed launcher helper, and the launch verifies both helper and client hashes.

The [saved plan](../../experiments/configs/client_harness/442_isolation_plan_v1.json) records listener state and remaining world-entry requirements. The [DVC evidence pointer](../../artifacts/client_harness/442_runtime_launch_20261001.tar.gz.dvc) retains sanitized configs/logs, the database/import receipts, native challenge results, the TLS probe, a login-screen capture, frozen server binaries and DVCLive metrics. Private credentials and the active CASC/Wine/database storage are excluded.
