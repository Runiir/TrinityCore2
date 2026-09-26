#ifndef TRINITY_BOT_CHIMAERON_FACTS_H
#define TRINITY_BOT_CHIMAERON_FACTS_H

#include "Bots/BotEncounterBlackboard.h"

#include <algorithm>
#include <cstdint>
#include <initializer_list>
#include <limits>
#include <optional>
#include <string_view>

// Read-only Chimaeron (Blackwing Descent) facts for bot arbitration. Every
// identity below is a native one: boss_chimaeron.cpp, the TDB 4.3.4 world
// snapshot and the pinned 4.3.4 client Spell/SpellEffect tables (see
// docs/bot_raids/strategies/t11/blackwing_descent/chimaeron.md). Nothing here
// changes encounter state; the strategy only reads the cohort blackboard.
namespace BotEncounter::Chimaeron
{
constexpr uint32 BossEntry = 43296;
constexpr uint32 BileOTronEntry = 44418;
constexpr uint32 FinkleEntry = 44202;

// Finkle's Mixture: area aura the Bile-O-Tron 800 spreads to every player.
// Effect 0 base points 10000: damage taken above that health cannot reduce the
// player below 1 health (spell_chimaeron_finkles_mixture absorbs the rest).
constexpr uint32 FinklesMixtureSpell = 82705;
constexpr uint32 MassacreSpell = 82848;          // 4000 ms cast, 999999 damage
constexpr uint32 BreakSpell = 82881;             // +25% physical taken, 4 stacks, 60 s
constexpr uint32 DoubleAttackSpell = 88826;      // one charge: next swing hits twice
constexpr uint32 FeudSpell = 88872;              // 30000 ms pacify after a knockout
constexpr uint32 MortalityRaidSpell = 82890;     // -99% healing received
constexpr uint32 MortalityBossSpell = 82934;     // 10N: immune to taunt, +10% taken
constexpr uint32 MortalityBossAltSpell = 95524;  // 25N difficulty variant
constexpr uint32 CausticSlimeSpell = 82935;      // 10N: 235200 Nature split in 6 yd

constexpr uint64 MixtureFloorHealth = 10000;
// Bot margin: heal a mixture-protected player to at least this much so a
// small non-lethal hit cannot leave them unprotected before the next one.
constexpr uint64 FloorTargetHealth = 20000;
constexpr float MortalityHealthPct = 20.0f;
// Burn window before Mortality (both guides pause around 22-25%): damage is
// held between these bounds until the raid is ready; tanks enter at 80%+.
constexpr float BurnHoldMaxPct = 23.0f;
constexpr float BurnHoldFloorPct = 20.3f;
constexpr float BurnReadyTankPct = 80.0f;
constexpr uint32 FeudDurationMs = 30000;
constexpr uint32 MassacreCastMs = 4000;

constexpr std::string_view RegroupNode = "bwd.chimaeron.regroup";
constexpr std::string_view FinkleNode = "bwd.chimaeron.finkle";
constexpr std::string_view WakeWaitNode = "bwd.chimaeron.wake_wait";
constexpr std::string_view EncounterNode = "bwd.chimaeron.encounter";

enum class Phase : uint8
{
    None,       // not a Chimaeron node, or no live boss
    Prewake,    // the boss sleeps: before the wake, or back asleep after a reset
    Mixture,    // phase one with Finkle's Mixture protecting the raid
    Outage,     // Bile-O-Tron offline (Systems Failure): no mixture
    Mortality   // below 20%: Mortality, no healing, no taunt
};

inline char const* PhaseName(Phase phase)
{
    switch (phase)
    {
        case Phase::Prewake: return "prewake";
        case Phase::Mixture: return "mixture";
        case Phase::Outage: return "outage";
        case Phase::Mortality: return "mortality";
        default: return "none";
    }
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

inline ActorSnapshot const* FindBoss(Blackboard const& board)
{
    for (auto const* actors : { &board.Hostiles, &board.Summons })
        for (ActorSnapshot const& actor : *actors)
            if (actor.Alive && actor.Entry == BossEntry)
                return &actor;
    return nullptr;
}

inline ActorSnapshot const* FindPlayer(Blackboard const& board, ObjectGuid guid)
{
    if (guid.IsEmpty())
        return nullptr;
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid == guid)
            return &player;
    return nullptr;
}

// Another hostile (patrol, leftover trash, a summon) is fighting a raid
// member or a raid pet. Prewake offense suppression must not stop the raid
// from answering it; only the sleeping boss is off limits.
inline bool OtherHostileEngaged(Blackboard const& board, ActorSnapshot const& boss)
{
    auto raidMember = [&board](ObjectGuid guid)
    {
        ActorSnapshot const* actor = board.FindActor(guid);
        return actor && (actor->Kind == ActorKind::Player || actor->Kind == ActorKind::Pet);
    };
    for (auto const* actors : { &board.Hostiles, &board.Summons })
        for (ActorSnapshot const& actor : *actors)
            if (actor.Alive && actor.Guid != boss.Guid && actor.Kind != ActorKind::Pet
                && actor.Attackable && actor.InCombat && !actor.VictimGuid.IsEmpty()
                && raidMember(actor.VictimGuid))
                return true;
    return false;
}

inline bool IsAlivePlayer(Blackboard const& board, ObjectGuid guid)
{
    ActorSnapshot const* actor = FindPlayer(board, guid);
    return actor && actor->Alive;
}

inline bool IsEngaged(ActorSnapshot const& boss)
{
    return boss.InCombat || !boss.VictimGuid.IsEmpty();
}

// The boss sleeps: out of combat with no victim and REACT_PASSIVE. The native
// script is passive only while asleep (Initialize on spawn and on every
// Reset); JustEngagedWith and the wake event make him aggressive, and nothing
// makes him passive again until the next reset. This reads the boss's own
// state, not the instance-wide IsEncounterInProgress, which another BWD boss
// in progress on the full route would also set.
inline bool IsAsleep(ActorSnapshot const& boss)
{
    return !IsEngaged(boss) && !boss.ReactAggressive;
}

inline bool IsMortality(ActorSnapshot const& boss)
{
    return HasAura(boss, MortalityBossSpell) || HasAura(boss, MortalityBossAltSpell);
}

// Mixture state is a raid-wide decision: a strict majority of the living bots
// carry the area aura. A single late propagation or a dead member cannot flip
// the whole formation between spread and stack.
inline bool MixtureActive(Blackboard const& board)
{
    uint32 living = 0;
    uint32 protectedMembers = 0;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive)
        {
            ++living;
            if (HasAura(player, FinklesMixtureSpell))
                ++protectedMembers;
        }
    return living && protectedMembers * 2 > living;
}

struct Observation
{
    ActorSnapshot const* Boss = nullptr;
    ActorSnapshot const* Bot = nullptr;
    Phase CurrentPhase = Phase::None;
    bool MixtureOn = false;
    bool FeudActive = false;
    // Remaining Feud time from the aura expiry; empty when not observable.
    std::optional<uint32> FeudRemainingMs;
    bool DoubleAttackPending = false;
    bool MassacreCasting = false;
    // Authoritative native time to the next Massacre cast when the boss script
    // publishes it (GetTimeUntilEncounterMechanic); empty otherwise.
    std::optional<uint32> MassacreInMs;
};

inline bool IsPrewakeNode(std::string_view node)
{
    return node == RegroupNode || node == FinkleNode || node == WakeWaitNode;
}

// Boss-side observation, independent of any bot: the blackboard publisher
// evaluates encounter latches from it once per revision.
inline Observation ObserveEncounter(Blackboard const& board)
{
    Observation observation;
    bool const wakeNode = IsPrewakeNode(board.Route.NodeId);
    bool const encounterNode = board.Route.NodeId == EncounterNode;
    if (!wakeNode && !encounterNode)
        return observation;
    observation.Boss = FindBoss(board);
    if (!observation.Boss)
        return observation;

    ActorSnapshot const& boss = *observation.Boss;
    observation.MixtureOn = MixtureActive(board);
    if (AuraSnapshot const* feud = FindAura(boss, FeudSpell))
    {
        observation.FeudActive = true;
        if (feud->ExpiresAtMs > board.ObservedAtMs)
            observation.FeudRemainingMs =
                uint32(std::min<uint64>(feud->ExpiresAtMs - board.ObservedAtMs,
                    std::numeric_limits<uint32>::max()));
        else if (feud->ExpiresAtMs)
            observation.FeudRemainingMs = 0u;
    }
    observation.DoubleAttackPending = HasAura(boss, DoubleAttackSpell);
    observation.MassacreCasting = boss.Cast && boss.Cast->SpellId == MassacreSpell;
    if (MechanicTimerSnapshot const* timer = boss.FindMechanicTimer(MassacreSpell))
        if (timer->RemainingMs != std::numeric_limits<uint32>::max())
            observation.MassacreInMs = timer->RemainingMs;

    if (wakeNode)
        observation.CurrentPhase = IsEngaged(boss) ? Phase::None : Phase::Prewake;
    else if (IsAsleep(boss))
        // Back asleep at the encounter node: the native reset after a wipe
        // (REACT_PASSIVE, PHASE_ASLEEP; Finkle and the Bile-O-Tron respawn
        // 30 s after the evade). Only Finkle's gossip wakes him; attacking
        // the sleeping boss would start the fight without Finkle's Mixture.
        observation.CurrentPhase = Phase::Prewake;
    else if (IsMortality(boss))
        observation.CurrentPhase = Phase::Mortality;
    else if (!observation.MixtureOn)
        observation.CurrentPhase = Phase::Outage;
    else
        observation.CurrentPhase = Phase::Mixture;
    return observation;
}

inline Observation Observe(Blackboard const& board, ObjectGuid botGuid)
{
    Observation observation = ObserveEncounter(board);
    observation.Bot = board.FindActor(botGuid);
    if (!observation.Boss || !observation.Bot || !observation.Bot->Alive)
    {
        observation.CurrentPhase = Phase::None;
        observation.Bot = observation.Bot && observation.Bot->Alive ? observation.Bot : nullptr;
    }
    return observation;
}
}

#endif
