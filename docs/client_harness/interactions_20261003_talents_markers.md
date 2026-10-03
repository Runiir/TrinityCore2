# Talent, glyph and NPC marker repairs, October 3

The private 60895 client now renders the warrior talent selection correctly and
shows nine properly cropped Prime, Major and Minor glyph sockets. Marshal McBride
shows the ordinary yellow available-quest marker on the level-one scout. These
are live checks on the separate `feature/442-compat` lab, using ordinary inputs
and verified HDMI-1 windows. They do not qualify talent allocation, glyph
application or every quest-marker category.

## Protocol repairs

The native player talent packet and modern `SMSG_UPDATE_TALENT_DATA` have different
count fields, rank widths and specialization metadata. `talents.cpp` translates
the native data without changing the player's specialization. Native talent-tab
IDs already match the installed client: Arms 746, Fury 815 and Protection 845.
The modern Learn Talent request also needs its 16-bit rank widened for the native
reader. Pet talents and preview allocation remain separate open contracts.

Glyph sockets were missing their owner update fields. Stock
`GlyphFrameGlyph_UpdateSlot` returns before `SetGlyphType` when the slot type is
absent, leaving the full glyph atlas visible. Full and sparse owner updates now
carry all nine slot IDs, all nine applied glyph IDs and the enabled mask. The
client's actual Cata glyph Lua/XML was extracted read-only from its local CASC
storage and compared with the pinned source. No glyph UI replacement is needed.

Native quest status numeric bits cannot be copied directly into the modern
64-bit status mask. Before the repair, native available status 256 rendered a
blue marker. The semantic adapter maps it to modern `0x400000`; the same scout
and giver then render yellow. Trivial, incomplete, completed, repeatable,
unavailable and tracked-query variants remain open. Low-level quest tracking
also affects which markers the stock UI displays.

Observer v33 keeps its normal observation small and exposes the full read-only
talent/glyph catalog through `/tcui talents`. The trial always returns to
`/tcui state`. It observes stock tabs, slot types, frame bounds and textures;
it does not allocate talents or modify frames.

## Live evidence and validation

The closed batch is `client_interactions_20261003_ui24`. The pure panel trial
`talent_glyph_panels_02` opens talents, selects the stock Talents and Glyphs tabs,
checks the three named catalogs and nine enabled sockets, and closes the panel.
Native specialization, talents, glyphs, inventory and money remain unchanged.
`marker_visual_review.json` binds the before/after scout screenshots and status
packets to their SHA-256 hashes. Only the ordinary available marker is qualified.

The final world regression passes 664 checks. The selected ASan/UBSan regression
passes 15 checks. Earlier failures remain in the batch: a mixed-width C++ `auto`
declaration, incomplete glyph module wiring, two incorrect codec executable
names, a test started before the new codec finished building, and one differential
reference missing the new glyph fields. Each has a corrected passing result.
Live retries also retain the scout lobby/reload failure, oversized observer
payload failure, stale questgiver points and a native talent-tree whitespace
guard failure. These are not discarded or counted as passes.

The native worldserver supervisor remains PID 3428101 with start ticks 15075252.
Only the independent bridge was rebuilt and restarted. The native binary hash is
`2882faddd8df9214e634643e821b35c56d464f0470b0fdaaeed1b5b7d3a2ab5a`.
New trials use the code controller under the current AGENTS.md. No new Laya/Jev
call or learned questing result is claimed.

To reproduce the read-only panel check after both actors are in world with
observer v33:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_talents --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/talent_glyph_panels_01
```

The runner requires the registered unallocated warrior fixture and verifies
restoration. Quest progress and reward trials continue separately; opening the
fixed panels does not close those checks.
