# Magmaw Drudge source-home clearance repair handoff

The exact `9ce642a0f65721cf0868dcd9bc928592ebab010a` Canary26 failed closed under the completion watchdog after 297.124 seconds. It completed the entrance regroup and Chainwielder trash node, reached `bwd.magmaw.drudges`, and stopped on `death_loop_watchdog` with four deaths and six of ten bots alive. It did not reach or kill Magmaw. Identity, telemetry demultiplexing, cleanup, and forbidden-assistance gates passed. This is failed diagnostic evidence, not a clear.

The prior reseparation resource-classification repair worked. Pure `drudge_native_charge_lane_reseparate` work owned movement resource `4` instead of the former generic route mask, and independent healing actions executed. The next failure was downstream geometry. After the first exact-roster reseparation, non-tank recovery checks used only the Drudges' live positions. Bot 30003 passed the configured 15-yard live-source checks at approximately `(-296.112, -62.407)`, but that point was only 12.36 yards from source 0's native home. It then moved to approximately `(-294.078, -59.781)`, 10.56 yards from that home, and died. The native source can return toward its home, so live-position-only admission was not a safe invariant.

Commit `b673f5f565052fbc5afd4a46fc8677cc1236fe34` implements one bounded repair. Dynamic non-tank recovery endpoints, cached anchors, prior proofs, group-position checks, reseparation receipts, and native path segments must remain outside the existing 15-yard exclusion radius around both each source's live position and its native home. Tank recovery remains exempt so ordinary tank ownership and source following continue. The repair does not change thresholds, force movement or threat, teleport, revive bots, mutate the Drudge AI, or manufacture an encounter result.

Focused validation passed 246 tests, `git diff --check` passed, and every touched C or C++ source/header remains below 1,000 lines. The exact clean `b673f5f565052fbc5afd4a46fc8677cc1236fe34` worldserver build passed through the queued coordinator. Its binary SHA-256 is `ae7a15109cb4d353dab8283a4d26c7b2c4c0e923d91e4e1ea23bb6284e87eb64`.

The next action is live verification only. Provision a fresh exact ten-player roster and run one completion-watchdog Canary27 on the `b673` binary. There is no fixed raid success timer. If it fails, retain the closed evidence and route only the first newly proven edge. If it clears entrance, Chainwielder, Drudges, and Magmaw, repeat on a fresh roster for the required consecutive clear.

Failed Canary26 evidence:

- Report: `/tmp/trinity-magmaw-9ce642a0f6.3UefTk/canary26-run/capture/report.json`
- Canonical report SHA-256: `9e8a6c5f4f3c1212a216b23f87bf4cb1e93353f5792b43e12eeb8cf2de3cbf60`
- Report file SHA-256: `37c004ed1b771f3810118fe778228ae017687cefa57b9fc1c1e94215503539cf`
- Raw trace SHA-256: `336e5a3cf92eedd577c89ed8945d97b26b35a9eff5c683ea4024a06d277f4fd9`
- Server log SHA-256: `49f535152756bc892d1a83a3e178387c7d4b20d6b94f31e9ef81133a3816abf6`
- Exact build receipt: `/tmp/trinity-magmaw-9ce642a0f6.3UefTk/worldserver-build-receipt.json`
- Build receipt file SHA-256: `151679b673a317ff162b7567b2c3d9274fc6d0128379f31c4a7640cd7a438f7d`
- Exact binary SHA-256: `8ae8f1cd0003b77bbbf75d34f496f2f75606ecb40782089b9fed851c2d760c7c`
- Run identity: server epoch 6049740017052537, attempt 2, route generation 3

Do not promote Canary26 to DVC acceptance data.
