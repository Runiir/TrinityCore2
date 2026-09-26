#ifndef TRINITY_BOT_NEFARIAN_ASCENT_INTENT_H
#define TRINITY_BOT_NEFARIAN_ASCENT_INTENT_H

// The phase 2 ascent step (BotNefarianAscent.h) as the native request package
// T's swimmer stages execute (BotNativeAction::TransportSurfaceMove Float,
// Swim, Hop, Emerge; BotWorldPopulationMgrNativePathTransportLiquid.cpp).
// Survival priority: every second in the magma costs 5000 + 250 per stack.

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianAscent.h"

namespace BotEncounter::Nefarian
{
inline BotNativeAction::TransportSurfaceMove::Stage NativeAscentStage(AscentStage stage)
{
    using Stage = BotNativeAction::TransportSurfaceMove::Stage;
    switch (stage)
    {
        case AscentStage::Float: return Stage::Float;
        case AscentStage::Swim: return Stage::Swim;
        case AscentStage::Hop: return Stage::Hop;
        case AscentStage::Board: return Stage::Emerge;
    }
    return Stage::Float;
}

inline BotNativeAction::Candidate AscentCandidate(AscentStep const& step,
    Blackboard const& board, ObjectGuid bot)
{
    BotNativeAction::TransportSurfaceMove move;
    move.Transport = step.Transport;
    move.Kind = NativeAscentStage(step.Stage);
    move.X = step.World.X;
    move.Y = step.World.Y;
    move.Z = step.World.Z;
    move.EndOnTransport = true;
    move.FloorToleranceYards = step.FloorToleranceYards;
    move.FloatDepthYards = step.FloatDepthYards;
    move.SwimSpeedYardsPerSecond = step.SwimSpeedYardsPerSecond;

    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = board.CurrentScope.Key();
    candidate.Id.Strategy = "adaptive_nefarian";
    candidate.Id.Mechanic = std::string(AscentStageName(step.Stage));
    candidate.Id.Actor = bot;
    candidate.Id.EventGeneration = uint64(step.Stage) + 1;
    candidate.ActionPriority = BotActionArbitration::Priority::Survival;
    candidate.Utility = 460.0f;
    candidate.ExpiresAtMs = board.ObservedAtMs + 1000;
    candidate.Action = move;
    return candidate;
}
}

#endif
