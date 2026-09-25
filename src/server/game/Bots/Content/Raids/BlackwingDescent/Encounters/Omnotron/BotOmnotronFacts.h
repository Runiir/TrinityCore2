#ifndef TRINITY_BOT_OMNOTRON_FACTS_H
#define TRINITY_BOT_OMNOTRON_FACTS_H

#include "Bots/BotEncounterBlackboard.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <vector>

// Observable Omnotron Defense System facts for bot policy. Every constant is
// a native or client value with its source in
// experiments/configs/cata_raid_encounters/blackwing_descent/
// omnotron_defense_system_ledger_v1.json; nothing here schedules a timer.
namespace BotEncounter::Omnotron
{
inline constexpr char const* EncounterNodeId = "bwd.omnotron.encounter";

// blackwing_descent.h, creature_template (TDB 434.22011).
inline constexpr uint32 ArcanotronEntry = 42166;
inline constexpr uint32 MagmatronEntry = 42178;
inline constexpr uint32 ElectronEntry = 42179;
inline constexpr uint32 ToxitronEntry = 42180;
inline constexpr uint32 PowerGeneratorEntry = 42733;
inline constexpr uint32 PoisonBombEntry = 42897;
inline constexpr uint32 PoisonPuddleEntry = 42920;
inline constexpr uint32 ChemicalCloudEntry = 42934;

// Spell IDs in 4.3.4 SpellDifficulty.dbc order {10N, 25N, 10H, 25H}.
using SpellSet = std::array<uint32, 4>;
inline constexpr SpellSet ActivatedAura{ 78740, 95016, 95017, 95018 };
inline constexpr SpellSet UnstableShieldAura{ 79900, 91447, 91448, 91449 };
inline constexpr SpellSet BarrierAura{ 79582, 91516, 91517, 91518 };
inline constexpr SpellSet PoisonSoakedShellAura{ 79835, 91501, 91502, 91503 };
inline constexpr SpellSet PowerConversionAura{ 79729, 91543, 91544, 91545 };
inline constexpr SpellSet ArcaneAnnihilatorCast{ 79710, 91540, 91541, 91542 };
inline constexpr SpellSet LightningConductorAura{ 79888, 91431, 91432, 91433 };
inline constexpr SpellSet AcquiringTargetAura{ 79501, 92035, 92036, 92037 };
inline constexpr SpellSet FlamethrowerChannel{ 79505, 91531, 91532, 91533 };
inline constexpr SpellSet SoakedInPoisonAura{ 80011, 91504, 91505, 91506 };
// Recharging: 78697 Electron, 78698 Magmatron, 78699 Arcanotron, 78700
// Toxitron (10N) and their 95019-95030 variants.
inline constexpr std::array<uint32, 16> RechargingAura{ 78697, 78698, 78699,
    78700, 95019, 95020, 95021, 95022, 95023, 95024, 95025, 95026, 95027,
    95028, 95029, 95030 };
inline constexpr uint32 InactiveAura = 78726;
inline constexpr uint32 PoweredDownAura = 82265;
inline constexpr uint32 ShuttingDownCast = 78746;
inline constexpr uint32 FixateAura = 80094;
inline constexpr uint32 ShadowConductorAura = 92053;
inline constexpr uint32 EncasingShadowsAura = 92023;
// Heroic Overcharge: the generator grows and ends in Arcane Blowback.
inline constexpr uint32 OverchargedPowerGeneratorAura = 91857;

// Client radii (4.4.2.59185 SpellRadius, equal in the 4.3.4 client).
inline constexpr float ChemicalCloudPlayerRadius = 12.0f;  // 80161
inline constexpr float PoisonPuddleRadius = 6.0f;          // 80097
inline constexpr float PoisonBombBlastRadius = 6.0f;       // 80092
inline constexpr float LightningConductorRadius = 8.0f;    // 79889
inline constexpr float PowerGeneratorRadius = 5.0f;        // 79629
inline constexpr float FlamethrowerHalfAngleDeg = 12.5f;   // 79504, 25 deg cone
// creature_model_info 32684-32688 BoundingRadius. Area spells add the
// target's size, so a construct is inside a 5 yd field at ~8.6 yd.
inline constexpr float ConstructBoundingRadius = 3.56457f;
// creature_model_info CombatReach; melee reach against a construct is
// player 1.5 + construct 3.45 + 4/3 yd (Unit::GetMeleeRange).
inline constexpr float ConstructCombatReach = 3.45f;
inline constexpr float PlayerCombatReach = 1.5f;

// Encounter floor: map 669 navmesh (data/mmaps/669*.mmtile) is walkable on a
// full 21 yd disc around the route node (bwd.omnotron.encounter). Movement
// destinations stay 1 yd inside it.
inline constexpr float ArenaCenterX = -324.78f;
inline constexpr float ArenaCenterY = -399.078f;
inline constexpr float ArenaRadius = 20.0f;

enum class ConstructKind : uint8
{
    Arcanotron,
    Magmatron,
    Electron,
    Toxitron
};

enum class ShieldState : uint8
{
    None,
    Casting,
    Up
};

struct ConstructFact
{
    ActorSnapshot const* Actor = nullptr;
    ConstructKind Kind = ConstructKind::Arcanotron;
    bool Active = false;
    bool ShuttingDown = false;
    bool Recharging = false;
    ShieldState Shield = ShieldState::None;
    // Expiry of the Activated aura; later expiry means newer activation.
    uint64 ActivatedExpiresAtMs = 0;
    uint64 RechargeExpiresAtMs = 0;

    bool Shielded() const { return Shield != ShieldState::None; }
    bool Fighting() const { return Active && !ShuttingDown; }
};

struct EncounterFacts
{
    bool Engaged = false;
    std::vector<ConstructFact> Constructs;
    std::vector<ActorSnapshot const*> PoisonBombs;
    std::vector<ActorSnapshot const*> PoisonPuddles;
    std::vector<ActorSnapshot const*> ChemicalClouds;
    std::vector<ActorSnapshot const*> PowerGenerators;

    ConstructFact const* Find(ObjectGuid guid) const
    {
        for (ConstructFact const& fact : Constructs)
            if (fact.Actor->Guid == guid)
                return &fact;
        return nullptr;
    }

    ConstructFact const* FindKind(ConstructKind kind) const
    {
        for (ConstructFact const& fact : Constructs)
            if (fact.Kind == kind && fact.Actor->Alive)
                return &fact;
        return nullptr;
    }
};

template <typename Set>
inline bool InSet(Set const& set, uint32 spellId)
{
    return spellId && std::find(set.begin(), set.end(), spellId) != set.end();
}

template <typename Set>
inline AuraSnapshot const* FindAnyAura(ActorSnapshot const& actor, Set const& set)
{
    for (AuraSnapshot const& aura : actor.Auras)
        if (InSet(set, aura.SpellId))
            return &aura;
    return nullptr;
}

inline bool HasAura(ActorSnapshot const& actor, uint32 spellId)
{
    return std::any_of(actor.Auras.begin(), actor.Auras.end(),
        [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
}

inline bool IsCasting(ActorSnapshot const& actor, SpellSet const& set)
{
    return actor.Cast && InSet(set, actor.Cast->SpellId);
}

inline std::optional<ConstructKind> KindOf(uint32 entry)
{
    switch (entry)
    {
        case ArcanotronEntry: return ConstructKind::Arcanotron;
        case MagmatronEntry: return ConstructKind::Magmatron;
        case ElectronEntry: return ConstructKind::Electron;
        case ToxitronEntry: return ConstructKind::Toxitron;
        default: return std::nullopt;
    }
}

inline float PlanarDistance(Vector3 const& left, Vector3 const& right)
{
    float const dx = left.X - right.X;
    float const dy = left.Y - right.Y;
    return std::sqrt(dx * dx + dy * dy);
}

inline ShieldState ObserveShield(ActorSnapshot const& actor)
{
    if (FindAnyAura(actor, UnstableShieldAura) || FindAnyAura(actor, BarrierAura)
        || FindAnyAura(actor, PoisonSoakedShellAura)
        || FindAnyAura(actor, PowerConversionAura))
        return ShieldState::Up;
    if (IsCasting(actor, UnstableShieldAura) || IsCasting(actor, BarrierAura)
        || IsCasting(actor, PoisonSoakedShellAura)
        || IsCasting(actor, PowerConversionAura))
        return ShieldState::Casting;
    return ShieldState::None;
}

// Live constructs are script summons and therefore arrive as Summons; a
// hostile-classified snapshot is accepted as well.
template <typename Visitor>
inline void ForEachEncounterUnit(Blackboard const& board, Visitor&& visit)
{
    for (ActorSnapshot const& actor : board.Hostiles)
        visit(actor);
    for (ActorSnapshot const& actor : board.Summons)
        visit(actor);
}

inline EncounterFacts Observe(Blackboard const& board)
{
    EncounterFacts facts;
    ForEachEncounterUnit(board, [&facts](ActorSnapshot const& actor)
    {
        if (!actor.Alive)
            return;
        if (std::optional<ConstructKind> const kind = KindOf(actor.Entry))
        {
            ConstructFact fact;
            fact.Actor = &actor;
            fact.Kind = *kind;
            bool const inactive = HasAura(actor, InactiveAura)
                || HasAura(actor, PoweredDownAura);
            AuraSnapshot const* activated = FindAnyAura(actor, ActivatedAura);
            fact.Active = !inactive && (activated || actor.InCombat
                || !actor.VictimGuid.IsEmpty());
            fact.ShuttingDown = actor.Cast
                && actor.Cast->SpellId == ShuttingDownCast;
            fact.Shield = fact.Active ? ObserveShield(actor) : ShieldState::None;
            fact.ActivatedExpiresAtMs = activated ? activated->ExpiresAtMs : 0;
            if (AuraSnapshot const* recharge = FindAnyAura(actor, RechargingAura))
            {
                fact.Recharging = true;
                fact.RechargeExpiresAtMs = recharge->ExpiresAtMs;
            }
            facts.Engaged = facts.Engaged || fact.Active;
            facts.Constructs.push_back(fact);
            return;
        }
        switch (actor.Entry)
        {
            case PoisonBombEntry: facts.PoisonBombs.push_back(&actor); break;
            case PoisonPuddleEntry: facts.PoisonPuddles.push_back(&actor); break;
            case ChemicalCloudEntry: facts.ChemicalClouds.push_back(&actor); break;
            case PowerGeneratorEntry: facts.PowerGenerators.push_back(&actor); break;
            default: break;
        }
    });
    std::sort(facts.Constructs.begin(), facts.Constructs.end(),
        [](ConstructFact const& left, ConstructFact const& right)
        {
            return left.Actor->Guid < right.Actor->Guid;
        });
    return facts;
}

// The player a Poison Bomb pursues: its Fixate aura caster, else its victim.
inline ObjectGuid BombFixateTarget(Blackboard const& board,
    ActorSnapshot const& bomb)
{
    for (ActorSnapshot const& player : board.Players)
        for (AuraSnapshot const& aura : player.Auras)
            if (aura.SpellId == FixateAura && aura.CasterGuid == bomb.Guid)
                return player.Guid;
    return bomb.VictimGuid;
}

inline bool CarriesLightningConductor(ActorSnapshot const& player)
{
    return FindAnyAura(player, LightningConductorAura) != nullptr;
}

inline bool IsAcquiredTarget(ActorSnapshot const& player)
{
    return FindAnyAura(player, AcquiringTargetAura) != nullptr;
}
}

#endif
