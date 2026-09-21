#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Player.h"
#include "Unit.h"

namespace
{
constexpr uint32 DragonwrathAuraSpellId = 101056;
constexpr uint32 CalibrationSingleTargetDurationMs = 300000;
}

void BotWorldPopulationMgr::NotifyDragonwrathCopyProcStart(
    Unit* caster, uint32 originalSpellId, uint32 copySpellId)
{
    // This marker is observation-only. It scopes only the synchronous native
    // copy cast and never retries, changes, or scores the spell.
    if (!caster || !originalSpellId || !copySpellId)
        return;
    CohortScope scope = ScopeCallbackCohort(caster);
    if (!scope)
        return;
    if (!Cohort().Active || !Cohort().CalibrationActive
        || Cohort().CalibrationMode != "single_target_300"
        || !Cohort().CalibrationScoredStartedMs
        || Cohort().CalibrationWindowComplete)
        return;

    Player* bot = caster->ToPlayer();
    if (!bot || !bot->HasAura(DragonwrathAuraSpellId))
        return;

    uint64 const nowMs = BotWorldPopulationMgrSpellSemantics::NowMs();
    if (nowMs < Cohort().CalibrationScoredStartedMs
        || nowMs - Cohort().CalibrationScoredStartedMs
            >= CalibrationSingleTargetDurationMs)
        return;

    auto metrics = Cohort().CalibrationMetricsByGuid.find(
        bot->GetGUID().GetCounter());
    if (metrics == Cohort().CalibrationMetricsByGuid.end())
        return;

    CalibrationMetrics::DragonwrathCopyProcObservation& observation =
        metrics->second.DragonwrathCopyProcs[originalSpellId];
    observation.OriginalSpellId = originalSpellId;
    observation.CopySpellId = copySpellId;
    observation.CopyCastScopeActive = true;
    observation.CopyLandedDuringActiveCast = false;
}

void BotWorldPopulationMgr::NotifyDragonwrathCopyProcAttempt(
    Unit* caster, uint32 originalSpellId, uint32 castResult, bool accepted)
{
    // This hook is observation-only. The aura handler has already submitted
    // the native copy cast and this method never retries or changes it.
    if (!caster || !originalSpellId)
        return;
    CohortScope scope = ScopeCallbackCohort(caster);
    if (!scope)
        return;
    if (!Cohort().Active || !Cohort().CalibrationActive
        || Cohort().CalibrationMode != "single_target_300"
        || !Cohort().CalibrationScoredStartedMs
        || Cohort().CalibrationWindowComplete)
        return;

    Player* bot = caster->ToPlayer();
    if (!bot || !bot->HasAura(DragonwrathAuraSpellId))
        return;

    uint64 const nowMs = BotWorldPopulationMgrSpellSemantics::NowMs();
    if (nowMs < Cohort().CalibrationScoredStartedMs
        || nowMs - Cohort().CalibrationScoredStartedMs
            >= CalibrationSingleTargetDurationMs)
        return;

    auto metrics = Cohort().CalibrationMetricsByGuid.find(
        bot->GetGUID().GetCounter());
    if (metrics == Cohort().CalibrationMetricsByGuid.end())
        return;

    CalibrationMetrics::DragonwrathCopyProcObservation& observation =
        metrics->second.DragonwrathCopyProcs[originalSpellId];
    observation.OriginalSpellId = originalSpellId;
    ++observation.AttemptCount;
    if (accepted)
        ++observation.AcceptedCount;
    else
        ++observation.RejectedCount;
    observation.LastCastResult = castResult;
    if (observation.CopyCastScopeActive && accepted
        && !observation.CopyLandedDuringActiveCast)
        ++observation.AcceptedWithoutLandedDamageCount;
    observation.CopyCastScopeActive = false;
    observation.CopyLandedDuringActiveCast = false;
}
