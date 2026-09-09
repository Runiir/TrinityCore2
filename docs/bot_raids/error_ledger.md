# Raid program error ledger

Updated 2026-09-09. This is the canonical index of known blockers and rejected
assumptions. The current workflow summary chooses work; this ledger explains
what has already failed. Do not create a new handoff document merely to copy it.

## Current queue

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| DPS-006 | Straight trajectory live accepted | Orb's forward destination and execution both use ground pathfinding; it leaves damage range before the first tick. | `979f5c832f` completed: 29,706.767 DPS and nonzero Orb damage. All five trajectories and 82736 accepted; remaining lifetime failure is DPS-009. |
| DPS-007 | Native admission identity accepted on Hunter927 | Hunter compares an 11-row catalog with a 14-row loaded pet spellbook. Normal saving also persists those 14 rows. | All 14 admission rows and their hash match throughout the live window. Remaining Python compatibility mismatch is DPS-017; do not reset the pet baseline. |
| DPS-008 | Affliction and Fire setup live accepted | Fire and Affliction (and other audited specs) declare required professions absent from actual `character_skills` rows. | Affliction90 has actual Tailoring 525, matching stats and 90.6387% reference DPS; independent review accepts setup and calibration. Fire also has native Tailoring 525 and applicable enchant4115; exact Fire compatibility awaits DPS-012 consumer repair. Do not tune Affliction coefficients. |
| OBS-001 | Observation gap; no repair admitted | Current complete calibration exports have no aggregate `native_spell_finish` series, although full/delta serialization was repaired. | Inspect producer/capture mode if a future diagnosis needs cast-finish joins. Do not rebuild only to repeat the serializer change. |
| DPS-009 | Live accepted on 90a181db01 | After straight-motion repair, all five successful-hit Orbs still disappear around five seconds, before their remaining summon timer expires. | All five Orbs survive five seconds and end at 15.404–15.426 seconds; independent live approval. Orb damage 258,122/61 events versus 85,322/22. |
| DPS-010 | Native stat application accepted on Hunter927 | All three Hunter setup lists omit Mail Specialization parent 87506; native Agility multiplier is 1.0 instead of 1.05. | Learned parent 87506 produces native child 86538 and the correct five-percent multiplier. Keep the separate remaining crit/buff question visible. |
| DPS-011 | Native sockets and reference metadata accepted on Hunter927 | Two Hunter Blacksmithing socket gems are serialized without native socket creators; exactly 100 raw Agility is lost. | Blacksmithing 525 and both socket gems apply; 9,536.1 scoring-start Agility minus 1,260 pre-pot matches the exact 8,276.1 baseline. Current v3 references are promoted and clean-verified. |
| BUILD-002 | Recurred on 3e; unchanged retry succeeded | GCC 15 internally segfaulted compiling unchanged ValidationRouteTrashThreatControl.cpp; no source drift or memory-pressure violation. | Also recurred compiling unchanged BotMgrEvents/QueryResult on 3e. Failed receipt retained under failed-compiler-attempt-1; unchanged incremental retry compiled and verified. No source workaround admitted. |
| CAP-003 | Live accepted on 90a181db01 | Startup accepts a list-bearing payload as bot status and calls int(list); 905a5213f2 ended during startup readiness, with no native report. | Typed scalar startup completes; CAP-002 window and native cleanup pass. Preserve malformed/mixed-payload regressions. |
| PERF-001 | Independently approved; next controller validation pending | Isolated calibration was waiting for ordinary bots, although native calibration owns a separate population. | Skip that ordinary readiness wait only for calibration startup; 47 focused and four existing watchdog tests pass. Do not claim measured 180-second speedup. |
| DPS-012 | Independently approved; retained Fire replay passes | Fire prepull validation uses final persistent readiness after the valid Mana Gem use, rejecting a proven ready pre-score snapshot. | Validate readiness from the attributable pre-score observation, retain detailed setup receipt checks and malformed/missing snapshot rejection. |

| PERF-002 | Independently approved; live pending | Affliction waits for pet resources during warmup before a final reset that can recover its persistent mana pet natively. | Review bounded self-provided summon bypass; preserve Hunter/Ghoul waits and final exact resource checks. |
| SETUP-001 | Independently approved; live pending | First scored reset erases warmup flask/food receipts while their auras persist, causing a second native use (20 restocked, final receipt 19 to 18). | Preserve current-attempt flask/food receipt state across self-provided reset; test pending and completed native use without preserving scored metrics or potion receipts. |

| REF-001 | Independently approved; current status passes | Status and workspace commands read hardcoded v1 reference paths after the request catalog promotes a newer cohort. | Resolve one coherent current publication from catalog evidence for status and workspace operations; reject mixed/missing authority and preserve path protections. |

| DPS-013 | Live launch accepted on 92787b59c4 | Hunter prelaunch profession checks call ambient DBC loaders in the frozen checkout, before server launch or DB mutation. | Use frozen profession/socket authority and explicitly configured native DBC for exact bonuses/gem colors; test full preparation with default checkout data absent. Failed prelaunch published, remote verified and exact payloads evicted. |

| DPS-014 | Independently approved; cold retained replay passes | Post-run gear identity projection calls the full native gear materializer and fails on absent default DBC after a completed Hunter window. | Pure canonical identity preserves all 16 manifests; seven tests and independent cold frozen-source replay pass. Preserve original report; commit a separate re-evaluation receipt. |

| DPS-015 | Independently approved; committed 56b2f39fd4 | Wild Quiver proc uses CAST phase, whose native event has no action target; its handler silently does nothing. HIT phase has the target but is excluded. | Change only spell_proc 76659 phase mask from 1 to 2, test native proc semantics, independently review, then measure. Exact reference contribution is about 3,975 DPS; no coefficient change. |
| DPS-016 | Independently approved; committed 981aabe57f | Self-targeted Readiness checks its legacy maximum-health gate against the healthy Hunter instead of the hostile target. | Add a typed hostile maximum-health gate alongside the existing minimum gate; migrate Readiness and test all consumers. |
| DPS-017 | Approved; new v4 cohort promoted and clean-verified | Pet manifest lists three autocasts but its own 14-row spellbook has seven active-193 rows; native admission hash matches. | Corrected producer and native-created-by consumer preserve exact 14-row identity and seven autocasts; all 83 affected tests pass after rematerialization. Publish a new cohort; preserve historical v3. |

| OBS-002 | Independently approved; joined native validation pending | Initial Hunter stats precede pet combat/autocast eligibility; the t0 crit gap does not prove Furious Howl failed. Full-window owner aura presence is unobserved. | Add fixed aggregate native aura receipts for 24604 and 76659 to the joined validation. No pet AI or coefficient change. |

| DPS-018 | Full-window absence proven; native diagnosis active | Hunter3e has no owner Furious Howl aura in 260,913 samples spanning 300 seconds (maximum gap 43 ms), despite the exact enabled wolf spellbook. | Trace native autocast selection/target/application. Earlier t0 timing explanation does not explain full-window absence. No coefficient or manual-aura repair. |

CAP-001 closes the observed equal-partition truncation. The 64 MiB capture cap
remains bounded; it is not a promise that every larger future payload fits. A
separate audit is checking remaining silent-loss paths without reopening the
fixed partition bug. Any new counterexample receives a new entry.

## Closed blockers

| ID | Accepted repair | Live evidence | Wrong assumption to avoid |
| --- | --- | --- | --- |
| CAP-002 | Native eligible/retained/dropped counts, coverage timestamps, 4,096 capacity and final completeness rejection. | `90a181db01`: all 2,997 Soulburn rows through 299,911 ms, zero drops, 2,430 chunks; independent approval; DVC remote verified and exact raw evicted. | Complete transport cannot prove a producer retained every event. Keep permanent compact acceptance regressions after raw eviction. |
| DPS-001 | Native and Python self-provided aura admission follow caster ownership for player and target effects. | `2b661e8b67` Fire passed owned-aura checks. | An aura ID alone does not prove an external buff. Fix every actual consumer, including Python final acceptance. |
| DPS-002 | The real calibration launch reconciles the selected actor's learned spells and reads them back. | `a3d0719729` and `ec02d7196a`: Wizardry 89744 present; native intellect multiplier 1.05. | Generated SQL or a catalog entry does not prove an existing actor learned the passive. |
| DPS-003 | Promoted spec reaction settings feed the native combat scheduler with a 100 ms floor. | `ec02d7196a` Fire: 2,998 decisions, about 100 ms apart; old Fire used about 500 ms. | WoWSims is event-driven; its 10 ms setting is not a polling frequency. Faster decisions also enlarge exports. |
| CAP-001 | Latest heartbeat responses share the bounded capture budget; malformed/truncated exports remain infrastructure failures through final acceptance. | `ec02d7196a`: all 1,399 Fire, 1,738 Hunter and 2,239 Affliction chunks retained. | Equal per-command partitions discarded a complete native export while other capacity was unused. Partial scalars are not a complete accepted run. |
| DPS-005 | Orb suppresses inherited idle owner-follow. | `ec02d7196a`: all five Orbs retain idle motion 0 and do not return to the owner. | Removing follow does not prove damage. The separate destination/execution defect is DPS-006. |
| REF-002 | Correct reference CLI path/commit ordering and track every reconstruction process descriptor, including ignored .log files. | v3 clean promotion check passes all 16 at `70f70a9be6`; no repeat simulations were needed. | Receipt-relative paths are repository-relative; final promotion check requires a clean later commit containing every referenced process log. |
| BUILD-001 | Preserve real native prerequisite includes when splitting translation units. | `9423ec8a17` repaired the earlier missing Common.h/Pet.h build failure. | Extracted-body fixtures do not compile the real include chain. The actual build uses non-unity mode. |

## Active error details

### CAP-003: Status parser accepts a non-count bot list

- The first `905a5213f2` Affliction launch failed inside startup readiness:
  `bot_status_snapshot` used `int(active_bots or bots or activeBots or 0)`.
  A list reached `int`, raising TypeError without a retained scoring result. Which startup command
  preceded the failure and whether scoring started are unknown.
- Recognition allowed any JSON object containing `bots`; calibration and
  diagnosis rows also use that key for arrays. The fallback also discards
  explicit zero counts. Exact offending native bytes were lost by the exception
  path; do not invent which row supplied them.
- Native build and post-run binary verification pass. The process disappeared,
  but actor 1306 retained online/in_use state. Parent verified no worldserver,
  cleared only those stale actor fields and recorded before/after readback.
  Native cleanup did not pass; explicit parent recovery did.
- Reviewed repair recognizes typed status and supported scalar aliases, rejects malformed
  counts, and tests real startup readiness plus transport-neutral polling with
  mixed list-bearing diagnostics and inactive/active statuses. No gameplay change.
- Evidence: `calibration-affliction_warlock-console-905a5213f2.log`, failed
  `closed_summary.json` and `cleanup_readback.json` under the validation root.
  This failed attempt has no DPS/HPS result and does not accept or reject CAP-002
  live. The corrected 90a181db01 retry then completed all 300 seconds, native
  exit/cleanup passed, and independent review accepted CAP-003 live.

### CAP-002: Native diagnostic truncation hidden by complete transport

- Complete `ec02d7196a` Affliction has 2,048 Soulburn diagnostic rows ending at
  204,900 ms; its primary 2,998-row decision timeline ends at 299,977 ms.
  `ObserveAfflictionSoulburnDecision` silently returns at a separate 2,048 cap.
  The artifact cannot tell how many qualifying later rows were discarded.
- CAP-001 did not fail: every one of the 2,239 chunks reassembled. Data omitted
  by the native producer never reaches the transport parser.
- Bounded repair: use the existing primary 4,096 decision capacity, count
  eligible attempts, retained and dropped records plus coverage timestamps,
  and serialize a completeness receipt. Overall evidence must reject a missing
  or incomplete required diagnostic while preserving the independent DPS/HPS
  measurement. Do not label native omission as missing transport chunks.
- First independent review found the final-assembly regression would skip after
  raw evidence eviction. A permanent compact clean/drop fixture now passes;
  optional full-size archived-payload checks cannot replace that regression.
- Required counterexamples: 3,001 eligible observations fully retained;
  4,097 observations yield exactly one explicit drop; complete chunk transport
  with a dropped diagnostic must fail final evidence acceptance. Test the
  enlarged real-shape final payload under the existing capture budget too.
- Independent review approves the repair, including permanent regressions with
  raw unavailable (43 passed; three optional raw integrations skipped). The
  actual enlarged export was also reproduced with 1,614,345 bytes headroom.
  Native build and independent live acceptance now pass on 90a181db01: 2,997
  rows through 299,911 ms, zero drops, 2,430/2,430 chunks and 1,674,034
  heartbeat bytes headroom. Overall qualification still lacks external identity.
- Adjacent caps are audit limits, not claimed fixes: primary decisions 4,096,
  Affliction landed events 2,048, pet bite and off-target events 128. Current
  evidence did not fill these arrays. Any future change to duration or sampling
  must account for their coverage; complete transport alone is insufficient.
- Accepted repair evidence: [Affliction90 archive](../../artifacts/cata_raid_program/calibration_affliction_warlock_90a181db01_20260909.tar.gz.dvc),
  including independent diagnostic and DPS reviews; remote reconstruction verified.
- Historical failure evidence: [Affliction ec02 archive](../../artifacts/cata_raid_program/calibration_affliction_warlock_ec02d7196a_20260909.tar.gz.dvc),
  member `calibration-affliction_warlock-ec02d7196a/report.json`, plus local
  `diagnostic-truncation-audit.md` under the validation root. The old controller
  passed its role checks; program-level complete-diagnostic acceptance is withdrawn.

### DPS-006: Orb destination and execution

- Observed on complete `ec02d7196a` Fire evidence: five casts, zero Orb damage.
  The forward path ends 13.476 horizontal yards from the target. Aura 82690
  appears around 400 ms; the first nominal tick is around 1.4 s, after the Orb
  has left the 10-yard selector cylinder. Target validity, LOS and attackability
  remain true. Exact tick timestamps are inferred from native scheduling.
- Earliest code mismatch: `summoner->MovePositionToFirstCollision` derives a
  ground-navmesh endpoint; default `MovePoint` pathfinds again. Changing only
  one call would leave the other rewrite intact.
- Repair `979f5c832f`: one shared collision implementation with unchanged
  default behavior; only Orb requests straight collision calculation and
  straight native movement at both submissions. `Object.h` remains unchanged
  to avoid broad recompilation. Five focused tests and independent Sol review
  pass; native build passes. `979f5c832f` then completed 300 seconds: 29,706.767 DPS, 85,322 damage
  from 22 Orb events and 36,304 Fire Power damage from six events. All 1,399
  chunks survived. Independent review accepts the trajectory and snare; the
  remaining early despawn is DPS-009. Missing Tailoring prevents a complete setup claim.
- Reject: victim requirements, radius/tick/coefficient changes, dummy-position
  changes, bot Z steering, collision bypass, or treating no-follow as DPS repair.
- Evidence: [Fire ec02 archive](../../artifacts/cata_raid_program/calibration_fire_mage_ec02d7196a_20260909.tar.gz.dvc),
  member `calibration-fire_mage-ec02d7196a/dps-review/flame-orb-live-review.md`.

### DPS-007: Hunter persisted and loaded identity

- `ec02d7196a` Hunter: 23,106.767 DPS, pet 737,564 damage, alive throughout.
  All 3,002 pet setup observations nevertheless fail identity; ready ticks are
  zero. This is not evidence of an idle/dead pet.
- Generated authority expects 11 rows, hash `be83c8a872bfb2b7fca6d9fb26d6aa1a0ebb1e9b00eb93d36d1f2ffa36254b74`.
  Loaded state has 14, hash `bc3322f102216e3308dc94e4fa30e2960641678949109ccbda1a90063e684ce8`.
  Extra spells are 1742, 24604 and 65220; 2649/17253 autocast states also differ.
- A fresh parent SELECT after normal native saving found that same 14-row
  state in `pet_spell`. The report's first proposed requirement to see 11 rows
  before every launch is therefore paused. A new loader-receipt subsystem has
  **not** been implemented. The superseding DBC/native design addendum proves
  the stable 14-row projection and saved actionbar. The upstream producer,
  three Hunter catalog rows and generated header now encode that fixed point;
  exact native comparisons remain unchanged. Six focused tests and independent
  review pass; native live acceptance remains pending. Do not bless arbitrary extra spells.
- Affected callers are duplicated in CalibrationReset.cpp, CalibrationBot.cpp
  and CalibrationCompletion.cpp. Rows already uses the shared
  BotWorldPopulationMgrCalibrationIdentity helper. A Completion-only patch
  would be incomplete.
- Actual Hunter throughput remains unresolved even after identity is fixed.
  936 Auto Shot maintenance decisions are not 936 shots; 117 damage events
  landed. The retained WCL raid has Survival, not Marksmanship.
- Closed evidence is currently under
  `/home/runiir/Games/trinity-shared-instance-validation-03cb01db0b/calibration-marksmanship_hunter-ec02d7196a/dps-review/`.
  Publication is remotely verified; all readers finished and exact raw payloads
  were evicted. The owner-DPS diagnosis establishes DPS-010. The archived design addendum explicitly supersedes the original
  repair packet. Reference: [Hunter ec02 archive](../../artifacts/cata_raid_program/calibration_marksmanship_hunter_ec02d7196a_20260909.tar.gz.dvc).

### DPS-008: Required professions missing at actual launch

- `ec02d7196a` Affliction: complete 300 seconds, 29,240.243 DPS (93.3806% of
  reference), 388.6 self-healing HPS, no deaths or movement loss. Throughput
  thresholds pass; this does not establish every setup input.
- The review explicitly lacked independent profession readback. Parent then
  queried actor 1306, skill 197, and received no row. Catalog requirements are
  `provisioning_bot.profession_setup.requirements`, not `bot.skills`.
- Reject the earlier statement that the corrected profession setup was
  accepted. Equipped enchant identity is not native enchant applicability.
  The launch currently reconciles learned spells, not profession requirements.
- Expanded current database audit: Fire, Affliction, Demonology, Shadow and
  Balance lack required skill 197; Enhancement lacks required skill 165.
  Elemental already has its correct required profession and remains accepted.
  Native static-stat parity alone did not detect the missing dynamic enchant.
  See `calibration-profession-database-audit.json` under the validation root.
- Generic launch reconciliation passes 73 tests and independent review;
  no database mutation or new live acceptance has occurred.
- Evidence: local `calibration-affliction_warlock-ec02d7196a/report.json`,
  `dps-review/affliction-calibration-review.md`, and
  `profession_postrun_readback.json` under the same validation root.
  Publication is remotely verified; CAP-002 raw reads are DONE and exact raw payloads are evicted. No claim of an observed Lightweave proc.

### DPS-009: Successful Orb hit still enters early despawn

- `979f5c832f` has five successful-hit Orbs, all disappearing at 4.901–4.905
  seconds with about 13.1 seconds on the summon timer. Every Orb acquires
  native self-snare 82736 but remains victimless.
- The existing `!IsInCombat()` early branch does not recognize that successful
  proximity hit. Add the existing 82736 aura exclusion, whose pinned duration
  covers the normal 15.4-second lifecycle. Never-hit behavior remains unchanged.
- Implementation and independent review pass five focused checks. Native build
  and matched live survival/damage validation remain pending. No coefficients,
  target rules, timer values or native combat state were changed.

### DPS-010: Hunter learned Mail Specialization absent

- The exact owner-stat review of `ec02d7196a` finds Agility multiplier 1.0;
  WoWSims applies 1.05 for full mail. The three Hunter setup lists contain
  Aspect 13165 but omit learned parent 87506. Native spell learning owns child
  86528, and ordinary player load applies the armor specialization.
- Add parent 87506 to producer and linked action lists using an idempotent
  reconciliation. Preserve the approved 14-row pet fixture. Do not persist the
  child or install its aura manually. Implementation passes 24 focused checks;
  independent review passes.
- This does not explain the whole DPS deficit. Subtracting the pre-pot leaves
  native Agility 7,782; applying 1.05 gives 8,171.1 versus simulator 8,276.1.
  The remaining 100 raw / 105 multiplied Agility is now attributed to DPS-011.
  Weapon effective stats and sustained class-buff uptime remain observation limits.
- Compact diagnosis: `hunter-owner-dps-diagnosis.md` under the validation root;
  immutable raw source is the Hunter ec02 DVC archive linked above.

### DPS-011: Blacksmithing socket gems lack native creators

- The exact Marksmanship profile adds a +50 Agility gem beyond native sockets
  on bracers 78430 and gloves 78362. Materialization emits their gem enchants
  but no prismatic creator; the native applicability guard rejects both.
- Required creators are 3717 (bracer) and 3723 (gloves), associated with
  Blacksmithing 164. Belt creator 3729 already works. Existing profession
  inference inspects ordinary permanent enchants and misses extra sockets.
- Exact decomposition reproduces simulator raw gear Agility 7,492 and native
  7,392, closing the 100-point gap without a new run or coefficient change.
- Source implementation covers actual selected-actor equipment reconciliation,
  player-obtainable profession rank and frozen authority, with 27 focused tests.
  Independent review is active; generated outputs and references are pending.
  The exact current affected set is nine specs / 18 items, each losing 100
  primary stat. Crafting requires Blacksmithing 400; provisioning uses 525.
  Existing reference contracts require a new complete 16-spec cohort.
  DBC applicability rank alone is not proof of obtainable crafting rank.
  Do not run another Hunter calibration on the known incomplete input.
- Evidence: `hunter-owner-agility-gap-addendum.md` under the validation root,
  retained with the `905a5213f2` build review context for DVC publication.

## Run index and acceptance boundaries

| Source / spec | DPS | HPS | Interpretation |
| --- | ---: | ---: | --- |
| `798a115d45` Elemental | 32,911.683 | 0 | 88.9522% of reference, optimization accepted. Preserve this result. |
| `2b661e8b67` Fire | 23,839.460 | 0 | Missing actual Wizardry; owned-aura repair passed. |
| `a3d0719729` Fire | 28,821.683 | 0 | Partial native prefix only; final capture truncated. Not accepted full-window evidence. |
| `ec02d7196a` Fire | 29,021.037 | 0 | Complete; Wizardry/cadence pass; Tailoring missing; Orb still zero. |
| `ec02d7196a` Hunter | 23,106.767 | 0 | Complete; pet identity incompatibility and hard-floor failure. |
| `ec02d7196a` Affliction | 29,240.243 | 388.6 | Complete; throughput passes; actual profession setup incomplete. |
| `090f24f4b8` Magmaw 10N | 128,636.918 | 19,225.751 | Native clear; 233 damage-bearing seconds, zero boss deaths. Roster DPS objective remains open. |

Magmaw's encounter-start-to-death duration was 271.011 seconds. Do not mix that
denominator with 233 damage-bearing seconds. Retained WCL uses 1 tank / 1 healer /
8 DPS versus our 2 / 3 / 5; its 378,849 aggregate DPS is not a matched roster floor.
All current development calibrations remain training-ineligible because the
qualification identity and non-certifying fixture boundaries are unresolved.

## Updating and using the ledger

1. Before dispatch or retry, select an existing ID or add one evidenced failure.
   Include that ID, current evidence, rejected approaches, owned callers and the
   acceptance condition in the worker packet. Do not send the entire history.
2. Update the same entry after diagnosis, implementation, review, build and live
   result. These are separate states. A repair with no live outcome stays pending.
3. Record every subsequent attempt as source/run ID plus what changed and its
   outcome. No new run solely because a worker finished or metadata is stale.
4. Count only attempts that reach the same causal edge. Historic counts before
   this ledger are not reconstructed or invented. At ten occurrences, stop
   unchanged retries and write the causal summary against this ID.
5. Keep large traces in DVC. Link the archive and member when published; remove
   obsolete local payload references after verified eviction. A ledger edit
   needs no extra approval, build or live experiment.

## Process failures already observed

- Broad reviews and handoffs omitted actual launch consumers or duplicate native
  callers. Parent caught these late. Map the finite launch-to-outcome path before
  assigning an implementation; return all known blockers together.
- Fixtures proved isolated behavior while setup, native include closure or final
  report assembly remained wrong. Use the actual failing caller and negative
  counterexample; do not equate a passing stub with live success.
- Report and catalog assumptions survived as stale current status. This ledger
  records their replacement explicitly; old reports remain historical evidence.
- Agent usage limits interrupted Hunter diagnosis and implementation preparation.
  No Hunter gameplay edits were made. This is an infrastructure limit, not another
  failed canary or evidence that a different model repaired DPS.
