#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilTankThreatRecovery.h"

#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
bool Context::Run(TankThreatRecoveryRequest const& request)
{
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    BotProgressionStage stage = request.Stage;
    BotProgressionActivity activity = request.Activity;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
    Unit* add = request.Add;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    uint32 addCount = discovery.AddCount;
    std::vector<Creature*> const& localAdds = discovery.LocalAdds;
    bool cohortSwarmActive = discovery.CohortSwarmActive;
    std::string const& role = density.Role;
    BotClassSpecActionProfile const& profile = density.Profile;
    uint32 reservedAreaSpellId = density.ReservedAreaSpellId;
    Player* densityTank = density.DensityTank;
    Player* densityHealer = density.DensityHealer;
    Player* densityDefenseTarget = density.DensityDefenseTarget;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;
    std::function<bool(Unit*)> const& continueStableTankSwarmApproach =
        request.ContinueStableTankSwarmApproach;
    std::function<float(Player*, Unit const*, uint32)> const& routeEngageRange =
        request.RouteEngageRange;

    // Rerun210's maximum-dwell identity was the one survivor after
    // Thunder Clap acquired the rest of an eleven-follower healer wave.
    // A newer, larger damage-role cluster then won density selection for
    // the next nine seconds, so the Warrior never submitted its ready
    // single-target Taunt against that residual healer threat.  Preserve
    // density priority for the larger damage-role swarm, but peel only a
    // bounded one- or two-attacker healer remainder first with the
    // Warrior's existing native Taunt. Rerun211 proved the same remainder
    // can itself be the selected defense target after a recovery; it must
    // receive the identical Taunt instead of falling through to density
    // holds. Lowest GUID is the deterministic oldest-spawn tie-breaker;
    // all cooldown, range, LOS, target, stance, and spell-legality gates
    // remain native.
    size_t warriorHealerAttackerCount = densityHealer
        ? observedListedAttackerCount(densityHealer) : 0;
    Creature* warriorResidualHealerAdd = nullptr;
    uint32 warriorResidualHealerGuid =
        std::numeric_limits<uint32>::max();
    if (role == "tank" && profile.SpecTag == "protection_warrior"
        && densityHealer && warriorHealerAttackerCount > 0
        && warriorHealerAttackerCount < 3)
    {
        for (Creature* candidate : localAdds)
        {
            if (!candidate || candidate->GetVictim() != densityHealer)
                continue;
            uint32 guid = candidate->GetGUID().GetCounter();
            if (!warriorResidualHealerAdd
                || guid < warriorResidualHealerGuid)
            {
                warriorResidualHealerAdd = candidate;
                warriorResidualHealerGuid = guid;
            }
        }
        if (warriorResidualHealerAdd && bot->HasSpell(355)
            && manager.TryCastCombatSpell(bot, warriorResidualHealerAdd, 355))
        {
            std::string raw = manager.BuildRawJson(
                bot, warriorResidualHealerAdd);
            std::string semantic = manager.BuildSemanticJson(
                bot, warriorResidualHealerAdd, "dungeon_boss", &power,
                stage, activity);
            manager.RecordEvent(state, bot, "boss_adds",
                warriorResidualHealerAdd,
                "warrior_taunt_residual_healer_threat", raw.c_str(),
                semantic.c_str(),
                bot->GetExactDist(warriorResidualHealerAdd),
                float(warriorHealerAttackerCount), 355);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = warriorResidualHealerAdd->GetGUID();
            state.WasInCombat = true;
            target = warriorResidualHealerAdd;
            situation = "dungeon_boss";
            action = "warrior_taunt_residual_healer_threat";
            return true;
        }
    }

    // Rerun209's generation-14 maximum dwell began with fifteen Azil
    // followers on the Restoration Druid while Protection Warrior was
    // outside Thunder Clap range.  The tank spent six seconds on ordinary
    // ground approach and one single-target Taunt; the first native Thunder
    // Clap then acquired almost the complete wave immediately.  Use the
    // Warrior's already-known native Charge against the deterministic
    // healer-owned density representative before area-profile movement.
    // A successful Charge keeps the ordinary one-second decision interval
    // so its native movement can finish before Thunder Clap resolution.
    // Native range, LOS, cooldown, stance, combat, GCD, power, and spell
    // legality remain authoritative.  Rejection falls through unchanged,
    // but polls this exact urgent healer handoff at the established 250 ms
    // pickup cadence.
    if (role == "tank" && profile.SpecTag == "protection_warrior"
        && densityHealer && densityDefenseTarget == densityHealer
        && add && add->GetVictim() == densityHealer
        && warriorHealerAttackerCount >= 3
        && bot->GetExactDist(add) > 8.0f && bot->HasSpell(100))
    {
        if (manager.TryCastCombatSpell(bot, add, 100))
        {
            std::string raw = manager.BuildRawJson(bot, add);
            std::string semantic = manager.BuildSemanticJson(
                bot, add, "dungeon_boss", &power, stage, activity);
            manager.RecordEvent(state, bot, "boss_add_density", add,
                "warrior_charge_healer_swarm_pickup", raw.c_str(),
                semantic.c_str(), bot->GetExactDist(add), addCount, 100);
            state.TargetGuid = add->GetGUID();
            state.WasInCombat = true;
            target = add;
            situation = "dungeon_boss";
            action = "warrior_charge_healer_swarm_pickup";
            return true;
        }
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);
    }

    // Rerun210 proved the complementary native dead zone.  The densest
    // healer-owned representative could already be below Charge's
    // eight-yard minimum while still outside the melee range required by
    // the Thunder Clap profile.  That path spent up to 3.322 seconds
    // approaching before the first area cast, and new waves could extend
    // the same identity beyond the dwell ceiling.  Shockwave is already
    // known by the provisioned Warrior; the prior 771/771 out-of-range
    // result came from unbounded remote submissions.  Permit it only in
    // this explicit greater-than-five and at-most-ten-yard gap, after the
    // native Charge attempt and before generic area movement.  Native
    // facing, range, LOS, cooldown, GCD, power, and cast legality remain
    // authoritative, and rejection preserves the existing chain.
    if (role == "tank" && profile.SpecTag == "protection_warrior"
        && densityHealer && densityDefenseTarget == densityHealer
        && add && add->GetVictim() == densityHealer
        && warriorHealerAttackerCount >= 3
        && bot->GetExactDist(add) > 5.0f
        && bot->GetExactDist(add) <= 10.0f
        && bot->HasSpell(46968)
        && manager.TryCastCombatSpell(bot, add, 46968))
    {
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(
            bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_add_density", add,
            "warrior_shockwave_healer_swarm_gap", raw.c_str(),
            semantic.c_str(), bot->GetExactDist(add),
            float(warriorHealerAttackerCount), 46968);
        state.TargetGuid = add->GetGUID();
        state.WasInCombat = true;
        target = add;
        situation = "dungeon_boss";
        action = "warrior_shockwave_healer_swarm_gap";
        return true;
    }

    // On a multi-target wave, establish area threat before spending
    // decision ticks on individual taunts.  Corborus and Azil can assign
    // a complete spawn burst to healing threat in one tick; alternating
    // Righteous Defense, Hand of Reckoning, and movement allowed the
    // oldest adds to remain on the healer for several seconds.  Use the
    // configured Protection AoE profile immediately and fall through to
    // the rescue tools only while every legal area action is unavailable.
    if (role == "tank" && add && addCount >= 2)
    {
        size_t protectionHealerAttackerCount = densityHealer
            ? observedListedAttackerCount(densityHealer) : 0;
        // Rerun192 showed two distinct Protection starvation paths.  A
        // ready multi-target Righteous Defense acquired a prior nine-add
        // Azil wave within one telemetry tick, but a later wave spent its
        // opening GCD on Consecration first and then could not submit the
        // same native rescue until 3063 ms.  Prefer only that existing
        // multi-target rescue before area-GCD spending while two or more
        // exact hostiles own the healer; every native cooldown, range,
        // target, and spell-legality gate remains authoritative.
        if (profile.SpecTag == "protection" && densityHealer
            && protectionHealerAttackerCount >= 2
            && bot->HasSpell(31789)
            && manager.TryCastFriendlySpell(bot, densityHealer, 31789))
        {
            std::string raw = manager.BuildRawJson(bot, densityHealer);
            std::string semantic = manager.BuildSemanticJson(
                bot, densityHealer, "dungeon_boss", &power, stage,
                activity);
            manager.RecordEvent(state, bot, "boss_adds", densityHealer,
                "righteous_defense_healer_before_area_gcd",
                raw.c_str(), semantic.c_str(),
                float(protectionHealerAttackerCount), addCount, 31789);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = add->GetGUID();
            target = add;
            situation = "dungeon_boss";
            action = "righteous_defense_healer_before_area_gcd";
            return true;
        }
        // Rerun197 captured the complementary native-rescue starvation
        // path. Righteous Defense was unavailable or rejected against a
        // twelve-follower healer wave, Hammer acquired only half of it,
        // and valid area movement then returned on every decision until
        // the existing Hand of Protection emergency below became
        // reachable 6646 ms later. Try that same native defensive before
        // area-GCD work only for the already-established five-attacker
        // emergency. Native aura, target, cooldown, range, and spell
        // legality remain authoritative; rejection falls through to the
        // unchanged area and rescue chain.
        if (profile.SpecTag == "protection" && densityHealer
            && protectionHealerAttackerCount >= 5
            && bot->HasSpell(1022) && !densityHealer->HasAura(1022)
            && manager.TryCastFriendlySpell(bot, densityHealer, 1022))
        {
            std::string raw = manager.BuildRawJson(bot, densityHealer);
            std::string semantic = manager.BuildSemanticJson(
                bot, densityHealer, "dungeon_boss", &power, stage,
                activity);
            manager.RecordEvent(state, bot, "external_defensive", densityHealer,
                "hand_of_protection_healer_before_area_gcd",
                raw.c_str(), semantic.c_str(),
                float(protectionHealerAttackerCount), addCount, 1022);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = add->GetGUID();
            target = add;
            situation = "dungeon_boss";
            action = "hand_of_protection_healer_before_area_gcd";
            return true;
        }
        // Rerun191 captured fifteen Azil followers on the healer while
        // Protection repeatedly preferred remote Hammer/Avenger targets.
        // Holy Wrath was natively ready, but the first local wave spent
        // 7.899 seconds cycling representatives before pickup. When a
        // majority of the healer-owned wave is already inside the tank's
        // ten-yard native area, prefer only configured self-centered area
        // actions. If none passes the unchanged profile and native gates,
        // preserve the ordinary area, rescue, and movement chain.
        uint32 localProtectionHealerOwnedCount = 0;
        if (profile.SpecTag == "protection" && densityHealer)
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == densityHealer
                    && bot->GetExactDist2d(candidate) <= 10.0f)
                    ++localProtectionHealerOwnedCount;
        bool preferSelfCenteredProtectionArea = profile.SpecTag == "protection"
            && localProtectionHealerOwnedCount >= 2
            && localProtectionHealerOwnedCount * 2
                >= protectionHealerAttackerCount;
        ResolvedCombatAction immediateAreaThreat = manager.ResolveProfileCombatAction(
            bot, add, addCount, true, reservedAreaSpellId, true,
            preferSelfCenteredProtectionArea);
        if (!immediateAreaThreat.Valid && preferSelfCenteredProtectionArea)
        {
            preferSelfCenteredProtectionArea = false;
            immediateAreaThreat = manager.ResolveProfileCombatAction(
                bot, add, addCount, true, reservedAreaSpellId, true);
        }
        if (immediateAreaThreat.Valid)
        {
            float engageRange = immediateAreaThreat.MaxRange > 0.0f
                ? immediateAreaThreat.MaxRange
                : routeEngageRange(bot, add, immediateAreaThreat.SpellId);
            uint32 selfCenteredTargets = 0;
            if (immediateAreaThreat.TargetGuid == bot->GetGUID())
                for (Creature* candidate : localAdds)
                    if (candidate && bot->GetExactDist2d(candidate) <= 10.0f)
                        ++selfCenteredTargets;
            // Local adds make self-centered AoE immediately useful only when
            // the selected urgent pickup is also inside its radius. Otherwise
            // move into the loose healer/DPS cluster before casting instead of
            // repeatedly hitting adds the tank already owns.
            //
            // Rerun201 proved one exception already encoded by the resolver:
            // a local majority of the healer-owned Azil wave selected ready
            // self-centered Holy Wrath, but the remote representative add
            // kept this final proximity conjunct false. Righteous Defense and
            // Hand of Reckoning made partial native pickups, Avenger's Shield
            // was on cooldown, and eight movement returns displaced the ready
            // area cast. When the bounded Protection local-majority preference
            // selected a self-centered action, honor that exact topology even
            // if the deterministic representative remains remote. All native
            // action, target-count, cooldown, GCD, power, and spell gates stay
            // inside the existing resolver and executor.
            bool preferredLocalProtectionAreaReady =
                preferSelfCenteredProtectionArea
                && immediateAreaThreat.TargetGuid == bot->GetGUID()
                && selfCenteredTargets >= 2;
            bool selfCenteredAreaReady = immediateAreaThreat.TargetGuid == bot->GetGUID()
                && selfCenteredTargets >= 2
                && (preferredLocalProtectionAreaReady
                    || !densityDefenseTarget
                    || bot->GetExactDist2d(add) <= 10.0f);
            bool approach = !selfCenteredAreaReady
                && (bot->GetExactDist(add) > std::max(5.0f, engageRange - 1.0f)
                    || !bot->IsWithinLOSInMap(add));
            if (approach)
            {
                // Rerun185 completed Azil but localized 554 healer-target
                // samples to repeated remote Protection add waves. The
                // configured self-centered area action was valid, so its
                // approach returned before the native ranged rescue chain
                // below could run; the longest wave spent 4617 ms moving
                // before Consecration and reached 6158 ms of healer dwell.
                // Only when the selected remote density add is currently
                // attacking the healer, try the same native Protection
                // rescue order already established for ordinary trash.
                // Failed or unavailable casts preserve the existing area
                // approach exactly, and no threat or victim is assigned.
                if (profile.SpecTag == "protection" && densityHealer
                    && densityDefenseTarget == densityHealer
                    && add->GetVictim() == densityHealer)
                {
                    uint32 healerAttackerCount =
                        observedListedAttackerCount(densityHealer);
                    if (bot->HasSpell(31789)
                        && manager.TryCastFriendlySpell(bot, densityHealer, 31789))
                    {
                        std::string raw = manager.BuildRawJson(bot, densityHealer);
                        std::string semantic = manager.BuildSemanticJson(
                            bot, densityHealer, "dungeon_boss", &power,
                            stage, activity);
                        manager.RecordEvent(state, bot, "boss_adds", densityHealer,
                            "righteous_defense_healer_before_area_approach",
                            raw.c_str(), semantic.c_str(),
                            float(healerAttackerCount), addCount, 31789);
                        state.DecisionTimer = std::min<uint32>(
                            state.DecisionTimer, 250);
                        state.TargetGuid = add->GetGUID();
                        target = add;
                        situation = "dungeon_boss";
                        action = "righteous_defense_healer_before_area_approach";
                        return true;
                    }
                    if (bot->HasSpell(62124)
                        && manager.TryCastCombatSpell(bot, add, 62124))
                    {
                        std::string raw = manager.BuildRawJson(bot, add);
                        std::string semantic = manager.BuildSemanticJson(
                            bot, add, "dungeon_boss", &power, stage,
                            activity);
                        manager.RecordEvent(state, bot, "boss_adds", add,
                            "hand_of_reckoning_healer_before_area_approach",
                            raw.c_str(), semantic.c_str(),
                            bot->GetExactDist(add),
                            float(healerAttackerCount), 62124);
                        state.DecisionTimer = std::min<uint32>(
                            state.DecisionTimer, 250);
                        state.TargetGuid = add->GetGUID();
                        state.WasInCombat = true;
                        target = add;
                        situation = "dungeon_boss";
                        action = "hand_of_reckoning_healer_before_area_approach";
                        return true;
                    }
                    if (healerAttackerCount >= 2 && bot->HasSpell(31935)
                        && manager.TryCastCombatSpell(bot, add, 31935))
                    {
                        std::string raw = manager.BuildRawJson(bot, add);
                        std::string semantic = manager.BuildSemanticJson(
                            bot, add, "dungeon_boss", &power, stage,
                            activity);
                        manager.RecordEvent(state, bot, "boss_adds", add,
                            "avengers_shield_healer_before_area_approach",
                            raw.c_str(), semantic.c_str(),
                            bot->GetExactDist(add),
                            float(healerAttackerCount), 31935);
                        state.DecisionTimer = std::min<uint32>(
                            state.DecisionTimer, 250);
                        state.TargetGuid = add->GetGUID();
                        state.WasInCombat = true;
                        target = add;
                        situation = "dungeon_boss";
                        action = "avengers_shield_healer_before_area_approach";
                        return true;
                    }
                }
                bool continuingStableApproach = continueStableTankSwarmApproach(add);
                bool moved = continuingStableApproach
                    || manager.MoveBotToProfileRange(state, bot, add, &immediateAreaThreat);
                char const* moveAction = continuingStableApproach
                    ? "tank_continue_stable_swarm_approach"
                    : (moved ? "tank_move_to_immediate_aoe_threat_range"
                             : "tank_immediate_aoe_threat_path_rejected");
                std::string raw = manager.BuildRawJson(bot, add);
                std::string semantic = manager.BuildSemanticJson(
                    bot, add, "dungeon_boss", &power, stage, activity);
                manager.RecordEvent(state, bot, "boss_add_density", add,
                    moveAction, raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(add), addCount, immediateAreaThreat.SpellId);
                state.TargetGuid = add->GetGUID();
                target = add;
                situation = "dungeon_boss";
                action = continuingStableApproach
                    ? "continue_stable_swarm_approach"
                    : (moved ? "move_to_immediate_aoe_threat_range"
                             : "hold_immediate_aoe_threat_range");
                return true;
            }

            BotActionResult areaResult = manager.ExecuteProfileCombatAction(
                &state, bot, add, &immediateAreaThreat, addCount, true,
                reservedAreaSpellId, true,
                preferSelfCenteredProtectionArea);
            if (areaResult == BotActionResult::Ok)
            {
                std::string raw = manager.BuildRawJson(bot, add);
                std::string semantic = manager.BuildSemanticJson(
                    bot, add, "dungeon_boss", &power, stage, activity);
                manager.RecordEvent(state, bot, "boss_add_density", add,
                    "tank_immediate_aoe_threat", raw.c_str(), semantic.c_str(),
                    float(addCount), densityHealer
                        ? float(observedListedAttackerCount(densityHealer)) : 0.0f,
                    immediateAreaThreat.SpellId);
                state.TargetGuid = add->GetGUID();
                state.WasInCombat = true;
                target = add;
                situation = "dungeon_boss";
                action = "tank_immediate_aoe_threat";
                return true;
            }
        }
    }

    if (role == "tank" && densityHealer
        && observedListedAttackerCount(densityHealer) >= 5
        && bot->HasSpell(1022) && !densityHealer->HasAura(1022)
        && manager.TryCastFriendlySpell(bot, densityHealer, 1022))
    {
        std::string raw = manager.BuildRawJson(bot, densityHealer);
        std::string semantic = manager.BuildSemanticJson(bot, densityHealer, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "external_defensive", densityHealer, "hand_of_protection_healer_emergency",
            raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(densityHealer)), addCount, 1022);
        target = add;
        situation = "dungeon_boss";
        action = "hand_of_protection_healer_emergency";
        return true;
    }

    if (role == "tank" && densityDefenseTarget
        && bot->HasSpell(31789) && manager.TryCastFriendlySpell(bot, densityDefenseTarget, 31789))
    {
        bool healerPickup = densityDefenseTarget == densityHealer;
        char const* pickupAction = healerPickup ? "righteous_defense_healer_pickup" : "righteous_defense_party_pickup";
        std::string raw = manager.BuildRawJson(bot, densityDefenseTarget);
        std::string semantic = manager.BuildSemanticJson(bot, densityDefenseTarget, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_adds", densityDefenseTarget, pickupAction,
            raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(densityDefenseTarget)), addCount, 31789);
        target = add;
        situation = "dungeon_boss";
        action = pickupAction;
        return true;
    }

    Player* addVictim = add && add->GetVictim() ? add->GetVictim()->ToPlayer() : nullptr;
    if (role == "tank" && addVictim && addVictim != bot
        && std::string(manager.GetDungeonRole(addVictim)) != "tank"
        && bot->HasSpell(62124) && manager.TryCastCombatSpell(bot, add, 62124))
    {
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_adds", add, "hand_of_reckoning_add_pickup",
            raw.c_str(), semantic.c_str(), bot->GetExactDist(add), addCount, 62124);
        state.TargetGuid = add->GetGUID();
        target = add;
        situation = "dungeon_boss";
        action = "hand_of_reckoning_add_pickup";
        return true;
    }

    // Rerun200's only strict role failure was a remote two-follower Azil
    // handoff. No area action resolved while the tank was remote, so the
    // generic profile approached for self-centered Holy Wrath. Once Hand
    // of Reckoning entered range, the native engine rejected three legal
    // submissions with SPELL_FAILED_CANT_DO_THAT_RIGHT_NOW; Righteous
    // Defense recovered the pair at 3576 ms. Reuse the already-configured
    // ranged multi-target rescue immediately after that direct-taunt
    // fallback. Native range, line-of-sight, cooldown, GCD, power, target,
    // and spell-legality checks remain authoritative, and rejection falls
    // through to the unchanged Consecration and profile movement chain.
    if (role == "tank" && profile.SpecTag == "protection"
        && densityHealer && densityDefenseTarget == densityHealer
        && addVictim == densityHealer
        && observedListedAttackerCount(densityHealer) >= 2
        && bot->HasSpell(31935)
        && manager.TryCastCombatSpell(bot, add, 31935))
    {
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(
            bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_adds", add,
            "avengers_shield_healer_add_pickup", raw.c_str(),
            semantic.c_str(), bot->GetExactDist(add),
            float(observedListedAttackerCount(densityHealer)), 31935);
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);
        state.TargetGuid = add->GetGUID();
        state.WasInCombat = true;
        target = add;
        situation = "dungeon_boss";
        action = "avengers_shield_healer_add_pickup";
        return true;
    }

    if (role == "tank" && densityDefenseTarget
        && bot->GetExactDist2d(densityDefenseTarget) <= 8.0f
        && bot->HasSpell(26573) && manager.TryCastFriendlySpell(bot, bot, 26573))
    {
        bool healerPickup = densityDefenseTarget == densityHealer;
        char const* pickupAction = healerPickup ? "consecration_healer_pickup" : "consecration_party_pickup";
        std::string raw = manager.BuildRawJson(bot, densityDefenseTarget);
        std::string semantic = manager.BuildSemanticJson(bot, densityDefenseTarget, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_adds", densityDefenseTarget, pickupAction,
            raw.c_str(), semantic.c_str(), float(observedListedAttackerCount(densityDefenseTarget)), addCount, 26573);
        target = add;
        situation = "dungeon_boss";
        action = pickupAction;
        return true;
    }
}

bool TryTankThreatRecovery(
    TankThreatRecoveryRequest const& request)
{
    return Context::Run(request);
}
}
