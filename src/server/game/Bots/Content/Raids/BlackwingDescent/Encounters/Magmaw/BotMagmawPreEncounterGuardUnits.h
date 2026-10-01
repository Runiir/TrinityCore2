#ifndef TRINITY_BOT_MAGMAW_PRE_ENCOUNTER_GUARD_UNITS_H
#define TRINITY_BOT_MAGMAW_PRE_ENCOUNTER_GUARD_UNITS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPreEncounterGuard.h"

#include "Creature.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <list>
#include <vector>

// World adapter for BotMagmawPreEncounterGuard: reads the living Magmaw parts
// around a caster and the native area radius of a spell. Read-only; the
// caller decides what to refuse (see the round-4 Magmaw handoff patch
// request for the Felguard Felstorm gate in BotActionExecutor.cpp).
namespace BotEncounter::MagmawPreEncounterGuard
{
// Search range around the caster. Magmaw's largest part reach (18.75) plus
// the largest area radius a bot or pet uses (Felstorm 8, Thunderclap-class
// 10-15) plus the chase margin stays far below this.
constexpr float PartSearchRange = 80.0f;

struct ObservedParts
{
    std::vector<Part> Parts;
    bool MagmawEngaged = false;
};

inline ObservedParts ObserveParts(WorldObject const* anchor)
{
    ObservedParts observed;
    if (!anchor)
        return observed;
    constexpr std::array<uint32, 5> Entries = { BossEntry, ExposedHeadEntry,
        ExposedHeadMirrorEntry, PincerLeftEntry, PincerRightEntry };
    for (uint32 entry : Entries)
    {
        std::list<Creature*> found;
        anchor->GetCreatureListWithEntryInGrid(found, entry, PartSearchRange);
        for (Creature const* creature : found)
        {
            if (!creature || !creature->IsAlive())
                continue;
            if (entry == BossEntry && creature->IsEngaged())
                observed.MagmawEngaged = true;
            observed.Parts.push_back({ entry,
                { creature->GetPositionX(), creature->GetPositionY(),
                    creature->GetPositionZ() },
                creature->GetCombatReach(), true });
        }
    }
    return observed;
}

// Largest hostile area radius of the spell, following one level of trigger
// spells (Felstorm 89751 is a channel whose periodic trigger carries the
// whirl radius). Returns a negative value when the spell has no area effect.
inline float HostileAreaRadius(SpellInfo const* spellInfo, WorldObject* caster)
{
    float radius = -1.0f;
    if (!spellInfo)
        return radius;
    auto scan = [&radius, caster](SpellInfo const* info)
    {
        for (uint8 index = 0; index < MAX_SPELL_EFFECTS; ++index)
        {
            SpellEffectInfo const& effect = info->Effects[index];
            if (!effect.IsEffect() || info->IsPositiveEffect(index))
                continue;
            if (effect.IsTargetingArea()
                || effect.IsEffect(SPELL_EFFECT_PERSISTENT_AREA_AURA)
                || effect.IsAreaAuraEffect())
                radius = std::max(radius, effect.CalcRadius(caster));
        }
    };
    scan(spellInfo);
    for (uint8 index = 0; index < MAX_SPELL_EFFECTS; ++index)
        if (uint32 trigger = spellInfo->Effects[index].TriggerSpell)
            if (SpellInfo const* triggered = sSpellMgr->GetSpellInfo(trigger))
                scan(triggered);
    return radius;
}

// True when `caster` (a bot or its pet) must not start the area spell now: an
// un-engaged Magmaw part lies within the spell's radius of the caster, or of
// the unit it is attacking (a pet follows its target while it whirls).
inline Decision EvaluateUnitArea(Unit* caster, Unit const* target,
    SpellInfo const* spellInfo)
{
    if (!caster)
        return {};
    float const radius = HostileAreaRadius(spellInfo, caster);
    if (radius < 0.0f)
        return {};
    ObservedParts const observed = ObserveParts(caster);
    if (observed.Parts.empty())
        return {};
    std::vector<Point> centers = { { caster->GetPositionX(),
        caster->GetPositionY(), caster->GetPositionZ() } };
    if (target && target != caster)
        centers.push_back({ target->GetPositionX(), target->GetPositionY(),
            target->GetPositionZ() });
    return EvaluateAreaReach(observed.MagmawEngaged, centers, radius,
        observed.Parts);
}
}

#endif
