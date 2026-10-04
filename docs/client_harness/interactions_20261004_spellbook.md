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
