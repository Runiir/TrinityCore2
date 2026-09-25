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
// the fight turns into. Spell rows (4.3.4 DBC):
//   Thunderclap 80649 (Moltenfist): 15 yd around the caster, only while its
//     victim is in melee range, every 6-8 s.
//   Chain Lightning 80646 (Shadowforge): random target within 90 yd,
//     8 targets, magic chain (12.5 yd jumps), every 10-11 s.
//   Stormbolt 80648 (Anvilrage): random target within 30 yd, 8 yd splash
//     with a stun, every 19-23 s.
//   Burden of the Crown 80718 (Corehammer): on its victim, +100% damage done
//     and no power cost, a 13.9k self-hit on each hit (80722).
//   Whirlwind 80652 (Burningeye), Avatar 80645 (Thaurissan; Angerforge's
//     Bestowal also grants Avatar in the native script), Stoneblood 80655
//     (Angerforge), Shield of Light 80747 then Execution Sentence 80727 on
//     the victim (Ironstar).
// Plan:
//   - kill order: the ability least harmful to hand on first, the one never
//     to hand on last. North (Icy Veins): Corehammer (Burden then buffs the
//     raid), Anvilrage, Moltenfist, Shadowforge. South (no readable source
//     yet): Angerforge, Thaurissan, Burningeye, Ironstar;
//   - ranged and healers stand on a half circle 26 yd from the engaged pack,
//     toward the arena centre: outside every Thunderclap (15 yd + 1.5 reach)
//     and 13 yd apart, so Chain Lightning does not jump between them;
//   - the tank and melee are left to native tanking and melee range.
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

inline constexpr float ThunderclapRadius = 15.0f;
inline constexpr float ChainJumpRadius = 12.5f;
inline constexpr float StandoffRadius = 26.0f;
inline constexpr float StandoffStepRad = 30.0f * Geometry::Pi / 180.0f;
inline constexpr float StandoffTolerance = 4.0f;
// Inside this of an engaged spirit the next Thunderclap lands: leave with
// survival priority.
inline constexpr float DangerRadius = ThunderclapRadius + PlayerCombatReach + 1.5f;

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
