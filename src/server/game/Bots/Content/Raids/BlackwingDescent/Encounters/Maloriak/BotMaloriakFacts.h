#ifndef TRINITY_BOT_MALORIAK_FACTS_H
#define TRINITY_BOT_MALORIAK_FACTS_H

#include "Bots/BotEncounterBlackboard.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <optional>
#include <string_view>
#include <vector>

// Observable Maloriak facts for the adaptive strategy. Every value comes from
// the cohort blackboard (visible units, auras, casts, native mechanic
// timers); nothing here reads or changes server state. Identifiers are the
// native script's (boss_maloriak_shared.h, blackwing_descent.h) and the
// 4.4.2 client spell rows recorded in maloriak_ledger_v1.json.
namespace BotEncounter::Maloriak
{
constexpr std::string_view EncounterNode = "bwd.maloriak.encounter";
constexpr std::string_view StrategyName = "adaptive_maloriak";

constexpr uint32 BossEntry = 41378;
constexpr uint32 AberrationEntry = 41440;
constexpr uint32 PrimeSubjectEntry = 41841;
constexpr uint32 FlashFreezeEntry = 41576;
constexpr uint32 AbsoluteZeroEntry = 41961;
constexpr uint32 MagmaJetFireEntry = 41901;
constexpr uint32 VileSwillEntry = 49811;

constexpr uint32 ArcaneStormSpell = 77896;
constexpr uint32 RemedySpell = 77912;
constexpr uint32 ReleaseAberrationsSpell = 77569;
constexpr uint32 ReleaseAllMinionsSpell = 77991;
constexpr uint32 FireImbuedSpell = 78896;
constexpr uint32 FrostImbuedSpell = 78895;
constexpr uint32 ShadowImbuedSpell = 92716;
constexpr uint32 SlimeImbuedSpell = 92917;
constexpr uint32 DrinkAllBottlesSpell = 95662;
constexpr uint32 UnstableMixSpell = 95663;
constexpr uint32 DebilitatingSlimeSpell = 77615;
constexpr uint32 BitingChillSpell = 77760;
constexpr uint32 MagmaJetsCastSpell = 78194;
constexpr uint32 ThrowGreenBottleSpell = 77937;
// Client-difficulty variants of the player debuffs (10N, 25N, 10H, 25H).
constexpr std::array<uint32, 4> ConsumingFlamesSpells{ 77786, 92971, 92972, 92973 };
constexpr std::array<uint32, 4> FlashFreezeStunSpells{ 77699, 92978, 92979, 92980 };

// Mechanic spells whose native schedule boss_maloriak.cpp publishes through
// UnitAI::GetTimeUntilEncounterMechanic (0 while casting, the next cauldron
// visit for the vial throw spells and the heroic Black drink).
constexpr std::array<uint32, 15> PublishedMechanicSpells{
    ArcaneStormSpell, ReleaseAberrationsSpell, RemedySpell,
    77679 /*Scorching Blast*/, 77786 /*Consuming Flames*/, BitingChillSpell,
    97693 /*Flash Freeze*/, 92754 /*Engulfing Darkness*/,
    93022 /*Magma Jets*/, 78225 /*Acid Nova*/, 78223 /*Absolute Zero*/,
    77925 /*Throw Red Bottle*/, 77932 /*Throw Blue Bottle*/,
    ThrowGreenBottleSpell, 92828 /*Drink Black Bottle*/ };

// Client SpellDuration rows: Arcane Storm channels 6 s, Remedy lasts 10 s.
constexpr uint32 ArcaneStormChannelMs = 6000;
constexpr uint32 RemedyDurationMs = 10000;
// Native DamageTaken: phase two starts on the hit that crosses 25%.
constexpr float PhaseTwoHealthPct = 25.0f;

enum class Phase : uint8
{
    Prepull,
    Transition,
    Red,
    Blue,
    Green,
    Black,
    PhaseTwo
};

inline std::string_view PhaseName(Phase phase)
{
    switch (phase)
    {
        case Phase::Prepull: return "prepull";
        case Phase::Transition: return "transition";
        case Phase::Red: return "red";
        case Phase::Blue: return "blue";
        case Phase::Green: return "green";
        case Phase::Black: return "black";
        case Phase::PhaseTwo: return "phase_two";
    }
    return "unknown";
}

// Creatures the Maloriak encounter owner may target; the route observer
// attributes native engagement only through these entries.
inline bool IsDeclaredEncounterEntry(uint32 entry)
{
    return entry == BossEntry || entry == AberrationEntry
        || entry == PrimeSubjectEntry || entry == FlashFreezeEntry
        || entry == VileSwillEntry;
}

inline AuraSnapshot const* FindAura(ActorSnapshot const& actor, uint32 spellId)
{
    auto itr = std::find_if(actor.Auras.begin(), actor.Auras.end(),
        [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
    return itr == actor.Auras.end() ? nullptr : &*itr;
}

inline bool HasAura(ActorSnapshot const& actor, uint32 spellId)
{
    return FindAura(actor, spellId) != nullptr;
}

template <std::size_t N>
inline bool HasAnyAura(ActorSnapshot const& actor,
    std::array<uint32, N> const& spells)
{
    return std::any_of(spells.begin(), spells.end(),
        [&actor](uint32 spellId) { return HasAura(actor, spellId); });
}

inline float Distance2d(Vector3 const& left, Vector3 const& right)
{
    float const dx = left.X - right.X;
    float const dy = left.Y - right.Y;
    return std::sqrt(dx * dx + dy * dy);
}

inline bool IsFrozen(ActorSnapshot const& actor)
{
    return HasAnyAura(actor, FlashFreezeStunSpells);
}

// Elapsed part of a self aura with a known full duration; nullopt when the
// aura is absent or carries no expiry.
inline std::optional<uint32> ElapsedAuraMs(ActorSnapshot const& actor,
    uint32 spellId, uint32 durationMs, uint64 observedAtMs)
{
    AuraSnapshot const* aura = FindAura(actor, spellId);
    if (!aura || !aura->ExpiresAtMs)
        return std::nullopt;
    uint64 const remaining = aura->ExpiresAtMs > observedAtMs
        ? aura->ExpiresAtMs - observedAtMs : 0;
    return remaining >= durationMs ? 0u : uint32(durationMs - remaining);
}

struct Observation
{
    ActorSnapshot const* Boss = nullptr;
    Phase CurrentPhase = Phase::Prepull;
    bool Engaged = false;
    // Debilitating Slime (Green): +100% damage taken for 15 s on everyone.
    bool SlimeWindow = false;
    bool ArcaneStormInterruptible = false;
    // 0 during the 0.5 s cast, then the elapsed part of the 6 s channel.
    uint32 ArcaneStormElapsedMs = 0;
    bool ReleaseInterruptible = false;
    bool MagmaJetsCasting = false;
    std::optional<uint32> RemedyElapsedMs;
    // Released (selectable) Aberrations; Attackable filters landed ones.
    std::vector<ActorSnapshot const*> ActiveAberrations;
    // Chamber creatures not yet released (sleeping, not selectable).
    uint32 ReserveAberrations = 0;
    std::vector<ActorSnapshot const*> PrimeSubjects;
    std::vector<ActorSnapshot const*> FlashFreezeBlocks;
    std::vector<ActorSnapshot const*> AbsoluteZeros;
    std::vector<ActorSnapshot const*> MagmaJetFires;
    std::vector<ActorSnapshot const*> VileSwills;
    // Native schedule, when the blackboard publishes it (optional).
    std::optional<uint32> NextGreenVialMs;

    std::size_t AttackableAberrationCount() const
    {
        return std::size_t(std::count_if(ActiveAberrations.begin(),
            ActiveAberrations.end(), [](ActorSnapshot const* actor)
            {
                return actor->Attackable;
            }));
    }
};

inline ActorSnapshot const* FindBoss(Blackboard const& board)
{
    for (std::vector<ActorSnapshot> const* actors : { &board.Hostiles, &board.Summons })
        for (ActorSnapshot const& actor : *actors)
            if (actor.Alive && actor.Entry == BossEntry)
                return &actor;
    return nullptr;
}

inline bool IsEngaged(Blackboard const& board, ActorSnapshot const& boss)
{
    return boss.InCombat || board.NativeBossState == "in_progress";
}

inline Phase ClassifyPhase(Blackboard const& board, ActorSnapshot const& boss)
{
    if (!IsEngaged(board, boss))
        return Phase::Prepull;
    bool const castingTransition = boss.Cast
        && (boss.Cast->SpellId == ReleaseAllMinionsSpell
            || boss.Cast->SpellId == DrinkAllBottlesSpell);
    if (boss.HealthPct <= PhaseTwoHealthPct
        || HasAura(boss, UnstableMixSpell) || castingTransition)
        return Phase::PhaseTwo;
    if (HasAura(boss, FireImbuedSpell))
        return Phase::Red;
    if (HasAura(boss, FrostImbuedSpell))
        return Phase::Blue;
    if (HasAura(boss, SlimeImbuedSpell))
        return Phase::Green;
    if (HasAura(boss, ShadowImbuedSpell))
        return Phase::Black;
    return Phase::Transition;
}

inline Observation Observe(Blackboard const& board)
{
    Observation observation;
    observation.Boss = FindBoss(board);
    if (!observation.Boss)
        return observation;
    ActorSnapshot const& boss = *observation.Boss;
    observation.CurrentPhase = ClassifyPhase(board, boss);
    observation.Engaged = IsEngaged(board, boss);

    if (boss.Cast && boss.Cast->Interruptible)
    {
        if (boss.Cast->SpellId == ArcaneStormSpell)
        {
            observation.ArcaneStormInterruptible = true;
            observation.ArcaneStormElapsedMs = ElapsedAuraMs(boss,
                ArcaneStormSpell, ArcaneStormChannelMs, board.ObservedAtMs)
                .value_or(0);
        }
        else if (boss.Cast->SpellId == ReleaseAberrationsSpell)
            observation.ReleaseInterruptible = true;
    }
    observation.MagmaJetsCasting = boss.Cast
        && boss.Cast->SpellId == MagmaJetsCastSpell;
    observation.RemedyElapsedMs = ElapsedAuraMs(boss, RemedySpell,
        RemedyDurationMs, board.ObservedAtMs);
    observation.SlimeWindow = HasAura(boss, DebilitatingSlimeSpell);

    for (std::vector<ActorSnapshot> const* actors : { &board.Hostiles, &board.Summons })
        for (ActorSnapshot const& actor : *actors)
        {
            if (!actor.Alive)
                continue;
            switch (actor.Entry)
            {
                case AberrationEntry:
                    if (actor.Selectable)
                    {
                        observation.ActiveAberrations.push_back(&actor);
                        observation.SlimeWindow = observation.SlimeWindow
                            || HasAura(actor, DebilitatingSlimeSpell);
                    }
                    else
                        ++observation.ReserveAberrations;
                    break;
                case PrimeSubjectEntry:
                    if (actor.Selectable)
                        observation.PrimeSubjects.push_back(&actor);
                    break;
                case FlashFreezeEntry:
                    if (actor.Selectable && actor.Attackable)
                        observation.FlashFreezeBlocks.push_back(&actor);
                    break;
                case AbsoluteZeroEntry:
                    observation.AbsoluteZeros.push_back(&actor);
                    break;
                case MagmaJetFireEntry:
                    observation.MagmaJetFires.push_back(&actor);
                    break;
                case VileSwillEntry:
                    if (actor.Attackable)
                        observation.VileSwills.push_back(&actor);
                    break;
                default:
                    break;
            }
        }

    if (MechanicTimerSnapshot const* green =
            boss.FindMechanicTimer(ThrowGreenBottleSpell);
        green && green->RemainingMs != std::numeric_limits<uint32>::max())
        observation.NextGreenVialMs = green->RemainingMs;
    return observation;
}
}

#endif
