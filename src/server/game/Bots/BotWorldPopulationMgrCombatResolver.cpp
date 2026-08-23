#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellAuraEffects.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <list>
#include <sstream>
#include <string>
#include <vector>

namespace
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

bool MaintainedProfileAuraBlocksRefresh(Unit const* target, BotActionProfileSpell const& spell)
{
    Aura const* aura = target && spell.MaintainAuraId ? target->GetAura(spell.MaintainAuraId) : nullptr;
    if (!aura)
        return false;
    int32 durationMs = aura->GetDuration();
    return !spell.RefreshAuraBelowMs || durationMs < 0 || uint32(durationMs) > spell.RefreshAuraBelowMs;
}


bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth = 0)
{
    if (!spellInfo || depth > 4)
        return false;
    // Starfall's owner aura delegates hostile selection to triggered spells;
    // retain the explicit root as a conservative client-data semantic guard.
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

// Future encounter protection must be geometry-aware.  Keeping the global
// entry set is useful for route bookkeeping, but it must not suppress AoE on
// a current trash pack that is nowhere near the protected encounter.

bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target)
{
    if (!owner || !target || !BotRaidAreaAuthority::HasProtectedEncounterEntries(owner->GetGUID().GetRawValue()))
        return false;

    std::vector<WorldObject*> nearbyObjects;
    Trinity::AllWorldObjectsInRange check(target, 45.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
        target, nearbyObjects, check);
    Cell::VisitAllObjects(target, searcher, 45.0f);
    for (WorldObject* object : nearbyObjects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || creature == target || !creature->IsAlive()
            || !owner->IsValidAttackTarget(creature))
            continue;
        if (BotRaidAreaAuthority::IsProtectedEncounterTarget(
                owner->GetGUID().GetRawValue(), creature->GetEntry(),
                creature->GetSpawnId(), creature->GetGUID().GetRawValue()))
            return true;
    }
    return false;
}

}

ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction(Player* bot, Unit* target, uint32 hostileCount, bool densityOnly, uint32 excludedSpellId, bool areaOnly, bool selfCenteredOnly, bool forbidArea, bool allowMultidot, bool hostileTargetOnly, bool movementCompatibleOnly, char const* specTagOverride) const
{
    ResolvedCombatAction action;
    action.Valid = false;
    action.Type = "wait";
    action.DebugName = "no_valid_profile_action";
    if (!bot || !target || !target->IsAlive())
        return action;
    if (Creature const* creature = target->ToCreature();
        IsImmediateNextValidationRouteEncounterMember(creature))
    {
        action.TargetGuid = target->GetGUID();
        action.DebugName = "future_encounter_target_forbidden";
        return action;
    }

    std::string role = GetDungeonRole(bot);
    BotClassSpecActionProfile profile = specTagOverride && *specTagOverride
        ? BotClassSpecActionProfileStore::BuildForSpec(
            bot, role.c_str(), specTagOverride)
        : BotClassSpecActionProfileStore::Build(bot, role.c_str());
    action.MovementDirective = profile.MovementDirective;
    action.AutoAttackMode = profile.AutoAttackMode;
    action.MinRange = profile.MinRange;
    action.MaxRange = profile.MaxRange;

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
    auto effectiveSpellMinRange = [bot, target](BotActionCandidate const& candidate, float configuredMinRange) -> float
    {
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
        if (!spellInfo)
            return configuredMinRange;

        float spellMinRange = bot->GetSpellMinRangeForTarget(target, spellInfo);
        if (spellInfo->RangeEntry && (spellInfo->RangeEntry->Flags & SPELL_RANGE_RANGED))
            spellMinRange += bot->GetMeleeRange(target);
        return std::max(configuredMinRange, spellMinRange);
    };
    auto effectiveSpellMaxRange = [bot, target](BotActionCandidate const& candidate,
        float configuredMaxRange) -> float
    {
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
        if (!spellInfo)
            return configuredMaxRange;

        float nativeMaxRange = bot->GetSpellMaxRangeForTarget(target, spellInfo);
        if (spellInfo->RangeEntry
            && (spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE))
            nativeMaxRange = std::max(nativeMaxRange,
                bot->GetMeleeRange(target));
        else
            nativeMaxRange += bot->GetCombatReach() + target->GetCombatReach();
        // A profile maximum is a policy cap, never permission to extend the
        // native spell envelope.  Shadowflame exposed the distinction: its
        // profile allowed a 15-yard approach while the core rejected that
        // point.  Intersect the configured and native limits so movement and
        // final Spell::CheckRange agree.
        return configuredMaxRange > 0.0f
            ? std::min(configuredMaxRange, nativeMaxRange)
            : nativeMaxRange;
    };

    if (!hostileCount)
    {
        hostileCount = 1;
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(target, 12.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(target, objects, check);
        Cell::VisitAllObjects(target, searcher, 12.0f);
        for (WorldObject* object : objects)
        {
            Unit* unit = object ? object->ToUnit() : nullptr;
            if (unit && unit != target && unit->IsAlive() && bot->IsValidAttackTarget(unit)
                && engagedWithBotParty(unit)
                && !IsImmediateNextValidationRouteEncounterMember(unit->ToCreature()))
                ++hostileCount;
        }
    }

    // Fire AoE is multi-DoT first. Select up to three engaged enemies that do
    // not already carry this mage's Living Bomb, while preserving the normal
    // priority target for every other action.
    if (allowMultidot
        && !HasNearbyProtectedEncounterTarget(bot, target)
        && bot->getClass() == CLASS_MAGE && hostileCount >= 3 && bot->HasSpell(44457))
    {
        std::vector<Unit*> spreadTargets = { target };
        std::vector<WorldObject*> nearbyObjects;
        Trinity::AllWorldObjectsInRange spreadCheck(target, 12.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> spreadSearcher(
            target, nearbyObjects, spreadCheck);
        Cell::VisitAllObjects(target, spreadSearcher, 12.0f);
        for (WorldObject* object : nearbyObjects)
        {
            Unit* unit = object ? object->ToUnit() : nullptr;
            Creature* creature = unit ? unit->ToCreature() : nullptr;
            if (!unit || unit == target || !unit->IsAlive() || !bot->IsValidAttackTarget(unit))
                continue;
            if (IsImmediateNextValidationRouteEncounterMember(creature))
                continue;
            if (!engagedWithBotParty(unit) && (!creature || !IsTrainingDummy(creature)))
                continue;
            spreadTargets.push_back(unit);
        }
        std::sort(spreadTargets.begin(), spreadTargets.end(), [bot](Unit const* left, Unit const* right)
        {
            return bot->GetExactDist(left) < bot->GetExactDist(right);
        });

        uint32 activeLivingBombs = 0;
        for (Unit* spreadTarget : spreadTargets)
            if (spreadTarget->HasAura(44457, bot->GetGUID()))
                ++activeLivingBombs;
        if (activeLivingBombs < 3)
        {
            for (Unit* spreadTarget : spreadTargets)
            {
                if (spreadTarget->HasAura(44457, bot->GetGUID()))
                    continue;
                std::vector<BotActionCandidate> spreadCandidates =
                    BotClassSpecActionProfileStore::BuildCandidates(bot, spreadTarget, profile);
                auto livingBomb = std::find_if(spreadCandidates.begin(), spreadCandidates.end(), [excludedSpellId](BotActionCandidate const& candidate)
                {
                    return candidate.SpellId == 44457 && candidate.SpellId != excludedSpellId
                        && candidate.RejectReason.empty();
                });
                if (livingBomb == spreadCandidates.end())
                    break;

                action.Valid = true;
                action.Type = "cast";
                action.SpellId = 44457;
                action.TargetGuid = spreadTarget->GetGUID();
                action.DebugName = "living_bomb_spread";
                action.MovementDirective = livingBomb->Profile.MovementDirective.empty()
                    ? profile.MovementDirective : livingBomb->Profile.MovementDirective;
                action.AutoAttackMode = livingBomb->Profile.AutoAttackMode.empty()
                    ? profile.AutoAttackMode : livingBomb->Profile.AutoAttackMode;
                action.MinRange = livingBomb->Profile.MinRange > 0.0f
                    ? livingBomb->Profile.MinRange : profile.MinRange;
                action.MaxRange = livingBomb->Profile.MaxRange > 0.0f
                    ? livingBomb->Profile.MaxRange : profile.MaxRange;
                action.InterruptCurrentChanneledSpell = livingBomb->InterruptCurrentChanneledSpell;
                return action;
            }
        }
    }

    bool const targetActivelyCasting = target->IsNonMeleeSpellCast(false);
    BotActionCandidate* best = nullptr;
    BotActionCandidate* bestInterrupt = nullptr;
    BotActionCandidate* bestDensityRecovery = nullptr;
    BotActionCandidate* bestDensityResourceFallback = nullptr;
    BotActionCandidate* bestDensityGenerator = nullptr;
    BotActionCandidate* bestDensityFallback = nullptr;
    BotActionCandidate* bestRangeRecovery = nullptr;
    auto candidatePreferred = [](BotActionCandidate const& candidate, BotActionCandidate const* current) -> bool
    {
        return !current || candidate.Profile.PriorityBucket < current->Profile.PriorityBucket
            || (candidate.Profile.PriorityBucket == current->Profile.PriorityBucket
                && (candidate.Score > current->Score
                    || (candidate.Score == current->Score && candidate.Profile.SortOrder < current->Profile.SortOrder)
                    || (candidate.Score == current->Score && candidate.Profile.SortOrder == current->Profile.SortOrder
                        && candidate.ActionId < current->ActionId)));
    };
    auto hasMechanicTag = [](std::string const& tags, char const* required) -> bool
    {
        size_t start = 0;
        while (start <= tags.size())
        {
            size_t end = tags.find(',', start);
            if (tags.compare(start, (end == std::string::npos ? tags.size() : end) - start, required) == 0)
                return true;
            if (end == std::string::npos)
                break;
            start = end + 1;
        }
        return false;
    };
    bool const exactSingleTargetCalibration =
        Cohort().CalibrationMode == "single_target_300"
        && bot->GetGUID() == Cohort().CalibrationTargetGuid;
    for (BotActionCandidate& candidate : candidates)
    {
        if (hostileTargetOnly && candidate.Profile.TargetSelector != "enemy")
        {
            candidate.RejectReason = "hostile_target_required";
            continue;
        }
        if (excludedSpellId && candidate.SpellId == excludedSpellId)
        {
            candidate.RejectReason = "temporarily_suppressed";
            continue;
        }
        if (exactSingleTargetCalibration && candidate.SpellId == 42650
            && hasMechanicTag(candidate.Profile.MechanicTags, "prepull"))
        {
            // The exact v1 reference replaces the upstream prepull list with
            // fixture-owned setup and therefore contains no Army cast. Keep
            // this ordinary learned cooldown available in dungeons, but do
            // not let a combat-time cast inflate the calibration numerator.
            candidate.RejectReason = "reference_prepull_action_excluded";
            continue;
        }
        if (areaOnly && candidate.Category != BotCombatActionCategory::Aoe
            && candidate.Category != BotCombatActionCategory::Cleave)
        {
            candidate.RejectReason = "area_action_required";
            continue;
        }
        if (forbidArea && (candidate.Category == BotCombatActionCategory::Aoe
            || candidate.Category == BotCombatActionCategory::Cleave))
        {
            candidate.RejectReason = "declarative_area_damage_forbidden";
            continue;
        }
        if (selfCenteredOnly && candidate.Profile.TargetSelector != "self")
        {
            candidate.RejectReason = "self_centered_action_required";
            continue;
        }
        // Rerun165 canary 3 captured a Protection tank owning all 49 Azil
        // followers before density-only selected Seal of Truth twice.  The
        // following snapshot put all 48 survivors on the healer.  Persistent
        // setup already owns self-buff readiness; a density decision must keep
        // its defensive and resource-recovery fallbacks, but never spend the
        // threat opportunity refreshing an ordinary profile buff.
        if (densityOnly && candidate.Category == BotCombatActionCategory::Buff)
        {
            candidate.RejectReason = "density_buff_not_actionable";
            continue;
        }

        SpellInfo const* candidateSpellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
        if (movementCompatibleOnly && candidateSpellInfo
            && (candidateSpellInfo->CalcCastTime(bot->getLevel()) > 0
                || candidateSpellInfo->IsChanneled()))
        {
            candidate.RejectReason = "movement_requires_instant_action";
            continue;
        }
        if (HasNearbyProtectedEncounterTarget(bot, target)
            && SpellHasHostileMultiTargetSemantics(candidateSpellInfo))
        {
            candidate.RejectReason = "future_encounter_splash_forbidden";
            continue;
        }
        if (forbidArea && SpellHasHostileMultiTargetSemantics(candidateSpellInfo))
        {
            candidate.RejectReason = "declarative_area_damage_semantics_forbidden";
            continue;
        }
        if (bot->HasUnitState(UNIT_STATE_CONTROLLED))
        {
            candidate.RejectReason = "caster_controlled";
            continue;
        }
        if (candidateSpellInfo
            && ((candidateSpellInfo->PreventionType == SPELL_PREVENTION_TYPE_SILENCE
                    && bot->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_SILENCED))
                || (candidateSpellInfo->PreventionType == SPELL_PREVENTION_TYPE_PACIFY
                    && bot->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PACIFIED))))
        {
            candidate.RejectReason = "caster_prevented";
            continue;
        }
        if (candidate.Category == BotCombatActionCategory::HealFast
            || candidate.Category == BotCombatActionCategory::HealEfficient
            || candidate.Category == BotCombatActionCategory::HealAoe
            || candidate.Category == BotCombatActionCategory::DispelCleanse
            || candidate.Category == BotCombatActionCategory::ExternalDefensive
            || (candidate.Category == BotCombatActionCategory::Buff
                && candidate.Profile.TargetSelector != "self"))
        {
            candidate.RejectReason = "requires_ally_target";
            continue;
        }
        if (!candidate.RejectReason.empty())
        {
            // Preserve the highest-priority ordinary action that is blocked
            // only by maximum range. Silently falling through to a
            // lower-priority long-range filler makes a declared short-range
            // action permanently unreachable (for example Affliction
            // Shadowflame before Shadow Bolt). Selecting the rejected row
            // here does not submit it: the caller consumes the resolved
            // native range envelope as a normal movement intent, then the
            // profile and core revalidate the spell on a later tick.
            if (!densityOnly && candidate.RejectReason == "out_of_range"
                && candidate.Profile.TargetSelector == "enemy"
                && candidatePreferred(candidate, bestRangeRecovery))
                bestRangeRecovery = &candidate;
            // A ranged profile can spawn inside its dead zone before any action
            // is valid. Preserve the rejected candidate's minimum range so the
            // caller can move outward instead of waiting forever.
            if (candidate.RejectReason == "ranged_range_required")
                action.MinRange = std::max(action.MinRange, 5.0f);
            continue;
        }
        bool candidateIsMajorTankDefensive = role == "tank"
            && candidate.Category == BotCombatActionCategory::Defensive
            && (candidate.SpellId == 498 || candidate.SpellId == 31850 || candidate.SpellId == 86150);
        bool anotherMajorTankDefensiveActive = bot->HasAura(498)
            || bot->HasAura(31850) || bot->HasAura(86150) || bot->HasAura(86659);
        if (candidateIsMajorTankDefensive && anotherMajorTankDefensiveActive
            && !bot->HasAura(candidate.SpellId))
        {
            candidate.RejectReason = "major_tank_defensive_already_active";
            continue;
        }
        if (candidate.Profile.MinEnemies > hostileCount)
        {
            candidate.RejectReason = "enemy_count_too_low";
            continue;
        }
        if (candidate.Profile.MaxEnemies && hostileCount > candidate.Profile.MaxEnemies)
        {
            candidate.RejectReason = "enemy_count_too_high";
            continue;
        }
        if (bot->getClass() == CLASS_DRUID && profile.SpecTag == "balance_druid")
        {
            bool const solarEclipse = bot->HasAura(48517);
            bool const lunarEclipse = bot->HasAura(48518);
            bool const solarMarker = bot->HasAura(67483);
            if (candidate.SpellId == 88747)
            {
                // The base v1 exact fixture owns no Balance mushroom prepull.
                // Placement therefore cannot leak into the scored priority as
                // an unbound simulator-only start-state manufacture.
                candidate.RejectReason = "prepull_only";
                continue;
            }
            if ((candidate.SpellId == 93402 && !solarEclipse)
                || (candidate.SpellId == 8921 && solarEclipse))
            {
                candidate.RejectReason = "eclipse_dot_direction";
                continue;
            }
            if (candidate.SpellId == 16914 && !solarEclipse)
            {
                // Sustained Balance AoE enters Solar Eclipse before channeling
                // Hurricane, preserving Eclipse damage and allowing the pinned
                // an ordinary player-planted mushroom set to detonate when one
                // exists outside the exact base fixture.
                candidate.RejectReason = "solar_aoe_required";
                continue;
            }
            if (candidate.SpellId == 88751)
            {
                SpellInfo const* mushroomSpell = sSpellMgr->GetSpellInfo(88747);
                std::list<Creature*> mushrooms;
                if (mushroomSpell)
                    bot->GetAllMinionsByEntry(mushrooms, uint32(mushroomSpell->Effects[EFFECT_0].MiscValue));
                if (!solarEclipse || mushrooms.size() < 3)
                {
                    candidate.RejectReason = "solar_mushrooms_not_ready";
                    continue;
                }
            }
            if (candidate.SpellId == 2912 || candidate.SpellId == 5176)
            {
                // Continue Starfire after Lunar expires while the Solar marker
                // is still moving toward Solar. Once Solar activates, Wrath takes
                // over and drives the bar back toward Lunar.
                bool const castStarfire = lunarEclipse || (solarMarker && !solarEclipse);
                if ((candidate.SpellId == 2912) != castStarfire)
                {
                    candidate.RejectReason = "eclipse_direction";
                    continue;
                }
            }
        }
        if (bot->getClass() == CLASS_PALADIN
            && (candidate.SpellId == 53600 || candidate.SpellId == 84963)
            && bot->GetPower(POWER_HOLY_POWER) < 3 && !bot->HasAura(90174))
        {
            candidate.RejectReason = "insufficient_holy_power";
            continue;
        }
        if (bot->getClass() == CLASS_MAGE && candidate.SpellId == 11129)
        {
            // WoWSims waits for a meaningful Combustion estimate, not merely
            // the presence of three weak DoTs.  Ignite's current periodic
            // amount is the reliable live proxy available to the bot.  A
            // 10k tick is reachable in raid-normalized P4 gear while avoiding
            // the near-empty Combustions observed in calibration run 225.
            AuraEffect const* ignite = target->GetAuraEffect(12654, EFFECT_0, bot->GetGUID());
            if (!ignite || ignite->GetAmount() < 10000 || !target->HasAura(44457, bot->GetGUID())
                || (!target->HasAura(92315, bot->GetGUID()) && !target->HasAura(11366, bot->GetGUID())))
            {
                candidate.RejectReason = "combustion_dot_window_not_ready";
                continue;
            }
        }
        if (candidate.Profile.RequiresInterruptibleTarget && !targetActivelyCasting)
        {
            candidate.RejectReason = "target_not_interruptible";
            continue;
        }
        float manaPct = bot->GetMaxPower(POWER_MANA)
            ? float(bot->GetPower(POWER_MANA)) / float(bot->GetMaxPower(POWER_MANA)) : 0.0f;
        uint32 attackerCount = uint32(bot->getAttackers().size());
        if (manaPct < candidate.Profile.MinManaPct || manaPct > candidate.Profile.MaxManaPct)
        {
            candidate.RejectReason = "mana_gate";
            continue;
        }
        Powers primaryPowerType = bot->GetPowerType();
        uint32 maxPrimaryPower = bot->GetMaxPower(primaryPowerType);
        float primaryPowerPct = maxPrimaryPower
            ? float(bot->GetPower(primaryPowerType)) / float(maxPrimaryPower) : 0.0f;
        if (primaryPowerPct < candidate.Profile.MinPrimaryPowerPct
            || primaryPowerPct > candidate.Profile.MaxPrimaryPowerPct)
        {
            candidate.RejectReason = "primary_power_gate";
            continue;
        }
        if (attackerCount < candidate.Profile.MinAttackers
            || (candidate.Profile.MaxAttackers && attackerCount > candidate.Profile.MaxAttackers))
        {
            candidate.RejectReason = "attacker_count_gate";
            continue;
        }
        if ((candidate.Profile.RequiresStationary && bot->isMoving())
            || (candidate.Profile.RequiresMoving && !bot->isMoving()))
        {
            candidate.RejectReason = "movement_gate";
            continue;
        }
        if (candidate.Category == BotCombatActionCategory::Taunt
            && (!target->GetVictim() || target->GetVictim() == bot))
        {
            candidate.RejectReason = "threat_already_established";
            continue;
        }
        if (candidate.Profile.RequiresTargetNotVictim && target->GetVictim() == bot)
        {
            candidate.RejectReason = "target_already_on_bot";
            continue;
        }
        if (candidate.Profile.RequiresTargetVictim && target->GetVictim() != bot)
        {
            candidate.RejectReason = "target_not_on_bot";
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
        // Self-targeted hostile cones and point-blank effects still have a
        // hostile positioning envelope. A ranged profile may use one when
        // naturally close, but must not run into melee for it and then retreat
        // for the rest of its rotation. WoWSims likewise treats an out-of-range
        // action as unavailable rather than simulating a movement excursion.
        bool const selfCenteredHostileAction = selfTarget && target != bot
            && candidate.Profile.MaxRange > 0.0f && candidateSpellInfo
            && !candidateSpellInfo->IsPositive();
        Unit* actionTarget = selfTarget ? static_cast<Unit*>(bot) : target;
        if (!selfTarget)
        {
            if (candidateSpellInfo && (actionTarget->IsImmunedToSpell(candidateSpellInfo, bot)
                || (candidateSpellInfo->HasOnlyDamageEffects() && actionTarget->IsImmunedToDamage(candidateSpellInfo))))
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
        float selfHealthPct = UnitHealthPct(bot);
        if (selfHealthPct < candidate.Profile.MinSelfHealthPct || selfHealthPct > candidate.Profile.MaxSelfHealthPct)
        {
            candidate.RejectReason = "self_health_gate";
            continue;
        }
        if (candidate.Profile.RequiredTargetAura && !actionTarget->HasAura(candidate.Profile.RequiredTargetAura))
        {
            candidate.RejectReason = "missing_target_aura";
            continue;
        }
        if (candidate.Profile.ForbiddenTargetAura && actionTarget->HasAura(candidate.Profile.ForbiddenTargetAura))
        {
            candidate.RejectReason = "forbidden_target_aura";
            continue;
        }
        if (MaintainedProfileAuraBlocksRefresh(actionTarget, candidate.Profile))
        {
            candidate.RejectReason = "maintain_aura_active";
            continue;
        }
        float distance = selfCenteredHostileAction
            ? bot->GetExactDist(target)
            : (selfTarget ? 0.0f : bot->GetExactDist(actionTarget));
        float minRange = selfTarget ? 0.0f
            : (candidate.Profile.MinRange > 0.0f ? candidate.Profile.MinRange : profile.MinRange);
        if (!selfTarget)
            minRange = effectiveSpellMinRange(candidate, minRange);
        float maxRange = candidate.Profile.MaxRange > 0.0f ? candidate.Profile.MaxRange : profile.MaxRange;
        if (candidate.Profile.MaxRange <= 0.0f)
            if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId))
                maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
        if (!selfTarget)
            maxRange = effectiveSpellMaxRange(candidate, maxRange);
        if (candidate.Profile.RequiresMeleeRange && !bot->IsWithinMeleeRange(actionTarget))
        {
            candidate.RejectReason = "melee_range_required";
            continue;
        }
        if (candidate.Profile.RequiresRangedRange && distance < 5.0f)
        {
            candidate.RejectReason = "ranged_range_required";
            continue;
        }
        if (minRange > 0.0f && distance < minRange)
        {
            action.MinRange = std::max(action.MinRange, minRange);
            candidate.RejectReason = "min_range_required";
            continue;
        }
        if (maxRange > 0.0f && distance > maxRange)
        {
            candidate.RejectReason = "max_range_exceeded";
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
                if (role == "tank")
                    roleScore += candidate.Profile.ThreatWeight + candidate.Profile.MitigationWeight + candidate.Profile.SurvivalWeight * 0.45f;
                else
                    roleScore += candidate.Profile.DamageWeight + (candidate.Category == BotCombatActionCategory::Interrupt ? 0.6f : 0.0f);
                break;
        }

        candidate.Score = roleScore;
        candidate.Reason = saturation.SaturationReason;
        bool densityRecovery = densityOnly
            && (candidate.Category == BotCombatActionCategory::ResourceGenerator
                || candidate.Category == BotCombatActionCategory::UseItem)
            && hasMechanicTag(candidate.Profile.MechanicTags, "mana_recovery");
        if (targetActivelyCasting && candidate.Category == BotCombatActionCategory::Interrupt
            && candidate.Profile.RequiresInterruptibleTarget)
        {
            if (candidatePreferred(candidate, bestInterrupt))
                bestInterrupt = &candidate;
        }
        else if (densityRecovery)
        {
            if (candidatePreferred(candidate, bestDensityRecovery))
                bestDensityRecovery = &candidate;
        }
        else if (densityOnly && candidate.Category == BotCombatActionCategory::ResourceGenerator
            && hasMechanicTag(candidate.Profile.MechanicTags, "resource_fallback"))
        {
            if (candidatePreferred(candidate, bestDensityResourceFallback))
                bestDensityResourceFallback = &candidate;
        }
        else if (densityOnly && candidate.Category == BotCombatActionCategory::ResourceGenerator)
        {
            if (candidatePreferred(candidate, bestDensityGenerator))
                bestDensityGenerator = &candidate;
        }
        else if (densityOnly)
        {
            if (candidatePreferred(candidate, bestDensityFallback))
                bestDensityFallback = &candidate;
        }
        else if (candidatePreferred(candidate, best))
            best = &candidate;
    }

    // A real, profile-declared interrupt must preempt ordinary rotation choices
    // only while the selected target is actively casting. The candidate has
    // already passed resource, cooldown, range, and all other profile gates.
    if (bestInterrupt)
        best = bestInterrupt;
    else if (!densityOnly && bestRangeRecovery
        && candidatePreferred(*bestRangeRecovery, best))
        best = bestRangeRecovery;
    else if (densityOnly)
    {
        Powers primaryPowerType = bot->GetPowerType();
        uint32 maxPrimaryPower = bot->GetMaxPower(primaryPowerType);
        float primaryPowerPct = maxPrimaryPower
            ? float(bot->GetPower(primaryPowerType)) / float(maxPrimaryPower) : 1.0f;
        bool resourcePressure = primaryPowerPct <= 0.25f;
        if (bot->GetMaxPower(POWER_MANA))
            resourcePressure = float(bot->GetPower(POWER_MANA)) / float(bot->GetMaxPower(POWER_MANA)) <= 0.25f;
        best = bestDensityRecovery
            ? bestDensityRecovery
            : (bestDensityResourceFallback
                ? bestDensityResourceFallback
                : (resourcePressure && bestDensityGenerator
                    ? bestDensityGenerator
                    : (bestDensityFallback ? bestDensityFallback : bestDensityGenerator)));
    }

    uint32 botKey = bot->GetGUID().GetCounter();
    std::ostringstream rejectionJson;
    rejectionJson << '[';
    bool firstReject = true;
    for (BotActionCandidate const& candidate : candidates)
    {
        if (!candidate.SpellId || candidate.RejectReason.empty())
            continue;
        if (!firstReject)
            rejectionJson << ',';
        firstReject = false;
        rejectionJson << "{\"spell_id\":" << candidate.SpellId
                      << ",\"reason\":\"" << JsonEscape(candidate.RejectReason) << "\"}";
    }
    rejectionJson << ']';
    Party().LastCombatRejectsByBot[botKey] = rejectionJson.str();
    Party().LastSaturationByBot[botKey] = saturation;
    Party().LastCombatMaskByBot[botKey] = BotClassSpecActionProfileStore::CandidateMaskJson(candidates, profile, roleGoal.c_str(), saturation.ToJson().c_str());
    Party().LastChosenCombatByBot[botKey] = BotClassSpecActionProfileStore::ChosenActionJson(best, profile, roleGoal.c_str(), BotRoleSaturationPolicy::ToString(saturation.RecommendedBalanceMode), saturation.ExperimentConfidence);
    Party().LastActionCategoryByBot[botKey] = best ? BotCombatActionCatalog::ToString(best->Category) : "wait";

    if (!best || !best->SpellId)
    {
        bool globalCooldownSchedulingWait = std::any_of(
            candidates.begin(), candidates.end(), [](BotActionCandidate const& candidate)
            {
                return candidate.RejectReason == "global_cooldown";
            });
        // Rerun157 showed that a legal Fire filler rejected only by the native
        // GCD lost its spell identity here, so the diagnostic layer could not
        // observe HasGlobalCooldown and mislabeled the scheduling wait as an
        // inactive no_action. Preserve the resolver cause without changing any
        // candidate, cooldown, or role-quality threshold.
        action.DebugName = profile.MissingProfile ? profile.ProfileSource
            : (globalCooldownSchedulingWait ? "global_cooldown"
                                            : "no_valid_profile_action");
        if (!profile.MissingProfile && !areaOnly && profile.AutoAttackMode == "melee"
            && bot->IsValidAttackTarget(target))
        {
            // Rerun169 canary 3 reached a remote healer-owned cluster after every
            // native Protection pickup was temporarily unavailable. The fallback
            // retained the profile's ranged maximum, so ordinary trash considered
            // it in range and repeatedly submitted a remote melee fallback without
            // closing range across the eligible exposure interval. Describe its actual
            // native reach so the existing caller movement gate closes range
            // before retrying it.
            action.Valid = true;
            action.Type = "auto_attack";
            action.TargetGuid = target->GetGUID();
            action.DebugName = "melee_auto_attack_fallback";
            action.MinRange = 0.0f;
            action.MaxRange = std::max(5.0f, bot->GetMeleeRange(target));
        }
        return action;
    }

    action.Valid = true;
    action.Type = best->Category == BotCombatActionCategory::UseItem ? "use_item" : "cast";
    action.SpellId = best->SpellId;
    bool selfTarget = best->Profile.TargetSelector == "self";
    action.TargetGuid = selfTarget ? bot->GetGUID() : target->GetGUID();
    action.DebugName = BotCombatActionCatalog::ToString(best->Category);
    action.MovementDirective = best->Profile.MovementDirective.empty() ? profile.MovementDirective : best->Profile.MovementDirective;
    action.AutoAttackMode = best->Profile.AutoAttackMode.empty() ? profile.AutoAttackMode : best->Profile.AutoAttackMode;
    action.InterruptCurrentChanneledSpell = best->InterruptCurrentChanneledSpell;
    action.MinRange = selfTarget ? 0.0f : (best->Profile.MinRange > 0.0f ? best->Profile.MinRange : profile.MinRange);
    if (!selfTarget)
        action.MinRange = effectiveSpellMinRange(*best, action.MinRange);
    // A self-centered hostile action can still have a player-positioning
    // envelope. Shadowflame and Holy Wrath are cast on the player, while the
    // selected hostile remains the movement/facing anchor. Preserve an
    // explicitly configured maximum for that generic action shape; the final
    // native cast still targets self and validates its own spell contract.
    action.MaxRange = selfTarget
        ? best->Profile.MaxRange
        : (best->Profile.MaxRange > 0.0f
            ? best->Profile.MaxRange : profile.MaxRange);
    action.SuppressAreaDamage = forbidArea;
    if (!selfTarget && best->Profile.MaxRange <= 0.0f)
        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(best->SpellId))
            action.MaxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    if (!selfTarget)
        action.MaxRange = effectiveSpellMaxRange(*best, action.MaxRange);
    return action;
}
