# Auction UI qualification, October 3

The isolated 60895 client opens its stock modern auction house through an existing
auctioneer and gossip selection. `ui18/auction_open_02` passes three ordinary
code-controlled choices. `auction_bids_01` also verifies the automatic initial
bid query against the native request/response, translated result, `BIDS_UPDATED`
event and public complete empty catalog. `auction_owned_02` passes four choices:
open, gossip selection, owned Auctions tab and close. Its stock "No items found"
display, native empty catalog, `OWNED_AUCTIONS_UPDATED` event and complete public
catalog agree. All native auctions, both characters' items and money, and the
staged character position are restored. Both windows remain on HDMI-1; the native
worldserver was not rebuilt or restarted.

These are empty-catalog qualifications. Populated rows, sorting, paging, posting,
bidding, buying, cancellation, commodity semantics, fees, delivery and negative
paths remain open. Opening a panel is not transaction coverage. The broader
891-operation inventory remains a plan, not coverage, and these code-controlled
trials do not evaluate learned autonomy.

## Protocol changes

The native 13-byte `MSG_AUCTION_HELLO` grants opening authority for the visible
auctioneer. The bridge translates it to `SMSG_AUCTION_HELLO_RESPONSE`. Native
authority and visible-NPC checks also guard modern bid and owned-catalog reads;
closing the interaction or logging out clears the grant. Valid captured sort
metadata is parsed, but native ordering is retained and ordering variants are
unqualified. Native requested-ID/current-bid overlap is deduplicated only when
the complete encoded rows agree. Conflicting duplicate rows fail validation.

The modern client uses `AuctionHouseFrame` and `C_AuctionHouse`. Observer v23
reads those public catalog APIs, completeness flags, recent catalog events and
the actual search field. It makes no gameplay calls. Quiet catalog observations
skip unnecessary bag-control traversal while retaining all passive item data.

`auction_browse_02` exposes the next missing adapter. Its ordinary Search button
emits a captured `CMSG_AUCTION_BROWSE_QUERY`, with the default 4032 quality mask,
zero class filters and price/name sorts. No native search request follows.
This failed verdict is retained. The original search text and complete native
auction/inventory/money/position baseline are restored.

Layouts are checked against the pinned [TrinityCore auction packets](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/AuctionHousePackets.cpp)
and [4.4.2 WowPacketParser auction parser](https://github.com/TrinityCore/WowPacketParser/blob/28fc3d194b22063ce8e94d2ed7235ca98ca51ef2/WowPacketParserModule.V4_4_0_54481/Parsers/AuctionHandler.cs).
Selected source files and hash/provenance receipts are included with the evidence.

## City transport interruption

`auction_owned_01` disconnected before the tab input because a native city update
contained a transport passenger. The captured packets describe vehicles 52358 and
52359, with one attached to the other. The C++ reader now preserves native unit
and game-object transport layouts, relative position, seat, times and vehicle
metadata. Public unit/player create packets carry supported transport data, and
native vehicle GUIDs map to modern vehicle identities and remain visible.

Captured-packet regressions verify complete parsing, modern transport/vehicle
fields, targetability and malformed-body rejection. The subsequent owned-tab
trial passes without a disconnect. That trial did not capture another matching
city vehicle create, so it qualifies the UI retry, not a repeated live vehicle
spawn. Player vehicle control and boat/elevator travel remain unqualified.
Native inventory/money/pose and temporary-teleport cleanup after the failed
trial were verified independently. Auction cleanup now records its native
baseline even when client observation fails.

## Tests and preserved failures

The catalog suite passes 598 regression tests and 35 selected ASan/UBSan checks.
The later transport suite passes 601 regression tests and 50 selected sanitizer
checks; a further four-test sanitizer run includes the added native visibility
and targetability case. These are protocol checks, not unique feature counts.

- The initial open failed before the hello translator existed.
- The first focused catalog sanitizer command named a nonexistent test file;
  collection failed and no tests ran. The corrected command passes.
- The first transport patch's optional-field check treated a missing value as
  an object, causing five failures and 25 passes. The corrected patch restores
  existing public-player and unit serialization.
- The next focused run had 29 passes and one incorrect fixture expectation:
  both captured objects are vehicles, including the passenger. The corrected
  fixture is included in the final successful suites.
- `auction_browse_01` started while the client was still disconnected and failed
  observation before any search input. The later connected search failure is
  the attributable missing-adapter trace.
- The first independent native restoration check compared JSON arrays to SQL
  tuples. The normalized comparison passes, with the original check retained.

## Reproduction and storage

Initialize a new evidence batch and run physical-input trials serially:

```bash
pixi run python -m tools.client_compatibility.checkpoint_interactions --initialize --directory ~/.local/share/trinity-client442-lab/evidence/<new-batch>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_auction --point 640 130 --query bids --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/auction_bids_01
```

Use `--query owned` or `--query browse` for the separate cases. The point refers
to the reviewed 1280×720 view of Auctioneer Fitch and must be rechecked after
camera changes. Empty-catalog trials require the native auction table to be
empty. Failures do not count as qualifications; inspect restoration before the
next trial. Deploy bridge changes through the owned bridge helper and reconnect
each reviewed client serially. Observer-only changes use the reload helper.

The closed UI18 batch is tracked by
`artifacts/client_harness/442_interactions_20261003_19.tar.gz.dvc`.
Commit source/configuration before checkpointing, verify the DVC remote and
archive hashes, then prune only that batch's raw frames and evict only its named
archive/cache object. Keep small receipts locally. The checkpoint records code
choices separately from historical model choices and makes no new Laya/Jev calls.
