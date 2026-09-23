#ifndef TRINITY_BOT_MAGMAW_OBSERVATIONS_H
#define TRINITY_BOT_MAGMAW_OBSERVATIONS_H

#include "Bots/BotEncounterBlackboard.h"

namespace BotEncounter
{
struct MagmawActorObservation
{
    ActorSnapshot const* Boss = nullptr;
    ActorSnapshot const* Head = nullptr;
    ActorSnapshot const* NearestParasite = nullptr;
    float NearestParasiteDistance = 0.0f;
    ActorSnapshot const* SupportParasite = nullptr;
    float SupportParasiteDistance = 0.0f;
    bool SupportOpportunitiesObserved = false;
    bool BossStaticDamageOpportunity = false;
    ActorSnapshot const* PersonalParasiteThreat = nullptr;
    float PersonalParasiteThreatDistance = 0.0f;
    // The same native static damage observation as SupportParasite: the
    // threat is a valid attack target in map line of sight and inside one of
    // the actor's profile damage ranges. False when no opportunity view was
    // supplied; SupportOpportunitiesObserved distinguishes that case.
    bool PersonalParasiteThreatStaticDamageOpportunity = false;
};

struct MagmawHazardObservation
{
    ActorSnapshot const* Pillar = nullptr;
    ActorSnapshot const* Crash = nullptr;
    float CrashDistance = 0.0f;
    ActorSnapshot const* NearestImmediateHazard = nullptr;
    float NearestImmediateHazardDistance = 0.0f;
};

struct MagmawHookAssignment
{
    bool Assigned = false;
    ActorSnapshot const* Vehicle = nullptr;
    ActorSnapshot const* Spike = nullptr;
};
}

#endif
