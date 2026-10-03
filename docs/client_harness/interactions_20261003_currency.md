# Stock currency controls

UI31 continues the open 916-operation interaction inventory on the isolated
`feature/442-compat` lab. New trials use code-controlled ordinary keyboard/mouse
inputs under the current AGENTS.md. Both actors use private displays, D3D11 and
verified HDMI-1 windows. Native worldserver PID/start-time must remain unchanged.

`currency_read_01` opens the stock tab, then rejects native/public name agreement.
Native Honor Points 392 appears as `Honor Deprecated 3` in installed build 60895.
Quantities agree, and native currency, inventory and money remain unchanged.
The failure remains evidence; opening does not qualify the rest of the panel.

A strictly local CASC read pins `CurrencyTypes.db2`, layout `A0DA38E0`, SHA-256
`5d7f5531f048d1d2e9ada7f5b944d29175993f9506d764f4fbaee1e4c1fad61e`.
Its 52 rows contain active Honor Points 1901 and deprecated 392. Both retain
the 100:1 display scalar and 400000 raw cap. The [build-specific schema](https://github.com/wowdev/WoWDBDefs/blob/master/definitions/CurrencyTypes.dbd)
is retained with SHA-256 and a bounded decoded-table receipt. An initial strict
exploratory parse rejected an empty string offset; its retry explicitly handles
zero as empty while checking every nonzero string address and all row boundaries.

The bridge maps native Honor 392 to modern 1901 in startup, incremental amounts,
quest-offer rewards and trade updates. Native balances and IDs stay authoritative.
Static quest-cache reward/required-currency references use the same mapping, with
a regression that preserves quantity fields. A live currency-quest fixture remains open.

The pinned [modern request parser](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/MiscPackets.cpp#L108)
reads uint32 ID followed by uint8 flags. That reference is newer than the installed
60895 client. Both first live flag trials disconnected: captured backpack body
`6d07000004000000` and unused body `6d07000008000000` prove that this installed
client sends uint32 ID followed by uint32 flags. Native saved flags remained zero;
no matching native request was forwarded. The initial five-byte regression tests
mirrored the wrong reference and did not establish installed-client compatibility.
The corrected adapter accepts the installed eight-byte contract, reverses the two
uint32 fields and maps Honor back to 392. It rejects truncation, extra bytes,
deprecated Honor requests, zero/out-of-range IDs and flags outside the native
four-bit representation. Backpack and unused bits are 4 and 8 in the pinned
[currency flags](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Miscellaneous/SharedDefines.h#L6679).
Public currency packet bodies are retained by the bounded capture allowlist;
authentication bodies remain excluded.

The initial, failing optimized and sanitizer builds share source digest
`fbbc3071468603000a6af6dc3a1df74f6174a0972a9a21f9977d523739c3e837`.
The optimized binary SHA-256 is
`98ca8c9b47be6e15ae18c19632fac59cf817770594c7131b244210df096f91db`.
772 world/auth regression checks and 25 focused ASan/UBSan checks passed before
the live request-width failure. Those results remain historical evidence and do
not validate the corrected implementation. Captured-body regressions now cover
both failing requests and the live harness's independent journal decoder.
Build source revision is `52473380f23c68a1cc719b913bfaf1a50c6efeae`;
later ordinary-input orchestration commits do not relabel that runtime identity.

Run the committed read-only observer deployment, then the ordinary controls:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_observer_deploy --output <new-owned-directory> --version 39
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_currency --output <new-owned-directory>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_currency_flags --output <new-owned-directory> --kind backpack --persist
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_currency_flags --output <new-owned-directory> --kind unused
```

Only `currency_bridge_deployment_01` replaces the bridge. Observer v39 uses
ordinary reload and public API reads without gameplay mutations. Currency
oracles compare complete saved rows and original inventory/money. Stock inputs
must restore changed flags, headers and the visible catalog; successful checkbox
rendering alone is insufficient. Earning/spending, nonzero caps, PvP, other
currencies and full-session persistence remain separate requirements. Closed
results and DVC-qualified scopes will be added after their live trials.
