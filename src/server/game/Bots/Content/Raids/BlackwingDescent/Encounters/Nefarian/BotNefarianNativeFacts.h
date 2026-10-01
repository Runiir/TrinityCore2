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
#include <array>
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
// BotSpellResolution), whether it is ready now (SpellHistory::IsReady) and
// whether the bot can pay its power cost now (SpellInfo::CalcPowerCost against
// its current power); a spell the bot lacks is recorded as unknown and not
// ready.
struct SpellReadiness
{
    ObjectGuid Actor;
    uint32 SpellId = 0;
    bool Ready = true;
    bool Known = true;
    bool Affordable = true;
};

// The bot's own movement: whether a spline is running and where it ends
// (world frame), so the same leg is not re-submitted while in flight.
struct MovementState
{
    ObjectGuid Actor;
    bool Moving = false;
    Vector3 Destination;
};

// A native fall in progress (the falling movement flags or a running fall
// spline) and a finished fall whose landing is not reported yet
// (BotValidationRouteBoardingAction::NativeFallInProgress/LandingPending).
struct FallState
{
    ObjectGuid Actor;
    bool Falling = false;
    bool LandingPending = false;
};

// The single runtime answer to "can the movement layer take a bot from the
// floor onto a pillar top?": yes, by the swim-and-hop ascent (Float, Swim,
// Hop, Emerge; package T's swimmer stages). Every plan (NativeFacts below)
// and the nefarian_duty_plan status read this one function, so they agree.
inline bool RuntimePillarAscentSupported()
{
    return true;
}

// The Onyxia tank's pickup across decisions (round 7 review): kept by the
// native observer (BotNefarianNativeObserver.h) per tank and Onyxia GUID, so
// neither a new decision nor a moving victim resets it.
struct PickupState
{
    ObjectGuid Tank;
    ObjectGuid Onyxia;         // the dragon being picked up
    uint32 DragonEntry = 0;    // its entry (Onyxia 41270, Nefarian 41376)
    uint64 ElapsedMs = 0;      // since the pickup began (Onyxia on another)
    uint32 Rejections = 0;     // spots the native line of sight rejected
    std::vector<Vector3> RejectedSpots;
    bool Exhausted = false;    // budget spent: nefarian_pickup_exhausted
};

struct NativeFacts
{
    std::vector<CastProgress> Casts;
    std::vector<TransportPlacement> Placements;
    // Whether the movement layer can take a bot from the floor onto a pillar
    // top. Without it phase 2 holds each team at its pillar's foot.
    bool PillarAscentSupported = RuntimePillarAscentSupported();
    std::vector<SpellReadiness> Readiness;
    std::vector<MovementState> Motion;
    std::vector<FallState> Falls;
    // The instance's difficulty (Map::IsHeroic): heroic keeps the phase 1
    // Electrocute pacing (BotNefarianTactics.h PhaseOnePacingFor).
    bool Heroic = false;
    // Raid members the observing bot has no line of sight to
    // (WorldObject::IsWithinLOSInMap), for its heals.
    std::vector<ObjectGuid> OutOfSight;

    bool InSight(ObjectGuid actor) const
    {
        return std::find(OutOfSight.begin(), OutOfSight.end(), actor) == OutOfSight.end();
    }

    FallState const* FindFall(ObjectGuid actor) const
    {
        auto itr = std::find_if(Falls.begin(), Falls.end(),
            [actor](FallState const& state) { return state.Actor == actor; });
        return itr == Falls.end() ? nullptr : &*itr;
    }

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

    // Whether the bot can pay the spell's power cost now. A spell without an
    // entry counts as affordable: native submission stays the judge.
    bool SpellAffordable(ObjectGuid actor, uint32 spellId) const
    {
        for (SpellReadiness const& entry : Readiness)
            if (entry.Actor == actor && entry.SpellId == spellId)
                return entry.Affordable;
        return true;
    }

    std::vector<PickupState> Pickups;
    // When each pillar's prototype was first seen dead in phase 2 (0: alive
    // or unknown), kept by the observer per attempt (PillarKillMemory): the
    // first finisher sends the cross-pillar help, and keeps that duty.
    std::array<uint64, 3> PillarKillMs{ 0, 0, 0 };
    // Feral tanks without the Glyph of Frenzied Regeneration (spell 54810):
    // their Frenzied Regeneration converts rage into health, so Enrage feeds
    // it. The canonical Feral carries the glyph (+30% healing received, no
    // rage conversion); a Feral not listed here is taken to carry it.
    std::vector<ObjectGuid> UnglyphedFrenziedRegeneration;

    bool FrenziedRegenerationGlyphed(ObjectGuid actor) const
    {
        return std::find(UnglyphedFrenziedRegeneration.begin(),
            UnglyphedFrenziedRegeneration.end(), actor) == UnglyphedFrenziedRegeneration.end();
    }

    PickupState const* FindPickup(ObjectGuid tank, ObjectGuid onyxia) const
    {
        for (PickupState const& pickup : Pickups)
            if (pickup.Tank == tank && pickup.Onyxia == onyxia)
                return &pickup;
        return nullptr;
    }

    bool PickupExhausted(ObjectGuid tank, ObjectGuid onyxia) const
    {
        PickupState const* pickup = FindPickup(tank, onyxia);
        return pickup && pickup->Exhausted;
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
