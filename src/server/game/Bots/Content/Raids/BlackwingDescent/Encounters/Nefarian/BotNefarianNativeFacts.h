#ifndef TRINITY_BOT_NEFARIAN_NATIVE_FACTS_H
#define TRINITY_BOT_NEFARIAN_NATIVE_FACTS_H

// Native facts the shared blackboard does not carry yet: cast progress of the
// Chromatic Prototypes and each bot's transport placement. The dispatch fills
// them from the live objects (BotNefarianNativeObserver.h) once per decision;
// without them the strategy falls back to blackboard-only rules. Observation
// only: nothing here changes a cast, a passenger or a position.

#include "Bots/BotEncounterBlackboard.h"
#include <algorithm>
#include <vector>

namespace BotEncounter::Nefarian
{
struct CastProgress
{
    ObjectGuid Caster;
    uint32 SpellId = 0;
    int32 CastTimeMs = 0;
    int32 RemainingMs = 0;

    int32 ElapsedMs() const { return std::max(0, CastTimeMs - RemainingMs); }
};

struct TransportPlacement
{
    ObjectGuid Actor;
    ObjectGuid Transport;
    uint32 TransportEntry = 0;
    Vector3 Offset; // transport-local position (GetTransOffsetX/Y/Z)
};

struct NativeFacts
{
    std::vector<CastProgress> Casts;
    std::vector<TransportPlacement> Placements;
    // Whether the movement layer can take a bot from the floor onto a pillar
    // top (package T: not supported; it can neither swim nor climb). Without
    // it phase 2 holds each team at its pillar's foot.
    bool PillarAscentSupported = false;

    CastProgress const* FindCast(ObjectGuid caster) const
    {
        auto itr = std::find_if(Casts.begin(), Casts.end(),
            [caster](CastProgress const& cast) { return cast.Caster == caster; });
        return itr == Casts.end() ? nullptr : &*itr;
    }

    TransportPlacement const* FindPlacement(ObjectGuid actor) const
    {
        auto itr = std::find_if(Placements.begin(), Placements.end(),
            [actor](TransportPlacement const& placement)
            {
                return placement.Actor == actor;
            });
        return itr == Placements.end() ? nullptr : &*itr;
    }
};
}

#endif
