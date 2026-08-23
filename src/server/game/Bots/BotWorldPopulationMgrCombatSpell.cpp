#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Map.h"
#include "Player.h"
#include "Random.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace
{
float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;
    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}

float Distance2d(float ax, float ay, float bx, float by)
{
    float dx = ax - bx;
    float dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}

bool HasPowerForSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;
    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > powerCost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(powerCost);
}

bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth = 0)
{
    if (!spellInfo || depth > 4)
        return false;
    if (spellInfo->Id == 48505 || spellInfo->Id == 89751)
        return true;
    for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[effectIndex];
        if (!effect.IsEffect())
            continue;
        if (!spellInfo->IsPositiveEffect(effectIndex)
            && (effect.ChainTarget > 1 || effect.IsTargetingArea()
                || effect.IsEffect(SPELL_EFFECT_PERSISTENT_AREA_AURA)
                || effect.IsAreaAuraEffect()))
            return true;
        if (effect.TriggerSpell
            && SpellHasHostileMultiTargetSemantics(sSpellMgr->GetSpellInfo(effect.TriggerSpell), depth + 1))
            return true;
    }
    return false;
}

bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target)
{
    if (!owner || !target || !BotRaidAreaAuthority::HasProtectedEncounterEntries(owner->GetGUID().GetRawValue()))
        return false;
    std::vector<WorldObject*> nearbyObjects;
    Trinity::AllWorldObjectsInRange check(target, 45.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(target, nearbyObjects, check);
    Cell::VisitAllObjects(target, searcher, 45.0f);
    for (WorldObject* object : nearbyObjects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || creature == target || !creature->IsAlive()
            || !owner->IsValidAttackTarget(creature))
            continue;
        if (BotRaidAreaAuthority::IsProtectedEncounterTarget(owner->GetGUID().GetRawValue(),
                creature->GetEntry(), creature->GetSpawnId(), creature->GetGUID().GetRawValue()))
            return true;
    }
    return false;
}
}

uint32 BotWorldPopulationMgr::SelectCombatSpell(Player* bot, Unit* target) const
{
    if (!bot || !target || !target->IsAlive())
        return 0;

    std::string role = GetDungeonRole(bot);
    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role.c_str());

    RoleSaturationState saturation = BuildRoleSaturationState(bot, target, role.c_str());
    std::string roleGoal = BotProgressionGoalPolicy::RoleGoal(role);
    std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile);
    auto engagedWithBotParty = [bot](Unit* unit) -> bool
    {
        auto belongsToBotParty = [bot](Unit* participant) -> bool
        {
            Player* player = participant ? participant->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
            return player && (player == bot || (bot->GetGroup() && player->GetGroup() == bot->GetGroup()));
        };
        if (!unit || (!unit->IsInCombat() && !unit->GetVictim()))
            return false;
        if (belongsToBotParty(unit->GetVictim()))
            return true;
        for (Unit* attacker : unit->getAttackers())
            if (belongsToBotParty(attacker))
                return true;
        return false;
    };
    uint32 nearbyEnemyCount = 1;
    {
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 10.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 10.0f);
        for (WorldObject* object : objects)
        {
            Unit* unit = object ? object->ToUnit() : nullptr;
            if (unit && unit != target && unit->IsAlive() && bot->IsValidAttackTarget(unit)
                && engagedWithBotParty(unit))
                ++nearbyEnemyCount;
        }
    }

    BotActionCandidate* best = nullptr;
    for (BotActionCandidate& candidate : candidates)
    {
        if (candidate.Profile.MinEnemies > nearbyEnemyCount)
        {
            candidate.RejectReason = "min_enemies_not_met";
            continue;
        }
        if (candidate.Profile.MaxEnemies && candidate.Profile.MaxEnemies < nearbyEnemyCount)
        {
            candidate.RejectReason = "max_enemies_exceeded";
            continue;
        }
        if (candidate.Category == BotCombatActionCategory::HealFast
            || candidate.Category == BotCombatActionCategory::HealEfficient
            || candidate.Category == BotCombatActionCategory::HealAoe
            || candidate.Category == BotCombatActionCategory::Buff
            || candidate.Category == BotCombatActionCategory::DispelCleanse
            || candidate.Category == BotCombatActionCategory::ExternalDefensive)
        {
            candidate.RejectReason = "requires_ally_target";
            continue;
        }
        if (!candidate.RejectReason.empty())
            continue;
        if (candidate.Category == BotCombatActionCategory::Taunt
            && (!target->GetVictim() || target->GetVictim() == bot))
        {
            candidate.RejectReason = "threat_already_established";
            continue;
        }
        if (Cohort().Config.ValidationRouteEnable
            && Cohort().Config.ValidationRouteKind != "boss"
            && candidate.Category == BotCombatActionCategory::Taunt
            && (!target->GetVictim() || target->GetVictim() == bot))
        {
            candidate.RejectReason = "validation_trash_requires_damage_progress";
            continue;
        }
        if (candidate.Category == BotCombatActionCategory::Taunt)
        {
            if (Player* victimPlayer = target->GetVictim() ? target->GetVictim()->ToPlayer() : nullptr)
            {
                if (victimPlayer->GetMap() == bot->GetMap() && std::string(GetDungeonRole(victimPlayer)) == "tank")
                {
                    bool validationCohortVictim = false;
                    for (WorldBotState const& cohortState : Party().Bots)
                    {
                        Player* member = GetBot(cohortState);
                        if (member && member == victimPlayer)
                        {
                            validationCohortVictim = true;
                            break;
                        }
                    }
                    if (validationCohortVictim)
                    {
                        candidate.RejectReason = "cohort_threat_established";
                        continue;
                    }
                }
            }
        }
        bool selfTarget = candidate.Profile.TargetSelector == "self";
        Unit* actionTarget = selfTarget ? static_cast<Unit*>(bot) : target;
        if (!selfTarget)
        {
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
            if (spellInfo && (actionTarget->IsImmunedToSpell(spellInfo, bot)
                || (spellInfo->HasOnlyDamageEffects() && actionTarget->IsImmunedToDamage(spellInfo))))
            {
                candidate.RejectReason = "target_immune";
                continue;
            }
        }
        float targetHealthPct = UnitHealthPct(actionTarget);
        if (targetHealthPct < candidate.Profile.MinTargetHealthPct || targetHealthPct > candidate.Profile.MaxTargetHealthPct)
        {
            candidate.RejectReason = "target_health_gate";
            continue;
        }
        if (!MeetsHostileTargetHealthGate(candidate.Profile, UnitHealthPct(target)))
        {
            candidate.RejectReason = "hostile_target_health_gate";
            continue;
        }
        float selfHealthPct = UnitHealthPct(bot);
        if (selfHealthPct < candidate.Profile.MinSelfHealthPct || selfHealthPct > candidate.Profile.MaxSelfHealthPct)
        {
            candidate.RejectReason = "self_health_gate";
            continue;
        }

        if (!candidate.RejectReason.empty())
            continue;

        float roleScore = candidate.Score;
        switch (saturation.RecommendedBalanceMode)
        {
            case BotRoleBalanceMode::PureSurvival:
            case BotRoleBalanceMode::Recovery:
                roleScore += candidate.Profile.SurvivalWeight * 1.5f + candidate.Profile.MitigationWeight + candidate.Profile.HealingWeight;
                roleScore -= candidate.Profile.DamageWeight * 0.25f;
                break;
            case BotRoleBalanceMode::BalancedRoleDps:
                roleScore += candidate.Profile.DamageWeight * 0.55f + candidate.Profile.HealingWeight * 0.25f + candidate.Profile.ThreatWeight * 0.25f;
                break;
            case BotRoleBalanceMode::DpsPush:
                roleScore += candidate.Profile.DamageWeight + candidate.Profile.ProgressionWeight * 0.35f;
                break;
            case BotRoleBalanceMode::RoleFirst:
            default:
                if (role == "healer")
                    roleScore += candidate.Profile.HealingWeight + candidate.Profile.SurvivalWeight * 0.45f;
                else if (role == "tank")
                    roleScore += candidate.Profile.ThreatWeight + candidate.Profile.MitigationWeight + candidate.Profile.SurvivalWeight * 0.45f;
                else
                    roleScore += candidate.Profile.DamageWeight + (candidate.Category == BotCombatActionCategory::Interrupt ? 0.6f : 0.0f);
                break;
        }

        if (role == "tank" && candidate.Category == BotCombatActionCategory::Taunt)
        {
            if (Unit* victim = target->GetVictim())
            {
                Player* victimPlayer = victim->ToPlayer();
                bool victimIsTank = victimPlayer && std::string(GetDungeonRole(victimPlayer)) == "tank";
                if (victim != bot && !victimIsTank)
                    roleScore += 10.0f;
            }
        }

        candidate.Score = roleScore;
        candidate.Reason = saturation.SaturationReason;
        if (!best || candidate.Profile.PriorityBucket < best->Profile.PriorityBucket
            || (candidate.Profile.PriorityBucket == best->Profile.PriorityBucket
                && (candidate.Score > best->Score
                    || (candidate.Score == best->Score && candidate.Profile.SortOrder < best->Profile.SortOrder)
                    || (candidate.Score == best->Score && candidate.Profile.SortOrder == best->Profile.SortOrder && candidate.ActionId < best->ActionId))))
            best = &candidate;
    }

    uint32 botKey = bot->GetGUID().GetCounter();
    Party().LastSaturationByBot[botKey] = saturation;
    Party().LastCombatMaskByBot[botKey] = BotClassSpecActionProfileStore::CandidateMaskJson(candidates, profile, roleGoal.c_str(), saturation.ToJson().c_str());
    Party().LastChosenCombatByBot[botKey] = BotClassSpecActionProfileStore::ChosenActionJson(best, profile, roleGoal.c_str(), BotRoleSaturationPolicy::ToString(saturation.RecommendedBalanceMode), saturation.ExperimentConfidence);
    Party().LastActionCategoryByBot[botKey] = best ? BotCombatActionCatalog::ToString(best->Category) : "wait";

    return best ? best->SpellId : 0;
}

bool BotWorldPopulationMgr::TryCastCombatSpell(Player* bot, Unit* target, uint32 spellId) const
{
    if (!bot || !target || !spellId || !target->IsAlive() || !bot->IsValidAttackTarget(target))
        return false;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo || !bot->IsWithinLOSInMap(target))
        return false;
    uint64 const ownerGuid = bot->GetGUID().GetRawValue();
    if (BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid))
        return false;
    if (Creature const* creature = target->ToCreature();
        creature && BotRaidAreaAuthority::IsProtectedEncounterTarget(
            ownerGuid, creature->GetEntry(), creature->GetSpawnId(),
            creature->GetGUID().GetRawValue()))
        return false;
    if (HasNearbyProtectedEncounterTarget(bot, target)
        && SpellHasHostileMultiTargetSemantics(spellInfo))
        return false;
    if (bot->HasUnitState(UNIT_STATE_CONTROLLED)
        || (spellInfo->PreventionType == SPELL_PREVENTION_TYPE_SILENCE
            && bot->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_SILENCED))
        || (spellInfo->PreventionType == SPELL_PREVENTION_TYPE_PACIFY
            && bot->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PACIFIED)))
        return false;

    float maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    if (!bot->IsWithinDistInMap(target, maxRange))
        return false;

    bot->SetFacingToObject(target);
    if (bot->HasUnitState(UNIT_STATE_CASTING) || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo) || !bot->GetSpellHistory()->IsReady(spellInfo))
        return false;

    if (!HasPowerForSpell(bot, spellInfo))
        return false;

    return bot->CastSpell(target, spellId, false) == SPELL_CAST_OK;
}

void BotWorldPopulationMgr::MoveToWanderPoint(Player* bot, WorldBotState& state)
{
    if (!bot)
        return;

    uint64 poiId = 0;
    float poiX = 0.0f;
    float poiY = 0.0f;
    float poiZ = 0.0f;
    if (FindMemoryPoiTarget(bot, poiX, poiY, poiZ, poiId))
    {
        if (bot->GetExactDist2d(poiX, poiY) <= INTERACTION_DISTANCE)
            MarkPoiVisited(poiId);
        else
            MoveBotToPoint(state, bot, poiX, poiY, poiZ);
        return;
    }

    float fromCenter = Distance2d(bot->GetPositionX(), bot->GetPositionY(), Cohort().Config.CenterX, Cohort().Config.CenterY);
    for (uint8 attempt = 0; attempt < 8; ++attempt)
    {
        float angle = fromCenter > Cohort().Config.Radius ? bot->GetAngle(Cohort().Config.CenterX, Cohort().Config.CenterY) : frand(0.0f, 2.0f * float(M_PI));
        float distance = frand(8.0f, 25.0f);
        Position pos = bot->GetFirstCollisionPosition(distance, angle);
        if (GetLocalDangerScore(bot->GetGUID().GetCounter(), bot->GetMapId(), pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ()) >= 3.0f)
            continue;
        if (IsFailedPathRecently(bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), pos.GetPositionX(), pos.GetPositionY()))
            continue;

        MoveBotToPoint(state, bot, pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ());
        return;
    }

    Position fallback = bot->GetFirstCollisionPosition(4.0f, bot->GetAngle(Cohort().Config.CenterX, Cohort().Config.CenterY));
    MoveBotToPoint(state, bot, fallback.GetPositionX(), fallback.GetPositionY(), fallback.GetPositionZ());
}
