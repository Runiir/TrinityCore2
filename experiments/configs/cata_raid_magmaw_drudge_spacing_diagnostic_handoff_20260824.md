# Magmaw Drudge reseparation repair handoff

The exact `d9024ddb5cc9e213e9f0048444b66522cd4d005c` canary `canary1r2` failed closed under the completion watchdog after 346.533 seconds. It regrouped at the entrance, cleared the Chainwielder, reached `bwd.magmaw.drudges`, and stopped on `death_loop_watchdog` with three deaths and seven of ten bots alive. It did not reach or kill Magmaw. Identity, telemetry demultiplexing, cleanup, database storage, and forbidden-assistance gates passed. This is failed diagnostic evidence, not a clear and not acceptance data.

The bounded receipts now identify the first useful behavior boundary. Receipt 119 for bot 30008 completed selection, arbitration, native movement, progress, arrival, and closure. The first later selection failure was bot 30005 at `(-311.5, -71.3, 213.292)`: candidate 0 was rejected as `drudge_anchor_source_unsafe` with `source0_safe=false`, so arbitration and movement were correctly not attempted. The same batch also contained lane and floor rejects. The first accepted-selection arbitration divergence was receipt 74 for bot 30008, rejected as `higher_priority_movement_active`; later submissions did succeed, so that retryable rejection alone is not a lethal attribution.

All 14 observed Drudge charges landed. Charge sequences 1 through 8 recorded exact ten-player reseparation. Sequences 9 through 14 recorded none. Sequence 9 was the first missing reseparation: source 59, spawn 250140, target 30003, valid range and interval, but zero complete native threat candidates and a spacing failure for bot 30006 with `source0_safe=false` and unsafe group position. The first trace-backed repair scope is therefore Drudge route candidate geometry, lane anchoring, and its interaction with movement arbitration after repeated landed charges. It is not a class rotation repair. Shared movement arbitration must not be changed unless the specialist proves that a shared edge, rather than the route candidate, caused the failure.

The death order was bot 30003 at `1787636669930`, bot 30007 at `1787636686123`, then bot 30004 at `1787636689858`. Recovery remained `native_recovery_wait_hostile_activity`; no resurrection, runback, or re-entry occurred. The trace also retained 1,600 `no_valid_profile_action` blocks, but valid native spell outcomes were observed and these blocks are not yet proven to cause the first reseparation failure.

The next specialist must make at most one trace-backed repair in the Drudge route movement/geometry slice, add focused deterministic coverage for the demonstrated repeated-charge case, and keep every changed C or C++ source/header below 1,000 lines. It must return no edit if it cannot prove a repair from these receipts. After review, build the exact clean repair commit through the queued coordinator, provision a fresh ten-player roster, and run one completion-watchdog canary. There is no fixed raid success timer. Do not teleport, force movement or threat, revive bots, alter native encounter state, or manufacture an outcome.

Failed local evidence:

- Report: `/tmp/trinity-magmaw-d9024ddb5c/canary1r2/capture/report.json`
- Canonical report SHA-256: `cf878046267b89b1b4173bb723c296670c3d2e2e2243bca8774e647158fafe21`
- Report file SHA-256: `686ca50b0529e4b7f2a5acba37496d8c6cbe3d2b8d903a7153cdbf229d11d416`
- Raw trace SHA-256: `7da942700514788b203c1b4fff4c841fce2846e7f70c315b3d01922d096b04dd`
- Server log SHA-256: `382e3a134f6d4df325a86aff858f945fd4f4ae8069f18438936f9eea817791d3`
- Exact build receipt: `/tmp/trinity-magmaw-d9024ddb5c/build/worldserver-build-receipt-v8.json`
- Receipt-bound SHA-256: `f002e800251ab2c6f8c7ff54c3ad8d8fff45256ed869c964c22584f63622a5ec`
- Exact binary SHA-256: `73a669506fc1320608fdd917b4bb66548896b67735ae787c950185890bfb4264`
- Run identity: run 2835, server epoch 322515630582308, attempt 2, profile generation 1, route generation 3

Do not promote this failed run to DVC acceptance data.
