#ifndef TRINITY_BOT_SPELL_CAST_TARGET_H
#define TRINITY_BOT_SPELL_CAST_TARGET_H

#include "CellImpl.h"
#include "Creature.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "Unit.h"

#include <algorithm>

// A spell's explicit unit target, for bot decisions: what
// `spell->m_targets.GetUnitTarget()` returned, but only while that unit is
// alive as an object.
//
// SpellCastTargets caches the target as a raw pointer that only
// Spell::UpdatePointers() refreshes from the target GUID (Spell::update, cast
// and delayed handling). Bot decisions run in the world update before the
// tick's map update, so the cached pointer can name a unit that was deleted
// since the spell last refreshed it (a creature removed at the end of the
// previous map update, a player logged out). Reading such a pointer is a
// use-after-free; the round-4 `.botauto stop` SIGSEGV went through the same
// cache (patch 0001).
//
// UnitTarget(spell) returns the cached pointer when one of these proves the
// object alive, and nullptr otherwise. The cached pointer itself is compared,
// never dereferenced:
//  - it is the caster itself;
//  - it is the unit with the target GUID in the caster's map (a unit in world;
//    GUIDs are unique, so no other live object has that GUID there);
//  - it is the connected player with that GUID, on any map or in far-teleport
//    transit (ObjectAccessor holds a Player from login until it is deleted);
//  - it is a creature with that GUID still resident in the caster's map grid
//    after leaving the world (the map's remove list, deleted at its next
//    DelayedUpdate: a pet dismissed, a summon unsummoned, a despawn earlier in
//    the same bot pass).
// Every live unit a current spell can target is one of these while its caster
// has a map; the grid search covers the longest player spell range (100 yd,
// plus a tick of caster movement) or the visibility range, whichever is
// larger. Two live cases are left:
//  - a creature on another map than the caster, which only a far teleport
//    that kept the spell (TELE_TO_SPELL) can produce; bot decisions only read
//    current spells of in-world bots and their pets and controlled units;
//  - a remove-list creature farther than the search radius, for the one tick
//    before its map deletes it. Only Auto Shot (75) stays current out of range
//    (Unit::_UpdateAutoRepeatSpell keeps it on a range failure), so it needs a
//    hunter more than the radius from its Auto Shot target at the moment the
//    target leaves the world; the decision sees no target for that tick.
namespace BotSpellCastTarget
{
constexpr float ResidentSearchMinimumYards = 105.0f;

struct ResidentCreatureSearch
{
    WorldObject const* Cached = nullptr;
    ObjectGuid Guid;
    Unit* Found = nullptr;

    void Visit(GridRefManager<Creature>& creatures)
    {
        for (GridRefManager<Creature>::iterator itr = creatures.begin();
            !Found && itr != creatures.end(); ++itr)
            if (Creature* creature = itr->GetSource();
                creature == Cached && creature->GetGUID() == Guid)
                Found = creature;
    }

    template <class NotSearched>
    void Visit(GridRefManager<NotSearched>&) { }
};

inline Unit* UnitTarget(Spell const* spell)
{
    if (!spell)
        return nullptr;
    WorldObject* const cached = spell->m_targets.GetObjectTarget();
    // Empty for a game object, corpse or no object target: GetUnitTarget()
    // returned nullptr for those too.
    ObjectGuid const guid = spell->m_targets.GetUnitTargetGUID();
    WorldObject* const caster = spell->GetCaster();
    if (!cached || guid.IsEmpty() || !caster)
        return nullptr;
    if (guid == caster->GetGUID())
        return cached == caster ? caster->ToUnit() : nullptr;

    Map* const map = caster->FindMap();
    if (map)
        if (Unit* resolved = ObjectAccessor::GetUnit(*caster, guid))
            return resolved == cached ? resolved : nullptr;
    if (guid.IsPlayer())
    {
        Player* const player = ObjectAccessor::FindConnectedPlayer(guid);
        return player && static_cast<WorldObject*>(player) == cached ? player : nullptr;
    }
    if (!map)
        return nullptr;
    ResidentCreatureSearch search;
    search.Cached = cached;
    search.Guid = guid;
    Cell::VisitAllObjects(caster, search,
        std::max(caster->GetVisibilityRange(), ResidentSearchMinimumYards));
    return search.Found;
}
}

#endif
