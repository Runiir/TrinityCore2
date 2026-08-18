#include "Bots/BotWorldPopulationMgr.h"

#include "GameTime.h"
#include "Player.h"
#include "Totem.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <limits>

namespace
{
constexpr uint32 CalibrationSingleTargetDurationMs = 300000;

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
