import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
IMPL = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
GENERIC_SMOKE = json.loads((ROOT / "experiments/configs/cata_raid_phase1_generic_mechanic_smoke_v1.json").read_text())


def test_single_cohort_owns_one_raid_runtime():
    raid_struct = HEADER.index("struct RaidRuntime")
    cohort_struct = HEADER.index("struct CohortRuntime")
    cohort_end = HEADER.index("struct BotGuidLease", cohort_struct)

    assert raid_struct < cohort_struct
    assert "RaidRuntime Raid;" in HEADER[cohort_struct:cohort_end]
    assert "uint64 ServerEpoch" in HEADER[raid_struct:cohort_struct]
    assert "uint64 AttemptId" in HEADER[raid_struct:cohort_struct]
    assert "std::map<uint32, RaidRosterSlot> RosterByGuid" in HEADER[raid_struct:cohort_struct]


def test_no_pch_runtime_declares_roster_plan_before_use_and_compares_transport_identity_by_guid():
    group_start = IMPL.index("void BotWorldPopulationMgr::EnsureValidationCohortGroup()")
    group_end = IMPL.index("bool BotWorldPopulationMgr::ResolveSpawnPlacement", group_start)
    group_runtime = IMPL[group_start:group_end]
    assert group_runtime.index("std::vector<RaidRosterPlanSlot> const rosterPlan") < group_runtime.index("rosterPlan.size()")
    assert '#include "VehicleDefines.h"' in IMPL[:IMPL.index("namespace")]
    assert "transport->GetTransportGUID() == gameObject->GetGUID()" in IMPL
    assert "bot->GetTransport() == gameObject->ToTransport()" not in IMPL


def test_raid_size_and_difficulty_are_explicit_and_fail_closed():
    assert "uint8 RaidSize = 10;" in HEADER
    assert "uint8 RaidDifficulty = 0;" in HEADER
    assert '"raid_size"' in IMPL
    assert '"raid_difficulty"' in IMPL
    assert '"raid_size_difficulty_mismatch"' in IMPL
    assert "leader->GetSession()->HandleSetRaidDifficultyOpcode(difficultyRequest);" in IMPL
    assert "group->SetRaidDifficulty(requestedRaidDifficulty);" not in IMPL
    assert "group->SetRaidDifficulty(RAID_DIFFICULTY_10MAN_NORMAL);" not in IMPL

    valid = {(10, 0), (10, 2), (25, 1), (25, 3)}
    observed = {
        (size, difficulty)
        for size in (10, 25)
        for difficulty in range(4)
        if ((size == 25) == bool(difficulty & 1))
    }
    assert observed == valid


def test_deterministic_five_player_subgroups_cover_10_and_25():
    assert "memberIndex / MAXGROUPSIZE" in IMPL
    assert "group->ChangeMembersGroup(bot->GetGUID(), subgroup);" in IMPL

    assert [index // 5 for index in range(10)] == [0] * 5 + [1] * 5
    assert [index // 5 for index in range(25)] == sum(([group] * 5 for group in range(5)), [])


def test_generic_raid_mechanic_contracts_are_typed_executable_and_fail_closed():
    assert GENERIC_SMOKE["authority"] == "synthetic_test_only_not_boss_fidelity"
    contracts = [row["mechanic_contract"] for row in GENERIC_SMOKE["routes"]]
    assert {row["formation_family"] for row in contracts} == {"pair", "lane", "quadrant", "ring", "cone"}
    assert all(row["id"] and row["arrival_tolerance_yards"] > 0 for row in contracts)
    assert all(row["target_entries"] for row in contracts)
    assert "node.MechanicContractResolved" in IMPL
    assert 'adapter.AssignmentType = "contract_unresolved"' in IMPL
    assert 'result.Action = "raid_" + raidAnchors.FormationFamily + "_anchor"' in IMPL
    assert 'raidAdapter.TargetControl == "do_not_damage"' in IMPL
    assert 'raidAdapter.TargetControl == "controlled_aoe"' in IMPL
    assert 'raidAdapter.TargetControl == "kill_sync"' in IMPL
    assert "HandleGameObjectUseOpcode(use)" in IMPL
    assert "HandleSpellClick(click)" in IMPL
    assert "transport->GetTransportGUID() == gameObject->GetGUID()" in IMPL
    assert "HandleAreaTriggerOpcode(areaTrigger)" in IMPL
    assert "declarative_area_damage_forbidden" in IMPL
    route_start = IMPL.index("bool BotWorldPopulationMgr::TryValidationRouteObjective")
    route_end = IMPL.index("bool BotWorldPopulationMgr::IsBossContext", route_start)
    route_runtime = IMPL[route_start:route_end]
    assert route_runtime.count("TryBossMechanics(state, bot, power, stage, activity)") >= 2


def test_phase1_target_transfer_and_swap_controls_are_executable():
    for token in (
        'raidAdapter.TargetControl == "focus_fire"',
        '"declared_target_selected"',
        'raidAdapter.BattleResurrectionPolicy != "assigned_only"',
        'currentTank->GetGUID() == raidAssignment.MainTankGuid',
        'currentTank->GetGUID() == raidAssignment.OffTankGuid',
        '"raid_kill_sync_execution_hold_low_target"',
        'isHeldLowTarget(bot->GetVictim())',
        'isHeldLowTarget(current->m_targets.GetUnitTarget())',
        'isHeldLowTarget(repeat->m_targets.GetUnitTarget())',
        'isHeldLowTarget(pet->GetVictim())',
        'isHeldLowTarget(controlled->GetVictim())',
        'bot->InterruptSpell(CURRENT_GENERIC_SPELL, false);',
        'bot->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);',
        'for (Unit* controlled : bot->m_Controlled)',
    ):
        assert token in IMPL


def test_tank_swap_level_triggers_are_edge_latched_until_the_condition_clears():
    assert "std::string LastRaidTankSwapTriggerKey" in HEADER
    assert "uint64 LastRaidTankSwapWipeGeneration" in HEADER
    for token in (
        'tankSwapTriggerKey = "cast:"',
        'tankSwapTriggerKey = "add:"',
        'tankSwapTriggerKey = "phase:"',
        "state.LastRaidTankSwapTriggerKey != tankSwapTriggerKey",
        "state.LastRaidTankSwapTriggerKey.clear();",
        "state.LastRaidTankSwapWipeGeneration != Cohort().Raid.WipeGeneration",
        "state.LastRaidTankSwapWipeGeneration = Cohort().Raid.WipeGeneration;",
        "memberState.LastRaidTankSwapTriggerKey = tankSwapTriggerKey;",
        "memberState.LastRaidTankSwapWipeGeneration = Cohort().Raid.WipeGeneration;",
        "state.LastRaidTankSwapTriggerKey.clear();",
    ):
        assert token in IMPL


def test_battle_res_slots_allow_native_capable_non_healers_and_role_priority_is_real():
    raid_brez = IMPL[
        IMPL.index("bool battleResOwner"):
        IMPL.index("if (result.Features.RaidEncounter && raidAdapter.ContractResolved && raidAdapter.DispelAuraId)")
    ]
    assert 'std::string(role) == "healer"' not in raid_brez
    assert "raidAdapter.BattleResurrectionPolicy" in raid_brez
    for token in (
        'targetPolicy == "tank_then_healer_then_dps"',
        'deadRole == "tank" ? 3 : deadRole == "healer" ? 2 : 1',
        "requestedByHealer ? 100 : pendingByHealer ? 90 : rolePriority",
        "uniqueBattleResSlots.size() == node.BattleResurrectionSlots.size()",
        "slot > 0 && slot <= Cohort().Config.RaidSize",
    ):
        assert token in IMPL


def test_controlled_aoe_counts_only_declared_targets_and_fails_closed_near_undeclared_hostiles():
    for token in (
        "uint32 declaredControlledAoeTargets = 0;",
        "bool undeclaredControlledAoeHostile = false;",
        "declared = std::find(raidAdapter.TargetEntries.begin()",
        "undeclaredControlledAoeHostile = true;",
        "++declaredControlledAoeTargets;",
        "!undeclaredControlledAoeHostile",
        "declaredControlledAoeTargets >= raidAdapter.ControlledAoeMinimumTargets",
        '? declaredControlledAoeTargets : result.Features.AddCount',
        "&profileAction, combatAddCount, controlledAoeReleased",
        "TryEnsureCombatTotems(*state, bot, target, forbidArea ? 1 : hostileCount)",
        "allowMultidot && !forbidArea",
        "magma->UnSummon();",
        "candidate->RemoveAura(44457, bot->GetGUID());",
        "spellInfo->IsAffectingArea()",
        "spellInfo->Effects[effectIndex].ChainTarget > 1",
        "declarative_area_damage_semantics_forbidden",
        "action.SuppressAreaDamage = forbidArea;",
        "raid_area_damage_contamination_fail_closed",
        "HandleCancelAuraOpcode(cancel)",
        "bot->RemoveDynObject(action.SpellId);",
        "state.SuppressedRaidAreaAutocasts.push_back",
        "creature->GetPetAutoSpellOnPos(index)",
        "pet->ToggleAutocast(spellInfo, false);",
        "charmInfo->ToggleCreatureAutocast(spellInfo, false);",
        "reconcileRaidAreaAutocasts(!controlledAoeReleased);",
        "reconcileRaidAreaAutocasts(false);",
        'raidAdapter.TargetControl == "controlled_aoe" && !controlledAoeReleased',
        "bot->InterruptSpell(CURRENT_CHANNELED_SPELL, false);",
    ):
        assert token in IMPL


def test_focus_fire_owns_target_and_cancels_every_wrong_attacker():
    focus_start = IMPL.index('raidAdapter.TargetControl == "focus_fire"')
    focus_end = IMPL.index('if (result.Features.RaidEncounter && raidAdapter.ContractResolved)\n    {', focus_start)
    focus = IMPL[focus_start:focus_end]
    for token in (
        "auto stopWrongFocusTarget = [focus](Unit* attacker)",
        "attacker->InterruptSpell(CURRENT_GENERIC_SPELL, false);",
        "attacker->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);",
        "attacker->InterruptSpell(CURRENT_CHANNELED_SPELL, false);",
        "stopWrongFocusTarget(bot);",
        "stopWrongFocusTarget(pet);",
        "stopWrongFocusTarget(controlled);",
        "state.TargetGuid = focus->GetGUID();",
        "if (!focus || current->m_targets.GetUnitTarget() != focus)",
    ):
        assert token in focus
    assert 'raidAdapter.TargetControl != "focus_fire"' in IMPL
    assert '(node.TargetControl != "focus_fire" || (!node.AllowMultidot && !node.AllowAreaDamage))' in IMPL
    assert "state.WasInCombat = true;" in IMPL


def test_platform_completion_requires_all_declared_destination_dimensions():
    for token in (
        "bool const declaredDestinationMap",
        "bool const declaredDestinationArea",
        "bool const declaredDestinationZ",
        "(!declaredDestinationMap",
        "(!declaredDestinationArea",
        "(!declaredDestinationZ || destinationZMatches)",
        'raidAdapter.PlatformPolicy != "altitude"',
        "|| destinationZMatches;",
        'raidAdapter.PlatformPolicy != "flying" || bot->IsFlying()',
    ):
        assert token in IMPL
    platform_start = IMPL.index("bool const platformPostcondition")
    platform_end = IMPL.index("bool const altitudePostcondition", platform_start)
    platform = IMPL[platform_start:platform_end]
    assert "|| (raidAdapter.PlatformDestinationMapId" not in platform
    assert "|| (raidAdapter.PlatformDestinationAreaId" not in platform


def test_phase1_jump_platform_altitude_and_flying_require_native_postconditions():
    for token in (
        'bot->GetMapId() == raidAdapter.PlatformDestinationMapId',
        'bot->GetAreaId() == raidAdapter.PlatformDestinationAreaId',
        'bot->GetPositionZ() >= raidAdapter.PlatformMinimumZ',
        'bot->GetPositionZ() <= raidAdapter.PlatformMaximumZ',
        'raidAdapter.PlatformPolicy != "flying" || bot->IsFlying()',
        '"raid_jump_pad_native_submitted"',
        '"raid_platform_native_transfer_complete"',
        '"raid_platform_native_regroup_complete"',
        'raidAdapter.PlatformPolicy != "ground"',
        'bot->GetExactDist2d(raidAnchors.ResolvedX, raidAnchors.ResolvedY)',
    ):
        assert token in IMPL
    assert 'node.InteractionKind != "jump_pad"' in IMPL
    assert 'node.MovementLink != "none" && node.MovementLink != "regroup"' in IMPL
    assert "&& jumpTransferResolved" in IMPL
    assert "state.LastRaidJumpPadEntrySubmitted == raidAdapter.JumpPadEntry" in IMPL
    assert "state.LastRaidJumpPadRouteGeneration == Party().ValidationRouteGeneration" in IMPL
    assert 'if (raidAdapter.InteractionKind == "jump_pad")' in IMPL


def test_generic_contract_has_explicit_soak_dispel_and_cooldown_assignments():
    cone = next(
        row["mechanic_contract"] for row in GENERIC_SMOKE["routes"]
        if row["mechanic_contract"]["formation_family"] == "cone"
    )
    assert cone["soak_minimum_count"] == len(cone["soak_roster_slots"])
    assert cone["dispel_owner_slot"] != cone["dispel_backup_slot"]
    assert cone["cooldown_trigger_spell_id"] > 0
    for token in (
        "raid_soak_wait_for_assigned_count", "raid_dispel_owner",
        "raid_dispel_backup", "raid_cooldown_schedule",
    ):
        assert token in IMPL


def test_runtime_records_live_identity_lockout_and_unique_leases():
    for token in (
        "raid.GroupGuid = group->GetGUID();",
        "raid.LeaderGuid = leader->GetGUID();",
        "raid.MapDifficulty",
        "raid.LockoutSaveId = bind->save->GetInstanceId();",
        "slot.LeaseOwned = LeaseOwnedByCurrentCohort(guid, slot.LeaseRoleSlot);",
        "raid.RosterComplete = raid.ActiveSize == raid.ExpectedSize;",
    ):
        assert token in IMPL


def test_permanent_roster_slots_and_exact_role_shapes_fail_closed():
    for token in (
        "std::string RosterSlotId",
        "std::string LeaseRoleSlot",
        "std::string ClassSpec",
        "std::string GearIdentity",
        "bool RosterCompositionValid",
    ):
        assert token in HEADER
    for token in (
        "lease.RoleSlot == roleSlot",
        "SelectNextRosterSlot()",
        'slot.RosterSlotId = "raid_tank_"',
        "raid.ExpectedSize == 10 ? 3 : 6",
        "raid.ExpectedSize == 10 ? 5 : 17",
        '"exact_raid_role_composition_mismatch"',
    ):
        assert token in IMPL


def test_native_ready_check_is_explicit_attempt_and_wipe_scoped():
    command = (ROOT / "src/server/scripts/Commands/cs_healerbot.cpp").read_text(encoding="utf-8")
    for token in (
        "RequestNativeRaidReadyCheckForCohort",
        "MSG_RAID_READY_CHECK",
        "HandleRaidReadyCheckOpcode(request);",
        "HandleRaidReadyCheckOpcode(response);",
        "NativeReadyCheckResponseCount",
        "NativeReadyCheckActionGeneration",
        "NativeReadyCheckActionAttemptId",
        "NativeReadyCheckActionWipeGeneration",
        "raid.NativeReadyCheckActionObserved = false;",
    ):
        assert token in HEADER or token in IMPL
    assert '{ "readycheck"' in command
    assert "HandleAutoReadyCheckCommand" in command


def test_status_diagnose_trace_and_evidence_expose_raid_identity():
    assert IMPL.count('\\\"raid_runtime\\\"') >= 5
    assert "++Cohort().Raid.EvidenceSequence;" in IMPL
    assert 'context << "{\\\"raid_runtime\\\":" << BuildRaidRuntimeJson()' in IMPL
    assert '\\\"strategy_id\\\"' in IMPL
    assert '\\\"assignment_generation\\\"' in IMPL


def test_cleanup_preserves_terminal_raid_identity_for_final_status_demux():
    assert "uint64 ProfileGeneration" in HEADER
    assert "std::string ProfileContentHash" in HEADER
    release_start = IMPL.index("void BotWorldPopulationMgr::ReleaseCohortLeases")
    release = IMPL[
        release_start:
        IMPL.index("bool BotWorldPopulationMgr::LeaseOwnedByCurrentCohort", release_start)
    ]
    assert "Cohort().Raid = RaidRuntime();" not in release
    stop = IMPL[
        IMPL.index("std::string BotWorldPopulationMgr::StopAutonomyForCohort"):
        IMPL.index("std::string BotWorldPopulationMgr::SelectRuntimeProfileForCohort")
    ]
    for token in (
        "uint64 const serverEpoch = Cohort().Raid.ServerEpoch;",
        "uint64 const attemptId = Cohort().Raid.AttemptId;",
        "Cohort().Raid.Active = false;",
        "Cohort().Raid.ActiveSize = 0;",
        "Cohort().Raid.AliveSize = 0;",
    ):
        assert token in stop
    assert "std::vector<uint32> Talents" in HEADER
    assert "std::vector<uint32> Glyphs" in HEADER
    assert "std::vector<RaidRosterItemIdentity> GearManifest" in HEADER
    roster_json = IMPL[
        IMPL.index("std::string BotWorldPopulationMgr::BuildRaidRuntimeJson"):
        IMPL.index("std::string BotWorldPopulationMgr::BuildRaidPositioningAnchorsJson")
    ]
    assert "ObjectAccessor::FindPlayer(slot.Guid)" not in roster_json
    assert "slot.Talents" in roster_json
    assert "slot.Glyphs" in roster_json
    assert "slot.GearManifest" in roster_json


def test_live_kill_sync_holds_low_targets_until_every_peer_reaches_floor():
    assert "lowestPct <= raidAdapter.KillSyncExecutionFloorPct && peerAboveExecutionFloor" in IMPL
    assert '"raid_kill_sync_execution_hold_low_target"' in IMPL
    assert 'result.Action = "raid_kill_sync_balance_high_target";' in IMPL
    assert "UnitHealthPct(highest) <= raidAdapter.KillSyncExecutionFloorPct" not in IMPL


def test_runtime_reconstructs_native_boss_wipe_reset_and_recovery_state():
    raid_struct = HEADER.index("struct RaidRuntime")
    cohort_struct = HEADER.index("struct CohortRuntime")
    runtime = HEADER[raid_struct:cohort_struct]
    for token in (
        "uint32 AliveSize",
        "uint64 WipeGeneration",
        "uint64 BossResetGeneration",
        "uint64 RecoveryGeneration",
        "bool EncounterInProgress",
        "bool ReadyCheckSatisfied",
        "bool NativeDeathObserved",
        "bool NativeReleaseObserved",
        "bool NativeResurrectionObserved",
        "bool NativeRunbackObserved",
        "bool NativeRecoveryEvidenceComplete",
        "std::vector<uint8> BossStates",
    ):
        assert token in runtime
    for token in (
        "instance->IsEncounterInProgress()",
        "instance->GetEncounterCount()",
        "instance->GetBossState(bossId)",
        'raid.WipeState = "wiped";',
        'raid.RecoveryState = "recovered_ready_check";',
        "++raid.BossResetGeneration;",
        "raid.ReadyCheckSatisfied = raid.RosterComplete",
        '\\\"boss_states\\\"',
    ):
        assert token in IMPL


def test_bwd_profile_pins_10n_and_world_defaults_are_documented():
    profiles = json.loads((ROOT / "dataset/bot_runtime_profiles/profiles.json").read_text(encoding="utf-8"))
    bwd = next(profile for profile in profiles["profiles"] if profile["name"] == "blackwing_descent_10n")
    assert bwd["raid_size"] == 10
    assert bwd["raid_difficulty"] == 0

    conf = (ROOT / "src/server/worldserver/worldserver.conf.dist").read_text(encoding="utf-8")
    assert "BotProgression.RaidSize = 10" in conf
    assert "BotProgression.RaidDifficulty = 0" in conf
