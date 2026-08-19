#include "Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgr.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <string>
#include <utility>

namespace BotWorldPopulationMgrValidationRoute
{
bool ObjectiveContext::RunTrashThreatControl(
    TrashThreatControl& trashThreatControl,
    TrashThreatControlCallbacks const& callbacks)
{
    WorldBotState& state = State;
    Player* bot = Bot;
    BotRolePowerBreakdown const& power = Power;
    BotProgressionStage stage = Stage;
    BotProgressionActivity activity = Activity;
    std::string& situation = Situation;
    std::string& action = Action;
    Unit*& target = Target;
    bool discoveryLeg = callbacks.DiscoveryLeg();
    auto const& isImmediateNextValidationRouteEncounterMember =
        callbacks.IsImmediateNextValidationRouteEncounterMember;
    auto const& isPendingScriptedEventEntry =
        callbacks.IsPendingScriptedEventEntry;
    auto const& isValidationRouteScriptTarget =
        callbacks.IsValidationRouteScriptTarget;
    auto const& routeEngageRange = callbacks.RouteEngageRange;
    auto const& moveOutOfProfileDeadZone =
        callbacks.MoveOutOfProfileDeadZone;
    auto const& tryValidationRouteAdds = callbacks.TryValidationRouteAdds;
    auto Cohort = [this]() -> decltype(auto) { return Manager.Cohort(); };
    auto Party = [this]() -> decltype(auto) { return Manager.Party(); };
    auto GetLoadedBot = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.GetLoadedBot(std::forward<decltype(args)>(args)...);
    };
    auto GetDungeonRole = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.GetDungeonRole(std::forward<decltype(args)>(args)...);
    };
    auto SubmitMeleeAutoAttackIntent = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.SubmitMeleeAutoAttackIntent(
            std::forward<decltype(args)>(args)...);
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
    auto RecordCombatAttempt = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.RecordCombatAttempt(
            std::forward<decltype(args)>(args)...);
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
    trashThreatControl = TrashThreatControl();
    // Boss nodes can still contain ordinary prerequisite packs. Apply the
    // same secure-threat and Misdirection policy to those mobs, while leaving
    // the configured boss and declared boss adds to their specialized logic.
    {
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (member && member->IsAlive() && member->GetMap() == bot->GetMap()
                && member->GetGroup() == bot->GetGroup()
                && std::string(GetDungeonRole(member)) == "tank")
            {
                trashThreatControl.Tank = member;
                break;
            }
        }

        std::vector<WorldObject*> threatObjects;
        Trinity::AllWorldObjectsInRange threatCheck(bot, 80.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> threatSearcher(bot, threatObjects, threatCheck);
        Cell::VisitAllObjects(bot, threatSearcher, 80.0f);
        uint8 areaTargetPriority = 0;
        float areaTargetDistance = std::numeric_limits<float>::max();
        uint32 areaTargetGuid = std::numeric_limits<uint32>::max();
        for (WorldObject* object : threatObjects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || !creature->IsAlive() || !creature->GetHealth()
                || !bot->IsValidAttackTarget(creature) || (!creature->IsInCombat() && !creature->GetVictim())
                || isImmediateNextValidationRouteEncounterMember(creature))
                continue;
            // A configured scripted actor (Millhouse in the opening
            // Corborus node) is a future route event, not ordinary trash.  It
            // may already be attackable/in combat due to native script
            // preparation, but it must not enter the generic threat scan until
            // the discovery handoff has enrolled its current-generation GUID.
            bool currentDiscoveryScriptedMember = discoveryLeg
                && Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())
                    != Party().ValidationRoutePackMemberGuids.end();
            if (isPendingScriptedEventEntry(creature) && !currentDiscoveryScriptedMember)
                continue;
            bool declaredBossAdd = Cohort().Config.ValidationRouteKind == "boss"
                && std::find(Cohort().Config.ValidationRouteAddTargetEntries.begin(),
                    Cohort().Config.ValidationRouteAddTargetEntries.end(), creature->GetEntry())
                    != Cohort().Config.ValidationRouteAddTargetEntries.end();
            if (Cohort().Config.ValidationRouteKind == "boss"
                && (isValidationRouteScriptTarget(creature) || declaredBossAdd))
                continue;
            Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
            if (!victim || victim->GetGroup() != bot->GetGroup())
                continue;

            ++trashThreatControl.EngagedCount;
            std::string victimRole = GetDungeonRole(victim);
            if (victimRole == "healer")
            {
                ++trashThreatControl.HealerTargetCount;
                trashThreatControl.HealerOwnedTargets.push_back(creature);
                if (!trashThreatControl.HealerTarget
                    || victim->GetGUID().GetCounter()
                        < trashThreatControl.HealerTarget->GetGUID().GetCounter())
                    trashThreatControl.HealerTarget = victim;
            }
            uint8 priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 1 : 2);
            float distance = bot->GetExactDist(creature);
            uint32 guid = creature->GetGUID().GetCounter();
            if (!trashThreatControl.AreaTarget || priority > areaTargetPriority
                || (priority == areaTargetPriority && (distance < areaTargetDistance
                    || (distance == areaTargetDistance && guid < areaTargetGuid))))
            {
                trashThreatControl.AreaTarget = creature;
                areaTargetPriority = priority;
                areaTargetDistance = distance;
                areaTargetGuid = guid;
            }

            if (!trashThreatControl.Tank || victim != trashThreatControl.Tank)
                continue;
            trashThreatControl.TankOwnedTargets.push_back(creature);
            ++trashThreatControl.TankOwnedCount;
            float tankThreat = creature->GetThreatManager().GetThreat(trashThreatControl.Tank, true);
            float highestPartyThreat = 0.0f;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetLoadedBot(cohortState);
                if (!member || member == trashThreatControl.Tank || !member->IsAlive()
                    || member->GetMap() != creature->GetMap())
                    continue;
                highestPartyThreat = std::max(highestPartyThreat,
                    creature->GetThreatManager().GetThreat(member, true));
            }
            // In a raid trash node, the native ThreatManager's ranged victim
            // switch threshold (130%) is the observable safety boundary.  The
            // old dungeon-tuning floor of 2000 threat and 2.5x headroom starved
            // all five BWD damage slots while both tanks already owned every
            // declared Drakonid.  Keep that legacy tuning outside raid trash;
            // here require current native victim ownership plus positive 1.3x
            // headroom, recomputed on every decision.
            bool secureThreat = bot->GetMap() && bot->GetMap()->IsRaid()
                && Cohort().Config.ValidationRouteKind != "boss"
                ? tankThreat > 0.0f && tankThreat >= highestPartyThreat * 1.3f
                : tankThreat >= 2000.0f && tankThreat >= highestPartyThreat * 2.5f;
            if (secureThreat)
                ++trashThreatControl.SecureTankCount;
            else
                trashThreatControl.InsecureTankOwnedTargets.push_back(creature);
        }
    }
    // A boss node has no authority to finish ordinary corridor trash.  The
    // manifest must place that pack in an explicit preceding trash node.  Run
    // this rejection immediately after observation and before any of the
    // shared trash threat, movement, Misdirection, defensive, or profile-action
    // branches below; a downstream check is too late because many of those
    // branches return after acting on AreaTarget.
    if (Cohort().Config.ValidationRouteKind == "boss"
        && trashThreatControl.EngagedCount > 0
        && trashThreatControl.AreaTarget)
    {
        Unit* rejected = trashThreatControl.AreaTarget;
        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "trash_threat_hold");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        std::string raw = BuildRawJson(bot, rejected);
        std::string semantic = BuildSemanticJson(
            bot, rejected, "validation_route_prerequisite", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_prerequisite_rejected",
            rejected, "boss_route_target_not_declared", raw.c_str(),
            semantic.c_str(), bot->GetExactDist(rejected),
            Cohort().Config.ValidationRouteTargetEntry);
        state.TargetGuid.Clear();
        target = nullptr;
        situation = "validation_route_prerequisite";
        action = "boss_route_prerequisite_blocked";
        return true;
    }
    trashThreatControl.InsecureTrashSwarm = trashThreatControl.EngagedCount >= 3
        && trashThreatControl.SecureTankCount * 10 < trashThreatControl.EngagedCount * 9;
    trashThreatControl.TankOwnsTrashMajority = trashThreatControl.EngagedCount > 0
        && trashThreatControl.TankOwnedCount * 10 >= trashThreatControl.EngagedCount * 9;
    bool hunterTrashMisdirectionActive = bot->getClass() == CLASS_HUNTER
        && (bot->HasAura(34477) || bot->HasAura(35079));
    // Ordinary route movement repeatedly preempted Discipline's existing Fade
    // while 11-13 Flayers retained the healer in rerun104. Put the same native
    // gate ahead of those movement/hold decisions. Rerun115 showed that a
    // two-attacker transient can consume Fade before a later 15-hostile wave,
    // rerun116 found the same pattern at three, and rerun117 at a precursor
    // peaking at eight, so use the shared nine-attacker reservation. Never
    // cancel a positive
    // heal; if one is active, this branch is retried on the next tick.
    // Rerun173's Protection/Holy composition fully owned the opening corridor
    // pack before one successful heal flipped four already-eligible hostiles.
    // The healer was outside every immediate native Paladin rescue range, so
    // six bounded tank movement ticks still produced 28 strict exposure
    // samples before Hand of Protection and Righteous Defense recovered them.
    // Use the existing native Fade at that exact four-hostile threshold only
    // with a Protection Paladin tank. Rerun196 then captured a distinct Feral
    // handoff where four of five already-eligible hostiles flipped together
    // after one successful heal. Native Swipe recovered all four in 773 ms,
    // but four 250-ms identity snapshots exceeded the unchanged exposure-ratio
    // ceiling. Admit the same native Fade only when at least four hostiles and
    // at least 80% of the current pack already target the healer with a Druid
    // tank. Smaller Feral precursors and Blood/Warrior tanks retain the
    // established nine-hostile reservation for a later large wave; a rejected
    // cast changes only observation cadence while native legality stays final.
    bool protectionPaladinHealerThreat =
        trashThreatControl.Tank
        && trashThreatControl.Tank->getClass() == CLASS_PALADIN
        && trashThreatControl.HealerTargetCount >= 4;
    bool feralDruidMajorityHealerThreat =
        trashThreatControl.Tank
        && trashThreatControl.Tank->getClass() == CLASS_DRUID
        && trashThreatControl.HealerTargetCount >= 4
        && trashThreatControl.HealerTargetCount * 5
            >= trashThreatControl.EngagedCount * 4;
    if (std::string(GetDungeonRole(bot)) == "healer"
        && (trashThreatControl.HealerTargetCount >= 9
            || protectionPaladinHealerThreat
            || feralDruidMajorityHealerThreat)
        && bot->HasSpell(586) && !bot->HasAura(586))
    {
        if (protectionPaladinHealerThreat
            || feralDruidMajorityHealerThreat)
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
        if (Spell* currentSpell = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            if (!currentSpell->IsPositive())
                bot->InterruptNonMeleeSpells(false);
        if (!bot->HasUnitState(UNIT_STATE_CASTING)
            && TryCastFriendlySpell(bot, bot, 586))
        {
            std::string raw = BuildRawJson(bot, trashThreatControl.AreaTarget);
            std::string semantic = BuildSemanticJson(bot,
                trashThreatControl.AreaTarget, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "healer_assignment", bot,
                "fade_early_trash_swarm_threat_drop",
                raw.c_str(), semantic.c_str(),
                float(trashThreatControl.HealerTargetCount),
                trashThreatControl.EngagedCount, 586);
            situation = "validation_route_group_heal";
            action = "fade_early_trash_swarm_threat_drop";
            return true;
        }
    }
    // The group-heal helper already converges a healer with a Feral tank, but
    // rerun110 proved ordinary route/combat movement can win first and preserve
    // a split Flayer topology for several Roar cycles.  Reuse that same
    // collision-safe four-yard pickup before route movement when a large wave
    // is forming or the healer already owns at least three hostiles.  Exact
    // hazard movement ran earlier and remains authoritative; urgent health and
    // active positive casts still prevent this positioning action.
    if (std::string(GetDungeonRole(bot)) == "healer"
        && trashThreatControl.Tank
        && trashThreatControl.Tank->getClass() == CLASS_DRUID
        && bot->GetExactDist2d(trashThreatControl.Tank) > 6.0f
        && !bot->HasUnitState(UNIT_STATE_CASTING)
        && !bot->IsFalling())
    {
        bool proactiveLargeWaveStack =
            trashThreatControl.EngagedCount >= 12
            && trashThreatControl.HealerTargetCount == 0
            && UnitHealthPct(bot) > 0.88f
            && UnitHealthPct(trashThreatControl.Tank) > 0.88f;
        bool reactiveHealerStack =
            trashThreatControl.HealerTargetCount >= 3
            && UnitHealthPct(bot) > 0.45f
            && UnitHealthPct(trashThreatControl.Tank) > 0.40f;
        if (proactiveLargeWaveStack || reactiveHealerStack)
        {
            Unit* nearestAttacker = nullptr;
            float nearestAttackerDistance =
                std::numeric_limits<float>::max();
            for (Unit* attacker : bot->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == bot
                    && bot->IsValidAttackTarget(attacker)
                    && bot->GetExactDist2d(attacker)
                        < nearestAttackerDistance)
                {
                    nearestAttacker = attacker;
                    nearestAttackerDistance =
                        bot->GetExactDist2d(attacker);
                }
            Unit* approachFrom = nearestAttacker
                ? nearestAttacker : trashThreatControl.AreaTarget;
            float pickupAngle = approachFrom
                ? approachFrom->GetAngle(trashThreatControl.Tank)
                    - trashThreatControl.Tank->GetOrientation()
                : trashThreatControl.Tank->GetAngle(bot)
                    - trashThreatControl.Tank->GetOrientation();
            Position pickup =
                trashThreatControl.Tank->GetFirstCollisionPosition(
                    4.0f, pickupAngle);
            if (MoveBotToPoint(state, bot,
                    pickup.GetPositionX(), pickup.GetPositionY(),
                    pickup.GetPositionZ()))
            {
                std::string raw = BuildRawJson(
                    bot, trashThreatControl.AreaTarget);
                std::string semantic = BuildSemanticJson(
                    bot, trashThreatControl.AreaTarget,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "healer_assignment",
                    trashThreatControl.Tank,
                    reactiveHealerStack
                        ? "healer_converge_early_for_feral_trash_pickup"
                        : "healer_preposition_early_for_feral_trash_pickup",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(trashThreatControl.Tank),
                    trashThreatControl.HealerTargetCount);
                situation = "validation_route_group_heal";
                action = reactiveHealerStack
                    ? "healer_converge_early_for_feral_trash_pickup"
                    : "healer_preposition_early_for_feral_trash_pickup";
                return true;
            }
        }
    }
    bool hunterTrashAoeTransferReady = true;
    float hunterTrashAoeMinRange = 5.0f;
    static constexpr float HunterTrashAoeMinRangeSafety = 3.0f;
    static constexpr float HunterTrashMaxRange = 35.0f;
    if (bot->getClass() == CLASS_HUNTER && trashThreatControl.EngagedCount >= 2)
    {
        Unit* areaTarget = trashThreatControl.AreaTarget;
        if (areaTarget)
            if (SpellInfo const* multiShot = sSpellMgr->GetSpellInfo(2643))
            {
                float spellMinRange = bot->GetSpellMinRangeForTarget(areaTarget, multiShot);
                if (multiShot->RangeEntry && (multiShot->RangeEntry->Flags & SPELL_RANGE_RANGED))
                    spellMinRange += bot->GetMeleeRange(areaTarget);
                hunterTrashAoeMinRange = std::max(hunterTrashAoeMinRange, spellMinRange);
            }
        hunterTrashAoeMinRange = std::min(HunterTrashMaxRange - 1.0f,
            hunterTrashAoeMinRange + HunterTrashAoeMinRangeSafety);
        hunterTrashAoeTransferReady = areaTarget && bot->HasSpell(2643)
            && bot->GetPower(POWER_FOCUS) >= 40
            && bot->GetExactDist(areaTarget) >= hunterTrashAoeMinRange
            && bot->GetExactDist(areaTarget) <= HunterTrashMaxRange
            && bot->IsWithinLOSInMap(areaTarget);
    }
    if (std::string(GetDungeonRole(bot)) == "dps"
        && trashThreatControl.EngagedCount >= 3
        && UnitHealthPct(bot) <= (bot->getClass() == CLASS_SHAMAN ? 0.45f : 0.35f))
    {
        uint32 emergencySpellId = bot->getClass() == CLASS_MAGE ? 45438
            : (bot->getClass() == CLASS_HUNTER ? 19263
                : (bot->getClass() == CLASS_SHAMAN ? 30823 : 0));
        if (emergencySpellId && bot->HasSpell(emergencySpellId)
            && !bot->HasAura(emergencySpellId)
            && TryCastFriendlySpell(bot, bot, emergencySpellId))
        {
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "prerequisite_swarm_emergency_defensive");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            std::string raw = BuildRawJson(bot, trashThreatControl.AreaTarget);
            std::string semantic = BuildSemanticJson(bot, trashThreatControl.AreaTarget,
                "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "defensive", bot, "prerequisite_swarm_emergency_defensive",
                raw.c_str(), semantic.c_str(), UnitHealthPct(bot), trashThreatControl.EngagedCount,
                emergencySpellId);
            target = trashThreatControl.Tank && trashThreatControl.Tank->GetVictim()
                ? trashThreatControl.Tank->GetVictim() : trashThreatControl.AreaTarget;
            state.TargetGuid = target ? target->GetGUID() : ObjectGuid::Empty;
            situation = "normal_dungeon_trash";
            action = "prerequisite_swarm_emergency_defensive";
            return true;
        }
    }
    if (bot->getClass() == CLASS_HUNTER
        && trashThreatControl.Tank
        && trashThreatControl.EngagedCount > 0
        && bot->HasSpell(34477)
        && !hunterTrashMisdirectionActive
        && hunterTrashAoeTransferReady
        && TryCastFriendlySpell(bot, trashThreatControl.Tank, 34477))
    {
        std::string raw = BuildRawJson(bot, trashThreatControl.AreaTarget);
        std::string semantic = BuildSemanticJson(bot, trashThreatControl.AreaTarget,
            "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_transfer", trashThreatControl.AreaTarget,
            "misdirection_to_tank", raw.c_str(), semantic.c_str(),
            float(trashThreatControl.EngagedCount), Cohort().Config.ValidationRouteTargetEntry, 34477);
        target = trashThreatControl.AreaTarget;
        state.TargetGuid = target ? target->GetGUID() : ObjectGuid::Empty;
        situation = "normal_dungeon_trash";
        action = "misdirection_to_tank";
        return true;
    }
    if (hunterTrashMisdirectionActive
        && trashThreatControl.Tank
        && trashThreatControl.AreaTarget)
    {
        target = trashThreatControl.AreaTarget;
        state.TargetGuid = target->GetGUID();
        bool useAreaTransfer = trashThreatControl.EngagedCount >= 2;
        if (useAreaTransfer && bot->GetPower(POWER_FOCUS) < 40)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target,
                "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_transfer", target,
                "misdirection_aoe_wait_for_focus", raw.c_str(), semantic.c_str(),
                float(bot->GetPower(POWER_FOCUS)), trashThreatControl.EngagedCount, 2643);
            situation = "normal_dungeon_trash";
            action = "misdirection_aoe_wait_for_focus";
            return true;
        }
        float transferMinRange = useAreaTransfer ? hunterTrashAoeMinRange : 5.0f;
        if (bot->GetExactDist(target) < transferMinRange
            || bot->GetExactDist(target) > HunterTrashMaxRange
            || !bot->IsWithinLOSInMap(target))
        {
            ResolvedCombatAction rangeAction;
            rangeAction.MovementDirective = "ranged";
            rangeAction.AutoAttackMode = "ranged";
            rangeAction.MinRange = transferMinRange;
            rangeAction.MaxRange = HunterTrashMaxRange;
            bool moved = MoveBotToProfileRange(state, bot, target, &rangeAction);
            situation = "normal_dungeon_trash";
            action = moved
                ? (useAreaTransfer ? "move_to_misdirection_aoe_range" : "move_to_misdirection_single_range")
                : (useAreaTransfer ? "hold_misdirection_aoe_range" : "hold_misdirection_single_range");
            return true;
        }
        if (bot->isMoving())
            bot->StopMoving();
        ResolvedCombatAction transferAction;
        BotActionResult result = BotActionResult::NoAction;
        if (useAreaTransfer)
        {
            transferAction.Valid = true;
            transferAction.Type = "cast";
            transferAction.SpellId = 2643;
            transferAction.TargetGuid = target->GetGUID();
            transferAction.DebugName = "cleave";
            transferAction.MovementDirective = "ranged";
            transferAction.AutoAttackMode = "ranged";
            transferAction.MinRange = hunterTrashAoeMinRange;
            transferAction.MaxRange = HunterTrashMaxRange;
            BotActionExecutor executor;
            result = executor.ExecuteCombat(bot, bot, transferAction);
            std::string castFailureReason;
            if (result == BotActionResult::CastFailed)
                castFailureReason = "spell_cast_result_" + std::to_string(executor.LastSpellCastResult());
            RecordCombatAttempt(state, bot, target, "misdirection_aoe_transfer", &transferAction,
                result, castFailureReason.empty() ? nullptr : castFailureReason.c_str());
        }
        else
        {
            transferAction = ResolveProfileCombatAction(bot, target, 1, false);
            result = ExecuteProfileCombatAction(&state, bot, target, &transferAction, 1, false);
        }
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_transfer", target,
            useAreaTransfer ? "misdirection_aoe_transfer" : "misdirection_single_target_transfer",
            raw.c_str(), semantic.c_str(), float(trashThreatControl.EngagedCount),
            Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? transferAction.SpellId : 0);
        situation = "normal_dungeon_trash";
        action = useAreaTransfer ? "misdirection_aoe_transfer" : "misdirection_single_target_transfer";
        state.WasInCombat = true;
        return true;
    }
    if (std::string(GetDungeonRole(bot)) == "dps"
        && trashThreatControl.Tank
        && trashThreatControl.InsecureTrashSwarm
        && !hunterTrashMisdirectionActive)
    {
        Unit* tankFocus = trashThreatControl.Tank->GetVictim();
        if (trashThreatControl.TankOwnsTrashMajority && tankFocus && tankFocus->IsAlive() && bot->IsValidAttackTarget(tankFocus))
        {
            bool rangedDps = bot->getClass() == CLASS_MAGE || bot->getClass() == CLASS_HUNTER;
            if (rangedDps && trashThreatControl.EngagedCount >= 3
                && bot->GetExactDist2d(trashThreatControl.Tank) < 8.0f
                && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
            {
                Unit* approachFrom = trashThreatControl.AreaTarget
                    ? trashThreatControl.AreaTarget : tankFocus;
                float spreadOffset = bot->GetGUID().GetCounter() % 2 ? 0.35f : -0.35f;
                Position safeRange = trashThreatControl.Tank->GetFirstCollisionPosition(10.0f,
                    approachFrom->GetAngle(trashThreatControl.Tank)
                        - trashThreatControl.Tank->GetOrientation() + spreadOffset);
                if (MoveBotToPoint(state, bot, safeRange.GetPositionX(), safeRange.GetPositionY(), safeRange.GetPositionZ()))
                {
                    SubmitMeleeAutoAttackIntent(state,
                        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                        BotMeleeAutoAttack::Owner::Threat,
                        BotActionArbitration::Priority::ThreatControl,
                        "trash_threat_spread_hold");
                    if (Pet* pet = bot->GetPet())
                        pet->AttackStop();
                    std::string raw = BuildRawJson(bot, tankFocus);
                    std::string semantic = BuildSemanticJson(bot, tankFocus,
                        "normal_dungeon_trash", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_threat_gate", tankFocus,
                        "spread_after_secure_prerequisite_threat", raw.c_str(), semantic.c_str(),
                        bot->GetExactDist2d(trashThreatControl.Tank), trashThreatControl.EngagedCount);
                    target = tankFocus;
                    state.TargetGuid = tankFocus->GetGUID();
                    situation = "validation_route_regroup";
                    action = "spread_after_secure_prerequisite_threat";
                    return true;
                }
            }
            if (bot->GetVictim() && bot->GetVictim() != tankFocus)
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Threat,
                    BotActionArbitration::Priority::ThreatControl,
                    "trash_threat_focus_switch");
            if (Pet* pet = bot->GetPet(); pet && pet->GetVictim() && pet->GetVictim() != tankFocus)
                pet->AttackStop();
            target = tankFocus;
            state.TargetGuid = tankFocus->GetGUID();
            ResolvedCombatAction focusedAction = ResolveProfileCombatAction(bot, tankFocus, 1, false);
            float engageRange = focusedAction.MaxRange > 0.0f
                ? focusedAction.MaxRange : routeEngageRange(bot, tankFocus, focusedAction.SpellId);
            float targetDistance = bot->GetExactDist(tankFocus);
            if (focusedAction.Valid && focusedAction.MinRange > 0.0f && targetDistance < focusedAction.MinRange)
            {
                bool moved = moveOutOfProfileDeadZone(bot, tankFocus, focusedAction);
                situation = "normal_dungeon_trash";
                action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
                return true;
            }
            if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(tankFocus))
            {
                bool moved = MoveBotToProfileRange(state, bot, tankFocus,
                    focusedAction.Valid ? &focusedAction : nullptr);
                situation = "normal_dungeon_trash";
                action = moved ? "move_to_focused_trash_target" : "hold_tactical_path_rejected";
                return true;
            }

            BotActionResult result = focusedAction.AutoAttackMode == "melee"
                && SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::StartOrSwitch,
                    tankFocus->GetGUID(), BotMeleeAutoAttack::Owner::Threat,
                    BotActionArbitration::Priority::ThreatControl,
                    "trash_focused_melee_engagement")
                        ? BotActionResult::Ok : BotActionResult::NoAction;
            if (focusedAction.Valid)
            {
                BotActionResult focusedResult = ExecuteProfileCombatAction(&state, bot, tankFocus, &focusedAction, 1, false);
                if (focusedResult != BotActionResult::NoAction)
                    result = focusedResult;
            }
            std::string raw = BuildRawJson(bot, tankFocus);
            std::string semantic = BuildSemanticJson(bot, tankFocus, "normal_dungeon_trash", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_gate", tankFocus,
                "focused_damage_during_trash_threat_build", raw.c_str(), semantic.c_str(),
                float(trashThreatControl.SecureTankCount), trashThreatControl.EngagedCount,
                result == BotActionResult::Ok && focusedAction.Valid ? focusedAction.SpellId : 0);
            situation = "normal_dungeon_trash";
            action = "focused_damage_during_trash_threat_build";
            state.WasInCombat = true;
            return true;
        }

        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "trash_threat_pickup_hold");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        bool moved = false;
        if (bot->GetExactDist2d(trashThreatControl.Tank) > 6.0f && !bot->IsFalling())
        {
            Unit* approachFrom = trashThreatControl.AreaTarget ? trashThreatControl.AreaTarget : trashThreatControl.Tank;
            Position pickup = trashThreatControl.Tank->GetFirstCollisionPosition(4.0f,
                approachFrom->GetAngle(trashThreatControl.Tank) - trashThreatControl.Tank->GetOrientation());
            moved = MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ());
        }
        std::string raw = BuildRawJson(bot, trashThreatControl.AreaTarget);
        std::string semantic = BuildSemanticJson(bot, trashThreatControl.AreaTarget, "normal_dungeon_trash", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_threat_gate", trashThreatControl.AreaTarget,
            moved ? "stack_for_secure_trash_threat" : "hold_for_secure_trash_threat",
            raw.c_str(), semantic.c_str(), float(trashThreatControl.TankOwnedCount), trashThreatControl.EngagedCount);
        state.TargetGuid = trashThreatControl.Tank->GetVictim()
            ? trashThreatControl.Tank->GetVictim()->GetGUID() : ObjectGuid::Empty;
        target = trashThreatControl.Tank->GetVictim();
        situation = "validation_route_regroup";
        action = moved ? "stack_for_secure_trash_threat" : "hold_for_secure_trash_threat";
        return true;
    }
    if (tryValidationRouteAdds())
        return true;

    return false;
}
}
