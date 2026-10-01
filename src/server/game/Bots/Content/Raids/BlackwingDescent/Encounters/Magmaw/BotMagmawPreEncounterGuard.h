#ifndef TRINITY_BOT_MAGMAW_PRE_ENCOUNTER_GUARD_H
#define TRINITY_BOT_MAGMAW_PRE_ENCOUNTER_GUARD_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string_view>
#include <vector>

// Magmaw-specific pre-engagement guard (BWD 10N round 4).
//
// Round 3 never engaged Magmaw at its boss step: in all four runs the warlock's
// Felguard cast Felstorm (89751, 8-yard whirl) at the Drakonid Drudge spawn
// during bwd.magmaw.drudges and struck "Exposed Head of Magmaw" from 22.7-28
// yards of Magmaw's centre (~/.cache/r3pk/diag_r3.md, Q2). Native area
// targeting admits a unit whose combat reach overlaps the area radius, and the
// Magmaw parts are large: world DB creature_model_info gives Magmaw 41570
// CombatReach 15 and both Exposed Heads (42347 at ExposedHeadOfMagmawPos,
// 48270 at Magmaw's own position) CombatReach 18.75. The drudge home spawn
// (-298.8, -50.3) is 18.9 yards from Magmaw, so any area effect centred on a
// drudge at its spawn, or on a pet meleeing it, reaches the head.
//
// This guard is pure data: the caller supplies the living Magmaw parts it
// found (entry, position, runtime combat reach) and whether the boss is
// already engaged. It never moves, targets or casts; it only refuses.
namespace BotEncounter::MagmawPreEncounterGuard
{
constexpr std::string_view EncounterNode = "bwd.magmaw.encounter";

constexpr std::uint32_t BossEntry = 41570;
constexpr std::uint32_t ExposedHeadEntry = 42347;
constexpr std::uint32_t ExposedHeadMirrorEntry = 48270;
constexpr std::uint32_t PincerLeftEntry = 41620;
constexpr std::uint32_t PincerRightEntry = 41789;

// A pet (and a melee bot) stands within nominal melee range of the unit it
// attacks, so a self-centred whirl can be carried up to that far from the
// target's position before the cast lands. 5 yards is NOMINAL_MELEE_RANGE: a
// bot execution tolerance, not an encounter value.
constexpr float ChaseMargin = 5.0f;

inline bool IsMagmawPartEntry(std::uint32_t entry)
{
    return entry == BossEntry || entry == ExposedHeadEntry
        || entry == ExposedHeadMirrorEntry || entry == PincerLeftEntry
        || entry == PincerRightEntry;
}

struct Point
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
};

struct Part
{
    std::uint32_t Entry = 0;
    Point Position;
    float CombatReach = 0.0f;
    bool Alive = true;
};

enum class Verdict : std::uint8_t
{
    Allowed,
    ForbiddenDirectTarget,
    ForbiddenAreaReach
};

struct Decision
{
    Verdict Result = Verdict::Allowed;
    std::string_view Reason;
    std::uint32_t PartEntry = 0;

    bool Forbidden() const { return Result != Verdict::Allowed; }
};

// Active until Magmaw is engaged. Once the boss is in combat the pull has
// happened (lawfully at the encounter step, or as route contamination that the
// harness reports separately), and refusing to fight back only wipes the raid.
inline bool GuardActive(bool magmawEngaged)
{
    return !magmawEngaged;
}

// Direct offense on a Magmaw part is allowed only at the boss step: there the
// adaptive strategy's designated pull tank opens deliberately.
inline Decision EvaluateDirectTarget(std::string_view routeNodeId,
    bool magmawEngaged, std::uint32_t targetEntry)
{
    if (!GuardActive(magmawEngaged) || !IsMagmawPartEntry(targetEntry)
        || routeNodeId == EncounterNode)
        return {};
    return { Verdict::ForbiddenDirectTarget,
        "magmaw_part_target_before_boss_step", targetEntry };
}

inline float Distance3d(Point const& left, Point const& right)
{
    float const dx = left.X - right.X;
    float const dy = left.Y - right.Y;
    float const dz = left.Z - right.Z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

// An area effect of `areaRadius` centred on any of `centers` reaches a part
// when the centre lies inside radius + the part's combat reach (the native
// area check) plus the chase margin. Before the pull no bot or pet area effect
// may reach an un-engaged Magmaw part, at any route node including the boss
// step's prepull: the pull is the designated tank's single-target opener.
inline Decision EvaluateAreaReach(bool magmawEngaged,
    std::vector<Point> const& centers, float areaRadius,
    std::vector<Part> const& parts)
{
    if (!GuardActive(magmawEngaged) || areaRadius < 0.0f)
        return {};
    for (Part const& part : parts)
    {
        if (!part.Alive || !IsMagmawPartEntry(part.Entry))
            continue;
        float const reach = areaRadius + std::max(part.CombatReach, 0.0f)
            + ChaseMargin;
        for (Point const& center : centers)
            if (Distance3d(center, part.Position) <= reach)
                return { Verdict::ForbiddenAreaReach,
                    "magmaw_part_in_area_reach_before_pull", part.Entry };
    }
    return {};
}
}

#endif
