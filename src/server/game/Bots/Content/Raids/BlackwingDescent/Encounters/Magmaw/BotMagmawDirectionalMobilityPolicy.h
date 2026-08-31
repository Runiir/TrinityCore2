#ifndef TRINITY_BOT_MAGMAW_DIRECTIONAL_MOBILITY_POLICY_H
#define TRINITY_BOT_MAGMAW_DIRECTIONAL_MOBILITY_POLICY_H

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawParasitePolicy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMobilityReservation.h"

#include <cmath>
#include <optional>

namespace BotEncounter
{
struct MagmawDirectionalMobilityInput
{
    uint32 SpellId = 0;
    uint32 NativeReuseCooldownMs = 0;
};

inline std::optional<BotNativeAction::Candidate>
ProposeMagmawDirectionalMobility(Blackboard const& board,
    ActorSnapshot const& bot, ActorSnapshot const& boss,
    BotNativeAction::Candidate const& pointMovement,
    MagmawDirectionalMobilityInput const& input,
    MagmawParasiteRouteFacts const& routeFacts)
{
    constexpr uint32 MassiveCrashSpell = 88253;
    constexpr uint32 BlinkSpell = 1953;
    constexpr uint32 DisengageSpell = 781;
    constexpr float BlinkTravelDistance = 20.0f;
    constexpr float DisengageTravelDistance = 13.0f;

    BotNativeAction::Move const* point =
        std::get_if<BotNativeAction::Move>(&pointMovement.Action);
    bool const fireMage = bot.ClassSpec == "fire_mage"
        && input.SpellId == BlinkSpell;
    bool const marksHunter = bot.ClassSpec == "marksmanship_hunter"
        && input.SpellId == DisengageSpell;
    if (!point || (!fireMage && !marksHunter)
        || !input.NativeReuseCooldownMs)
        return std::nullopt;

    // These spells travel a fixed distance.  Do not use one for a nearer
    // waypoint: overshooting it can leave route progress unobserved and make
    // the next tick request movement back toward the same point.
    float const pointDistance = std::hypot(point->X - bot.Position.X,
        point->Y - bot.Position.Y);
    float const travelDistance = fireMage
        ? BlinkTravelDistance : DisengageTravelDistance;
    if (pointDistance < travelDistance)
        return std::nullopt;

    MagmawMobilityDecision const decision = EvaluateMagmawMobilityReservation(
        boss.FindMechanicTimer(MassiveCrashSpell),
        input.NativeReuseCooldownMs, routeFacts.EmergencyClearance);
    if (decision != MagmawMobilityDecision::AllowRoutine
        && decision != MagmawMobilityDecision::AllowEmergency)
        return std::nullopt;

    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = board.CurrentScope.Key();
    candidate.Id.Strategy = "adaptive_magmaw";
    candidate.Id.Mechanic = "parasite_directional_mobility";
    candidate.Id.Actor = bot.Guid;
    candidate.Id.EventGeneration = pointMovement.Id.EventGeneration;
    candidate.ActionPriority = pointMovement.ActionPriority;
    candidate.Utility = pointMovement.Utility + 5.0f;
    candidate.ExpiresAtMs = pointMovement.ExpiresAtMs;
    candidate.Action = BotNativeAction::DirectionalMobility{
        point->X, point->Y, point->Z, input.SpellId,
        fireMage ? BotNativeAction::DirectionalMobilityFacing::Forward
                 : BotNativeAction::DirectionalMobilityFacing::Backward,
        "parasite_directional_mobility" };
    return candidate;
}
}

#endif
