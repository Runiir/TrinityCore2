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
Live cutover qualification is pending. The Python service remains the default until
the complete native candidate passes validation with the real client.

## Independent build and parity checks

```bash
cmake -S tools/client_compatibility/native_bridge -B /home/runiir/.local/share/trinity-client442-lab/build/native_bridge -DCMAKE_BUILD_TYPE=Release
cmake --build /home/runiir/.local/share/trinity-client442-lab/build/native_bridge -j 4
CLIENT442_CODEC=/home/runiir/.local/share/trinity-client442-lab/build/native_bridge/bridge_codec pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m pytest -q tools/client_compatibility/world/tests/test_native_bridge_codec.py
```

The supervisor also provides `world.control build` and `world.control start
--engine cpp`. `build` records source/schema and binary hashes. Starting a stale
binary is rejected. The default is still `--engine python` during migration.
`client442_bridge --root <lab> --repo <worktree> --self-check` verifies private DB
identity and public table loading without opening a listener. No credentials belong
on the command line. The target requires OpenSSL 3.5 for Ed25519ctx support.

Python supervises the native candidate and supplies its test oracle. `bridge_codec` has no Python runtime
dependency and never opens a live game socket. Future service validation must prove
both launcher/direct login, owned realm/instance continuation, world entry,
movement, bags/gear/professions, cast bars, mounts, archaeology loot, taxi and
cross-map portal transfer. Track latency/CPU under concurrent sessions separately
from semantic parity. Keep per-session queues and frame sizes bounded and exclude
authentication material from diagnostics.
