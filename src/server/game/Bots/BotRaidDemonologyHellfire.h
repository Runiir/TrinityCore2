#ifndef TRINITY_BOT_RAID_DEMONOLOGY_HELLFIRE_H
#define TRINITY_BOT_RAID_DEMONOLOGY_HELLFIRE_H

#include "Define.h"
#include "Position.h"

#include <cmath>

// Canonical-composition raid Demonology warlocks only (BotCanonicalRaidScope.h):
// when Hellfire (1949, a 15 s channel hitting every enemy within 10 yd of the
// warlock and burning the warlock itself) may start and when it stops.
//
// The pinned row admits Hellfire with three enemies within 12 yd of the
// warlock's target, not of the warlock, and nothing ends the channel. BWD 10N
// round 3 (label blackwing_descent_10n-r03-a3864fcf6d), Maloriak batch
// 35b93d, 61-74 s: the warlock kept channelling for up to 13 s after the
// kited Aberration pack left its radius, damaging only itself; cd3009 70-80 s:
// no warlock or Felguard damage on any enemy while the warlock burned itself.
//
// Start: at least StartEnemies engaged enemies inside the warlock's own
// radius. Stop: fewer than KeepEnemies remain inside it, the way a player
// cancels the channel. The gap between the two keeps a pack that thins by one
// burning and cannot flip a start straight into a stop.
//
// "Inside the radius" is the native target geometry of the damage spell, not
// a size-aware reach. Each second the channel (an aura trigger on the warlock)
// casts Hellfire Effect 5857: TargetA TARGET_DEST_CASTER, TargetB
// TARGET_UNIT_DEST_AREA_ENEMY, radius index 13 (10 yd). Its enemies come from
// Spell::SearchAreaTargets -> WorldObjectSpellAreaTargetCheck, which tests the
// target's centre against a cylinder around the destination: 2D distance
// below the radius and a height difference of at most the radius. The
// combat-reach term (target->GetMeleeRange(caster)) is added only when the
// spell has SPELL_ATTR5_TREAT_AS_AREA_EFFECT (0x8000) and a non-generic spell
// family; the 4.3.4 DBC row of 5857 has AttributesEx5 0x40000000 (and is
// SPELLFAMILY_WARLOCK), so nothing is added. Three adds 12 yd away with 1.5 yd
// combat reaches are outside it (a size-aware test, IsWithinDistInMap, would
// admit them out to 13 yd and let Hellfire burn only the warlock).
namespace BotRaidDemonologyHellfire
{
inline constexpr uint32 Hellfire = 1949;
// The damage spell the channel triggers every second.
inline constexpr uint32 DamageSpell = 5857;
inline constexpr float Radius = 10.0f;
inline constexpr uint32 StartEnemies = 3;
inline constexpr uint32 KeepEnemies = 2;
inline constexpr char const* StartRejectReason = "hellfire_radius_enemy_count";
inline constexpr char const* StopReason = "hellfire_radius_emptied";

// Whether the damage spell hits an enemy standing at enemy while the warlock
// stands at warlock: WorldObjectSpellAreaTargetCheck for a unit, without the
// area-effect hitbox term (see above), through the same native Position
// helper (WorldObject::IsWithinDist2d is Position::IsInDist2d).
inline bool InDamageArea(Position const& warlock, Position const& enemy)
{
    return enemy.IsInDist2d(&warlock, Radius)
        && std::abs(enemy.GetPositionZ() - warlock.GetPositionZ()) <= Radius;
}

inline bool StartAllowed(uint32 enemiesInRadius)
{
    return enemiesInRadius >= StartEnemies;
}

inline bool ShouldStop(uint32 channelSpellId, uint32 enemiesInRadius)
{
    return channelSpellId == Hellfire && enemiesInRadius < KeepEnemies;
}
}

#endif
