#ifndef TRINITY_BOT_NEFARIAN_NATIVE_FACTS_H
#define TRINITY_BOT_NEFARIAN_NATIVE_FACTS_H

// Native facts the shared blackboard does not carry yet: cast progress of the
// Chromatic Prototypes, each bot's transport placement, its running spline
// and the readiness of its interrupt and control spells. The dispatch fills
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

// Whether the bot knows a duty spell (Player::HasSpell, through
// BotSpellResolution) and whether it is ready now (SpellHistory::IsReady); a
// spell the bot lacks is recorded as unknown and not ready.
struct SpellReadiness
{
    ObjectGuid Actor;
    uint32 SpellId = 0;
    bool Ready = true;
    bool Known = true;
};

// The bot's own movement: whether a spline is running and where it ends
// (world frame), so the same leg is not re-submitted while in flight.
struct MovementState
{
    ObjectGuid Actor;
    bool Moving = false;
    Vector3 Destination;
};

// The single runtime answer to "can the movement layer lift a bot from the
// floor onto a pillar top?". Package T's transport-surface movement can
// neither swim nor climb, so it is false. Every plan (NativeFacts below) and
// the nefarian_duty_plan status read this one function, so they agree; flip
// it (or make it query T's executor) when a lawful ascent exists.
inline bool RuntimePillarAscentSupported()
{
    return false;
}

struct NativeFacts
{
    std::vector<CastProgress> Casts;
    std::vector<TransportPlacement> Placements;
    // Whether the movement layer can take a bot from the floor onto a pillar
    // top. Without it phase 2 holds each team at its pillar's foot.
    bool PillarAscentSupported = RuntimePillarAscentSupported();
    std::vector<SpellReadiness> Readiness;
    std::vector<MovementState> Motion;

    // A spell without an entry counts as known and ready: native submission
    // stays the judge.
    bool SpellKnown(ObjectGuid actor, uint32 spellId) const
    {
        for (SpellReadiness const& entry : Readiness)
            if (entry.Actor == actor && entry.SpellId == spellId)
                return entry.Known;
        return true;
    }

    bool SpellReady(ObjectGuid actor, uint32 spellId) const
    {
        for (SpellReadiness const& entry : Readiness)
            if (entry.Actor == actor && entry.SpellId == spellId)
                return entry.Ready;
        return true;
    }

    // What every duty asks before naming a spell: known and ready.
    bool SpellUsable(ObjectGuid actor, uint32 spellId) const
    {
        return SpellKnown(actor, spellId) && SpellReady(actor, spellId);
    }

    MovementState const* FindMotion(ObjectGuid actor) const
    {
        auto itr = std::find_if(Motion.begin(), Motion.end(),
            [actor](MovementState const& state) { return state.Actor == actor; });
        return itr == Motion.end() ? nullptr : &*itr;
    }

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
