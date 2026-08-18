#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "GroupReference.h"
#include "MotionMaster.h"
#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

bool BotWorldPopulationMgr::TryValidationRouteGroupHeal(
    WorldBotState& state, Player* bot, Player* healer, Unit* combatTarget,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action, bool allowMovement, bool allowStationaryCastTime)
{
        if (!healer || std::string(GetDungeonRole(healer)) != "healer")
            return false;

        uint64 nowMs = NowMs();
        if (state.RouteHealSuppressedUntilMs <= nowMs)
        {
            state.RouteHealSuppressedTargetGuid.Clear();
            state.RouteHealSuppressedUntilMs = 0;
        }
        auto routeHealTargetSuppressed = [&state, nowMs](Unit const* target) -> bool
        {
            return target && !state.RouteHealSuppressedTargetGuid.IsEmpty()
                && state.RouteHealSuppressedTargetGuid == target->GetGUID()
                && state.RouteHealSuppressedUntilMs > nowMs;
        };
        auto tryRouteFriendlySpell = [this, healer, allowMovement,
            allowStationaryCastTime](
            Unit* friendlyTarget, uint32 spellId,
            std::string* failureReason = nullptr) -> bool
        {
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            if (!allowMovement && spellInfo
                && !allowStationaryCastTime
                && spellInfo->CalcCastTime(healer->getLevel()) > 0)
            {
                if (failureReason)
                    *failureReason = "movement_preserved_cast_time_spell";
                return false;
            }
            return TryCastFriendlySpell(
                healer, friendlyTarget, spellId, failureReason);
        };

        // Holy Word: Chastise only becomes a friendly Holy Word: Serenity
        // while Chakra: Serenity is active. Establish Chakra before choosing
        // heals; a following Heal/Flash Heal/Greater Heal activates Serenity.
        if (healer->getClass() == CLASS_PRIEST
            && healer->HasSpell(14751)
            && !healer->HasAura(14751)
            && !healer->HasAura(81208)
            && tryRouteFriendlySpell(healer, 14751))
        {
            std::string raw = BuildRawJson(healer, combatTarget);
            std::string semantic = BuildSemanticJson(healer, combatTarget, "healer_assignment", &power, stage, activity);
            RecordEvent(state, healer, "healing_stance", healer, "chakra_serenity_primed",
                raw.c_str(), semantic.c_str(), UnitHealthPct(healer), 0, 14751);
            situation = "validation_route_group_heal";
            action = "prime_chakra_serenity";
            return true;
        }

        // Unit::getAttackers can lag a scripted follower transition in either
        // direction. Keep its broader count for healing/defensive heuristics,
        // but spend Fade only when the same explicit current-victim observation
        // used by identity-scoped evidence proves at least two live healer
        // attackers. Rerun86 consumed Fade with zero, and rerun87 consumed it
        // for one attacker nine seconds before the 27-47-hostile Flayer wave.
        // The existing Feral Growl rule retains the single-attacker fallback.
        size_t healerAttackerCount = healer->getAttackers().size();
        size_t healerTargetingHostileCount = 0;
        std::vector<WorldObject*> healerObjects;
        Trinity::AllWorldObjectsInRange healerCheck(healer, 45.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> healerSearcher(
            healer, healerObjects, healerCheck);
        Cell::VisitAllObjects(healer, healerSearcher, 45.0f);
        for (WorldObject* object : healerObjects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (creature && creature->IsAlive() && creature->GetHealth()
                && healer->IsValidAttackTarget(creature)
                && creature->GetVictim() == healer)
                ++healerTargetingHostileCount;
        }
        healerAttackerCount = std::max(healerAttackerCount, healerTargetingHostileCount);

        if (healerTargetingHostileCount >= 2
            && healer->HasSpell(586) && !healer->HasAura(586)
            && tryRouteFriendlySpell(healer, 586))
        {
            std::string raw = BuildRawJson(healer, combatTarget);
            std::string semantic = BuildSemanticJson(healer, combatTarget, "healer_assignment", &power, stage, activity);
            RecordEvent(state, healer, "healer_assignment", healer, "fade_threat_drop",
                raw.c_str(), semantic.c_str(),
                float(healerTargetingHostileCount), 0, 586);
            situation = "validation_route_group_heal";
            action = "fade_threat_drop";
            return true;
        }

        float healerHealthPct = UnitHealthPct(healer);
        bool guardianSpiritEmergency = healerAttackerCount >= 3 && healerHealthPct <= 0.55f;
        bool guardianSpiritSwarm = healerAttackerCount >= 8 && healerHealthPct <= 0.90f;
        if ((guardianSpiritEmergency || guardianSpiritSwarm)
            && healer->HasSpell(47788) && !healer->HasAura(47788)
            && tryRouteFriendlySpell(healer, 47788))
        {
            std::string raw = BuildRawJson(healer, combatTarget);
            std::string semantic = BuildSemanticJson(healer, combatTarget, "healer_assignment", &power, stage, activity);
            RecordEvent(state, healer, "external_defensive", healer, "guardian_spirit_self_emergency",
                raw.c_str(), semantic.c_str(), healerHealthPct, uint32(healerAttackerCount), 47788);
            situation = "validation_route_group_heal";
            action = "guardian_spirit_self_emergency";
            return true;
        }
        if (healerAttackerCount >= 5 && healerHealthPct <= 0.85f
            && healer->HasSpell(19236) && tryRouteFriendlySpell(healer, 19236))
        {
            std::string raw = BuildRawJson(healer, combatTarget);
            std::string semantic = BuildSemanticJson(healer, combatTarget, "healer_assignment", &power, stage, activity);
            RecordEvent(state, healer, "healing_lifecycle", healer, "desperate_prayer_self_emergency",
                raw.c_str(), semantic.c_str(), healerHealthPct, uint32(healerAttackerCount), 19236);
            situation = "validation_route_group_heal";
            action = "desperate_prayer_self_emergency";
            return true;
        }

        Unit* lowestTarget = routeHealTargetSuppressed(healer) ? nullptr : healer;
        Unit* tankTarget = nullptr;
        float lowestHealthPct = lowestTarget ? UnitHealthPct(lowestTarget) : 2.0f;
        if (Group* group = healer->GetGroup())
        {
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != healer->GetMap())
                    continue;

                if (!tankTarget && std::string(GetDungeonRole(member)) == "tank")
                    tankTarget = member;

                float memberHealthPct = UnitHealthPct(member);
                if (!routeHealTargetSuppressed(member) && memberHealthPct < lowestHealthPct)
                {
                    lowestHealthPct = memberHealthPct;
                    lowestTarget = member;
                }
            }
        }
        else
        {
            for (WorldBotState const& cohortState : Party().Bots)
            {
                Player* member = GetBot(cohortState);
                if (!member || !member->IsAlive() || member->GetMap() != healer->GetMap())
                    continue;

                if (!tankTarget && std::string(GetDungeonRole(member)) == "tank")
                    tankTarget = member;

                float memberHealthPct = UnitHealthPct(member);
                if (!routeHealTargetSuppressed(member) && memberHealthPct < lowestHealthPct)
                {
                    lowestHealthPct = memberHealthPct;
                    lowestTarget = member;
                }
            }
        }

        if (!lowestTarget)
            return false;

        // In a dungeon pull a healthy healer must not spend its next global on
        // Wrath/Moonfire while an engaged hostile is still owned by a DPS (or
        // has no stable tank victim).  That is a rotation/route boundary, not
        // a healing-threshold decision: the profile is allowed to do damage
        // only after the tank has re-established native threat.  The first
        // Stonecore 5H trace showed exactly this failure, with Restoration
        // Druid casting Wrath at a 25-yard Unbound Earth Rager while the pack
        // was still splitting onto the party.
        size_t unstablePartyThreatCount = 0;
        if (tankTarget && Cohort().Config.ValidationRouteKind != "boss")
        {
            for (WorldObject* object : healerObjects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || !healer->IsValidAttackTarget(creature)
                    || (!creature->IsInCombat() && !creature->GetVictim()))
                    continue;

                Player* victim = creature->GetVictim()
                    ? creature->GetVictim()->ToPlayer() : nullptr;
                if (!victim || victim->GetMap() != healer->GetMap()
                    || victim->GetGroup() != healer->GetGroup()
                    || victim == tankTarget || victim == healer)
                    continue;

                ++unstablePartyThreatCount;
            }
        }
        if (unstablePartyThreatCount > 0 && lowestHealthPct > 0.88f
            && tankTarget && !healer->HasUnitState(UNIT_STATE_CASTING)
            && !healer->IsFalling())
        {
            bool moved = false;
            if (allowMovement)
            {
                Position tankAnchor = tankTarget->GetFirstCollisionPosition(
                    6.0f, tankTarget->GetAngle(healer) - tankTarget->GetOrientation());
                moved = MoveBotToPoint(state, healer,
                    tankAnchor.GetPositionX(), tankAnchor.GetPositionY(),
                    tankAnchor.GetPositionZ());
            }
            if (!moved && (state.ActivePathValid || state.IsMoving || healer->isMoving()))
            {
                healer->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                healer->StopMoving();
                state.ActivePathValid = false;
                state.IsMoving = false;
            }
            std::string raw = BuildRawJson(healer, combatTarget);
            std::string semantic = BuildSemanticJson(
                healer, combatTarget, "healer_assignment", &power, stage, activity);
            RecordEvent(state, healer, "healer_assignment", tankTarget,
                moved ? "healer_move_for_tank_threat_stabilization"
                      : "healer_hold_for_tank_threat_stabilization",
                raw.c_str(), semantic.c_str(),
                float(unstablePartyThreatCount), lowestHealthPct);
            situation = "validation_route_group_heal";
            action = moved ? "healer_move_for_tank_threat_stabilization"
                           : "healer_hold_for_tank_threat_stabilization";
            return true;
        }

        // A discovery/trash pull can become native combat between the last
        // threat observation and this healer decision.  Do not begin a hard
        // damage cast while an attackable dungeon hostile is already inside
        // the pull envelope; hold at the tank and let native threat/healing
        // observations settle first.  This closes the opening Stonecore 5H
        // race where Wrath started at 25 yards, then the pack split before the
        // next decision could see a victim.
        size_t pendingDungeonPullCount = 0;
        if (tankTarget && Cohort().Config.ValidationRouteKind != "boss"
            && lowestHealthPct > 0.88f)
        {
            for (WorldObject* object : healerObjects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || creature->GetMap() != healer->GetMap()
                    || healer->GetExactDist2d(creature) > 35.0f
                    || !healer->IsValidAttackTarget(creature)
                    || creature->IsDungeonBoss() || creature->isWorldBoss()
                    || creature->IsCritter() || creature->IsPet()
                    || creature->IsTotem() || creature->IsSummon()
                    || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
                    continue;

                ++pendingDungeonPullCount;
            }

            // The range search above can lag the route focus by one map update:
            // the healer may already have a hostile target selected while the
            // creature is not yet present in the 45-yard object snapshot.  Use
            // that authoritative combat target as a bounded second source so
            // a hard damage cast cannot slip through the pull boundary.  Only
            // hold when the target has no tank/healer victim yet; once native
            // threat belongs to the tank, the ordinary healing/profile lane
            // resumes unchanged.
            Creature* focusedPendingPull = combatTarget
                ? combatTarget->ToCreature() : nullptr;
            if (focusedPendingPull && focusedPendingPull->IsAlive()
                && focusedPendingPull->GetHealth()
                && healer->IsValidAttackTarget(focusedPendingPull)
                && focusedPendingPull->GetMap() == healer->GetMap())
            {
                Unit* victim = focusedPendingPull->GetVictim();
                if (!victim || (victim != tankTarget && victim != healer))
                    ++pendingDungeonPullCount;
            }
        }
        if (pendingDungeonPullCount > 0 && !healer->IsFalling())
        {
            // If the profile already started Wrath/Moonfire in the one-tick
            // race, cancel that non-healing cast before anchoring at the tank.
            // This is a native interruption only; it does not manufacture a
            // heal or alter the target's combat state.
            if (healer->HasUnitState(UNIT_STATE_CASTING))
                healer->InterruptNonMeleeSpells(false);

            bool moved = false;
            if (allowMovement)
            {
                Position tankAnchor = tankTarget->GetFirstCollisionPosition(
                    6.0f, tankTarget->GetAngle(healer) - tankTarget->GetOrientation());
                moved = MoveBotToPoint(state, healer,
                    tankAnchor.GetPositionX(), tankAnchor.GetPositionY(),
                    tankAnchor.GetPositionZ());
            }
            if (!moved && (state.ActivePathValid || state.IsMoving || healer->isMoving()))
            {
                healer->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                healer->StopMoving();
                state.ActivePathValid = false;
                state.IsMoving = false;
            }
            std::string raw = BuildRawJson(healer, combatTarget);
            std::string semantic = BuildSemanticJson(
                healer, combatTarget, "healer_assignment", &power, stage, activity);
            RecordEvent(state, healer, "healer_assignment", tankTarget,
                moved ? "healer_hold_for_pending_dungeon_pull"
                      : "healer_wait_for_pending_dungeon_pull",
                raw.c_str(), semantic.c_str(),
                float(pendingDungeonPullCount), lowestHealthPct);
            situation = "validation_route_group_heal";
            action = moved ? "healer_hold_for_pending_dungeon_pull"
                           : "healer_wait_for_pending_dungeon_pull";
            return true;
        }

        // The tank is the group's only stable threat owner.  At critical health
        // it takes precedence over a marginally lower DPS target; otherwise the
        // normal lowest-health triage remains in effect.
        if (tankTarget && !routeHealTargetSuppressed(tankTarget) && UnitHealthPct(tankTarget) <= 0.60f
            && (healer->getAttackers().empty() || UnitHealthPct(healer) > 0.60f))
        {
            lowestTarget = tankTarget;
            lowestHealthPct = UnitHealthPct(tankTarget);
        }

        // Reactive convergence starts after follower victim assignment and
        // cannot erase the first grace-eligible exposure samples. While the
        // whole group is healthy and no hostile owns the healer, keep the
        // ranged healer inside the Feral's bounded pickup radius before the
        // next wave activates. Healing triage above and configured hazard
        // movement outside this helper remain authoritative.
        bool proactiveFeralPickupStack = tankTarget
            && tankTarget->getClass() == CLASS_DRUID
            && healerAttackerCount == 0
            && lowestHealthPct > 0.88f
            && UnitHealthPct(tankTarget) > 0.88f
            && healer->GetExactDist2d(tankTarget) > 6.0f
            && !healer->HasUnitState(UNIT_STATE_CASTING)
            && !healer->IsFalling();
        if (allowMovement && proactiveFeralPickupStack)
        {
            float pickupAngle = combatTarget
                ? combatTarget->GetAngle(tankTarget)
                    - tankTarget->GetOrientation()
                : tankTarget->GetAngle(healer)
                    - tankTarget->GetOrientation();
            Position pickup = tankTarget->GetFirstCollisionPosition(
                4.0f, pickupAngle);
            if (MoveBotToPoint(state, healer,
                    pickup.GetPositionX(), pickup.GetPositionY(),
                    pickup.GetPositionZ()))
            {
                std::string raw = BuildRawJson(healer, combatTarget);
                std::string semantic = BuildSemanticJson(
                    healer, combatTarget, "healer_assignment",
                    &power, stage, activity);
                RecordEvent(state, healer, "healer_assignment", tankTarget,
                    "healer_preposition_for_feral_swarm_pickup",
                    raw.c_str(), semantic.c_str(),
                    healer->GetExactDist2d(tankTarget), 0.0f);
                situation = "validation_route_group_heal";
                action = "healer_preposition_for_feral_swarm_pickup";
                return true;
            }
        }

        // A stable healer anchor is sufficient for a small Feral pickup, but a
        // large spread swarm cannot converge inside the three-second retention
        // gate while only the tank moves. When both are healthy, close the
        // existing bounded pickup distance from both sides. Configured hazard
        // movement runs before group healing and remains authoritative.
        bool feralTankApproachesHealerSwarm = tankTarget
            && tankTarget->getClass() == CLASS_DRUID && healerAttackerCount >= 3;
        bool urgentFeralHealerStack = feralTankApproachesHealerSwarm
            && healerAttackerCount >= 5
            && UnitHealthPct(healer) > 0.45f
            && UnitHealthPct(tankTarget) > 0.40f
            && !healer->HasUnitState(UNIT_STATE_CASTING)
            && !healer->IsFalling()
            && healer->GetExactDist2d(tankTarget) > 6.0f;
        if (allowMovement && urgentFeralHealerStack)
        {
            Unit* nearestAttacker = nullptr;
            float nearestAttackerDistance = std::numeric_limits<float>::max();
            for (Unit* attacker : healer->getAttackers())
                if (attacker && attacker->IsAlive()
                    && healer->GetExactDist2d(attacker) < nearestAttackerDistance)
                {
                    nearestAttacker = attacker;
                    nearestAttackerDistance = healer->GetExactDist2d(attacker);
                }
            float pickupAngle = nearestAttacker
                ? nearestAttacker->GetAngle(tankTarget)
                : tankTarget->GetAngle(healer);
            Position pickup = tankTarget->GetFirstCollisionPosition(
                4.0f, pickupAngle - tankTarget->GetOrientation());
            if (MoveBotToPoint(state, healer,
                    pickup.GetPositionX(), pickup.GetPositionY(),
                    pickup.GetPositionZ()))
            {
                std::string raw = BuildRawJson(healer, combatTarget);
                std::string semantic = BuildSemanticJson(
                    healer, combatTarget, "healer_assignment",
                    &power, stage, activity);
                RecordEvent(state, healer, "healer_assignment", tankTarget,
                    "healer_converge_for_feral_swarm_pickup",
                    raw.c_str(), semantic.c_str(),
                    healer->GetExactDist2d(tankTarget),
                    float(healerAttackerCount));
                situation = "validation_route_group_heal";
                action = "healer_converge_for_feral_swarm_pickup";
                return true;
            }
        }
        if (allowMovement && feralTankApproachesHealerSwarm)
        {
            if (state.ActivePathValid || state.IsMoving || healer->isMoving())
            {
                healer->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                healer->StopMoving();
                state.ActivePathValid = false;
                state.IsMoving = false;
            }
            std::string raw = BuildRawJson(healer, combatTarget);
            std::string semantic = BuildSemanticJson(healer, combatTarget, "healer_assignment", &power, stage, activity);
            RecordEvent(state, healer, "healer_assignment", tankTarget, "healer_hold_for_feral_swarm_pickup",
                raw.c_str(), semantic.c_str(), healer->GetExactDist2d(tankTarget), float(healerAttackerCount));
            situation = "validation_route_group_heal";
            action = "healer_hold_for_feral_swarm_pickup";
        }
        else if (allowMovement && !healer->getAttackers().empty() && tankTarget
            && !healer->HasUnitState(UNIT_STATE_CASTING) && !healer->IsFalling())
        {
            Unit* nearestAttacker = nullptr;
            float nearestAttackerDistance = std::numeric_limits<float>::max();
            for (Unit* attacker : healer->getAttackers())
                if (attacker && attacker->IsAlive() && healer->GetExactDist2d(attacker) < nearestAttackerDistance)
                {
                    nearestAttacker = attacker;
                    nearestAttackerDistance = healer->GetExactDist2d(attacker);
                }
            float safeAngle = nearestAttacker
                ? nearestAttacker->GetAngle(tankTarget) : tankTarget->GetAngle(healer);
            Position pickup = tankTarget->GetFirstCollisionPosition(4.0f, safeAngle - tankTarget->GetOrientation());
            if (healer->GetExactDist2d(pickup) > 2.0f
                && MoveBotToPoint(state, healer, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
            {
                std::string raw = BuildRawJson(healer, combatTarget);
                std::string semantic = BuildSemanticJson(healer, combatTarget, "healer_assignment", &power, stage, activity);
                RecordEvent(state, healer, "healer_assignment", tankTarget, "healer_stack_for_add_pickup",
                    raw.c_str(), semantic.c_str(), healer->GetExactDist2d(tankTarget), float(healer->getAttackers().size()));
                situation = "validation_route_group_heal";
                action = "healer_stack_for_add_pickup";
                return true;
            }
        }

        if (combatTarget)
        {
            std::string raw = BuildRawJson(healer, combatTarget);
            std::string semantic = BuildSemanticJson(healer, combatTarget, "healer_assignment", &power, stage, activity);
            uint32 focusEntry = 0;
            if (Creature const* focusCreature = combatTarget->ToCreature())
                focusEntry = focusCreature->GetEntry();
            RecordEvent(state, healer, "healer_assignment", lowestTarget, lowestHealthPct > 0.88f ? "monitor_group_healthy" : "assigned_lowest_ally", raw.c_str(), semantic.c_str(), lowestHealthPct, focusEntry);
        }

        if (lowestHealthPct > 0.88f)
            return allowMovement && feralTankApproachesHealerSwarm;

        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(healer, "healer");
        BotActionProfileSpell const* bestHeal = nullptr;
        Unit* healTarget = nullptr;
        float healTargetHealthPct = 1.0f;
        bool healBlockedByCastState = false;
        for (BotActionProfileSpell const& spell : profile.Spells)
        {
            if (!spell.SpellId || !healer->HasSpell(spell.SpellId))
                continue;

            bool externalDefensive = spell.Category == BotCombatActionCategory::ExternalDefensive;
            if (!externalDefensive && spell.HealingWeight <= 0.0f)
                continue;
            if (spell.Category != BotCombatActionCategory::HealFast
                && spell.Category != BotCombatActionCategory::HealEfficient
                && spell.Category != BotCombatActionCategory::HealAoe
                && !externalDefensive)
                continue;

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId);
            if (!spellInfo)
                continue;

            Unit* candidateTarget = spell.TargetSelector == "self" ? static_cast<Unit*>(healer) : (spell.TargetSelector == "tank" ? tankTarget : lowestTarget);
            if (!candidateTarget || routeHealTargetSuppressed(candidateTarget)
                || !candidateTarget->IsAlive() || !healer->IsValidAssistTarget(candidateTarget))
                continue;

            float candidateHealthPct = UnitHealthPct(candidateTarget);
            if ((spell.MinTargetHealthPct > 0.0f && candidateHealthPct < spell.MinTargetHealthPct)
                || candidateHealthPct > spell.MaxTargetHealthPct)
                continue;
            if ((spell.RequiredSelfAura && !healer->HasAura(spell.RequiredSelfAura))
                || (spell.ForbiddenSelfAura && healer->HasAura(spell.ForbiddenSelfAura))
                || (spell.RequiredTargetAura && !candidateTarget->HasAura(spell.RequiredTargetAura))
                || (spell.ForbiddenTargetAura && candidateTarget->HasAura(spell.ForbiddenTargetAura))
                || MaintainedProfileAuraBlocksRefresh(candidateTarget, spell))
                continue;

            uint32 injuredPlayers = 0;
            float injuredThreshold = spell.InjuredHealthPct > 0.0f ? spell.InjuredHealthPct : 1.0f;
            auto countInjured = [&](Player* member)
            {
                if (member && member->IsAlive() && member->GetMap() == healer->GetMap()
                    && UnitHealthPct(member) < injuredThreshold)
                    ++injuredPlayers;
            };
            if (Group* group = healer->GetGroup())
                for (GroupReference* itr = group->GetFirstMember(); itr; itr = itr->next())
                    countInjured(itr->GetSource());
            else
                for (WorldBotState const& cohortState : Party().Bots)
                    countInjured(GetBot(cohortState));

            float manaPct = healer->GetMaxPower(POWER_MANA)
                ? float(healer->GetPower(POWER_MANA)) / float(healer->GetMaxPower(POWER_MANA)) : 0.0f;
            uint32 attackerCount = uint32(healerAttackerCount);
            if (injuredPlayers < spell.MinInjuredPlayers
                || (spell.MaxInjuredPlayers && injuredPlayers > spell.MaxInjuredPlayers)
                || manaPct < spell.MinManaPct || manaPct > spell.MaxManaPct
                || attackerCount < spell.MinAttackers
                || (spell.MaxAttackers && attackerCount > spell.MaxAttackers)
                || (spell.RequiresStationary && healer->isMoving())
                || (spell.RequiresMoving && !healer->isMoving()))
                continue;

            if (!HasPowerForSpell(healer, spellInfo))
                continue;

            if (healer->HasUnitState(UNIT_STATE_CASTING) || healer->GetSpellHistory()->HasGlobalCooldown(spellInfo) || !healer->GetSpellHistory()->IsReady(spellInfo))
            {
                healBlockedByCastState = true;
                continue;
            }

            if (!bestHeal)
            {
                bestHeal = &spell;
                healTarget = candidateTarget;
                healTargetHealthPct = candidateHealthPct;
                continue;
            }

            bool currentEmergency = spell.Category == BotCombatActionCategory::ExternalDefensive;
            bool bestEmergency = bestHeal->Category == BotCombatActionCategory::ExternalDefensive;
            bool currentFast = spell.Category == BotCombatActionCategory::HealFast;
            bool bestFast = bestHeal->Category == BotCombatActionCategory::HealFast;
            if ((currentEmergency && !bestEmergency)
                || (currentEmergency == bestEmergency && candidateHealthPct < 0.55f && currentFast && !bestFast)
                || (currentEmergency == bestEmergency && currentFast == bestFast
                    && (spell.PriorityBucket < bestHeal->PriorityBucket
                        || (spell.PriorityBucket == bestHeal->PriorityBucket
                            && (spell.HealingWeight > bestHeal->HealingWeight
                                || (spell.HealingWeight == bestHeal->HealingWeight && spell.SortOrder < bestHeal->SortOrder)
                                || (spell.HealingWeight == bestHeal->HealingWeight && spell.SortOrder == bestHeal->SortOrder && spell.SpellId < bestHeal->SpellId))))))
            {
                bestHeal = &spell;
                healTarget = candidateTarget;
                healTargetHealthPct = candidateHealthPct;
            }
        }

        auto buildRouteHealRaw = [&](Unit const* routeHealTarget, uint32 spellId, float healthPct, char const* castResult, char const* castFailureReason) -> std::string
        {
            std::ostringstream raw;
            raw << "{\"base\":" << BuildRawJson(healer, combatTarget)
                << ",\"route_heal\":{\"selected_heal_spell_id\":" << spellId
                << ",\"heal_target_guid\":" << (routeHealTarget ? routeHealTarget->GetGUID().GetCounter() : 0)
                << ",\"heal_target_health_pct\":" << healthPct
                << ",\"cast_result\":\"" << JsonEscape(castResult ? castResult : "")
                << "\",\"cast_failure_reason\":\"" << JsonEscape(castFailureReason ? castFailureReason : "") << "\"}}";
            return raw.str();
        };

        if (!bestHeal || !healTarget)
        {
            if (healBlockedByCastState)
            {
                std::string raw = buildRouteHealRaw(lowestTarget, 0, lowestHealthPct, "pending", "cast_state_pending");
                std::string semantic = BuildSemanticJson(healer, combatTarget, "validation_route_group_heal", &power, stage, activity);
                RecordEvent(state, healer, "validation_route_group_heal", lowestTarget, "heal_cast_state_pending", raw.c_str(), semantic.c_str(), lowestHealthPct, 0);
                situation = "validation_route_group_heal";
                action = "validation_route_group_heal_pending";
                return true;
            }
            return allowMovement && feralTankApproachesHealerSwarm;
        }

        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(bestHeal->SpellId);
        float healRange = bestHeal->MaxRange > 0.0f ? bestHeal->MaxRange : std::max(5.0f, spellInfo ? spellInfo->GetMaxRange(false) : 5.0f);
        std::string semantic = BuildSemanticJson(healer, combatTarget, "validation_route_group_heal", &power, stage, activity);
        if (!healer->IsWithinDistInMap(healTarget, std::max(5.0f, healRange - 1.0f)) || !healer->IsWithinLOSInMap(healTarget))
        {
            if (allowMovement && feralTankApproachesHealerSwarm)
                return true;

            if (!allowMovement)
                return false;

            float maxApproachRange = Cohort().Config.ValidationRouteEnable && healer->GetMap() && healer->GetMap()->IsRaid() ? 35.0f : 18.0f;
            float approachRange = std::max(3.0f, std::min(healRange - 2.0f, maxApproachRange));
            Position healPosition = healTarget->GetFirstCollisionPosition(approachRange, healTarget->GetAngle(healer));
            MoveBotToPoint(state, healer, healPosition.GetPositionX(), healPosition.GetPositionY(), healPosition.GetPositionZ());
            std::string raw = buildRouteHealRaw(healTarget, bestHeal->SpellId, healTargetHealthPct, "pending", !healer->IsWithinLOSInMap(healTarget) ? "line_of_sight" : "out_of_range");
            RecordEvent(state, healer, "validation_route_group_heal", healTarget, "approach_ally", raw.c_str(), semantic.c_str(), healTargetHealthPct, 0, bestHeal->SpellId);
            situation = "validation_route_group_heal";
            action = "move_to_validation_route_heal_target";
            return true;
        }

        if (allowMovement)
            healer->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        std::string castFailureReason;
        bool cast = tryRouteFriendlySpell(
            healTarget, bestHeal->SpellId, &castFailureReason);
        if (!cast && castFailureReason == "spell_cast_result_150")
        {
            state.RouteHealSuppressedTargetGuid = healTarget->GetGUID();
            state.RouteHealSuppressedUntilMs = NowMs() + 5000;
        }
        ResolvedCombatAction healAction;
        healAction.Valid = true;
        healAction.Type = "cast";
        healAction.SpellId = bestHeal->SpellId;
        healAction.TargetGuid = healTarget->GetGUID();
        healAction.DebugName = BotCombatActionCatalog::ToString(bestHeal->Category);
        RecordCombatAttempt(state, healer, healTarget, "heal_cast", &healAction,
            cast ? BotActionResult::Ok : BotActionResult::CastFailed,
            cast ? nullptr : castFailureReason.c_str());
        std::string raw = buildRouteHealRaw(healTarget, bestHeal->SpellId, healTargetHealthPct, cast ? "ok" : "failed", cast ? "" : castFailureReason.c_str());
        RecordEvent(state, healer, "validation_route_group_heal", healTarget, cast ? "ok" : castFailureReason.c_str(), raw.c_str(), semantic.c_str(), healTargetHealthPct, 0, bestHeal->SpellId);
        situation = "validation_route_group_heal";
        action = cast ? "validation_route_group_heal" : "validation_route_group_heal_failed";
        return cast || (allowMovement && feralTankApproachesHealerSwarm);
}
