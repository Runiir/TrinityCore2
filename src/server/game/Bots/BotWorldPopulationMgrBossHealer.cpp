#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrBossMechanicsSupport.h"

#include "Group.h"
#include "GroupReference.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <string>

using BotWorldBossMechanics::UnitHealthPct;

bool BotWorldPopulationMgr::TryBossHealer(
    WorldBotState& state, Player* bot, char const* role,
    BossMechanicActionResult& result,
    RaidRoleAssignment const& raidAssignment,
    RaidPositioningAnchors const& raidAnchors,
    RaidMechanicAdapter const& raidAdapter,
    RaidGearTargetPlan const& raidGearPlan,
    HeroicRaidProgression const& heroicProgression,
    char const* rawJson, char const* semanticJson)
{
    if (std::string(role) != "healer")
        return false;

    auto recordRejection = [this, &state, bot, &result, &raidAssignment,
        &raidAnchors, &raidAdapter, &raidGearPlan, &heroicProgression,
        rawJson, semanticJson](char const* reason, Unit const* target,
        float valueFloat, uint32 spellId)
    {
        RecordEvent(state, bot, "boss_heal_rejected", target, reason,
            rawJson, semanticJson, valueFloat, result.Features.CastSpellId,
            spellId);
        if (result.Features.RaidEncounter)
            RecordRaidTelemetry(state, bot, target, "raid_healer_rejection",
                reason, result.Features, raidAssignment, raidAnchors,
                raidAdapter, raidGearPlan, heroicProgression, rawJson,
                semanticJson, valueFloat, result.Features.CastSpellId,
                spellId);
    };

    bool const assignedHealer = raidAdapter.HealerOwnerSlots.empty()
        || std::find(raidAdapter.HealerOwnerSlots.begin(),
            raidAdapter.HealerOwnerSlots.end(), raidAssignment.RoleIndex)
            != raidAdapter.HealerOwnerSlots.end();
    if (!assignedHealer)
    {
        recordRejection("unassigned_healer", nullptr, 0.0f, 0);
        return false;
    }

    Unit* healTarget = nullptr;
    Unit* rangeOrLosRejected = nullptr;
    if (Group* group = bot->GetGroup())
    {
        float lowestHp = 2.0f;
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr;
            itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;
            if (!bot->IsWithinLOSInMap(member))
            {
                if (!rangeOrLosRejected)
                    rangeOrLosRejected = member;
                continue;
            }

            bool const tank = GetDungeonRole(member) == std::string("tank");
            bool const sameSubgroup = group->GetMemberGroup(member->GetGUID())
                == raidAssignment.SubGroup;
            bool const owned = raidAdapter.HealerOwnership == "raid_triage"
                || (raidAdapter.HealerOwnership == "tank" && tank)
                || (raidAdapter.HealerOwnership == "subgroup" && sameSubgroup)
                || (raidAdapter.HealerOwnership == "tank_and_subgroup"
                    && (tank || sameSubgroup));
            if (!owned)
                continue;

            float hp = UnitHealthPct(member);
            if (hp < lowestHp)
            {
                healTarget = member;
                lowestHp = hp;
            }
        }
    }

    if (!healTarget)
    {
        if (rangeOrLosRejected)
            recordRejection("range_or_los_rejected", rangeOrLosRejected,
                bot->GetExactDist(rangeOrLosRejected), 0);
        else
            recordRejection("no_eligible_target", nullptr, 0.0f, 0);
        return false;
    }

    uint32 const healSpell = SelectHealSpell(bot, healTarget);
    if (!healSpell)
    {
        recordRejection("no_profile_heal", healTarget,
            UnitHealthPct(healTarget), 0);
        return false;
    }

    if (UnitHealthPct(healTarget)
        >= (result.Features.RaidDamage ? 0.9f : 0.75f))
        return false;

    std::string failureReason;
    if (!TryCastFriendlySpell(bot, healTarget, healSpell, &failureReason))
    {
        std::string const reason = failureReason.empty()
            ? "cast_failed" : "cast_failed:" + failureReason;
        recordRejection(reason.c_str(), healTarget,
            UnitHealthPct(healTarget), healSpell);
        return false;
    }

    result.Action = result.Features.RaidDamage
        ? "heal_raid_damage" : "heal_boss_damage";
    result.SpellId = healSpell;
    result.Target = healTarget;
    RecordEvent(state, bot, "boss_heal", result.Target, "ok", rawJson,
        semanticJson, UnitHealthPct(healTarget), result.Features.CastSpellId,
        healSpell);
    if (result.Features.RaidEncounter)
        RecordRaidTelemetry(state, bot, result.Target, "raid_healer_cooldown",
            "ok", result.Features, raidAssignment, raidAnchors, raidAdapter,
            raidGearPlan, heroicProgression, rawJson, semanticJson,
            UnitHealthPct(healTarget), result.Features.CastSpellId, healSpell);
    return true;
}
