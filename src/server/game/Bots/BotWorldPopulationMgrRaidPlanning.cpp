#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotLongTermProgressionBrain.h"

#include "Group.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

BotWorldPopulationMgr::RaidRoleAssignment BotWorldPopulationMgr::BuildRaidRoleAssignment(Player* bot) const
{
    RaidRoleAssignment assignment;
    if (!bot)
        return assignment;

    assignment.Role = GetDungeonRole(bot);
    assignment.ClassSpec = GetBotClassSpec(bot);
    assignment.AverageItemLevel = bot->GetAverageItemLevel();
    for (WorldBotState const& state : Party().Bots)
        if (state.Guid == bot->GetGUID())
        {
            assignment.RosterSlotId = state.RosterSlotId;
            assignment.LeaseRoleSlot = state.RosterSlotId;
            if (!state.RosterClassSpec.empty())
                assignment.ClassSpec = state.RosterClassSpec;
            if (state.RosterAverageItemLevel > 0.0f)
                assignment.AverageItemLevel = state.RosterAverageItemLevel;
            break;
        }
    if (Group* group = bot->GetGroup())
    {
        assignment.RaidLeaderGuid = group->GetLeaderGUID();
        assignment.SubGroup = group->GetMemberGroup(bot->GetGUID());
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != bot->GetMap())
                continue;

            ++assignment.RaidSize;
            std::string role = GetDungeonRole(member);
            if (role == "tank")
            {
                if (assignment.MainTankGuid.IsEmpty())
                    assignment.MainTankGuid = member->GetGUID();
                else if (assignment.OffTankGuid.IsEmpty())
                    assignment.OffTankGuid = member->GetGUID();
                ++assignment.TankCount;
            }
            else if (role == "healer")
            {
                ++assignment.HealerCount;
            }
            else
                ++assignment.DpsCount;

            if (member == bot)
            {
                if (role == "tank")
                    assignment.RoleIndex = assignment.TankCount;
                else if (role == "healer")
                    assignment.RoleIndex = assignment.HealerCount;
                else
                    assignment.RoleIndex = assignment.DpsCount;
                assignment.Role = role;
            }
        }
    }

    if (!assignment.RaidSize)
    {
        assignment.RaidSize = 1;
        assignment.RoleIndex = 1;
        if (assignment.Role == "tank")
        {
            assignment.TankCount = 1;
            assignment.MainTankGuid = bot->GetGUID();
        }
        else if (assignment.Role == "healer")
            assignment.HealerCount = 1;
        else
            assignment.DpsCount = 1;
    }

    if (assignment.MainTankGuid.IsEmpty() && assignment.Role == "tank")
        assignment.MainTankGuid = bot->GetGUID();

    if (!assignment.RosterSlotId.empty())
        for (RaidRosterPlanSlot const& slot : BuildRosterPlan())
            if (slot.RosterSlotId == assignment.RosterSlotId)
            {
                assignment.SubGroup = slot.SubGroup;
                assignment.RoleIndex = slot.SlotIndex + 1;
                break;
            }

    return assignment;
}

BotWorldPopulationMgr::RaidPositioningAnchors BotWorldPopulationMgr::BuildRaidPositioningAnchors(Player* bot, Unit const* boss, RaidRoleAssignment const& assignment, BossMechanicFeatures const& features) const
{
    RaidPositioningAnchors anchors;
    if (!bot || Party().ValidationRouteManifestIndex >= Party().ValidationRouteManifest.size())
        return anchors;

    ValidationRouteManifestNode const& contract = Party().ValidationRouteManifest[Party().ValidationRouteManifestIndex];
    if (!contract.MechanicContractResolved || contract.FormationFamily.empty())
        return anchors;
    uint32 oneBasedSlot = assignment.RoleIndex;
    uint32 scopeOrdinal = 0;
    uint32 scopeCount = 0;
    uint32 currentSlotIndex = oneBasedSlot ? oneBasedSlot - 1 : 0;
    auto currentRoster = Cohort().Raid.RosterByGuid.find(bot->GetGUID().GetCounter());
    if (currentRoster != Cohort().Raid.RosterByGuid.end())
    {
        currentSlotIndex = currentRoster->second.SlotIndex;
        oneBasedSlot = currentSlotIndex + 1;
    }
    for (auto const& [guid, slot] : Cohort().Raid.RosterByGuid)
    {
        bool inScope = contract.FormationScope == "raid"
            || (contract.FormationScope == "role" && slot.Role == assignment.Role)
            || (contract.FormationScope == "subgroup" && slot.SubGroup == assignment.SubGroup);
        if (!inScope)
            continue;
        if (slot.SlotIndex < currentSlotIndex)
            ++scopeOrdinal;
        ++scopeCount;
    }
    if (!scopeCount)
    {
        scopeOrdinal = currentSlotIndex;
        scopeCount = std::max<uint32>(1, assignment.RaidSize);
    }
    anchors.Active = bot->GetMap() && bot->GetMap()->IsRaid();
    anchors.FormationFamily = contract.FormationFamily;
    anchors.ArrivalToleranceYards = contract.FormationArrivalToleranceYards;
    Unit const* anchor = nullptr;
    if (contract.FormationAnchor == "boss")
        anchor = boss;
    else if (contract.FormationAnchor == "main_tank" && !assignment.MainTankGuid.IsEmpty())
        anchor = ObjectAccessor::FindPlayer(assignment.MainTankGuid);
    else if (contract.FormationAnchor == "raid_leader" && !assignment.RaidLeaderGuid.IsEmpty())
        anchor = ObjectAccessor::FindPlayer(assignment.RaidLeaderGuid);
    else if (contract.FormationAnchor == "role" || contract.FormationAnchor == "subgroup")
    {
        uint32 bestSlot = std::numeric_limits<uint32>::max();
        for (auto const& [guid, slot] : Cohort().Raid.RosterByGuid)
        {
            bool matches = contract.FormationAnchor == "role"
                ? slot.Role == assignment.Role : slot.SubGroup == assignment.SubGroup;
            if (!matches || slot.SlotIndex >= bestSlot)
                continue;
            if (Player* candidate = ObjectAccessor::FindPlayer(slot.Guid);
                candidate && candidate->IsAlive() && candidate->GetMap() == bot->GetMap())
            {
                bestSlot = slot.SlotIndex;
                anchor = candidate;
            }
        }
    }
    if (contract.FormationAnchor == "route_anchor")
    {
        anchors.AnchorType = "route_anchor";
        anchors.AnchorX = contract.NavigationAnchorX;
        anchors.AnchorY = contract.NavigationAnchorY;
        anchors.AnchorZ = contract.NavigationAnchorZ;
    }
    else if (anchor && anchor->IsInWorld() && anchor->GetMap() == bot->GetMap())
    {
        anchors.AnchorType = contract.FormationAnchor;
        anchors.AnchorGuid = anchor->GetGUID();
        anchors.AnchorX = anchor->GetPositionX();
        anchors.AnchorY = anchor->GetPositionY();
        anchors.AnchorZ = anchor->GetPositionZ();
    }
    else
        return RaidPositioningAnchors();

    float baseAngle = contract.NavigationAnchorO;
    if (contract.FormationOrientation == "boss_facing" && boss)
        baseAngle = boss->GetOrientation();
    else if (contract.FormationOrientation == "anchor_to_boss" && boss)
        baseAngle = std::atan2(boss->GetPositionY() - anchors.AnchorY, boss->GetPositionX() - anchors.AnchorX);
    uint32 const ordinal = scopeOrdinal;
    uint32 const raidSize = std::max<uint32>(1, scopeCount);
    float forward = 0.0f;
    float lateral = 0.0f;
    float const spacing = std::max(contract.FormationSpacingYards, contract.FormationMinimumDistanceYards);
    float radial = std::max(contract.FormationRadiusYards, contract.FormationMinimumDistanceYards);
    if (raidSize > 1 && (contract.FormationFamily == "ring" || contract.FormationFamily == "spread"
        || contract.FormationFamily == "cone"))
    {
        float const arc = contract.FormationFamily == "cone" ? contract.FormationArcRadians : float(2.0 * M_PI);
        float const step = arc / float(contract.FormationFamily == "cone" ? raidSize - 1 : raidSize);
        if (step > 0.0f && contract.FormationMinimumDistanceYards > 0.0f)
            radial = std::max(radial, contract.FormationMinimumDistanceYards / (2.0f * std::sin(step * 0.5f)));
    }
    float angle = baseAngle;
    if (contract.FormationFamily == "pair")
    {
        forward = float(ordinal / 2) * spacing;
        lateral = (ordinal % 2 ? 0.5f : -0.5f) * spacing;
    }
    else if (contract.FormationFamily == "lane")
    {
        uint32 const lanes = contract.FormationLaneCount;
        forward = float(ordinal / lanes) * spacing;
        lateral = (float(ordinal % lanes) - float(lanes - 1) * 0.5f) * spacing;
    }
    else if (contract.FormationFamily == "quadrant")
    {
        angle += float(ordinal % 4) * float(M_PI * 0.5);
        radial *= float(1 + ordinal / 4);
    }
    else if (contract.FormationFamily == "ring" || contract.FormationFamily == "spread")
        angle += float(2.0 * M_PI) * float(ordinal) / float(raidSize);
    else if (contract.FormationFamily == "cone")
        angle += raidSize > 1
            ? -contract.FormationArcRadians * 0.5f + contract.FormationArcRadians * float(ordinal) / float(raidSize - 1)
            : 0.0f;
    else if (contract.FormationFamily == "behind" || contract.FormationFamily == "front_exclusion")
    {
        angle += float(M_PI);
        if (raidSize > 1)
            angle += -contract.FormationArcRadians * 0.5f
                + contract.FormationArcRadians * float(ordinal) / float(raidSize - 1);
    }

    if (contract.FormationFamily == "pair" || contract.FormationFamily == "lane")
    {
        anchors.ResolvedX = anchors.AnchorX + std::cos(baseAngle) * forward - std::sin(baseAngle) * lateral;
        anchors.ResolvedY = anchors.AnchorY + std::sin(baseAngle) * forward + std::cos(baseAngle) * lateral;
    }
    else
    {
        anchors.ResolvedX = anchors.AnchorX + std::cos(angle) * radial;
        anchors.ResolvedY = anchors.AnchorY + std::sin(angle) * radial;
    }
    anchors.ResolvedZ = anchors.AnchorZ;
    anchors.StackX = anchors.SpreadX = anchors.ResolvedX;
    anchors.StackY = anchors.SpreadY = anchors.ResolvedY;
    anchors.StackZ = anchors.SpreadZ = anchors.ResolvedZ;
    anchors.DistanceToAnchor = bot->GetExactDist2d(anchors.AnchorX, anchors.AnchorY);

    return anchors;
}

BotWorldPopulationMgr::RaidMechanicAdapter BotWorldPopulationMgr::BuildRaidMechanicAdapter(Player* bot, Unit const* /*boss*/, RaidRoleAssignment const& assignment, BossMechanicFeatures const& features) const
{
    RaidMechanicAdapter adapter;
    if (!bot)
        return adapter;

    ValidationRouteManifestNode const* contract = Party().ValidationRouteManifestIndex < Party().ValidationRouteManifest.size()
        ? &Party().ValidationRouteManifest[Party().ValidationRouteManifestIndex] : nullptr;
    if (contract)
    {
        adapter.ContractId = contract->MechanicContractId;
        adapter.ContractError = contract->MechanicContractError;
        adapter.ContractResolved = contract->MechanicContractResolved;
        adapter.FormationFamily = contract->FormationFamily.empty() ? "none" : contract->FormationFamily;
        adapter.FormationScope = contract->FormationScope;
        adapter.TargetControl = contract->TargetControl.empty() ? "focus_fire" : contract->TargetControl;
        adapter.AllowAreaDamage = contract->AllowAreaDamage;
        adapter.AllowMultidot = contract->AllowMultidot;
        adapter.TargetEntries = contract->TargetEntries;
        adapter.ControlledAoeMinimumTargets = contract->ControlledAoeMinimumTargets;
        adapter.KillSyncTolerancePct = contract->KillSyncTolerancePct;
        adapter.KillSyncExecutionFloorPct = contract->KillSyncExecutionFloorPct;
        adapter.TankSwapTrigger = contract->TankSwapTrigger;
        adapter.TankSwapAuraId = contract->TankSwapAuraId;
        adapter.TankSwapAuraStacks = contract->TankSwapAuraStacks;
        adapter.TankSwapIntervalMs = contract->TankSwapIntervalMs;
        adapter.TankSwapTriggerSpellId = contract->TankSwapTriggerSpellId;
        adapter.TankSwapAddEntry = contract->TankSwapAddEntry;
        adapter.TankSwapPhase = contract->TankSwapPhase;
        adapter.InterruptOwnerSlot = contract->InterruptOwnerSlot;
        adapter.InterruptBackupSlot = contract->InterruptBackupSlot;
        adapter.InterruptTriggerSpellId = contract->InterruptTriggerSpellId;
        adapter.InteractableEntry = contract->InteractableEntry;
        adapter.VehicleEntry = contract->VehicleEntry;
        adapter.TransportEntry = contract->TransportEntry;
        adapter.TransferAreaTriggerId = contract->TransferAreaTriggerId;
        adapter.ExtraActionSpellId = contract->ExtraActionSpellId;
        adapter.ExtraActionTriggerAuraId = contract->ExtraActionTriggerAuraId;
        adapter.DispelAuraId = contract->DispelAuraId;
        adapter.DispelOwnerSlot = contract->DispelOwnerSlot;
        adapter.DispelBackupSlot = contract->DispelBackupSlot;
        adapter.CooldownCategory = contract->CooldownCategory;
        adapter.CooldownOwnerSlot = contract->CooldownOwnerSlot;
        adapter.CooldownBackupSlot = contract->CooldownBackupSlot;
        adapter.CooldownTriggerSpellId = contract->CooldownTriggerSpellId;
        adapter.CooldownTarget = contract->CooldownTarget;
        adapter.HealerOwnership = contract->HealerOwnership;
        adapter.HealerOwnerSlots = contract->HealerOwnerSlots;
        adapter.SoakRosterSlots = contract->SoakRosterSlots;
        adapter.SoakMinimumCount = contract->SoakMinimumCount;
        adapter.SoakRadiusYards = contract->SoakRadiusYards;
        adapter.SoakTriggerSpellId = contract->SoakTriggerSpellId;
        adapter.SoakTriggerAuraId = contract->SoakTriggerAuraId;
        adapter.SoakImmunitySpellId = contract->SoakImmunitySpellId;
        adapter.SoakPersonalCooldownSpellId = contract->SoakPersonalCooldownSpellId;
        adapter.BattleResurrectionPolicy = contract->BattleResurrectionPolicy;
        adapter.BattleResurrectionSlots = contract->BattleResurrectionSlots;
        adapter.InteractionKind = contract->InteractionKind;
        adapter.JumpPadEntry = contract->JumpPadEntry;
        adapter.MovementLink = contract->MovementLink;
        adapter.PlatformPolicy = contract->PlatformPolicy;
        adapter.PlatformDestinationMapId = contract->PlatformDestinationMapId;
        adapter.PlatformDestinationAreaId = contract->PlatformDestinationAreaId;
        adapter.PlatformMinimumZ = contract->PlatformMinimumZ;
        adapter.PlatformMaximumZ = contract->PlatformMaximumZ;
    }

    adapter.Priority = features.DangerScore;
    adapter.AssignedTargetGuid = features.BossGuid;
    adapter.EvidenceGuid = features.CastSpellId ? features.BossGuid
        : (!features.PriorityAddGuid.IsEmpty() ? features.PriorityAddGuid
            : (!features.InteractableGuid.IsEmpty() ? features.InteractableGuid
                : (!features.VehicleGuid.IsEmpty() ? features.VehicleGuid : features.TransportGuid)));
    adapter.TriggerSpellId = features.CastSpellId;
    adapter.HeroicOnly = BotLongTermProgressionBrain::ClassifyStage(bot, BotLongTermProgressionBrain::CalculateRolePower(bot)) == BotProgressionStage::HeroicRaid;
    adapter.AssignmentObserved = !adapter.AssignedTargetGuid.IsEmpty() || !assignment.RosterSlotId.empty();
    adapter.EvidenceObserved = !adapter.EvidenceGuid.IsEmpty();
    adapter.RotationDirective = assignment.ClassSpec.empty() ? "db_profile_declared_class_unknown" : "db_profile_declared:" + assignment.ClassSpec;
    std::string const& declaredProfile = Cohort().Config.ValidationRouteMechanicProfile;
    if (!declaredProfile.empty())
        adapter.RotationDirective += ";pinned_strategy:" + declaredProfile;

    if (!adapter.ContractResolved)
    {
        adapter.AssignmentType = "contract_unresolved";
        adapter.RecommendedAction = "fail_closed_no_fidelity_acceptance";
        return adapter;
    }

    if (assignment.Role == "healer")
        adapter.HealDirective = features.RaidDamage ? "raid_damage_triage_and_cooldown" : "single_target_triage";
    if (features.RaidDamage)
        adapter.SoakDirective = features.StackPlaceholder ? "stack_anchor_observed" : "raid_damage_observed";
    if (features.DangerousCast)
        adapter.CooldownDirective = "native_cooldown_candidate_from_spell_observation";
    if (features.InteractableObserved)
        adapter.InteractableDirective = "native_interactable_observed";
    if (features.VehicleObserved)
        adapter.VehicleDirective = "native_vehicle_observed";
    if (features.TransportObserved)
        adapter.TransportDirective = "native_transport_observed";
    if (features.PlatformTransferObserved)
        adapter.PlatformTransferDirective = "native_transfer_candidate_observed";

    if (features.TankSpike)
    {
        adapter.MechanicFamily = "tank_swap";
        adapter.AssignmentType = assignment.Role == "tank" ? "tank_swap" : "maintain_role";
        adapter.RecommendedAction = assignment.Role == "tank" ? "tank_boss_position" : "avoid_front";
        adapter.SwapTrigger = features.CastSpellId ? "native_tank_spike_spell" : "native_tank_spike_observation";
        adapter.Priority += 0.25f;
    }
    else if (features.MustInterrupt)
    {
        adapter.MechanicFamily = "interrupt_rotation";
        adapter.AssignmentType = "interrupt";
        adapter.RecommendedAction = "interrupt_must_interrupt";
        adapter.Priority += 0.35f;
    }
    else if (features.RaidDamage)
    {
        adapter.MechanicFamily = "raid_wide_aoe";
        adapter.AssignmentType = assignment.Role == "healer" ? "healer_cooldown" : "stack";
        adapter.RecommendedAction = assignment.Role == "healer" ? "heal_raid_damage" : "raid_stack_anchor";
        adapter.Priority += 0.20f;
    }
    else if (features.MoveOut || features.SpreadPlaceholder)
    {
        adapter.MechanicFamily = "spread";
        adapter.AssignmentType = "spread";
        adapter.RecommendedAction = "raid_spread_anchor";
        adapter.Priority += 0.20f;
        adapter.SoakDirective = "spread_or_move_out_observed";
    }
    else if (features.AddsActive)
    {
        adapter.MechanicFamily = "add_wave";
        adapter.AssignmentType = assignment.Role == "healer" ? "maintain_role" : "target_switch";
        adapter.AssignedTargetGuid = features.PriorityAddGuid;
        adapter.RecommendedAction = assignment.Role == "healer" ? "heal_boss_damage" : "switch_to_adds";
        adapter.Priority += 0.15f;
        adapter.AssignmentObserved = !adapter.AssignedTargetGuid.IsEmpty();
    }

    if (adapter.MechanicFamily == "boss_pressure")
        adapter.RecommendedAction = assignment.Role == "tank" ? "tank_boss_position" : "boss_single_target";
    return adapter;
}

BotWorldPopulationMgr::RaidGearTargetPlan BotWorldPopulationMgr::BuildRaidGearTargetPlan(Player* bot, BotRolePowerBreakdown const& /*power*/, BotProgressionStage stage) const
{
    RaidGearTargetPlan plan;
    if (!bot)
        return plan;

    plan.CurrentItemLevel = bot->GetAverageItemLevel();
    plan.TargetItemLevel = stage == BotProgressionStage::HeroicRaid ? 372.0f : 359.0f;
    plan.NeededItemLevel = std::max(0.0f, plan.TargetItemLevel - plan.CurrentItemLevel);
    plan.ReadyForRaid = plan.CurrentItemLevel >= 346.0f;
    plan.ReadyForHeroicRaid = plan.CurrentItemLevel >= 372.0f;
    if (!plan.ReadyForRaid)
        plan.RecommendedActivity = "heroic_dungeon";
    else if (!plan.ReadyForHeroicRaid)
        plan.RecommendedActivity = "raid";
    else
        plan.RecommendedActivity = "heroic_raid";
    return plan;
}

