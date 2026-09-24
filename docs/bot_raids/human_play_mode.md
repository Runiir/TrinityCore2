# Human play mode: humans raiding with trained bots

Status (2026-09-24): steps 0-1 are done. Step 2 (first playable version) is next.
First target is Magmaw 10N (`blackwing_descent_10n_magmaw_diagnostic`, trained
roster GUIDs 30001-30010).

## Progress

**Steps 0-1: done**
- Commits:
  - `e4fa8a143a`: the change itself.
  - `d60e6deea2`: review fixes.
  - Follow-up commits: parser and guard nits, plus scoreboard records.
- Step 0 fixture: `tests/fixtures/magmaw_full_roster_duties_v1.json`. It comes from
  the 8 accepted `b5-d1898555` kills. Across all 8 kills: baiters are 30006/30007
  alternating with hunter 30009, the mushroom caster is 30001, and the taunt caster
  is 30002.
- Chains riders, pull tank and Bloodlust owner leave no kill evidence, so they are
  pinned by `tests/test_magmaw_duty_plan.py`. The live status JSON now reports them
  as `magmaw_duty_plan`: pull 30002, baiters 30006+30009, riders 30007+30008,
  mushrooms 30001, lust 30010.
- Runtime seams, inert for validation:
  - `CohortPurpose` (always validation today);
  - `BotWorld.PlayMode.Enable` (default off);
  - `Blackboard.ExternalPlayers` (always empty);
  - `cohort_purpose` in status and diagnose.
- Value-only pieces:
  - raid-chat callout parser and claims (`BotRaidDutyClaims.h`, `BotMagmawDutyCallouts.h`);
  - raid member view (`BotRaidMember.h`);
  - human role resolver (`BotRaidRoleResolver.h`, checked against `TalentTab.dbc`).
- `tools/raid_program/play_mode_guard.py` refuses play runs in:
  - scoreboard ingest, run, verdict and keep;
  - graph acceptance;
  - the evidence archive;
  - the validation harness.
- Independent review:
  - It found one blocker, now fixed. The status read of the duty plan observed the
    shared baiter rotation, and could switch the bait mage on snapshots no bot
    observes. The receipt now uses `MagmawBaiterRotationRegistry::PeekBaiters` and
    `BuildHookUsers(board, baiters)`.
  - The re-review approved the fixes.
- Live checks on the fixed build:
  - Two smoke kills: clean.
  - Batches `play1-d60e6de` and `play1b-d60e6de`: 10/10 native clears, 0 deaths, and
    the target verdict passes both.
  - The Welch test flagged the Survival hunter once, then not in the confirmation
    batch. Its spells, hit counts and casts per minute match the `b5` kills, so the
    dip is per-hit RNG.

**Constraints learned (they shape step 2)**
- `worldserver.conf.dist` and `Makefile` are hash-pinned by
  `tools/raid_program/tracked_runtime_config_derivation.py` (`TEMPLATE_SHA256`,
  `RECIPE_SHA256`). Consequences:
  - the play key stays out of conf.dist (absent means off);
  - the play launcher must be a standalone script, not a `make` target.
- Non-graph builds go through `tools.raid_program.queued_build` with the frozen
  policy. The queue needs a clean worktree and a fresh `configure` ticket for each
  source commit. `workflow_build run` needs a saved-graph build claim.

## Goal and decisions

Once a boss's bots are trained, real players replace any number of bots, from
1 human + 9 bots up to 9 humans + 1 bot. The tuning and validation workflow does
not change: validation cohorts stay at exactly 10 bots.

Decisions (user, 2026-09-24):

1. Humans just join the raid. Their role comes from the role they set in the raid
   UI or from their talents. Bots adapt. A human can call a mechanic in raid chat
   ("I do chains"), and the bots then leave it alone. Without a callout, any capable
   bot does the job. Duties are not tied to one class (for example, chains and baits
   are not reserved for one spec).
2. The raid leader is a human, who runs ready checks and pull timers.
3. Bots engage when the pull timer reaches zero or when a human pulls, whichever
   comes first.
4. Success means bots do their duties and never get stuck. They play at trained
   peak and try their best. Kills are expected but not gated.
5. Play and validation never run at the same time. Play runs are recorded and kept
   for later ML training, but never scored.
6. The human manages their own lockouts (`.instance unbind`).

## Constraints from the code

- The trained Magmaw brain runs only inside the validation cohort/route lifecycle:
  - the kernel owns the tick only when `ValidationRouteEnable` is set
    (`BotWorldPopulationMgrUpdateBotPreparation.cpp:673`);
  - the strategy runs only on route node `bwd.magmaw.encounter`
    (`BotAdaptiveMagmawStrategy.h:106`);
  - the blackboard players come only from `Party().Bots`
    (`BotWorldPopulationMgrEncounterBlackboard.cpp:376`).

  Play mode is therefore a *play cohort*: the same lifecycle with
  `CohortPurpose::Play`. It is not a separate brain.
- Keep validation unchanged. All new behaviour sits behind `Purpose == Play` or
  behind a non-empty external-member set. External members never enter
  `Party().Bots`, `RosterByGuid` or `board.Players`; they go into a separate
  `ExternalPlayers` list. Every duty rule's first tier is today's exact selector.
  A validation-time shadow allocator must report 0 mismatches, and the Magmaw
  scoreboard run remains the regression gate.
- What blocks humans today:
  - an exact group-membership check each tick
    (`BotWorldPopulationMgrValidationCohortGroup.cpp:264-270`);
  - bots never accept or send invites;
  - the BWD 10N instance cap is 10 non-GM players;
  - humans cannot log into pool characters (`CharacterHandler.cpp:742`).
- Several files that need hooks are 900-999 lines. Put all logic in new files and
  use one-line call sites.

## Session flow

1. Server: a play worldserver config derived from `trinity-worldserver-test.conf`
   (the `Makefile` and conf.dist are hash-pinned, so no make target): add
   `BotWorld.PlayMode.Enable = 1`, `AllowTwoSide.Interaction.Group = 1`,
   `PlayerBot.Record.Enable = 0`, a higher `AccountInstancesPerHour`, and (until
   play recordings carry play tags) `BotWorld.AutoStartRecording = 0`. Start it
   with the console on stdin; `make host-auth` or an existing authserver serves
   logins. `fill` resets the bot pool itself (bot-owned rows only).
2. Human: logs in on their own level-85 Alliance character with GM mode off. They
   form a raid, set 10N, set their raid role, and go to the BWD entrance.
3. The leader runs `.botauto play fill`. The server counts humans by role, and the
   composition solver picks which trained slots stay bots. Bots are provisioned
   into the leader's group with `BotMgr::ProvisionWorldBotInGroup(leader, ...)`,
   which already accepts any grouped anchor (`BotMgr.cpp:218-255`). The instance
   therefore belongs to the human's group.
   - Planned: if a human joins later, the lowest-cost bot of the same role
     leaves automatically (today a later human is registered, and an 11th
     member ends the session).
   - If the leader kicks a bot, it despawns, and no refill happens unless asked.
4. Pacing (autonomous; `.botauto play go` is only a manual override). Bots move
   to the next route node when a human in the raid instance is within 45 yd of
   it, has moved closer to it than to the bots' node, or is fighting that
   node's creatures, or while the leader's pull timer is counting down or has
   just released. Otherwise they hold at their node.
5. Trash: once the bots have moved to a pack, the bot tank (or the Chainwielder
   patrol owner) pulls it as in validation. Known gap: a human who pulls the
   Drudges or the Chainwielder patrol before the bots arrive is not yet handled
   (the Drudge activation latch keeps bots out until its own pull; phase 4).
6. Boss:
   - The leader's ready check makes bots answer, through the existing responder
     (`BotWorldPopulationMgrRecovery.cpp`: "ready" after 5 s stable). Repeated
     checks are answered too; a check never reopens a completed wipe recovery.
   - Bots stage at Magmaw but hold the pull (`Route.PullPermitted`) until the
     leader's pull timer reaches zero or anyone engages the boss. After zero
     the pull stays open for 30 s; a wipe cancels the timer. Timer sources:
     DBM raid warning "Pull in N sec" and its addon sync (`D4`/`D5`, `U` pizza
     timer or `PT`), BigWigs sync, leader/assistant raid chat ("pull 10"), and
     `.botauto play pull [seconds|cancel]`. A number counts only when it ends
     the call or is followed by seconds.
   - The engagement spends the timer. `.botauto play status` reports
     `boss_engaged:pull_timer|before_timer|after_window|without_timer`, then
     `boss_killed` or `boss_reset:start_a_new_pull_timer|pull_timer_running`;
     `pull_window_expired` appears only when zero passes with no engagement.
     Edges count only when a bot inside the instance observed them. A boss
     that resets needs a new timer, even inside the 30 s window.
7. Wipe (all bots dead, or native encounter reset): bots release, run back and
   hold again until the next ready check and pull timer.
8. Kill: bots stay grouped. `.botauto play stop` removes the bots.

## Role detection (humans)

1. The role the human sets in the raid UI. `CMSG_SET_ROLE` calls
   `Group::SetLfgRoles` (`GroupHandler.cpp:395-416`), and `GetDungeonRole` already
   reads the group LFG role first (`BotWorldPopulationMgrCombatSupport.cpp:87-99`).
2. Otherwise, the primary talent tree (`Player::GetPrimaryTalentTree(GetActiveSpec())`)
   mapped to a role through a table (Protection, Blood and Feral bear → tank;
   Holy, Discipline and Restoration → healer).
3. Never the legacy class fallback, which treats every Warrior or DK as a tank. If
   the role is unknown (for example Feral with no role set), assume dps and ask in
   raid chat.

## Composition solver (`fill`)

- The template is the trained roster: 1 tank (Blood DK), 3 healers, and 6 dps,
  counting Balance in the `raid_tank_1` slot as dps.
- Each human takes a template slot of the same role, choosing the slot with the
  lowest duty-disruption cost from a per-encounter table.
- Extra humans of one role replace dps slots.
- Magmaw dps cost order: `raid_dps_5` (Elemental; lust only) < `raid_dps_3`
  (Affliction; a chains rider) < `raid_dps_1`/`raid_dps_2` (Fire; bait rotation)
  < `raid_dps_4` (Survival; bait and Chainwielder puller) < `raid_tank_1`
  (Balance; mushrooms, and the preferred battle-res bot).
- The healer cost order is still to be derived from heal-assignment and chains
  healer-tier use.

## Duties, callouts and fallbacks (Magmaw)

Each duty resolves in this order: a human claim → tier 1 (today's owner) →
capability fallback → unowned. Bots never wait for a human to perform a duty; they
wait only for presence, a pull or timer, or a native event. A bot confirms a claim
in raid chat. "bots do X" releases the claim.

| Duty | Callout keywords | Tier 1 today | Capability fallback |
|---|---|---|---|
| Chains (pincer riders ×2) | chains, pincer, hook | fire mage not currently baiting + warlock (then Balance, then healers), `BotAdaptiveMagmawStrategyHook.h:86-165` | any two ranged non-tank bots. Pair with a human seated on the other pincer. A lone bot never boards without a partner (today it would block the humans' pair). |
| Parasite/Pillar bait | bait, parasites, pillar | rotating fire mage + hunter, `BotMagmawBaiterRotation.h:107-147` | any ranged dps bot with mobility. With one capable bot, single lane. If claimed, bots stack. |
| Bloodlust/Heroism | lust, hero, bloodlust, time warp | Elemental Shaman; needs an exact 10-bot roster, `BotWorldPopulationMgrMagmawBloodlust.cpp:43-111` | any shaman bot, then a mage bot (Time Warp). If claimed, bots never lust; they already respect the lockout. |
| Chainwielder pull | I pull | slot-9 hunter, Misdirect onto the bot tank, `ValidationPatrolPull.cpp:212-315` | a human pull or the pull timer. Otherwise a bot tank or ranged bot. The handoff completes on any declared tank. |
| Main tank / taunts | (role) | lowest-GUID bot tank | first declared tank, bots first by slot order, then humans. A bot tank never taunts off a live declared tank. |
| Mushrooms | mushrooms | any Balance bot | skipped if there is no Balance bot |
| Battle res | brez, I res | cohort bots only, `BotWorldPopulationMgrCombatRes.cpp:276-303` | humans become candidates. Dead bots accept a rez from any group member. |
| Healing | (role) | bot healers target only `board.Players` (`UpdateBotKernelCandidates.cpp:775-907`) | all members by HP. The Mangle target has priority; `FindMangleOwner` also scans `ExternalPlayers`. |

Callouts are parsed from raid/party chat through the existing
`OnPlayerChat(..., Group*)` hook (`ChatHandler.cpp:409-489`) in a new PlayerScript.
The command `.botauto play claim|release <duty>` is the fallback.

## Ready check and pull timer

- Ready check: the server only relays it (`GroupHandler.cpp:733-765`). Add one core
  hook in the request branch (for example `sScriptMgr->OnGroupReadyCheck`), which
  arms the existing bot responder.
- Pull timer: `/pull` comes from an addon (DBM or BigWigs), not the base client. The
  server receives addon messages in `HandleAddonMessagechatOpcode`
  (`ChatHandler.cpp:567`), but that function has no script hook, so add one.
  - DBM sends prefix `D4`, text `PT\t<seconds>` to RAID (0 cancels).
  - The BigWigs 4.3.4 format is unverified. In play mode, log the leader's addon
    messages and confirm with one live `/pull`.
  - Fallbacks: raid chat "pull 10", or `.botauto play pull 10`.

## Data collection (for ML)

- Recording is on in play mode. Every record is tagged `cohort_purpose=play`, with
  the human members (guid, class, spec, role), the composition, the claims and the
  session id.
- The combat log resolves actors only through `FindCombatLogCohortPlayer`
  (`BotWorldPopulationMgrCombatNotifications.cpp:202-243, 540-541`), so human
  damage and heals are lost today. In play mode, include registered humans with
  `actor_kind=human`; human play is itself training signal.
- Collector: a new `tools/bot_ml/play_session.py`. It polls `.botauto combatlog
  delta`, `trace` and `diagnose` over SOAP (enabled in the test conf) at the
  heartbeat, archives each session under `artifacts/play_sessions/<id>/`, and runs
  `dvc add` and `dvc push`.
  - There is no scoreboard ingest.
  - A guard in the scoreboard, acceptance and archive tools refuses play runs.
- Mutual exclusion:
  - `.botauto play start` refuses while a validation cohort is active.
  - The validation harness refuses while a play session is active.
  - The next validation run re-provisions and resets the trained characters.

## Testing without humans (optional tooling)

`.botauto play sim <slot> <mode>` loads the dropped slot's trained character. It is
driven by the naive companion `BotController`, and it is registered only as an
external member, so the cohort treats it exactly like a human.

- Classification is by cohort membership, not `IsBotSession`.
- Modes: assist, idle, careless, pincer_thief, tank, premature, leader.
- Pass criteria: no membership terminal, no unexplained hold, and duty receipts
  equal to the allocator plan.

## Phases

0. Extract today's per-wave duty receipts from the accepted run (b5-d1898555) into a
   test fixture.
1. Foundations with no behaviour change:
   - `CohortPurpose`;
   - member view;
   - duty allocator plus claims model;
   - validation shadow allocator;
   - play guard in the scoring tools.

   Gate: 0 shadow mismatches, and the Magmaw 5-kill scoreboard passes.
2. Play MVP:
   - `host-world-play`;
   - human-led `fill`;
   - membership policy;
   - role detection;
   - ready-check and DBM pull hooks;
   - pacing;
   - healing, battle res and Mangle awareness for humans;
   - recording and collector;
   - sims (assist, idle).

   Gate: sim sessions plus one live session with one human dps.
3. Callouts and capability fallbacks (chains, bait, lust, pull), and human healers.
   Gate: sim sweep over every dps and healer slot.
4. Human tanks, route jump on early pulls, and wipe/re-pull pacing. Gate: tank sim
   plus a live human-tank session.
5. 1-4 bot mixes, and a generalized `DutyRules` interface for the next BWD boss.

## Verify live

- BigWigs `/pull` addon format on 4.3.4.
- Whether the DK's taunt (Dark Command) wins arbitration when a human takes threat.
- Whether raid-wide stat buffs reach members who join later.
- How the 4.3.4 client handles very long system chat lines (keep play status
  compact).
