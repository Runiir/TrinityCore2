#include "Bots/BotController.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotDatasetEvent.h"
#include "Bots/BotMgr.h"
#include "Config.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "Log.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "DataStores/DBCStructure.h"
#include "DungeonFinding/LFG.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Transport.h"
#include "Spell.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include <algorithm>
#include <boost/filesystem.hpp>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <map>
#include <sstream>
#include <utility>

namespace
{
bool RotationHasEnoughPower(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    int32 cost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (cost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > cost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(cost);
}

BotCombatArchetype CombatArchetypeForClass(uint8 classId, std::string const& runtimeRole, std::string const& classSpec = "")
{
    if (runtimeRole == "tank")
        return BotCombatArchetype::TankLikeMelee;
    if (runtimeRole == "healer")
        return BotCombatArchetype::HealerSolo;
    if (classSpec == "enhancement_shaman")
        return BotCombatArchetype::MeleeDps;

    switch (classId)
    {
        case CLASS_HUNTER:
            return BotCombatArchetype::RangedPhysical;
        case CLASS_MAGE:
        case CLASS_PRIEST:
        case CLASS_SHAMAN:
            return BotCombatArchetype::RangedCaster;
        case CLASS_WARLOCK:
            return BotCombatArchetype::PetClass;
        default:
            return BotCombatArchetype::MeleeDps;
    }
}

bool IsHealingCategory(BotCombatActionCategory category)
{
    return category == BotCombatActionCategory::HealFast
        || category == BotCombatActionCategory::HealEfficient
        || category == BotCombatActionCategory::HealAoe
        || category == BotCombatActionCategory::DispelCleanse
        || category == BotCombatActionCategory::ExternalDefensive
        || category == BotCombatActionCategory::Defensive
        || category == BotCombatActionCategory::Mitigation
        || category == BotCombatActionCategory::OffensiveCooldown;
}

uint32 CastTimeMs(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return 0;
    return uint32(std::max<int32>(0, spellInfo->CalcCastTime(bot->getLevel())));
}

bool MeetsCastDirectives(Player const* bot, BotActionProfileSpell const& spell, SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;
    uint32 castTime = CastTimeMs(bot, spellInfo);
    if (spell.RequiresInstantCast && castTime > 0)
        return false;
    if (spell.MaxCastTimeMs && castTime > spell.MaxCastTimeMs)
        return false;
    return true;
}
}

BotCombatState BotController::BuildCombatState(Player* owner, Player* bot, BotRecentEvents const& recentEvents) const
{
    BotCombatState frame;
    frame.ClassId = bot->getClass();
    frame.SpecId = 0;
    frame.Moving = bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
    frame.Casting = bot->HasUnitState(UNIT_STATE_CASTING);
    frame.ActiveAuraCount = bot->GetAppliedAuras().size();
    frame.InCombat = bot->IsInCombat() || owner->IsInCombat() || recentEvents.DamageTaken > 0;
    frame.SafePositionAvailable = owner->IsAlive() && bot->GetMap() == owner->GetMap() && !bot->IsFalling() && !bot->IsInWater();

    uint32 maxHealth = bot->GetMaxHealth();
    frame.SelfHpPct = maxHealth ? float(bot->GetHealth()) / float(maxHealth) : 0.0f;
    Powers power = bot->GetPowerType();
    uint32 maxPower = bot->GetMaxPower(power);
    frame.SelfPowerPct = maxPower ? float(bot->GetPower(power)) / float(maxPower) : 1.0f;

    SpellInfo const* gcdProbe = sSpellMgr->GetSpellInfo(6603);
    frame.GcdReady = !gcdProbe || !bot->GetSpellHistory()->HasGlobalCooldown(gcdProbe);

    Unit* target = nullptr;
    if (!_combatTargetGuid.IsEmpty())
        target = ObjectAccessor::GetUnit(*bot, _combatTargetGuid);
    if (!target && bot->GetVictim())
        target = bot->GetVictim();

    if (target)
    {
        frame.TargetGuid = target->GetGUID();
        if (Creature* creature = target->ToCreature())
        {
            frame.TargetEntry = creature->GetEntry();
            frame.TargetLootable = creature->isDead() && creature->hasLootRecipient();
        }

        frame.TargetDead = !target->IsAlive();
        uint32 targetMaxHealth = target->GetMaxHealth();
        frame.TargetHpPct = targetMaxHealth ? float(target->GetHealth()) / float(targetMaxHealth) : 0.0f;
        frame.TargetDistance = bot->GetExactDist(target);
        if (Spell* spell = target->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        {
            frame.TargetCastingSpellId = spell->GetSpellInfo()->Id;
            frame.TargetInterruptible = true;
        }
    }

    if (Unit* nearby = bot->SelectNearbyTarget(target, 8.0f))
    {
        ++frame.NearbyHostileCount;
        if (Creature* creature = nearby->ToCreature())
            if (creature->isElite())
                frame.EliteNearby = true;
    }
    if (Unit* nearby = bot->SelectNearbyTarget(target, 16.0f))
    {
        ++frame.NearbyHostileCount;
        if (Creature* creature = nearby->ToCreature())
            if (creature->isElite())
                frame.EliteNearby = true;
    }
    if (Unit* nearby = bot->SelectNearbyTarget(target, 24.0f))
    {
        ++frame.NearbyHostileCount;
        if (Creature* creature = nearby->ToCreature())
            if (creature->isElite())
                frame.EliteNearby = true;
    }
    frame.ExtraPullRisk = std::min(1.0f, frame.NearbyHostileCount / 3.0f);
    return frame;
}

BotCombatDecision BotController::DecideSoloCombat(BotCombatState const& state) const
{
    BotCombatDecision decision;
    decision.TargetGuid = state.TargetGuid;
    if (state.TargetGuid.IsEmpty())
        decision.Intent = BotCombatIntent::Wait;
    else if (state.TargetLootable)
        decision.Intent = BotCombatIntent::Loot;
    else if (state.TargetDead)
        decision.Intent = BotCombatIntent::Recover;
    else if (state.SelfHpPct < 0.35f && _runtimeRole == "healer")
        decision.Intent = BotCombatIntent::HealSelf;
    else if (state.SelfHpPct < 0.30f)
        decision.Intent = BotCombatIntent::UseDefensive;
    else if (state.TargetCastingSpellId && state.TargetInterruptible)
        decision.Intent = BotCombatIntent::Interrupt;
    else if (state.TargetDistance > 5.0f && CombatArchetypeForClass(state.ClassId, _runtimeRole, _classSpec) != BotCombatArchetype::RangedCaster && CombatArchetypeForClass(state.ClassId, _runtimeRole, _classSpec) != BotCombatArchetype::RangedPhysical)
        decision.Intent = BotCombatIntent::MoveToRange;
    else if (!state.InCombat)
        decision.Intent = BotCombatIntent::PullTarget;
    else
        decision.Intent = BotCombatIntent::MaintainRotation;
    return decision;
}

ResolvedCombatAction BotController::ResolveSoloCombat(BotCombatDecision const& decision, BotCombatState const& state) const
{
    ResolvedCombatAction action;
    action.TargetGuid = decision.TargetGuid;
    action.DebugName = ToString(decision.Intent);
    switch (decision.Intent)
    {
        case BotCombatIntent::Loot:
            action.Type = "loot";
            break;
        case BotCombatIntent::MoveToRange:
        case BotCombatIntent::PullTarget:
            action.Type = "pull";
            break;
        case BotCombatIntent::HealSelf:
            action.Type = "cast";
            action.TargetGuid = _botGuid;
            action.SpellId = _role == BotRole::HolyPaladinHealer ? 635 : 0;
            break;
        case BotCombatIntent::UseDefensive:
            action.Type = "cast";
            action.SpellId = _role == BotRole::Warrior ? 871 : 0;
            break;
        case BotCombatIntent::Interrupt:
            action.Type = "cast";
            action.SpellId = _role == BotRole::Warrior ? 6552 : 0;
            break;
        case BotCombatIntent::MaintainRotation:
            action.Type = "cast";
            if (GetSoloCombatArchetype(_role) == BotCombatArchetype::RangedCaster)
                action.SpellId = _role == BotRole::Mage ? 133 : 585;
            else if (_role == BotRole::Hunter)
                action.SpellId = 75;
            else if (_role == BotRole::HolyPaladinHealer)
                action.SpellId = 20271;
            else
                action.SpellId = 6603;
            break;
        case BotCombatIntent::Recover:
        case BotCombatIntent::Wait:
        default:
            action.Type = "wait";
            break;
    }

    if (!action.SpellId && action.Type == "cast")
        action.Valid = false;
    if (state.TargetGuid.IsEmpty() && action.TargetGuid != _botGuid)
        action.Valid = false;
    return action;
}

BotActionCandidate const* BotController::SelectProfileCombatAction(Player* bot, Unit* target, BotCombatState const& state, BotClassSpecActionProfile const& profile, std::vector<BotActionCandidate>& candidates) const
{
    std::vector<BotActionCandidate*> valid;
    uint8 bestBucket = 255;

    for (BotActionCandidate& candidate : candidates)
    {
        if (IsHealingCategory(candidate.Category))
        {
            candidate.RejectReason = "requires_ally_target";
            continue;
        }
        if (!candidate.RejectReason.empty())
            continue;

        if (candidate.Category == BotCombatActionCategory::Taunt && target && target->GetVictim() == bot)
        {
            candidate.RejectReason = "threat_already_established";
            continue;
        }
        if (candidate.Profile.RequiresTargetNotVictim && target && target->GetVictim() == bot)
        {
            candidate.RejectReason = "target_already_on_bot";
            continue;
        }
        if (candidate.Profile.RequiresTargetVictim && target && target->GetVictim() != bot)
        {
            candidate.RejectReason = "target_not_on_bot";
            continue;
        }
        if (candidate.Profile.MinEnemies > 1 && state.NearbyHostileCount < candidate.Profile.MinEnemies)
        {
            candidate.RejectReason = "enemy_count_too_low";
            continue;
        }
        if (candidate.Profile.MaxEnemies && state.NearbyHostileCount > candidate.Profile.MaxEnemies)
        {
            candidate.RejectReason = "enemy_count_too_high";
            continue;
        }
        if (state.TargetHpPct < candidate.Profile.MinTargetHealthPct || state.TargetHpPct > candidate.Profile.MaxTargetHealthPct)
        {
            candidate.RejectReason = "target_health_gate";
            continue;
        }
        if (!MeetsHostileTargetHealthGate(candidate.Profile, state.TargetHpPct))
        {
            candidate.RejectReason = "hostile_target_health_gate";
            continue;
        }
        if (state.SelfHpPct < candidate.Profile.MinSelfHealthPct || state.SelfHpPct > candidate.Profile.MaxSelfHealthPct)
        {
            candidate.RejectReason = "self_health_gate";
            continue;
        }
        if (candidate.Profile.RequiresInterruptibleTarget && !state.TargetInterruptible)
        {
            candidate.RejectReason = "target_not_interruptible";
            continue;
        }
        if (candidate.Profile.RequiredSelfAura && !bot->HasAura(candidate.Profile.RequiredSelfAura))
        {
            candidate.RejectReason = "missing_self_aura";
            continue;
        }
        if (candidate.Profile.RequiredSelfAuraStacks)
        {
            Aura const* aura = candidate.Profile.RequiredSelfAura ? bot->GetAura(candidate.Profile.RequiredSelfAura) : nullptr;
            if (!aura || aura->GetStackAmount() < candidate.Profile.RequiredSelfAuraStacks)
            {
                candidate.RejectReason = "insufficient_self_aura_stacks";
                continue;
            }
        }
        if (candidate.Profile.ForbiddenSelfAura && bot->HasAura(candidate.Profile.ForbiddenSelfAura))
        {
            candidate.RejectReason = "forbidden_self_aura";
            continue;
        }
        bool selfTarget = candidate.Profile.TargetSelector == "self";
        Unit* actionTarget = selfTarget ? static_cast<Unit*>(bot) : target;
        float targetDistance = selfTarget ? 0.0f : state.TargetDistance;
        if (actionTarget && candidate.Profile.RequiredTargetAura && !actionTarget->HasAura(candidate.Profile.RequiredTargetAura))
        {
            candidate.RejectReason = "missing_target_aura";
            continue;
        }
        if (actionTarget && candidate.Profile.ForbiddenTargetAura && actionTarget->HasAura(candidate.Profile.ForbiddenTargetAura))
        {
            candidate.RejectReason = "forbidden_target_aura";
            continue;
        }
        if (candidate.Profile.RequiresMeleeRange && actionTarget && !bot->IsWithinMeleeRange(actionTarget))
        {
            candidate.RejectReason = "melee_range_required";
            continue;
        }
        if (candidate.Profile.RequiresRangedRange && targetDistance < 5.0f)
        {
            candidate.RejectReason = "ranged_range_required";
            continue;
        }
        float minRange = candidate.Profile.MinRange > 0.0f ? candidate.Profile.MinRange : profile.MinRange;
        float maxRange = candidate.Profile.MaxRange > 0.0f ? candidate.Profile.MaxRange : profile.MaxRange;
        if (candidate.Profile.MaxRange <= 0.0f)
            if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId))
                maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
        if (minRange > 0.0f && targetDistance < minRange)
        {
            candidate.RejectReason = "min_range_required";
            continue;
        }
        if (maxRange > 0.0f && targetDistance > maxRange)
        {
            candidate.RejectReason = "max_range_exceeded";
            continue;
        }
        if (candidate.SpellId)
            if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId))
            {
                if (!RotationHasEnoughPower(bot, spellInfo))
                {
                    candidate.RejectReason = "insufficient_spell_power_type_resource";
                    continue;
                }
                if (!MeetsCastDirectives(bot, candidate.Profile, spellInfo))
                {
                    candidate.RejectReason = candidate.Profile.RequiresInstantCast ? "instant_cast_required" : "cast_time_too_long";
                    continue;
                }
            }

        if (!candidate.RejectReason.empty())
            continue;

        float roleScore = candidate.Score;
        if (_runtimeRole == "tank")
        {
            roleScore += candidate.Profile.ThreatWeight * 2.0f + candidate.Profile.MitigationWeight + candidate.Profile.SurvivalWeight * 0.5f;
            if (state.NearbyHostileCount >= 2 && (candidate.Category == BotCombatActionCategory::Aoe || candidate.Category == BotCombatActionCategory::Cleave || candidate.Category == BotCombatActionCategory::ThreatBuild))
                roleScore += 1.25f;
            if (target && target->GetVictim() && target->GetVictim() != bot && candidate.Category == BotCombatActionCategory::Taunt)
                roleScore += 2.0f;
        }
        else if (_runtimeRole == "healer")
            roleScore += candidate.Profile.DamageWeight * 0.65f;
        else
        {
            roleScore += candidate.Profile.DamageWeight;
            if (state.NearbyHostileCount >= 2 && (candidate.Category == BotCombatActionCategory::Aoe || candidate.Category == BotCombatActionCategory::Cleave))
                roleScore += 0.8f;
            if (candidate.Category == BotCombatActionCategory::Interrupt)
                roleScore += state.TargetInterruptible ? 2.0f : -0.4f;
        }

        roleScore += std::max<float>(0.0f, 12.0f - float(candidate.Profile.PriorityBucket)) * 0.35f;
        candidate.Score = roleScore;
        candidate.Reason = "guide_weighted_priority_band";
        if (candidate.Profile.PriorityBucket < bestBucket)
        {
            bestBucket = candidate.Profile.PriorityBucket;
            valid.clear();
        }
        if (candidate.Profile.PriorityBucket == bestBucket)
            valid.push_back(&candidate);
    }

    if (valid.empty())
        return nullptr;

    return *std::max_element(valid.begin(), valid.end(), [](BotActionCandidate const* left, BotActionCandidate const* right)
    {
        if (left->Score != right->Score)
            return left->Score < right->Score;
        if (left->Profile.SortOrder != right->Profile.SortOrder)
            return left->Profile.SortOrder > right->Profile.SortOrder;
        return left->ActionId > right->ActionId;
    });
}

ResolvedCombatAction BotController::ResolveProfileCombat(BotCombatDecision const& decision, BotCombatState const& state, Player* bot, Unit* target) const
{
    ResolvedCombatAction action;
    action.TargetGuid = decision.TargetGuid;
    action.DebugName = ToString(decision.Intent);

    if (decision.Intent == BotCombatIntent::Loot)
    {
        action.Type = "loot";
        return action;
    }
    if (decision.Intent == BotCombatIntent::Recover || decision.Intent == BotCombatIntent::Wait)
    {
        action.Type = "wait";
        action.Valid = false;
        return action;
    }
    if (!bot || !target || !target->IsAlive())
    {
        action.Type = "wait";
        action.Valid = false;
        action.DebugName = "no_valid_target";
        return action;
    }

    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, _runtimeRole.c_str());
    action.MovementDirective = profile.MovementDirective;
    action.AutoAttackMode = profile.AutoAttackMode;
    action.MinRange = profile.MinRange;
    action.MaxRange = profile.MaxRange;

    std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile);
    BotActionCandidate const* best = SelectProfileCombatAction(bot, target, state, profile, candidates);
    if (!best || !best->SpellId)
    {
        action.Type = "wait";
        action.Valid = false;
        action.DebugName = "no_valid_profile_action";
        return action;
    }

    action.Type = "cast";
    action.SpellId = best->SpellId;
    action.TargetGuid = best->Profile.TargetSelector == "self" ? bot->GetGUID() : target->GetGUID();
    action.MovementDirective = best->Profile.MovementDirective.empty() ? profile.MovementDirective : best->Profile.MovementDirective;
    action.AutoAttackMode = best->Profile.AutoAttackMode.empty() ? profile.AutoAttackMode : best->Profile.AutoAttackMode;
    action.MinRange = best->Profile.MinRange > 0.0f ? best->Profile.MinRange : profile.MinRange;
    action.MaxRange = best->Profile.MaxRange > 0.0f ? best->Profile.MaxRange : profile.MaxRange;
    if (best->Profile.MaxRange <= 0.0f)
        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(best->SpellId))
            action.MaxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    action.DebugName = BotCombatActionCatalog::ToString(best->Category);
    return action;
}

bool BotController::TryExecuteQueuedCombatAction(BotActionExecutor& executor, Player* owner, Player* bot, BotActionResult& result)
{
    if (!_queuedCombatAction.Valid || !_queuedCombatAction.SpellId || !_queuedCombatActionMs)
        return false;

    result = executor.ExecuteCombat(owner, bot, _queuedCombatAction);
    if (result == BotActionResult::Ok)
    {
        _queuedCombatAction = ResolvedCombatAction();
        _queuedCombatActionMs = 0;
        return true;
    }

    if (result == BotActionResult::Casting || result == BotActionResult::GlobalCooldown)
    {
        _queuedCombatActionMs = _queuedCombatActionMs > _updateTimer ? _queuedCombatActionMs - _updateTimer : 0;
        if (!_queuedCombatActionMs)
            _queuedCombatAction = ResolvedCombatAction();
        return true;
    }

    _queuedCombatAction = ResolvedCombatAction();
    _queuedCombatActionMs = 0;
    return false;
}
