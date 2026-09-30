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
// Air Resonating Clash: the striker keeps this 15 s dummy aura (effect 1 on
// the caster). The flame stops, waits 2 s, flies to the struck shield and
// then tracks the striker, so its holder is the next air kiter.
inline constexpr uint32 AirClashAura = 78168;
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
// TDB 434.22011: creature_template 41442 modelid1 34547, scale 1;
// creature_model_info 34547: BoundingRadius 2, CombatReach 20. The large
// "hitbox" is the combat reach (user raid experience, 2026-09-25).
inline constexpr float BossCombatReach = 20.0f;
// Unit::GetMeleeRange: attacker reach (1.5 for players) + target reach +
// 4/3, compared with the 3D centre-to-centre distance. Melee holds a slot
// just inside it, leaving room to sidestep a Sonar Pulse without leaving
// melee range (user raid experience, 2026-09-25: "melee should stay at max
// melee range as much as possible to have the chance to dodge the rings").
inline constexpr float PlayerCombatReach = 1.5f;
inline constexpr float MeleeRangeYards = PlayerCombatReach + BossCombatReach + 4.0f / 3.0f;
inline constexpr float MeleeSlotRadius = MeleeRangeYards - 1.25f;
// Native spellclick reach (executor: IsWithinDistInMap(shield, 5), 3D with
// both combat reaches) = INTERACTION_DISTANCE 5 + player reach 1.5 + shield
// CombatReach 6 (creature_model_info 32469) = 12.5 yd. Keep 1 yd of margin.
inline constexpr float ShieldClickDistance = 11.5f;

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
// Ground-phase tank anchor, near the arena centre ("drag the boss toward the
// door, into the big circular arena", Wowhead). From here every air relay
// station (BotAtramedesAirGong.h) is also in spell range of the grounded
// boss, so the gong owner can wait at its next air station through the
// ground phase and be in place when Atramedes lifts off.
inline constexpr Vector3 TankAnchor{ 150.0f, -224.5f, 75.0f };

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
    // Time to the liftoff, while the ground schedule is published.
    std::optional<uint32> LiftoffInMs;
    std::vector<ShieldFact> Shields;
    std::vector<ActorSnapshot const*> SonarPulses;
    std::vector<ActorSnapshot const*> TrackingFlames;
    std::vector<ActorSnapshot const*> ReverberatingFlames;
    std::vector<ActorSnapshot const*> FirePatches;
    std::vector<ActorSnapshot const*> BombMarkers;
    ObjectGuid GroundKiter;
    ObjectGuid AirKiter;
    // The air kiter known only as the target the flame keeps following (no
    // Tracking aura, see UntrackedAirKiter) and that flame.
    bool AirKiterUntracked = false;
    ActorSnapshot const* AirKiterFlame = nullptr;
    uint32 MaxSound = 0;
    ObjectGuid LoudestPlayer;
    // Ice Block was already used in this fight (IceBlockGuard,
    // BotAtramedesIceBlockGuard.h): the play is strictly once per fight, so
    // a cooldown that came back does not make it available again. Memory
    // across snapshots, so it is not derived by BuildFacts; the strategy
    // sets it from its guard.
    bool IceBlockSpent = false;
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

// Building Speed stack cap on the server: SpellMgrCorrectionsPart04.cpp sets
// StackAmount 10 for 78218/92463/92464/92465. The client rows (4.3.4 DBC and
// 4.4.2.59185 SpellAuraOptions) say 99 for 10N/25N/10H and 10 for 25H; the
// correction wins at runtime (the ledger records the conflict).
inline constexpr uint8 BuildingSpeedMaxStacks = 10;

// Building Speed stacks on a Reverberating Flame (+20% speed each), as
// observed: never clamped, so a higher runtime cap still reads true.
inline uint8 BuildingSpeedStacks(ActorSnapshot const& flame)
{
    AuraSnapshot const* aura = FindAnyAura(flame, BuildingSpeedAuras);
    return aura ? (aura->Stacks ? aura->Stacks : 1) : 0;
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

// Atramedes is always a native summon: the bell intro and the respawn 30 s
// after a wipe both use instance->SummonCreature (instance_blackwing_descent
// DATA_ATRAMEDES_INTRO, EVENT_RESPAWN_ATRAMEDES), and the encounter
// blackboard files an attackable TempSummon under Summons, not Hostiles
// (BotWorldPopulationMgrEncounterBlackboard.cpp). Round 4 looked only at
// Hostiles: the plan never found him, never owned the node, and the route
// failed closed on him for the whole fight (raid_mechanic_contract_fail_closed).
inline ActorSnapshot const* FindBoss(Blackboard const& board)
{
    for (auto const* list : { &board.Summons, &board.Hostiles })
        for (ActorSnapshot const& actor : *list)
            if (actor.Alive && actor.Entry == BossEntry)
                return &actor;
    return nullptr;
}

// Ice Block (45438) grants immunity to every school with
// SPELL_ATTR1_DISPEL_AURAS_ON_IMMUNITY, so it strips the physical Tracking
// aura (78092) and ends the flame's Tracking channel. The flame AI
// (npc_atramedes_reverberating_flame) keeps its MoveFollow and target and
// only re-acquires a dead or missing target: the flame stays on the iced
// mage and still follows it after the block, with no Tracking fact left.
// Without a Tracking target, a player under Ice Block or Hypothermia (41425)
// is the target of the flame nearest it, unless a newer air striker (a later
// Resonating Clash 78168) has taken the flame since.
inline constexpr uint32 IceBlockAura = 45438;
inline constexpr uint32 HypothermiaAura = 41425;
inline constexpr float UntrackedFollowRadius = 45.0f;

inline void UntrackedAirKiter(Blackboard const& board, Facts& facts)
{
    ActorSnapshot const* newestStriker = nullptr;
    uint64 newestExpiry = 0;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive)
            if (AuraSnapshot const* clash = FindAura(player, AirClashAura))
                if (!newestStriker || clash->ExpiresAtMs > newestExpiry)
                {
                    newestStriker = &player;
                    newestExpiry = clash->ExpiresAtMs;
                }
    float bestDistance = UntrackedFollowRadius;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || (!FindAura(player, IceBlockAura)
                && !FindAura(player, HypothermiaAura))
            || (newestStriker && newestStriker->Guid != player.Guid))
            continue;
        for (ActorSnapshot const* flame : facts.ReverberatingFlames)
        {
            float const dx = flame->Position.X - player.Position.X;
            float const dy = flame->Position.Y - player.Position.Y;
            float const distance = std::sqrt(dx * dx + dy * dy);
            if (distance <= bestDistance)
            {
                bestDistance = distance;
                facts.AirKiter = player.Guid;
                facts.AirKiterUntracked = true;
                facts.AirKiterFlame = flame;
            }
        }
    }
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
    {
        facts.GroundTimersPublished = timer->RemainingMs != std::numeric_limits<uint32>::max();
        if (facts.GroundTimersPublished)
            facts.LiftoffInMs = timer->RemainingMs;
    }

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
        // The Tracking Flames channel outlives the breath (10 s summon vs a
        // 2 s cast and 6 s channel): only an active breath makes a kiter.
        else if (facts.SonicBreathActive && tracks(player, facts.TrackingFlames))
            facts.GroundKiter = player.Guid;
    }
    if (facts.MaxSound == 0)
        facts.LoudestPlayer = ObjectGuid();
    if (facts.CurrentPhase == Phase::Air && facts.AirKiter.IsEmpty())
        UntrackedAirKiter(board, facts);
    return facts;
}

// The Reverberating Flame chasing the air kiter `self`: its Tracking marker,
// or the flame it is known to follow without one (UntrackedAirKiter).
inline ActorSnapshot const* MarkerOf(std::vector<ActorSnapshot const*> const& markers,
    ActorSnapshot const& self);
inline ActorSnapshot const* KiterFlame(Facts const& facts, ActorSnapshot const& self)
{
    if (facts.AirKiterUntracked && self.Guid == facts.AirKiter)
        return facts.AirKiterFlame;
    return MarkerOf(facts.ReverberatingFlames, self);
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
