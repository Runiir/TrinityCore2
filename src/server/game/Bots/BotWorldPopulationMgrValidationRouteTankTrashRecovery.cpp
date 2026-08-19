#include "Bots/BotWorldPopulationMgrValidationRouteTankTrashRecovery.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <string>
#include <utility>

namespace BotWorldPopulationMgrValidationRoute
{
bool ObjectiveContext::RunTankTrashRecovery(
    TankTrashRecoveryCallbacks const& callbacks)
{
    WorldBotState& state = State;
    Player* bot = Bot;
    BotRolePowerBreakdown const& power = Power;
    BotProgressionStage stage = Stage;
    BotProgressionActivity activity = Activity;
    std::string& situation = Situation;
    std::string& action = Action;
    Unit*& target = Target;
    Player* defenseTarget = callbacks.DefenseTarget();
    std::size_t defenseAttackerCount = callbacks.DefenseAttackerCount();
    TrashThreatControl& trashThreatControl =
        callbacks.TrashThreatControlResult();
    auto const& isProtectionProfile = callbacks.IsProtectionProfile;
    auto const& routeEngageRange = callbacks.RouteEngageRange;
    auto const& isImmediateNextValidationRouteEncounterMember =
        callbacks.IsImmediateNextValidationRouteEncounterMember;
    auto const& findTrashClusterThreatTarget =
        callbacks.FindTrashClusterThreatTarget;
    auto const& findLastKnownFocusTarget =
        callbacks.FindLastKnownFocusTarget;
    auto const& routeUsableCombatTarget = callbacks.RouteUsableCombatTarget;
    auto const& rememberValidationRouteFocus =
        callbacks.RememberValidationRouteFocus;
    auto Cohort = [this]() -> decltype(auto) { return Manager.Cohort(); };
    auto GetDungeonRole = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.GetDungeonRole(std::forward<decltype(args)>(args)...);
    };
    auto BuildRawJson = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.BuildRawJson(std::forward<decltype(args)>(args)...);
    };
    auto BuildSemanticJson = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.BuildSemanticJson(
            std::forward<decltype(args)>(args)...);
    };
    auto RecordEvent = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.RecordEvent(std::forward<decltype(args)>(args)...);
    };
    auto TryCastFriendlySpell = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.TryCastFriendlySpell(
            std::forward<decltype(args)>(args)...);
    };
    auto TryCastCombatSpell = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.TryCastCombatSpell(
            std::forward<decltype(args)>(args)...);
    };
    auto ResolveProfileCombatAction = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.ResolveProfileCombatAction(
            std::forward<decltype(args)>(args)...);
    };
    auto ExecuteProfileCombatAction = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.ExecuteProfileCombatAction(
            std::forward<decltype(args)>(args)...);
    };
    auto MoveBotToProfileRange = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MoveBotToProfileRange(
            std::forward<decltype(args)>(args)...);
    };
    auto MoveBotToPoint = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MoveBotToPoint(
            std::forward<decltype(args)>(args)...);
    };
    using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
    // Rerun157 localized 28 of 37 Protection healer-target samples to four
    // corridor attackers that remained on the healer while the native
    // pickup chain ran serially. Boss waves already use Hand of Protection
    // as an emergency victim break. Apply the same native protection before
    // ordinary-trash recovery only at three or more healer attackers; the
    // unchanged threat controller still has to acquire and retain the pack.
    // Rerun158 then observed the first exposed sample one decision before
    // that threshold, followed by successful protection and full recovery
    // within 1012 ms. Protect on the first healer attacker so the same
    // native recovery chain starts before the strict exposure ratio fails.
    // Blood/warrior tanks use a single-target native taunt instead of the
    // Protection-specific pickup chain below.  The first Stonecore 5H
    // trace exposed exactly this gap: Dark Command was learned and legal,
    // but no dungeon threat branch submitted it when Millhouse remained on
    // the healer, so the tank died with nine other hostiles already owned.
    if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
        && defenseAttackerCount >= 1
        && (bot->getClass() == CLASS_DEATH_KNIGHT
            || bot->getClass() == CLASS_WARRIOR))
    {
        uint32 tauntSpell = bot->getClass() == CLASS_DEATH_KNIGHT ? 56222 : 355;
        Unit* healerTauntTarget = nullptr;
        float healerTauntDistance = std::numeric_limits<float>::max();
        uint32 healerTauntGuid = std::numeric_limits<uint32>::max();
        auto considerHealerTauntTarget = [&](Unit* attacker)
        {
            if (!attacker || !attacker->IsAlive()
                || attacker->GetVictim() != defenseTarget
                || !bot->IsValidAttackTarget(attacker))
                return;
            float distance = bot->GetExactDist(attacker);
            uint32 guid = attacker->GetGUID().GetCounter();
            if (!healerTauntTarget || distance < healerTauntDistance
                || (distance == healerTauntDistance && guid < healerTauntGuid))
            {
                healerTauntTarget = attacker;
                healerTauntDistance = distance;
                healerTauntGuid = guid;
            }
        };
        for (Unit* attacker : trashThreatControl.HealerOwnedTargets)
            considerHealerTauntTarget(attacker);
        if (!healerTauntTarget)
            for (Unit* attacker : defenseTarget->getAttackers())
                considerHealerTauntTarget(attacker);

        if (healerTauntTarget && bot->HasSpell(tauntSpell)
            && TryCastCombatSpell(bot, healerTauntTarget, tauntSpell))
        {
            std::string raw = BuildRawJson(bot, healerTauntTarget);
            std::string semantic = BuildSemanticJson(
                bot, healerTauntTarget, "normal_dungeon_trash",
                &power, stage, activity);
            char const* tauntAction = bot->getClass() == CLASS_DEATH_KNIGHT
                ? "dark_command_healer_trash_pickup"
                : "taunt_healer_trash_pickup";
            RecordEvent(state, bot, "validation_route_threat_pickup",
                healerTauntTarget, tauntAction, raw.c_str(),
                semantic.c_str(), healerTauntDistance,
                float(defenseAttackerCount), tauntSpell);
            state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);
            state.TargetGuid = healerTauntTarget->GetGUID();
            target = healerTauntTarget;
            situation = "normal_dungeon_trash";
            action = tauntAction;
            state.WasInCombat = true;
            return true;
        }
    }

    // The route threat controller intentionally owns the tank decision, so
    // the ordinary class-profile survival rows are otherwise never reached
    // during a dense opening pack.  Preserve the native defensive lane for
    // a Blood DK before another area-threat retry: Icebound Fortitude buys
    // time at critical health and Death Strike uses the current hostile to
    // convert the recent damage window into a native self-heal.  No health,
    // aura, threat, or cooldown state is manufactured here.
    if (bot->getClass() == CLASS_DEATH_KNIGHT)
    {
        Unit* deathStrikeTarget = trashThreatControl.AreaTarget;
        if (!deathStrikeTarget || !deathStrikeTarget->IsAlive()
            || !bot->IsValidAttackTarget(deathStrikeTarget))
            deathStrikeTarget = bot->GetVictim();

        if (UnitHealthPct(bot) <= 0.75f && deathStrikeTarget
            && deathStrikeTarget->IsAlive()
            && bot->IsValidAttackTarget(deathStrikeTarget)
            && bot->HasSpell(49998)
            && TryCastCombatSpell(bot, deathStrikeTarget, 49998))
        {
            std::string raw = BuildRawJson(bot, deathStrikeTarget);
            std::string semantic = BuildSemanticJson(
                bot, deathStrikeTarget, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "defensive",
                deathStrikeTarget, "tank_trash_death_strike",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist(deathStrikeTarget),
                trashThreatControl.EngagedCount, 49998);
            state.TargetGuid = deathStrikeTarget->GetGUID();
            target = deathStrikeTarget;
            situation = "normal_dungeon_trash";
            action = "tank_trash_death_strike";
            state.WasInCombat = true;
            return true;
        }

        // Death Strike is the only immediate native self-heal in this
        // emergency lane.  Give it first refusal so a low-health tank
        // does not spend the decision/GCD on Icebound Fortitude and die
        // before the heal can land.  Icebound remains the bounded
        // fallback mitigation when Death Strike is unavailable or fails.
        if (UnitHealthPct(bot) <= 0.55f && bot->HasSpell(48792)
            && !bot->HasAura(48792)
            && TryCastFriendlySpell(bot, bot, 48792))
        {
            std::string raw = BuildRawJson(bot, deathStrikeTarget);
            std::string semantic = BuildSemanticJson(
                bot, deathStrikeTarget, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "defensive",
                bot, "tank_trash_icebound_fortitude",
                raw.c_str(), semantic.c_str(), UnitHealthPct(bot),
                trashThreatControl.EngagedCount, 48792);
            situation = "normal_dungeon_trash";
            action = "tank_trash_icebound_fortitude";
            return true;
        }
    }
    if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
        && defenseAttackerCount >= 1
        && bot->HasSpell(1022) && !defenseTarget->HasAura(1022)
        && TryCastFriendlySpell(bot, defenseTarget, 1022))
    {
        std::string raw = BuildRawJson(bot, defenseTarget);
        std::string semantic = BuildSemanticJson(bot, defenseTarget,
            "normal_dungeon_trash", &power, stage,
            activity);
        RecordEvent(state, bot, "external_defensive", defenseTarget,
            "hand_of_protection_healer_trash_emergency", raw.c_str(),
            semantic.c_str(), float(defenseAttackerCount),
            Cohort().Config.ValidationRouteTargetEntry, 1022);
        situation = "normal_dungeon_trash";
        action = "hand_of_protection_healer_trash_emergency";
        return true;
    }
    // Rerun145 localized Protection's only healer exposure to a two-add
    // corridor handoff: targeted Righteous Defense returned first, then
    // route movement displaced the adjacent native area pickup beyond the
    // strict dwell ceiling. When both adds are already inside the unchanged
    // Consecration radius, submit that existing native area threat first.
    // Righteous Defense remains the immediate fallback if the cast is not
    // legal, ready, or successful.
    if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
        && defenseAttackerCount >= 2
        && bot->GetExactDist2d(defenseTarget) <= 8.0f
        && bot->HasSpell(26573) && TryCastFriendlySpell(bot, bot, 26573))
    {
        std::string raw = BuildRawJson(bot, defenseTarget);
        std::string semantic = BuildSemanticJson(bot, defenseTarget,
            "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_pickup",
            defenseTarget, "consecration_healer_multi_trash_pickup",
            raw.c_str(), semantic.c_str(), float(defenseAttackerCount),
            Cohort().Config.ValidationRouteTargetEntry, 26573);
        situation = "normal_dungeon_trash";
        action = "consecration_healer_multi_trash_pickup";
        return true;
    }
    if (defenseTarget && bot->HasSpell(31789) && TryCastFriendlySpell(bot, defenseTarget, 31789))
    {
        Unit* pickupTarget = nullptr;
        uint32 pickupGuid = std::numeric_limits<uint32>::max();
        for (Unit* attacker : defenseTarget->getAttackers())
        {
            if (!attacker || !attacker->IsAlive() || !bot->IsValidAttackTarget(attacker))
                continue;
            uint32 guid = attacker->GetGUID().GetCounter();
            if (!pickupTarget || guid < pickupGuid)
            {
                pickupTarget = attacker;
                pickupGuid = guid;
            }
        }
        if (pickupTarget)
        {
            target = pickupTarget;
            state.TargetGuid = pickupTarget->GetGUID();
        }
        bool healerPickup = std::string(GetDungeonRole(defenseTarget)) == "healer";
        char const* pickupAction = healerPickup ? "righteous_defense_healer_pickup" : "righteous_defense_party_pickup";
        std::string raw = BuildRawJson(bot, defenseTarget);
        std::string semantic = BuildSemanticJson(bot, defenseTarget, "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_pickup", defenseTarget, pickupAction,
            raw.c_str(), semantic.c_str(), float(defenseAttackerCount), Cohort().Config.ValidationRouteTargetEntry, 31789);
        situation = "normal_dungeon_trash";
        action = pickupAction;
        return true;
    }
    // Rerun170 retained 17 eligible healer-target samples after every
    // multi-target Protection pickup remained native and successful. Twelve
    // samples came from three continuously engaged hostiles reacquiring the
    // healer together while Righteous Defense was unavailable; Avenger's
    // Shield and the next area action needed several telemetry ticks to
    // recover all three. Use the otherwise configured native single taunt
    // against one deterministic healer attacker before the multi-target
    // fallbacks, then poll the remaining exact exposure at 250 ms. This does
    // not assign threat directly and leaves every spell legality gate native.
    if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
        && defenseAttackerCount >= 1
        && isProtectionProfile()
        && bot->HasSpell(62124))
    {
        Unit* healerTauntTarget = nullptr;
        float healerTauntDistance = std::numeric_limits<float>::max();
        uint32 healerTauntGuid = std::numeric_limits<uint32>::max();
        bool healerTauntRepeatsCurrentTarget = true;
        for (Unit* attacker : defenseTarget->getAttackers())
        {
            if (!attacker || !attacker->IsAlive()
                || !bot->IsValidAttackTarget(attacker))
                continue;
            float distance = bot->GetExactDist(attacker);
            uint32 guid = attacker->GetGUID().GetCounter();
            bool repeatsCurrentTarget =
                attacker->GetGUID() == state.TargetGuid;
            if (!healerTauntTarget
                || (healerTauntRepeatsCurrentTarget
                    && !repeatsCurrentTarget)
                || (healerTauntRepeatsCurrentTarget
                        == repeatsCurrentTarget
                    && (distance < healerTauntDistance
                        || (distance == healerTauntDistance
                            && guid < healerTauntGuid))))
            {
                healerTauntTarget = attacker;
                healerTauntDistance = distance;
                healerTauntGuid = guid;
                healerTauntRepeatsCurrentTarget =
                    repeatsCurrentTarget;
            }
        }
        if (healerTauntTarget
            && TryCastCombatSpell(bot, healerTauntTarget, 62124))
        {
            std::string raw = BuildRawJson(bot, healerTauntTarget);
            std::string semantic = BuildSemanticJson(bot,
                healerTauntTarget, "normal_dungeon_trash", &power,
                stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                healerTauntTarget,
                "hand_of_reckoning_healer_trash_pickup",
                raw.c_str(), semantic.c_str(), healerTauntDistance,
                float(defenseAttackerCount), 62124);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = healerTauntTarget->GetGUID();
            target = healerTauntTarget;
            situation = "normal_dungeon_trash";
            action = "hand_of_reckoning_healer_trash_pickup";
            state.WasInCombat = true;
            return true;
        }
    }
    // Rerun151 localized Protection's remaining healer exposure to a
    // remote two-hostile corridor handoff. Righteous Defense had just been
    // consumed on another party member, while the generic density resolver
    // selected ranged Hand of Reckoning through its melee movement
    // envelope and did not submit it until after the strict dwell ceiling.
    // Use the existing native ranged multi-target pickup directly when the
    // healer owns at least two attackers; every normal spell legality gate
    // remains inside TryCastCombatSpell and all established fallbacks stay
    // below this branch.
    if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
        && defenseAttackerCount >= 2 && bot->HasSpell(31935))
    {
        Unit* healerClusterTarget = nullptr;
        float healerClusterDistance = std::numeric_limits<float>::max();
        uint32 healerClusterGuid = std::numeric_limits<uint32>::max();
        for (Unit* attacker : defenseTarget->getAttackers())
        {
            if (!attacker || !attacker->IsAlive()
                || !bot->IsValidAttackTarget(attacker))
                continue;
            float distance = bot->GetExactDist(attacker);
            uint32 guid = attacker->GetGUID().GetCounter();
            if (!healerClusterTarget || distance < healerClusterDistance
                || (distance == healerClusterDistance
                    && guid < healerClusterGuid))
            {
                healerClusterTarget = attacker;
                healerClusterDistance = distance;
                healerClusterGuid = guid;
            }
        }
        if (healerClusterTarget
            && TryCastCombatSpell(bot, healerClusterTarget, 31935))
        {
            std::string raw = BuildRawJson(bot, healerClusterTarget);
            std::string semantic = BuildSemanticJson(bot,
                healerClusterTarget, "normal_dungeon_trash", &power,
                stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                healerClusterTarget,
                "avengers_shield_healer_multi_trash_pickup",
                raw.c_str(), semantic.c_str(), healerClusterDistance,
                float(defenseAttackerCount), 31935);
            state.TargetGuid = healerClusterTarget->GetGUID();
            target = healerClusterTarget;
            situation = "normal_dungeon_trash";
            action = "avengers_shield_healer_multi_trash_pickup";
            state.WasInCombat = true;
            return true;
        }
    }
    if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
        && bot->HasSpell(1038) && !defenseTarget->HasAura(1038)
        && TryCastFriendlySpell(bot, defenseTarget, 1038))
    {
        std::string raw = BuildRawJson(bot, defenseTarget);
        std::string semantic = BuildSemanticJson(bot, defenseTarget, "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_pickup", defenseTarget,
            "hand_of_salvation_healer_trash_threat_drop", raw.c_str(), semantic.c_str(),
            float(defenseAttackerCount), Cohort().Config.ValidationRouteTargetEntry, 1038);
        situation = "normal_dungeon_trash";
        action = "hand_of_salvation_healer_trash_threat_drop";
        return true;
    }
    if (defenseTarget && bot->GetExactDist2d(defenseTarget) <= 8.0f
        && bot->HasSpell(26573) && TryCastFriendlySpell(bot, bot, 26573))
    {
        bool healerPickup = std::string(GetDungeonRole(defenseTarget)) == "healer";
        char const* pickupAction = healerPickup ? "consecration_healer_trash_pickup" : "consecration_party_trash_pickup";
        std::string raw = BuildRawJson(bot, defenseTarget);
        std::string semantic = BuildSemanticJson(bot, defenseTarget, "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_pickup", defenseTarget, pickupAction,
            raw.c_str(), semantic.c_str(), float(defenseAttackerCount), Cohort().Config.ValidationRouteTargetEntry, 26573);
        situation = "normal_dungeon_trash";
        action = pickupAction;
        return true;
    }

    if (trashThreatControl.EngagedCount >= 3 && trashThreatControl.AreaTarget)
    {
        // Rerun142 proved continuous aura-fresh next-encounter adds could
        // outrank the actual dense wave and churn this target. Retain the
        // current tank-owned set and select its largest ten-yard cluster
        // first. Within equal-density clusters prefer a target missing this
        // Feral's Thrash aura, then preserve deterministic distance and GUID
        // ordering. This changes only the target passed to the native profile
        // resolver; cooldowns, victims, and threat remain intact.
        bool feralTankOwnedDensitySelected = false;
        // Rerun175's only 14 eligible healer-exposure samples all belonged
        // to one generation-13 Flayer. The existing remote-handoff path was
        // unavailable, then this proactive tank-owned cluster selector
        // repeatedly displaced the already-established healer-owned area
        // fallback. Four 250-ms movements toward that exact Flayer began
        // only when the tank briefly lost its victim majority; once the
        // majority recovered, density retook priority and dwell reached
        // 6421 ms. Keep the established healer-owned fallback authoritative
        // while any exact current healer threat exists. Its native profile
        // action, range, LOS, path, cooldown, GCD, and threat gates remain
        // unchanged, as does proactive density whenever the healer is clear.
        if (bot->getClass() == CLASS_DRUID
            && trashThreatControl.EngagedCount >= 12
            && trashThreatControl.TankOwnsTrashMajority
            && !feralCurrentHealerThreat)
        {
            Unit* densestTankOwnedClusterTarget = nullptr;
            bool densestTankOwnedClusterMissingThrash = false;
            uint32 densestTankOwnedClusterCount = 0;
            float densestTankOwnedClusterDistance =
                std::numeric_limits<float>::max();
            uint32 densestTankOwnedClusterGuid =
                std::numeric_limits<uint32>::max();
            for (Unit* candidate : trashThreatControl.TankOwnedTargets)
            {
                if (!candidate || !candidate->IsAlive()
                    || candidate->GetMap() != bot->GetMap()
                    || candidate->GetVictim() != trashThreatControl.Tank
                    || !bot->IsValidAttackTarget(candidate))
                    continue;
                uint32 clusterCount = 0;
                for (Unit* neighbor : trashThreatControl.TankOwnedTargets)
                    if (neighbor && neighbor->IsAlive()
                        && neighbor->GetMap() == bot->GetMap()
                        && neighbor->GetVictim() == trashThreatControl.Tank
                        && bot->IsValidAttackTarget(neighbor)
                        && candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                bool missingThrash =
                    !candidate->HasAura(77758, bot->GetGUID());
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!densestTankOwnedClusterTarget
                    || clusterCount > densestTankOwnedClusterCount
                    || (clusterCount == densestTankOwnedClusterCount
                        && (missingThrash
                            && !densestTankOwnedClusterMissingThrash))
                    || (clusterCount == densestTankOwnedClusterCount
                        && missingThrash
                            == densestTankOwnedClusterMissingThrash
                        && (distance < densestTankOwnedClusterDistance
                            || (distance == densestTankOwnedClusterDistance
                                && guid < densestTankOwnedClusterGuid))))
                {
                    densestTankOwnedClusterTarget = candidate;
                    densestTankOwnedClusterMissingThrash = missingThrash;
                    densestTankOwnedClusterCount = clusterCount;
                    densestTankOwnedClusterDistance = distance;
                    densestTankOwnedClusterGuid = guid;
                }
            }
            if (densestTankOwnedClusterTarget)
            {
                trashThreatControl.AreaTarget =
                    densestTankOwnedClusterTarget;
                feralTankOwnedDensitySelected = true;
            }
        }
        // Rerun140 proved the specialized Feral handoffs selected the
        // densest healer-owned cluster, but their generic area fallback
        // reverted to the nearest healer-owned hostile. Preserve that
        // established ten-yard cluster contract after every higher-priority
        // pickup branch has fallen through when the proactive tank-owned
        // large-wave selector above does not apply.
        if (!feralTankOwnedDensitySelected
            && bot->getClass() == CLASS_DRUID && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer")
        {
            Unit* densestHealerClusterTarget = nullptr;
            uint32 densestHealerClusterCount = 0;
            float densestHealerClusterDistance =
                std::numeric_limits<float>::max();
            uint32 densestHealerClusterGuid =
                std::numeric_limits<uint32>::max();
            for (Unit* candidate : trashThreatControl.HealerOwnedTargets)
            {
                if (!candidate || !candidate->IsAlive()
                    || candidate->GetMap() != bot->GetMap()
                    || candidate->GetVictim() != defenseTarget
                    || !bot->IsValidAttackTarget(candidate))
                    continue;
                uint32 clusterCount = 0;
                for (Unit* neighbor : trashThreatControl.HealerOwnedTargets)
                    if (neighbor && neighbor->IsAlive()
                        && neighbor->GetMap() == bot->GetMap()
                        && neighbor->GetVictim() == defenseTarget
                        && bot->IsValidAttackTarget(neighbor)
                        && candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!densestHealerClusterTarget
                    || clusterCount > densestHealerClusterCount
                    || (clusterCount == densestHealerClusterCount
                        && (distance < densestHealerClusterDistance
                            || (distance == densestHealerClusterDistance
                                && guid < densestHealerClusterGuid))))
                {
                    densestHealerClusterTarget = candidate;
                    densestHealerClusterCount = clusterCount;
                    densestHealerClusterDistance = distance;
                    densestHealerClusterGuid = guid;
                }
            }
            if (densestHealerClusterTarget)
                trashThreatControl.AreaTarget =
                    densestHealerClusterTarget;
        }
        target = trashThreatControl.AreaTarget;
        state.TargetGuid = target->GetGUID();
        Creature const* areaCreature = target->ToCreature();
        // Rerun143 proved that restricting shared focus to the declared
        // current pack can strand every follower while the tank is in
        // legitimate party-linked combat with adjacent trash. Preserve
        // rerun142's isolation boundary only for the manifest-classified
        // immediate-next encounter; all other tactical area targets remain
        // valid party assist focus.
        if (areaCreature
            && !isImmediateNextValidationRouteEncounterMember(areaCreature))
            rememberValidationRouteFocus(target);
        ResolvedCombatAction areaAction = ResolveProfileCombatAction(bot, target,
            trashThreatControl.EngagedCount, true);
        if (areaAction.Valid)
        {
            float engageRange = areaAction.MaxRange > 0.0f
                ? areaAction.MaxRange : routeEngageRange(bot, target, areaAction.SpellId);
            float targetDistance = bot->GetExactDist(target);
            if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
            {
                bool moved = MoveBotToProfileRange(state, bot, target, &areaAction);
                // Rerun170's longest Protection exposure began with three
                // one-second movement decisions toward healer-owned hostile
                // 9 and ended at 3017 ms. The native pickup succeeded on the
                // next decision, but only after the unchanged 3000-ms strict
                // dwell ceiling. Retry only this healer-protection approach
                // at the existing urgent pickup cadence; ordinary density
                // movement and every native spell/range gate stay unchanged.
                Player* areaVictim = target->GetVictim()
                    ? target->GetVictim()->ToPlayer() : nullptr;
                if (moved && isProtectionProfile()
                    && areaVictim
                    && std::string(GetDungeonRole(areaVictim)) == "healer")
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 250);
                situation = "normal_dungeon_trash";
                action = moved ? "move_to_trash_density" : "hold_tactical_path_rejected";
                return true;
            }

            BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &areaAction,
                trashThreatControl.EngagedCount, true);
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup", target, "trash_density_area_threat",
                raw.c_str(), semantic.c_str(), float(trashThreatControl.SecureTankCount),
                trashThreatControl.EngagedCount, result == BotActionResult::Ok ? areaAction.SpellId : 0);
            situation = "normal_dungeon_trash";
            action = "trash_density_area_threat";
            state.WasInCombat = true;
            return true;
        }
    }

    Unit* threatFocus = findTrashClusterThreatTarget();
    Player* threatVictim = threatFocus && threatFocus->GetVictim() ? threatFocus->GetVictim()->ToPlayer() : nullptr;
    bool loosePartyThreat = threatVictim && threatVictim->GetGroup() == bot->GetGroup()
        && std::string(GetDungeonRole(threatVictim)) != "tank";
    Unit* rememberedFocus = loosePartyThreat ? threatFocus : findLastKnownFocusTarget();
    if (!rememberedFocus)
        rememberedFocus = threatFocus;
    if (rememberedFocus && target != rememberedFocus && (rememberedFocus->GetVictim() != bot || !bot->GetVictim()))
    {
        target = rememberedFocus;
        state.TargetGuid = target->GetGUID();
    }
    return false;
}
}
