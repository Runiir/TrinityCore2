# Stock paging, camera zoom and latency

UI48 qualifies three main-bar paging operations and two camera/latency operations
on the two idle human warriors. The checklist is 294/916 scoped fixture variants.
Both presenters remain verified on HDMI-1. Native sessions, worldserver and
bridge processes remain unchanged; no native rebuild was needed.

Paging uses the installed NEXTACTIONPAGE, PREVIOUSACTIONPAGE and ACTIONPAGE1/2
bindings. Public page and effective stance-page getters identify the requested
layout. Every one of the 12 main-bar slots matches native saved action rows for
the active spec. Returning to page1 restores all assignments and the original
layout. The primary mount button's companion kind is accepted only when its
exact ID is learned natively and SpellEffect identifies a mounted aura (78).
The native32235 contract is effect21975, effect kind6, aura78. Other companion
types are not accepted by this mapping.

Camera zoom sends one installed wheel-up event over clear world space, then its
inverse. The primary distance changes 8.1871118546 -> 7.1871118546 -> 8.1871118546;
the scout changes 5.5500001907 -> 4.5500001907 -> 5.5500001907. Character position
does not change. Ordinary main-menu hover produces the stock tooltip's home0ms
and world0ms lines. A read-only post-call hook records GetNetStats and the exact
stock formatted line. No setter or gameplay API is invoked by observation.
Both complete trials preserve native inventory, money and saved spells.

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_actionbar_pages --actor primary --output <new-owned-evidence-directory>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_camera_latency --actor scout --output <new-owned-evidence-directory>
```

Failed attempts remain in the archive:

- Both page01 preflights query an incorrect previous-page binding name and fail
  before gameplay steps. The installed catalog and local60895 Bindings_Cata.xml
  establish PREVIOUSACTIONPAGE. Observer69 corrects it.
- Primary page02 correctly restores the bar but fails an overly narrow oracle
  that expects only spell/item/macro kinds. Its mount is a companion action.
  Native DBC and learned-spell checks justify the specific mapping used by
  primary page03. Scout page02 passes without that companion variant.
- Scout camera/latency01 passes both zoom steps but fails its latency oracle.
  The tooltip helper returned only two values, dropping home/world latency.
  Observer70 preserves all four returns. Primary01 and scout02 then pass fully.
- Primary observer69/70 and scout observer70 reload reads time out. Separate
  read-only episodes establish the installed versions, unchanged sessions and
  baseline, with no repeated reload. Timeout episodes stay failed. Loading
  diagnostics find no matching native loading-notification rows in the selected
  packet journal and provide no acceptance evidence.

Python compilation and Lua parsing pass. A Lua runtime regression test verifies
that the actual tooltip observer retains distinct home/world values and leaves
them absent when GetNetStats fails, rather than inventing zeroes. It passes1/1.

DVC48 is synchronized. Archive review verifies28 JSON receipts and104 attributed
images. Ten exact paging/camera/tooltip images receive visual review. Raw frames
and this archive's exact local cache object may be evicted after remote and digest
verification. Available RAM stays16-17GiB during these trials, with zero pressure
stall averages. Only the two existing clients are used.

Other pages and bar types, camera presets/reset, remote-network latency,
performance thresholds and disconnect behavior remain open.
