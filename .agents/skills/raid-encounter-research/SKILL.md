---
name: raid-encounter-research
description: Research and review one Cataclysm raid encounter against online sources, pinned client/addon/log evidence, database state, and the repository's current scripts, then update its human dossier, mechanic contract, and quantitative ledger. Use for boss strategy, tactics, phase graphs, timers, spell IDs, difficulty/raid-size deltas, assignments, source conflicts, script-readiness review, unresolved encounter values, Warcraft Logs (WCL) access and matched WCL references. Do not implement C++/SQL gameplay changes or run live shards.
---

# Raid Encounter Research

Own one boss research packet. Do not own its implementation.

## Bind the boss packet

Run:

```bash
pixi run python -m tools.raid_program.raid_workloop boss <raid> <boss> --mode <mode>
```

Start with the emitted ledger's compact resume view:

```bash
pixi run python -m tools.raid_program.encounter_research_view <ledger-path>
```

Choose the next unresolved claim, then use `--key <claim-key>` for its values
and sources. Read the relevant dossier/contract sections, native functions and
DB rows. On the first audit, inventory the full boss/instance implementation
and read `experiments/configs/cata_raid_acceptance_policy_v1.json`. On a resume,
check source revisions before reusing retained observations. Do not reread all
evidence or rebuild a reference already bound to unchanged inputs.

Browse every referenced online page that supports a changed claim. Preserve
URL, title, publisher/author when available, publication/update date, retrieval
date, exact mode, and the bounded claim it supports. Do not cite a search result
or another dossier as the source.

For suspected timer, damage or phase bugs, follow
[the reproducible boss research procedure](references/reproduce-boss-research.md).
It covers longer WCL kill selection, browser extraction, addon event anchors,
client/native spell chains and the bounded implementation handoff.

## WCL access

Warcraft Logs (WCL) works through only one route: GPT-6.1 Sol driving the
user's own Chrome. Use it for every WCL read, including reports, fights,
rankings and event tables.

1. Put the whole task in one prompt and run it from a shell. Run long tasks
   in the background:

   ```bash
   codex exec -m gpt-6.1-sol --skip-git-repo-check "Use the Chrome plugin to connect to the user's already-running Google Chrome (profile Runiir). Open one new tab for this task and close it when done; touch no other tab. <task>" < /dev/null
   ```

   Keep `< /dev/null`. Add `-o ~/.cache/<boss>_wcl/<task>.md` to keep Sol's
   final answer. The `sol-reviewer` subagent, given the same instruction, is
   the alternative.
2. The plugin sees only tabs it opened itself, so never point it at a tab the
   user opened. Each agent opens one tab, reuses it for all of its reads and
   closes only that tab. Parallel agents are fine.
3. If a WCL human-verification or Cloudflare check appears, pass it and
   continue. The user decided this on 2026-09-27: "If a check appears they can
   click it".
4. Keep raw captures under `~/.cache/<boss>_wcl/`, not `/tmp`. Publish them
   through DVC and then delete the local copy (`raid-evidence-lifecycle`).
5. In the handoff, record the route, the UTC time and whether a check
   appeared.

These routes fail, so spend no attempts on them:

- headless Playwright;
- `curl` or any other plain HTTP client (Cloudflare blocks them);
- `CUA_REPL_ENABLED_SURFACES=browser codex exec ...`, which fails with
  "Browser is not available: iab";
- a Chrome started with a scratch profile, which loops on the check.

`blocked_external` is not an acceptable WCL result until you have tried the
route above in this round and it failed. When it fails, quote the exact
command and error in the handoff.

## Matched WCL references before WoWSims fallbacks

A gated spec with no matched WCL kill is judged against 0.90 × verified
WoWSims (`fallback_reference`). In round 2 that fallback overstated the target
by 20–50%. On Atramedes, five more matched kills showed that the round-1
"failures" of the Balance druid and the Assassination rogue came from the
fallback, not from the bots.

1. Before you accept a fallback for a gated spec, search the raid's WCL
   rankings with the boss, difficulty and size filters for kills that include
   that spec.
2. Open each candidate report. Verify boss, mode, size, date and patch,
   duration, phase coverage and roster before you add it (see the reproduce
   reference).
   - Match the item level. The user decided on 2026-09-29 to keep the roster's
     gear (average item level about 409, read from
     `dataset/validation_gear_profiles/profiles.json` `average_item_level`) and
     to pick reference kills near it: raid item level about 400–415.
   - Record each reference's `item_level` in the WCL manifest.
   - Don't mix low-gear kills into a median. In rounds 1–2 the references
     ranged from 354 to 401, so targets weren't comparable across bosses.
   - If no kill near the roster's item level has a given spec, say so, and
     keep the fallback for that spec.
   - Gear match comes before parse. The goal is optimal DPS on the current
     gear, not top 1% (user, 2026-09-30). Take competent, representative
     players at that gear, and leave out outliers: deaths that cut an actor's
     time short, very low activity, or extreme top parses.
3. Aim for three matched kills per gated spec, and record the kill count per
   spec in the raid target.
4. Keep the fallback only when no matched kill has that spec, and say so in
   the handoff.

Healers and `dps_gate_exempt_specs` (the Feral tank) need no reference.

## Per-mode research gate

A raid program runs one mode. Its `encounter_research` input closes for mode M
(for example `10N`) only when all of these hold:

- the contract has `"fidelity_state_by_mode": {"M": "accepted", ...}`, and the
  ledger says the same;
- in both files, `unresolved` is a list whose length equals
  `unresolved_material_count`;
- no unresolved claim covers M. Each unresolved claim is an object with
  `"modes": [...]` that uses only `10N`, `25N`, `10H` and `25H`. A claim with
  no `modes`, a bare-string claim, or an unknown mode counts as covering every
  mode.

Rules:

- Keep the contract-level `fidelity_state` at `fidelity_blocked` while any
  mode is open, because the research-contract tests require it.
- Set `fidelity_state_by_mode[M]` to `accepted` only when every material claim
  for M is resolved with sources, compared with native code and given an
  acceptance observation. Never set it just to unblock the gate.
- Give each open claim the narrowest true `modes` list. For example, a
  heroic-only item gets `["10H", "25H"]`.
- `raid_workloop program status --boss <key>` shows the gate's reason, which
  names the claim that still blocks. The Omnotron contract and ledger show the
  expected shape.

## Build the claim ledger

Follow [references/claim-ledger.md](references/claim-ledger.md). Research both:

- encounter truth: phases, native start/reset/credit, spells, timers, health,
  damage, counts, target selection, difficulty and raid-size deltas;
- executable strategy: tank/healer/DPS assignments, positioning, target
  priority, swaps, interrupts, dispels, cooldowns, vehicles/interactions,
  recovery, and legitimate completion.

Keep source truth, current repository behavior, and proposed bot tactic as
three separate fields. Record conflicts instead of choosing a convenient value.
If no authoritative input resolves a material value, leave it `unresolved` and
keep qualification `fidelity_blocked`.

Maintain `research_completion` in the existing ledger: one row per mechanic or
lifecycle obligation, with `key`, mode scope, status, known evidence, source
references and the exact next question. Full research is complete only when
the required coverage has supported values, a native comparison and specified
acceptance observations for the requested modes. Executing those observations
is implementation validation, not a prerequisite for finishing research.
Unresolved reference values still block the affected fidelity claim. A bounded
repair can be ready earlier; name its scope. Neither a populated packet nor a
clear proves full fidelity. Update superseded claims in the main dossier and
contract, not only an addendum that a worker may never read.

## Review the current script shape

Confirm source/loader/instance/DB registration, actor spawn or summon authority,
doors/transports, prerequisites, save/load, reset, death/credit, and all four
mode branches. Source presence is not runtime readiness.

Classify the implementation handoff:

- `missing_dedicated_implementation`;
- `instance_foundation_incomplete`;
- `source_present_static_gaps`;
- `source_present_ready_for_diagnostic_shard`;
- `fidelity_blocked` even if engineering may continue.

Do not invent code, SQL, coordinates, timers, or scaling during this pass.

## Deliver a bounded packet

Update only the boss dossier, contract, ledger, catalog/readiness rows that
derive from them, and focused tests. Run:

```bash
pixi run pytest -q tests/test_cata_raid_research_contracts.py
```

Hand `raid-encounter-implementation` a phase graph, mode matrix, exact resolved
claims with sources, unresolved blockers, current-script gaps, and acceptance
observations. The implementer must not need to repeat broad web research.

A tactic or policy choice, such as a phase threshold, allowed deaths, a DPS
gate or dropping an ability, is the user's. Put it in the handoff's
`needs_user_decision` and do not decide it yourself (trinity-orchestrator,
"When to ask the user").
