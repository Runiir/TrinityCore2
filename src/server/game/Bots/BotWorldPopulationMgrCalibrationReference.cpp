#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Map.h"
#include "Player.h"
#include "SpellAuras.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <string>
#include <utility>

namespace
{
struct CalibrationExecuteHealthWindow
{
    char const* Phase;
    uint32 StartMs;
    uint32 EndMs;
    uint8 TargetHealthPct;
    uint8 LowerBoundPct;
    bool LowerBoundInclusive;
    uint8 UpperBoundPct;
    bool UpperBoundInclusive;
};

constexpr uint32 CalibrationSingleTargetDurationMs = 300000;
constexpr std::array<CalibrationExecuteHealthWindow, 5> CalibrationExecuteHealthWindows = {{
    { "above_90",       0,  30000, 95, 90, false, 100, true  },
    { "between_35_90", 30000, 195000, 50, 35, false,  90, true  },
    { "between_25_35",195000, 225000, 30, 25, false,  35, true  },
    { "between_20_25",225000, 240000, 22, 20, false,  25, true  },
    { "below_20",     240000, 300000, 19,  0, true,   20, false },
}};

size_t CalibrationExecuteHealthWindowIndex(uint64 elapsedMs)
{
    for (size_t index = 0; index < CalibrationExecuteHealthWindows.size(); ++index)
        if (elapsedMs < CalibrationExecuteHealthWindows[index].EndMs)
            return index;
    return CalibrationExecuteHealthWindows.size() - 1;
}

bool CalibrationSpecUsesMana(std::string const& targetSpec)
{
    static std::array<char const*, 17> const ManaSpecs = {
        "affliction_warlock", "arcane_mage", "balance_druid",
        "demonology_warlock", "destruction_warlock", "discipline_priest",
        "elemental_shaman", "enhancement_shaman", "fire_mage", "frost_mage",
        "holy_paladin", "holy_priest", "protection_paladin",
        "restoration_druid", "restoration_shaman", "retribution_paladin",
        "shadow_priest",
    };
    return std::find(ManaSpecs.begin(), ManaSpecs.end(), targetSpec) != ManaSpecs.end();
}
}

std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions(Player* bot, Unit* target) const
{
    if (!Cohort().Config.CombatCalibrationReferenceConditions || !bot || !target)
        return { false, false };
    bool const provisioning = !Cohort().CalibrationScoredStartedMs;

    // One real Cataclysm aura from each non-overlapping raid-buff category.
    // This mode is calibration-only: it makes the live dummy conditions closer
    // to the full-raid WoWSims reference without changing damage coefficients.
    static constexpr std::array<uint32, 8> RaidBuffAuras = {
        53646, // Demonic Pact: spell power
        79058, // Arcane Brilliance: intellect and maximum mana
        24932, // Leader of the Pack: critical strike
        2895,  // Wrath of Air Totem: spell haste
        8515,  // Windfury Totem: melee/ranged haste
        8076,  // Strength of Earth: strength and agility
        82930, // Arcane Tactics: 3% damage
        57669, // Replenishment: raid mana regeneration
    };
    bool const replenishmentRequired = CalibrationSpecUsesMana(Cohort().CalibrationTargetSpec);
    for (uint32 spellId : RaidBuffAuras)
    {
        if (spellId == 57669 && !replenishmentRequired)
            continue;
        if (provisioning && !bot->HasAura(spellId))
        {
            // Arcane Brilliance and Replenishment are raid-area spells rather
            // than direct target auras. Execute their real triggered spell path
            // so target selection applies the aura to the calibration clone.
            if (spellId == 79058 || spellId == 57669)
                bot->CastSpell(nullptr, spellId, true);
            else
                bot->AddAura(spellId, bot);
        }
    }

    // Kings and Mark of the Wild are the same 5% primary-stat category. Preserve
    // a candidate's own Kings and provide the level-85 raid-area Mark only when
    // neither base nor current-rank aura is active.
    if (provisioning && !bot->HasAura(20217) && !bot->HasAura(79063)
        && !bot->HasAura(1126) && !bot->HasAura(79061))
        bot->CastSpell(nullptr, 79061, true);

    // A paladin cannot own Kings and Might on itself simultaneously. The
    // calibration tank must retain Kings for its production setup contract;
    // the three DPS clones can still receive the separate reference Might aura.
    if (provisioning && bot->getClass() != CLASS_PALADIN
        && !bot->HasAura(79102))
        bot->AddAura(79102, bot);

    uint32 flaskSpellId = 0;
    std::string const& targetSpec = Cohort().CalibrationTargetSpec;
    switch (bot->getClass())
    {
        case CLASS_PRIEST:
        case CLASS_MAGE:
        case CLASS_WARLOCK:
            flaskSpellId = 79470; // Draconic Mind
            break;
        case CLASS_HUNTER:
        case CLASS_ROGUE:
            flaskSpellId = 79471; // Winds
            break;
        case CLASS_WARRIOR:
        case CLASS_DEATH_KNIGHT:
            flaskSpellId = 79472; // Titanic Strength
            break;
        case CLASS_SHAMAN:
            flaskSpellId = targetSpec == "enhancement_shaman" ? 79471 : 79470;
            break;
        case CLASS_PALADIN:
            flaskSpellId = targetSpec == "holy_paladin" ? 79470 : 79472;
            break;
        case CLASS_DRUID:
            flaskSpellId = targetSpec == "feral_druid_tank" || targetSpec == "feral_druid_dps" ? 79471 : 79470;
            break;
        default:
            break;
    }
    if (provisioning && flaskSpellId && !bot->HasAura(flaskSpellId))
        bot->AddAura(flaskSpellId, bot);

    if (provisioning && targetSpec == "balance_druid"
        && !bot->HasAura(87547))
        bot->AddAura(87547, bot); // Well Fed: 90 Intellect and Stamina

    if (provisioning && targetSpec == "shadow_priest"
        && !bot->HasAura(87547))
        bot->AddAura(87547, bot); // Well Fed: 90 Intellect and Stamina

    // Static external fixture auras are installed only before scoring. Pin
    // finite native durations beyond the half-open 300-second window rather
    // than refreshing or mutating them during the scored interval.
    if (provisioning)
    {
        std::array<uint32, 15> const staticPlayerAuras = {
            53646, 79058, 24932, 2895, 8515, 8076, 82930, 57669,
            20217, 79063, 1126, 79061, 79102, flaskSpellId, 87547,
        };
        for (uint32 spellId : staticPlayerAuras)
            if (spellId)
                if (Aura* aura = bot->GetAura(spellId))
                    if (aura->GetMaxDuration() > 0)
                    {
                        aura->SetMaxDuration(CalibrationSingleTargetDurationMs
                            + 1000);
                        aura->SetDuration(CalibrationSingleTargetDurationMs
                            + 1000);
                    }
    }

    bool buffsReady = std::all_of(RaidBuffAuras.begin(), RaidBuffAuras.end(), [bot, replenishmentRequired](uint32 spellId)
    {
        return (spellId == 57669 && !replenishmentRequired) || bot->HasAura(spellId);
    });
    buffsReady = buffsReady && (bot->HasAura(20217) || bot->HasAura(79063)
        || bot->HasAura(1126) || bot->HasAura(79061));
    buffsReady = buffsReady && (bot->getClass() == CLASS_PALADIN || bot->HasAura(79102));
    buffsReady = buffsReady && (!flaskSpellId || bot->HasAura(flaskSpellId));
    buffsReady = buffsReady && (targetSpec != "balance_druid" || bot->HasAura(87547));
    buffsReady = buffsReady
        && (targetSpec != "shadow_priest" || bot->HasAura(87547));

    // Each clone uses its own nearest dummy, so each clone must own the
    // reference debuffs on that primary target. Keeping caster ownership local
    // also makes Sunder stacking deterministic when AoE splash reaches a
    // neighboring clone's dummy.
    static constexpr std::array<uint32, 3> TargetDebuffAuras = {
        1490,  // Curse of the Elements: magic damage taken
        22959, // Critical Mass: spell critical chance taken
        81326, // Brittle Bones: physical damage taken
    };
    for (uint32 spellId : TargetDebuffAuras)
        if (provisioning && !target->GetAura(spellId, bot->GetGUID()))
            bot->AddAura(spellId, target);

    Aura* sunder = target->GetAura(58567, bot->GetGUID());
    if (provisioning && !sunder)
        sunder = bot->AddAura(58567, target);
    if (provisioning && sunder && sunder->GetStackAmount() < 3)
        sunder->SetStackAmount(3);
    if (provisioning)
    {
        for (uint32 spellId : TargetDebuffAuras)
            if (Aura* aura = target->GetAura(spellId))
            {
                aura->SetMaxDuration(CalibrationSingleTargetDurationMs
                    + 1000);
                aura->SetDuration(CalibrationSingleTargetDurationMs + 1000);
            }
        if (sunder)
        {
            sunder->SetMaxDuration(CalibrationSingleTargetDurationMs + 1000);
            sunder->SetDuration(CalibrationSingleTargetDurationMs + 1000);
        }
    }

    bool targetDebuffsReady = std::all_of(TargetDebuffAuras.begin(), TargetDebuffAuras.end(), [target, bot](uint32 spellId)
    {
        return target->GetAura(spellId, bot->GetGUID()) != nullptr;
    });
    targetDebuffsReady = targetDebuffsReady && sunder && sunder->GetStackAmount() >= 3;
    return { buffsReady, targetDebuffsReady };
}

void BotWorldPopulationMgr::ObserveCalibrationReferenceConditions(
    CalibrationMetrics& metrics, Player* bot, Unit* target,
    uint64 observedAtMs) const
{
    if (!bot || !target || !observedAtMs)
        return;

    static constexpr std::array<uint32, 46> PlayerAuraUniverse = {
        // Static raid/stat categories, flasks, food, and native setup.
        53646, 79058, 24932, 2895, 8515, 8076, 82930, 57669,
        20217, 79063, 1126, 79061, 79102, 79470, 79471, 79472,
        87545, 87546, 87547, 2457, 2458, 768, 24858, 28176, 30482, 48265,
        13165, 31801, 7294,
        588, 15473, 324, 64420,
        // Temporal externals and every v1 disabled racial/tinker spell.
        2825, 10060, 85767, 85759, 96230, 20572, 26297, 28730,
        33697, 33702, 58984, 69041, 82174,
    };
    static constexpr std::array<uint32, 7> TargetAuraUniverse = {
        1490, 22959, 81326, 58567, 16511, 33876, 46857,
    };
    static constexpr std::array<uint32, 13> DisabledDynamicAuraUniverse = {
        2825, 10060, 85767, 85759, 96230, 20572, 26297, 28730,
        33697, 33702, 58984, 69041, 82174,
    };
    static constexpr std::array<uint32, 3> ExternalBleedAuraUniverse = {
        16511, 33876, 46857,
    };

    ++metrics.ReferenceConditionSampleCount;
    if (!metrics.FirstReferenceConditionObservedAtMs)
        metrics.FirstReferenceConditionObservedAtMs = observedAtMs;
    if (metrics.LastReferenceConditionObservedAtMs)
        metrics.MaximumReferenceConditionObservationGapMs = std::max(
            metrics.MaximumReferenceConditionObservationGapMs,
            observedAtMs - metrics.LastReferenceConditionObservedAtMs);
    metrics.LastReferenceConditionObservedAtMs = observedAtMs;

    for (uint32 spellId : PlayerAuraUniverse)
        if (bot->HasAura(spellId))
            ++metrics.ReferencePlayerAuraActiveSamples[spellId];
        else
            ++metrics.ReferencePlayerAuraInactiveSamples[spellId];

    auto hasAuraFromAnotherCaster = [target, bot](uint32 spellId)
    {
        auto const range = target->GetAppliedAuras().equal_range(spellId);
        for (auto itr = range.first; itr != range.second; ++itr)
            if (AuraApplication const* application = itr->second)
                if (Aura const* aura = application->GetBase())
                    if (aura->GetCasterGUID() != bot->GetGUID())
                        return true;
        return false;
    };
    for (uint32 spellId : TargetAuraUniverse)
    {
        bool const active = target->HasAura(spellId);
        Aura const* owned = target->GetAura(spellId, bot->GetGUID());
        if (active)
            ++metrics.ReferenceTargetAuraActiveSamples[spellId];
        else
            ++metrics.ReferenceTargetAuraInactiveSamples[spellId];
        if (owned)
            ++metrics.ReferenceTargetAuraOwnerMatchSamples[spellId];
        if (hasAuraFromAnotherCaster(spellId))
            ++metrics.ReferenceTargetAuraOwnerMismatchSamples[spellId];
    }

    uint8 const sunderStacks = target->GetAura(58567, bot->GetGUID())
        ? target->GetAura(58567, bot->GetGUID())->GetStackAmount() : 0;
    metrics.ReferenceSunderMinimumObservedStacks = std::min(
        metrics.ReferenceSunderMinimumObservedStacks, sunderStacks);
    metrics.ReferenceSunderMaximumObservedStacks = std::max(
        metrics.ReferenceSunderMaximumObservedStacks, sunderStacks);
    if (sunderStacks == 3)
        ++metrics.ReferenceSunderMatchingStackSamples;
    else
        ++metrics.ReferenceSunderMismatchStackSamples;

    if (bot->GetLastPotionId())
        ++metrics.LastPotionIdNonzeroSampleCount;
    if (std::any_of(DisabledDynamicAuraUniverse.begin(),
            DisabledDynamicAuraUniverse.end(),
            [bot](uint32 spellId) { return bot->HasAura(spellId); }))
        ++metrics.UnexpectedDynamicAuraActiveSamples;
    if (std::any_of(ExternalBleedAuraUniverse.begin(),
            ExternalBleedAuraUniverse.end(), hasAuraFromAnotherCaster))
        ++metrics.UnexpectedExternalBleedActiveSamples;
}

void BotWorldPopulationMgr::UpdateCalibrationTargetHealthSchedule(uint64 nowMs)
{
    if (Cohort().CalibrationMode != "single_target_300"
        || Cohort().CalibrationAoePhase
        || Cohort().RuntimeMode != BotWorldRuntimeMode::CalibrationFixture
        || !Cohort().NonCertifyingAssistance
        || !Cohort().CalibrationScoredStartedMs
        || Cohort().CalibrationWindowComplete)
        return;

    if (nowMs < Cohort().CalibrationScoredStartedMs)
        return;
    uint64 const windowElapsedMs = nowMs - Cohort().CalibrationScoredStartedMs;
    if (windowElapsedMs >= CalibrationSingleTargetDurationMs)
        return;

    Player* targetBot = nullptr;
    for (WorldBotState const& state : Party().CalibrationBots)
        if (state.Guid == Cohort().CalibrationTargetGuid)
        {
            targetBot = GetLoadedBot(state);
            break;
        }
    Creature* target = targetBot && targetBot->GetMap()
        ? targetBot->GetMap()->GetCreature(Cohort().CalibrationFixtureTargetGuid)
        : nullptr;
    if (!target || !target->IsAlive() || !target->GetMaxHealth()
        || target->GetMaxHealth() != Cohort().CalibrationFixtureExpectedTargetMaxHealth)
        return;

    auto metricsItr = Cohort().CalibrationMetricsByGuid.find(
        Cohort().CalibrationTargetGuid.GetCounter());
    if (metricsItr == Cohort().CalibrationMetricsByGuid.end())
        return;

    ++Cohort().CalibrationFixtureTargetPassiveObservationSampleCount;
    if (!Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs)
        Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs = nowMs;
    if (Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs)
        Cohort().CalibrationFixtureTargetMaximumPassiveObservationGapMs =
            std::max(Cohort().CalibrationFixtureTargetMaximumPassiveObservationGapMs,
                nowMs - Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs);
    Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs = nowMs;
    if (target->GetVictim())
        ++Cohort().CalibrationFixtureTargetVictimObservationSampleCount;

    size_t const phaseIndex = CalibrationExecuteHealthWindowIndex(windowElapsedMs);
    CalibrationExecuteHealthWindow const& phase =
        CalibrationExecuteHealthWindows[phaseIndex];
    uint64 const desiredHealth = std::max<uint64>(1,
        uint64(target->GetMaxHealth()) * phase.TargetHealthPct / 100);
    if (target->GetHealth() != desiredHealth)
        target->SetHealth(desiredHealth);

    // Capture an actual target read after every server-update reset. Damage
    // callbacks separately capture the pre-event and projected post-event
    // health, so this observation cannot hide between-update threshold drift.
    CalibrationMetrics::TargetHealthPhaseObservation& observation =
        metricsItr->second.TargetHealthPhaseObservations[phaseIndex];
    uint64 const observedHealth = target->GetHealth();
    uint64 const observedMaxHealth = target->GetMaxHealth();
    if (!observation.SampleCount)
        observation.FirstObservedElapsedMs = windowElapsedMs;
    observation.LastObservedElapsedMs = windowElapsedMs;
    ++observation.SampleCount;
    observation.MinimumObservedHealth = std::min(
        observation.MinimumObservedHealth, observedHealth);
    observation.MaximumObservedHealth = std::max(
        observation.MaximumObservedHealth, observedHealth);
    observation.MinimumObservedMaxHealth = std::min(
        observation.MinimumObservedMaxHealth, observedMaxHealth);
    observation.MaximumObservedMaxHealth = std::max(
        observation.MaximumObservedMaxHealth, observedMaxHealth);
}

