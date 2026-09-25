#include "Bots/BotWorldPopulationMgr.h"

#include "Cryptography/CryptoHash.h"
#include "DataStores/DBCStores.h"
#include "GameObjectData.h"
#include "ObjectMgr.h"
#include "Util.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "Bots/BotWorldPopulationMgrValidationRouteManifestFields.h"
#include "Bots/BotValidationRouteNativeContract.h"

using namespace BotValidationRouteManifestFields;

void BotWorldPopulationMgr::LoadValidationRouteManifest()
{
    Party().ValidationRoutePendingFinalTransitionGuids.clear();
    Party().ValidationRouteFinalTransitionGuids.clear();
    Party().ValidationRouteManifestSha256.clear();
    if (Cohort().Config.ValidationRouteManifestPath.empty())
        return;

    std::string manifestJson = ReadSmallTextFile(Cohort().Config.ValidationRouteManifestPath);
    if (manifestJson.empty())
    {
        Party().ValidationRouteManifestLoadError = "manifest_unreadable";
        return;
    }
    Party().ValidationRouteManifestSha256 = ByteArrayToHexStr(
        Trinity::Crypto::SHA256::GetDigestOf(manifestJson));
    std::transform(
        Party().ValidationRouteManifestSha256.begin(),
        Party().ValidationRouteManifestSha256.end(),
        Party().ValidationRouteManifestSha256.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });

    std::string routesJson = ExtractJsonArrayField(manifestJson, "routes");
    std::vector<std::string> routeObjects = routesJson.empty()
        ? ExtractJsonLineObjects(manifestJson)
        : ExtractJsonObjectArrayItems(routesJson);
    if (routeObjects.empty())
    {
        Party().ValidationRouteManifestLoadError = "manifest_routes_missing";
        return;
    }

    auto readInt = [](std::string const& objectJson, char const* key) -> int
    {
        int value = 0;
        ExtractJsonIntField(objectJson, key, value);
        return value;
    };
    auto readFloat = [](std::string const& objectJson, char const* key) -> float
    {
        float value = 0.0f;
        ExtractJsonNumberField(objectJson, key, value);
        return value;
    };

    for (std::string const& routeJson : routeObjects)
    {
        ValidationRouteManifestNode node;
        node.ScenarioId = ExtractJsonStringField(routeJson, "scenario_id");
        if (!Cohort().Config.ValidationRouteScenarioId.empty() && node.ScenarioId != Cohort().Config.ValidationRouteScenarioId)
            continue;
        node.RuntimeProfileId = ExtractJsonStringField(routeJson, "runtime_profile_id");
        // Diagnostic partitions are profile-owned. A missing or foreign
        // profile binding must stop native admission before any lease or bot
        // spawn; the historical canonical manifest is allowed to omit this
        // field for compatibility with its frozen identity contract.
        bool const dynamicValidationProfile = Cohort().Config.Name != "stonecore_5n"
            && Cohort().Config.Name != "blackwing_descent_10n";
        if ((dynamicValidationProfile && node.RuntimeProfileId.empty())
            || (!node.RuntimeProfileId.empty()
                && node.RuntimeProfileId != Cohort().Config.Name
                && node.RuntimeProfileId != Cohort().Config.ValidationRouteScenarioId))
        {
            Party().ValidationRouteManifestLoadError = "manifest_runtime_profile_identity_mismatch";
            return;
        }
        node.NodeId = ExtractJsonStringField(routeJson, "route_node_id");
        node.Label = ExtractJsonStringField(routeJson, "label");
        // Route rows are written with sorted keys, so a nested
        // "completion_contract" (and its "kind") precedes the row's own
        // "kind". Read the row field structurally; the regex value is kept as
        // the fallback and is identical for rows without nested kinds.
        node.Kind = BotValidationRouteNativeJson::TopLevelString(routeJson,
            "kind", ExtractJsonStringField(routeJson, "kind"));
        node.NodeKind = ExtractJsonStringField(routeJson, "node_kind");
        node.DescentAction = ExtractJsonStringField(routeJson, "descent_action");
        node.MechanicProfile = ExtractJsonStringField(routeJson, "mechanic_profile");
        std::string const bossRecoveryPolicy = ExtractJsonStringField(routeJson, "boss_recovery_policy");
        if (bossRecoveryPolicy == "native_full_wipe_only")
            node.BossRecoveryPolicy = ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly;
        else
            node.BossRecoveryPolicy = ValidationRouteBossRecoveryPolicy::NativeEncounter;
        std::string const mechanicContract = ExtractJsonObjectField(routeJson, "mechanic_contract");
        if (!mechanicContract.empty())
        {
            static std::set<std::string> const AllowedMechanicContractFields =
            {
                "id", "formation_family", "formation_anchor", "formation_scope", "formation_orientation",
                "spacing_yards", "minimum_distance_yards", "radius_yards", "arc_radians", "lane_count",
                "arrival_tolerance_yards", "target_control", "target_entries", "allow_area_damage",
                "allow_multidot", "controlled_aoe_minimum_targets", "kill_sync_tolerance_pct",
                "kill_sync_execution_floor_pct", "tank_swap_trigger", "tank_swap_aura_id",
                "tank_swap_aura_stacks", "tank_swap_interval_ms", "tank_swap_trigger_spell_id",
                "tank_swap_add_entry", "tank_swap_phase", "main_tank_roster_slot", "off_tank_roster_slot",
                "interrupt_owner_slot", "interrupt_backup_slot",
                "interrupt_trigger_spell_id", "dispel_aura_id", "dispel_owner_slot", "dispel_backup_slot",
                "area_damage_spell_allowlist", "area_damage_target_allowlist",
                "healer_ownership", "healer_owner_slots", "cooldown_category", "cooldown_owner_slot",
                "cooldown_backup_slot", "cooldown_trigger_spell_id", "cooldown_target", "soak_roster_slots",
                "soak_minimum_count", "soak_radius_yards", "soak_trigger_spell_id", "soak_trigger_aura_id",
                "soak_immunity_spell_id", "soak_personal_cooldown_spell_id", "battle_resurrection_policy",
                "battle_resurrection_slots", "interaction_kind", "interactable_entry", "vehicle_entry",
                "transport_entry", "jump_pad_entry", "extra_action_spell_id", "extra_action_trigger_aura_id",
                "movement_link", "transfer_area_trigger_id", "platform_policy", "platform_destination_map_id",
                "platform_destination_area_id", "platform_minimum_z", "platform_maximum_z"
            };
            for (std::string const& key : ExtractJsonTopLevelKeys(mechanicContract))
                if (AllowedMechanicContractFields.find(key) == AllowedMechanicContractFields.end())
                {
                    node.MechanicContractError = "unknown_field:" + key;
                    break;
                }
            node.MechanicContractId = ExtractJsonStringField(mechanicContract, "id");
            node.FormationFamily = ExtractJsonStringField(mechanicContract, "formation_family");
            node.FormationAnchor = ExtractJsonStringField(mechanicContract, "formation_anchor");
            node.FormationScope = ExtractJsonStringField(mechanicContract, "formation_scope");
            if (node.FormationScope.empty())
                node.FormationScope = "raid";
            node.FormationOrientation = ExtractJsonStringField(mechanicContract, "formation_orientation");
            node.TargetControl = ExtractJsonStringField(mechanicContract, "target_control");
            node.FormationSpacingYards = readFloat(mechanicContract, "spacing_yards");
            node.FormationMinimumDistanceYards = readFloat(mechanicContract, "minimum_distance_yards");
            node.FormationRadiusYards = readFloat(mechanicContract, "radius_yards");
            node.FormationArcRadians = readFloat(mechanicContract, "arc_radians");
            node.FormationArrivalToleranceYards = readFloat(mechanicContract, "arrival_tolerance_yards");
            node.FormationLaneCount = uint32(std::max(0, readInt(mechanicContract, "lane_count")));
            ExtractJsonBoolField(mechanicContract, "allow_area_damage", node.AllowAreaDamage);
            ExtractJsonBoolField(mechanicContract, "allow_multidot", node.AllowMultidot);
            node.TargetEntries = ExtractJsonUIntArrayField(mechanicContract, "target_entries");
            node.AreaDamageSpellAllowlist = ExtractJsonUIntArrayField(mechanicContract, "area_damage_spell_allowlist");
            node.AreaDamageTargetAllowlist = ExtractJsonUIntArrayField(mechanicContract, "area_damage_target_allowlist");
            node.ControlledAoeMinimumTargets = uint32(std::max(0, readInt(mechanicContract, "controlled_aoe_minimum_targets")));
            node.KillSyncTolerancePct = readFloat(mechanicContract, "kill_sync_tolerance_pct");
            node.KillSyncExecutionFloorPct = readFloat(mechanicContract, "kill_sync_execution_floor_pct");
            node.TankSwapTrigger = ExtractJsonStringField(mechanicContract, "tank_swap_trigger");
            node.TankSwapAuraId = uint32(std::max(0, readInt(mechanicContract, "tank_swap_aura_id")));
            node.TankSwapAuraStacks = uint32(std::max(0, readInt(mechanicContract, "tank_swap_aura_stacks")));
            node.TankSwapIntervalMs = uint32(std::max(0, readInt(mechanicContract, "tank_swap_interval_ms")));
            node.TankSwapTriggerSpellId = uint32(std::max(0, readInt(mechanicContract, "tank_swap_trigger_spell_id")));
            node.TankSwapAddEntry = uint32(std::max(0, readInt(mechanicContract, "tank_swap_add_entry")));
            node.TankSwapPhase = ExtractJsonStringField(mechanicContract, "tank_swap_phase");
            node.MainTankRosterSlot = uint32(std::max(0, readInt(mechanicContract, "main_tank_roster_slot")));
            node.OffTankRosterSlot = uint32(std::max(0, readInt(mechanicContract, "off_tank_roster_slot")));
            node.InterruptOwnerSlot = uint32(std::max(0, readInt(mechanicContract, "interrupt_owner_slot")));
            node.InterruptBackupSlot = uint32(std::max(0, readInt(mechanicContract, "interrupt_backup_slot")));
            node.InterruptTriggerSpellId = uint32(std::max(0, readInt(mechanicContract, "interrupt_trigger_spell_id")));
            node.InteractableEntry = uint32(std::max(0, readInt(mechanicContract, "interactable_entry")));
            node.VehicleEntry = uint32(std::max(0, readInt(mechanicContract, "vehicle_entry")));
            node.TransportEntry = uint32(std::max(0, readInt(mechanicContract, "transport_entry")));
            node.TransferAreaTriggerId = uint32(std::max(0, readInt(mechanicContract, "transfer_area_trigger_id")));
            node.ExtraActionSpellId = uint32(std::max(0, readInt(mechanicContract, "extra_action_spell_id")));
            node.ExtraActionTriggerAuraId = uint32(std::max(0, readInt(mechanicContract, "extra_action_trigger_aura_id")));
            node.DispelAuraId = uint32(std::max(0, readInt(mechanicContract, "dispel_aura_id")));
            node.DispelOwnerSlot = uint32(std::max(0, readInt(mechanicContract, "dispel_owner_slot")));
            node.DispelBackupSlot = uint32(std::max(0, readInt(mechanicContract, "dispel_backup_slot")));
            node.CooldownCategory = ExtractJsonStringField(mechanicContract, "cooldown_category");
            node.CooldownOwnerSlot = uint32(std::max(0, readInt(mechanicContract, "cooldown_owner_slot")));
            node.CooldownBackupSlot = uint32(std::max(0, readInt(mechanicContract, "cooldown_backup_slot")));
            node.CooldownTriggerSpellId = uint32(std::max(0, readInt(mechanicContract, "cooldown_trigger_spell_id")));
            node.CooldownTarget = ExtractJsonStringField(mechanicContract, "cooldown_target");
            if (node.CooldownTarget.empty())
                node.CooldownTarget = "self";
            node.HealerOwnership = ExtractJsonStringField(mechanicContract, "healer_ownership");
            if (node.HealerOwnership.empty())
                node.HealerOwnership = "raid_triage";
            node.HealerOwnerSlots = ExtractJsonUIntArrayField(mechanicContract, "healer_owner_slots");
            node.SoakRosterSlots = ExtractJsonUIntArrayField(mechanicContract, "soak_roster_slots");
            node.SoakMinimumCount = uint32(std::max(0, readInt(mechanicContract, "soak_minimum_count")));
            node.SoakRadiusYards = readFloat(mechanicContract, "soak_radius_yards");
            node.SoakTriggerSpellId = uint32(std::max(0, readInt(mechanicContract, "soak_trigger_spell_id")));
            node.SoakTriggerAuraId = uint32(std::max(0, readInt(mechanicContract, "soak_trigger_aura_id")));
            node.SoakImmunitySpellId = uint32(std::max(0, readInt(mechanicContract, "soak_immunity_spell_id")));
            node.SoakPersonalCooldownSpellId = uint32(std::max(0, readInt(mechanicContract, "soak_personal_cooldown_spell_id")));
            node.BattleResurrectionPolicy = ExtractJsonStringField(mechanicContract, "battle_resurrection_policy");
            if (node.BattleResurrectionPolicy.empty())
                node.BattleResurrectionPolicy = "native_rotation";
            node.BattleResurrectionSlots = ExtractJsonUIntArrayField(mechanicContract, "battle_resurrection_slots");
            node.InteractionKind = ExtractJsonStringField(mechanicContract, "interaction_kind");
            if (node.InteractionKind.empty())
                node.InteractionKind = "none";
            node.JumpPadEntry = uint32(std::max(0, readInt(mechanicContract, "jump_pad_entry")));
            node.MovementLink = ExtractJsonStringField(mechanicContract, "movement_link");
            if (node.MovementLink.empty())
                node.MovementLink = "none";
            node.PlatformPolicy = ExtractJsonStringField(mechanicContract, "platform_policy");
            if (node.PlatformPolicy.empty())
                node.PlatformPolicy = "ground";
            node.PlatformDestinationMapId = uint32(std::max(0, readInt(mechanicContract, "platform_destination_map_id")));
            node.PlatformDestinationAreaId = uint32(std::max(0, readInt(mechanicContract, "platform_destination_area_id")));
            node.PlatformMinimumZ = readFloat(mechanicContract, "platform_minimum_z");
            node.PlatformMaximumZ = readFloat(mechanicContract, "platform_maximum_z");
            bool const knownFormation = node.FormationFamily.empty()
                || node.FormationFamily == "stack" || node.FormationFamily == "spread"
                || node.FormationFamily == "pair" || node.FormationFamily == "lane"
                || node.FormationFamily == "quadrant" || node.FormationFamily == "ring"
                || node.FormationFamily == "cone" || node.FormationFamily == "behind"
                || node.FormationFamily == "front_exclusion";
            bool const knownAnchor = node.FormationFamily.empty()
                || node.FormationAnchor == "route_anchor" || node.FormationAnchor == "boss"
                || node.FormationAnchor == "main_tank" || node.FormationAnchor == "raid_leader"
                || node.FormationAnchor == "role" || node.FormationAnchor == "subgroup";
            bool const knownScope = node.FormationScope == "raid" || node.FormationScope == "role"
                || node.FormationScope == "subgroup";
            bool const knownOrientation = node.FormationFamily.empty()
                || node.FormationOrientation == "route" || node.FormationOrientation == "boss_facing"
                || node.FormationOrientation == "anchor_to_boss";
            bool const formationResolved = node.FormationFamily.empty()
                || (node.FormationArrivalToleranceYards > 0.0f
                    && (node.FormationFamily == "stack" || node.FormationSpacingYards > 0.0f
                        || node.FormationRadiusYards > 0.0f || node.FormationMinimumDistanceYards > 0.0f)
                    && (node.FormationFamily != "lane" || node.FormationLaneCount > 0)
                    && ((node.FormationFamily != "cone" && node.FormationFamily != "behind"
                            && node.FormationFamily != "front_exclusion")
                        || node.FormationArcRadians > 0.0f));
            bool const targetResolved = node.TargetControl.empty()
                || ((node.TargetControl == "focus_fire" || node.TargetControl == "multidot"
                        || node.TargetControl == "do_not_damage") && !node.TargetEntries.empty()
                    && (node.TargetControl != "focus_fire" || (!node.AllowMultidot && !node.AllowAreaDamage)))
                || (node.TargetControl == "controlled_aoe" && node.AllowAreaDamage
                    && !node.AllowMultidot && node.ControlledAoeMinimumTargets > 0
                    && !node.TargetEntries.empty())
                || (node.TargetControl == "kill_sync" && node.KillSyncTolerancePct > 0.0f
                    && node.KillSyncExecutionFloorPct > 0.0f && !node.TargetEntries.empty());
            bool const tankSwapResolved = node.TankSwapTrigger.empty()
                || (node.TankSwapTrigger == "debuff_stacks" && node.TankSwapAuraId > 0 && node.TankSwapAuraStacks > 0)
                || (node.TankSwapTrigger == "timer" && node.TankSwapIntervalMs > 0)
                || (node.TankSwapTrigger == "boss_cast" && node.TankSwapTriggerSpellId > 0)
                || (node.TankSwapTrigger == "add_spawn" && node.TankSwapAddEntry > 0)
                || (node.TankSwapTrigger == "phase_transition" && !node.TankSwapPhase.empty());
            bool const tankAssignmentResolved = (!node.MainTankRosterSlot && !node.OffTankRosterSlot)
                || (node.MainTankRosterSlot > 0 && node.OffTankRosterSlot > 0
                    && node.MainTankRosterSlot != node.OffTankRosterSlot
                    && node.MainTankRosterSlot <= Cohort().Config.RaidSize
                    && node.OffTankRosterSlot <= Cohort().Config.RaidSize);
            bool const interruptResolved = !node.InterruptOwnerSlot
                || (node.InterruptBackupSlot > 0 && node.InterruptOwnerSlot != node.InterruptBackupSlot
                    && node.InterruptTriggerSpellId > 0);
            bool const dispelResolved = !node.DispelAuraId
                || (node.DispelOwnerSlot > 0 && node.DispelBackupSlot > 0
                    && node.DispelOwnerSlot != node.DispelBackupSlot);
            bool const cooldownResolved = node.CooldownCategory.empty()
                || (node.CooldownOwnerSlot > 0 && node.CooldownTriggerSpellId > 0
                    && (node.CooldownTarget == "self" || node.CooldownTarget == "tank"
                        || node.CooldownTarget == "lowest" || node.CooldownTarget == "subgroup"));
            bool const soakResolved = node.SoakRosterSlots.empty()
                || (node.SoakMinimumCount > 0 && node.SoakRadiusYards > 0.0f
                    && node.SoakMinimumCount <= node.SoakRosterSlots.size());
            bool const extraActionResolved = !node.ExtraActionSpellId || node.ExtraActionTriggerAuraId > 0;
            bool const knownHealerOwnership = node.HealerOwnership == "raid_triage"
                || node.HealerOwnership == "subgroup" || node.HealerOwnership == "tank"
                || node.HealerOwnership == "tank_and_subgroup";
            bool const knownBattleRes = node.BattleResurrectionPolicy == "native_rotation"
                || node.BattleResurrectionPolicy == "tank_then_healer_then_dps"
                || node.BattleResurrectionPolicy == "assigned_only";
            std::set<uint32> const uniqueBattleResSlots(
                node.BattleResurrectionSlots.begin(), node.BattleResurrectionSlots.end());
            bool const battleResSlotsValid = node.BattleResurrectionSlots.empty()
                || (uniqueBattleResSlots.size() == node.BattleResurrectionSlots.size()
                    && std::all_of(node.BattleResurrectionSlots.begin(), node.BattleResurrectionSlots.end(),
                        [this](uint32 slot) { return slot > 0 && slot <= Cohort().Config.RaidSize; }));
            bool const battleResResolved = node.BattleResurrectionPolicy != "assigned_only"
                ? battleResSlotsValid : (!node.BattleResurrectionSlots.empty() && battleResSlotsValid);
            bool const knownInteraction = node.InteractionKind == "none" || node.InteractionKind == "object"
                || node.InteractionKind == "extra_action" || node.InteractionKind == "vehicle"
                || node.InteractionKind == "transport" || node.InteractionKind == "jump_pad";
            bool const interactionResolved = (node.InteractionKind == "none")
                || (node.InteractionKind == "object" && node.InteractableEntry > 0)
                || (node.InteractionKind == "extra_action" && node.ExtraActionSpellId > 0 && extraActionResolved)
                || (node.InteractionKind == "vehicle" && node.VehicleEntry > 0)
                || (node.InteractionKind == "transport" && node.TransportEntry > 0)
                || (node.InteractionKind == "jump_pad" && (node.JumpPadEntry > 0 || node.TransferAreaTriggerId > 0));
            bool const knownMovement = node.MovementLink == "none" || node.MovementLink == "encounter_link"
                || node.MovementLink == "cross_platform" || node.MovementLink == "regroup";
            bool const knownPlatform = node.PlatformPolicy == "ground" || node.PlatformPolicy == "platform"
                || node.PlatformPolicy == "altitude" || node.PlatformPolicy == "flying";
            bool const platformResolved = node.PlatformPolicy == "ground"
                || node.PlatformDestinationMapId > 0 || node.PlatformDestinationAreaId > 0
                || node.PlatformMaximumZ > node.PlatformMinimumZ;
            bool const jumpTransferResolved = node.InteractionKind != "jump_pad"
                || (node.MovementLink != "none" && node.MovementLink != "regroup"
                    && node.PlatformPolicy != "ground"
                    && (node.PlatformDestinationMapId > 0 || node.PlatformDestinationAreaId > 0
                        || node.PlatformMaximumZ > node.PlatformMinimumZ));
            node.MechanicContractResolved = !node.MechanicContractId.empty()
                && node.MechanicContractError.empty() && knownFormation && knownAnchor && knownScope
                && knownOrientation && formationResolved && targetResolved && tankSwapResolved
                && tankAssignmentResolved
                && interruptResolved && dispelResolved && cooldownResolved && soakResolved
                && knownHealerOwnership && knownBattleRes && battleResResolved
                && knownInteraction && interactionResolved
                && knownMovement && knownPlatform && platformResolved && jumpTransferResolved;
            if (!node.MechanicContractResolved && node.MechanicContractError.empty())
                node.MechanicContractError = "unsupported_or_incomplete_contract";
        }
        // Native route contracts are parsed structurally and fail closed:
        // every declared kind/action is executable and observable, unknown
        // fields or kinds stop the manifest before any bot is admitted.
        namespace NativeRoute = BotValidationRouteNative;
        auto parseNativeContract = [&routeJson](char const* field, auto const& parse,
            auto& contract, char const* unknownPrefix, char const* invalidPrefix,
            std::string& loadError) -> bool
        {
            std::string const text = ExtractJsonObjectField(routeJson, field);
            if (text.empty())
                return true;
            NativeRoute::Json object;
            NativeRoute::ParseError error = NativeRoute::ParseObjectText(text, object);
            if (!error)
                error = parse(object, contract);
            if (!error)
                return true;
            loadError = std::string(error.Kind == NativeRoute::ParseError::Code::UnknownField
                ? unknownPrefix : invalidPrefix) + error.Detail;
            return false;
        };
        std::string nativeContractError;
        if (!parseNativeContract("interaction_contract",
                [](NativeRoute::Json const& object, NativeRoute::InteractionContract& out)
                { return NativeRoute::ParseInteraction(object, out); },
                node.NativeContract.Interaction, "native_interaction_unknown_field:",
                "native_interaction_contract_invalid:", nativeContractError)
            || !parseNativeContract("completion_contract",
                [](NativeRoute::Json const& object, NativeRoute::CompletionContract& out)
                { return NativeRoute::ParseCompletion(object, out); },
                node.NativeContract.Completion, "native_completion_unknown_field:",
                "native_completion_contract_invalid:", nativeContractError)
            || !parseNativeContract("transport_contract",
                [](NativeRoute::Json const& object, NativeRoute::TransportContract& out)
                { return NativeRoute::ParseTransport(object, out); },
                node.NativeContract.Transport, "native_transport_unknown_field:",
                "native_transport_contract_invalid:", nativeContractError))
        {
            Party().ValidationRouteManifestLoadError = nativeContractError;
            return;
        }
        if (NativeRoute::ParseError shapeError = NativeRoute::ValidateNodeShape(
                node.Kind, node.NativeContract.Interaction,
                node.NativeContract.Completion, node.NativeContract.Transport))
        {
            Party().ValidationRouteManifestLoadError =
                "native_route_contract_shape_invalid:" + shapeError.Detail;
            return;
        }
        // Legacy mirrors read by the encounter blackboard and strategies.
        node.NativeInteractionAction = node.NativeContract.Interaction.ActionName;
        node.NativeInteractionEntry = node.NativeContract.Interaction.Entry;
        node.NativeInteractionMenus = node.NativeContract.Interaction.Menus;
        node.NativeInteractionOption = node.NativeContract.Interaction.Option;
        node.NativeCompletionKind = node.NativeContract.Completion.KindName;
        node.NativeCompletionEntry = node.NativeContract.Completion.Entry;
        node.NativeCompletionSpellId = node.NativeContract.Completion.SpellId;
        node.MapId = uint32(std::max(0, readInt(routeJson, "map_id")));
        // A transport's readiness must match how its template moves: stop
        // frames (GoState 25 + n) only for templates with stop times, origin
        // heights only for continuously cycling templates.
        if (node.NativeContract.Transport.Declared)
        {
            auto const& transport = node.NativeContract.Transport;
            uint32 entry = transport.Entry;
            if (GameObjectData const* data = transport.SpawnId
                    ? sObjectMgr->GetGameObjectData(ObjectGuid::LowType(transport.SpawnId)) : nullptr)
            {
                if ((entry && data->id != entry) || data->mapId != node.MapId)
                {
                    Party().ValidationRouteManifestLoadError =
                        "native_transport_contract_invalid:spawn_mismatch";
                    return;
                }
                entry = data->id;
            }
            GameObjectTemplate const* goInfo = entry ? sObjectMgr->GetGameObjectTemplate(entry) : nullptr;
            if (!goInfo || goInfo->type != GAMEOBJECT_TYPE_TRANSPORT)
            {
                Party().ValidationRouteManifestLoadError =
                    "native_transport_contract_invalid:not_a_transport";
                return;
            }
            int32 stopFrames = 0;
            for (uint32 stopTime : { goInfo->transport.Timeto2ndfloor, goInfo->transport.Timeto3rdfloor,
                    goInfo->transport.Timeto4thfloor, goInfo->transport.Timeto5thfloor })
            {
                if (!stopTime)
                    break;
                ++stopFrames;
            }
            bool const levelOnStopFrames = stopFrames > 0
                && (transport.HasBoardLevel || transport.HasExitLevel);
            bool const frameOnCycling = transport.BoardStopFrame >= stopFrames
                || transport.ExitStopFrame >= stopFrames;
            if (levelOnStopFrames || frameOnCycling)
            {
                Party().ValidationRouteManifestLoadError = levelOnStopFrames
                    ? "native_transport_contract_invalid:level_readiness_on_stop_frame_transport"
                    : "native_transport_contract_invalid:stop_frame_not_in_template";
                return;
            }
        }
        // A declared area trigger must exist on the route map; never walk
        // toward an unresolved trigger position.
        if (node.NativeContract.Interaction.Declared
            && node.NativeContract.Interaction.Action
                == BotValidationRouteNative::InteractionAction::AreaTrigger)
        {
            AreaTriggerEntry const* trigger = sAreaTriggerStore.LookupEntry(
                node.NativeContract.Interaction.AreaTriggerId);
            if (!trigger || trigger->ContinentID != node.MapId)
            {
                Party().ValidationRouteManifestLoadError =
                    "native_interaction_contract_invalid:area_trigger_not_on_route_map";
                return;
            }
        }
        node.RecoveryEntranceAreaTriggerId = uint32(std::max(0,
            readInt(routeJson, "recovery_entrance_area_trigger_id")));
        node.RecoveryEntranceSourceMapId = uint32(std::max(0,
            readInt(routeJson, "recovery_entrance_source_map_id")));
        node.RecoveryEntranceTargetMapId = uint32(std::max(0,
            readInt(routeJson, "recovery_entrance_target_map_id")));
        node.X = readFloat(routeJson, "x");
        node.Y = readFloat(routeJson, "y");
        node.Z = readFloat(routeJson, "z");
        node.O = readFloat(routeJson, "o");
        node.NavigationAnchorX = node.X;
        node.NavigationAnchorY = node.Y;
        node.NavigationAnchorZ = node.Z;
        node.NavigationAnchorO = node.O;
        ExtractJsonNumberField(routeJson, "navigation_anchor_x", node.NavigationAnchorX);
        ExtractJsonNumberField(routeJson, "navigation_anchor_y", node.NavigationAnchorY);
        ExtractJsonNumberField(routeJson, "navigation_anchor_z", node.NavigationAnchorZ);
        ExtractJsonNumberField(routeJson, "navigation_anchor_o", node.NavigationAnchorO);
        node.BotStartMapId = uint32(std::max(0, readInt(routeJson, "bot_start_map_id")));
        node.BotStartX = readFloat(routeJson, "bot_start_x");
        node.BotStartY = readFloat(routeJson, "bot_start_y");
        node.BotStartZ = readFloat(routeJson, "bot_start_z");
        node.BotStartO = readFloat(routeJson, "bot_start_o");
        node.TargetEntry = uint32(std::max(0, readInt(routeJson, "source_entry")));
        std::string targetSpawnIdText = ExtractJsonStringField(routeJson, "source_guid");
        if (!targetSpawnIdText.empty())
            node.TargetSpawnId = ObjectGuid::LowType(strtoull(targetSpawnIdText.c_str(), nullptr, 10));
        else
            node.TargetSpawnId = ObjectGuid::LowType(std::max(0, readInt(routeJson, "source_guid")));
        node.OpenerTargetEntry = uint32(std::max(0, readInt(routeJson, "opener_target_entry")));
        node.AlternateTargetEntries = ExtractJsonUIntArrayField(routeJson, "alternate_target_entries");
        node.AddTargetEntries = ExtractJsonUIntArrayField(routeJson, "add_target_entries");
        node.PackTargetEntries = ExtractJsonUIntArrayField(routeJson, "pack_target_entries");
        node.ScriptedEventEntries = ExtractJsonUIntArrayField(routeJson, "scripted_event_entries");
        node.ScriptedEventTransitionAuraIds = ExtractJsonUIntArrayField(routeJson, "scripted_event_transition_aura_ids");
        ExtractJsonBoolField(routeJson, "scripted_event_require_passive", node.ScriptedEventRequirePassive);
        node.HazardSourceEntry = uint32(std::max(0, readInt(routeJson, "hazard_source_entry")));
        node.HazardDetectionSpellId = uint32(std::max(0, readInt(routeJson, "hazard_detection_spell_id")));
        node.HazardDamageSpellId = uint32(std::max(0, readInt(routeJson, "hazard_damage_spell_id")));
        node.HazardShape = ExtractJsonStringField(routeJson, "hazard_shape");
        node.HazardRadiusYards = readFloat(routeJson, "hazard_radius_yards");
        node.HazardSafetyMarginYards = readFloat(routeJson, "hazard_safety_margin_yards");
        node.MinimumDistanceSourceEntry = uint32(std::max(0, readInt(routeJson, "minimum_distance_source_entry")));
        node.MinimumDistanceYards = readFloat(routeJson, "minimum_distance_yards");
        node.SplitSourceGuids = ExtractJsonUIntArrayField(routeJson, "split_source_guids");
        node.SplitLaneARosterSlots = ExtractJsonUIntArrayField(routeJson, "split_lane_a_roster_slots");
        node.SplitLaneBRosterSlots = ExtractJsonUIntArrayField(routeJson, "split_lane_b_roster_slots");
        node.SplitLaneTankSlots = ExtractJsonUIntArrayField(routeJson, "split_lane_tank_slots");
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_member_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitMemberAnchors.push_back(anchor);
        }
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_recovery_member_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitRecoveryMemberAnchors.push_back(anchor);
        }
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_tank_combat_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitTankCombatAnchors.push_back(anchor);
        }
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_tank_navigation_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitTankNavigationAnchors.push_back(anchor);
        }
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_tank_recovery_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitTankRecoveryAnchors.push_back(anchor);
        }
        node.SplitMinimumSeparationYards = readFloat(routeJson, "split_minimum_separation_yards");
        node.SplitNavigationMarginYards = readFloat(routeJson, "split_navigation_margin_yards");
        node.SplitArrivalToleranceYards = readFloat(routeJson, "split_arrival_tolerance_yards");
        node.SplitTankArrivalToleranceYards = readFloat(routeJson, "split_tank_arrival_tolerance_yards");
        node.SplitNativeMeleeStopYards = readFloat(routeJson, "split_native_melee_stop_yards");
        if (!ExtractJsonStrictUIntArrayField(
            routeJson, "split_healer_roster_slots", node.SplitHealerRosterSlots))
            node.SplitHealerRosterSlots.clear();
        if (!ExtractJsonStrictUIntArrayField(
            routeJson, "split_seed_roster_slots", node.SplitSeedRosterSlots))
            node.SplitSeedRosterSlots.clear();
        node.SplitSeedMaxRangeYards = readFloat(routeJson, "split_seed_max_range_yards");
        node.SplitTankThreatHeadroomMultiplier = readFloat(
            routeJson, "split_tank_threat_headroom_multiplier");
        node.ThunderclapSpellId = uint32(std::max(0, readInt(routeJson, "thunderclap_spell_id")));
        node.ChargeSpellId = uint32(std::max(0, readInt(routeJson, "charge_spell_id")));
        node.ChargeRangeYards = readFloat(routeJson, "charge_range_yards");
        node.ChargeNativeIntervalMs = uint32(std::max(0, readInt(routeJson, "charge_native_interval_ms")));
        node.VengefulRageSpellId = uint32(std::max(0, readInt(routeJson, "vengeful_rage_spell_id")));
        node.ClusterRadiusYards = readFloat(routeJson, "cluster_radius_yards");
        node.PatrolPullPolicy = ExtractJsonStringField(routeJson, "patrol_pull_policy");
        node.PatrolWaitX = readFloat(routeJson, "patrol_wait_x");
        node.PatrolWaitY = readFloat(routeJson, "patrol_wait_y");
        node.PatrolWaitZ = readFloat(routeJson, "patrol_wait_z");
        node.PatrolWaitToleranceYards = readFloat(routeJson, "patrol_wait_tolerance_yards");
        node.PatrolAnchorToleranceYards = readFloat(routeJson, "patrol_anchor_tolerance_yards");
        node.PatrolEngageRadiusYards = readFloat(routeJson, "patrol_engage_radius_yards");
        node.PatrolFutureGuardMarginYards = readFloat(routeJson, "patrol_future_guard_margin_yards");
        std::string const patrolCombatAnchor = ExtractJsonObjectField(
            routeJson, "patrol_combat_anchor");
        node.PatrolCombatAnchor.X = readFloat(patrolCombatAnchor, "x");
        node.PatrolCombatAnchor.Y = readFloat(patrolCombatAnchor, "y");
        node.PatrolCombatAnchor.Z = readFloat(patrolCombatAnchor, "z");
        node.PatrolCombatAnchorToleranceYards = readFloat(
            routeJson, "patrol_combat_anchor_tolerance_yards");
        node.PatrolCombatClearanceYards = readFloat(
            routeJson, "patrol_combat_clearance_yards");
        node.PatrolPullOwnerRosterSlot = uint32(std::max(0, readInt(routeJson, "patrol_pull_owner_roster_slot")));
        node.ExpectedAliveCount = uint32(std::max(0, readInt(routeJson, "expected_alive_count")));
        node.ActivationAreaTriggerId = uint32(std::max(0, readInt(routeJson, "activation_area_trigger_id")));
        node.ActivationDataId = uint32(std::max(0, readInt(routeJson, "activation_data_id")));
        node.ActivationDataValue = uint32(std::max(0, readInt(routeJson, "activation_data_value")));
        node.ActivationSpawnGroupId = uint32(std::max(0, readInt(routeJson, "activation_spawn_group_id")));
        node.ActivationActionEntry = uint32(std::max(0, readInt(routeJson, "activation_action_entry")));
        node.ActivationActionId = readInt(routeJson, "activation_action_id");
        node.ActivationSummonEntry = uint32(std::max(0, readInt(routeJson, "activation_summon_entry")));
        node.ActivationSummonX = readFloat(routeJson, "activation_summon_x");
        node.ActivationSummonY = readFloat(routeJson, "activation_summon_y");
        node.ActivationSummonZ = readFloat(routeJson, "activation_summon_z");
        node.ActivationSummonO = readFloat(routeJson, "activation_summon_o");
        node.OpenerSummonEntry = uint32(std::max(0, readInt(routeJson, "opener_summon_entry")));
        node.OpenerSummonX = readFloat(routeJson, "opener_summon_x");
        node.OpenerSummonY = readFloat(routeJson, "opener_summon_y");
        node.OpenerSummonZ = readFloat(routeJson, "opener_summon_z");
        node.OpenerSummonO = readFloat(routeJson, "opener_summon_o");
        node.ExpectedBotCount = uint32(std::max(0, readInt(routeJson, "expected_bot_count")));
        for (std::string const& identityJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "roster_identity")))
        {
            ValidationRouteManifestNode::RosterIdentity identity;
            identity.RosterSlotId = ExtractJsonStringField(identityJson, "roster_slot_id");
            identity.Guid = uint32(std::max(0, readInt(identityJson, "guid")));
            identity.Name = ExtractJsonStringField(identityJson, "name");
            identity.Role = ExtractJsonStringField(identityJson, "role");
            identity.ClassSpec = ExtractJsonStringField(identityJson, "class_spec");
            node.ExpectedRoster.push_back(std::move(identity));
        }
        if (!node.NodeId.empty() && !node.Kind.empty())
            Party().ValidationRouteManifest.push_back(node);
    }

    if (Party().ValidationRouteManifest.empty())
    {
        Party().ValidationRouteManifestLoadError = "manifest_routes_empty";
        return;
    }

    ApplyValidationRouteManifestNode(0, "manifest_load");
}
