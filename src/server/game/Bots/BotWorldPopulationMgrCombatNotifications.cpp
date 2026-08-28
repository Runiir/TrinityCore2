#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "GameTime.h"
#include "Log.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Totem.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <limits>
#include <utility>

namespace
{
constexpr uint32 CalibrationSingleTargetDurationMs = 300000;
constexpr uint32 ShadowBiteSpellId = 54049;

bool IsSharedDamageCallback(uint32 spellId, uint32 damageType)
{
    if (damageType != uint32(NODAMAGE) || !spellId)
        return false;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    return spellInfo && spellInfo->HasAura(SPELL_AURA_SHARE_DAMAGE_PCT);
}

struct PendingPeriodicOutcome
{
    Unit* Attacker = nullptr;
    Unit* Victim = nullptr;
    uint32 SpellId = 0;
    bool Critical = false;
    float CritChancePct = 0.0f;
    bool Armed = false;
};

thread_local PendingPeriodicOutcome PendingOutcome;

struct CalibrationExecuteHealthWindow
{
    uint32 EndMs;
    uint8 TargetHealthPct;
};

constexpr std::array<CalibrationExecuteHealthWindow, 5> CalibrationExecuteHealthWindows = {{
    { 30000, 95 },
    { 195000, 50 },
    { 225000, 30 },
    { 240000, 22 },
    { 300000, 19 },
}};

size_t CalibrationExecuteHealthWindowIndex(uint64 elapsedMs)
{
    for (size_t index = 0; index < CalibrationExecuteHealthWindows.size(); ++index)
        if (elapsedMs < CalibrationExecuteHealthWindows[index].EndMs)
            return index;
    return CalibrationExecuteHealthWindows.size() - 1;
}

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

Player* CombatOwnerPlayer(Unit* unit)
{
    if (!unit)
        return nullptr;
    if (Player* player = unit->GetCharmerOrOwnerPlayerOrPlayerItself())
        return player;
    Unit* current = unit;
    for (uint8 depth = 0; depth < 4 && current; ++depth)
    {
        current = current->IsTotem() ? current->ToTotem()->GetOwner() : current->GetCharmerOrOwner();
        if (!current)
            break;
        if (Player* player = current->ToPlayer())
            return player;
    }
    return nullptr;
}

std::vector<uint32> ObserveOwnerCastWarlockPeriodicDamageAuraSpellIds(
    Player* owner, Unit* victim)
{
    std::vector<uint32> spellIds;
    if (!owner || owner->getClass() != CLASS_WARLOCK || !victim)
        return spellIds;

    for (auto const& [_, application] : victim->GetAppliedAuras())
    {
        Aura const* aura = application ? application->GetBase() : nullptr;
        SpellInfo const* spellInfo = aura ? aura->GetSpellInfo() : nullptr;
        if (!spellInfo || aura->GetCasterGUID() != owner->GetGUID())
            continue;

        bool periodicDamage = false;
        for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
        {
            AuraType const auraType = AuraType(
                spellInfo->Effects[effectIndex].ApplyAuraName);
            if (auraType == SPELL_AURA_PERIODIC_DAMAGE)
            {
                periodicDamage = true;
                break;
            }
        }
        if (periodicDamage)
            spellIds.push_back(spellInfo->Id);
    }

    std::sort(spellIds.begin(), spellIds.end());
    return spellIds;
}
}

void BotWorldPopulationMgr::NotifyCombatAttackAttempt(Unit* attacker,
    Unit* victim)
{
    if (!Cohort().Active || !attacker || !victim
        || !Cohort().CalibrationScoredStartedMs
        || Cohort().CalibrationWindowComplete
        || attacker->GetGUID()
            != Cohort().CalibrationFixtureTargetGuid)
        return;

    uint64 const nowMs = NowMs();
    if (nowMs >= Cohort().CalibrationScoredStartedMs
        && nowMs - Cohort().CalibrationScoredStartedMs
            < CalibrationSingleTargetDurationMs)
        ++Cohort().CalibrationFixtureTargetAttackEventCount;
}


void BotWorldPopulationMgr::NotifyCombatHeal(Unit* healer, Unit* target, uint32 spellId, uint32 attemptedHeal,
    uint32 effectiveHeal, uint32 absorbedHeal)
{
    if (!Cohort().Active || !healer || !target || (!attemptedHeal && !effectiveHeal && !absorbedHeal))
        return;

    if (Player* calibrationHealer = CombatOwnerPlayer(healer))
    {
        auto calibration = Cohort().CalibrationMetricsByGuid.find(calibrationHealer->GetGUID().GetCounter());
        bool const scored = Cohort().CalibrationScoredStartedMs && !Cohort().CalibrationWindowComplete
            && NowMs() >= Cohort().CalibrationScoredStartedMs
            && NowMs() - Cohort().CalibrationScoredStartedMs <= 300000;
        if (calibration != Cohort().CalibrationMetricsByGuid.end() && scored)
        {
            CalibrationMetrics& metrics = calibration->second;
            metrics.AttemptedHealing += attemptedHeal;
            metrics.EffectiveHealing += effectiveHeal;
            metrics.AbsorbedHealing += absorbedHeal;
            if (effectiveHeal || absorbedHeal)
            {
                uint32 const targetGuid = target->GetGUID().GetCounter();
                ++metrics.HealTargetCounts[targetGuid];
                auto damaged = metrics.LastControlledDamageMsByTarget.find(targetGuid);
                if (damaged != metrics.LastControlledDamageMsByTarget.end())
                {
                    uint64 const eventMs = damaged->second;
                    metrics.HealResponseLatenciesMs.push_back(uint32(std::min<uint64>(
                        NowMs() - eventMs, std::numeric_limits<uint32>::max())));
                    for (auto itr = metrics.LastControlledDamageMsByTarget.begin();
                        itr != metrics.LastControlledDamageMsByTarget.end();)
                        if (itr->second == eventMs)
                            itr = metrics.LastControlledDamageMsByTarget.erase(itr);
                        else
                            ++itr;
                }
            }
            return;
        }
    }

    Player* sourceActor = FindCombatLogCohortPlayer(healer);
    Player* targetActor = FindCombatLogCohortPlayer(target);
    if (!sourceActor && !targetActor)
        return;

    uint64 nowMs = NowMs();
    ++Party().CombatLogEventCount;
    if (sourceActor)
        AddCombatLogAggregate(CombatLogPerspective::HealingDone, sourceActor, healer, target, spellId,
            0, effectiveHeal, attemptedHeal, absorbedHeal, nowMs);
    if (targetActor)
        AddCombatLogAggregate(CombatLogPerspective::HealingReceived, targetActor, healer, target, spellId,
            0, effectiveHeal, attemptedHeal, absorbedHeal, nowMs);
    AddCombatLogEvent("heal", sourceActor ? sourceActor : targetActor, healer, target, spellId,
        0, 0, effectiveHeal, attemptedHeal, absorbedHeal, nowMs);
}

void BotWorldPopulationMgr::PrepareCombatPeriodicOutcome(Unit* attacker,
    Unit* victim, uint32 spellId, bool critical, float critChancePct)
{
    PendingOutcome = { attacker, victim, spellId, critical, critChancePct, true };
}

void BotWorldPopulationMgr::NotifyCombatDamage(Unit* attacker, Unit* victim, uint32 spellId, uint32 damage,
    uint32 unmitigatedDamage, uint32 damageType, uint32 schoolMask)
{
    PendingPeriodicOutcome const pending = std::exchange(
        PendingOutcome, PendingPeriodicOutcome{});
    bool const critical = pending.Armed
        && pending.Attacker == attacker
        && pending.Victim == victim
        && pending.SpellId == spellId
        && damageType == uint32(DOT)
        && pending.Critical;
    bool const criticalOutcomeAvailable = pending.Armed
        && pending.Attacker == attacker
        && pending.Victim == victim
        && pending.SpellId == spellId
        && damageType == uint32(DOT);
    float const critChancePct = pending.Armed
        && pending.Attacker == attacker
        && pending.Victim == victim
        && pending.SpellId == spellId
        && damageType == uint32(DOT)
            ? pending.CritChancePct : 0.0f;

    if (!Cohort().Active || !attacker || !victim || (!damage && !unmitigatedDamage))
        return;

    bool const sharedDamage = IsSharedDamageCallback(spellId, damageType);
    if (!sharedDamage && Cohort().CalibrationScoredStartedMs
        && !Cohort().CalibrationWindowComplete
        && attacker->GetGUID()
            == Cohort().CalibrationFixtureTargetGuid
        && NowMs() >= Cohort().CalibrationScoredStartedMs
        && NowMs() - Cohort().CalibrationScoredStartedMs
            < CalibrationSingleTargetDurationMs)
        ++Cohort().CalibrationFixtureTargetOriginatedDamageEventCount;

    Player* owner = CombatOwnerPlayer(attacker);
    if (owner)
    {
        auto calibration = Cohort().CalibrationMetricsByGuid.find(owner->GetGUID().GetCounter());
        if (calibration != Cohort().CalibrationMetricsByGuid.end())
        {
            uint64 const nowMs = NowMs();
            uint64 const windowElapsedMs = Cohort().CalibrationScoredStartedMs
                && nowMs >= Cohort().CalibrationScoredStartedMs
                    ? nowMs - Cohort().CalibrationScoredStartedMs : 0;
            bool const scored = Cohort().CalibrationScoredStartedMs && !Cohort().CalibrationWindowComplete
                && nowMs >= Cohort().CalibrationScoredStartedMs
                && windowElapsedMs < CalibrationSingleTargetDurationMs;
            if (scored && sharedDamage)
                return;
            if (scored)
                ObserveWillOfUnbinding(calibration->second, owner, nowMs);
            if (!scored)
            {
                // The exact request is half-open [0, 300000). A map damage
                // callback can race the manager's completion tick at exactly
                // 300000 ms. Diagnose that normal update-order boundary
                // exclusion separately: it is neither numerator damage nor
                // acceptance-gated cross-window contamination.
                if (Cohort().CalibrationScoredStartedMs
                    && !Cohort().CalibrationWindowComplete
                    && nowMs >= Cohort().CalibrationScoredStartedMs
                    && windowElapsedMs >= CalibrationSingleTargetDurationMs)
                {
                    ++Cohort().CalibrationExcludedBoundaryDamageEventCount;
                    TC_LOG_WARN("server", "BotWorld calibration boundary damage excluded owner=%s attacker=%s victim=%s spell=%u elapsed_ms=%llu damage=%u raw=%u",
                        owner->GetGUID().ToString().c_str(), attacker->GetGUID().ToString().c_str(),
                        victim->GetGUID().ToString().c_str(), spellId,
                        static_cast<unsigned long long>(windowElapsedMs), damage,
                        unmitigatedDamage);
                }
                // A final channel tick can already be queued when the exact
                // 300-second boundary interrupts the cast. Give that in-flight
                // delivery one normal three-second periodic interval to drain;
                // anything later is genuine cross-window contamination.
                if (Cohort().CalibrationWindowComplete && Cohort().CalibrationScoredEndedMs
                    && nowMs > Cohort().CalibrationScoredEndedMs + 3000)
                {
                    ++Cohort().CalibrationCrossWindowEventCount;
                    TC_LOG_WARN("server", "BotWorld calibration post-window damage owner=%s attacker=%s victim=%s spell=%u damage=%u raw=%u",
                        owner->GetGUID().ToString().c_str(), attacker->GetGUID().ToString().c_str(),
                        victim->GetGUID().ToString().c_str(), spellId, damage, unmitigatedDamage);
                }
                return;
            }
            uint32 measuredDamage = damage ? damage : unmitigatedDamage;
            bool const exactPetDamage = owner->GetPet() == attacker;
            if (exactPetDamage && spellId == ShadowBiteSpellId
                && calibration->second.PrimaryPetShadowBiteEvents.size() < 128)
            {
                CalibrationMetrics::PrimaryPetShadowBiteEvent event;
                event.ElapsedMs = windowElapsedMs;
                event.MeasuredDamage = measuredDamage;
                event.UnmitigatedDamage = unmitigatedDamage;
                // This notification receives resolved amounts, not the
                // DamageInfo hit mask. Keep crit chance as an observation and
                // do not infer a hit/crit outcome from the amounts.
                if (Pet* pet = attacker->ToPet())
                {
                    event.PetSpellPower = pet->GetBonusDamage();
                    if (SpellInfo const* shadowBite = sSpellMgr->GetSpellInfo(spellId))
                        event.PetSpellCritPct = pet->SpellCritChanceDone(
                            shadowBite, shadowBite->GetSchoolMask());
                }
                event.OwnerCastWarlockPeriodicDamageAuraSpellIds =
                    ObserveOwnerCastWarlockPeriodicDamageAuraSpellIds(owner, victim);
                calibration->second.PrimaryPetShadowBiteEvents.push_back(std::move(event));
            }
            bool const isolatedSingleTarget =
                Cohort().CalibrationMode == "single_target_300";
            bool const primaryTargetDamage = isolatedSingleTarget
                && !Cohort().CalibrationFixtureTargetGuid.IsEmpty()
                && victim->GetGUID() == Cohort().CalibrationFixtureTargetGuid;
            if (primaryTargetDamage)
                ObserveAfflictionDamageStage(calibration->second, owner, victim,
                    spellId, measuredDamage, unmitigatedDamage, damageType,
                    critical, critChancePct);
            if (primaryTargetDamage)
                ObserveAfflictionLandedEvent(calibration->second, attacker,
                    owner, victim, spellId, damage, unmitigatedDamage,
                    damageType, critical, criticalOutcomeAvailable,
                    critChancePct, windowElapsedMs);
            if (primaryTargetDamage
                && Cohort().RuntimeMode == BotWorldRuntimeMode::CalibrationFixture
                && Cohort().NonCertifyingAssistance)
            {
                // Damage can land between population-manager updates, including
                // on the first millisecond of a new execute band. Apply that
                // exact wall-clock band before reading pre-damage health so a
                // stale prior-band value cannot be attributed to the new band.
                UpdateCalibrationTargetHealthSchedule(nowMs);
                if (windowElapsedMs < CalibrationSingleTargetDurationMs)
                {
                    size_t const phaseIndex =
                        CalibrationExecuteHealthWindowIndex(windowElapsedMs);
                    CalibrationMetrics::TargetHealthPhaseObservation& observation =
                        calibration->second.TargetHealthPhaseObservations[phaseIndex];
                    uint64 const preDamageHealth = victim->GetHealth();
                    // Training dummies can suppress landed health loss while
                    // retaining the authoritative pre-suppression damage. The
                    // scored numerator already uses this same measuredDamage
                    // fallback, so the execute-band event proof must bind that
                    // amount rather than recording a zero-sized hit.
                    uint64 const projectedPostDamageHealth = preDamageHealth > measuredDamage
                        ? preDamageHealth - measuredDamage : 0;
                    uint64 const maximumHealth = victim->GetMaxHealth();
                    if (!observation.DamageEventSampleCount)
                        observation.FirstDamageEventElapsedMs = windowElapsedMs;
                    observation.LastDamageEventElapsedMs = windowElapsedMs;
                    ++observation.DamageEventSampleCount;
                    observation.MinimumPreDamageHealth = std::min(
                        observation.MinimumPreDamageHealth, preDamageHealth);
                    observation.MaximumPreDamageHealth = std::max(
                        observation.MaximumPreDamageHealth, preDamageHealth);
                    observation.MinimumProjectedPostDamageHealth = std::min(
                        observation.MinimumProjectedPostDamageHealth,
                        projectedPostDamageHealth);
                    observation.MaximumProjectedPostDamageHealth = std::max(
                        observation.MaximumProjectedPostDamageHealth,
                        projectedPostDamageHealth);
                    observation.MinimumDamageEventMaxHealth = std::min(
                        observation.MinimumDamageEventMaxHealth, maximumHealth);
                    observation.MaximumDamageEventMaxHealth = std::max(
                        observation.MaximumDamageEventMaxHealth, maximumHealth);
                    observation.MaximumDamageEvent = std::max(
                        observation.MaximumDamageEvent, measuredDamage);
                }
            }
            if (isolatedSingleTarget && !primaryTargetDamage)
            {
                calibration->second.OffTargetDamage += measuredDamage;
                if (calibration->second.OffTargetDamageEvents.size() < 128)
                {
                    CalibrationMetrics::OffTargetDamageEvent event;
                    event.ElapsedMs = windowElapsedMs;
                    event.AttackerGuid = attacker->GetGUID().GetCounter();
                    event.VictimGuid = victim->GetGUID().GetCounter();
                    event.VictimEntry = victim->GetEntry();
                    event.SpellId = spellId;
                    if (Spell* current = attacker->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                        event.CurrentGenericSpellId = current->GetSpellInfo()->Id;
                    if (Spell* current = attacker->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                        event.CurrentChanneledSpellId = current->GetSpellInfo()->Id;
                    event.Damage = measuredDamage;
                    event.VictimTypeId = uint8(victim->GetTypeId());
                    event.VictimIsOwner = victim == owner;
                    auto appendPeriodicHealthAuras = [&event](Unit* holder)
                    {
                        if (!holder)
                            return;
                        for (auto const& [_, application] : holder->GetAppliedAuras())
                        {
                            Aura const* aura = application ? application->GetBase() : nullptr;
                            SpellInfo const* spellInfo = aura ? aura->GetSpellInfo() : nullptr;
                            if (!spellInfo)
                                continue;
                            for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
                            {
                                AuraType const auraType = AuraType(spellInfo->Effects[effectIndex].ApplyAuraName);
                                if (auraType != SPELL_AURA_OBS_MOD_HEALTH
                                    && auraType != SPELL_AURA_PERIODIC_HEALTH_FUNNEL)
                                    continue;
                                CalibrationMetrics::OffTargetDamageEvent::PeriodicHealthAuraCandidate candidate;
                                candidate.SpellId = aura->GetId();
                                candidate.HolderGuid = holder->GetGUID().GetCounter();
                                candidate.CasterGuid = aura->GetCasterGUID().GetCounter();
                                candidate.EffectIndex = effectIndex;
                                candidate.AuraType = uint16(auraType);
                                event.PeriodicHealthAuraCandidates.push_back(candidate);
                            }
                        }
                    };
                    appendPeriodicHealthAuras(owner);
                    appendPeriodicHealthAuras(owner->GetPet());
                    calibration->second.OffTargetDamageEvents.push_back(event);
                }
            }
            else
            {
                calibration->second.Damage += measuredDamage;
                if (primaryTargetDamage)
                    calibration->second.PrimaryTargetDamage += measuredDamage;
                if (attacker != owner)
                    calibration->second.PetDamage += measuredDamage;
                calibration->second.SpellDamage[spellId] += measuredDamage;
                ++calibration->second.SpellDamageEvents[spellId];
                if (exactPetDamage)
                {
                    calibration->second.PrimaryPetSpellDamage[spellId] += measuredDamage;
                    ++calibration->second.PrimaryPetSpellDamageEvents[spellId];
                }
            }
            if (Creature* dummy = victim->ToCreature(); dummy && IsTrainingDummy(dummy))
            {
                calibration->second.LastDamageMsByTarget[dummy->GetGUID().GetCounter()] = nowMs;
                calibration->second.TargetCount = uint32(
                    calibration->second.LastDamageMsByTarget.size());
            }
            return;
        }
    }

    Player* sourceActor = FindCombatLogCohortPlayer(attacker);
    Player* targetActor = FindCombatLogCohortPlayer(victim);
    if (!sourceActor && !targetActor)
        return;

    uint64 nowMs = NowMs();
    ++Party().CombatLogEventCount;
    if (sourceActor)
        AddCombatLogAggregate(CombatLogPerspective::DamageDone, sourceActor, attacker, victim, spellId,
            damageType, damage, unmitigatedDamage, 0, nowMs, sharedDamage);
    if (targetActor)
        AddCombatLogAggregate(CombatLogPerspective::DamageTaken, targetActor, attacker, victim, spellId,
            damageType, damage, unmitigatedDamage, 0, nowMs, sharedDamage);
    AddCombatLogEvent("damage", sourceActor ? sourceActor : targetActor, attacker, victim, spellId,
        damageType, schoolMask, damage, unmitigatedDamage, 0, nowMs, sharedDamage);
}
