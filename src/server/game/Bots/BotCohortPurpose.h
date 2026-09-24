#ifndef TRINITY_BOT_COHORT_PURPOSE_H
#define TRINITY_BOT_COHORT_PURPOSE_H

#include "Define.h"

// Why a cohort exists. Validation cohorts are the exact all-bot tuning and
// acceptance runs. Play cohorts share their raid with human (external)
// members, are never certifying, and must never reach scored evidence
// (docs/bot_raids/human_play_mode.md). Every play-only behaviour is gated on
// Play, so a Validation cohort keeps its legacy code paths unchanged.
enum class CohortPurpose : uint8
{
    Validation = 0,
    Play = 1
};

inline char const* CohortPurposeName(CohortPurpose purpose)
{
    return purpose == CohortPurpose::Play ? "play" : "validation";
}

#endif
