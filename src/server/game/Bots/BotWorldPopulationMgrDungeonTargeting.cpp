#include "Bots/BotWorldPopulationMgr.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Map.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace
{
float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;
    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
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
}

bool BotWorldPopulationMgr::IsDungeonTrashContext(Player* bot, Unit const* target) const
{
    if (!Cohort().Config.AllowDungeons || !bot || !bot->GetMap() || !bot->GetMap()->IsNonRaidDungeon())
        return false;

    if (target && target->IsAlive())
        if (Creature const* creature = target->ToCreature())
            return !creature->IsDungeonBoss();

    return bot->GetGroup() != nullptr || bot->IsInCombat();
}

Player* BotWorldPopulationMgr::FindDungeonAnchor(Player* bot) const
{
    if (!bot)
        return nullptr;

    auto findCohortAnchor = [this, bot]() -> Player*
    {
        for (WorldBotState const& state : Party().Bots)
        {
            Player* member = GetBot(state);
            if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;

            if (std::string(GetDungeonRole(member)) == "tank")
                return member;
        }

        for (WorldBotState const& state : Party().Bots)
        {
            Player* member = GetBot(state);
            if (member && member != bot && member->IsAlive() && member->GetMap() == bot->GetMap())
                return member;
        }

        return nullptr;
    };

    Group* group = bot->GetGroup();
    if (!group)
        return findCohortAnchor();

    for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
    {
        Player* member = itr->GetSource();
        if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap())
            continue;

        if (std::string(GetDungeonRole(member)) == "tank")
            return member;
    }

    ObjectGuid leaderGuid = group->GetLeaderGUID();
    for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
    {
        Player* member = itr->GetSource();
        if (member && member != bot && member->GetGUID() == leaderGuid && member->IsAlive() && member->GetMap() == bot->GetMap())
            return member;
    }

    for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
    {
        Player* member = itr->GetSource();
        if (member && member != bot && member->IsAlive() && member->GetMap() == bot->GetMap())
            return member;
    }

    return findCohortAnchor();
}

Unit* BotWorldPopulationMgr::FindGroupCombatTarget(Player* bot, Player* anchor) const
{
    if (!bot)
        return nullptr;

    auto usableTarget = [bot](Unit* target) -> Unit*
    {
        if (!target || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
            return nullptr;
        if (Creature* creature = target->ToCreature())
            if (creature->IsDungeonBoss())
                return nullptr;
        return target;
    };

    if (Unit* target = usableTarget(anchor ? anchor->GetVictim() : nullptr))
        return target;

    if (Group* group = bot->GetGroup())
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;

            if (Unit* target = usableTarget(member->GetVictim()))
                return target;
        }
    }

    return usableTarget(bot->GetVictim());
}

BotWorldPopulationMgr::DungeonTrashPackFeatures BotWorldPopulationMgr::BuildDungeonTrashPackFeatures(Player* bot, Unit const* focus) const
{
    DungeonTrashPackFeatures pack;
    if (!bot)
        return pack;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 35.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 35.0f);

    float bestScore = -1.0f;
    for (WorldObject* object : objects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || !creature->IsAlive() || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
            continue;
        if (creature->IsDungeonBoss())
            continue;

        float distance = bot->GetExactDist(creature);
        if (distance > 30.0f)
            pack.PatrolNearby = true;
        if (distance > 25.0f && creature != focus)
            continue;

        ++pack.PackSize;
        if (creature->isElite())
            ++pack.EliteCount;
        if (creature->GetMaxPower(POWER_MANA) > 0)
            ++pack.CasterCount;

        uint32 castSpellId = 0;
        bool dangerousCast = false;
        if (Spell* spell = creature->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        {
            SpellInfo const* spellInfo = spell->GetSpellInfo();
            castSpellId = spellInfo ? spellInfo->Id : 0;
            ++pack.ActiveCasts;
            if (SpellLooksLikeHeal(spellInfo))
                ++pack.HealerCount;
            dangerousCast = SpellLooksDangerous(spellInfo) || SpellLooksLikeHeal(spellInfo);
            if (dangerousCast)
                ++pack.DangerousCasts;
        }

        float score = 100.0f - distance;
        if (creature == focus)
            score += 100.0f;
        if (dangerousCast)
            score += 80.0f;
        if (castSpellId)
            score += 30.0f;
        if (creature->GetVictim() == bot)
            score += 20.0f;

        if (score > bestScore)
        {
            bestScore = score;
            pack.PriorityTargetGuid = creature->GetGUID();
            pack.PriorityTargetEntry = creature->GetEntry();
            pack.PrioritySpellId = castSpellId;
        }
    }

    pack.InterruptPriority = pack.PackSize ? std::min(1.0f, float(pack.DangerousCasts) / float(pack.PackSize) + (pack.HealerCount ? 0.35f : 0.0f)) : 0.0f;
    pack.AoeValue = std::min(1.0f, float(pack.PackSize) / 5.0f);
    pack.CcValue = std::min(1.0f, float(pack.CasterCount + pack.HealerCount) / 4.0f);
    pack.PullRisk = std::min(1.0f, float(pack.PackSize + pack.EliteCount) / 7.0f + (pack.PatrolNearby ? 0.2f : 0.0f));

    if (Group* group = bot->GetGroup())
    {
        float totalHp = 0.0f;
        uint32 memberCount = 0;
        float healerManaTotal = 0.0f;
        uint32 healerCount = 0;
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != bot->GetMap())
                continue;

            float hp = UnitHealthPct(member);
            totalHp += hp;
            pack.LowestAllyHpPct = memberCount ? std::min(pack.LowestAllyHpPct, hp) : hp;
            ++memberCount;

            if (std::string(GetDungeonRole(member)) == "healer")
            {
                uint32 maxMana = member->GetMaxPower(POWER_MANA);
                healerManaTotal += maxMana ? float(member->GetPower(POWER_MANA)) / float(maxMana) : 1.0f;
                ++healerCount;
            }
        }

        if (memberCount)
            pack.PartyAverageHpPct = totalHp / float(memberCount);
        if (healerCount)
            pack.HealerManaPct = healerManaTotal / float(healerCount);
    }
    else
    {
        pack.PartyAverageHpPct = UnitHealthPct(bot);
        pack.LowestAllyHpPct = pack.PartyAverageHpPct;
    }

    Player* anchor = FindDungeonAnchor(bot);
    Unit* focusMutable = focus ? const_cast<Unit*>(focus) : nullptr;
    if (anchor && focusMutable && focusMutable->GetVictim() == anchor)
        pack.TankThreat = 1.0f;
    else if (focusMutable && focusMutable->GetVictim() == bot && std::string(GetDungeonRole(bot)) == "tank")
        pack.TankThreat = 1.0f;
    else if (focusMutable && focusMutable->GetVictim())
        pack.TankThreat = 0.35f;

    return pack;
}

