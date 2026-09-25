#ifndef TRINITY_BOT_NEFARIAN_FACTS_H
#define TRINITY_BOT_NEFARIAN_FACTS_H

// Observation layer for Nefarian's End (Blackwing Descent). Every identity and
// number here is a native fact: blackwing_descent.h, boss_nefarians_end.cpp,
// the 4.3.4 client DBC rows loaded by this server, TDB 434.22011 rows and the
// SpellMgr corrections. The dossier and ledger cite each value
// (docs/bot_raids/strategies/t11/blackwing_descent/nefarian.md). This layer
// reads the blackboard only; it never moves, casts or targets.

#include "Bots/BotEncounterBlackboard.h"
#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <string_view>
#include <vector>

namespace BotEncounter::Nefarian
{
inline constexpr std::string_view EncounterNodeId = "bwd.nefarian.encounter";

// Creature and gameobject entries (blackwing_descent.h, TDB 434.22011).
constexpr uint32 NefarianEntry = 41376;
constexpr uint32 OnyxiaEntry = 41270;
constexpr uint32 PrototypeEntry = 41948;
constexpr uint32 BoneWarriorEntry = 41918;
constexpr uint32 FlashpointEntry = 42595;
constexpr uint32 ShadowblazeEntry = 42596; // Brushfire Summon 79405 misc value
constexpr uint32 ElevatorEntry = 207834;

// Native spells (10N id first; the difficulty rows come from SpellDifficulty).
constexpr uint32 SpellPhaseTwoHealthAura = 81582;
constexpr uint32 SpellOnyxiaFeignDeath = 29266;
constexpr uint32 SpellBoneFeignDeath = 70628;
constexpr uint32 SpellLightningDischarge = 78090; // 5 s wind-up aura
constexpr uint32 SpellLightningDischargePulse = 77832; // 5 x 1 s pulses
constexpr uint32 SpellShackleUndead = 9484;

inline bool IsBlastNova(uint32 spellId)
{
    return spellId == 80734 || spellId == 101430 || spellId == 101431
        || spellId == 101432;
}

inline bool IsShadowflameBreath(uint32 spellId)
{
    return spellId == 77826 || spellId == 94124 || spellId == 94125
        || spellId == 94126;
}

inline bool IsTailLash(uint32 spellId)
{
    return spellId == 77827 || spellId == 94128 || spellId == 94129
        || spellId == 94130;
}

// Movement impairments that already hold a bone warrior. A controller never
// reapplies over one of these (Shackle Undead 9484 breaks on damage).
inline bool IsBoneWarriorControlAura(uint32 spellId)
{
    switch (spellId)
    {
        case 9484:  // Shackle Undead
        case 853:   // Hammer of Justice
        case 122:   // Frost Nova
        case 82691: // Ring of Frost
        case 3355:  // Freezing Trap
        case 5116:  // Concussive Shot
        case 45524: // Chains of Ice
        case 8056:  // Frost Shock
        case 3600:  // Earthbind
        case 13810: // Ice Trap
        case 18223: // Curse of Exhaustion
        case 24394: // Intimidation
        case 89766: // Axe Toss
            return true;
        default:
            return false;
    }
}

// Platform transport (GO 207834 spawn 235179). The transport is rotated by pi,
// so a local offset (x, y) lies at world (OriginX - x, OriginY - y). Raised and
// lowered origins come from the TDB spawn plus TransportAnimation.dbc stop 0
// (+13.90172); the floor sits 0.46235 below the origin. Pillar tops are the
// native Chromatic Prototype jump destinations; Shadow of Cowardice punishes a
// passenger whose transport offset Z exceeds 9.5 outside phase 2.
struct PlatformFrame
{
    static constexpr float OriginX = -107.213f;
    static constexpr float OriginY = -224.62f;
    static constexpr float Orientation = 3.14159f;
    static constexpr float RaisedOriginZ = 7.03378f;
    static constexpr float LoweredOriginZ = -6.86794f;
    static constexpr float FloorLocalZ = -0.46235f;
    static constexpr float PillarTopLocalZ = 9.925069f;
    static constexpr float CowardiceLocalZ = 9.5f;
    static constexpr float StopTolerance = 0.35f;
};

struct LocalPoint
{
    float X = 0.0f;
    float Y = 0.0f;
};

// ChromaticPrototypeJumpPositions (boss_nefarians_end.cpp).
inline constexpr LocalPoint PillarCenters[3] = {
    { 40.50549f, -0.06254366f },
    { -20.47418f, -34.21686f },
    { -20.44454f, 34.39596f },
};

// Unit combat reach (creature_model_info) plus a 1.5-yard player and the
// native 4/3 yard allowance: Unit::GetMeleeRange.
constexpr float NefarianMeleeReach = 22.83f;
constexpr float OnyxiaMeleeReach = 20.83f;
constexpr float PrototypeMeleeReach = 7.21f;
constexpr float BoneWarriorMeleeReach = 6.58f;

// Cone geometry as this server resolves it: breath has no DBC cone angle and
// gets the 90-degree SpellMgr default; Tail Lash is -82 (rear); Lightning
// Discharge 77833 is CONE_BACK (spell_custom_attr) and 77836 a front cone,
// both 90 degrees and both granting immunity, so its damage lands on the
// flanks. Every radius is 60 yards (SpellRadius 48).
constexpr float BreathHalfAngleDeg = 45.0f;
constexpr float TailLashHalfAngleDeg = 41.0f;
constexpr float DischargeImmuneHalfAngleDeg = 45.0f;
constexpr float DragonConeRadius = 60.0f;
constexpr float ShadowblazeRadius = 4.0f; // Shadowblaze 81007 max radius
constexpr float ChildrenOfDeathwingRange = 50.0f;

enum class ElevatorState : uint8
{
    Unknown,
    Raised,
    Lowered,
    Moving
};

struct ElevatorView
{
    bool Observed = false;
    ObjectGuid Guid;
    float OriginZ = PlatformFrame::RaisedOriginZ;
    ElevatorState State = ElevatorState::Unknown;
};

enum class Phase : uint8
{
    Inactive,
    PreEngage,       // Onyxia still feign-dead or not yet engaged
    OnyxiaOnly,      // Onyxia engaged, Nefarian still airborne
    BothDragons,     // Nefarian landed
    PlatformAscent,  // Onyxia dead: reach the pillar before the floor sinks
    PlatformHold,    // prototypes on the pillars, floor lowered
    PlatformReturn,  // prototypes dead, floor rising: stay on the pillar
    NefarianLanding, // floor raised, Nefarian still airborne: leave pillars
    NefarianGround,  // phase 3
    Done
};

inline std::string_view PhaseName(Phase phase)
{
    switch (phase)
    {
        case Phase::Inactive: return "inactive";
        case Phase::PreEngage: return "pre_engage";
        case Phase::OnyxiaOnly: return "onyxia_only";
        case Phase::BothDragons: return "both_dragons";
        case Phase::PlatformAscent: return "platform_ascent";
        case Phase::PlatformHold: return "platform_hold";
        case Phase::PlatformReturn: return "platform_return";
        case Phase::NefarianLanding: return "nefarian_landing";
        case Phase::NefarianGround: return "nefarian_ground";
        case Phase::Done: return "done";
    }
    return "unknown";
}

inline bool PhaseWantsPillar(Phase phase)
{
    return phase == Phase::PlatformAscent || phase == Phase::PlatformHold
        || phase == Phase::PlatformReturn;
}

inline bool HasAnyAura(ActorSnapshot const& actor,
    std::initializer_list<uint32> spells)
{
    return std::any_of(actor.Auras.begin(), actor.Auras.end(),
        [spells](AuraSnapshot const& aura)
        {
            return std::find(spells.begin(), spells.end(), aura.SpellId)
                != spells.end();
        });
}

inline bool HasAura(ActorSnapshot const& actor, uint32 spellId)
{
    return HasAnyAura(actor, { spellId });
}

// A bone warrior that can move and attack. Collapsed warriors carry the
// permanent feign death and are not selectable (spell_nefarians_end_animate_bones_dummy).
inline bool IsActiveBoneWarrior(ActorSnapshot const& actor)
{
    return actor.Entry == BoneWarriorEntry && actor.Alive && actor.Selectable
        && !HasAura(actor, SpellBoneFeignDeath);
}

// Stunned, rooted or shackled: the warrior cannot chase anyone.
inline bool IsBoneWarriorHeld(ActorSnapshot const& actor)
{
    return HasAnyAura(actor, { 9484, 853, 122, 82691, 3355, 24394, 89766 });
}

inline bool IsBoneWarriorControlled(ActorSnapshot const& actor)
{
    return std::any_of(actor.Auras.begin(), actor.Auras.end(),
        [](AuraSnapshot const& aura)
        {
            return IsBoneWarriorControlAura(aura.SpellId);
        });
}

struct EncounterView
{
    ActorSnapshot const* Nefarian = nullptr;
    ActorSnapshot const* Onyxia = nullptr;
    std::vector<ActorSnapshot const*> Prototypes;   // alive
    std::vector<ActorSnapshot const*> BoneWarriors; // alive, active or collapsed
    std::vector<ActorSnapshot const*> Fires;        // flashpoints and Shadowblaze
    ElevatorView Elevator;
    Phase CurrentPhase = Phase::Inactive;

    bool Owns() const
    {
        return CurrentPhase != Phase::Inactive && CurrentPhase != Phase::Done;
    }

    bool OnyxiaAlive() const { return Onyxia && Onyxia->Alive; }

    bool NefarianLanded() const
    {
        return Nefarian && Nefarian->Alive && !Nefarian->Flying
            && Nefarian->Attackable;
    }

    bool OnyxiaDischarging() const
    {
        return OnyxiaAlive() && HasAnyAura(*Onyxia,
            { SpellLightningDischarge, SpellLightningDischargePulse });
    }
};

inline ElevatorState ClassifyElevator(float originZ)
{
    if (std::fabs(originZ - PlatformFrame::RaisedOriginZ)
        <= PlatformFrame::StopTolerance)
        return ElevatorState::Raised;
    if (std::fabs(originZ - PlatformFrame::LoweredOriginZ)
        <= PlatformFrame::StopTolerance)
        return ElevatorState::Lowered;
    return ElevatorState::Moving;
}

// Summoned dragons, prototypes, warriors and fires publish as Summons; an
// immune or feign-dead actor can also publish as an Interactable. Prefer a
// living match so a despawning corpse never hides the live actor.
inline ActorSnapshot const* FindEncounterActor(Blackboard const& board,
    uint32 entry)
{
    ActorSnapshot const* corpse = nullptr;
    for (auto const* list : { &board.Hostiles, &board.Summons,
            &board.Interactables })
        for (ActorSnapshot const& actor : *list)
        {
            if (actor.Entry != entry || actor.Kind == ActorKind::Player)
                continue;
            if (actor.Alive)
                return &actor;
            if (!corpse)
                corpse = &actor;
        }
    return corpse;
}

inline void CollectAlive(Blackboard const& board, uint32 entry,
    std::vector<ActorSnapshot const*>& out)
{
    for (auto const* list : { &board.Hostiles, &board.Summons,
            &board.Interactables })
        for (ActorSnapshot const& actor : *list)
            if (actor.Entry == entry && actor.Alive
                && std::none_of(out.begin(), out.end(),
                    [&actor](ActorSnapshot const* seen)
                    {
                        return seen->Guid == actor.Guid;
                    }))
                out.push_back(&actor);
    std::sort(out.begin(), out.end(), [](auto left, auto right)
    {
        return left->Guid.GetRawValue() < right->Guid.GetRawValue();
    });
}

inline Phase ClassifyPhase(EncounterView const& view)
{
    if (!view.Nefarian && !view.Onyxia)
        return Phase::Inactive;
    if (view.Nefarian && !view.Nefarian->Alive)
        return Phase::Done;
    if (view.OnyxiaAlive())
    {
        bool const engaged = view.Onyxia->InCombat
            && !HasAura(*view.Onyxia, SpellOnyxiaFeignDeath);
        if (!engaged)
            return Phase::PreEngage;
        return view.NefarianLanded() ? Phase::BothDragons : Phase::OnyxiaOnly;
    }
    if (!view.Nefarian)
        return Phase::Inactive;

    bool const phaseTwoAura = HasAura(*view.Nefarian, SpellPhaseTwoHealthAura);
    bool const onyxiaCorpse = view.Onyxia != nullptr; // despawns 19 s after death
    bool const prototypeAlive = !view.Prototypes.empty();
    bool const prototypeEngaged = std::any_of(view.Prototypes.begin(),
        view.Prototypes.end(), [](ActorSnapshot const* prototype)
        {
            return prototype->InCombat;
        });
    ElevatorState const elevator = view.Elevator.State;
    bool const raised = elevator == ElevatorState::Raised
        || elevator == ElevatorState::Unknown;

    // Onyxia's corpse spans the gap between her death and the lift-off aura,
    // and the 400 ms before the prototypes spawn. It is gone (19 s despawn)
    // long before phase 3 can raise the floor again.
    if (onyxiaCorpse && (!phaseTwoAura || raised || !prototypeEngaged))
        return Phase::PlatformAscent;
    if (phaseTwoAura && (prototypeEngaged || (prototypeAlive && !raised)))
        return elevator == ElevatorState::Lowered ? Phase::PlatformHold
            : Phase::PlatformAscent;
    if (phaseTwoAura && !raised)
        return Phase::PlatformReturn;
    if (view.Nefarian->Flying || phaseTwoAura)
        return Phase::NefarianLanding;
    return Phase::NefarianGround;
}

inline EncounterView ObserveEncounter(Blackboard const& board)
{
    EncounterView view;
    if (board.Route.NodeId != EncounterNodeId)
        return view;
    view.Nefarian = FindEncounterActor(board, NefarianEntry);
    view.Onyxia = FindEncounterActor(board, OnyxiaEntry);
    CollectAlive(board, PrototypeEntry, view.Prototypes);
    CollectAlive(board, BoneWarriorEntry, view.BoneWarriors);
    CollectAlive(board, FlashpointEntry, view.Fires);
    CollectAlive(board, ShadowblazeEntry, view.Fires);
    for (ActorSnapshot const& object : board.Interactables)
        if (object.Entry == ElevatorEntry)
        {
            view.Elevator.Observed = true;
            view.Elevator.Guid = object.Guid;
            view.Elevator.OriginZ = object.Position.Z;
            view.Elevator.State = ClassifyElevator(object.Position.Z);
            break;
        }
    view.CurrentPhase = ClassifyPhase(view);
    return view;
}
}

#endif
