#include "Bots/BotWorldPopulationMgr.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GameObject.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "GroupReference.h"
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

}

bool BotWorldPopulationMgr::IsBossContext(Player* bot, Unit const* target) const
{
    if (!bot || !bot->GetMap())
        return false;

    bool eligibleMap = (Cohort().Config.AllowDungeons && bot->GetMap()->IsNonRaidDungeon()) || (Cohort().Config.AllowRaids && bot->GetMap()->IsRaid());
    if (!eligibleMap)
        return false;

    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        if (creature->IsDungeonBoss() || creature->isWorldBoss())
            return true;

    return bot->IsInCombat() && FindBossTarget(bot) != nullptr;
}

Unit* BotWorldPopulationMgr::FindBossTarget(Player* bot) const
{
    if (!bot || !bot->GetMap())
        return nullptr;

    auto usableBoss = [bot](Unit* target) -> Unit*
    {
        if (!target || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
            return nullptr;

        Creature* creature = target->ToCreature();
        if (!creature || (!creature->IsDungeonBoss() && !creature->isWorldBoss()))
            return nullptr;

        return target;
    };

    if (Unit* target = usableBoss(bot->GetVictim()))
        return target;

    if (Group* group = bot->GetGroup())
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;

            if (Unit* target = usableBoss(member->GetVictim()))
                return target;
        }
    }

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 60.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 60.0f);

    Unit* best = nullptr;
    float bestDistance = 0.0f;
    for (WorldObject* object : objects)
    {
        Unit* unit = object ? object->ToUnit() : nullptr;
        Unit* boss = usableBoss(unit);
        if (!boss)
            continue;

        float distance = bot->GetExactDist(boss);
        if (!best || distance < bestDistance)
        {
            best = boss;
            bestDistance = distance;
        }
    }

    return best;
}

BotWorldPopulationMgr::BossMechanicFeatures BotWorldPopulationMgr::BuildBossMechanicFeatures(Player* bot, Unit const* boss) const
{
    BossMechanicFeatures features;
    if (!bot)
        return features;

    features.RaidEncounter = bot->GetMap() && bot->GetMap()->IsRaid();
    features.BossPresent = boss != nullptr;
    if (boss)
    {
        features.BossGuid = boss->GetGUID();
        if (Creature const* creature = boss->ToCreature())
            features.BossEntry = creature->GetEntry();
    }

    SpellInfo const* castInfo = nullptr;
    if (boss)
    {
        if (Spell* spell = const_cast<Unit*>(boss)->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        {
            castInfo = spell->GetSpellInfo();
            features.BossCasting = castInfo != nullptr;
            features.CastSpellId = castInfo ? castInfo->Id : 0;
            features.CastRemainingMs = spell->GetRemainingCastTime();
        }
    }

    features.DangerousCast = SpellLooksDangerous(castInfo) || SpellLooksLikeHeal(castInfo);
    features.GroundDanger = SpellLooksLikeGroundDanger(castInfo);
    features.MoveOut = features.GroundDanger;
    features.RaidDamage = SpellLooksRaidWide(castInfo);
    features.TankSpike = SpellLooksTankSpike(castInfo);
    features.AddsActive = SpellLooksLikeSummonOrAdds(castInfo);
    features.MustInterrupt = castInfo && features.DangerousCast && castInfo->CanBeInterrupted(boss, false);
    features.InterruptPriority = features.MustInterrupt ? 1.0f : (features.DangerousCast && features.BossCasting ? 0.45f : 0.0f);

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 45.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 45.0f);

    float bestAddScore = -1.0f;
    for (WorldObject* object : objects)
    {
        if (GameObject* gameObject = object ? object->ToGameObject() : nullptr)
        {
            if (gameObject->IsTransport())
            {
                features.TransportObserved = true;
                if (features.TransportGuid.IsEmpty())
                    features.TransportGuid = gameObject->GetGUID();
            }
            else if (gameObject->IsAtInteractDistance(bot))
            {
                ++features.InteractableCount;
                features.InteractableObserved = true;
                if (features.InteractableGuid.IsEmpty())
                    features.InteractableGuid = gameObject->GetGUID();
            }
            continue;
        }

        if (Unit* unit = object ? object->ToUnit() : nullptr)
            if (unit != bot && unit->IsVehicle())
            {
                ++features.VehicleCount;
                features.VehicleObserved = true;
                if (features.VehicleGuid.IsEmpty())
                    features.VehicleGuid = unit->GetGUID();
            }

        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || !creature->IsAlive() || creature == boss || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
            continue;
        if (creature->IsDungeonBoss() || creature->isWorldBoss())
            continue;

        ++features.AddCount;
        features.AddsActive = true;
        float score = 45.0f - bot->GetExactDist(creature);
        if (creature->GetVictim() == bot)
            score += 20.0f;
        if (creature->isElite())
            score += 10.0f;
        if (score > bestAddScore)
        {
            bestAddScore = score;
            features.PriorityAddGuid = creature->GetGUID();
        }
    }

    features.PlatformTransferObserved = features.VehicleObserved || features.TransportObserved;

    if (Group* group = bot->GetGroup())
    {
        float totalHp = 0.0f;
        uint32 memberCount = 0;
        float healerManaTotal = 0.0f;
        uint32 healerCount = 0;
        float tankHp = 1.0f;
        bool tankSeen = false;
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != bot->GetMap())
                continue;

            float hp = UnitHealthPct(member);
            totalHp += hp;
            features.LowestAllyHpPct = memberCount ? std::min(features.LowestAllyHpPct, hp) : hp;
            ++memberCount;

            std::string memberRole = GetDungeonRole(member);
            if (memberRole == "tank")
            {
                tankHp = hp;
                tankSeen = true;
            }
            if (memberRole == "healer")
            {
                uint32 maxMana = member->GetMaxPower(POWER_MANA);
                healerManaTotal += maxMana ? float(member->GetPower(POWER_MANA)) / float(maxMana) : 1.0f;
                ++healerCount;
            }
        }

        if (memberCount)
            features.PartyAverageHpPct = totalHp / float(memberCount);
        if (tankSeen)
            features.TankHpPct = tankHp;
        if (healerCount)
            features.HealerManaPct = healerManaTotal / float(healerCount);
    }
    else
    {
        features.PartyAverageHpPct = UnitHealthPct(bot);
        features.LowestAllyHpPct = features.PartyAverageHpPct;
        features.TankHpPct = features.PartyAverageHpPct;
    }

    if (features.RaidDamage && features.LowestAllyHpPct < 0.55f)
        features.StackPlaceholder = true;
    if (features.GroundDanger || features.RaidDamage)
        features.SpreadPlaceholder = true;

    features.DangerScore = std::min(1.0f,
        (features.MustInterrupt ? 0.35f : 0.0f)
        + (features.GroundDanger ? 0.25f : 0.0f)
        + (features.RaidDamage ? 0.20f : 0.0f)
        + (features.TankSpike ? 0.15f : 0.0f)
        + (features.AddsActive ? std::min(0.20f, float(features.AddCount) * 0.05f) : 0.0f)
        + (features.LowestAllyHpPct < 0.4f ? 0.20f : 0.0f));

    return features;
}


