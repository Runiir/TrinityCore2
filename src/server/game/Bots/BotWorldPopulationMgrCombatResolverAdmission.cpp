#include "Bots/BotWorldPopulationMgrCombatResolverAdmission.h"

#include "Bots/BotCastWhileMoving.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotElementalSpiritwalkersGrace.h"
#include "Bots/BotEncounterInterruptVeto.h"
#include "Bots/BotRaidCombatPotionHealthOwner.h"
#include "Bots/BotRaidHealthRecoveryGate.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotSpellMinimumRange.h"
#include "Bots/BotTauntVehicleSeat.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrCombatRange.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMangleCooldownPlan.h"
#include "Creature.h"
#include "Group.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellAuraEffects.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <string>
#include <vector>

// Candidate admission for ResolveProfileCombatAction, moved verbatim from
// BotWorldPopulationMgrCombatResolver.cpp: every profile, route, class,
// resource, target and range gate, then the role score and priority bucket
// of each admitted candidate. The resolver builds the candidates before and
// selects among the bests after. Each ProfileCombatAdmission member is bound
// to a local of the resolver's own name, so the gates read unchanged.

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

using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;
using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMeleeChainSemantics;
using BotWorldPopulationMgrSpellSemantics::HasNearbyProtectedEncounterTarget;

}

void BotWorldPopulationMgr::AdmitProfileCombatCandidates(
    ProfileCombatAdmission& admission) const
{
    Player* bot = admission.Bot;
    Unit* target = admission.Target;
    std::string const& role = admission.Role;
    BotClassSpecActionProfile const& profile = admission.Profile;
    bool const raidRotationScope = admission.RaidRotationScope;
    uint32 const targetEntry = admission.TargetEntry;
    bool const solarEclipse = admission.SolarEclipse;
    BotEncounter::MagmawBalanceMushroomState const& mushroomState = admission.MushroomState;
    RoleSaturationState const& saturation = admission.Saturation;
    BotCombatPotionHealthOwner const& potionHealthOwner = admission.PotionHealthOwner;
    BotRaidCooldownReservation::RouteContext const& cooldownRoute = admission.CooldownRoute;
    uint32 const hostileCount = admission.HostileCount;
    bool const densityOnly = admission.DensityOnly;
    uint32 const excludedSpellId = admission.ExcludedSpellId;
    bool const areaOnly = admission.AreaOnly;
    bool const selfCenteredOnly = admission.SelfCenteredOnly;
    bool const forbidArea = admission.ForbidArea;
    bool const hostileTargetOnly = admission.HostileTargetOnly;
    bool const movementCompatibleOnly = admission.MovementCompatibleOnly;
    uint32 const policyExcludedSpellId = admission.PolicyExcludedSpellId;
    uint32 const scopedAreaSpellId = admission.ScopedAreaSpellId;
    uint32 const scopedAreaTargetEntry = admission.ScopedAreaTargetEntry;
    auto const& effectiveSpellMinRange = admission.EffectiveSpellMinRange;
    auto const& effectiveSpellMaxRange = admission.EffectiveSpellMaxRange;
    auto const candidatePreferred = admission.CandidatePreferred;
    std::vector<BotActionCandidate>& candidates = admission.Candidates;
    ResolvedCombatAction& action = admission.Action;
    BotActionCandidate*& best = admission.Best;
    BotActionCandidate*& bestInterrupt = admission.BestInterrupt;
    BotActionCandidate*& bestDensityRecovery = admission.BestDensityRecovery;
    BotActionCandidate*& bestDensityResourceFallback = admission.BestDensityResourceFallback;
    BotActionCandidate*& bestDensityGenerator = admission.BestDensityGenerator;
    BotActionCandidate*& bestDensityFallback = admission.BestDensityFallback;
    BotActionCandidate*& bestRangeRecovery = admission.BestRangeRecovery;
    BotActionCandidate*& bestMagmawMushroomPlacement = admission.BestMagmawMushroomPlacement;
    BotActionCandidate*& bestMagmawMushroomDetonation = admission.BestMagmawMushroomDetonation;
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
    int8 livingGroupHealerCache = -1;
    auto livingGroupHealer = [this, bot, &livingGroupHealerCache]() -> bool
    {
        if (livingGroupHealerCache < 0)
        {
            livingGroupHealerCache = 0;
            if (Group* group = bot->GetGroup())
                for (GroupReference* itr = group->GetFirstMember(); itr; itr = itr->next())
                    if (Player* member = itr->GetSource(); member && member != bot
                        && member->IsAlive() && member->IsInMap(bot)
                        && std::string(GetDungeonRole(member)) == "healer")
                    {
                        livingGroupHealerCache = 1;
                        break;
                    }
        }
        return livingGroupHealerCache == 1;
    };
    bool const targetActivelyCasting = target->IsNonMeleeSpellCast(false);
    // Encounter strategies can veto interrupting a cast (Maloriak's admitted
    // Release Aberrations; r03 cut every release with profile interrupts).
    bool const targetCastVetoed = targetActivelyCasting
        && BotEncounterInterruptVeto::IsCurrentCastVetoed(target,
            CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL);
    bool const exactSingleTargetCalibration =
        Cohort().CalibrationMode == "single_target_300"
        && bot->GetGUID() == Cohort().CalibrationTargetGuid;
    if (profile.SpecTag == BotElementalSpiritwalkersGrace::ElementalSpec)
        BotElementalSpiritwalkersGrace::EvaluateGraceAfterDamageOpportunities(
            candidates);
    BotEncounter::MagmawMangleCooldownPlan::Plan const manglePlan =
        BotEncounter::MagmawMangleCooldownPlan::Observe(bot, role,
            Cohort().EncounterSnapshot.get(), candidates, excludedSpellId,
            policyExcludedSpellId);
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
        if (candidate.RejectReason.empty()
            && candidate.Category == BotCombatActionCategory::Defensive)
            if (char const* bossReserve = BossDefensiveReservationReason(bot, candidate.ResolvedSpellId))
            {
                candidate.RejectReason = bossReserve;
                continue;
            }
        if (candidate.RejectReason.empty())
            if (char const* mangleHold = manglePlan.RejectReason(candidate.SpellId))
            {
                candidate.RejectReason = mangleHold;
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
        bool const candidateHasCastTime =
            BotCastWhileMoving::HasEffectiveCastTime(bot, candidateSpellInfo);
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
        if (HasNearbyProtectedEncounterTarget(bot, target, candidateSpellInfo)
            && SpellHasHostileMultiTargetSemantics(candidateSpellInfo)
            && !magmawMushroomAction
            && (!scopedAreaAction || SpellHasHostileMeleeChainSemantics(candidateSpellInfo)))
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
        if (candidate.Category == BotCombatActionCategory::Interrupt && targetCastVetoed)
        {
            candidate.RejectReason = "encounter_interrupt_vetoed";
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
            && BotTauntVehicleSeat::TauntWouldOnlyPullHolderOntoSeat(bot, target))
        {
            candidate.RejectReason = BotTauntVehicleSeat::RejectReason;
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
        if (BotRaidHealthRecoveryGate::Holds(raidRotationScope,
                hasMechanicTag(candidate.Profile.MechanicTags,
                    BotRaidHealthRecoveryGate::HealthRecoveryTag),
                selfHealthPct, livingGroupHealer))
        {
            candidate.RejectReason = BotRaidHealthRecoveryGate::RejectReason;
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
}
