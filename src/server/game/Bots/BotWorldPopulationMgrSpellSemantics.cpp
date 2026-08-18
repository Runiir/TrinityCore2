#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "CellImpl.h"
#include "Creature.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <chrono>
#include <sstream>
#include <vector>

namespace BotWorldPopulationMgrSpellSemantics
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

bool SpellLooksLikeHeal(SpellInfo const* spellInfo)
{
    return spellInfo && (spellInfo->HasEffect(SPELL_EFFECT_HEAL)
        || spellInfo->HasEffect(SPELL_EFFECT_HEAL_PCT)
        || spellInfo->HasEffect(SPELL_EFFECT_HEAL_MECHANICAL));
}

bool SpellLooksDangerous(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    return spellInfo->HasEffect(SPELL_EFFECT_SCHOOL_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL)
        || spellInfo->HasEffect(SPELL_EFFECT_NORMALIZED_WEAPON_DMG)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_PERCENT_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_POWER_DRAIN)
        || spellInfo->HasEffect(SPELL_EFFECT_HEALTH_LEECH);
}

bool SpellLooksLikeSummonOrAdds(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    return spellInfo->HasEffect(SPELL_EFFECT_SUMMON)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_PET)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_OBJECT_SLOT1)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_OBJECT_SLOT2)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_OBJECT_SLOT3)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_OBJECT_SLOT4)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_CHANGE_ITEM);
}

bool SpellLooksLikeGroundDanger(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    if (spellInfo->HasEffect(SPELL_EFFECT_PERSISTENT_AREA_AURA))
        return true;

    for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[i];
        if (!effect.IsEffect())
            continue;

        if ((effect.IsTargetingArea() || effect.CalcRadius() >= 4.0f)
            && (SpellLooksDangerous(spellInfo) || effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE))
            return true;
    }

    return false;
}

bool SpellLooksRaidWide(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    if (spellInfo->MaxAffectedTargets >= 4)
        return true;

    for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[i];
        if (!effect.IsEffect())
            continue;

        if ((effect.IsTargetingArea() || effect.CalcRadius() >= 12.0f) && SpellLooksDangerous(spellInfo))
            return true;
    }

    return false;
}

bool SpellLooksTankSpike(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    if (spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL)
        || spellInfo->HasEffect(SPELL_EFFECT_NORMALIZED_WEAPON_DMG)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_PERCENT_DAMAGE))
        return true;

    return SpellLooksDangerous(spellInfo) && !SpellLooksRaidWide(spellInfo);
}

uint32 SemanticMechanicKey(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = result && *result ? result : "ok";
    if (res.size() > 63)
        res.resize(63);
    if (event == "interrupt_success" || event == "interrupt_failed")
        return 2;
    if (event == "boss_mechanic" || res == "move_out")
        return 1;
    if (event == "boss_adds" || event == "boss_add_killed")
        return 5;
    if (event == "boss_heal")
        return 4;
    if (event == "boss_action" || event == "boss_started")
        return 11;
    if (event == "trash_action" || event == "trash_heal")
        return 10;
    if (event == "death")
        return 99;
    return 0;
}

char const* SemanticMechanicFamily(uint32 key)
{
    switch (key)
    {
        case 1: return "ground_danger";
        case 2: return "must_interrupt";
        case 4: return "raid_damage";
        case 5: return "adds";
        case 10: return "trash_pack";
        case 11: return "boss_pressure";
        case 99: return "death_failure";
        default: return "unknown";
    }
}

bool EventLooksSuccessful(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = result && *result ? result : "ok";
    if (res.size() > 63)
        res.resize(63);
    return res == "ok"
        || event == "mob_killed"
        || event == "boss_killed"
        || event == "quest_completed"
        || event == "objective_progress"
        || event == "gear_upgrade"
        || event == "gear_evaluated"
        || event == "interrupt_success";
}

bool EventLooksFailure(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = result && *result ? result : "ok";
    if (res.size() > 63)
        res.resize(63);
    return event == "death"
        || event == "repeated_death"
        || event == "stuck_detected"
        || event == "objective_failed"
        || event == "death_recovery_failed"
        || event == "interrupt_failed"
        || event == "teleport_fallback_used"
        || res == "failed"
        || res.find("failed") != std::string::npos
        || res.find("blocked") != std::string::npos;
}

std::string BuildSpellTagJson(SpellInfo const* spellInfo, bool mustInterrupt,
    bool groundDanger, bool tankSpike, bool raidDamage, bool adds)
{
    std::ostringstream tags;
    tags << "[";
    bool first = true;
    auto addTag = [&tags, &first](char const* tag)
    {
        if (!first)
            tags << ",";
        tags << "\"" << tag << "\"";
        first = false;
    };

    if (SpellLooksDangerous(spellInfo))
        addTag("direct_damage");
    if (groundDanger)
    {
        addTag("ground_effect");
        addTag("move_out");
    }
    if (mustInterrupt)
        addTag("must_interrupt");
    if (tankSpike)
        addTag("tank_spike");
    if (raidDamage)
        addTag("raid_damage");
    if (adds)
        addTag("add_wave");
    if (SpellLooksLikeHeal(spellInfo))
        addTag("boss_heal");

    tags << "]";
    return tags.str();
}

bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth)
{
    if (!spellInfo || depth > 4)
        return false;
    // Starfall's owner aura delegates hostile selection to triggered spells;
    // retain the explicit root as a conservative client-data semantic guard.
    if (spellInfo->Id == 48505 || spellInfo->Id == 89751)
        return true;
    for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[effectIndex];
        if (!effect.IsEffect())
            continue;
        if (!spellInfo->IsPositiveEffect(effectIndex)
            && (effect.ChainTarget > 1 || effect.IsTargetingArea()
                || effect.IsEffect(SPELL_EFFECT_PERSISTENT_AREA_AURA)
                || effect.IsAreaAuraEffect()))
            return true;
        if (effect.TriggerSpell
            && SpellHasHostileMultiTargetSemantics(sSpellMgr->GetSpellInfo(effect.TriggerSpell), depth + 1))
            return true;
    }
    return false;
}

// Future encounter protection must be geometry-aware. Keeping the global entry
// set is useful for route bookkeeping, but it must not suppress AoE on a
// current trash pack that is nowhere near the protected encounter.
bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target)
{
    if (!owner || !target || !BotRaidAreaAuthority::HasProtectedEncounterEntries(owner->GetGUID().GetRawValue()))
        return false;

    std::vector<WorldObject*> nearbyObjects;
    Trinity::AllWorldObjectsInRange check(target, 45.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
        target, nearbyObjects, check);
    Cell::VisitAllObjects(target, searcher, 45.0f);
    for (WorldObject* object : nearbyObjects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || creature == target || !creature->IsAlive()
            || !owner->IsValidAttackTarget(creature))
            continue;
        if (BotRaidAreaAuthority::IsProtectedEncounterTarget(
                owner->GetGUID().GetRawValue(), creature->GetEntry(),
                creature->GetSpawnId(), creature->GetGUID().GetRawValue()))
            return true;
    }
    return false;
}
}
