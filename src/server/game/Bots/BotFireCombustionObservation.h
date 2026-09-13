#ifndef BOT_FIRE_COMBUSTION_OBSERVATION_H
#define BOT_FIRE_COMBUSTION_OBSERVATION_H

#include "Define.h"
#include <array>
#include <string>
#include <vector>

class Player;
class Unit;

namespace BotFireCombustionObservation
{
struct Component
{
    uint32 SpellId, EffectIndex;
    int32 Amount, Contribution;
};
struct AuraState
{
    bool Present = false;
    int32 RemainingMs = 0;
};
struct Snapshot
{
    uint64 EvaluationStartedAtMs = 0, ObservedAtMs = 0;
    uint32 ActorGuid = 0, TargetGuid = 0, TargetEntry = 0, Race = 0;
    bool ActorAvailable = false, TargetAvailable = false;
    bool CombustionAvailable = false, PeriodicAvailable = false;
    bool IgnitePresent = false, IgniteEffect0Present = false;
    int32 IgniteAmount = 0;
    bool LivingBomb = false, Pyro92315 = false, Pyro11366 = false;
    std::array<AuraState, 4> Buffs{}; // 2825, 32182, 80353, 26297
    bool BerserkingKnown = false;
    bool RawScalingAvailable = false;
    float ScalingPercent = 0;
    uint32 EligibleComponentCount = 0;
    int64 SummedBasePoints = 0;
    std::vector<Component> Components;
    int32 PeriodicEffectIndex = -1, DurationMs = 0, PeriodMs = 0;
    float HasteMod = 0, FireCritPct = 0, TargetSpellCritPct = 0, TargetAllCritPct = 0;
    float SpellCritMultiplier = 0, FireCritDamageMultiplier = 0;
    int32 HastedPeriodMs = 0, TickCount = 0;
    bool EstimateAvailable = false;
    double EstimatedTotal = 0;
};
Snapshot Capture(Player const* actor, Unit const* target, uint64 evaluationStartedAtMs, uint64 observedAtMs);
std::string ToJson(Snapshot const& snapshot);
}
#endif
