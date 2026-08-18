#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotAdmissionIdentityGenerated.h"
#include "Player.h"

#include <map>
#include <sstream>
#include <string>
#include <vector>

std::string BotWorldPopulationMgr::BuildRaidRuntimeJson(bool compactTelemetry) const
{
    RaidRuntime const& raid = Cohort().Raid;
    std::map<uint32, std::string> currentGearManifestSha256ByGuid;
    std::map<uint32, bool> currentGearMatchesAdmissionByGuid;
    bool allCurrentGearMatchesAdmission = !raid.AdmissionReceiptByGuid.empty()
        && raid.AdmissionReceiptByGuid.size() == raid.ExpectedSize;
    for (auto const& [guid, receipt] : raid.AdmissionReceiptByGuid)
    {
        WorldBotState const* state = nullptr;
        for (WorldBotState const& candidate : Party().Bots)
            if (candidate.Guid.GetCounter() == guid)
            {
                state = &candidate;
                break;
            }
        std::vector<RaidRosterItemIdentity> currentManifest;
        std::string currentManifestSha256;
        std::string expectedGearProfileId;
        std::string expectedManifestSha256;
        Player const* member = state ? GetLoadedBot(*state) : nullptr;
        bool const matches = member
            && ResolveExpectedBotGearIdentity(receipt.ClassSpec,
                expectedGearProfileId, expectedManifestSha256)
            && ObserveEquippedGearIdentity(member,
                currentManifest, currentManifestSha256)
            && receipt.GearProfileId == expectedGearProfileId
            && receipt.GearManifestSha256 == expectedManifestSha256
            && currentManifestSha256 == receipt.GearManifestSha256
            && EquippedGearManifestsEqual(currentManifest, receipt.GearManifest);
        currentGearManifestSha256ByGuid.emplace(guid, currentManifestSha256);
        currentGearMatchesAdmissionByGuid.emplace(guid, matches);
        allCurrentGearMatchesAdmission = allCurrentGearMatchesAdmission && matches;
    }
    std::ostringstream json;
    json << "{\"active\":" << (raid.Active ? "true" : "false")
         << ",\"instance_kind\":\"" << (raid.RaidInstance ? "raid" : "dungeon") << "\""
         << ",\"admission_phase\":\"" << (Cohort().ValidationAdmission == ValidationAdmissionPhase::Active
            ? "active" : (Cohort().ValidationAdmission == ValidationAdmissionPhase::Terminal ? "terminal" : "provisioning")) << "\""
         << ",\"server_provisioning_complete\":" << (raid.ServerProvisioningComplete ? "true" : "false")
         << ",\"bot_actions_enabled\":" << (raid.BotActionsEnabled ? "true" : "false")
         << ",\"provisioned_member_count\":" << raid.ProvisionedMemberCount
         << ",\"group_guid\":" << raid.GroupGuid.GetRawValue()
         << ",\"leader_guid\":" << raid.LeaderGuid.GetRawValue()
         << ",\"expected_size\":" << raid.ExpectedSize
         << ",\"active_size\":" << raid.ActiveSize
         << ",\"alive_size\":" << raid.AliveSize
         << ",\"roster_complete\":" << (raid.RosterComplete ? "true" : "false")
         << ",\"expected_difficulty\":" << uint32(raid.ExpectedDifficulty)
         << ",\"group_difficulty\":" << uint32(raid.GroupDifficulty)
         << ",\"map_difficulty\":" << raid.MapDifficulty
         << ",\"difficulty_member_count\":" << raid.DifficultyMemberCount
         << ",\"difficulty_matching_member_count\":" << raid.DifficultyMatchingMemberCount
         << ",\"difficulty_readback_complete\":" << (raid.DifficultyReadbackComplete ? "true" : "false")
         << ",\"difficulty_matches\":" << (raid.DifficultyMatches ? "true" : "false")
         << ",\"map_id\":" << raid.MapId
         << ",\"instance_id\":" << raid.InstanceId
         << ",\"lockout_save_id\":" << raid.LockoutSaveId
         << ",\"server_epoch\":" << raid.ServerEpoch
         << ",\"attempt_id\":" << raid.AttemptId
         << ",\"profile_generation\":" << raid.ProfileGeneration
         << ",\"profile_content_hash\":\"" << JsonEscape(raid.ProfileContentHash) << "\""
         << ",\"assignment_generation\":" << raid.AssignmentGeneration
         << ",\"evidence_sequence\":" << raid.EvidenceSequence
         << ",\"admission_receipt\":{\"attempt_id\":" << raid.AdmissionAttemptId
         << ",\"server_epoch\":" << raid.ServerEpoch
         << ",\"group_guid\":" << raid.GroupGuid.GetRawValue()
         << ",\"instance_id\":" << raid.InstanceId
         << ",\"committed_at_ms\":" << raid.AdmissionCommittedAtMs
         << ",\"bot_actions_enabled_at_commit\":" << (raid.AdmissionActionGateEnabled ? "true" : "false")
         << ",\"scenario_id\":\"" << JsonEscape(raid.AdmissionScenarioId) << "\""
         << ",\"runtime_profile\":\"" << JsonEscape(raid.AdmissionRuntimeProfile) << "\""
         << ",\"identity_catalog_source_sha256\":\""
         << BotAdmissionIdentityGenerated::SourceContentSha256 << "\""
         << ",\"route_manifest_sha256\":\"" << JsonEscape(raid.AdmissionRouteManifestSha256) << "\""
         << ",\"recovery_entrance_area_trigger_id\":" << raid.AdmissionRecoveryEntranceAreaTriggerId
         << ",\"recovery_entrance_source_map_id\":" << raid.AdmissionRecoveryEntranceSourceMapId
         << ",\"recovery_entrance_target_map_id\":" << raid.AdmissionRecoveryEntranceTargetMapId
         << ",\"entrance_map_id\":" << raid.AdmissionEntranceMapId
         << ",\"entrance_x\":" << raid.AdmissionEntranceX
         << ",\"entrance_y\":" << raid.AdmissionEntranceY
         << ",\"entrance_z\":" << raid.AdmissionEntranceZ
         << ",\"entrance_o\":" << raid.AdmissionEntranceO
         << ",\"profile_generation\":" << raid.ProfileGeneration
         << ",\"profile_content_hash\":\"" << JsonEscape(raid.ProfileContentHash) << "\""
         << ",\"leader_guid\":" << raid.LeaderGuid.GetRawValue()
         << ",\"all_current_gear_matches_admission\":"
         << (allCurrentGearMatchesAdmission ? "true" : "false")
         << ",\"members\":[";
    bool firstAdmissionMember = true;
    for (auto const& [guid, member] : raid.AdmissionReceiptByGuid)
    {
        if (!firstAdmissionMember)
            json << ',';
        firstAdmissionMember = false;
        json << "{\"guid\":" << guid
             << ",\"group_guid\":" << member.GroupGuid.GetRawValue()
             << ",\"leader_guid\":" << member.LeaderGuid.GetRawValue()
             << ",\"roster_slot_id\":\"" << JsonEscape(member.RosterSlotId) << "\""
             << ",\"role\":\"" << JsonEscape(member.Role) << "\""
             << ",\"class_spec\":\"" << JsonEscape(member.ClassSpec) << "\""
             << ",\"class_id\":" << uint32(member.ClassId)
             << ",\"active_spec_index\":" << uint32(member.ActiveSpecIndex)
             << ",\"primary_talent_tree_id\":" << member.PrimaryTalentTreeId
             << ",\"active_talent_count\":" << member.ActiveTalentCount
             << ",\"active_talent_spell_ids\":[";
        for (size_t index = 0; index < member.ActiveTalentSpellIds.size(); ++index)
        {
            if (index)
                json << ',';
            json << member.ActiveTalentSpellIds[index];
        }
        json << ']'
             << ",\"pet_identity_present\":" << (member.PetIdentityPresent ? "true" : "false")
             << ",\"pet_id\":" << member.PetId
             << ",\"pet_entry\":" << member.PetEntry
             << ",\"pet_spell_count\":" << member.PetSpellCount
             << ",\"pet_spellbook\":[";
        for (size_t index = 0; index < member.PetSpellbook.size(); ++index)
        {
            if (index)
                json << ',';
            json << "{\"spell_id\":" << member.PetSpellbook[index].first
                 << ",\"active\":" << uint32(member.PetSpellbook[index].second) << '}';
        }
        json << ']'
             << ",\"pet_spellbook_sha256\":\"" << JsonEscape(member.PetSpellbookSha256) << "\""
             << ",\"gear_profile_id\":\"" << JsonEscape(member.GearProfileId) << "\""
             << ",\"gear_item_count\":" << member.GearItemCount
             << ",\"gear_manifest\":[";
        for (size_t itemIndex = 0; itemIndex < member.GearManifest.size(); ++itemIndex)
        {
            if (itemIndex)
                json << ',';
            RaidRosterItemIdentity const& item = member.GearManifest[itemIndex];
            json << "{\"slot\":" << uint32(item.Slot)
                 << ",\"item_id\":" << item.Entry
                 << ",\"enchant_id\":" << item.EnchantId
                 << ",\"reforge_id\":" << item.ReforgeId
                 << ",\"gem_item_ids\":[";
            for (size_t gemIndex = 0; gemIndex < item.GemItemIds.size(); ++gemIndex)
            {
                if (gemIndex)
                    json << ',';
                json << item.GemItemIds[gemIndex];
            }
            json << "]}";
        }
        json << ']'
             << ",\"gear_manifest_sha256\":\""
             << JsonEscape(member.GearManifestSha256) << "\""
             << ",\"current_gear_manifest_sha256\":\""
             << JsonEscape(currentGearManifestSha256ByGuid.at(guid)) << "\""
             << ",\"gear_identity_current_matches_admission\":"
             << (currentGearMatchesAdmissionByGuid.at(guid) ? "true" : "false")
             << ",\"map_id\":" << member.MapId
             << ",\"instance_id\":" << member.InstanceId
             << ",\"expected_difficulty\":" << uint32(member.ExpectedDifficulty)
             << ",\"player_difficulty\":" << uint32(member.PlayerDifficulty)
             << ",\"map_difficulty\":" << member.MapDifficulty
             << ",\"spawn_x\":" << member.SpawnX
             << ",\"spawn_y\":" << member.SpawnY
             << ",\"spawn_z\":" << member.SpawnZ
             << ",\"spawn_o\":" << member.SpawnO
             << ",\"server_provisioned\":" << (member.ServerProvisioned ? "true" : "false")
             << ",\"initial_baseline_normalized\":"
             << (member.InitialBaselineNormalized ? "true" : "false")
             << ",\"initial_alive_state_verified\":"
             << (member.InitialAliveStateVerified ? "true" : "false") << '}';
    }
    json << "]}";

    if (compactTelemetry)
    {
        json << ",\"wipe_generation\":" << raid.WipeGeneration
             << ",\"boss_reset_generation\":" << raid.BossResetGeneration
             << ",\"native_recovery_hold_active\":" << (raid.NativeRecoveryHoldActive ? "true" : "false")
             << ",\"native_recovery_route_generation\":" << raid.NativeRecoveryRouteGeneration
             << ",\"native_recovery_node_id\":\"" << JsonEscape(raid.NativeRecoveryNodeId) << "\""
             << ",\"native_hostile_activity_active\":" << (raid.NativeHostileActivityActive ? "true" : "false")
             << ",\"native_hostile_inactivity_observed\":" << (raid.NativeHostileInactivityObserved ? "true" : "false")
             << ",\"native_hostile_reset_generation\":" << raid.NativeHostileResetGeneration
             << ",\"native_hostile_observation_attempt_id\":" << raid.NativeHostileObservationAttemptId
             << ",\"native_hostile_observation_route_generation\":" << raid.NativeHostileObservationRouteGeneration
             << ",\"native_hostile_observation_node_id\":\"" << JsonEscape(raid.NativeHostileObservationNodeId) << "\""
             << ",\"recovery_generation\":" << raid.RecoveryGeneration
             << ",\"encounter_in_progress\":" << (raid.EncounterInProgress ? "true" : "false")
             << ",\"strategy_id\":\"" << JsonEscape(raid.StrategyId) << "\""
             << ",\"route_progress\":{\"generation\":" << Party().ValidationRouteGeneration
             << ",\"node_index\":" << Party().ValidationRouteManifestIndex << "}"
             << ",\"strategy_transition\":{\"from_strategy\":\""
             << JsonEscape(raid.PreviousStrategyId) << "\",\"to_strategy\":\""
             << JsonEscape(raid.StrategyId) << "\",\"advanced\":"
             << (raid.StrategyTransitionRouteGeneration == Party().ValidationRouteGeneration
                 && !raid.PreviousStrategyId.empty() ? "true" : "false") << "}"
             << ",\"encounter_phase\":\"" << JsonEscape(raid.EncounterPhase) << "\""
             << ",\"wipe_state\":\"" << JsonEscape(raid.WipeState) << "\""
             << ",\"recovery_state\":\"" << JsonEscape(raid.RecoveryState) << "\""
             << ",\"boss_states\":[";
        for (size_t bossId = 0; bossId < raid.BossStates.size(); ++bossId)
        {
            if (bossId)
                json << ',';
            json << uint32(raid.BossStates[bossId]);
        }
        json << "],\"roster\":[";
        bool firstCompactRoster = true;
        for (auto const& [guid, slot] : raid.RosterByGuid)
        {
            if (!firstCompactRoster)
                json << ',';
            firstCompactRoster = false;
            json << "{\"roster_slot_id\":\"" << JsonEscape(slot.RosterSlotId)
                 << "\",\"lease_role_slot\":\"" << JsonEscape(slot.LeaseRoleSlot)
                 << "\",\"slot\":" << slot.SlotIndex
                 << ",\"guid\":" << guid
                 << ",\"subgroup\":" << uint32(slot.SubGroup)
                 << ",\"role\":\"" << JsonEscape(slot.Role)
                 << "\",\"class_id\":" << uint32(slot.ClassId)
                 << ",\"class_spec\":\"" << JsonEscape(slot.ClassSpec)
                 << "\",\"gear_identity\":\"" << JsonEscape(slot.GearIdentity)
                 << "\",\"account_id\":" << slot.AccountId
                 << ",\"account\":\"" << JsonEscape(slot.AccountName)
                 << "\",\"name\":\"" << JsonEscape(slot.CharacterName)
                 << "\",\"talents\":[";
            bool firstCompactTalent = true;
            for (uint32 spellId : slot.Talents)
            {
                if (!firstCompactTalent)
                    json << ',';
                firstCompactTalent = false;
                json << spellId;
            }
            json << "],\"glyphs\":[";
            bool firstCompactGlyph = true;
            for (uint32 glyph : slot.Glyphs)
            {
                if (!firstCompactGlyph)
                    json << ',';
                firstCompactGlyph = false;
                json << glyph;
            }
            json << "],\"gear_identity_manifest\":{\"items\":[";
            bool firstCompactItem = true;
            for (RaidRosterItemIdentity const& item : slot.GearManifest)
            {
                if (!firstCompactItem)
                    json << ',';
                firstCompactItem = false;
                json << "{\"slot\":" << uint32(item.Slot)
                     << ",\"guid\":" << item.Guid
                     << ",\"entry\":" << item.Entry
                     << ",\"enchant_id\":" << item.EnchantId
                     << ",\"gem_item_ids\":[";
                for (size_t gemIndex = 0; gemIndex < item.GemItemIds.size(); ++gemIndex)
                {
                    if (gemIndex)
                        json << ',';
                    json << item.GemItemIds[gemIndex];
                }
                json << "],\"reforge_id\":" << item.ReforgeId << '}';
            }
            json << "]},\"active\":" << (slot.Active ? "true" : "false")
                 << ",\"lease_owned\":" << (slot.LeaseOwned ? "true" : "false") << "}";
        }
        json << "]}";
        return json.str();
    }

    json
         << ",\"wipe_generation\":" << raid.WipeGeneration
         << ",\"boss_reset_generation\":" << raid.BossResetGeneration
         << ",\"boss_reset_generation_at_wipe\":" << raid.BossResetGenerationAtWipe
         << ",\"native_recovery_hold_active\":" << (raid.NativeRecoveryHoldActive ? "true" : "false")
         << ",\"native_recovery_route_generation\":" << raid.NativeRecoveryRouteGeneration
         << ",\"native_recovery_node_id\":\"" << JsonEscape(raid.NativeRecoveryNodeId) << "\""
         << ",\"native_hostile_activity_active\":" << (raid.NativeHostileActivityActive ? "true" : "false")
         << ",\"native_hostile_activity_seen_at_wipe\":" << (raid.NativeHostileActivitySeenAtWipe ? "true" : "false")
         << ",\"native_hostile_inactivity_observed\":" << (raid.NativeHostileInactivityObserved ? "true" : "false")
         << ",\"native_hostile_reset_generation\":" << raid.NativeHostileResetGeneration
         << ",\"native_hostile_reset_generation_at_wipe\":" << raid.NativeHostileResetGenerationAtWipe
         << ",\"native_hostile_observation_attempt_id\":" << raid.NativeHostileObservationAttemptId
         << ",\"native_hostile_observation_route_generation\":" << raid.NativeHostileObservationRouteGeneration
         << ",\"native_hostile_observation_node_id\":\"" << JsonEscape(raid.NativeHostileObservationNodeId) << "\""
         << ",\"native_hostile_activity_entry\":" << raid.NativeHostileActivityEntry
         << ",\"native_hostile_activity_guid\":" << raid.NativeHostileActivityGuid.GetRawValue()
         << ",\"native_hostile_activity_reason\":\"" << JsonEscape(raid.NativeHostileActivityReason) << "\""
         << ",\"recovery_generation\":" << raid.RecoveryGeneration
         << ",\"encounter_in_progress\":" << (raid.EncounterInProgress ? "true" : "false")
         << ",\"ready_check_satisfied\":" << (raid.ReadyCheckSatisfied ? "true" : "false")
         << ",\"roster_composition_valid\":" << (raid.RosterCompositionValid ? "true" : "false")
         << ",\"unique_leases\":" << (raid.UniqueLeases ? "true" : "false")
         << ",\"native_recovery\":{\"death_observed\":" << (raid.NativeDeathObserved ? "true" : "false")
         << ",\"corpse_observed\":" << (raid.NativeCorpseObserved ? "true" : "false")
         << ",\"release_observed\":" << (raid.NativeReleaseObserved ? "true" : "false")
         << ",\"resurrection_observed\":" << (raid.NativeResurrectionObserved ? "true" : "false")
         << ",\"runback_observed\":" << (raid.NativeRunbackObserved ? "true" : "false")
         << ",\"ready_check_action_observed\":" << (raid.NativeReadyCheckActionObserved ? "true" : "false")
         << ",\"ready_check_action_generation\":" << raid.NativeReadyCheckActionGeneration
         << ",\"ready_check_response_count\":" << raid.NativeReadyCheckResponseCount
         << ",\"ready_check_action_attempt_id\":" << raid.NativeReadyCheckActionAttemptId
         << ",\"ready_check_action_wipe_generation\":" << raid.NativeReadyCheckActionWipeGeneration
         << ",\"ready_check_assignment_generation\":" << raid.NativeReadyCheckAssignmentGeneration
         << ",\"ready_check_action_evidence_sequence\":" << raid.NativeReadyCheckActionEvidenceSequence
         << ",\"recovery_wipe_generation\":" << raid.WipeGeneration
         << ",\"evidence_complete\":" << (raid.NativeRecoveryEvidenceComplete ? "true" : "false")
         << ",\"members\":[";
    bool firstRecoveryMember = true;
    for (auto const& [guid, signal] : raid.NativeSignalsByGuid)
    {
        if (!firstRecoveryMember)
            json << ',';
        firstRecoveryMember = false;
        json << "{\"guid\":" << guid
             << ",\"wipe_generation\":" << signal.WipeGeneration
             << ",\"death_sequence\":" << signal.DeathSequence
             << ",\"corpse_sequence\":" << signal.CorpseSequence
             << ",\"release_sequence\":" << signal.ReleaseSequence
             << ",\"runback_sequence\":" << signal.RunbackSequence
             << ",\"reentry_sequence\":" << signal.ReentrySequence
             << ",\"resurrection_sequence\":" << signal.ResurrectionSequence << "}";
    }
    json << "]}"
         << ",\"strategy_id\":\"" << JsonEscape(raid.StrategyId) << "\""
         << ",\"route_progress\":{\"generation\":" << Party().ValidationRouteGeneration
         << ",\"node_index\":" << Party().ValidationRouteManifestIndex << "}"
         << ",\"drudge_threat_seed\":{\"attempt_id\":"
         << Party().ValidationRouteDrudgeThreatSeedAttemptId
         << ",\"wipe_generation\":" << Party().ValidationRouteDrudgeThreatSeedWipeGeneration
         << ",\"route_generation\":" << Party().ValidationRouteDrudgeThreatSeedRouteGeneration
         << ",\"closed\":" << (Party().ValidationRouteDrudgeThreatSeedClosed ? "true" : "false")
         << ",\"complete\":" << (Party().ValidationRouteDrudgeThreatSeedComplete ? "true" : "false")
         << ",\"failure\":" << (Party().ValidationRouteDrudgeThreatSeedFailure ? "true" : "false")
         << ",\"roster_guids\":[";
    bool firstThreatSeedGuid = true;
    for (uint32 guid : Party().ValidationRouteDrudgeThreatSeedRosterGuids)
    {
        if (!firstThreatSeedGuid)
            json << ',';
        firstThreatSeedGuid = false;
        json << guid;
    }
    json << "],\"observations\":[";
    bool firstThreatSeedObservation = true;
    for (ValidationRouteDrudgeThreatSeedEvidence const& evidence :
        Party().ValidationRouteDrudgeThreatSeedEvidenceRows)
    {
        if (!firstThreatSeedObservation)
            json << ',';
        firstThreatSeedObservation = false;
        json << "{\"sequence\":" << evidence.Sequence
             << ",\"attempt_id\":" << evidence.AttemptId
             << ",\"wipe_generation\":" << evidence.WipeGeneration
             << ",\"route_generation\":" << evidence.RouteGeneration
             << ",\"observed_at_ms\":" << evidence.ObservedAtMs
             << ",\"member_guid\":" << evidence.MemberGuid
             << ",\"member_slot\":" << evidence.MemberSlot
             << ",\"member_lane\":" << evidence.MemberLane
             << ",\"source_spawn_id\":" << evidence.SourceSpawnId
             << ",\"source_guid\":" << evidence.SourceGuid
             << ",\"source_lane\":" << evidence.SourceLane
             << ",\"spell_id\":" << evidence.SpellId
             << ",\"selected_distance\":" << evidence.SelectedDistance
             << ",\"min_range\":" << evidence.MinRange
             << ",\"max_range\":" << evidence.MaxRange
             << ",\"position_safe\":" << (evidence.PositionSafe ? "true" : "false")
             << ",\"line_of_sight\":" << (evidence.LineOfSight ? "true" : "false")
             << ",\"in_range\":" << (evidence.InRange ? "true" : "false")
             << ",\"profile_action_valid\":" << (evidence.ProfileActionValid ? "true" : "false")
             << ",\"action_succeeded\":" << (evidence.ActionSucceeded ? "true" : "false")
             << ",\"selected_offense_unsuppressed\":"
             << (evidence.SelectedOffenseUnsuppressed ? "true" : "false")
             << ",\"other_offense_suppressed\":"
             << (evidence.OtherOffenseSuppressed ? "true" : "false")
             << ",\"action_debug_name\":\"" << JsonEscape(evidence.ActionDebugName)
             << "\",\"action_result\":\"" << JsonEscape(evidence.ActionResult) << "\"}";
    }
    json << "]}"
         << ",\"drudge_charge\":{\"generation\":" << Party().ValidationRouteDrudgeChargeGeneration
         << ",\"landed_generation\":" << Party().ValidationRouteDrudgeChargeLandedGeneration
         << ",\"evidence_attempt_id\":" << Party().ValidationRouteDrudgeEvidenceAttemptId
         << ",\"evidence_wipe_generation\":" << Party().ValidationRouteDrudgeEvidenceWipeGeneration
         << ",\"evidence_route_generation\":" << Party().ValidationRouteDrudgeEvidenceRouteGeneration
         << ",\"prepared_count\":" << Party().ValidationRouteDrudgeChargePreparedCount
         << ",\"delivered_count\":" << Party().ValidationRouteDrudgeChargeDeliveredCount
         << ",\"queue_overflow\":" << (Party().ValidationRouteDrudgeChargeQueueOverflow ? "true" : "false")
         << ",\"sources\":[";
    bool firstChargeSource = true;
    for (uint32 spawnId : Party().ValidationRouteDrudgeEvidenceSourceSpawnIds)
    {
        if (!firstChargeSource)
            json << ',';
        firstChargeSource = false;
        auto delivered = Party().ValidationRouteDrudgeDeliveredBySpawn.find(spawnId);
        auto intervals = Party().ValidationRouteDrudgeValidIntervalsBySpawn.find(spawnId);
        json << "{\"spawn_id\":" << spawnId
             << ",\"delivered_count\":"
             << (delivered == Party().ValidationRouteDrudgeDeliveredBySpawn.end() ? 0 : delivered->second)
             << ",\"valid_interval_count\":"
             << (intervals == Party().ValidationRouteDrudgeValidIntervalsBySpawn.end() ? 0 : intervals->second)
             << '}';
    }
    json << "]"
         << ",\"reseparated_roster_guids\":[";
    bool firstReseparatedGuid = true;
    for (uint32 guid : Party().ValidationRouteDrudgeReseparatedRosterGuids)
    {
        if (!firstReseparatedGuid)
            json << ',';
        firstReseparatedGuid = false;
        json << guid;
    }
    json << "]"
         << ",\"ownership_roster_guids\":[";
    bool firstOwnershipGuid = true;
    for (uint32 guid : Party().ValidationRouteDrudgeOwnershipRosterGuids)
    {
        if (!firstOwnershipGuid)
            json << ',';
        firstOwnershipGuid = false;
        json << guid;
    }
    json << "]"
         << ",\"taunt_roster_guids\":[";
    bool firstTauntGuid = true;
    for (uint32 guid : Party().ValidationRouteDrudgeTauntRosterGuids)
    {
        if (!firstTauntGuid)
            json << ',';
        firstTauntGuid = false;
        json << guid;
    }
    json << "]"
         << ",\"health_sync_roster_guids\":[";
    bool firstHealthSyncGuid = true;
    for (uint32 guid : Party().ValidationRouteDrudgeHealthSyncRosterGuids)
    {
        if (!firstHealthSyncGuid)
            json << ',';
        firstHealthSyncGuid = false;
        json << guid;
    }
    json << "]"
         << ",\"health_sync_evidence_attempt_id\":" << Party().ValidationRouteDrudgeHealthSyncEvidenceAttemptId
         << ",\"health_sync_evidence_wipe_generation\":" << Party().ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration
         << ",\"health_sync_evidence_route_generation\":" << Party().ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration
         << ",\"health_sync_evaluated_roster_guids\":[";
    bool firstHealthSyncEvaluatedGuid = true;
    for (uint32 guid : Party().ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids)
    {
        if (!firstHealthSyncEvaluatedGuid)
            json << ',';
        firstHealthSyncEvaluatedGuid = false;
        json << guid;
    }
    json << "]"
         << ",\"health_sync_hold_source_spawn_id\":"
         << Party().ValidationRouteDrudgeHealthSyncHoldSourceSpawnId
         << ",\"health_sync_hold_tank_guid\":"
         << Party().ValidationRouteDrudgeHealthSyncHoldTankGuid
         << ",\"health_sync_hold_lower_pct\":"
         << Party().ValidationRouteDrudgeHealthSyncHoldLowerPct
         << ",\"health_sync_hold_peer_pct\":"
         << Party().ValidationRouteDrudgeHealthSyncHoldPeerPct
         << ",\"health_sync_hold_lower_alive\":"
         << (Party().ValidationRouteDrudgeHealthSyncHoldLowerAlive ? "true" : "false")
         << ",\"health_sync_hold_peer_alive\":"
         << (Party().ValidationRouteDrudgeHealthSyncHoldPeerAlive ? "true" : "false")
         << ",\"death_attempt_id\":" << Party().ValidationRouteDrudgeDeathAttemptId
         << ",\"death_wipe_generation\":" << Party().ValidationRouteDrudgeDeathWipeGeneration
         << ",\"death_route_generation\":" << Party().ValidationRouteDrudgeDeathRouteGeneration
         << ",\"death_source_spawn_id\":" << Party().ValidationRouteDrudgeDeathSourceSpawnId
         << ",\"death_source_guid\":" << Party().ValidationRouteDrudgeDeathSourceGuid
         << ",\"survivor_source_spawn_id\":" << Party().ValidationRouteDrudgeSurvivorSourceSpawnId
         << ",\"survivor_source_guid\":" << Party().ValidationRouteDrudgeSurvivorSourceGuid
         << ",\"death_evidence_sequence\":" << Party().ValidationRouteDrudgeDeathEvidenceSequence
         << ",\"rage_wait_evidence_sequence\":" << Party().ValidationRouteDrudgeRageWaitEvidenceSequence
         << ",\"rage_aura_evidence_sequence\":" << Party().ValidationRouteDrudgeRageAuraEvidenceSequence
         << ",\"profile_action_roster_guids\":[";
    bool firstProfileActionGuid = true;
    for (uint32 guid : Party().ValidationRouteDrudgeProfileActionRosterGuids)
    {
        if (!firstProfileActionGuid)
            json << ',';
        firstProfileActionGuid = false;
        json << guid;
    }
    json << "]"
         << ",\"observations\":[";
    bool firstChargeObservation = true;
    for (ValidationRouteDrudgeChargeObservation const& observation :
        Party().ValidationRouteDrudgeChargeObservations)
    {
        if (!firstChargeObservation)
            json << ',';
        firstChargeObservation = false;
        json << "{\"sequence\":" << observation.Sequence
             << ",\"attempt_id\":" << observation.AttemptId
             << ",\"wipe_generation\":" << observation.WipeGeneration
             << ",\"route_generation\":" << observation.RouteGeneration
             << ",\"observed_at_ms\":" << observation.ObservedAtMs
             << ",\"observed_interval_ms\":" << observation.ObservedIntervalMs
             << ",\"source_guid\":" << observation.SourceGuid.GetCounter()
             << ",\"source_spawn_id\":" << observation.SourceSpawnId
             << ",\"target_guid\":" << observation.TargetGuid.GetCounter()
             << ",\"target_raw_guid\":" << observation.TargetRawGuid
             << ",\"selected_distance\":" << observation.SelectedDistance
             << ",\"source_combat_reach\":" << observation.SourceCombatReach
             << ",\"target_combat_reach\":" << observation.TargetCombatReach
             << ",\"same_map\":" << (observation.SameMap ? "true" : "false")
             << ",\"same_phase\":" << (observation.SamePhase ? "true" : "false")
             << ",\"range_valid\":" << (observation.RangeValid ? "true" : "false")
             << ",\"interval_valid\":" << (observation.IntervalValid ? "true" : "false")
             << ",\"landed\":" << (observation.Landed ? "true" : "false")
             << ",\"reseparation_recorded\":" << (observation.ReseparationRecorded ? "true" : "false")
             << ",\"native_threat_candidates\":[";
        bool firstThreatCandidate = true;
        for (ValidationRouteDrudgeThreatCandidateEvidence const& candidate :
            observation.NativeThreatCandidates)
        {
            if (!firstThreatCandidate)
                json << ',';
            firstThreatCandidate = false;
            json << "{\"guid\":" << candidate.Guid
                 << ",\"raw_guid\":" << candidate.RawGuid
                 << ",\"slot\":" << candidate.Slot
                 << ",\"lane\":" << candidate.Lane
                 << ",\"threat\":" << candidate.Threat
                 << ",\"distance\":" << candidate.Distance
                 << ",\"source_combat_reach\":" << candidate.SourceCombatReach
                 << ",\"candidate_combat_reach\":" << candidate.CandidateCombatReach
                 << ",\"is_player\":" << (candidate.IsPlayer ? "true" : "false")
                 << ",\"alive\":" << (candidate.Alive ? "true" : "false")
                 << ",\"same_map\":" << (candidate.SameMap ? "true" : "false")
                 << ",\"same_phase\":" << (candidate.SamePhase ? "true" : "false")
                 << ",\"available\":" << (candidate.Available ? "true" : "false")
                 << ",\"line_of_sight\":" << (candidate.LineOfSight ? "true" : "false")
                 << ",\"in_range\":" << (candidate.InRange ? "true" : "false")
                 << ",\"native_combat_range\":" << (candidate.NativeCombatRange ? "true" : "false")
                 << ",\"cross_lane\":" << (candidate.CrossLane ? "true" : "false")
                 << ",\"native_selector_eligible\":" << (candidate.NativeSelectorEligible ? "true" : "false")
                 << ",\"tactic_cross_lane_eligible\":" << (candidate.TacticCrossLaneEligible ? "true" : "false")
                 << ",\"role\":\"" << JsonEscape(candidate.Role) << "\"}";
        }
        json << "]"
             << ",\"native_threat_candidates_count\":" << observation.NativeThreatCandidatesCount
             << ",\"native_threat_candidates_complete\":"
             << (observation.NativeThreatCandidatesComplete ? "true" : "false")
             << ",\"native_threat_candidates_truncated\":"
             << (observation.NativeThreatCandidatesTruncated ? "true" : "false")
             << ",\"geometry\":{\"home0_x\":" << observation.Home0X
             << ",\"home0_y\":" << observation.Home0Y
             << ",\"home1_x\":" << observation.Home1X
             << ",\"home1_y\":" << observation.Home1Y
             << ",\"midpoint_x\":" << observation.MidpointX
             << ",\"midpoint_y\":" << observation.MidpointY
             << ",\"axis_x\":" << observation.AxisX
             << ",\"axis_y\":" << observation.AxisY
             << ",\"lane_separation\":" << observation.LaneSeparation
             << ",\"minimum_distance\":" << observation.MinimumDistance
             << ",\"navigation_margin\":" << observation.NavigationMargin
             << ",\"source0_x\":" << observation.Source0X
             << ",\"source0_y\":" << observation.Source0Y
             << ",\"source0_projection\":" << observation.Source0Projection
             << ",\"source0_health_pct\":" << observation.Source0HealthPct
             << ",\"source0_lane_side_valid\":" << (observation.Source0LaneSideValid ? "true" : "false")
             << ",\"source1_x\":" << observation.Source1X
             << ",\"source1_y\":" << observation.Source1Y
             << ",\"source1_projection\":" << observation.Source1Projection
             << ",\"source1_health_pct\":" << observation.Source1HealthPct
             << ",\"source1_lane_side_valid\":" << (observation.Source1LaneSideValid ? "true" : "false")
             << ",\"source0_victim_guid\":" << observation.Source0VictimGuid
             << ",\"source1_victim_guid\":" << observation.Source1VictimGuid
             << ",\"source0_alive\":" << (observation.Source0Alive ? "true" : "false")
             << ",\"source1_alive\":" << (observation.Source1Alive ? "true" : "false")
             << ",\"source_separation\":" << observation.SourceSeparation
             << ",\"minimum_source_separation\":" << observation.MinimumSourceSeparation
             << ",\"lane_tank_x\":" << observation.LaneTankX
             << ",\"lane_tank_y\":" << observation.LaneTankY
             << ",\"lane_tank_guid\":" << observation.LaneTankGuid
             << ",\"lane_tank_slot\":" << observation.LaneTankSlot
             << ",\"lane_tank_projection\":" << observation.LaneTankProjection
             << ",\"lane_tank_source_distance\":" << observation.LaneTankSourceDistance
             << ",\"other_tank_x\":" << observation.OtherTankX
             << ",\"other_tank_y\":" << observation.OtherTankY
             << ",\"other_tank_guid\":" << observation.OtherTankGuid
             << ",\"other_tank_slot\":" << observation.OtherTankSlot
             << ",\"other_tank_projection\":" << observation.OtherTankProjection
             << ",\"other_tank_source_distance\":" << observation.OtherTankSourceDistance
             << ",\"minimum_member_spacing\":" << observation.MinimumMemberSpacing
             << ",\"arrival_tolerance\":" << observation.ArrivalTolerance
             << ",\"tank_arrival_tolerance\":" << observation.TankArrivalTolerance
             << ",\"tank0_x\":" << observation.Tank0X
             << ",\"tank0_y\":" << observation.Tank0Y
             << ",\"tank0_guid\":" << observation.Tank0Guid
             << ",\"tank0_slot\":" << observation.Tank0Slot
             << ",\"tank0_projection\":" << observation.Tank0Projection
             << ",\"tank0_source_distance\":" << observation.Tank0SourceDistance
             << ",\"tank1_x\":" << observation.Tank1X
             << ",\"tank1_y\":" << observation.Tank1Y
             << ",\"tank1_guid\":" << observation.Tank1Guid
             << ",\"tank1_slot\":" << observation.Tank1Slot
             << ",\"tank1_projection\":" << observation.Tank1Projection
             << ",\"tank1_source_distance\":" << observation.Tank1SourceDistance
             << ",\"members\":[";
        bool firstMemberGeometry = true;
        for (ValidationRouteDrudgeMemberGeometry const& geometry : observation.MemberGeometry)
        {
            if (!firstMemberGeometry)
                json << ',';
            firstMemberGeometry = false;
            json << "{\"guid\":" << geometry.Guid
                 << ",\"roster_slot\":" << geometry.RosterSlot
                 << ",\"x\":" << geometry.X
                 << ",\"y\":" << geometry.Y
                 << ",\"projection\":" << geometry.Projection
                 << ",\"group_anchor_base_x\":" << geometry.GroupAnchorBaseX
                 << ",\"group_anchor_base_y\":" << geometry.GroupAnchorBaseY
                 << ",\"anchor_x\":" << geometry.AnchorX
                 << ",\"anchor_y\":" << geometry.AnchorY
                 << ",\"anchor_distance\":" << geometry.AnchorDistance
                 << ",\"nearest_same_lane_distance\":" << geometry.NearestSameLaneDistance
                 << ",\"anchor_candidate_index\":" << geometry.AnchorCandidateIndex
                 << ",\"lane_side_valid\":" << (geometry.LaneSideValid ? "true" : "false")
                 << ",\"anchor_selected\":" << (geometry.AnchorSelected ? "true" : "false")
                 << ",\"anchor_path_valid\":" << (geometry.AnchorPathValid ? "true" : "false")
                 << ",\"same_lane_spacing_valid\":" << (geometry.SameLaneSpacingValid ? "true" : "false")
                 << "}";
        }
        json << "]}"
             << ",\"reseparated_roster_guids\":[";
        bool firstObservationGuid = true;
        for (uint32 guid : observation.ReseparatedRosterGuids)
        {
            if (!firstObservationGuid)
                json << ',';
            firstObservationGuid = false;
            json << guid;
        }
        json << "]}";
    }
    json << "]}"
         << ",\"strategy_transition\":{\"from_strategy\":\"" << JsonEscape(raid.PreviousStrategyId)
         << "\",\"to_strategy\":\"" << JsonEscape(raid.StrategyId)
         << "\",\"advanced\":" << (raid.StrategyTransitionRouteGeneration == Party().ValidationRouteGeneration && !raid.PreviousStrategyId.empty() ? "true" : "false") << "}"
         << ",\"encounter_phase\":\"" << JsonEscape(raid.EncounterPhase) << "\""
         << ",\"wipe_state\":\"" << JsonEscape(raid.WipeState) << "\""
         << ",\"recovery_state\":\"" << JsonEscape(raid.RecoveryState) << "\""
         << ",\"boss_states\":[";
    for (size_t bossId = 0; bossId < raid.BossStates.size(); ++bossId)
    {
        if (bossId)
            json << ',';
        json << uint32(raid.BossStates[bossId]);
    }
    json << "]"
         << ",\"roster\":[";
    bool first = true;
    for (auto const& [guid, slot] : raid.RosterByGuid)
    {
        if (!first)
            json << ',';
        first = false;
        json << "{\"roster_slot_id\":\"" << JsonEscape(slot.RosterSlotId) << "\""
             << ",\"lease_role_slot\":\"" << JsonEscape(slot.LeaseRoleSlot) << "\""
             << ",\"slot\":" << slot.SlotIndex
             << ",\"guid\":" << guid
             << ",\"account_id\":" << slot.AccountId
             << ",\"account\":\"" << JsonEscape(slot.AccountName) << "\""
             << ",\"name\":\"" << JsonEscape(slot.CharacterName) << "\""
             << ",\"character_name\":\"" << JsonEscape(slot.CharacterName) << "\""
             << ",\"subgroup\":" << uint32(slot.SubGroup)
             << ",\"role\":\"" << JsonEscape(slot.Role) << "\""
             << ",\"class_id\":" << uint32(slot.ClassId)
             << ",\"class_spec\":\"" << JsonEscape(slot.ClassSpec) << "\""
             << ",\"average_item_level\":" << slot.AverageItemLevel
             << ",\"gear_identity\":\"" << JsonEscape(slot.GearIdentity) << "\""
             << ",\"talent_identity\":\"" << JsonEscape(slot.TalentIdentity) << "\""
             << ",\"glyph_identity\":\"" << JsonEscape(slot.GlyphIdentity) << "\""
             << ",\"talents\":[";
        bool firstTalent = true;
        for (uint32 spellId : slot.Talents)
        {
            if (!firstTalent)
                json << ',';
            firstTalent = false;
            json << spellId;
        }
        json << "]"
             << ",\"glyphs\":[";
        bool firstGlyph = true;
        for (uint32 glyph : slot.Glyphs)
        {
            if (!firstGlyph)
                json << ',';
            firstGlyph = false;
            json << glyph;
        }
        json << "]"
             << ",\"gear_identity_manifest\":{\"items\":[";
        bool firstItem = true;
        for (RaidRosterItemIdentity const& item : slot.GearManifest)
        {
            if (!firstItem)
                json << ',';
            firstItem = false;
            json << "{\"slot\":" << uint32(item.Slot)
                 << ",\"guid\":" << item.Guid
                 << ",\"entry\":" << item.Entry
                 << ",\"enchant_id\":" << item.EnchantId
                 << ",\"gem_item_ids\":[";
            for (size_t gemIndex = 0; gemIndex < item.GemItemIds.size(); ++gemIndex)
            {
                if (gemIndex)
                    json << ',';
                json << item.GemItemIds[gemIndex];
            }
            json << "]"
                 << ",\"reforge_id\":" << item.ReforgeId << '}';
        }
        json << "]}"
             << ",\"active\":" << (slot.Active ? "true" : "false")
             << ",\"lease_owned\":" << (slot.LeaseOwned ? "true" : "false") << '}';
    }
    json << "]}";
    return json.str();
}

