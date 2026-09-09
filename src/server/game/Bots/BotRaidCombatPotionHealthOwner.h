#ifndef TRINITY_BOT_RAID_COMBAT_POTION_HEALTH_OWNER_H
#define TRINITY_BOT_RAID_COMBAT_POTION_HEALTH_OWNER_H

#include "Bots/BotClassSpecActionProfile.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

namespace BotRaidCombatPotionHealthOwner
{
inline bool MeetsHostileTargetHealthGate(BotActionProfileSpell const& spell, Unit const* target,
    BotCombatPotionHealthOwner const& owner)
{
    bool const required = owner.Required && spell.TargetSelector == "self"
        && spell.Category == BotCombatActionCategory::UseItem
        && ("," + spell.MechanicTags + ",").find(",combat_potion,") != std::string::npos;
    Unit const* healthTarget = required ? owner.Target : target;
    return !(required && !healthTarget)
        && ::MeetsHostileTargetHealthGate(spell,
            healthTarget && healthTarget->GetMaxHealth()
                ? float(healthTarget->GetHealth()) / float(healthTarget->GetMaxHealth()) : 0.0f,
            healthTarget != nullptr);
}

template<class Cohort, class Party>
BotCombatPotionHealthOwner Resolve(Player const* bot, Cohort const& cohort, Party const& party)
{
    if (!cohort.Config.ValidationRouteEnable || !cohort.Raid.RaidInstance
        || !cohort.Raid.EncounterInProgress || cohort.Config.ValidationRouteKind != "boss"
        || cohort.CalibrationActive)
        return {};

    BotCombatPotionHealthOwner owner{true, nullptr};
    // Engagement identity survives temporary head/add damage-target selection.
    if (!bot || party.ValidationRouteEngagedBossGeneration != party.ValidationRouteGeneration
        || party.ValidationRouteEngagedBossMapId != bot->GetMapId()
        || party.ValidationRouteEngagedBossInstanceId != bot->GetInstanceId())
        return owner;
    Unit const* boss = ObjectAccessor::GetUnit(*bot, party.ValidationRouteEngagedBossGuid);
    if (boss && boss->IsAlive() && boss->GetMaxHealth()
        && boss->GetEntry() == cohort.Config.ValidationRouteTargetEntry
        && bot->IsInMap(boss) && bot->IsInPhase(boss))
        owner.Target = boss;
    return owner;
}
}

#endif
