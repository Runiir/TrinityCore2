# Raid program error ledger

Updated 2026-09-12. This is the canonical index of known blockers and rejected
assumptions. The current workflow summary chooses work; this ledger explains
what has already failed. Do not create a new handoff document merely to copy it.

## Current queue

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| OBS-009 | Timeline incoming-damage omission repaired | Existing raw callbacks were retained but the timeline only emitted outgoing damage and healing. Amount-zero incoming callbacks and native raw amounts were invisible in the primary diagnostic view. | Incoming summary and damage_taken events now join the same identity/route/window. Delta-eviction regression test and retained a4b9 replay preserve DPS/HPS. Absorption/outcome gaps remain explicitly unknown. |
| ENC-006 | Native low pre-armor envelope recovered; exact tuning unresolved | The a4b9 raw stream retains24 Magmaw melee callbacks, raw4,466-8,012, health20,127,17zero-health. Native raw is after done/taken modifiers but before armor/outcome, unlike WCL U. Zero-health cause and real absorption remain unavailable. DamageModifier1 is inherited, not a proven recent regression. | Use summary.incoming_damage before requesting another capture. Obtain ordinary-swing roll/modifier/outcome/mitigation context for a stage-matched WCL comparison; no guessed multiplier. See the current Magmaw baseline. |
| REF-001 | WoWSims input-check false stale result fixed | The CLI compared pending generator JSON against a promoted catalog including result fields, while its existing test correctly stripped promotion fields. All16 accepted references validated, but `--check` rejected them. | CLI now uses the existing pending projection; fixtures accept promoted results and reject changed request hashes/invalid JSON. Keep `validate-catalog` for result integrity. Never regenerate an accepted catalog to remove its result fields. |
| ENC-004 | Native queue repair reviewed; fixture and 150.254s live clear passed; live collision attribution and overall performance remain unaccepted | A second overdue Mangle event is consumed while Lava Spew has just started casting; native rejects Mangle but the old script advances Crash anyway. | Preserve queued events with a post-dispatch cast check, including the impaled-phase exception. See [Magmaw audit](magmaw_fidelity_20260912.md). This is not a proven cause of the historical DPS decline. |
| ENC-005 | Research-backed native discrepancy; target-era compatibility pending | Sweltering Armor is applied on Mangle boarding, while historical 10N and 25H WCL apply it at Mangle removal. | See [longer WCL evidence](magmaw_longer_wcl_20260912.md). Distinguish successful hooks, timeout release and reset/death before moving application. Second 25H removal follows Mangled Lifeless by 113ms; the tank survives. Aura removal alone does not prove hook success. No causal DPS attribution or combat fix claimed. |
| CAP-006 | False failure streak repaired and native accepted on b113 | f0be stopped on Chainwielder at 84.675s despite fresh attacks: same situation/action count22 included successes. Native result is now part of the repeat predicate; tests preserve 20 real failures. b113 passed both trash nodes and cleared; reviewed outcome changes reset to1. | Preserve thresholds and the outcome-aware counter. Do not blame optional support or weaken termination for this accounting defect. The complete timeline made the false stop directly diagnosable. |
| CAP-005 | Immutable timeline and native pressure retention accepted | A 128-row tail erased decisive manual events. New record-time context plus4096 pending entries retain the causal stream; native4097 pressure emission drains33 pages to zero and reports the deliberate overflow. b113 has26345 trace rows and no trace/combat gaps. | Use retained delta timeline, not a late interactive tail. Keep aggregates/identity. Actual pressure command parser must accept four digits; replace source-string tests that bless a three-digit limit with the compiled registered-command fixture. |
| ENC-003 | Actor-specific optional support admission implemented; exercised live on b113 | On6882 Fire hook had244 damage in final57.689s and Hunter23 Serpent Sting LOS failures. Selection lacked actor LOS/range while movement forbade repairing geometry. Production fixtures reject blocked optional parasites and preserve mandatory bait/threat; current live run exercises legal support and fresh body return. | Preserve actor-specific native admission and mandatory ownership. Do not infer every rejected nearest candidate from snapshots, or claim this explains every outage. Exact raid DPS recovered138308→181673; original DPS-023 cause and full performance acceptance remain unresolved. |
| OBS-008 | Native terminal cast-failure reason absent on6882 | Fire bait's Hazard Scorch lasts1.246s with path progress, then native_spell_finish_v1 reports only success=false. No same-timestamp LOS/profile rejection identifies the cause. The prior rapid cancellation loop is removed. | Retain terminal native SpellCastResult/cancellation cause and cast-instance identity before another guessed rotation change. Current-spell observations and accepted submissions do not identify terminal failure. |
| REV-001 | Corrected recent-event attribution on6882 | Initial late-window sum4,079,235 included1,041,252 damage-taken events and33,977 friendly damage because recent events omit perspective. Canonical hostile outgoing total is3,004,006, exactly matching cumulative-counter change. | Reconstruct actor ownership and hostile target identity before summing recent events; reconcile against canonical counters. Review guidance updated. This is an analysis error, not a gameplay defect. |
| ENC-002 | Native two-way swap accepted on6882 | Contract alone failed on41266 because adaptive ownership bypassed both callers and generic boss candidate claimed Movement. Narrow typed action now submits Paladin62124 and DK56222; native ownership transfers follow, with exactly two swaps and no repeats. | Preserve shared swap/latch and moving-spline-safe facing. First Pal transfer observed by+91.919s; reciprocal DK body ownership+186.133s. All ten survive the boss. |
| DPS-035 | Corrective FLOAT migration installed and read back on 41266 | ff34 had only Scorch55 because native FLOAT equality matched zero rows; SQLite missed precision. Correction08 now installs exactly one moving Scorch56 while preserving55. | Setup edge accepted. Do not repeat SQL changes. Follow new native completion failure DPS-036. |
| DPS-036 | Early hazard cancellation repair accepted on6882; terminal Scorch gap is OBS-008 | On41266,47 accepted Scorches were cancelled within26-300ms by retained Hazard movement. On6882 the Hazard cast lasts1.246s with path progress; uncovered Fireball still interrupts. Full Scorch finish/landing remains unsuccessful. | Preserve both native movement permission checks. Do not repeat the repaired interruption patch or infer terminal cause from success=false. Obtain native failure reason via OBS-008. |
| DPS-037 | Elemental close-range Lightning Bolt eligibility rejected on 41266; repair queued | At pull+39.844s actor30010 is stationary, not casting, and has no legal candidate. LB403 fails only configured min_range12; bound native SpellRange4 has minimum0. Eleven unique retained evaluations repeat this restriction. | The same row controls preferred positioning, so do not disguise a duplicate filler via tags or silently alter formation. Separate native cast legality from positioning explicitly, or validate the deliberate positioning change. No coefficient tuning admitted. |
| DPS-034 | Rejected immediate DK handback hypothesis; no implementation | DK receives Sweltering Armor 78199 at +90.019s; run-bound DBC duration is 90 seconds. Paladin body ownership covers this armor-reduced interval, then takes the next Mangle at +185.023s. | Preserve normal two-tank alternation. The run ends before a required post-second-Mangle handback can be observed. Preferred DK main tank does not justify reclaiming during its armor debuff. |
| DPS-033 | Moving Scorch candidate reaches submission on 41266; native completion blocked by DPS-036 | Fire bait previously had42.500 seconds of moving Fireball rejection with Scorch mana-gated. Moving row56 now selects in corrected high-mana masks, while higher valid choices remain preferred. | Preserve the candidate repair and stationary low-mana row. Native failure belongs to execution diagnosis DPS-036. |
| DPS-032 | Boss-health potion gate accepted live on ff34 | On a152 the newly enabled79476 casts successfully when parasite201 is at19.11% and Magmaw is roughly66%. | Stable engaged-boss health now feeds candidate and both downstream gates. First review caught omitted consumers; corrected, with 11 focused tests passing. Native item lockout and ordinary add execute remain unchanged. ff34 native use follows boss24.957% despite parasite target; next snapshot proves self potion aura and stat increase. No fresh inventory decrement receipt. |
| OBS-007 | General raid effective-stat observation accepted live on ff34 | Ordinary raid snapshots expose melee AP/Vengeance, while fuller owner/pet stat collection is calibration-only. Class reviews repeatedly lack live caster/secondary-stat joins. | Native collector reused for timestamped owner/permanent-pet raid snapshots, with school-specific SP/crit and legacy fields preserved. Eight focused tests and independent review pass. Capture in the gameplay batch; no standalone rerun. |
| DPS-031 | Rejected maintenance-priority hypothesis; no implementation | Exact joins show both Aimed-over-maintenance samples satisfy a conditional Aimed branch that precedes maintenance in the pinned APL. Isolated Steadies were interrupted by movement, not a proven lower-APL successor. | Do not change maintenance priority from total haste count. Require an actual stationary valid-maintenance evaluation displaced by a lower-APL successor. The53220 gate repair and final filler executed correctly on a152. |
| ENC-001 | Drudge survival failed on ff34; recurrence under causal review | Firehook30007 and Aff30008 die to overlapping Drudge79974/79604 on a152. The>=18yd safety check fails, movement requests the same reached anchor, then ContinuePackCombat permits combat despite tactical safety failure. | Existing per-slot recovery anchors restore separation. First review found return path lacked source-union checks despite safe endpoints; correct and test both directions before build. No native path or tolerance workaround. |
| DPS-030 | Affliction combat potion native cast observed on a152; timing issue DPS-032 | Actor30008 pre-pots and reaches execute health, but its raid profile contains no79476 action despite a reserved second58091 item and the exact APL's second potion. | Add the ordinary item candidate with observable execute-health timing. First verify native LastPotionId lifecycle and shared reservation; never clear lockout or install an aura to force use. |
| HEAL-001 | Holy Paladin profile incomplete; bounded repair pending | Actor30004 learned Beacon53563, Aura Mastery31821, Divine Plea54428 and Light of Dawn85222, but its loaded six-action profile contains none of them and no Holy Power spender. | Define one native capability repair using existing tank assignments and normal resource gates. Keep observed zero deaths separate from complete healer behavior. |
| OBS-006 | Discipline shield outcome missing from healing totals | Actor30005 successfully casts Power Word: Shield26 times across ten players, but the full export has no spell17 healing rows and no recorded absorbed_amount. | Trace native absorbed damage into attributed healer outcomes before ranking Discipline by reported HPS; successful shield casts alone do not prove absorption amount. |
| DPS-027 | Marksmanship aura and filler accepted live on a152 | Actor30009 checks53221 for Steady Shot maintenance; native paired Steady Shots apply haste53220. Required53221 is missing in107 stationary masks. | Scoped aura53220 gates plus exact-APL final Steady filler preserve focus generation; seven focused tests and independent review pass. Review caught MySQL comment syntax missed by SQLite; corrected with a compatibility check. Native aura gates and row 72 filler executed on a152; separate priority hypothesis DPS-031 was rejected. |
| DPS-028 | Elemental movement cooldown accepted live on a152 | Actor30010 lacks79206 in learned spells and action profile; four movement-only masks reject otherwise-ready Lava Burst solely for movement. | One native79206 success unblocks a successful moving51505 cast; stationary, unavailable-opportunity and cooldown controls pass. Glyph101052 still affects Lightning Bolt only. Whole-fight cadence differs with phase duration; no new Elemental repair admitted. |
| DPS-029 | Affliction Shadowflame area restriction proven on a152 | Actor30008 has zero Shadowflame submissions; all191 corrected a152 boss masks reject declarative_area_damage_semantics_forbidden. | Join with DPS-026 shared area protection. Admit only a reviewed action-aware safety repair; do not clear protections globally or tune coefficients. |
| DPS-026 | Heart Strike blocked by declared encounter area filter | Source4b24 DK is actual MT, 17,075.296 DPS, 19 DS and20 RS, but zero HS/DRW. Both actions are enabled and learned. | Actual20/20 execution masks reject HS cleave with forbid_area=true; passive range previews overwrite the last mask with a false appearance of selection. Native cooldown and total-rune hypotheses rejected. Keep existing encounter protection until a safe replacement is reviewed; batch with multi-class findings. |
| DPS-025 | Native Vengeance repaired; self-owned AP observed on4b24 | Current native code replaces accumulated AP with 33% of the last two seconds of damage and removes it on an empty window. Official 4.3 notes and pinned WoWSims require accumulated AP with a one-third floor and gradual decay. | Independent recurrence review and focused fixtures passed; live self-owned Vengeance effect0 reached13,817 AP with cap14,738. Accepted; preserve this behavior in the class batch. |
| DPS-024 | DS/RS cadence repaired live on4b24; HS/DRW remain DPS-026 | Manual 21c kill has 3 Death Strike and 3 Rune Strike hits, no Heart Strike or Dancing Rune Weapon damage over 218.902 seconds. DK took a Mangle cycle and substantial incoming damage; survival is not throughput acceptance. | Shared world-bot resolver incorrectly capped unset melee actions at raw five-yard range. Native-reach repair independently approved and accepted live with19 DS and20 RS landings. Scoped Rune Strike cap migration and user-requested DK main-tank assignment independently approved; native Vengeance is DPS-025. WCL Catamara source 11 provides 14 DS casts, 12 RS, 12 HS and 1 DRW in 70.9 seconds, with different solo-tank pressure and gear. |
| DPS-023 | User-observed head-return outage; causal diagnosis active | Manual spectator run on 21c survives beyond exposed head; user reports damage targets recover only after the next Pillar/add switch. Earlier accepted kill ended during head exposure and did not cover this return transition. | Retained evidence proves damage outage but not its internal cause. Fixed-size target/native-stat observation independently approved; one-second capture4b24 is valid but UNEXERCISED because kill ends during first head. The a152 head return passes with 195/195 valid post-return DPS targets and native body damage. This is run-specific acceptance; no targeted repair or universal claim. Preserve the prior intermittent occurrence; no unchanged retry. |
| CAP-004 | Independently live accepted on Magmaw21c | Frozen raid validator calls full native gear materialization and reads absent source/data/dbc/enUS/SkillLineAbility.dbc despite valid configuredDataDir and passed provisioning/readback. | Magmaw9ed ends before any boss attempt; native exit0 and fresh13actor cleanup pass. Pure projection matches all70 BWD actor identities. Magmaw21c passes actual startup and repeated identity checks, clears natively with zero deaths, and cleans all actors. No further retry of this edge. |
| DPS-006 | Straight trajectory live accepted | Orb's forward destination and execution both use ground pathfinding; it leaves damage range before the first tick. | `979f5c832f` completed: 29,706.767 DPS and nonzero Orb damage. All five trajectories and 82736 accepted; remaining lifetime failure is DPS-009. |
| DPS-007 | Native admission identity accepted on Hunter927 | Hunter compares an 11-row catalog with a 14-row loaded pet spellbook. Normal saving also persists those 14 rows. | All 14 admission rows and their hash match throughout the live window. Remaining Python compatibility mismatch is DPS-017; do not reset the pet baseline. |
| DPS-008 | Affliction and Fire setup live accepted | Fire and Affliction (and other audited specs) declare required professions absent from actual `character_skills` rows. | Affliction90 has actual Tailoring 525, matching stats and 90.6387% reference DPS; independent review accepts setup and calibration. Fire also has native Tailoring 525 and applicable enchant4115; exact Fire compatibility awaits DPS-012 consumer repair. Do not tune Affliction coefficients. |
| OBS-004 | Preview publication repair built and exercised on a152 | Lower-priority range observation overwrites all five last-combat diagnostic maps, making an unsubmitted preview look like the execution choice. | Explicit non-publishing mode at two passive callers;16 focused tests pass. Preserve execution publication and returned preview action. |
| OBS-005 | False fallback reason repair built and exercised on a152 | Spell0 successful melee fallback has no SpellInfo; false CooldownReady/HasPower fields synthesize cooldown/no_power reasons. | Infer those reasons only with spell metadata. Four focused tests preserve explicit overrides and real spell failures. |
| OBS-001 | Observation gap; no repair admitted | Current complete calibration exports have no aggregate `native_spell_finish` series, although full/delta serialization was repaired. | Inspect producer/capture mode if a future diagnosis needs cast-finish joins. Do not rebuild only to repeat the serializer change. |
| DPS-009 | Live accepted on 90a181db01 | After straight-motion repair, all five successful-hit Orbs still disappear around five seconds, before their remaining summon timer expires. | All five Orbs survive five seconds and end at 15.404–15.426 seconds; independent live approval. Orb damage 258,122/61 events versus 85,322/22. |
| DPS-010 | Native stat application accepted on Hunter927 | All three Hunter setup lists omit Mail Specialization parent 87506; native Agility multiplier is 1.0 instead of 1.05. | Learned parent 87506 produces native child 86538 and the correct five-percent multiplier. Keep the separate remaining crit/buff question visible. |
| DPS-011 | Native sockets and reference metadata accepted on Hunter927 | Two Hunter Blacksmithing socket gems are serialized without native socket creators; exactly 100 raw Agility is lost. | Blacksmithing 525 and both socket gems apply; 9,536.1 scoring-start Agility minus 1,260 pre-pot matches the exact 8,276.1 baseline. Current v4 references are promoted and clean-verified; native simulator inputs match v3. |
| BUILD-002 | Recurred on 3e; unchanged retry succeeded | GCC 15 internally segfaulted compiling unchanged ValidationRouteTrashThreatControl.cpp; no source drift or memory-pressure violation. | Also recurred compiling unchanged BotMgrEvents/QueryResult on 3e. Failed receipt retained under failed-compiler-attempt-1; unchanged incremental retry compiled and verified. No source workaround admitted. |
| CAP-003 | Live accepted on 90a181db01 | Startup accepts a list-bearing payload as bot status and calls int(list); 905a5213f2 ended during startup readiness, with no native report. | Typed scalar startup completes; CAP-002 window and native cleanup pass. Preserve malformed/mixed-payload regressions. |
| PERF-001 | Independently approved; next controller validation pending | Isolated calibration was waiting for ordinary bots, although native calibration owns a separate population. | Skip that ordinary readiness wait only for calibration startup; 47 focused and four existing watchdog tests pass. Do not claim measured 180-second speedup. |
| DPS-012 | Independently approved; retained Fire replay passes | Fire prepull validation uses final persistent readiness after the valid Mana Gem use, rejecting a proven ready pre-score snapshot. | Validate readiness from the attributable pre-score observation, retain detailed setup receipt checks and malformed/missing snapshot rejection. |

| PERF-002 | Independently approved; live pending | Affliction waits for pet resources during warmup before a final reset that can recover its persistent mana pet natively. | Review bounded self-provided summon bypass; preserve Hunter/Ghoul waits and final exact resource checks. |
| SETUP-001 | Independently approved; live pending | First scored reset erases warmup flask/food receipts while their auras persist, causing a second native use (20 restocked, final receipt 19 to 18). | Preserve current-attempt flask/food receipt state across self-provided reset; test pending and completed native use without preserving scored metrics or potion receipts. |

| REF-001 | Independently approved; current status passes | Status and workspace commands read hardcoded v1 reference paths after the request catalog promotes a newer cohort. | Resolve one coherent current publication from catalog evidence for status and workspace operations; reject mixed/missing authority and preserve path protections. |

| DPS-013 | Live launch accepted on 92787b59c4 | Hunter prelaunch profession checks call ambient DBC loaders in the frozen checkout, before server launch or DB mutation. | Use frozen profession/socket authority and explicitly configured native DBC for exact bonuses/gem colors; test full preparation with default checkout data absent. Failed prelaunch published, remote verified and exact payloads evicted. |

| DPS-014 | Independently approved; cold retained replay passes | Post-run gear identity projection calls the full native gear materializer and fails on absent default DBC after a completed Hunter window. | Pure canonical identity preserves all 16 manifests; seven tests and independent cold frozen-source replay pass. Preserve original report; commit a separate re-evaluation receipt. |

| DPS-015 | Live accepted on Hunter3e | Wild Quiver proc uses CAST phase, whose native event has no action target; its handler silently does nothing. HIT phase has the target but is excluded. | Phase-mask repair produced 110 Wild Quiver hits / 931,396 damage on Hunter3e. Native outcomes independently accepted; no coefficient change. |
| DPS-016 | Health gate live accepted on Hunter3e | Self-targeted Readiness checks its legacy maximum-health gate against the healthy Hunter instead of the hostile target. | Typed hostile-health gate passed all consumers and produced two Readiness uses on Hunter3e. Later cooldown sequencing is DPS-019, a separate failure. |
| DPS-017 | Runtime compatibility live accepted on Hunter3e | Pet manifest lists three autocasts but its own 14-row spellbook has seven active-193 rows; native admission hash matches. | Corrected producer and native-created-by consumer preserve exact 14-row identity and seven autocasts; all 83 affected tests pass after rematerialization. V4 is promoted and clean-verified; historical v3 is preserved. |

| OBS-002 | Full-window observation live accepted on Hunter3e | Initial Hunter stats precede pet combat/autocast eligibility; the t0 crit gap does not prove Furious Howl failed. Full-window owner aura presence is unobserved. | Fixed aggregate receipts proved 24604 absent and 76659 active across all 260,913 Hunter3e samples. The resulting pet targeting repair is DPS-018. |

| DPS-018 | Owner buff independently live accepted on Hunter5c | Hunter3e has no owner Furious Howl aura in 260,913 samples spanning 300 seconds (maximum gap 43 ms), despite the exact enabled wolf spellbook. | Grouped PetAI omitted the owner; Howl cannot target the remaining player-controlled pet. Include the owner and retain periodic grouped refresh. Reject cardinality-only caching, which retains stale equal-size membership. Portable actual-body tests and independent review pass. Hunter5c owner Howl starts111ms and is present in every subsequent sample; 28,522.63DPS/0HPS, complete transport and cleanup. |

| DPS-019 | Native override execution live accepted on e562 | Requested 19434 now resolves native Fire 82926 to replacement 82928 through eligibility and execution. | e562 lands replacement 82928 once at 23.510 seconds. Full Aimed recovery remains blocked by separate native scaling error DPS-022; do not reopen accepted override resolution. |
| DPS-020 | Independently live accepted on c87 | Heroic Vial of Shadows 77999 triggers 109724 at matching cadence, but native damage lacks the pinned simulator's 0.339 attack-power term. Restored-buff5c still averages 5,425.63 per event. | c87 has 28 procs / 458,341 damage, averaging 16,369.32 versus prior 5,425.63. Exact binding, native shutdown and complete transport pass; independent outcome review accepts the repair. Coefficient authority remains pinned simulator, with outcome variance explicit. |
| DPS-021 | Sequencing mismatch proven; repair not yet admitted | Hunter5c selects Readiness before Chimera and submits Rapid Fire three times versus four exact. | Preserve accepted DPS-016 health gate. Determine whether an existing prerequisite can express the reference sequence; a spell merely being on cooldown may not prove the intended ordering. Do not expand DPS-019 into a new policy framework. |

| OBS-003 | Full-window proc observation live accepted on e562 | Fixed aggregates retain native stack aura 82925 and Fire 82926 presence. | Both activate 12 times; Fire is present in 89,761/260,927 samples. Presence transitions do not measure individual stack increments. |

| DPS-022 | Independently live accepted on Hunter9ed | Replacement Aimed 82928 has zero base cast time but ScalingID 578 overrides it with 2,400 ms. The below-E90 1,000 ms gate correctly rejects it. | Hunter9ed lands12 instant82928 casts after30seconds, with12/12 Fire activations/deactivations; combined Aimed damage1,037,243 is98.528% of exact. 30,568.92DPS/0HPS. Previous base-only fixture missed scaling precedence. |


| TEST-001 | Test-only repair independently accepted | Six capture tests copied a live recurrence bank with an old declared config identity, then supplied the current identity; the real evaluator correctly rejected that mismatch before capture. | Rebind only the temporary fixture bank before committing/sealing it. All24 affected cases pass with negative checks intact. Production gates and the real qualification bank remain unchanged; real qualification requires current evidence. |

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
| BUILD-001 | Preserve real native prerequisite includes when splitting or extending headers. | `9423ec8a17` repaired the earlier missing Common.h/Pet.h build failure. | Extracted-body fixtures do not compile the real include chain. The actual build uses non-unity mode. Recurred on aba37: new MAX_SPELL_SCHOOL array lacked SharedDefines.h in the owning header; fixture supplied its own enum and missed this dependency. Add the defining include; preserve the failed build receipt. Recurred on b5bb98493a: support-range adapter used SPELL_RANGE_RANGED/MELEE without Spell.h; extracted fixtures and review missed the native dependency. Minimal Spell.h include independently approved; resume incremental compilation, preserving build-preflight-b5bb98493a. |

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
| `c87cba4c4b` Hunter | 28,870.930 | 0 | Complete 300-second score; Vial damage recovered, Aimed unchanged; independent review active. |
| `5c1d8e430a` Hunter | 28,522.630 | 0 | Owner Howl and role target independently accepted; cooldown sequencing and Vial damage remain open. |
| `3e0b48374e` Hunter | 28,122.610 | 0 | Wild Quiver, Readiness health gate, exact pet compatibility and complete aura observation accepted; proved missing Howl. |
| `92787b59c4` Hunter | 23,506.897 | 0 | Exact native gear/socket/Mail setup accepted; archived and remotely verified. |
| `90a181db01` Fire | 32,288.553 | 0 | 91.8882% of reference; Orb and profession setup accepted. Prepull consumer repaired separately. |
| `90a181db01` Affliction | 28,381.680 | 388.6 | 90.6387% of reference; complete diagnostics and profession setup accepted. |
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

Hunter3e, Hunter5c and Hunterc87 closed evidence is remotely verified and exact raw payloads
are evicted after all causal reviewers finished:

- [Hunterc87 DVC pointer](../../artifacts/cata_raid_program/calibration_marksmanship_hunter_c87cba4c4b_20260909.tar.gz.dvc)
- [Hunter3e DVC pointer](../../artifacts/cata_raid_program/calibration_marksmanship_hunter_3e0b48374e_20260909.tar.gz.dvc)
- [Hunter5c DVC pointer](../../artifacts/cata_raid_program/calibration_marksmanship_hunter_5c1d8e430a_20260909.tar.gz.dvc)

Original summary bytes used by the reviews are preserved as `reviewed_summary.json`
inside each archive; final closure records that input mapping explicitly.

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

- Pressure validation on `36074a3a15` exposed two launch failures before gameplay:
  port 8086 belonged to an unrelated HTTP server, then the native command's
  three-digit parser converted the requested 4097 rows to zero. The latter
  assertion was also copied into a structural test, so the test preserved the
  defect instead of exercising parsing. Retain both failed captures. Use the
  tracked instance-listener overlay and test the actual command caller through
  the manager's bounds gate before the next pressure run.
- A late producer edit missed the source freeze while its consumer was committed.
  Freeze all worker edits before staging, inspect the complete dirty-file set,
  and run the producer-to-consumer fixture on that exact set. Worker completion
  and separate passing tests do not prove the committed integration is complete.
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

## 2026-09-10 timeline closure

Current native source b1132dd087 clears in156.064s at181,672.583 exact DPS
and14,729.419 exact HPS; all ten survive the boss. The comparator separates
clear/repair from performance, remains inconclusive on old switch coverage,
and still requires diagnosis for known healer activity/HPS declines. Raid
damage taken fell20.3%; that demand change and survival do not establish every
healer cause. Do not suppress known declines merely because another metric is
missing. No controlled evidence justified reverting an unrelated accepted fix.

Capture bytes per second fell31.39%; lossless full-event HTML is7,061,175 bytes
instead of213,524,963. An over64MiB browser-tool response was an artifact
packaging issue, not missing telemetry. Preserve all records with deterministic
compression and lazy detail rendering. Keep original report inventories immutable.

An unrelated listener on8086 blocked one owned server startup. The tracked
instance-listener-only overlay uses18086 and records both configuration hashes;
it does not authorize killing the unrelated service or changing gameplay.
The build include failure, pressure command parser and false watchdog attempts
are retained in the current DVC bundle, not silently recast as boss failures.

Publication pointer:
`artifacts/cata_raid_program/magmaw_development_b1132dd087_20260910.tar.gz.dvc`.
The adjacent publication receipt and contained independent reviews define exact
acceptance scope. Next observation is OBS-008; DPS-023 remains historically
unresolved. Do not rerun this accepted capture/retention edge unchanged.
