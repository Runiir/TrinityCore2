#include "Bots/BotController.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotDatasetEvent.h"
#include "Bots/BotMgr.h"
#include "Config.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "Log.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "DataStores/DBCStructure.h"
#include "DungeonFinding/LFG.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Transport.h"
#include "Spell.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include <algorithm>
#include <boost/filesystem.hpp>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <map>
#include <sstream>
#include <utility>

namespace
{
bool RotationHasEnoughPower(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    int32 cost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (cost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > cost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(cost);
}

bool IsHealingCategory(BotCombatActionCategory category)
{
    return category == BotCombatActionCategory::HealFast
        || category == BotCombatActionCategory::HealEfficient
        || category == BotCombatActionCategory::HealAoe
        || category == BotCombatActionCategory::DispelCleanse
        || category == BotCombatActionCategory::ExternalDefensive
        || category == BotCombatActionCategory::Defensive
        || category == BotCombatActionCategory::Mitigation
        || category == BotCombatActionCategory::OffensiveCooldown;
}

uint32 CastTimeMs(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return 0;
    return uint32(std::max<int32>(0, spellInfo->CalcCastTime(bot->getLevel())));
}

bool MeetsCastDirectives(Player const* bot, BotActionProfileSpell const& spell, SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;
    uint32 castTime = CastTimeMs(bot, spellInfo);
    if (spell.RequiresInstantCast && castTime > 0)
        return false;
    if (spell.MaxCastTimeMs && castTime > spell.MaxCastTimeMs)
        return false;
    return true;
}

HealerUnitFrame const* SelectHealerUnit(HealerFrame const& frame, std::string const& selector)
{
    HealerUnitFrame const* selected = nullptr;
    for (HealerUnitFrame const& unit : frame.Party)
    {
        if (!unit.Alive || !unit.Friendly || !unit.LineOfSight)
            continue;

        if (selector == "self")
        {
            if (unit.Guid == frame.BotGuid)
                return &unit;
            continue;
        }

        if (selector == "owner")
        {
            if (unit.Guid == frame.OwnerGuid)
                return &unit;
            continue;
        }

        if (selector == "tank")
        {
            if (!(unit.Role & lfg::PLAYER_ROLE_TANK))
                continue;
            if (!selected || unit.HealthPct < selected->HealthPct)
                selected = &unit;
            continue;
        }

        if (!selected || unit.HealthPct < selected->HealthPct || (unit.IsOwner && unit.HealthPct == selected->HealthPct))
            selected = &unit;
    }
    return selected;
}
}

bool BotController::TryResolveHealerAction(BotActionExecutor& executor, Player* owner, Player* bot, BotRecentEvents const& recentEvents, bool shouldRecord, BotMovementFrame const& movementFrame)
{
    // DB categories, including BotCombatActionCategory::HealFast, are the sole healer action authority.
    _lastHealerCandidateMaskJson = "{}";
    _lastHealerChosenActionJson = "{}";
    HealerFrame frame = BuildFrame(owner, bot, recentEvents);
    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, "healer");
    ResolvedBotAction action;
    action.DebugName = "no_valid_db_healer_action";
    HealerDecision decision;
    struct HealerAttempt
    {
        BotActionProfileSpell const* Spell = nullptr;
        ObjectGuid TargetGuid;
        float Score = 0.0f;
        BotActionCandidate Candidate;
    };
    std::vector<HealerAttempt> attempts;
    std::vector<BotActionCandidate> evaluatedCandidates;
    uint8 attackers = uint8(std::min<size_t>(255, bot->GetThreatManager().GetThreatenedByMeList().size()));

    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        if (!spell.SpellId || !IsHealingCategory(spell.Category))
            continue;
        BotActionCandidate telemetryCandidate;
        telemetryCandidate.ActionId = BotCombatActionCatalog::StableActionId(spell.Category, spell.SpellId);
        telemetryCandidate.SpellId = spell.SpellId;
        telemetryCandidate.Category = spell.Category;
        telemetryCandidate.TargetType = spell.TargetSelector;
        telemetryCandidate.Profile = spell;
        auto rejectCandidate = [&](char const* reason) { telemetryCandidate.RejectReason = reason; evaluatedCandidates.push_back(telemetryCandidate); };
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId);
        if (!spellInfo) { rejectCandidate("missing_spell_info"); continue; }
        if (!bot->GetSpellHistory()->IsReady(spellInfo)) { rejectCandidate("cooldown_not_ready"); continue; }
        if (!RotationHasEnoughPower(bot, spellInfo)) { rejectCandidate("insufficient_power"); continue; }
        uint8 injuredPlayers = 0;
        for (HealerUnitFrame const& partyUnit : frame.Party)
            if (partyUnit.Alive && partyUnit.Friendly && float(partyUnit.HealthPct) / 100.0f <= spell.InjuredHealthPct)
                ++injuredPlayers;
        uint32 castTime = CastTimeMs(bot, spellInfo);
        if (!MeetsCastDirectives(bot, spell, spellInfo)) { rejectCandidate("cast_directive_rejected"); continue; }
        if ((movementFrame.Moving && castTime && !spell.RequiresMoving) || (spell.RequiresStationary && movementFrame.Moving) || (spell.RequiresMoving && !movementFrame.Moving)) { rejectCandidate("movement_gate"); continue; }
        if (spell.MinInjuredPlayers && injuredPlayers < spell.MinInjuredPlayers) { rejectCandidate("injured_player_count_too_low"); continue; }
        if (spell.MaxInjuredPlayers && injuredPlayers > spell.MaxInjuredPlayers) { rejectCandidate("injured_player_count_too_high"); continue; }
        if (spell.MinAttackers && attackers < spell.MinAttackers) { rejectCandidate("attacker_count_too_low"); continue; }
        if (spell.MaxAttackers && attackers > spell.MaxAttackers) { rejectCandidate("attacker_count_too_high"); continue; }
        if (float(frame.BotManaPct) / 100.0f < spell.MinManaPct) { rejectCandidate("mana_too_low"); continue; }
        if (float(frame.BotManaPct) / 100.0f > spell.MaxManaPct) { rejectCandidate("mana_too_high"); continue; }
        bool utility = spell.Category == BotCombatActionCategory::Defensive || spell.Category == BotCombatActionCategory::Mitigation
            || spell.Category == BotCombatActionCategory::OffensiveCooldown;
        Unit* target = nullptr;
        ObjectGuid targetGuid;
        float healthPct = float(frame.BotHealthPct) / 100.0f;
        if (spell.TargetSelector == "enemy")
        {
            target = bot->GetSelectedUnit();
            if (!target || !bot->IsValidAttackTarget(target))
                target = bot->GetVictim();
            if (!target || !bot->IsValidAttackTarget(target))
            { rejectCandidate("missing_enemy_target"); continue; }
            targetGuid = target->GetGUID();
        }
        else
        {
            HealerUnitFrame const* unit = SelectHealerUnit(frame, spell.TargetSelector.empty() ? "lowest_ally" : spell.TargetSelector);
            if (!unit)
            { rejectCandidate("missing_ally_target"); continue; }
            targetGuid = unit->Guid;
            healthPct = float(unit->HealthPct) / 100.0f;
            target = ObjectAccessor::GetUnit(*bot, targetGuid);
            if (!target)
            { rejectCandidate("invalid_ally_target"); continue; }
        }
        if (float(frame.BotHealthPct) / 100.0f < spell.MinSelfHealthPct || float(frame.BotHealthPct) / 100.0f > spell.MaxSelfHealthPct
            || (!utility && (healthPct < spell.MinTargetHealthPct || healthPct > spell.MaxTargetHealthPct
                || (spell.InjuredHealthPct < 1.0f && healthPct > spell.InjuredHealthPct))))
        { rejectCandidate("health_gate"); continue; }
        float distance = bot->GetExactDist(target);
        if ((spell.MaxRange > 0.0f && distance > spell.MaxRange) || (spell.MinRange > 0.0f && distance < spell.MinRange)
            || (spell.MaxRange <= 0.0f && distance > std::max(5.0f, spellInfo->GetMaxRange(false))))
        { rejectCandidate("range_gate"); continue; }
        if ((spell.ForbiddenTargetAura && target->HasAura(spell.ForbiddenTargetAura))
            || (spell.MaintainAuraId && target->HasAura(spell.MaintainAuraId))
            || (spell.RequiredTargetAura && !target->HasAura(spell.RequiredTargetAura))
            || (spell.RequiredSelfAura && !bot->HasAura(spell.RequiredSelfAura))
            || (spell.ForbiddenSelfAura && bot->HasAura(spell.ForbiddenSelfAura)))
        { rejectCandidate("aura_gate"); continue; }

        float missingHealth = float(target->GetMaxHealth() - target->GetHealth());
        float expectedRawHealing = utility ? 0.0f : std::max(0.0f, spell.HealingWeight) * float(target->GetMaxHealth());
        float expectedEffectiveHealing = utility ? 0.0f : std::min(missingHealth, expectedRawHealing);
        float expectedOverheal = utility ? 0.0f : std::max(0.0f, expectedRawHealing - expectedEffectiveHealing);
        float urgency = 1.0f - healthPct;
        float score = utility
            ? (spell.SurvivalWeight + spell.ThreatWeight * float(attackers) + spell.MitigationWeight + spell.MovementWeight) * float(bot->GetMaxHealth())
            : expectedEffectiveHealing - expectedOverheal * 0.35f + spell.SurvivalWeight * urgency * float(target->GetMaxHealth());
        score -= float(spell.PriorityBucket) * 0.03f;
        uint32 manaCost = uint32(std::max<int32>(0, spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask())));
        telemetryCandidate.TargetGuid = targetGuid.GetCounter();
        telemetryCandidate.Score = score;
        telemetryCandidate.Reason = "db_profile_healing_policy";
        telemetryCandidate.PredictedRawHeal = expectedRawHealing;
        telemetryCandidate.PredictedEffectiveHeal = expectedEffectiveHealing;
        telemetryCandidate.PredictedOverheal = expectedOverheal;
        telemetryCandidate.ManaCost = manaCost;
        telemetryCandidate.CastTimeMs = castTime;
        telemetryCandidate.Profile = spell;
        evaluatedCandidates.push_back(telemetryCandidate);
        attempts.push_back(HealerAttempt{ &spell, targetGuid, score, telemetryCandidate });
    }

    std::sort(attempts.begin(), attempts.end(), [](HealerAttempt const& left, HealerAttempt const& right)
    {
        return left.Score > right.Score;
    });

    BotActionResult result = BotActionResult::NoAction;
    for (HealerAttempt const& attempt : attempts)
    {
        action.Intent = HealerIntent::EfficientSingleHeal;
        action.TargetGuid = attempt.TargetGuid;
        action.SpellId = attempt.Spell->SpellId;
        action.DebugName = BotCombatActionCatalog::ToString(attempt.Spell->Category);
        Unit* lifecycleTarget = ObjectAccessor::GetUnit(*bot, attempt.TargetGuid);
        std::string candidateMaskJson = BotClassSpecActionProfileStore::CandidateMaskJson(evaluatedCandidates, profile, "preserve_party", "{}");
        std::string chosenActionJson = BotClassSpecActionProfileStore::ChosenActionJson(&attempt.Candidate, profile, "preserve_party", "role_first", 1.0f);
        _lastHealerCandidateMaskJson = candidateMaskJson;
        _lastHealerChosenActionJson = chosenActionJson;
        uint64 pendingCastId = sBotWorldPopulationMgr->NotifyBotSpellStarted(bot, lifecycleTarget, attempt.Spell->SpellId, candidateMaskJson, chosenActionJson);
        result = executor.Execute(owner, bot, action);
        if (result == BotActionResult::Ok || result == BotActionResult::Casting)
            break;
        sBotWorldPopulationMgr->CancelBotSpellStart(pendingCastId, bot, ToString(result));
        if (result == BotActionResult::GlobalCooldown)
            break;
    }

    if (shouldRecord)
    {
        RecordFrame(frame, decision, &action, result, owner, bot);
        RecordMovementFrame(movementFrame, ToString(_movementMode), ToString(decision.Intent), action.DebugName.c_str(), result != BotActionResult::Disabled, owner, bot);
    }

    return result == BotActionResult::Ok || result == BotActionResult::Casting || result == BotActionResult::GlobalCooldown;
}

HealerFrame BotController::BuildFrame(Player* owner, Player* bot, BotRecentEvents const& recentEvents) const
{
    HealerFrame frame;
    frame.OwnerGuid = owner->GetGUID();
    frame.BotGuid = bot->GetGUID();
    frame.MapId = bot->GetMapId();
    frame.BotAlive = bot->IsAlive();
    frame.BotCasting = bot->HasUnitState(UNIT_STATE_CASTING);
    if (Spell* spell = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        frame.BotCastSpellId = spell->GetSpellInfo()->Id;
    if (Spell* spell = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
        frame.BotChannelSpellId = spell->GetSpellInfo()->Id;
    frame.BotAuraCount = bot->GetAppliedAuras().size();
    for (auto const& aura : bot->GetAppliedAuras())
        if (aura.second && !aura.second->IsPositive())
            ++frame.BotDebuffCount;
    frame.InCombat = bot->IsInCombat() || owner->IsInCombat();
    frame.RecentDamageTaken = recentEvents.DamageTaken;
    frame.RecentHealingDone = recentEvents.HealingDone;
    frame.RecentHealingReceived = recentEvents.HealingReceived;
    frame.MovementMode = _movementMode;

    uint32 maxHealth = bot->GetMaxHealth();
    frame.BotHealthPct = maxHealth ? uint32(bot->GetHealth() * 100 / maxHealth) : 0;
    uint32 maxMana = bot->GetMaxPower(POWER_MANA);
    frame.BotManaPct = maxMana ? uint32(bot->GetPower(POWER_MANA) * 100 / maxMana) : 100;

    SpellInfo const* holyLight = sSpellMgr->GetSpellInfo(635);
    frame.GcdReady = !holyLight || !bot->GetSpellHistory()->HasGlobalCooldown(holyLight);

    Group* group = owner->GetGroup();
    auto addUnit = [&](Player* player, bool isOwner)
    {
        if (!player || player->GetMap() != bot->GetMap())
            return;

        HealerUnitFrame unit;
        unit.Guid = player->GetGUID();
        unit.Name = player->GetName();
        unit.Role = group ? group->GetLfgRoles(player->GetGUID()) : 0;
        unit.Subgroup = group ? group->GetMemberGroup(player->GetGUID()) : 0;
        unit.Alive = player->IsAlive();
        unit.Friendly = bot->IsFriendlyTo(player) || bot->IsValidAssistTarget(player);
        unit.LineOfSight = bot->IsWithinLOSInMap(player);
        unit.Distance = bot->GetExactDist(player);
        unit.IsOwner = isOwner;
        if (Spell* spell = player->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            unit.CastSpellId = spell->GetSpellInfo()->Id;
        if (Spell* spell = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
            unit.ChannelSpellId = spell->GetSpellInfo()->Id;
        unit.AuraCount = player->GetAppliedAuras().size();
        for (auto const& aura : player->GetAppliedAuras())
            if (aura.second && !aura.second->IsPositive())
                ++unit.DebuffCount;
        auto damageItr = recentEvents.PartyDamageTaken.find(player->GetGUID());
        if (damageItr != recentEvents.PartyDamageTaken.end())
            unit.RecentDamageTaken = damageItr->second;
        auto healingItr = recentEvents.PartyHealingReceived.find(player->GetGUID());
        if (healingItr != recentEvents.PartyHealingReceived.end())
            unit.RecentHealingReceived = healingItr->second;
        uint32 unitMaxHealth = player->GetMaxHealth();
        unit.HealthPct = unitMaxHealth ? uint8(std::min<uint32>(100, player->GetHealth() * 100 / unitMaxHealth)) : 0;
        frame.Party.push_back(unit);
    };

    if (group)
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            addUnit(itr->GetSource(), itr->GetSource() == owner);
    }
    else
        addUnit(owner, true);

    return frame;
}
