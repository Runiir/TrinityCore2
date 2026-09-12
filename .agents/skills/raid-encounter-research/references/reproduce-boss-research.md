# Reproduce boss timing and damage research

Use this procedure when a native encounter appears wrong or lacks an implementation.
Keep the boss-specific values in its dossier/contract/ledger, not in this skill.

## Choose evidence that covers the failure

1. Run `pixi run python -m tools.raid_program.raid_workloop boss <raid> <boss> --mode 10N` (modes are case-sensitive: 10N, 10H, 25N, 25H). Read the paths it emits and the pinned client build/hotfix cutoff. A newer upload or a Classic-branded page does not establish build compatibility.
2. Start from retained WCL report/fight URLs. For missing late mechanics, open the reporting guild's report list/calendar and inspect a longer kill. Prefer the same mode and compatible date. A fast ranking kill may skip the very mechanic being investigated. A longer different-mode/era kill can supply bounded observations but cannot silently replace the tuning baseline.
3. Open the fight itself and verify boss, difficulty, raid size, date, duration and roster. Confirm that the required mechanic actually occurs. Stop collecting candidates once useful coverage is found; seek another only for a named missing claim or contradictory observation.

## Reproduce WCL access and extraction

Use an available WCL connector/API if authorized. Otherwise the public report UI or the user's already-authorized browser session works. Do not assume OAuth is necessary because an API request failed. Do not extract browser cookies or guess private API endpoints.

For an observed report/fight, useful report views are:

- `?fight=<id>&type=casts&view=events&hostility=1`: enemy casts;
- `?fight=<id>&type=auras&spells=debuffs&view=events&ability=<id>`: player debuff apply/remove;
- `?fight=<id>&type=auras&view=events&hostility=1&ability=<id>`: enemy buffs;
- `?fight=<id>&type=damage-taken&view=events&by=ability&options=4098`: incoming events with mitigation detail;
- `?fight=<id>&view=replay`: actor movement and encounter context.

Verify the selected UI filters after navigation. Wait for the loaded table; an initial empty page is not evidence of zero events. Read the event table and spell/actor links, not the entire summary DOM with every gear link. In supported browser tools, extract rendered row text plus linked spell IDs and report-local actor IDs. Preserve pagination or time filters and report how many rows were actually captured. A missing aura in one view does not prove the aura was absent; check buff/debuff direction and entity before classifying it unavailable.

Resolve same-named NPCs by their NPC and report-local actor IDs. In Damage Taken, the URL's `source` selects the recipient and `target` the attacker; verify the UI labels. Exclude encounter damage-sharing callbacks before measuring fresh attacks, then separate DoTs and pets. A player's first/last swing bounds observed activity, not exact targetability. Aura removal alone does not identify successful interaction, timeout, dispel or death. Join the surrounding damage/death events before prescribing a release callback change.

The rendered quick filter accepts expressions such as `ability.id != <observed-mirror-id>`. Enter it in `#quick-filter-pin`, submit, then verify the loaded table and pagination. Spell IDs and this encounter's mirror exclusion belong in its packet. An empty cast view can coexist with landed damage; record that capture limitation.

Normalize selected evidence into compact records: report/fight/date/mode, relative timestamp and its origin, event type, spell ID, source/target IDs and names, displayed value, mitigation fields, source URL and capture scope. Keep null for unavailable values. Preserve selected original row text alongside derived intervals so a worker can audit the transformation. Do not fabricate GUIDs from WCL local actor IDs or call selected rows a complete raw export.

## Resolve timing semantics before changing a constant

Locate the installed DBM/BigWigs boss module using `rg --files` in the actual addon directory. Retain package/interface version, module revision, file SHA-256 and, where possible, matching upstream commit. Follow each timer's `Start`/reset/cancel call back to its event and spell ID. Record first-use and repeat predictions separately, including author caveats.

Treat addon bars as expected cooldowns. Distinguish cast start, cast success, aura application, periodic trigger, first damage, emote and player interaction. Group periodic ticks separately from parent casts. Compare intervals with the same event anchor and phase. Record observed intervals and sample count; do not invent random ranges from a few samples or equate a single interval with a cooldown distribution.

Inspect native scheduling, cast-state checks, event consumption, failed submission, phase cancellation and target/vehicle lifecycle. Use the existing event queue for state-dependent leeway between incompatible cast starts. Define which lifecycle events must continue during casting. Instant spells, missiles and periodic effects may legitimately overlap. Do not impose universal spacing or copy a triggered-tick timer into a parent-cast schedule.

## Resolve damage through the complete spell chain

Use exact WCL spell IDs, not names or a guide's nearest link. Follow parent, trigger, periodic damage, difficulty variant and aura modifier IDs in the pinned client tables. Reuse `tools.raid_program.extract_442_client_spell_rows` with repeatable `--spell-id <id>` and `--output <path>` to retain explicit IDs, including trigger metadata that document-based discovery may miss. The tool is specifically pinned to 4.4.2; check its build before using it for another target.

Add `--follow-triggers` for a new chain extraction. It downloads each table once, follows forward trigger references including cycles, and reports missing name/effect records. This is metadata reachability; scripts, creature auras and visual wrappers can introduce IDs outside that graph. Inventory WCL damage IDs before the extraction and retain missing IDs as gaps. Reuse the pinned Difficulty table's ID/fallback mapping; normal/heroic names or legacy variant spell IDs are insufficient.

Check the loaded worldserver DataDir and hash its DBC files. An offline checkout subset is not automatically the runtime data. Read applicable DB overrides, SpellMgr corrections and native script/aura modifiers. Keep the repository observation separate from external evidence.

WCL health loss, absorbed damage and U (unmitigated estimate) are distinct. Gear alone cannot reconstruct active defensive cooldowns, resistance, absorbs or encounter modifiers. Never multiply a tank's displayed damage by a guessed armor factor. Use explicit mitigation observations or leave the base roll unresolved.

The comparison input uses `columns` plus `samples` (arrays in that column order), including `spell_id` and `wcl_unmitigated_estimate`, and `report`, `fight`, `mode`, `limitations`. Preserve original rows and source URL. Client roll endpoints are separate from WCL sample compatibility and from verified native outcomes.

`tools.raid_program.compare_encounter_spell_samples` compares selected U estimates to an explicit client effect/difficulty row. It supports simple positive integer direct-damage rolls only and rejects unsupported/missing scaling fields and empty observations. Zero out-of-range samples means sample compatibility, not recovered endpoints, complete distribution, or proof of server hotfix parity. Do not weaken its checks to force a match.

## Turn research into a bounded repair

Deliver the implementer one earliest causal mismatch with exact owned files, event/phase sequence, resolved values and source locations, forbidden unrelated changes, production-path fixture, required commands and observable live acceptance. For a missing boss, specify the native phase graph and registration/instance dependencies before class or bot tuning.

Route the code repair to `raid-encounter-implementation`. A fixture must exercise the relevant production scheduler/helper and demonstrate failure before repair, then success after it. Preserve reset, phase, target return and death/credit behavior. Follow required independent review before the coordinator's build and one completion-watchdog canary.

Keep encounter clear, requested mechanic repair and overall performance acceptance separate. Compare matched setup and phase coverage, tank ownership, hostile incoming damage, per-bot activity, DPS/HPS and survival. A clear or higher raid DPS does not resolve an unobserved cast outcome. Missing damage is not proof of a missing cast without adequate cast/absorb telemetry. Record the next precise evidence gap instead of repeating the same run.

Commit code/config and the compact claim packet. Use `raid-evidence-lifecycle` to DVC-publish generated source observations and closed experiments, verify a fresh remote reconstruction and remove exact redundant local payloads. Keep a reconstruction pointer and concise findings. Do not rewrite a previously published run when adding research.

Worked example: `docs/bot_raids/magmaw_fidelity_20260912.md` and its longer-kill addendum. Its spell IDs, timings and impale exception are Magmaw-specific, not defaults for other bosses.
