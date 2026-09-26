#ifndef TRINITY_BOT_ATRAMEDES_SPIRITS_H
#define TRINITY_BOT_ATRAMEDES_SPIRITS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesArenaFloor.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesMovementPolicy.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <limits>
#include <optional>
#include <string_view>
#include <utility>
#include <vector>

// The two Dark Iron spirit packs before the Ancient Bell (route nodes
// bwd.atramedes.north_spirits and bwd.atramedes.south_spirits).
//
// Native (blackwing_descent.cpp npc_bwd_dwarven_spirit, spawn groups 435 and
// 436, creature_formations groupAI 3): each group of four aggroes together,
// resets and respawns 30 s after a wipe. A dying spirit casts its Bestowal
// on the others, which then gain its ability, so the kill order decides what
// the fight turns into. Spell rows (4.3.4 DBC). An area effect with TargetA
// SRC_CASTER and TargetB UNIT_SRC_AREA_ENEMY uses the TargetB radius
// (SpellEffectInfo::CalcRadius), tested as a 2D cylinder with no hitbox for
// these generic-family spells (WorldObjectSpellAreaTargetCheck):
//   Thunderclap 80649 (Moltenfist): 20 yd around the caster (TargetB radius
//     index 9; round 3 logged a hit at 16 yd), only while its victim is in
//     melee range, every 6-8 s.
//   Chain Lightning 80646 (Shadowforge): random target within 90 yd,
//     8 targets, magic chain (12.5 yd jumps), every 10-11 s.
//   Stormbolt 80648 (Anvilrage): random target within 30 yd, 8 yd splash
//     with a stun, every 19-23 s.
//   Burden of the Crown 80718 (Corehammer): on its victim, +100% damage done
//     and no power cost, a 13.9k self-hit on each hit (80722).
//   Whirlwind 80652 (Burningeye): 5 s, every second 80651 (56.5k physical,
//     4 yd: TargetB radius index 26; round 3: the tank at 4.37-4.56 yd took
//     0 of 13 ticks) around the spirit; Avatar 80645 (Thaurissan; Angerforge's
//     Bestowal also grants Avatar in the native script), Stoneblood 80655
//     (Angerforge), Shield of Light 80747 then Execution Sentence 80727 on
//     the victim (Ironstar).
// Plan:
//   - kill order: the ability least harmful to hand on first, the one never
//     to hand on last. North (Icy Veins): Corehammer (Burden then buffs the
//     raid), Anvilrage, Moltenfist, Shadowforge. South (no readable source
//     yet): Angerforge, Thaurissan, Burningeye, Ironstar;
//   - ranged and healers stand on a ring 30 yd from the engaged pack, as
//     near the bearing toward the arena centre as the room allows: outside
//     every Thunderclap (20 yd, with a 1.5 yd margin), 35 yd from every idle
//     spirit (the other pack), on the arena floor and 15.5 yd apart, so
//     Chain Lightning (12.5 yd jumps) does not jump between them;
//   - melee (not the tank) within WhirlwindDangerYards of a spirit under
//     Whirlwind (80652) step to a ring WhirlwindHoldYards from their target:
//     outside every whirlwinding spirit's 4 yd pulse and still inside melee
//     range (1.5 + spirit reach 3.375 + 4/3 = 6.21 yd, creature_model_info
//     36437-36444), so they keep hitting and the native chase does not pull
//     them back in; with no such point (two whirlwinding spirits side by
//     side) they leave radially from those spirits' centroid (round 3: the
//     rogue and the retribution paladin died to Whirlwind handed on to two
//     spirits);
//   - everyone, the tank included, damages the kill-order target: on a trash
//     route the shared group focus is the tank's own target, so the tank
//     sets the order for the raid; the tank's position and the melee's
//     outside a Whirlwind are left to native tanking and melee range.
// The route keeps the pull, threat pickup and completion (OwnsNode stays
// false); before the pack is engaged this plan is empty.
namespace BotEncounter::Atramedes::Spirits
{
inline constexpr std::string_view NorthNode = "bwd.atramedes.north_spirits";
inline constexpr std::string_view SouthNode = "bwd.atramedes.south_spirits";

inline constexpr uint32 Corehammer = 43122;
inline constexpr uint32 Moltenfist = 43125;
inline constexpr uint32 Anvilrage = 43128;
inline constexpr uint32 Shadowforge = 43129;
inline constexpr uint32 Angerforge = 43119;
inline constexpr uint32 Thaurissan = 43126;
inline constexpr uint32 Ironstar = 43127;
inline constexpr uint32 Burningeye = 43130;

inline constexpr std::array<uint32, 4> NorthKillOrder{ Corehammer, Anvilrage,
    Moltenfist, Shadowforge };
inline constexpr std::array<uint32, 4> SouthKillOrder{ Angerforge, Thaurissan,
    Burningeye, Ironstar };

inline constexpr float ThunderclapRadius = 20.0f;
inline constexpr float ChainJumpRadius = 12.5f;
inline constexpr float StandoffRadius = 30.0f;
inline constexpr float StandoffStepRad = 30.0f * Geometry::Pi / 180.0f;
// Ring candidates are scanned every 2 degrees.
inline constexpr float StandoffCandidateStepRad = 2.0f * Geometry::Pi / 180.0f;
// Slot gaps: 15.5 yd preferred (30 degrees at 30 yd), never under 12.75 yd
// while the room allows (Chain Lightning jumps 12.5 yd;
// 2 asin(12.5 / 60) = 24.2 degrees at 30 yd).
inline constexpr float StandoffPreferredGapYards = 15.5f;
inline constexpr float StandoffMinimumGapYards = 12.75f;
// Every slot keeps every engaged spirit in spell range.
inline constexpr float StandoffSpellRange = 40.0f;
// On the arena floor: the shields stand 47-50 yd from the arena centre and
// round 2-4 ranged stood up to 46 yd out.
inline constexpr float StandoffRoomRadius = 48.0f;
// Healers keep the tank in heal range (40 yd plus both reaches, about 43):
// every slot within HealReachYards of the living main tank, or, with none in
// the snapshot, of the pack centre less the TankBeyondPackYards a tank can
// stand beyond it.
inline constexpr float HealReachYards = 38.0f;
inline constexpr float TankBeyondPackYards = 5.0f;
// An idle spirit aggroes a level-85 player at 20 yd plus both combat reaches
// (3.375 + 1.5); keep 10 yd more.
inline constexpr float IdleSafeYards = 35.0f;
inline constexpr float StandoffTolerance = 4.0f;
// Inside this of an engaged spirit the next Thunderclap lands (no hitbox, a
// 1.5 yd margin): leave with survival priority.
inline constexpr float DangerRadius = ThunderclapRadius + 1.5f;
// Whirlwind (80652) pulses 80651 every second, 4 yd around the spirit (2D,
// no hitbox). A melee player within WhirlwindDangerYards of a whirlwinding
// spirit moves; the point it takes is WhirlwindHoldYards from its target and
// at least WhirlwindClearYards from every whirlwinding spirit, so it does
// not trigger again (hysteresis) and stays inside melee range.
inline constexpr uint32 WhirlwindAura = 80652;
inline constexpr float WhirlwindRadius = 4.0f;
inline constexpr float WhirlwindDangerYards = WhirlwindRadius + 0.75f;
inline constexpr float WhirlwindClearYards = WhirlwindRadius + 1.0f;
inline constexpr float WhirlwindHoldYards = 5.4f;
// creature_model_info 36437-36444 (every spirit): CombatReach 3.375.
inline constexpr float SpiritCombatReach = 3.375f;
inline constexpr float SpiritMeleeRange = PlayerCombatReach + SpiritCombatReach + 4.0f / 3.0f;

inline bool IsSpiritNode(std::string_view node)
{
    return node == NorthNode || node == SouthNode;
}

inline bool IsSpirit(uint32 entry)
{
    return std::find(NorthKillOrder.begin(), NorthKillOrder.end(), entry)
            != NorthKillOrder.end()
        || std::find(SouthKillOrder.begin(), SouthKillOrder.end(), entry)
            != SouthKillOrder.end();
}

struct Pack
{
    // Living spirits in combat, any group (a stray pull counts as danger).
    std::vector<ActorSnapshot const*> Engaged;
    // Living spirits not yet in combat (the other group): the standoff must
    // stay out of their aggro range.
    std::vector<ActorSnapshot const*> Idle;
    Vector3 Center;
};

inline Pack BuildPack(Blackboard const& board)
{
    Pack pack;
    float x = 0.0f;
    float y = 0.0f;
    // Spawn-group creatures are Hostiles; Summons too, like FindBoss.
    for (auto const* list : { &board.Hostiles, &board.Summons })
        for (ActorSnapshot const& hostile : *list)
        {
            if (!hostile.Alive || !IsSpirit(hostile.Entry))
                continue;
            if (!hostile.InCombat)
            {
                pack.Idle.push_back(&hostile);
                continue;
            }
            pack.Engaged.push_back(&hostile);
            x += hostile.Position.X;
            y += hostile.Position.Y;
        }
    if (!pack.Engaged.empty())
        pack.Center = { x / float(pack.Engaged.size()),
            y / float(pack.Engaged.size()), ArenaCenter.Z };
    return pack;
}

// First engaged, attackable spirit in this node's kill order, then any other
// engaged spirit (the other group's order) so a stray pull is still killed.
inline ActorSnapshot const* KillTarget(Pack const& pack, std::string_view node)
{
    auto const& primary = node == SouthNode ? SouthKillOrder : NorthKillOrder;
    auto const& secondary = node == SouthNode ? NorthKillOrder : SouthKillOrder;
    for (auto const* order : { &primary, &secondary })
        for (uint32 entry : *order)
            for (ActorSnapshot const* spirit : pack.Engaged)
                if (spirit->Entry == entry && spirit->Attackable)
                    return spirit;
    return nullptr;
}

// The pack's kill-order target for this snapshot, or empty (not a spirit
// node, nothing engaged). The route's shared focus defers to it on the
// spirit nodes (patch spirit_kill_order_focus.patch): the tank's native
// target there is its area-threat choice, not the kill order.
inline ObjectGuid OrderedKillTarget(Blackboard const& board)
{
    if (!IsSpiritNode(board.Route.NodeId))
        return ObjectGuid();
    ActorSnapshot const* target = KillTarget(BuildPack(board), board.Route.NodeId);
    return target ? target->Guid : ObjectGuid();
}

// Ranged and healers (anyone neither tank nor melee) in GUID order, dead
// included, so the half-circle slots do not shift when someone dies.
inline std::vector<ObjectGuid> StandoffOrder(Blackboard const& board, ObjectGuid tank)
{
    std::vector<ObjectGuid> order;
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid != tank && !IsTank(player) && !IsMelee(player))
            order.push_back(player.Guid);
    std::sort(order.begin(), order.end());
    return order;
}

// Where the healers must reach: the living main tank, else the pack centre.
struct HealReach
{
    Vector3 Anchor;
    float Yards = HealReachYards;
};

inline HealReach HealReachFor(Blackboard const& board, Pack const& pack, ObjectGuid tank)
{
    ActorSnapshot const* actor = tank.IsEmpty() ? nullptr : board.FindActor(tank);
    if (actor && actor->Alive)
        return { actor->Position, HealReachYards };
    return { pack.Center, HealReachYards - TankBeyondPackYards };
}

// On the arena floor: in the room (StandoffRoomRadius from the arena centre)
// and clear of the pillar holes in the navmesh.
inline bool OnStandoffFloor(Vector3 const& point)
{
    return Geometry::Distance2d(point, ArenaCenter) <= StandoffRoomRadius
        && ArenaFloor::Solid(point.X, point.Y);
}

// Safe from the spirits: IdleSafeYards from every idle one and outside every
// engaged one's Thunderclap (DangerRadius).
inline bool ClearOfSpirits(Pack const& pack, Vector3 const& point)
{
    for (ActorSnapshot const* spirit : pack.Idle)
        if (Geometry::Distance2d(spirit->Position, point) < IdleSafeYards)
            return false;
    for (ActorSnapshot const* spirit : pack.Engaged)
        if (Geometry::Distance2d(spirit->Position, point) < DangerRadius)
            return false;
    return true;
}

// A standoff point: on the floor, clear of the spirits, every engaged spirit
// within StandoffSpellRange and the heal anchor within its reach.
inline bool StandoffPointValid(Pack const& pack, HealReach const& reach, Vector3 const& point)
{
    if (!OnStandoffFloor(point) || !ClearOfSpirits(pack, point)
        || Geometry::Distance2d(point, reach.Anchor) > reach.Yards + 0.01f)
        return false;
    for (ActorSnapshot const* spirit : pack.Engaged)
        if (Geometry::Distance2d(spirit->Position, point) > StandoffSpellRange)
            return false;
    return true;
}

// Offsets (sorted nearest the facing first), at least `spacing` apart.
inline std::vector<float> PickApart(std::vector<float> const& nearFirst, std::size_t count,
    float spacing)
{
    std::vector<float> chosen;
    for (float offset : nearFirst)
    {
        if (chosen.size() >= count)
            break;
        if (std::all_of(chosen.begin(), chosen.end(), [offset, spacing](float other)
            {
                return std::fabs(Geometry::AngleDelta(offset, other)) >= spacing - 0.001f;
            }))
            chosen.push_back(offset);
    }
    return chosen;
}

// `count` offsets spread evenly across the widest contiguous run of valid
// scan steps: a whole number of steps apart, at most StandoffStepRad and at
// least `minimum`, the block as near the facing as the run allows. Empty
// when the widest run is too narrow.
inline std::vector<float> SpreadOverWidestArc(std::vector<bool> const& valid, std::size_t count,
    float minimum)
{
    int const steps = int(valid.size());
    int first = 0;
    while (first < steps && valid[std::size_t(first)])
        ++first;
    if (!count || first == steps)
        return {};
    // Runs as [start, start + length) in steps unwrapped past `first`.
    int bestStart = 0;
    int bestLength = 0;
    for (int index = first + 1; index <= first + steps; )
    {
        if (!valid[std::size_t(index % steps)])
        {
            ++index;
            continue;
        }
        int const start = index;
        while (index <= first + steps && valid[std::size_t(index % steps)])
            ++index;
        if (index - start > bestLength)
        {
            bestLength = index - start;
            bestStart = start;
        }
    }
    int const gaps = int(count) - 1;
    int const floorSteps = int(std::ceil(minimum / StandoffCandidateStepRad - 0.001f));
    int const ceilingSteps = int(std::lround(StandoffStepRad / StandoffCandidateStepRad));
    int spacing = gaps ? std::min(ceilingSteps, (bestLength - 1) / gaps) : 0;
    if (gaps && spacing < floorSteps)
        return {};
    int const block = spacing * gaps;
    int placed = bestStart;
    float placedMiss = std::numeric_limits<float>::max();
    for (int start = bestStart; start + block < bestStart + bestLength; ++start)
    {
        float const miss = std::fabs(Geometry::AngleDelta(
            (float(start) + float(block) / 2.0f) * StandoffCandidateStepRad, 0.0f));
        if (miss < placedMiss - 0.001f)
        {
            placedMiss = miss;
            placed = start;
        }
    }
    std::vector<float> offsets;
    for (int slot = 0; slot <= gaps; ++slot)
        offsets.push_back(Geometry::AngleDelta(float(placed + slot * spacing)
            * StandoffCandidateStepRad, 0.0f));
    return offsets;
}

// The most offsets `spacing` apart on the valid scan steps of one ring (a
// greedy sweep from just after an invalid step), then the `count` of them
// nearest the facing. Empty when the ring holds fewer than `count`.
inline std::vector<float> PackRing(std::vector<bool> const& valid, std::size_t count,
    float spacing)
{
    int const steps = int(valid.size());
    int first = 0;
    while (first < steps && valid[std::size_t(first)])
        ++first;
    std::vector<float> packed;
    float last = 0.0f;
    for (int scanned = 1; scanned <= steps; ++scanned)
    {
        // Unwrapped angle from the facing, increasing along the sweep.
        int const index = first + scanned;
        if (!valid[std::size_t(index % steps)])
            continue;
        float const angle = float(index) * StandoffCandidateStepRad;
        if (packed.empty() || angle - last >= spacing - 0.001f)
        {
            packed.push_back(angle);
            last = angle;
        }
    }
    if (packed.size() > 1 && packed.front() + Geometry::TwoPi - packed.back() < spacing - 0.001f)
        packed.pop_back();
    if (packed.size() < count)
        return {};
    // Any of them are far enough apart: keep the `count` nearest the facing.
    for (float& angle : packed)
        angle = Geometry::AngleDelta(angle, 0.0f);
    std::stable_sort(packed.begin(), packed.end(), [](float left, float right)
    {
        return std::fabs(left) < std::fabs(right) - 0.001f;
    });
    packed.resize(count);
    return packed;
}

// Greedy packings of `band`, StandoffMinimumGapYards apart: sweeping
// around the pack from 12 bearings (the first toward `facing`), across it
// from 8 directions, then outermost and innermost first. The first holding
// `count`, else the one holding the most.
inline std::vector<Vector3> PackBand(Pack const& pack, std::vector<Vector3> const& band,
    std::size_t count, float facing)
{
    std::vector<Vector3> best;
    std::vector<std::pair<float, Vector3>> order;
    for (int sweep = 0; sweep < 22 && best.size() < count; ++sweep)
    {
        order.clear();
        for (Vector3 const& point : band)
        {
            float key;
            if (sweep < 12)
            {
                key = Geometry::AngleDelta(Geometry::Bearing(pack.Center, point),
                    facing + float(sweep) * Geometry::Pi / 6.0f);
                if (key < 0.0f)
                    key += Geometry::TwoPi;
            }
            else if (sweep < 20)
            {
                float const direction = facing + float(sweep - 12) * Geometry::Pi / 4.0f;
                key = point.X * std::cos(direction) + point.Y * std::sin(direction);
            }
            else
                key = (sweep == 20 ? -1.0f : 1.0f) * Geometry::Distance2d(point, pack.Center);
            order.emplace_back(key, point);
        }
        std::stable_sort(order.begin(), order.end(), [](auto const& left, auto const& right)
        {
            return left.first < right.first;
        });
        std::vector<Vector3> taken;
        for (auto const& [key, point] : order)
        {
            if (taken.size() >= count)
                break;
            if (std::all_of(taken.begin(), taken.end(), [&point](Vector3 const& other)
                {
                    return Geometry::Distance2d(point, other) >= StandoffMinimumGapYards;
                }))
                taken.push_back(point);
        }
        if (taken.size() > best.size())
            best = std::move(taken);
    }
    return best;
}

// The standoff slots of the whole order, deterministic from the snapshot,
// sorted by angle and handed out in GUID order:
//   1. on the 30 yd ring, the valid points nearest the bearing toward the
//      arena centre, 30 degrees (15.5 yd) apart;
//   2. short of that, spread evenly across the widest valid arc of that
//      ring, 30 degrees apart down to 12.75 yd (26 degrees in 2 degree
//      steps; Chain Lightning jumps 12.5 yd);
//   3. short of that: the rings at 30, 33 and 27 yd, packed first 15.5 yd
//      apart, then 12.75 yd apart, the `count` nearest the facing;
//   4. a room too cramped for any ring (the pack dragged to a wall or
//      toward the idle pack): the valid points of a 1 yd grid around the
//      pack, packed 12.75 yd apart (PackBand); a room too cramped even for
//      that, the rest on the valid points farthest from those taken (never
//      a shared slot). With no valid point at all (two engaged spirits more
//      than 80 yd apart), from the 30 yd ring: its points on the floor and
//      clear of the spirits, else those on the floor, else any.
// Valid (StandoffPointValid): on the arena floor clear of pillar holes,
// 35 yd from every idle spirit, outside Thunderclap, within 40 yd (spell
// range) of every engaged spirit and within heal reach of the tank (38 yd,
// or 33 yd of the pack centre with no living tank). Round 5: the tank had
// dragged the north pack 14 yd south,
// the fixed half circle toward the arena centre put both healers 26 yd from
// the idle south pack and it joined the fight
// (validation_route_future_encounter_contamination).
inline std::vector<Vector3> StandoffSlots(Pack const& pack, HealReach const& reach,
    std::size_t count)
{
    std::vector<Vector3> slots;
    if (!count || pack.Engaged.empty())
        return slots;
    float facing = Geometry::Pi;
    if (Geometry::Distance2d(pack.Center, ArenaCenter) > 5.0f)
        facing = Geometry::Bearing(pack.Center, ArenaCenter);
    int const steps = int(std::lround(Geometry::TwoPi / StandoffCandidateStepRad));
    auto point = [&pack, facing](float radius, float offset)
    {
        return Geometry::PointAt(pack.Center, facing + offset, radius, ArenaCenter.Z);
    };
    auto scan = [&](float radius)
    {
        std::vector<bool> valid(std::size_t(steps), false);
        for (int step = 0; step < steps; ++step)
        {
            valid[std::size_t(step)] = StandoffPointValid(pack, reach,
                point(radius, float(step) * StandoffCandidateStepRad));
        }
        return valid;
    };
    auto finish = [&](float radius, std::vector<float> offsets)
    {
        std::sort(offsets.begin(), offsets.end());
        for (float offset : offsets)
            slots.push_back(point(radius, offset));
        return slots;
    };

    std::vector<bool> const home = scan(StandoffRadius);
    std::vector<float> nearFirst;
    for (int step = 0; step < steps; ++step)
        if (home[std::size_t(step)])
            nearFirst.push_back(Geometry::AngleDelta(float(step) * StandoffCandidateStepRad, 0.0f));
    std::stable_sort(nearFirst.begin(), nearFirst.end(), [](float left, float right)
    {
        float const a = std::fabs(left);
        float const b = std::fabs(right);
        return a < b - 0.001f || (std::fabs(a - b) <= 0.001f && left < right);
    });
    std::vector<float> preferred = PickApart(nearFirst, count, StandoffStepRad);
    if (preferred.size() == count)
        return finish(StandoffRadius, preferred);
    float const minimumStep = 2.0f * std::asin(StandoffMinimumGapYards / (2.0f * StandoffRadius));
    std::vector<float> spread = SpreadOverWidestArc(home, count, minimumStep);
    if (spread.size() == count)
        return finish(StandoffRadius, spread);

    std::array<float, 3> const radii{ StandoffRadius, StandoffRadius + 3.0f, StandoffRadius - 3.0f };
    std::array<std::vector<bool>, 3> const rings{ home, scan(radii[1]), scan(radii[2]) };
    for (float chord : { StandoffPreferredGapYards, StandoffMinimumGapYards })
        for (std::size_t ring = 0; ring < radii.size(); ++ring)
        {
            float const spacing = 2.0f * std::asin(chord / (2.0f * radii[ring]));
            std::vector<float> packed = PackRing(rings[ring], count, spacing);
            if (packed.size() == count)
                return finish(radii[ring], packed);
        }

    // Cramped: pack the valid band (a fixed 1 yd world grid), then fill from
    // it; with no valid point at all, from the home ring's best points.
    std::vector<Vector3> pool;
    float const band = StandoffSpellRange;
    for (float x = std::floor(pack.Center.X - band); x <= pack.Center.X + band; x += 1.0f)
        for (float y = std::floor(pack.Center.Y - band); y <= pack.Center.Y + band; y += 1.0f)
            if (StandoffPointValid(pack, reach, { x, y, ArenaCenter.Z }))
                pool.push_back({ x, y, ArenaCenter.Z });
    std::vector<Vector3> taken = PackBand(pack, pool, count, facing);
    for (int tier = 0; pool.empty() && tier < 3; ++tier)
        for (int step = 0; step < steps; ++step)
        {
            Vector3 const at = point(StandoffRadius, float(step) * StandoffCandidateStepRad);
            if (tier == 2 || (OnStandoffFloor(at) && (tier == 1 || ClearOfSpirits(pack, at))))
                pool.push_back(at);
        }
    while (taken.size() < count)
    {
        std::optional<Vector3> farthest;
        float farthestGap = -1.0f;
        for (Vector3 const& candidate : pool)
        {
            float gap = std::numeric_limits<float>::max();
            for (Vector3 const& other : taken)
                gap = std::min(gap, Geometry::Distance2d(candidate, other));
            if (gap > farthestGap + 0.001f)
            {
                farthestGap = gap;
                farthest = candidate;
            }
        }
        taken.push_back(*farthest);
    }
    // Angular order around the pack, as the other layouts.
    std::sort(taken.begin(), taken.end(), [&pack, facing](Vector3 const& left, Vector3 const& right)
    {
        return Geometry::AngleDelta(Geometry::Bearing(pack.Center, left), facing)
            < Geometry::AngleDelta(Geometry::Bearing(pack.Center, right), facing);
    });
    return taken;
}

// Every ranged bot of a snapshot gets the same layout, and in a cramped
// drag the cascade costs up to about 0.5 ms: keep the last few layouts per
// thread, keyed on every input bit for bit (the engaged and idle spirits'
// positions, the heal anchor and reach, the slot count), so a hit returns
// exactly what the cascade would.
struct StandoffSlotCache
{
    struct Entry
    {
        std::vector<uint32> Key;
        std::vector<Vector3> Slots;
    };
    std::array<Entry, 8> Entries;
    std::size_t Next = 0;
    // Cascade runs, for the tests.
    uint64 Misses = 0;
};

inline StandoffSlotCache& StandoffSlotCacheForThread()
{
    static thread_local StandoffSlotCache cache;
    return cache;
}

inline std::vector<Vector3> CachedStandoffSlots(Pack const& pack, HealReach const& reach,
    std::size_t count)
{
    std::vector<uint32> key;
    key.reserve(4 + 2 * (pack.Engaged.size() + pack.Idle.size()) + 3);
    auto push = [&key](float value)
    {
        uint32 bits;
        std::memcpy(&bits, &value, sizeof(bits));
        key.push_back(bits);
    };
    key.push_back(uint32(count));
    key.push_back(uint32(pack.Engaged.size()));
    key.push_back(uint32(pack.Idle.size()));
    for (auto const* list : { &pack.Engaged, &pack.Idle })
        for (ActorSnapshot const* spirit : *list)
        {
            push(spirit->Position.X);
            push(spirit->Position.Y);
        }
    push(reach.Anchor.X);
    push(reach.Anchor.Y);
    push(reach.Yards);
    StandoffSlotCache& cache = StandoffSlotCacheForThread();
    for (StandoffSlotCache::Entry const& entry : cache.Entries)
        if (!entry.Key.empty() && entry.Key == key)
            return entry.Slots;
    ++cache.Misses;
    StandoffSlotCache::Entry& entry = cache.Entries[cache.Next];
    cache.Next = (cache.Next + 1) % cache.Entries.size();
    entry.Key = std::move(key);
    entry.Slots = StandoffSlots(pack, reach, count);
    return entry.Slots;
}

inline std::optional<Vector3> StandoffSlot(Blackboard const& board, Pack const& pack,
    ObjectGuid tank, ObjectGuid self)
{
    std::vector<ObjectGuid> const order = StandoffOrder(board, tank);
    auto itr = std::find(order.begin(), order.end(), self);
    if (itr == order.end() || pack.Engaged.empty())
        return std::nullopt;
    std::vector<Vector3> const slots = CachedStandoffSlots(pack,
        HealReachFor(board, pack, tank), order.size());
    return slots[std::size_t(itr - order.begin())];
}

inline float NearestSpiritDistance(Pack const& pack, Vector3 const& point)
{
    float nearest = std::numeric_limits<float>::max();
    for (ActorSnapshot const* spirit : pack.Engaged)
        nearest = std::min(nearest, Geometry::Distance2d(spirit->Position, point));
    return nearest;
}

// Melee near a whirlwinding spirit. Nothing to do unless `self` is within
// WhirlwindDangerYards of one. Then: the point on the WhirlwindHoldYards
// ring around `target` (the spirit it hits) nearest to it that is at least
// WhirlwindClearYards from every whirlwinding spirit; with none, straight
// out from the whirlwinding spirits' centroid until clear of them all.
inline std::optional<MoveProposal> WhirlwindExit(Pack const& pack, ActorSnapshot const& self,
    ActorSnapshot const* target)
{
    std::vector<ActorSnapshot const*> whirling;
    bool danger = false;
    for (ActorSnapshot const* spirit : pack.Engaged)
        if (FindAura(*spirit, WhirlwindAura))
        {
            whirling.push_back(spirit);
            danger = danger || Geometry::Distance2d(spirit->Position, self.Position)
                < WhirlwindDangerYards;
        }
    if (!danger)
        return std::nullopt;
    auto clear = [&whirling](Vector3 const& point)
    {
        return std::all_of(whirling.begin(), whirling.end(), [&point](ActorSnapshot const* spirit)
        {
            return Geometry::Distance2d(spirit->Position, point) >= WhirlwindClearYards;
        });
    };
    if (target)
    {
        std::optional<Vector3> best;
        float bestDistance = 0.0f;
        for (int step = 0; step < 72; ++step)
        {
            Vector3 const point = Geometry::PointAt(target->Position,
                float(step) * Geometry::TwoPi / 72.0f, WhirlwindHoldYards, ArenaCenter.Z);
            float const distance = Geometry::Distance2d(point, self.Position);
            if (clear(point) && (!best || distance < bestDistance))
            {
                best = point;
                bestDistance = distance;
            }
        }
        if (best)
            return Survival(*best, "spirit_whirlwind_ring", 530.0f);
    }
    float x = 0.0f;
    float y = 0.0f;
    for (ActorSnapshot const* spirit : whirling)
    {
        x += spirit->Position.X;
        y += spirit->Position.Y;
    }
    Vector3 const centroid{ x / float(whirling.size()), y / float(whirling.size()), ArenaCenter.Z };
    float const bearing = Geometry::Distance2d(centroid, self.Position) > 0.1f
        ? Geometry::Bearing(centroid, self.Position) : Geometry::Bearing(centroid, ArenaCenter);
    for (float radius = WhirlwindHoldYards; radius <= 30.0f; radius += 0.5f)
    {
        Vector3 const point = Geometry::PointAt(centroid, bearing, radius, ArenaCenter.Z);
        if (clear(point))
            return Survival(point, "spirit_whirlwind_exit", 530.0f);
    }
    return std::nullopt;
}

inline std::optional<MoveProposal> StandoffMove(Blackboard const& board, Pack const& pack,
    ObjectGuid tank, ActorSnapshot const& self)
{
    std::optional<Vector3> const slot = StandoffSlot(board, pack, tank, self.Guid);
    if (!slot || Geometry::Distance2d(*slot, self.Position) <= StandoffTolerance)
        return std::nullopt;
    if (NearestSpiritDistance(pack, self.Position) < DangerRadius)
        return Survival(*slot, "spirit_thunderclap_exit", 520.0f);
    return Positioning(*slot, "spirit_ranged_standoff", 300.0f);
}
}

#endif
