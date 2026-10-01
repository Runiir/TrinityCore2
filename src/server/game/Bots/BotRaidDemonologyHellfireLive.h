#ifndef TRINITY_BOT_RAID_DEMONOLOGY_HELLFIRE_LIVE_H
#define TRINITY_BOT_RAID_DEMONOLOGY_HELLFIRE_LIVE_H

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidDemonologyHellfire.h"

#include "CellImpl.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "Unit.h"

#include <vector>

// The live side of BotRaidDemonologyHellfire.h: the engaged enemies inside
// the warlock's own Hellfire radius, and the channel the warlock runs.
namespace BotRaidDemonologyHellfire
{
// Living enemies the warlock may attack that are in combat or hold a victim,
// inside the damage spell's native target cylinder around the warlock
// (InDamageArea: 10 yd centre to centre, no combat reach). Both the start gate
// and the keep (stop) test count this way, so a pack that Hellfire would not
// hit never starts or sustains the channel. An un-engaged pack standing nearby
// is not counted, so the count never argues for pulling.
inline uint32 CountEngagedEnemiesInRadius(Player* warlock)
{
    if (!warlock || !warlock->IsInWorld())
        return 0;
    std::vector<WorldObject*> objects;
    // Only a pre-filter: the grid test is size-aware, so it reaches at least as
    // far as the native centre-distance cylinder; InDamageArea decides.
    float const searchRadius = Radius + 10.0f;
    Trinity::AllWorldObjectsInRange check(warlock, searchRadius);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
        warlock, objects, check);
    Cell::VisitAllObjects(warlock, searcher, searchRadius);
    uint32 count = 0;
    for (WorldObject* object : objects)
    {
        Unit* unit = object ? object->ToUnit() : nullptr;
        if (unit && unit != warlock && unit->IsAlive()
            && warlock->IsValidAttackTarget(unit)
            && (unit->IsInCombat() || unit->GetVictim())
            && warlock->IsInMap(unit) && warlock->IsInPhase(unit)
            && InDamageArea(*warlock, *unit))
            ++count;
    }
    return count;
}

// The start gate, applied to the resolver's candidates before admission: an
// otherwise open Hellfire row is rejected unless StartEnemies engaged enemies
// stand in the warlock's own radius. The grid search runs at most once, and
// only when such a row exists.
inline void RejectStartsWithoutPack(Player* warlock,
    std::vector<BotActionCandidate>& candidates)
{
    int64 enemies = -1;
    for (BotActionCandidate& candidate : candidates)
    {
        if (candidate.SpellId != Hellfire || !candidate.RejectReason.empty())
            continue;
        if (enemies < 0)
            enemies = CountEngagedEnemiesInRadius(warlock);
        if (!StartAllowed(uint32(enemies)))
            candidate.RejectReason = StartRejectReason;
    }
}

inline uint32 ChannelSpellId(Unit const* caster)
{
    Spell const* channel = caster
        ? caster->GetCurrentSpell(CURRENT_CHANNELED_SPELL) : nullptr;
    return channel && channel->GetSpellInfo() ? channel->GetSpellInfo()->Id : 0;
}
}

#endif
