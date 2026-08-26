# Magmaw Canary38 Drudge escape-path handoff

Canary38 ran exact clean source `bc755ada8410798c8319e168bdaaff09fc0847f4` under the uncapped completion watchdog. It cleared the entrance regroup and Chainwielder, then failed closed at the Drudge pair after 368.636 seconds on `death_loop_watchdog`. Magmaw was not reached. The worldserver exited normally, final forced diagnosis and trace passed, telemetry identity remained clean, forbidden assistance was absent, and cleanup removed every bot and lease.

## What Canary38 proved

The post-Rush lane-local offense repair worked. Both tanks retained native Drudge ownership, twelve Rushes landed, and all seven offensive roster slots `30001`, `30002`, and `30006` through `30010` submitted trained single-target profile actions. Before the first death the trace contained 40 `drudge_lane_single_target_action` decisions, 397 native spell casts, 344 attacks, 128 raid-heal actions, and 127 trained heals. The last complete pre-death geometry sample placed the two Drudges near 79.6% and 78.3% health. Canary37 had only six single-target actions and left both Drudges near 96%, so cross-lane offense suppression is closed.

## First actionable runtime edge

`unsafe_drudge_member_escape_exhausts_native_candidates`

The first death was Holy Paladin `30004` at timestamp `1787725556666`. Its route trace first recorded `drudge_anchor_native_end_rejected:end2d=0.977814:endz=0.129654`, then repeatedly recorded `drudge_anchor_native_path_rejected:path_type=8`, where `8` is Trinity's `PATHFIND_NOPATH`. The bot remained on the unsafe declared lane anchor with `no_valid_profile_action` and `blocked_no_fallback`; no alternate safe native movement was submitted before death. The native damage source is not attributable from the retained trace and must remain unknown.

Tank `30001` died 28.594 seconds later at `1787725585260`. Affliction Warlock `30008` died 8.536 seconds after the tank at `1787725593796`. Both later deaths occurred while native hostile activity remained active and full-wipe-only recovery correctly returned `native_recovery_wait_hostile_activity`. Partial resurrection is not an admissible repair.

## Bounded repair contract

- Preserve the declared Drudge anchors as the first deterministic choice.
- When a non-tank is unsafe relative to the live-plus-native-home source union and the declared or first dynamic endpoint fails strict native path admission, continue through bounded deterministic outward candidates in the same tick or retry heartbeat.
- Admit only a complete native path with valid floors, safe endpoint, monotonically outward escape from every source the bot starts inside, and no inward regression for sources it starts outside.
- Submit ordinary movement through the existing movement arbiter and native executor. Do not call `MotionMaster` from encounter policy code.
- Preserve exact attempt, wipe, route, source, lane, spacing, arrival, and movement-lease identity.
- Preserve the verified lane-local offense, native Rush, tank ownership, health-sync, kill-sync, and full-wipe-only recovery behavior.

Do not reduce the 15-yard safety distance, accept `PATHFIND_NOPATH`, grant pathing or line of sight, teleport, force threat or victims, change healing priorities or enemy damage, resurrect partial deaths, alter Drudge AI, or manufacture a clear.

## Required implementation evidence

Add focused deterministic replay coverage for:

1. an unsafe non-tank whose declared endpoint has a small native endpoint miss;
2. a first dynamic candidate returning `PATHFIND_NOPATH` while a later bounded outward candidate is valid;
3. rejection of inward, unsafe-endpoint, incomplete, shortcut, off-floor, and source-home-unsafe candidates;
4. selection and native-arbiter submission of the first valid later candidate;
5. retention of lane-local offense and full-wipe-only recovery gates.

Every touched C or C++ source/header must remain below 1,000 lines. Do not build or run a live shard from the implementation work unit. After root review and a queued exact build, run a fresh Canary39 under the completion watchdog.

## Immutable Canary38 evidence

- Source commit: `bc755ada8410798c8319e168bdaaff09fc0847f4`
- Source tree: `403bc4198f8bbcfc1f55095e5605e054c9e23b4d`
- Binary SHA-256: `f04c7d4bae584dafd7bc4fe09931e79121adc86b243dcefee76c1b8e3e7eea79`
- Build receipt: `/tmp/trinity-magmaw-bc755ada84-build.fclN4A/worldserver-build-receipt.json`
- Build receipt file SHA-256: `8748d1ad884d53c1c1144f9953848eccbec80b8a22dc0493fd244de1b730fafc`
- Build receipt canonical SHA-256: `059245ed9991daa0871db4a01aa5aeca1e0696313d91cfe03f76d7ec9ff0b657`
- Report: `/tmp/trinity-magmaw-bc755ada84-canary38.OrV5wb/canary38-run/capture/report.json`
- Report canonical SHA-256: `a8ff90e0dbeefa6a514ff8cc44b8a26b0b2b6484c8c8116c08c4ab5eef1751bc`
- Report file SHA-256: `7294be1c5f59a1b4d5c5a4828e55ff6e2faae7fe68824eb2e9a932a380a540e5`
- Raw trace SHA-256: `1de5f7272e5a8a23c66595f47b24a159a85fb7badefc184ec7a4a2ef3c8b6e23`
- Server log SHA-256: `334d0e59ba62b51720f13f7ababe605ac3851df2a28bdf8f0cd5aae6b8f1cee8`
- Run identity: server epoch `1788240621933761`, attempt `2`, route generation `3`
- Terminal result: `gameplay_failure`, `death_loop_watchdog` at `3/3`
- Route result: entrance clear, Chainwielder clear, Drudges incomplete, Magmaw not reached
- Death order: `30004`, `30001`, `30008`
- Native Rushes: 12 landed, six per source; the final two prepared Rushes did not land before shutdown
- Native ownership roster: `30001`, `30002`
- Offensive profile roster: `30001`, `30002`, `30006`, `30007`, `30008`, `30009`, `30010`
- Final forced diagnosis and trace: passed
- Forbidden-assistance gate: passed
- Evidence demultiplexing: 132/132 retained rows bound, zero rejected or unchecked
- Cleanup: passed, worldserver exit code `0`, zero bots and leases

This failed canary is diagnostic evidence only. Do not promote it as an accepted clear.
