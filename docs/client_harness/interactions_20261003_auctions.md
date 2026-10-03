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

`ui19/auction_browse_02` also passes five ordinary choices, including a unique
absent-name search, search-text restoration and the visible stock close button.
Native search request/result, modern browse response, public complete empty
catalog and browse-results event agree. The reviewed UI shows "No items found".
Both inventory/money baselines and the staged position are restored.

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

`ui18/auction_browse_02` exposed the missing browse adapter. Its ordinary Search button
emits a captured `CMSG_AUCTION_BROWSE_QUERY`, with the default 4032 quality mask,
zero class filters and price/name sorts. No native search request follows.
This failed verdict is retained. The original search text and complete native
auction/inventory/money/position baseline are restored. The UI19 C++ adapter now
collects every native search page before applying supported modern class, quality
and required-level filters, grouping and sorting. Native DB2/hotfix metadata is
loaded once at bridge startup. Partial commodity transactions, fractional native
unit prices, random-suffix keys, collection filters and concurrent catalog changes
remain open. A 4,096-native-row bound prevents unbounded scans.

Observer v24 adds passive stock sale-item, quantity, price, duration and item-search
observations. `ui19/auction_sell_select_01` qualifies selecting the existing unbound
pants through their ordinary bag button, with no native mutation. The stock UI
then remains stuck on "Searching..." because its item-ID search was unmapped.
The next adapter adds native-backed item-ID/bucket-key reads and base item keys to
plain owned/bid rows. `auction_sell_post_probe_01` reaches native search and returns
a modern result but fails the completeness oracle. Its response envelope uses
base level one where the pinned item-ID handler uses wildcard level zero. No
posting input is attempted, and all native state is restored. The source fix now
echoes a bucket request's key or uses itemID/level zero for an item-ID request.

UI20's `auction_sell_post_probe_02` still fails that oracle, but its screenshot
shows "No items found", its public `ITEM_SEARCH_RESULTS_UPDATED` event arrives,
and throttling is ready. Observer v24 queried completeness with the bag item's
level-one key instead of the stock Sell list's wildcard key. This was an observer
failure, not evidence that the client ignored the level-zero response. Observer
v25 reads the stock frame's `listDisplayedItemKey` without changing it, retains
the original item key separately, and requires the search-results event.

Auction replies also now use the realm connection specified by the pinned
[opcode connection table](https://github.com/TrinityCore/TrinityCore/blob/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Protocol/Opcodes.cpp).
This corrects a separate routing mismatch; it was not established as the cause
of the earlier completeness failure. Both clients reconnect with observer v25
and exact money, inventory, equipment and group baselines retained. The native
worldserver remains unchanged.

`ui20/auction_sell_post_probe_03` now passes the complete empty Sell catalog:
native request/result, realm reply, wildcard completeness flag, zero rows, ready
throttling and public results event agree. The ordinary price field accepts one
gold and enables Create Auction. Clicking it captures a 38-byte modern sale
request with minimum bid zero, buyout 10,000 copper, 1,440-minute duration and
one owned item. No native sale request follows, so posting remains a captured
missing adapter. The overall probe retains its failed verdict. Native auctions,
both inventories and balances, staged pose and temporary fixture state are fully
restored. The empty catalog and price entry are qualified separately from posting.

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
The browse suite passes 617 full checks and 45 selected sanitizer checks. The
subsequent item-search suite passes 632 full checks and 56 selected sanitizer
checks before the live response-key correction. UI20's corrected-key full suite
passes 635 checks and 59 selected ASan/UBSan checks. The realm-routing full suite
also passes 635 checks. These offline suites do not establish live catalog or
transaction coverage; the physical trials remain separate evidence.

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
- UI19's first browse retry passes search but incorrectly assumes one Escape
  closes the panel after restoring a focused search field. The corrected visible
  close-button retry passes; the original verdict is retained and classified as
  a runner failure.
- The first two focused item-search selections each have six browse failures and
  30 passes because the new query-kind read required a string on older browse
  state. Explicit browse-kind initialization fixes this. The corrected focused
  run passes 37 checks, followed by the 632-check full suite. These failures are
  retained separately from the later live wildcard response-key failure.
- UI20's second posting probe fails before any price or posting input. Its
  completion assertion uses the wrong public search key. The original receipt
  and a visual-review correction remain preserved; observer v25 fixes the read.

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
The closed UI19 batch uses
`artifacts/client_harness/442_interactions_20261003_20.tar.gz.dvc`.
The closed UI20 batch uses
`artifacts/client_harness/442_interactions_20261003_21.tar.gz.dvc`.
The original UI18/UI19 tracking counter compared the persisted controller name
to the short name `code` and therefore reported zero code choices. Their immutable
episode receipts each confirm 20 code inputs and zero model inputs. The correction
is tracked separately in
`artifacts/client_harness/442_interaction_tracking_corrections_20261003_01.json.dvc`;
future checkpoints use the persisted controller names and distinguish a saved
choice from confirmed input completion.
Commit source/configuration before checkpointing, verify the DVC remote and
archive hashes, then prune only that batch's raw frames and evict only its named
archive/cache object. Keep small receipts locally. The checkpoint records code
choices separately from historical model choices and makes no new Laya/Jev calls.
