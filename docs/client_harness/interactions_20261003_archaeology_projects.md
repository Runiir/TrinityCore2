# Stock archaeology project solving

UI32 uses the isolated `feature/442-compat` lab and code-controlled ordinary
keyboard/mouse inputs under the current AGENTS.md. Both clients share one native
worldserver and the C++ protocol bridge. Their private displays and owned windows
remain on HDMI-1. Native worldserver PID 3428101, start ticks 15075252, stays unchanged.

The first read-only trial opens professions with K, opens Archaeology and selects
Draenei through its stock race button. Plated Elekk Goad, native project 260,
spell 90987, 138 fragments and a 45-fragment cost agree with the rendered page.
The observer reads public APIs and stock frame properties; selection and solving
use physical inputs. Native project, branch, cost and crafted-item contracts come
from the pinned native DBC files.

`archaeology_project_solve_01` fails before native submission. Its captured client
cast has one currency weight, type 1, ID 398, quantity 45. The old bridge rejects
every weight tail. Native state remains unchanged. The corrected adapter preserves
the fragment weight and adds native HAS_WEIGHT flag 8. It also accepts one
optional native keystone weight while retaining native project, inventory and
resource validation. Moving or targeted weighted casts remain rejected and
unqualified. The actual captured request, truncation and malformed weights have
regression coverage.

`archaeology_project_solve_02` spends exactly 45 fragments and creates item 64458,
but fails its public-history oracle. The earned item and completion remain on the
character. A separate, SHA-bound inspection verifies that unchanged earned state
and the visible backpack item. The stock Completed tab is empty; both API records
report zero completion counts. This is a client compatibility failure.

The native completion notification always reports count 1. The bridge requests
canonical native history to preserve the accumulated count and first completion
time, then sends owned ActivePlayerData fields. The newer pinned Trinity writer
joins the mandatory PetStable presence bit and nested history mask. The
[pinned 4.4.2 reader](https://github.com/TrinityCore/WowPacketParser/blob/28fc3d194b22063ce8e94d2ed7235ca98ca51ef2/WowPacketParserModule.V4_4_0_54481/Parsers/UpdateFieldsHandler442.cs#L2468)
aligns on entering ResearchHistory. Applying that independent boundary to the
captured outgoing packet reads mask zero. Four corrected tests fail against the
old binary for empty, one, 33 and 144 completed projects. The initial 808 passing
tests mirrored the wrong boundary; their historical receipt does not establish
compatibility. The bridge now flushes the presence byte before the nested mask.

The corrected build passes 808 full world/auth regression checks and 39 focused
ASan/UBSan checks. Its source revision is `461e7e7f0b253d91d5ef62390f8fafe3b0630711`,
source digest `907676d63ad4b63b6ec6472784bb4b6d766ef6231c6740b1907eedcb9e723f31`,
optimized SHA-256 `9e4a9c1d09355600e98609d6e1de234d7b18d0e873d2115103f1001667df8f0a`
and sanitizer SHA-256 `68322a50e45c9f1d5361dd42694f189e8c8a04935c0303c8f94a0212b0d1d5df`.
Only the independent bridge is rebuilt and restarted. Both observer-v41 clients
reenter with intact public baselines. A second source-bound inspection shows
Plated Elekk Goad in the stock Completed tab with the exact native timestamp and
count, while preserving the earned item and all resources.

The fresh `archaeology_project_solve_03` passes in one uninterrupted trial. It
solves Strange Silver Paperweight, project 243 and spell 90861, using 46 earned
fragments. Draenei quantity drops from 93 to 47 and exactly one item 64443 appears
in the backpack. Existing items, all other currency rows and money are unchanged.
Both completed artifacts render with exact native counts and first timestamps.
Ordinary Escape closes the archaeology window. After `/reload`, the same native
inventory, fragments, current project and complete rendered history are retained.
Screenshots of the crafted item and both history displays are reviewed.

Use fresh owned output directories and the already-running lab:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_observer_deploy --output <new-owned-directory> --version 42
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_archaeology_projects --output <new-owned-directory>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_archaeology_projects --output <new-owned-directory> --solve --persist
```

The solve runner requires an existing affordable Draenei project and earned
fragments. It retains legitimate completions and crafted items, and never grants
or refunds fragments. The separate `interaction_archaeology_history` inspector
requires a failed earned-solve receipt whose complete native post-state still
matches; `--require-history` checks both API and rendered history. It does not
replay the original Solve click. All original failed episodes and four failing
pre-fix regression cases remain in the evidence batch.

Completion repeats, rare artifacts, other races, fragment caps, Survey
cast-bar verification, continent maps and full-session persistence remain separate
requirements. These code-controlled UI checks do not qualify learned autonomy or
whole-game compatibility.

The closed batch is remote-verified in
[442_interactions_20261003_33.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_33.tar.gz.dvc),
archive SHA-256 `63a5dde90a6e370b6fb421b0466e1b63398ba4da1e2a1172a78b53a9722bc3a6`.
Eight JSON receipts/reviews and 104 attributed frame hashes were verified by
streaming the archive. Three scoped records qualify seven new operations,
bringing the checklist to 239/916. Remaining variants stay open.

UI33 passes a fresh, ordinary-input keystone trial with observer v42. Adding an
existing Draenei Tome shows its socket icon and exactly 12 extra fragments;
removing it restores the unadjusted display. Neither toggle changes native state.
Adding it again and clicking Solve creates Scepter of the Nathrezim, native
project 245, spell 90864 and item 64444. The captured native request contains
weights `(currency 398, 34)` and `(keystone 64394, 1)`. Earned fragments decrease
from 47 to 13, the existing Tome stack decreases from five to four, and one new
artifact appears in the backpack. Every other item, currency row and money stays
unchanged. The next project is Anklet with Golden Bells at 13/45 fragments.

The original Solve frame captures public spell 90864, matching stock bar text and
a visible three-second cast bar. This qualifies a stationary Solve cast, while
Survey remains open. The source episode ran revision
`899bd592f230a0d61e8bd1f490321e9ab8da80ee`; its original `case.after.player_cast`
provides this proof, rather than the later helper added at `2a3ac7e5f7`.
All three earned artifacts appear in the stock Completed tab. Physical hovering
over the disabled common-artifact button shows the exact title, first completion
date and completion count one. The observer uses public reads and the stock
button's existing mouse-motion scripts.

Eleven private-input/cohort guards pass. An earlier command selected a nonexistent
test file and collected no tests; that selection error is retained in the batch.
The native worldserver and bridge lifetimes remain unchanged throughout UI33.
The weighted solve, frames and source-bound review are checkpointed separately in
[442_interactions_20261003_34.tar.gz.dvc](../../artifacts/client_harness/442_interactions_20261003_34.tar.gz.dvc),
archive SHA-256 `f5804bb941fe4505930c6416230841cabd4f137d0b94b3327d02a5a87f60d743`.
Five JSON receipts/reviews and 73 attributed PNG hashes pass the archive review.
Three new scoped operations bring the checklist to 242/916; eight qualification
and inventory guards pass. One-keystone, common Draenei Solve and
its completed tooltip are the tested variants. Additional socket counts, rare
artifacts, repeats, other races and Survey casts remain pending.
