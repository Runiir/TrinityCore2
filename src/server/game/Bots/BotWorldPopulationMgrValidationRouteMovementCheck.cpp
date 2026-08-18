#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotRaidHazardState.h"
#include "Bots/BotWorldPopulationMgrValidationHazards.h"
#include "Bots/BotClassSpecActionProfile.h"

#include "CellImpl.h"
#include "Creature.h"
#include "DynamicObject.h"
#include "GridNotifiersImpl.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "WorldObject.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::Distance2d;
using BotWorldPopulationMgrSpellSemantics::NowMs;
using BotWorldPopulationMgrSpellSemantics::SpellLooksLikeGroundDanger;

bool BotWorldPopulationMgr::TryValidationRouteMovementCheck(
    WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power,
    BotProgressionStage stage, BotProgressionActivity activity,
    std::string& situation, std::string& action, Unit* preferredTarget,
    ValidationRouteMovementCheckCallbacks const& callbacks)
{
        if (!bot
            || !bot->IsAlive()
            || bot->IsFalling())
            return false;

        using HazardDefinition = BotWorldValidationHazards::Definition;
        using ActiveHazard = BotWorldValidationHazards::Active;
        std::vector<HazardDefinition> hazardDefinitions =
            BotWorldValidationHazards::BuildDefinitions(
                Cohort().Config.ValidationRouteHazardSourceEntry,
                Cohort().Config.ValidationRouteHazardDetectionSpellId,
                Cohort().Config.ValidationRouteHazardDamageSpellId,
                Cohort().Config.ValidationRouteHazardShape,
                Cohort().Config.ValidationRouteHazardRadiusYards,
                Cohort().Config.ValidationRouteHazardSafetyMarginYards);

        // Hazard geometry belongs to the active route node. Importing every
        // later manifest node here made ordinary opening-pack casts inherit
        // Slabhide, Flayer, and Azil dodge behavior before those encounters.
        bool profileAllowsGenericCastMovement = Cohort().Config.ValidationRouteMechanicProfile.find("movement_check") != std::string::npos
            || Cohort().Config.ValidationRouteMechanicProfile.find("ground_danger") != std::string::npos;
        bool mechanicProfileRequiresMovement = profileAllowsGenericCastMovement || !hazardDefinitions.empty();
        bool currentNodeHasConfiguredHazard = Cohort().Config.ValidationRouteHazardSourceEntry != 0;
        auto hazardDefinitionFor = [&hazardDefinitions](uint32 sourceEntry, uint32 spellId) -> HazardDefinition const*
        {
            return BotWorldValidationHazards::FindDefinition(
                hazardDefinitions, sourceEntry, spellId);
        };
        std::vector<ActiveHazard> activeHazards;
        auto hazardIsActive = [bot](Creature* hazard, HazardDefinition const* definition) -> bool
        {
            return BotWorldValidationHazards::IsActive(bot, hazard, definition);
        };
        auto refreshActiveHazards = [&]()
        {
            activeHazards = BotWorldValidationHazards::FindActive(
                bot, hazardDefinitions, mechanicProfileRequiresMovement);
        };
        auto positionOutsideHazard = [](ActiveHazard const& hazard, Position const& position) -> bool
        {
            return BotWorldValidationHazards::PositionOutside(
                hazard, position.GetPositionX(), position.GetPositionY());
        };
        auto positionOutsideActiveHazards = [&](Position const& position) -> bool
        {
            return BotWorldValidationHazards::PositionsOutside(
                activeHazards, position.GetPositionX(), position.GetPositionY());
        };
        auto pathOutsideActiveHazards = [&](float x, float y, float z) -> bool
        {
            return BotWorldValidationHazards::PathOutside(
                bot, activeHazards, x, y, z);
        };
        auto isScopedGenericCastCandidate = [this, &hazardDefinitionFor, &callbacks,
            currentNodeHasConfiguredHazard](Unit* candidate) -> bool
        {
            if (!currentNodeHasConfiguredHazard)
                return true;

            Creature* creature = candidate ? candidate->ToCreature() : nullptr;
            if (!creature || hazardDefinitionFor(creature->GetEntry(), 0)
                || Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration
                || Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())
                    == Party().ValidationRoutePackMemberGuids.end()
                || Party().ValidationRoutePackDeathGuids.find(creature->GetGUID())
                    != Party().ValidationRoutePackDeathGuids.end()
                || Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID())
                    != Party().ValidationRoutePackTransitionGuids.end())
                return false;

            return callbacks.IsCombatLinked(creature);
        };
        uint64 const nowMs = NowMs();
        // Refresh immediately before the state guard so a newly spawned or
        // overlapping Laser Strike cannot be missed between two AI ticks.
        refreshActiveHazards();
        if (!state.ValidationRouteDodgeCasterGuid.IsEmpty()
            && state.ValidationRouteDodgeSpellId)
        {
            Unit* previousHazard = ObjectAccessor::GetUnit(*bot, state.ValidationRouteDodgeCasterGuid);
            HazardDefinition const* previousDefinition = previousHazard
                ? hazardDefinitionFor(previousHazard->GetEntry(), state.ValidationRouteDodgeSpellId) : nullptr;
            if (previousDefinition)
            {
                float safeRadius = std::max(1.0f, previousDefinition->RadiusYards + previousDefinition->SafetyMarginYards);
                bool outsideHazard = bot->GetExactDist2d(previousHazard) > safeRadius;
                if (previousDefinition->Shape == "frontal_cone" && !previousHazard->HasInArc(float(M_PI), bot))
                    outsideHazard = true;
                // The previous single-caster guard is retained for telemetry,
                // but an exit is complete only when the bot is outside every
                // currently active source.  This matters when two Golem
                // Sentries place overlapping Laser Strike creatures.
                for (ActiveHazard const& activeHazard : activeHazards)
                {
                    if (!activeHazard.Source || !activeHazard.HazardDefinition)
                        continue;
                    bool insideActiveHazard = bot->GetExactDist2d(activeHazard.Source)
                        <= activeHazard.SafeRadius;
                    if (activeHazard.HazardDefinition->Shape == "frontal_cone")
                        insideActiveHazard = insideActiveHazard
                            && activeHazard.Source->HasInArc(float(M_PI), bot);
                    bool outsideActiveHazard = !insideActiveHazard;
                    outsideHazard = outsideHazard && outsideActiveHazard;
                }
                // Persistent ground objects and native timed markers share the
                // same activity predicate used by the fresh-hazard scan.
                bool hazardActive = hazardIsActive(
                    previousHazard->ToCreature(), previousDefinition);
                if (outsideHazard && hazardActive && state.ValidationRouteDodgeUntilMs > nowMs)
                {
                    if (previousDefinition->Shape == "radial"
                        && state.FeralChargePickupUntilMs > nowMs
                        && !state.FeralChargePickupTargetGuid.IsEmpty())
                    {
                        Unit* chargeTarget = ObjectAccessor::GetUnit(
                            *bot, state.FeralChargePickupTargetGuid);
                        if (chargeTarget && chargeTarget->IsAlive()
                            && bot->IsValidAttackTarget(chargeTarget)
                            && bot->GetExactDist2d(chargeTarget) > 10.0f)
                        {
                            std::string raw = BuildRawJson(bot, chargeTarget);
                            std::string semantic = BuildSemanticJson(
                                bot, chargeTarget, "validation_route_mechanic",
                                &power, stage, activity);
                            RecordEvent(state, bot, "validation_route_threat_pickup",
                                chargeTarget,
                                "feral_charge_safe_hazard_swarm_pickup_in_flight",
                                raw.c_str(), semantic.c_str(),
                                bot->GetExactDist2d(chargeTarget),
                                Cohort().Config.ValidationRouteTargetEntry, 16979);
                            state.TargetGuid = chargeTarget->GetGUID();
                            situation = "validation_route_mechanic";
                            action = "feral_charge_safe_hazard_swarm_pickup_in_flight";
                            return true;
                        }
                        state.FeralChargePickupTargetGuid.Clear();
                        state.FeralChargePickupUntilMs = 0;
                    }
                    else if (state.FeralChargePickupUntilMs
                        && state.FeralChargePickupUntilMs <= nowMs)
                    {
                        state.FeralChargePickupTargetGuid.Clear();
                        state.FeralChargePickupUntilMs = 0;
                    }

                    // Crossing the radius is not enough: ordinary melee/range
                    // movement immediately walked bots back into live fissures
                    // and rotating Flay cones. Hold the safe side briefly while
                    // the exact hazard remains active. A bounded safe Charge keeps
                    // its motion until arrival before this hold clears the slot.
                    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                    state.ActivePathValid = false;
                    state.IsMoving = false;
                    // Once safely outside, a healer may use the native trained
                    // healing profile from this exact position. Movement-owned
                    // healer convergence remains disabled, but cast-time heals
                    // are safe because the accepted hazard exit is complete.
                    if (callbacks.TryGroupHeal(bot, preferredTarget, false, true))
                        return true;
                    if (TryValidationRouteHealerHazardFade(state, bot, preferredTarget, power, stage, activity, situation, action))
                        return true;
                    if (TryValidationRouteTankHazardHoldAreaThreat(state, bot, previousHazard, safeRadius,
                            previousDefinition->Shape == "radial", true, power, stage, activity, situation, action))
                        return true;
                    situation = "validation_route_mechanic";
                    action = "hold_outside_hazard";
                    return true;
                }
                if (!previousHazard->IsAlive() || outsideHazard || !hazardActive)
                {
                    std::string raw = BuildRawJson(bot, previousHazard);
                    std::string semantic = BuildSemanticJson(bot, previousHazard, "validation_route_mechanic", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_mechanic", previousHazard, "hazard_exit_completed",
                        raw.c_str(), semantic.c_str(), bot->GetExactDist(previousHazard),
                        previousDefinition->SourceEntry, state.ValidationRouteDodgeSpellId);
                    state.ValidationRouteDodgeCasterGuid.Clear();
                    state.ValidationRouteDodgeSpellId = 0;
                    state.ValidationRouteDodgeUntilMs = 0;
                    state.ValidationRouteDodgeBearingAttempt = 0;
                }
                else if (state.ActivePathValid && state.IsMoving)
                {
                    // Keep the accepted exit path authoritative until the bot
                    // is outside the hazard. A normal combat/range decision on
                    // the next tick must not replace the dodge mid-stride.
                    // Rerun73 isolated one healer-owned hostile for 15 seconds
                    // while every Feral decision returned here. Growl is an
                    // instant single-target pickup and does not replace or
                    // clear the already accepted hazard-exit motion.
                    if (TryValidationRouteHealerHazardFade(state, bot, preferredTarget, power, stage, activity, situation, action))
                        return true;
                    // Preserve the accepted strict hazard-exit path while still
                    // allowing native instant self-centered threat. Rerun83
                    // showed Flayer and Azil waves targeting the healer for
                    // 6-10 seconds because every Feral tick returned here
                    // before the declared add handler could submit Roar,
                    // Swipe, or Thrash. This in-flight mode cannot Charge or
                    // issue ground movement, so hazard geometry remains the
                    // sole movement authority.
                    if (previousDefinition->Shape == "radial"
                        && TryValidationRouteTankHazardHoldAreaThreat(
                            state, bot, previousHazard, safeRadius, true, false,
                            power, stage, activity, situation, action))
                        return true;
                    if (previousDefinition->Shape == "radial"
                        && TryValidationRouteFeralHazardLooseTaunt(state, bot, power, stage, activity, situation, action))
                        return true;
                    situation = "validation_route_mechanic";
                    action = "move_out_of_hazard";
                    return true;
                }
            }
        }

        Unit* caster = nullptr;
        WorldObject const* movementOrigin = nullptr;
        SpellInfo const* castSpell = nullptr;
        bool configuredHazard = false;
        float configuredSafeRadius = 0.0f;
        std::string configuredHazardShape;
        auto inspectCaster = [&](Unit* candidate) -> bool
        {
            if (!candidate || !candidate->IsAlive() || !bot->IsValidAttackTarget(candidate) || !bot->IsWithinDistInMap(candidate, 35.0f))
                return false;

            if (Spell* spell = candidate->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                castSpell = spell->GetSpellInfo();
            if (!castSpell)
                if (Spell* spell = candidate->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                    castSpell = spell->GetSpellInfo();
            if (!castSpell || !castSpell->CalcCastTime(candidate->getLevel()))
            {
                castSpell = nullptr;
                return false;
            }
            if (!SpellLooksLikeGroundDanger(castSpell))
            {
                castSpell = nullptr;
                return false;
            }

            caster = candidate;
            movementOrigin = candidate;
            return true;
        };

        if (mechanicProfileRequiresMovement && !hazardDefinitions.empty())
        {
            float bestHazardDistance = std::numeric_limits<float>::max();
            for (ActiveHazard const& activeHazard : activeHazards)
            {
                Creature* hazard = activeHazard.Source;
                HazardDefinition const* definition = activeHazard.HazardDefinition;
                if (!hazard || !definition)
                    continue;

                float safeRadius = activeHazard.SafeRadius;
                float distance = bot->GetExactDist2d(hazard);
                if (distance > safeRadius)
                    continue;
                if (definition->Shape == "frontal_cone" && !hazard->HasInArc(float(M_PI), bot))
                    continue;
                if (distance >= bestHazardDistance)
                    continue;

                bestHazardDistance = distance;
                caster = hazard;
                movementOrigin = hazard;
                castSpell = sSpellMgr->GetSpellInfo(definition->DamageSpellId
                    ? definition->DamageSpellId : definition->DetectionSpellId);
                configuredHazard = castSpell != nullptr;
                configuredSafeRadius = safeRadius;
                configuredHazardShape = definition->Shape;
            }
        }

        // Exact route geometry takes precedence over spell-shape guessing.
        // When that configured source is inactive, a different enrolled and
        // cohort-combat-linked member of the current trash pack can still cast
        // a second ground danger (rerun208: Crystalspawn Giant Quake alongside
        // configured Flayer Flay). Keep boss phases, future packs, and unrelated
        // nearby casters outside this fallback.
        if (!caster && profileAllowsGenericCastMovement
            && isScopedGenericCastCandidate(preferredTarget))
            inspectCaster(preferredTarget);
        if (!caster && mechanicProfileRequiresMovement)
        {
            for (auto const& [_, application] : bot->GetAppliedAuras())
            {
                if (!application || application->IsPositive())
                    continue;

                Aura const* aura = application->GetBase();
                SpellInfo const* auraSpell = aura ? aura->GetSpellInfo() : nullptr;
                if (!auraSpell)
                    continue;

                bool persistentPeriodicDamage = false;
                for (SpellEffectInfo const& effect : auraSpell->Effects)
                {
                    if (effect.Effect == SPELL_EFFECT_PERSISTENT_AREA_AURA
                        && (effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE
                            || effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE_PERCENT))
                    {
                        persistentPeriodicDamage = true;
                        break;
                    }
                }
                if (!persistentPeriodicDamage)
                    continue;

                movementOrigin = aura->GetOwner();
                caster = ObjectAccessor::GetUnit(*bot, aura->GetCasterGUID());
                if (!caster)
                    caster = preferredTarget;
                if (!caster)
                    continue;

                castSpell = auraSpell;
                break;
            }
        }
        if (!caster && profileAllowsGenericCastMovement)
        {
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 35.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 35.0f);
            for (WorldObject* object : objects)
            {
                Unit* candidate = object ? object->ToUnit() : nullptr;
                if (isScopedGenericCastCandidate(candidate) && inspectCaster(candidate))
                    break;
            }
        }

        if (!caster || !castSpell)
            return false;

        // A generic cast is one dodge window, not a movement command on every
        // AI tick. Exact configured hazards use the active exit/hold logic
        // above because they may remain dangerous after the cast completes.
        if (!configuredHazard
            && state.ValidationRouteDodgeCasterGuid == caster->GetGUID()
            && state.ValidationRouteDodgeSpellId == castSpell->Id
            && state.ValidationRouteDodgeUntilMs > nowMs)
            return false;

        WorldObject const* dodgeOrigin = movementOrigin && movementOrigin != bot ? movementOrigin : caster;
        float distanceFromOrigin = bot->GetExactDist2d(dodgeOrigin);
        float dodgeDistance = configuredHazard
            ? std::max(3.0f, configuredSafeRadius - distanceFromOrigin + 2.0f) : 8.0f;
        float angle = bot->GetRelativeAngle(dodgeOrigin) + float(M_PI);
        if (configuredHazard)
        {
            float absoluteAwayAngle = dodgeOrigin->GetAngle(bot);
            if (configuredHazardShape == "frontal_cone")
            {
                float side = bot->GetGUID().GetCounter() % 2 ? 1.0f : -1.0f;
                absoluteAwayAngle = dodgeOrigin->GetOrientation() + side * float(M_PI_2);
                dodgeDistance = std::max(4.0f, configuredSafeRadius);
            }
            else
            {
                uint8 bearingBucket = BotRaidHazard::RotatedBearingBucket(
                    bot->GetGUID().GetCounter(),
                    state.ValidationRouteDodgeBearingAttempt);
                float spreadOffset = (int32(bearingBucket) - 2) * 0.16f;
                absoluteAwayAngle += spreadOffset;
            }
            angle = absoluteAwayAngle - bot->GetOrientation();
        }
        // Rerun84 showed the new strict radial path was accepted before the
        // instant healer threat-drop and Feral loose-healer taunt were
        // submitted. Once movement owned the decision, the last loose hostile
        // persisted for 4017 ms even though the subsequent safe-side area
        // resolver succeeded. Submit only these existing instant native rules
        // before path ownership; the strict hazard destination below remains
        // unchanged and is still issued in this decision.
        if (configuredHazard && configuredHazardShape == "radial")
        {
            TryValidationRouteHealerHazardFade(state, bot, preferredTarget, power, stage, activity, situation, action);
            if (!TryValidationRouteFeralHazardHealerRoar(state, bot, power, stage, activity, situation, action))
                TryValidationRouteFeralHazardLooseTaunt(state, bot, power, stage, activity, situation, action);
        }

        bot->InterruptNonMeleeSpells(false);
        bool moved = false;
        bool feralHazardHandoffBiased = false;
        bool feralHazardCurrentClusterBiased = false;
        std::vector<Position> dodgeCandidates;
        // A direct radial exit can land outside the local navmesh beside lava
        // cracks, walls, or shelf edges.  Try a small deterministic fan of
        // equally safe bearings before reporting a failed hazard exit.
        for (float angleOffset : { 0.0f, float(M_PI_4), -float(M_PI_4), float(M_PI_2), -float(M_PI_2) })
            dodgeCandidates.push_back(
                bot->GetFirstCollisionPosition(dodgeDistance, angle + angleOffset));

        // MoveBotToPoint validates navmesh reachability, while this geometry
        // gate validates the complete active-hazard set.  Do not submit a
        // candidate that exits one Laser Strike only to enter another
        // overlapping strike on the same path endpoint.
        dodgeCandidates.erase(
            std::remove_if(dodgeCandidates.begin(), dodgeCandidates.end(),
                [&](Position const& candidate)
                {
                    return !positionOutsideActiveHazards(candidate);
                }),
            dodgeCandidates.end());
        dodgeCandidates.erase(
            std::remove_if(dodgeCandidates.begin(), dodgeCandidates.end(),
                [&](Position const& candidate)
                {
                    return !pathOutsideActiveHazards(
                        candidate.GetPositionX(), candidate.GetPositionY(), candidate.GetPositionZ());
                }),
            dodgeCandidates.end());

        // Rerun106's longest healer dwell began while ordinary-trash recovery
        // already owned a validated remote hostile anchor. A new strict radial
        // hazard correctly replaced that movement, but the geometry-only fan
        // chose the opposite safe side and local Swipe could not reach the
        // remote cluster for 6.56 seconds. Preserve the same five collision-safe
        // candidates and unchanged hazard radius, but rank their endpoints
        // toward the still-valid identity-bound handoff anchor. Hazard movement
        // remains authoritative and every candidate still passes MoveBotToPoint.
        Unit* feralHazardHandoffAnchor = nullptr;
        if (configuredHazard && configuredHazardShape == "radial"
            && state.FeralHealerThreatHandoffUntilMs > nowMs
            && !state.FeralHealerThreatHandoffAnchorGuid.IsEmpty())
        {
            BotClassSpecActionProfile hazardProfile =
                BotClassSpecActionProfileStore::Build(bot, GetDungeonRole(bot));
            Unit* candidate = ObjectAccessor::GetUnit(
                *bot, state.FeralHealerThreatHandoffAnchorGuid);
            Player* victim = candidate && candidate->GetVictim()
                ? candidate->GetVictim()->ToPlayer() : nullptr;
            if (hazardProfile.SpecTag == "feral_druid_tank"
                && candidate && candidate->IsAlive()
                && candidate->GetMap() == bot->GetMap()
                && bot->IsValidAttackTarget(candidate)
                && victim && GetDungeonRole(victim) == "healer"
                && bot->GetGroup()
                && victim->GetGroup() == bot->GetGroup())
                feralHazardHandoffAnchor = candidate;
        }
        // Rerun109's largest loss began when a fresh Flayer wave flipped to
        // the healer after hazard movement became authoritative but before an
        // ordinary handoff existed.  In that state the rerun106 rule had no
        // anchor and retained the geometry-only bearing for 5.6 seconds.  Use
        // the same deterministic densest healer-owned cluster as a bearing
        // hint for the unchanged five safe candidates.  This neither creates
        // a handoff nor changes the hazard radius/path acceptance contract.
        if (!feralHazardHandoffAnchor
            && configuredHazard && configuredHazardShape == "radial")
        {
            BotClassSpecActionProfile hazardProfile =
                BotClassSpecActionProfileStore::Build(
                    bot, GetDungeonRole(bot));
            if (hazardProfile.SpecTag == "feral_druid_tank")
            {
                std::vector<WorldObject*> objects;
                Trinity::AllWorldObjectsInRange check(bot, 45.0f);
                Trinity::WorldObjectListSearcher<
                    Trinity::AllWorldObjectsInRange> searcher(
                        bot, objects, check);
                Cell::VisitAllObjects(bot, searcher, 45.0f);
                std::vector<Creature*> healerAttackers;
                for (WorldObject* object : objects)
                {
                    Creature* creature = object ? object->ToCreature() : nullptr;
                    Player* victim = creature && creature->GetVictim()
                        ? creature->GetVictim()->ToPlayer() : nullptr;
                    if (creature && creature->IsAlive()
                        && creature->GetMap() == bot->GetMap()
                        && bot->IsValidAttackTarget(creature)
                        && victim && GetDungeonRole(victim) == "healer"
                        && bot->GetGroup()
                        && victim->GetGroup() == bot->GetGroup())
                        healerAttackers.push_back(creature);
                }
                uint32 bestClusterCount = 0;
                float bestDistance = std::numeric_limits<float>::max();
                uint32 bestGuid = std::numeric_limits<uint32>::max();
                for (Creature* candidate : healerAttackers)
                {
                    uint32 clusterCount = 0;
                    for (Creature* neighbor : healerAttackers)
                        if (candidate->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!feralHazardHandoffAnchor
                        || clusterCount > bestClusterCount
                        || (clusterCount == bestClusterCount
                            && (distance < bestDistance
                                || (distance == bestDistance
                                    && guid < bestGuid))))
                    {
                        feralHazardHandoffAnchor = candidate;
                        bestClusterCount = clusterCount;
                        bestDistance = distance;
                        bestGuid = guid;
                    }
                }
                feralHazardCurrentClusterBiased =
                    feralHazardHandoffAnchor != nullptr;
            }
        }
        if (feralHazardHandoffAnchor)
        {
            std::stable_sort(dodgeCandidates.begin(), dodgeCandidates.end(),
                [&](Position const& left, Position const& right)
                {
                    bool leftOutside = Distance2d(
                        left.GetPositionX(), left.GetPositionY(),
                        dodgeOrigin->GetPositionX(), dodgeOrigin->GetPositionY())
                        > configuredSafeRadius + 0.5f;
                    bool rightOutside = Distance2d(
                        right.GetPositionX(), right.GetPositionY(),
                        dodgeOrigin->GetPositionX(), dodgeOrigin->GetPositionY())
                        > configuredSafeRadius + 0.5f;
                    if (leftOutside != rightOutside)
                        return leftOutside;
                    return Distance2d(
                        left.GetPositionX(), left.GetPositionY(),
                        feralHazardHandoffAnchor->GetPositionX(),
                        feralHazardHandoffAnchor->GetPositionY())
                        < Distance2d(
                            right.GetPositionX(), right.GetPositionY(),
                            feralHazardHandoffAnchor->GetPositionX(),
                            feralHazardHandoffAnchor->GetPositionY());
                });
            feralHazardHandoffBiased = true;
        }
        for (Position const& dodge : dodgeCandidates)
        {
            if (MoveBotToPoint(state, bot, dodge.GetPositionX(), dodge.GetPositionY(), dodge.GetPositionZ()))
            {
                moved = true;
                break;
            }
        }
        bool const newDodgeSource = state.ValidationRouteDodgeCasterGuid
            != caster->GetGUID();
        if (newDodgeSource)
            state.ValidationRouteDodgeBearingAttempt = 0;
        state.ValidationRouteDodgeCasterGuid = caster->GetGUID();
        state.ValidationRouteDodgeSpellId = castSpell->Id;
        state.ValidationRouteDodgeUntilMs = nowMs + (moved ? 3000 : 500);
        if (configuredHazard && moved)
            state.ValidationRouteDodgeUntilMs = nowMs + (configuredHazardShape == "radial" ? 6000 : 3000);
        if (configuredHazard && !moved)
        {
            state.ValidationRouteDodgeBearingAttempt = uint8(
                (state.ValidationRouteDodgeBearingAttempt + 1) % 5);
            state.LastPathRejectReason = "hazard_exit_no_union_safe_native_path";
            state.LastRecoveryResult = state.LastPathRejectReason;
        }

        std::string raw = BuildRawJson(bot, caster);
        std::string semantic = BuildSemanticJson(bot, caster, "validation_route_mechanic", &power, stage, activity);
        char const* movementReason = moved
            ? (configuredHazard
                ? (feralHazardHandoffBiased
                    ? (feralHazardCurrentClusterBiased
                        ? "hazard_exit_started_toward_feral_healer_cluster"
                        : "hazard_exit_started_toward_feral_healer_handoff")
                    : "hazard_exit_started")
                : "movement_check_jump")
            : (configuredHazard ? "hazard_exit_failed" : "tactical_path_rejected");
        RecordEvent(state, bot, "validation_route_mechanic", caster, movementReason, raw.c_str(), semantic.c_str(), bot->GetExactDist(caster), Cohort().Config.ValidationRouteTargetEntry, castSpell->Id);
        if (moved && configuredHazard && configuredHazardShape == "radial"
            && TryValidationRouteTankHazardHoldAreaThreat(
                state, bot, caster, configuredSafeRadius, true, false,
                power, stage, activity, situation, action))
            return true;
        situation = "validation_route_mechanic";
        action = moved ? (configuredHazard ? "move_out_of_hazard" : "movement_check_jump")
            : (configuredHazard ? "hold_hazard_exit_failed" : "hold_tactical_path_rejected");
        return true;
}
