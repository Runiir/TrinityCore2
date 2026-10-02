# Standalone C++ world bridge

This migration replaces the Python modern/native world-packet path with a separate
C++20 process. It uses Boost.Asio, OpenSSL, zlib, Boost.JSON and the MySQL client
library. Building it does not build or restart Trinity's worldserver.

C++ and Rust both support this workload. C++ fits the existing Trinity toolchain,
wire types and deployment dependencies. Rust with Tokio would offer memory-safe
ownership, but introduces another language/toolchain and separate protocol types.
This is a repository integration decision, not a claim that C++ is intrinsically
faster than Rust. Python has not yet been measured as a live bottleneck.

References: [Asio concurrent execution](https://www.boost.org/doc/libs/latest/doc/html/boost_asio/overview/core/threads.html),
[Tokio](https://tokio.rs/tokio/tutorial),
[OpenSSL Ed25519ctx](https://docs.openssl.org/3.5/man7/EVP_SIGNATURE-ED25519/).

## Migration status

The separately built codec covers modern AES-GCM framing, native header ARC4,
world key derivation, Ed25519ctx/RSA signatures, supported movement/control ACKs,
native object parsing, player/creature/GO/item creation, profession/research fields,
Survey casts, owned aura changes and artifact loot. The declarative create
serializers compile once at startup. Unsupported optional serializers fail when
used; they do not silently produce a new layout.

Twenty-three differential tests currently compare the candidate against the Python
oracle, including captured ordinary client/native packets and rejection boundaries.
The standalone service now also implements asynchronous networking, authenticated
realm/instance ownership, menus, taxi, portals and public client data. Database
operations use a separate worker pool. Public tables and serializers are cached at
startup. Each connection has its own strand, encryption counters and bounded queues.
The optimized native service is now the default. The cutover preserved the running
native auth/world services and private DBs. Two real clients passed simultaneous
observation and bounded keyboard movement, with separate accounts, GUIDs, prefixes,
sessions and verified HDMI-1 windows. Both launcher SSO and username/password world
entry passed. Gear preview, bags, professions, Survey cast bars, mount/flight and
console fixture transfers were also observed through the native service.

The latest authentication/world suite passed 277 tests. All 54 selected packet and
codec tests passed ASan/UBSan. The initial migration's 23 differential tests found
and repaired a profession-JSON lifetime error. Real clients exposed a dense update that expanded beyond 64 KiB;
the outbound limit now accommodates it while retaining the stricter incoming limit.
The earlier failed receipts are retained alongside the passing runs.

Party member snapshots, compact raid-frame profiles, assistant permissions and
role polls now translate both ways. Native partial member updates accumulate into
bounded, complete modern snapshots without invented health values. In-range other
player object creation and movement still need implementation and qualification.

The native five ground markers use the existing worldserver spell handlers.
Their destinations and native dynamic-object positions feed the modern eight-slot
marker packet. Markers 6–8 are group annotations owned by this C++ endpoint; no
native spell outcome is claimed for them. Placement requires normal group
permissions and a valid ground destination. The extra annotations use a 100-yard
range check. Transport-relative placement and reconnect persistence are unqualified.
See the [interaction report](../../../docs/client_harness/interactions_20261002.md).

## Independent build and parity checks

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.world.control build
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.world.control start
CLIENT442_CODEC=/home/runiir/.local/share/trinity-client442-lab/build/native_bridge/bridge_codec pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m pytest -q tools/client_compatibility/world/tests/test_native_bridge_codec.py
```

The supervisor also provides `world.control build` and `world.control start
--engine cpp`. `build` records source/schema and binary hashes. Starting a stale
binary is rejected. The default is `--engine cpp`; `--engine python` remains an
explicit reference/fallback option. `--sanitizers` selects a separate ASan/UBSan
build directory; it does not replace the optimized executable.
`client442_bridge --root <lab> --repo <worktree> --self-check` verifies private DB
identity and public table loading without opening a listener. No credentials belong
on the command line. The target requires OpenSSL 3.5 for Ed25519ctx support.

Python supervises the service and supplies its test oracle. `client442_bridge` and
`bridge_codec` have no Python runtime dependency. The codec never opens a live game
socket. A deterministic Survey-to-loot regression tests ordinary telescope packets,
public terrain/boundaries, keyboard movement and mouse interaction without a model
or private next-find coordinates. Its initial Grimsilt trial showed the cast bar
but stalled near terrain and stopped on combat; the diagnostic now detects confined
non-green backtracking earlier. A later Hammertoe trial completed a bounded green
recovery flight, then clicked and gathered an artifact. Native loot/currency packets
reported eight Dwarf fragments and a saved DB check confirmed them; the gather
animation ended. The first recovery-controller test exposed a landing correction
being considered before takeoff for short routes; phase gating fixed it. These
diagnostic receipts are distinct from the historical Laya proof.

Normal taxi and portal travel still need fresh native-service live qualification;
a console fixture transfer proves packet handling rather than autonomous travel.
General gameplay/content coverage and long-duration fleet recovery remain open.
Track latency/CPU under concurrent sessions separately from semantic parity. The
two-client trial is not a throughput benchmark. Keep per-session queues and frame
sizes bounded and exclude authentication material from diagnostics.

Generated traces, screenshots, test results, build receipts, inventories and
DVCLive metrics are checkpointed with `checkpoint_native_bridge.py`. The archive
excludes credentials, authentication bodies, client prefixes and CASC caches. Use
the [lab runbook](../../../docs/client_harness/README.md) for actor ownership and
the DB-first repair workflow.
