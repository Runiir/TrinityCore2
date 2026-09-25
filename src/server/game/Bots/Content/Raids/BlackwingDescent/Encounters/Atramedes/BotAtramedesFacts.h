#ifndef TRINITY_BOT_ATRAMEDES_FACTS_H
#define TRINITY_BOT_ATRAMEDES_FACTS_H

#include "Bots/BotEncounterBlackboard.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <string_view>
#include <vector>

// Read-only Atramedes (BWD 10N) facts derived from one encounter snapshot.
// Every identity below is native: boss_atramedes.cpp, blackwing_descent.h,
// the 4.3.4 client spell rows and the TDB map-669 spawns. Values and sources
// are in experiments/configs/cata_raid_encounters/blackwing_descent/
// atramedes_ledger_v1.json. Nothing here decides an action.
namespace BotEncounter::Atramedes
{
inline constexpr std::string_view EncounterNode = "bwd.atramedes.encounter";

inline constexpr uint32 BossEntry = 41442;
// Ground Sonar Pulse disk: 77674 ticks 77675 every 500 ms, +3 Sound in 5 yd.
inline constexpr uint32 SonarPulseEntry = 41546;
// Sonic Breath target marker; Atramedes channels 78098 at it (15 degree cone,
// 78100: 19,499 Fire and +20 Sound per 1 s tick).
inline constexpr uint32 TrackingFlamesEntry = 41879;
// Air Roaring Flame Breath (78353 every 500 ms: 15,599 Fire, +3 Sound, 5 yd)
// with a stacking +20% speed aura (78217 -> 78218).
inline constexpr uint32 ReverberatingFlameEntry = 41962;
// Fire patches: air trail (42001) and Searing Flame missiles (41807). Both
// carry 78018 -> 78023 every second: 9,749 Fire, DoT, +5 Sound in 3 yd.
inline constexpr uint32 RoaringFlamePatchEntry = 42001;
inline constexpr uint32 SearingFlamePatchEntry = 41807;
// Air Sonar Bomb marker (92530 summon); 92553 hits 6 yd: 20,000 Arcane, +20 Sound.
inline constexpr uint32 SonarBombMarkerEntry = 49623;
inline constexpr std::array<uint32, 8> ShieldEntries = {
    41445, 42947, 42949, 42951, 42954, 42956, 42958, 42960 };

// Spells without a SpellDifficulty row: one ID in every mode.
inline constexpr uint32 SearingFlameSpell = 77840;
inline constexpr uint32 SonicBreathSpell = 78075;
inline constexpr uint32 TakeOffSpell = 86915;
// Channelled (SPELL_ATTR1_IS_CHANNELLED) by the breath marker on its target;
// interrupting the marker ends it, so it names the current kiter only.
inline constexpr uint32 TrackingAura = 78092;
inline constexpr uint32 NoisyAura = 78897;
// Spells with a SpellDifficulty row (4.3.4 DBC): the facts match every
// variant (10N, 25N, 10H, 25H) so a mode never reads as "absent". The
// strategy's numeric tuning (thresholds, speeds) is 10N; heroic-only
// mechanics (Obnoxious Fiend, Nefarius shield destruction) are not handled.
inline constexpr std::array<uint32, 4> SonicBreathChannelSpells = {
    78098, 92403, 92404, 92405 };                    // SpellDifficulty 3121
inline constexpr std::array<uint32, 4> VertigoAuras = {
    77717, 92389, 92390, 92391 };                    // SpellDifficulty 3120
inline constexpr std::array<uint32, 4> BuildingSpeedAuras = {
    78218, 92463, 92464, 92465 };                    // SpellDifficulty 3135

inline constexpr float SonarPulseRadius = 5.0f;
inline constexpr float SonarBombRadius = 6.0f;
inline constexpr float FirePatchRadius = 3.0f;
inline constexpr float FlameBreathRadius = 5.0f;
inline constexpr float SonicBreathHalfAngleRad = 7.5f * 3.14159265f / 180.0f;
// creature_model_info 34547: CombatReach 20.
inline constexpr float BossCombatReach = 20.0f;
// Spellclick reach = INTERACTION_DISTANCE 5 + player reach 1.5 + shield
// reach 6 (model 32469). Stay well inside it.
inline constexpr float ShieldClickDistance = 9.0f;

struct ShieldSpawn
{
    uint32 SpawnId;
    uint32 Entry;
    float X;
    float Y;
    float Z;
};

// TDB spawn group 400 (creature 250122-250131), map 669.
inline constexpr std::array<ShieldSpawn, 10> ShieldSpawns = {{
    { 250122, 42956, 106.283f, -276.951f, 76.7294f },
    { 250123, 42954, 108.625f, -171.259f, 76.7299f },
    { 250124, 42958, 152.005f, -173.882f, 76.7294f },
    { 250125, 42947, 130.481f, -282.245f, 76.7299f },
    { 250126, 42949, 153.931f, -276.589f, 76.7299f },
    { 250127, 41445, 129.568f, -167.481f, 76.7299f },
    { 250128, 42960, 169.575f, -262.495f, 76.7297f },
    { 250129, 42951, 169.712f, -186.167f, 76.7297f },
    { 250130, 42954, 181.769f, -253.035f, 76.7294f },
    { 250131, 42956, 182.734f, -196.465f, 76.7294f },
}};

// Arena floor centre of the shield ring (spirit spawns 250132-250139 lie on
// the same floor, z 74.99-75.05).
inline constexpr Vector3 ArenaCenter{ 145.0f, -225.0f, 75.0f };
// Ground-phase tank anchor: inside the ring, east of centre, so the two
// east shields (250130, 250131) are ~35 yd from the boss centre.
inline constexpr Vector3 TankAnchor{ 162.0f, -224.5f, 75.0f };

enum class Phase : uint8
{
    Absent,
    PrePull,
    Ground,
    Air
};

struct ShieldFact
{
    ObjectGuid Guid;
    Vector3 Position;
};

struct Facts
{
    ActorSnapshot const* Boss = nullptr;
    Phase CurrentPhase = Phase::Absent;
    bool SearingFlameChannel = false;
    bool SonicBreathActive = false;
    bool BossStunned = false;
    // The boss publishes its ground schedule (GetTimeUntilEncounterMechanic)
    // and the blackboard carries it: liftoff is always scheduled on the
    // ground, so its timer proves publication.
    bool GroundTimersPublished = false;
    std::optional<uint32> SearingFlameInMs;
    std::vector<ShieldFact> Shields;
    std::vector<ActorSnapshot const*> SonarPulses;
    std::vector<ActorSnapshot const*> TrackingFlames;
    std::vector<ActorSnapshot const*> ReverberatingFlames;
    std::vector<ActorSnapshot const*> FirePatches;
    std::vector<ActorSnapshot const*> BombMarkers;
    ObjectGuid GroundKiter;
    ObjectGuid AirKiter;
    uint32 MaxSound = 0;
    ObjectGuid LoudestPlayer;
};

inline bool HasAura(ActorSnapshot const& actor, uint32 spellId)
{
    return std::any_of(actor.Auras.begin(), actor.Auras.end(),
        [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
}

inline AuraSnapshot const* FindAura(ActorSnapshot const& actor, uint32 spellId)
{
    auto itr = std::find_if(actor.Auras.begin(), actor.Auras.end(),
        [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
    return itr == actor.Auras.end() ? nullptr : &*itr;
}

template <std::size_t N>
inline bool IsAnyOf(std::array<uint32, N> const& ids, uint32 id)
{
    return std::find(ids.begin(), ids.end(), id) != ids.end();
}

template <std::size_t N>
inline AuraSnapshot const* FindAnyAura(ActorSnapshot const& actor,
    std::array<uint32, N> const& ids)
{
    auto itr = std::find_if(actor.Auras.begin(), actor.Auras.end(),
        [&ids](AuraSnapshot const& aura) { return IsAnyOf(ids, aura.SpellId); });
    return itr == actor.Auras.end() ? nullptr : &*itr;
}

// Building Speed stacks on a Reverberating Flame (+20% speed each, max 10).
inline uint8 BuildingSpeedStacks(ActorSnapshot const& flame)
{
    AuraSnapshot const* aura = FindAnyAura(flame, BuildingSpeedAuras);
    return aura ? std::min<uint8>(aura->Stacks ? aura->Stacks : 1, 10) : 0;
}

inline bool IsShieldEntry(uint32 entry)
{
    return std::find(ShieldEntries.begin(), ShieldEntries.end(), entry)
        != ShieldEntries.end();
}

// Sound is the player's alternate power while the Sound Bar (88824) is up.
inline uint32 SoundOf(ActorSnapshot const& actor)
{
    return actor.MaxAlternatePower ? actor.AlternatePower : 0;
}

inline ActorSnapshot const* FindBoss(Blackboard const& board)
{
    for (ActorSnapshot const& actor : board.Hostiles)
        if (actor.Alive && actor.Entry == BossEntry)
            return &actor;
    return nullptr;
}

inline Facts BuildFacts(Blackboard const& board)
{
    Facts facts;
    facts.Boss = FindBoss(board);
    if (!facts.Boss)
        return facts;
    ActorSnapshot const& boss = *facts.Boss;

    // Liftoff makes Atramedes passive (AttackStop, REACT_PASSIVE) before the
    // takeoff spline; the landing restores REACT_AGGRESSIVE after 800 ms.
    if (!boss.InCombat)
        facts.CurrentPhase = Phase::PrePull;
    else if (boss.Flying || !boss.ReactAggressive)
        facts.CurrentPhase = Phase::Air;
    else
        facts.CurrentPhase = Phase::Ground;

    if (boss.Cast)
    {
        facts.SearingFlameChannel = boss.Cast->SpellId == SearingFlameSpell;
        // 2 s cast, then the 6 s channel: both carry the same spell ID.
        facts.SonicBreathActive = IsAnyOf(SonicBreathChannelSpells, boss.Cast->SpellId);
    }
    facts.BossStunned = FindAnyAura(boss, VertigoAuras) != nullptr;
    if (MechanicTimerSnapshot const* timer = boss.FindMechanicTimer(SearingFlameSpell))
        if (timer->RemainingMs != std::numeric_limits<uint32>::max())
            facts.SearingFlameInMs = timer->RemainingMs;
    if (MechanicTimerSnapshot const* timer = boss.FindMechanicTimer(TakeOffSpell))
        facts.GroundTimersPublished = timer->RemainingMs != std::numeric_limits<uint32>::max();

    auto collect = [&facts](std::vector<ActorSnapshot> const& actors)
    {
        for (ActorSnapshot const& actor : actors)
        {
            if (!actor.Alive)
                continue;
            switch (actor.Entry)
            {
                case SonarPulseEntry: facts.SonarPulses.push_back(&actor); break;
                case TrackingFlamesEntry: facts.TrackingFlames.push_back(&actor); break;
                case ReverberatingFlameEntry: facts.ReverberatingFlames.push_back(&actor); break;
                case RoaringFlamePatchEntry:
                case SearingFlamePatchEntry: facts.FirePatches.push_back(&actor); break;
                case SonarBombMarkerEntry: facts.BombMarkers.push_back(&actor); break;
                default: break;
            }
        }
    };
    collect(board.Summons);
    collect(board.Hostiles);

    // A used shield loses its spellclick flag and becomes unselectable
    // (npc_atramedes_ancient_dwarven_shield::OnSpellClick), so only usable
    // shields remain interactable.
    for (ActorSnapshot const& actor : board.Interactables)
        if (actor.Alive && actor.Selectable && actor.Interactable
            && IsShieldEntry(actor.Entry))
            facts.Shields.push_back({ actor.Guid, actor.Position });
    std::sort(facts.Shields.begin(), facts.Shields.end(),
        [](ShieldFact const& left, ShieldFact const& right)
        {
            return left.Guid < right.Guid;
        });

    // A marker's own Tracking channel names its target; the target's aura
    // (cast by that marker) is the same fact seen from the player side.
    auto tracks = [](ActorSnapshot const& player,
        std::vector<ActorSnapshot const*> const& markers)
    {
        AuraSnapshot const* aura = FindAura(player, TrackingAura);
        return std::any_of(markers.begin(), markers.end(),
            [&player, aura](ActorSnapshot const* marker)
            {
                if (aura && aura->CasterGuid == marker->Guid)
                    return true;
                return marker->Cast && marker->Cast->SpellId == TrackingAura
                    && marker->Cast->TargetGuid == player.Guid;
            });
    };
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive)
            continue;
        uint32 const sound = SoundOf(player);
        if (sound > facts.MaxSound
            || (sound == facts.MaxSound && !facts.LoudestPlayer.IsEmpty()
                && player.Guid < facts.LoudestPlayer))
        {
            facts.MaxSound = sound;
            facts.LoudestPlayer = player.Guid;
        }
        // Only a live marker in this snapshot makes the player a kiter. A
        // gong interrupts the Reverberating Flame, so during a redirect
        // nobody is the air kiter until the flame re-tracks the striker.
        if (tracks(player, facts.ReverberatingFlames))
            facts.AirKiter = player.Guid;
        else if (tracks(player, facts.TrackingFlames))
            facts.GroundKiter = player.Guid;
    }
    if (facts.MaxSound == 0)
        facts.LoudestPlayer = ObjectGuid();
    return facts;
}

// The breath marker (Tracking Flames or Reverberating Flame) chasing `self`.
inline ActorSnapshot const* MarkerOf(std::vector<ActorSnapshot const*> const& markers,
    ActorSnapshot const& self)
{
    AuraSnapshot const* aura = FindAura(self, TrackingAura);
    for (ActorSnapshot const* marker : markers)
        if ((aura && aura->CasterGuid == marker->Guid)
            || (marker->Cast && marker->Cast->SpellId == TrackingAura
                && marker->Cast->TargetGuid == self.Guid))
            return marker;
    return nullptr;
}
}

#endif
