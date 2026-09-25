#ifndef TRINITY_BOT_ATRAMEDES_GONG_POLICY_H
#define TRINITY_BOT_ATRAMEDES_GONG_POLICY_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesGeometry.h"
#include <optional>
#include <string_view>

// When to strike an Ancient Dwarven Shield and who strikes it. The strike
// itself is the native spellclick (npc_spellclick_spells 77709 plus
// npc_atramedes_ancient_dwarven_shield::OnSpellClick); nothing here changes
// Sound, Vertigo or the breath target.
namespace BotEncounter::Atramedes
{
// 100 Sound is Devastation (78868). Ninety leaves one Sonic Breath tick (+20).
inline constexpr uint32 SoundEmergency = 90;
// Above this, spend a shield unless Searing Flame (which is gonged anyway
// and resets every bar) is due within SearingSoonMs.
inline constexpr uint32 SoundHigh = 80;
inline constexpr uint32 SearingSoonMs = 15000;
// Air rescue: the Reverberating Flame damages within 5 yd and speeds up
// every second; redirect it before it reaches the kiter.
inline constexpr float AirRescueDistance = 11.0f;
// Duty shields stand this far inside the shield toward the tank anchor.
inline constexpr float ShieldStandInset = 4.0f;

struct GongDecision
{
    bool Required = false;
    bool Urgent = false;
    std::string_view Reason;
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

inline ActorSnapshot const* NearestFlame(Facts const& facts, Vector3 const& from)
{
    ActorSnapshot const* best = nullptr;
    for (ActorSnapshot const* flame : facts.ReverberatingFlames)
        if (!best || Geometry::Distance2d(from, flame->Position)
            < Geometry::Distance2d(from, best->Position))
            best = flame;
    return best;
}

inline GongDecision DecideGroundGong(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    GongDecision decision;
    if (facts.BossStunned)
        return decision;
    if (facts.SearingFlameChannel)
        decision.Reason = "searing_flame";
    else if (facts.MaxSound >= SoundEmergency)
        decision.Reason = "sound_emergency";
    else if (facts.MaxSound >= SoundHigh
        && !(facts.SearingFlameInMs && *facts.SearingFlameInMs <= SearingSoonMs))
        decision.Reason = "sound_high";
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

inline GongDecision DecideAirGong(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    GongDecision decision;
    ActorSnapshot const* kiter = FindLivingPlayer(board, facts.AirKiter);
    ActorSnapshot const* flame = kiter ? NearestFlame(facts, kiter->Position) : nullptr;
    if (kiter && flame
        && Geometry::Distance2d(kiter->Position, flame->Position) <= AirRescueDistance)
        decision.Reason = "air_breath_rescue";
    else if (facts.MaxSound >= SoundEmergency)
        decision.Reason = "sound_emergency";
    else
        return decision;
    decision.Required = true;
    decision.Urgent = true;

    // The struck shield becomes the breath's next stop and its striker the
    // next kiter. Prefer the kiter itself (the breath returns to it at reset
    // speed); otherwise a non-tank bot already in reach of a shield, using
    // the shield farthest from the flame; otherwise the kiter or owner walks.
    if (kiter)
        if (std::optional<ShieldFact> const shield = NearestShield(facts, kiter->Position);
            shield && Geometry::Distance3d(kiter->Position, shield->Position)
                <= ShieldClickDistance)
        {
            decision.Clicker = kiter->Guid;
            decision.Shield = shield;
            return decision;
        }
    float bestFlameDistance = -1.0f;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || player.Guid == duties.Tank)
            continue;
        for (ShieldFact const& shield : facts.Shields)
        {
            if (Geometry::Distance3d(player.Position, shield.Position) > ShieldClickDistance)
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
    if (!decision.Clicker.IsEmpty())
        return decision;
    ActorSnapshot const* walker = kiter ? kiter
        : FindLivingPlayer(board, GroundGonger(board, facts, duties));
    if (walker)
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
