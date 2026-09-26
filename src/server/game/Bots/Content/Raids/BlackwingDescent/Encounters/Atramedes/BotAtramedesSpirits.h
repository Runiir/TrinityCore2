#ifndef TRINITY_BOT_ATRAMEDES_SPIRITS_H
#define TRINITY_BOT_ATRAMEDES_SPIRITS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesMovementPolicy.h"
#include <algorithm>
#include <array>
#include <limits>
#include <optional>
#include <string_view>
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
//   - ranged and healers stand on a half circle 30 yd from the engaged pack,
//     toward the arena centre: outside every Thunderclap (20 yd, with a
//     1.5 yd margin) and 15.5 yd apart, so Chain Lightning (12.5 yd jumps)
//     does not jump between them;
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
    Vector3 Center;
};

inline Pack BuildPack(Blackboard const& board)
{
    Pack pack;
    float x = 0.0f;
    float y = 0.0f;
    for (ActorSnapshot const& hostile : board.Hostiles)
        if (hostile.Alive && hostile.InCombat && IsSpirit(hostile.Entry))
        {
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

inline std::optional<Vector3> StandoffSlot(Blackboard const& board, Pack const& pack,
    ObjectGuid tank, ObjectGuid self)
{
    std::vector<ObjectGuid> const order = StandoffOrder(board, tank);
    auto itr = std::find(order.begin(), order.end(), self);
    if (itr == order.end() || pack.Engaged.empty())
        return std::nullopt;
    float facing = Geometry::Pi;
    if (Geometry::Distance2d(pack.Center, ArenaCenter) > 5.0f)
        facing = Geometry::Bearing(pack.Center, ArenaCenter);
    float const offset = (float(itr - order.begin()) - float(order.size() - 1) / 2.0f)
        * StandoffStepRad;
    return Geometry::PointAt(pack.Center, facing + offset, StandoffRadius, ArenaCenter.Z);
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
