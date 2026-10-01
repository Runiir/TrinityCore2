# Whitemane 4.4.2 local authentication

Both **direct username/password login** and **launcher SSO** now authenticate the real Whitemane 4.4.2 build 60895 client and reach the `Client442 Lab` realm list. The game launches on HDMI-1, the second monitor. The lightweight launcher is available at [127.0.0.1:18081/launcher](http://127.0.0.1:18081/launcher).

This document records the authentication checkpoint. The subsequent [world movement trial](world_movement_20261001.md) added a build-60895 frontend, entered the native world and validated keyboard movement. Realm discovery now advertises build 60895 when that owned frontend is running and reports the native mismatch otherwise.

## What was implemented

The worktree contains a small Python login adapter under `tools/client_compatibility/auth/`, with its own locked Pixi environment. It serves Battle.net protobuf RPC over TLS on `127.0.0.1:1119`, and login REST plus the local launcher on `127.0.0.1:18081`. The native authserver on port 13724 and worldserver on port 18085 remain separate.

Direct login uses Battle.net SRP v2 with SHA-256 proofs and the client's signed PBKDF2-SHA512 password exponent. It supports the reference `JSESSIONID` cookie and state retained on a persistent HTTP connection. The client obtains a short-lived REST ticket, verifies it over TLS and receives its linked game account and realm-list ticket.

Launcher login checks the same modern verifier and issues a 600-second SSO ticket. The pinned Whitemane launch helper writes the ticket into the lab's private Wine registry. The game starts with `-launcherlogin -uid WoW` and submits cached web credentials automatically. Neither the account password nor the ticket appears in process arguments or diagnostics. Choosing **Open game login** clears the lab's launcher registry entries and starts without the SSO flag, preserving manual login.

The launcher has username/password fields, **Sign in and launch**, and **Open game login**. It refreshes its request token after service restarts, reports launch progress and errors, and uses the existing verified second-monitor placement worker. It reuses the tested patch helper rather than implementing a new executable patcher.

Only `client442_auth` receives new tables: `lab_login_accounts` and `lab_login_tickets`. The modern account is linked to the existing lab native account, `CLIENTLAB`. Modern SRP verifiers and SHA-256 hashes of expiring tickets are stored in that isolated database. Native account fields, the running boss database and the mainline server binaries were not changed. The password remains in the private `~/.local/share/trinity-client442-lab/secrets/game_account.json` file.

## Source and scope

Wire descriptors and SRP behavior come from the official Classic reference pinned at `6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2`. `generate_schema.py` extracts descriptors from the generated C++ sources, preserves wire fields and removes generator-specific options. Its output records the upstream revision and source hashes. Derived definitions and SRP implementation retain GPL-2.0-or-later attribution.

Primary references are [Session framing](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/bnetserver/Server/Session.cpp), [authentication RPC](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/bnetserver/Services/AuthenticationService.cpp), [login REST](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/bnetserver/REST/LoginRESTService.cpp), [HTTP sessions](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/bnetserver/REST/LoginHttpSession.cpp), [SRP](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/common/Cryptography/Authentication/SRP6.cpp), and [realm services](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/bnetserver/Services/GameUtilitiesService.cpp).

TLS uses the pinned upstream development certificate, which the installed helper's patched trust bundle accepts. These are loopback-only lab services. No public service or production certificate deployment was configured. The adapter implements the login and discovery methods exercised by this client, not the whole Battle.net API. It does not implement a WebSocket login endpoint; successful observed exchanges use the referenced framed protobuf RPC and REST flow.

## Validation

The actual client completed both paths, including account-state RPCs, realm-list ticket creation, subregion discovery and successful realm-list responses. The launcher SSO path also exercised web-credential generation. Screenshots show the local realm selection dialog. The lightweight launcher's direct-login button starts a blank game login screen; its valid SSO API starts an automatically authenticated client. The browser rejects a deliberately invalid password and clears the password field.

Twelve focused tests pass. They cover mutual SRP proofs with mixed-case passwords, wrong-password rejection, proof replay rejection, invalid public keys, fragmented RPC frames, malformed protobuf, size bounds, invalid tickets, expired sessions, foreign game-account IDs, unsupported builds, command suffixes, compressed realm JSON, HTTP session persistence and launcher request validation. Live database checks also rejected wrong passwords, unknown tickets and an explicitly expired test ticket.

The first test run had **10 passes and one failure**: rejecting a foreign HTTP origin left its body unread, corrupting the next request on that persistent connection. The handler now consumes valid-sized bodies before rejecting their origin and closes connections when rejected input remains unread. The corrected test passes. Earlier live attempts exposed the required REST content type (`WOW51900312`), first-request `JSESSIONID` handling (`WOW51900317`), suffixed realm commands and the missing launcher-login startup flag; all were repaired and both complete paths were rerun. The first schema setup used an unsupported `BINARY(256)` column and was corrected to `VARBINARY(256)` before account provisioning. Startup now waits for the local service to become ready, and port checks tolerate TIME_WAIT while still refusing occupied listeners.

The [DVC evidence](../../artifacts/client_harness/442_modern_auth_20261001.tar.gz.dvc) contains sanitized event records, test results, code hashes, screenshots, monitor receipts and DVCLive metrics. It excludes passwords, verifier rows, tickets, registry files, Wine/CASC storage and the active database. The [saved isolation plan](../../experiments/configs/client_harness/442_isolation_plan_v1.json) retains the remaining world-entry requirements.

## Run and maintain

From `/home/runiir/Games/trinity-442-compatibility`:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.auth.control start
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.auth.control status
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.auth.control launch-direct
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.auth.control launch-sso
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml test
```

`launch-sso` uses only the private saved lab credentials. The browser launcher accepts credentials entered by the user. `stop` terminates only the recorded modern login process group after checking its PID and process start time. `setup --reference /path/to/pinned/TrinityCore` installs the pinned development certificate and provisions the linked account without overwriting an existing verifier. Regenerate protocol definitions with `python -m tools.client_compatibility.auth.generate_schema /path/to/pinned/TrinityCore` through the auth Pixi environment.

The [world movement trial](world_movement_20261001.md) completed the next connection milestone. Broader gameplay packet translation remains open.
