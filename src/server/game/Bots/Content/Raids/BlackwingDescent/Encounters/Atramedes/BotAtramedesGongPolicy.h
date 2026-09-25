#ifndef TRINITY_BOT_ATRAMEDES_GONG_POLICY_H
#define TRINITY_BOT_ATRAMEDES_GONG_POLICY_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesGeometry.h"
#include <cmath>
#include <limits>
#include <optional>
#include <string_view>

// When to strike an Ancient Dwarven Shield and who strikes it. The strike
// itself is the native spellclick (npc_spellclick_spells 77709 plus
// npc_atramedes_ancient_dwarven_shield::OnSpellClick); nothing here changes
// Sound, Vertigo or the breath target.
//
// Budget: the ten shields are finite and Searing Flame must always find one.
// Shields for the Searing Flames still expected stay in reserve; an
// emergency or air rescue may spend down to the reserve, an elective
// (80 Sound) gong keeps one more spare.
namespace BotEncounter::Atramedes
{
// 100 Sound is Devastation (78868). Ninety leaves one Sonic Breath tick (+20).
inline constexpr uint32 SoundEmergency = 90;
// Above this, spend a shield unless Searing Flame (which is gonged anyway
// and resets every bar) is due within SearingSoonMs.
inline constexpr uint32 SoundHigh = 80;
inline constexpr uint32 SearingSoonMs = 15000;
// Duty shields stand this far inside the shield toward the tank anchor.
inline constexpr float ShieldStandInset = 4.0f;

// Next-ground-phase Searing Flame reserve. The next ground phase's Searing
// Flame comes at least 51 s after landing (native schedule), and the air
// phase lasts at least 31 s, so it is >= 82 s away on the ground and >= 51 s
// away in the air. At a 150k raid-DPS floor (the canonical 10N composition
// measured 274-279k on Magmaw) and native 10N health 26,111,168 that removes
// 47% or 29% of the boss's health: below these the boss dies first.
inline constexpr float NextSearingHealthPctFromGround = 50.0f;
inline constexpr float NextSearingHealthPctFromAir = 30.0f;

// Air rescue by time to contact. Reverberating Flame: speed_run 0.714 of the
// 7 yd/s base (5 yd/s), +20% of that per Building Speed stack, one stack per
// second (78217 -> 78218, max 10); its breath (78353) reaches 5 yd.
inline constexpr float FlameBaseSpeed = 5.0f;
inline constexpr float FlameSpeedPerStack = 1.0f;
inline constexpr uint8 FlameMaxStacks = 10;
// Unbuffed player run speed; speed buffs only make the estimate cautious.
inline constexpr float KiterSpeed = 7.0f;
// Strike when contact is this close: the spellclick lands within one
// decision tick and the flame stops at once (SetGUID interrupts and stops it).
inline constexpr float RescueLeadSeconds = 1.0f;
// A shield counts as ahead of the kiter unless it lies more than this far
// behind it (toward the flame) around the arena centre.
inline constexpr float AheadToleranceRad = 10.0f * Geometry::Pi / 180.0f;

struct GongDecision
{
    bool Required = false;
    bool Urgent = false;
    std::string_view Reason;
    // Set when a gong would be wanted but the budget holds it back.
    std::string_view Withheld;
    ObjectGuid Clicker;
    std::optional<ShieldFact> Shield;
};

inline ActorSnapshot const* FindLivingPlayer(Blackboard const& board,
    ObjectGuid guid)
{
    if (guid.IsEmpty())
        return nullptr;
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid == guid)
            return player.Alive ? &player : nullptr;
    return nullptr;
}

// Shields to keep for the Searing Flames still expected: this ground phase's
// (from the published timer; unknown counts as pending) and the next ground
// phase's while the boss has enough health to reach it.
inline uint32 SearingFlameReserve(Facts const& facts)
{
    if (!facts.Boss)
        return 0;
    uint32 reserve = 0;
    float threshold = NextSearingHealthPctFromAir;
    if (facts.CurrentPhase != Phase::Air)
    {
        threshold = NextSearingHealthPctFromGround;
        bool const pending = facts.SearingFlameChannel || facts.SearingFlameInMs
            || !facts.GroundTimersPublished;
        if (pending)
            ++reserve;
    }
    if (facts.Boss->HealthPct > threshold)
        ++reserve;
    return reserve;
}

// Available shields ordered by distance to the ground tank anchor (GUID
// breaks ties). Rank 0 is the gong owner's, rank 1 the backup's.
inline std::optional<ShieldFact> DutyShield(Facts const& facts, std::size_t rank)
{
    std::vector<ShieldFact> shields = facts.Shields;
    std::stable_sort(shields.begin(), shields.end(),
        [](ShieldFact const& left, ShieldFact const& right)
        {
            return Geometry::Distance2d(left.Position, TankAnchor)
                < Geometry::Distance2d(right.Position, TankAnchor);
        });
    if (rank >= shields.size())
        return std::nullopt;
    return shields[rank];
}

inline Vector3 ShieldStandPoint(ShieldFact const& shield)
{
    float const bearing = Geometry::Bearing(shield.Position, TankAnchor);
    return Geometry::PointAt(shield.Position, bearing, ShieldStandInset,
        ArenaCenter.Z);
}

inline std::optional<ShieldFact> NearestShield(Facts const& facts,
    Vector3 const& from)
{
    std::optional<ShieldFact> best;
    float bestDistance = 0.0f;
    for (ShieldFact const& shield : facts.Shields)
    {
        float const distance = Geometry::Distance3d(from, shield.Position);
        if (!best || distance < bestDistance)
        {
            best = shield;
            bestDistance = distance;
        }
    }
    return best;
}

inline bool IsKiter(Facts const& facts, ObjectGuid guid)
{
    return !guid.IsEmpty() && (guid == facts.GroundKiter || guid == facts.AirKiter);
}

// Ground clicker: the owner, else the backup, else the living non-tank
// player closest to any shield. A kiter never leaves its kite to gong.
inline ObjectGuid GroundGonger(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    for (ObjectGuid guid : { duties.GongOwner, duties.GongBackup })
        if (FindLivingPlayer(board, guid) && !IsKiter(facts, guid))
            return guid;
    ObjectGuid best;
    float bestDistance = 0.0f;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || player.Guid == duties.Tank || IsKiter(facts, player.Guid))
            continue;
        std::optional<ShieldFact> const shield = NearestShield(facts, player.Position);
        if (!shield)
            continue;
        float const distance = Geometry::Distance3d(player.Position, shield->Position);
        if (best.IsEmpty() || distance < bestDistance)
        {
            best = player.Guid;
            bestDistance = distance;
        }
    }
    return best;
}

// Air kite direction around the arena centre: away from the chasing flame,
// clockwise while the flame still sits on the kiter.
inline int AirKiteDirection(Facts const& facts, ActorSnapshot const& kiter)
{
    if (ActorSnapshot const* flame = MarkerOf(facts.ReverberatingFlames, kiter))
        if (int const away = Geometry::AwayFromChaser(ArenaCenter, kiter.Position,
                flame->Position))
            return away;
    return -1;
}

// Seconds until the flame's 5 yd breath reaches the kiter when the kiter
// keeps running at KiterSpeed and the flame keeps gaining one stack a second.
inline float FlameTimeToContact(ActorSnapshot const& flame, ActorSnapshot const& kiter)
{
    uint8 const stacks = BuildingSpeedStacks(flame);
    float const gap = Geometry::Distance2d(flame.Position, kiter.Position)
        - FlameBreathRadius;
    float const closing = FlameBaseSpeed + FlameSpeedPerStack * float(stacks)
        - KiterSpeed;
    float const acceleration = stacks < FlameMaxStacks ? FlameSpeedPerStack : 0.0f;
    if (gap <= 0.0f)
        // Inside the breath: a slower flame is outrun, a faster one is not.
        return closing >= 0.0f ? 0.0f : std::numeric_limits<float>::infinity();
    if (acceleration <= 0.0f)
        return closing > 0.0f ? gap / closing : std::numeric_limits<float>::infinity();
    return (-closing + std::sqrt(closing * closing + 2.0f * acceleration * gap))
        / acceleration;
}

inline GongDecision DecideGroundGong(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    GongDecision decision;
    if (facts.BossStunned)
        return decision;
    std::size_t const available = facts.Shields.size();
    std::size_t const reserve = SearingFlameReserve(facts);
    if (facts.SearingFlameChannel)
        decision.Reason = "searing_flame";
    else if (facts.MaxSound >= SoundEmergency)
    {
        if (available <= reserve)
        {
            decision.Withheld = "sound_emergency_at_reserve";
            return decision;
        }
        decision.Reason = "sound_emergency";
    }
    else if (facts.MaxSound >= SoundHigh
        && !(facts.SearingFlameInMs && *facts.SearingFlameInMs <= SearingSoonMs))
    {
        if (available <= reserve + 1)
        {
            decision.Withheld = "sound_high_at_reserve";
            return decision;
        }
        decision.Reason = "sound_high";
    }
    else
        return decision;
    decision.Required = true;
    decision.Urgent = true;
    decision.Clicker = GroundGonger(board, facts, duties);
    if (ActorSnapshot const* clicker = FindLivingPlayer(board, decision.Clicker))
    {
        // The owner and backup strike their own duty shield when it is still
        // available; anyone else strikes the nearest.
        std::optional<ShieldFact> shield;
        if (decision.Clicker == duties.GongOwner)
            shield = DutyShield(facts, 0);
        else if (decision.Clicker == duties.GongBackup)
            shield = DutyShield(facts, 1);
        std::optional<ShieldFact> const nearest = NearestShield(facts, clicker->Position);
        if (!shield || (nearest && Geometry::Distance3d(clicker->Position, nearest->Position)
                <= ShieldClickDistance))
            shield = nearest;
        decision.Shield = shield;
    }
    return decision;
}

// A shield is ahead of the kiter unless it lies behind it (toward the flame)
// around the arena centre in the kite direction.
inline bool ShieldAhead(ShieldFact const& shield, ActorSnapshot const& kiter,
    int direction)
{
    float const offset = Geometry::AngleDelta(
        Geometry::Bearing(ArenaCenter, shield.Position),
        Geometry::Bearing(ArenaCenter, kiter.Position)) * float(direction);
    return offset >= -AheadToleranceRad;
}

// Best in-reach strike: the struck shield becomes the flame's next stop, so
// the farther it is from the flame the longer the relief. The kiter may use
// shields ahead of it; any other non-tank bot may relay from its own shield.
inline void ChooseAirStrike(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties, ActorSnapshot const* kiter, ActorSnapshot const* flame,
    GongDecision& decision)
{
    int const direction = kiter ? AirKiteDirection(facts, *kiter) : -1;
    float bestFlameDistance = -1.0f;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || player.Guid == duties.Tank)
            continue;
        bool const isKiter = kiter && player.Guid == kiter->Guid;
        for (ShieldFact const& shield : facts.Shields)
        {
            if (Geometry::Distance3d(player.Position, shield.Position) > ShieldClickDistance)
                continue;
            if (isKiter && !ShieldAhead(shield, *kiter, direction))
                continue;
            float const flameDistance = flame
                ? Geometry::Distance2d(flame->Position, shield.Position) : 0.0f;
            if (flameDistance > bestFlameDistance)
            {
                bestFlameDistance = flameDistance;
                decision.Clicker = player.Guid;
                decision.Shield = shield;
            }
        }
    }
}

inline GongDecision DecideAirGong(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    GongDecision decision;
    std::size_t const available = facts.Shields.size();
    std::size_t const reserve = SearingFlameReserve(facts);
    ActorSnapshot const* kiter = FindLivingPlayer(board, facts.AirKiter);
    ActorSnapshot const* flame = kiter ? MarkerOf(facts.ReverberatingFlames, *kiter) : nullptr;
    bool const contact = kiter && flame
        && FlameTimeToContact(*flame, *kiter) <= RescueLeadSeconds;
    if (contact)
        decision.Reason = "air_breath_rescue";
    else if (facts.MaxSound >= SoundEmergency)
        decision.Reason = "sound_emergency";
    else
        return decision;
    if (available <= reserve)
    {
        decision.Withheld = contact ? "air_breath_rescue_at_reserve"
            : "sound_emergency_at_reserve";
        decision.Reason = {};
        return decision;
    }
    decision.Required = true;
    decision.Urgent = true;

    ChooseAirStrike(board, facts, duties, kiter, flame, decision);
    if (!decision.Clicker.IsEmpty() || contact)
        // A rescue without a shield in reach waits: the kite route passes
        // each shield inside spellclick reach, the next one ahead included.
        return decision;
    // A Sound emergency with nobody in reach: the ground gonger walks.
    if (ActorSnapshot const* walker =
            FindLivingPlayer(board, GroundGonger(board, facts, duties)))
    {
        decision.Clicker = walker->Guid;
        decision.Shield = NearestShield(facts, walker->Position);
    }
    return decision;
}

inline GongDecision DecideGong(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    if (!facts.Boss || facts.Shields.empty())
        return {};
    if (facts.CurrentPhase == Phase::Ground)
        return DecideGroundGong(board, facts, duties);
    if (facts.CurrentPhase == Phase::Air)
        return DecideAirGong(board, facts, duties);
    return {};
}
}

#endif
