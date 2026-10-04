# Stock spellbook trials

Run the owned primary and scout independently with the code controller. Each
uses its private display, actor input lock and verified HDMI-1 presenter.
Observer61 automatically emits stock spellbook state and hovered tooltips;
the trial sends ordinary clicks and mouse movement, with no observer chat
commands. It does not call a decision model.

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_spellbook_navigation --actor primary --output <new-owned-evidence-directory>
```

Use `--actor scout` with a different output directory for the second client.
Both commands may run concurrently. They require the actors already in their
world, observer61, native login spell packets and a following General page.
The native worldserver and C++ bridge remain running.

The trial checks General page1→2→1, active/passive tooltips and the first
Arms/Fury/Protection pages. Public slots, types and names must match the
rendered controls. Learned spell IDs must occur in the actor's native
`SMSG_SEND_KNOWN_SPELLS` packet. Default racial/weapon/attack abilities are
included in that packet even when absent from saved `character_spell` rows.
SQL rows remain an independent preservation check. Cleanup restores saved
category/pages and closes the panels; money, inventory and saved spells
must remain unchanged.

UI43's initial primary/scout roots fail the incomplete SQL-only spell oracle.
All identified defaults occur in their native login packets. Both roots keep
their original failures and qualify nothing; all original resources/layout
restore. Fresh trials02 pass completely on the level85 and level1 human
warriors. Sixteen exact stock phase frames are visually reviewed, and their
execution intervals overlap by101.7 seconds without host activation.
These proofs await DVC44 remote/archive verification before adding six
operation checks: General/class tabs, next/previous page and spell/passive
tooltips.

Professions/pet tabs, spell drag/cast/learn/unlearn, rank resolution, other
classes and unsampled pages remain open. Unlearned guild perk trainer labels
and future spell levels are visible but are not qualified by this navigation
trial. Broader game coverage remains in the exhaustive checklist.

DVC44 is now remotely synchronized. Its archive review verifies11 selected JSON
receipts and167 attributed PNGs. The two complete navigation02 episodes and
their16 visually reviewed phase frames qualify exactly six new operations;
the checklist is270/916. Initial failed oracle episodes remain unqualified.

## Profession and action trials after OOM recovery

The October4 OOM ended the previous server lifetime. UI45 starts against the
recovered isolated native server and records both clients' reentry, process
identities and verified HDMI-1 presentation. Two clients remain the maximum.
Memory pressure is sampled during execution. Two inactive, reproducible pytest
fixture directories with dead owners were removed after checking process
references; the cleanup receipt records the exact paths. No active experiment
data was removed.

Profession trials01 checked the previous tab too soon and failed. The read-only
wait now requires the requested book type. Both profession trials02 pass the
complete native catalog, rendered name/rank/bar and restoration checks. The
trained primary shows all six professions at525; the untrained scout shows six
placeholders.

Action trials01 failed because unconditional Escape closed the book after slot
cleanup. Trials02 demonstrate that Escape also leaves a carried spell cursor
intact in this client. Cleanup now cancels an observed cursor with one ordinary
right-click and waits without replaying input. Scout03 passes the complete
drag/save/clear/cancel/restoration trial. Primary03 reached the Fury switch but
checked the old class tab too soon. The same read-only wait now requires the
requested class tab and page. Primary04 passes completely, including right-click
Battle Shout, native cast completion, public aura and ordinary aura cancellation.
Both complete trials restore saved action rows, book layout, inventory, money
and saved spells. Fourteen targeted wait/cleanup tests pass. The failed roots,
including scout observer63's reload observation timeout and subsequent read-only
verification, remain in the archive and qualify nothing.

DVC45 is synchronized. Its archive review verifies26 selected receipts and413
attributed PNGs; profession and action frames were also visually reviewed.
The qualification ledger adds the profession tab, spellbook drag/cast, action
bar spell drag/clear/save-backed persistence, and carried cursor pickup/cancel.
The checklist is278/916. These proofs cover the stated warrior fixtures and
one empty slot; pet tabs, learning/unlearning, rank transitions and other
classes/spells/bars remain open.
