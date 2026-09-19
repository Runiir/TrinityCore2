#include "Bots/BotSpellMinimumRange.h"
#include "Bots/BotFireCombustionObservation.h"
#include "Bots/BotRaidCombatPotionHealthOwner.h"
#include "Bots/BotSpellResolution.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotCombatMaskEvaluation.h"
#include "Bots/BotRaidAreaObservation.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotCastWhileMoving.h"
#include "Bots/BotElementalSpiritwalkersGrace.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotWorldPopulationMgrCombatRange.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
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
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotRaidAreaObservation::ObserveNearbyProtectedEncounterTarget;

bool MaintainedProfileAuraBlocksRefresh(Unit const* target, BotActionProfileSpell const& spell)
{
    Aura const* aura = target && spell.MaintainAuraId ? target->GetAura(spell.MaintainAuraId) : nullptr;
    if (!aura)
        return false;
    int32 durationMs = aura->GetDuration();
    return !spell.RefreshAuraBelowMs || durationMs < 0 || uint32(durationMs) > spell.RefreshAuraBelowMs;
}

using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;
}

ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction(Player* bot, Unit* target, uint32 hostileCount, bool densityOnly, uint32 excludedSpellId, bool areaOnly, bool selfCenteredOnly, bool forbidArea, bool allowMultidot, bool hostileTargetOnly, bool movementCompatibleOnly, char const* specTagOverride, bool publishDiagnostics, uint32 policyExcludedSpellId, uint32 scopedAreaSpellId, uint32 scopedAreaTargetEntry) const
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

    Creature const* targetCreature = target->ToCreature();
    uint32 const targetEntry = targetCreature ? targetCreature->GetEntry() : 0;
    bool const solarEclipse = bot->HasAura(48517);
    BotEncounter::MagmawBalanceMushroomState const mushroomState =
        BotEncounter::ObserveMagmawBalanceMushroomState(
            bot, Cohort().Config.ValidationRouteEnable,
            Cohort().Config.ValidationRouteNodeId, profile.SpecTag,
            targetEntry, solarEclipse);

    RoleSaturationState saturation = BuildRoleSaturationState(bot, target, role.c_str());
    std::string roleGoal = BotProgressionGoalPolicy::RoleGoal(role);
    uint64 const maskEvaluatedAtMs = BotWorldPopulationMgrSpellSemantics::NowMs();
    std::string const maskEvaluation = BotCombatMaskEvaluation::Context(
        maskEvaluatedAtMs, bot, target, Cohort(), Party(),
        "ResolveProfileCombatAction");
    BotRaidAreaObservation::Observation const areaObservation =
        ObserveNearbyProtectedEncounterTarget(bot, target);
    uint32 const requestedHostileCount = hostileCount;
    auto const potionHealthOwner = BotRaidCombatPotionHealthOwner::Resolve(bot, Cohort(), Party());
    std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile, potionHealthOwner);
    BotRaidCooldownReservation::RouteContext const cooldownRoute{
        Cohort().Config.ValidationRouteEnable,
        Cohort().Raid.RaidInstance,
        Cohort().Raid.EncounterInProgress,
        false,
        Cohort().Config.ValidationRouteKind,
        Cohort().Config.ValidationRouteNodeKind,
        Cohort().Raid.EncounterPhase};
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
        return BotSpellMinimumRange::Effective(bot, target,
            sSpellMgr->GetSpellInfo(candidate.ResolvedSpellId), configuredMinRange);
    };
    auto effectiveSpellMaxRange = [bot, target](BotActionCandidate const& candidate,
        float configuredMaxRange) -> float
    {
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.ResolvedSpellId);
        if (!spellInfo)
            return configuredMaxRange;

        float nativeMaxRange = bot->GetSpellMaxRangeForTarget(target, spellInfo);
        if (spellInfo->RangeEntry
            && (spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE))
            nativeMaxRange = std::max(nativeMaxRange,
                bot->GetMeleeRange(target));
        else
            nativeMaxRange += bot->GetCombatReach() + target->GetCombatReach();
        // An unset melee action maximum inherits native reach. The profile
        // range and raw DBC melee range are approach defaults, not explicit
        // action caps; clipping to them rejects legal large-hitbox attacks.
        if (spellInfo->RangeEntry && (spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE)
            && candidate.Profile.MaxRange <= 0.0f)
            return nativeMaxRange;
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
        && !areaObservation.ProtectedTargetFound
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
                    BotClassSpecActionProfileStore::BuildCandidates(bot, spreadTarget, profile, potionHealthOwner);
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
    BotActionCandidate* bestMagmawMushroomPlacement = nullptr;
    BotActionCandidate* bestMagmawMushroomDetonation = nullptr;
    if (profile.SpecTag == BotElementalSpiritwalkersGrace::ElementalSpec)
        BotElementalSpiritwalkersGrace::EvaluateGraceAfterDamageOpportunities(
            candidates);
    for (BotActionCandidate& candidate : candidates)
    {
        bool const magmawMushroomPlacement =
            BotEncounter::IsMagmawBalanceMushroomPlacement(mushroomState, candidate);
        bool const magmawMushroomDetonation =
            BotEncounter::IsMagmawBalanceMushroomDetonation(mushroomState, candidate);
        bool const magmawMushroomAction =
            BotEncounter::IsMagmawBalanceMushroomAction(mushroomState, candidate);
        bool const scopedAreaAction = scopedAreaSpellId
            && scopedAreaTargetEntry == targetEntry && candidate.SpellId == scopedAreaSpellId;
        if (hostileTargetOnly && candidate.Profile.TargetSelector != "enemy"
            && !magmawMushroomAction)
        {
            candidate.RejectReason = "hostile_target_required";
            continue;
        }
        if (excludedSpellId && candidate.SpellId == excludedSpellId)
        {
            candidate.RejectReason = "temporarily_suppressed";
            continue;
        }
        if (policyExcludedSpellId && candidate.SpellId == policyExcludedSpellId)
        {
            candidate.RejectReason = "target_purpose_excluded";
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
        if (candidate.RejectReason.empty())
            if (char const* reservationReason = BotRaidCooldownReservation::ReservationReason(
                    cooldownRoute, { candidate.Category, candidate.Profile.MechanicTags }))
            {
                candidate.RejectReason = reservationReason;
                continue;
            }
        if (areaOnly && candidate.Category != BotCombatActionCategory::Aoe
            && candidate.Category != BotCombatActionCategory::Cleave)
        {
            candidate.RejectReason = "area_action_required";
            continue;
        }
        if (forbidArea && (candidate.Category == BotCombatActionCategory::Aoe
            || candidate.Category == BotCombatActionCategory::Cleave)
            && !magmawMushroomAction && !scopedAreaAction)
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

        SpellInfo const* candidateSpellInfo = sSpellMgr->GetSpellInfo(candidate.ResolvedSpellId);
        bool const candidateHasCastTime = candidateSpellInfo
            && candidateSpellInfo->CalcCastTime(bot->getLevel()) > 0;
        bool const candidateIsChanneled = candidateSpellInfo
            && candidateSpellInfo->IsChanneled();
        bool const rejectedByMovement = BotCastWhileMoving::RejectMovingCandidate(
            bot, candidateSpellInfo, movementCompatibleOnly,
            candidateHasCastTime, candidateIsChanneled);
        bool const deferLavaBurstMovementRejection =
            BotElementalSpiritwalkersGrace::DeferLavaBurstMovementRejection(
                profile.SpecTag, candidate.SpellId, rejectedByMovement);
        if (rejectedByMovement && !deferLavaBurstMovementRejection)
        {
            candidate.RejectReason = "movement_requires_instant_action";
            continue;
        }
        if (areaObservation.ProtectedTargetFound
            && SpellHasHostileMultiTargetSemantics(candidateSpellInfo)
            && !magmawMushroomAction && !scopedAreaAction)
        {
            candidate.RejectReason = "future_encounter_splash_forbidden";
            continue;
        }
        if (forbidArea && SpellHasHostileMultiTargetSemantics(candidateSpellInfo)
            && !magmawMushroomAction && !scopedAreaAction)
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
            {
                Unit* rangeTarget = candidate.Profile.TargetSelector == "self"
                    ? static_cast<Unit*>(bot) : target;
                float configuredMinimum = candidate.Profile.MinRange > 0.0f
                    ? candidate.Profile.MinRange : profile.MinRange;
                action.MinRange = std::max(action.MinRange,
                    BotSpellMinimumRange::Effective(bot, rangeTarget,
                        candidateSpellInfo, configuredMinimum));
            }
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
            bool const lunarEclipse = bot->HasAura(48518);
            bool const solarMarker = bot->HasAura(67483);
            if (char const* mushroomRejection =
                    BotEncounter::MagmawBalanceMushroomRejection(
                        mushroomState, candidate))
            {
                candidate.RejectReason = mushroomRejection;
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
        if (candidate.Category == BotCombatActionCategory::Taunt
            && HasOtherLiveCohortTankVictim(bot, target))
        {
            candidate.RejectReason = "cohort_threat_established";
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
        bool const candidateSpellIsHostile = candidateSpellInfo
            && !candidateSpellInfo->IsPositive();
        float const selfCenteredHostileMaxRange =
            BotWorldPopulationMgrCombatRange::ResolveSelfCenteredHostileMaxRange(
                selfTarget, target != bot, candidateSpellIsHostile,
                candidate.Profile.MaxRange);
        bool const selfCenteredHostileAction = selfCenteredHostileMaxRange > 0.0f;
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
        if (!BotRaidCombatPotionHealthOwner::MeetsHostileTargetHealthGate(candidate.Profile, target, potionHealthOwner))
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
            if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.ResolvedSpellId))
                maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
        if (!selfTarget)
            maxRange = effectiveSpellMaxRange(candidate, maxRange);
        if (candidate.Profile.RequiresMeleeRange && !bot->IsWithinMeleeRange(actionTarget))
        {
            candidate.RejectReason = "melee_range_required";
            continue;
        }
        if (minRange > 0.0f && distance < minRange)
        {
            action.MinRange = std::max(action.MinRange, minRange);
            action.RangeRecoveryRequired = true;
            candidate.RejectReason = "min_range_required";
            continue;
        }
        if (maxRange > 0.0f && distance > maxRange)
        {
            // A ranged profile can become completely invalid when the target
            // moves beyond every declared action envelope. Preserve that
            // envelope for the executor so it can submit a movement-only
            // recovery instead of entering a no-action backoff loop. Keep the
            // narrowest rejected maximum; it is the only range that is safe
            // for every candidate observed in this resolution.
            if (!densityOnly && candidate.Profile.TargetSelector == "enemy")
            {
                action.RangeRecoveryRequired = true;
                action.MaxRange = action.MaxRange > 0.0f
                    ? std::min(action.MaxRange, maxRange) : maxRange;
                action.MinRange = std::max(action.MinRange, minRange);
            }
            candidate.RejectReason = "max_range_exceeded";
            continue;
        }
        if (deferLavaBurstMovementRejection)
        {
            candidate.RejectReason = std::string(
                BotElementalSpiritwalkersGrace::MovementRejection);
            continue;
        }
        if (profile.SpecTag == BotElementalSpiritwalkersGrace::ElementalSpec
            && candidate.SpellId == BotElementalSpiritwalkersGrace::SpiritwalkersGraceSpellId
            && !BotElementalSpiritwalkersGrace::HasMovementBlockedDamageOpportunity(candidates))
        {
            candidate.RejectReason = "no_movement_blocked_damage_opportunity";
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
        if (magmawMushroomPlacement)
            bestMagmawMushroomPlacement = &candidate;
        if (magmawMushroomDetonation)
            bestMagmawMushroomDetonation = &candidate;
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
    else if (bestMagmawMushroomDetonation)
        best = bestMagmawMushroomDetonation;
    else if (bestMagmawMushroomPlacement)
        best = bestMagmawMushroomPlacement;
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

    // A generic no_valid_profile_action is not actionable by itself. Preserve
    // the full-window native reasons that made every candidate in this
    // resolution invalid, so a canary can distinguish a bad DB gate from a
    // shared arbitration or movement problem without replaying the tail trace.
    if ((!best || !best->SpellId) && bot
        && Cohort().Active && Cohort().Config.ValidationRouteEnable
        && Cohort().Config.ValidationRouteKind == "boss"
        && Party().ValidationRouteGeneration)
    {
        uint32 const botKey = bot->GetGUID().GetCounter();
        uint64 const recordedAtMs = BotWorldPopulationMgrSpellSemantics::NowMs();
        for (BotActionCandidate const& candidate : candidates)
        {
            if (!candidate.SpellId || candidate.RejectReason.empty())
                continue;

            CombatCandidateRejectKey key;
            key.RouteGeneration = Party().ValidationRouteGeneration;
            key.RouteNodeId = Cohort().Config.ValidationRouteNodeId;
            key.ActorGuid = botKey;
            key.Phase = "profile_resolve";
            key.SpellId = candidate.SpellId;
            key.ActionCategory = BotCombatActionCatalog::ToString(candidate.Category);
            key.Reason = candidate.RejectReason;

            CombatCandidateRejectAggregate& aggregate =
                Party().CombatCandidateRejections[key];
            if (!aggregate.Count)
            {
                aggregate.ActorName = bot->GetName();
                aggregate.ActorRole = GetDungeonRole(bot);
                aggregate.ActorClassId = bot->getClass();
                aggregate.FirstAtMs = recordedAtMs;
            }
            aggregate.LastAtMs = recordedAtMs;
            ++aggregate.Count;
        }
    }

    if (publishDiagnostics)
    {
        if (bot->getClass() == CLASS_MAGE && profile.SpecTag == "fire"
            && target && target != bot && bot->IsValidAttackTarget(target)
            && std::any_of(candidates.begin(), candidates.end(), [](BotActionCandidate const& candidate) { return candidate.SpellId == 11129; }))
        {
            auto const observation = BotFireCombustionObservation::Capture(bot, target, maskEvaluatedAtMs,
                BotWorldPopulationMgrSpellSemantics::NowMs());
            candidates.front().ObservationJson = BotFireCombustionObservation::ToJson(observation);
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
        std::ostringstream maskFilters;
        maskFilters << std::boolalpha << "{\"hostile_count\":" << requestedHostileCount
            << ",\"effective_hostile_count\":" << hostileCount
            << ",\"density_only\":" << densityOnly
            << ",\"excluded_spell_id\":" << excludedSpellId
            << ",\"policy_excluded_spell_id\":" << policyExcludedSpellId
            << ",\"area_only\":" << areaOnly
            << ",\"self_centered_only\":" << selfCenteredOnly
            << ",\"forbid_area\":" << forbidArea
            << ",\"allow_multidot\":" << allowMultidot
            << ",\"hostile_target_only\":" << hostileTargetOnly
            << ",\"movement_compatible_only\":" << movementCompatibleOnly
            << ",\"spec_tag_override\":" << BotCombatMaskEvaluation::Quote(specTagOverride ? specTagOverride : "")
            << ",\"area_authority_observation\":" << areaObservation.ObservationJson(forbidArea) << "}";
        Party().LastCombatMaskByBot[botKey] = BotCombatMaskEvaluation::Append(
            BotClassSpecActionProfileStore::CandidateMaskJson(candidates, profile,
                roleGoal.c_str(), saturation.ToJson().c_str()), maskEvaluation,
            maskFilters.str());
        Party().LastChosenCombatByBot[botKey] = BotClassSpecActionProfileStore::ChosenActionJson(best, profile, roleGoal.c_str(), BotRoleSaturationPolicy::ToString(saturation.RecommendedBalanceMode), saturation.ExperimentConfidence);
        Party().LastActionCategoryByBot[botKey] = best ? BotCombatActionCatalog::ToString(best->Category) : "wait";
    }

    if (!best || !best->SpellId)
    {
        bool globalCooldownSchedulingWait = std::any_of(
            candidates.begin(), candidates.end(), [](BotActionCandidate const& candidate)
            {
                return candidate.RejectReason == "global_cooldown";
            });
        std::map<std::string, uint32> rejectionCounts;
        for (BotActionCandidate const& candidate : candidates)
            if (!candidate.RejectReason.empty())
                ++rejectionCounts[candidate.RejectReason];
        auto dominantRejection = std::max_element(
            rejectionCounts.begin(), rejectionCounts.end(),
            [](auto const& left, auto const& right)
            {
                return left.second < right.second;
            });
        action.ResolutionReason = dominantRejection != rejectionCounts.end()
            ? dominantRejection->first : "no_valid_profile_action";
        // Rerun157 showed that a legal Fire filler rejected only by the native
        // GCD lost its spell identity here, so the diagnostic layer could not
        // observe HasGlobalCooldown and mislabeled the scheduling wait as an
        // inactive no_action. Preserve the resolver cause without changing any
        // candidate, cooldown, or role-quality threshold.
        action.DebugName = profile.MissingProfile ? profile.ProfileSource
            : (globalCooldownSchedulingWait ? "global_cooldown"
                                            : (action.ResolutionReason == "already_casting"
                                                ? "already_casting"
                                                : "no_valid_profile_action"));
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
    bool const selectedMagmawMushroomPlacement =
        BotEncounter::IsMagmawBalanceMushroomPlacement(mushroomState, *best);
    bool const selectedMagmawMushroomDetonation =
        BotEncounter::IsMagmawBalanceMushroomDetonation(mushroomState, *best);
    bool const selectedMagmawMushroomAction =
        selectedMagmawMushroomPlacement || selectedMagmawMushroomDetonation;
    action.AllowMagmawBalanceMushroomSplash = selectedMagmawMushroomAction;
    action.AllowScopedEncounterAreaDamage = scopedAreaSpellId
        && scopedAreaTargetEntry == targetEntry && best->SpellId == scopedAreaSpellId;
    if (selectedMagmawMushroomPlacement
        && !BotEncounter::SetMagmawBalanceMushroomGroundTarget(action, bot, target))
    {
        // A destination-location spell must never fall back to the hostile
        // target when the live lava spawn disappeared between observation and
        // submission. Wait for the next lava spawn instead of placing the
        // mushroom on Magmaw or the exposed head.
        action.Valid = false;
        action.ResolutionReason = "magmaw_lava_spawn_ground_target_unavailable";
        action.DebugName = action.ResolutionReason;
        return action;
    }
    action.DebugName = BotCombatActionCatalog::ToString(best->Category);
    action.MovementDirective = best->Profile.MovementDirective.empty() ? profile.MovementDirective : best->Profile.MovementDirective;
    action.AutoAttackMode = best->Profile.AutoAttackMode.empty() ? profile.AutoAttackMode : best->Profile.AutoAttackMode;
    action.InterruptCurrentChanneledSpell = best->InterruptCurrentChanneledSpell;
    action.MinRange = selfTarget ? 0.0f : (best->Profile.MinRange > 0.0f ? best->Profile.MinRange : profile.MinRange);
    if (!selfTarget)
        action.MinRange = effectiveSpellMinRange(*best, action.MinRange);
    // A self-centered hostile action can still have a player-positioning
    // envelope. Shadowflame and Holy Wrath are cast on the player, while the
    // selected hostile remains the movement/facing anchor. Positive self-target
    // actions have no hostile range envelope and therefore resolve to zero.
    SpellInfo const* selectedSpellInfo = sSpellMgr->GetSpellInfo(best->ResolvedSpellId);
    bool const selectedSpellIsHostile = selectedSpellInfo
        && !selectedSpellInfo->IsPositive();
    float const selfCenteredHostileMaxRange =
        BotWorldPopulationMgrCombatRange::ResolveSelfCenteredHostileMaxRange(
            selfTarget, target != bot, selectedSpellIsHostile,
            best->Profile.MaxRange);
    action.MaxRange = selfTarget
        ? selfCenteredHostileMaxRange
        : (best->Profile.MaxRange > 0.0f
            ? best->Profile.MaxRange : profile.MaxRange);
    action.SuppressAreaDamage = forbidArea && !selectedMagmawMushroomAction
        && !action.AllowScopedEncounterAreaDamage;
    if (!selfTarget && best->Profile.MaxRange <= 0.0f)
        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(best->ResolvedSpellId))
            action.MaxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    if (!selfTarget)
        action.MaxRange = effectiveSpellMaxRange(*best, action.MaxRange);
    return action;
}
