# Reproduce boss timing and damage research

Use this procedure when a native encounter appears wrong or lacks an implementation.
Keep the boss-specific values in its dossier/contract/ledger, not in this skill.

## Separate execution from reference data

Read both `execution_target` and `fidelity_target` in the acceptance policy.
This project runs a 4.3.4 build-15595 client/server with resolved 4.4.2 tuning.
The reference build is not a requirement to upgrade the connecting client.
Identify the running executable's directory and its build log before selecting
addons or data. Separate installations can contain different DBM releases.

Use the execution client's combat log to corroborate delivered damage, casts,
auras and deaths. Its local spell tables and tooltips describe execution-era
data; they do not independently establish the intended 4.4.2 values. Retain the
reference spell/difficulty mapping and native overrides/corrections separately.
Do not copy newer DB2 files into legacy DBC directories or alter tooltips to
make a comparison pass.

Prefer existing client combat logging before adding another logger. For the
installed legacy client, `LoggingCombat(1)` starts capture and
`LoggingCombat(0)` stops it through `/run`. Check the resulting
`Logs/WoWCombatLog.txt`; a command or installed addon alone does not prove
capture. Bind the file to the native attempt using common GUID/spell events
and an explicit timestamp offset, checking drift across the pull. Preserve
missing fields and observer coverage limits. A spectator cannot reveal every
bot's rejected candidates, intended target, LOS decision or pre-defense roll;
join native telemetry for those questions. Publish only the bounded attempt
slice with identity and capture coverage, verify DVC remote content, then
remove exact unneeded copies. Never truncate an active log.

## Choose evidence that covers the failure

1. Run `pixi run python -m tools.raid_program.raid_workloop boss <raid> <boss> --mode 10N` (modes are case-sensitive: 10N, 10H, 25N, 25H). Read the paths it emits and the pinned client build/hotfix cutoff. A newer upload or a Classic-branded page does not establish build compatibility.
2. Start from retained WCL report/fight URLs. For missing late mechanics, open the reporting guild's report list/calendar and inspect a longer kill. Prefer the same mode and compatible date. A fast ranking kill may skip the very mechanic being investigated. A longer different-mode/era kill can supply bounded observations but cannot silently replace the tuning baseline.
3. Open the fight itself and verify boss, difficulty, raid size, date, duration and roster. Confirm that the required mechanic actually occurs. Stop collecting candidates once useful coverage is found; seek another only for a named missing claim or contradictory observation.

If the retained guild lacks a mode or era, use the raid's WCL rankings with the
visible boss, difficulty, size and phase filters, then open one report matching
the needed coverage. Read ranking rows with rendered `innerText`; `textContent`
can include embedded scripts and large gear payloads. A ranking is a discovery
index, not a matched DPS baseline. Verify report date and mode after opening it.

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

For a historical month, the guild calendar exposes `?date=<epoch milliseconds>`
after month navigation. Use that observed parameter to jump to the desired month
and verify its heading, rather than clicking through years. Filter by the raid
zone before opening reports; a long report is not necessarily a long boss kill.

## Inspect retained incoming damage before requesting another pull

Rebuild the existing bot timeline and read `summary.incoming_damage`. The
primary view now includes `damage_taken`, zero-health callbacks and native raw
values. Previously omitted display rows are a consumer defect, not capture loss.
Trace each numeric field back to its producer: legacy melee raw is after
attacker/defender modifiers but before armor and outcome adjustments, whereas
WCL U can exclude those defensive reductions. Legacy absorbed_amount is a
hardcoded placeholder. Do not call raw>0/health=0 a full absorb, infer swing
attempt counts from surviving callbacks, or fit a multiplier from unmatched
calculation stages. Preserve sequence/epoch/attempt binding when selecting rows.
Only request new instrumentation for specific stages or outcomes absent in the
retained records; preserve the original capture and publish replay separately.

## Resolve timing semantics before changing a constant

Locate the installed DBM/BigWigs boss module using `rg --files` in the actual addon directory. Retain package/interface version, module revision, file SHA-256 and, where possible, matching upstream commit. Follow each timer's `Start`/reset/cancel call back to its event and spell ID. Record first-use and repeat predictions separately, including author caveats.

Treat addon bars as expected cooldowns. Distinguish cast start, cast success, aura application, periodic trigger, first damage, emote and player interaction. Group periodic ticks separately from parent casts. Compare intervals with the same event anchor and phase. Record observed intervals and sample count; do not invent random ranges from a few samples or equate a single interval with a cooldown distribution.

Inspect native scheduling, cast-state checks, event consumption, failed submission, phase cancellation and target/vehicle lifecycle. Use the existing event queue for state-dependent leeway between incompatible cast starts. Define which lifecycle events must continue during casting. Instant spells, missiles and periodic effects may legitimately overlap. Do not impose universal spacing or copy a triggered-tick timer into a parent-cast schedule.

## Resolve damage through the complete spell chain

Use exact WCL spell IDs, not names or a guide's nearest link. Follow parent, trigger, periodic damage, difficulty variant and aura modifier IDs in the pinned client tables. Reuse `tools.raid_program.extract_442_client_spell_rows` with repeatable `--spell-id <id>` and `--output <path>` to retain explicit IDs, including trigger metadata that document-based discovery may miss. The tool is specifically pinned to 4.4.2; check its build before using it for another target.

Add `--follow-triggers` for a new chain extraction. It downloads each table once, follows forward trigger references including cycles, and reports missing name/effect records. This is metadata reachability; scripts, creature auras and visual wrappers can introduce IDs outside that graph. Inventory WCL damage IDs before the extraction and retain missing IDs as gaps. Reuse the pinned Difficulty table's ID/fallback mapping; normal/heroic names or legacy variant spell IDs are insufficient.

Check the loaded worldserver DataDir and hash its DBC files. An offline checkout subset is not automatically the runtime data. Read applicable DB overrides, SpellMgr corrections and native script/aura modifiers. Keep the repository observation separate from external evidence.

Search split `SpellMgrCorrections*` files too. Check `spell_dbc`,
`spelleffect_dbc` and `spelldifficulty_dbc` before declaring native values equal
to client rows. Missing client IDs can be server-defined helper spells. For
periodic summon counts, inspect the extra-initial-period flag as well as duration
and period; distinguish uninterrupted tick arithmetic from observed summons.

Audit creature melee and health separately from spell damage. Read the active
`creature_template` variants, `creature_classlevelstats`, applicable
`gt_npc_total_hp_exp*` / `gt_npc_damage_by_class_exp*` SQL tables and configured
rates. Follow native float/rounding and attack-speed/variance formulas. A flat
spell comparison says nothing about boss melee pressure or tank Vengeance.
Current DB rows do not establish what a historical run loaded.

For health, prefer explicit max HP. If only WCL's rendered resource bars are
available, retain consecutive amounts and full-precision health percentages.
Derive max HP from damage divided by lost-health fraction and corroborate across
several consecutive events on the same NPC instance. Exclude overkill, healing,
missing intervals and max-HP changes. Label the result derived, not a raw max-HP
observation; rounded `26.8m` display text is insufficient.

Run the retained observations through:

```bash
pixi run python -m tools.raid_program.derive_encounter_health <captures.json> --output <derived.json>
```

The input is a list of attributed records with `columns` and `observations`:
`displayed_relative_time`, `displayed_damage_amount`,
`health_bar_css_right_percent`. Declare `consecutive_no_healing_or_overkill`
only after checking capture scope; `initial_full_health` is optional. The tool
requires three corroborating intervals and rejects inconsistent estimates. It
does not validate historical patch compatibility or discover omitted events.

WCL health loss, absorbed damage and U (unmitigated estimate) are distinct. Gear alone cannot reconstruct active defensive cooldowns, resistance, absorbs or encounter modifiers. Never multiply a tank's displayed damage by a guessed armor factor. Use explicit mitigation observations or leave the base roll unresolved.

The comparison input uses `columns` plus `samples` (arrays in that column order), including `spell_id` and `wcl_unmitigated_estimate`, and `report`, `fight`, `mode`, `limitations`. Preserve original rows and source URL. Client roll endpoints are separate from WCL sample compatibility and from verified native outcomes.

`tools.raid_program.compare_encounter_spell_samples` compares selected U estimates to an explicit client effect/difficulty row. It supports simple positive integer direct-damage rolls only and rejects unsupported/missing scaling fields and empty observations. Zero out-of-range samples means sample compatibility, not recovered endpoints, complete distribution, or proof of server hotfix parity. Do not weaken its checks to force a match.

## Turn research into a bounded repair

Deliver the implementer one earliest causal mismatch with exact owned files, event/phase sequence, resolved values and source locations, forbidden unrelated changes, production-path fixture, required commands and observable live acceptance. For a missing boss, specify the native phase graph and registration/instance dependencies before class or bot tuning.

Route the code repair to `raid-encounter-implementation`. A fixture must exercise the relevant production scheduler/helper and demonstrate failure before repair, then success after it. Preserve reset, phase, target return and death/credit behavior. Follow required independent review before the coordinator's build and one completion-watchdog canary.

Keep encounter clear, requested mechanic repair and overall performance acceptance separate. Compare matched setup and phase coverage, tank ownership, hostile incoming damage, per-bot activity, DPS/HPS and survival. A clear or higher raid DPS does not resolve an unobserved cast outcome. Missing damage is not proof of a missing cast without adequate cast/absorb telemetry. Record the next precise evidence gap instead of repeating the same run.

The research handoff defines expected observations; the live worker supplies
them. Do not leave research open solely because its native acceptance test has
not run. Conversely, do not mark an unresolved external value resolved because
a fixture copied the current implementation. Scope loot/achievement parity
separately from combat training, while retaining reset, death, instance credit
and save/load as run-attribution requirements.

WoWSims supplies matched class mechanics and cadence references, not an expected
raid-wide Magmaw DPS number. Bind gear, effective stats, buffs, targets and time;
compare phase-specific fresh actions separately from pet/DoT tails. Tank and
healer validation also needs incoming pressure, defenses, threat, mana and
preventable deaths. Before admitting data for an actual-client policy, identify
which facts the client can observe and which are server-only teacher labels;
validate client action submission, latency and native outcomes separately.

Commit code/config and the compact claim packet. Use `raid-evidence-lifecycle` to DVC-publish generated source observations and closed experiments, verify a fresh remote reconstruction and remove exact redundant local payloads. Keep a reconstruction pointer and concise findings. Do not rewrite a previously published run when adding research.

Worked example: `docs/bot_raids/magmaw_fidelity_20260912.md` and its longer-kill addendum. Its spell IDs, timings and impale exception are Magmaw-specific, not defaults for other bosses.
