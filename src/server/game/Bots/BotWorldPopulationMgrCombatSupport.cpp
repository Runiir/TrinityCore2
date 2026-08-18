#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotMgr.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "CellImpl.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "LFG.h"
#include "MotionMaster.h"
#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <sstream>
#include <string>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;
    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}

bool HasPowerForSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;
    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > powerCost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(powerCost);
}

bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth = 0)
{
    if (!spellInfo || depth > 4)
        return false;
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

bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target)
{
    if (!owner || !target || !BotRaidAreaAuthority::HasProtectedEncounterEntries(owner->GetGUID().GetRawValue()))
        return false;
    std::vector<WorldObject*> nearbyObjects;
    Trinity::AllWorldObjectsInRange check(target, 45.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(target, nearbyObjects, check);
    Cell::VisitAllObjects(target, searcher, 45.0f);
    for (WorldObject* object : nearbyObjects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || creature == target || !creature->IsAlive()
            || !owner->IsValidAttackTarget(creature))
            continue;
        if (BotRaidAreaAuthority::IsProtectedEncounterTarget(owner->GetGUID().GetRawValue(),
                creature->GetEntry(), creature->GetSpawnId(), creature->GetGUID().GetRawValue()))
            return true;
    }
    return false;
}
}

char const* BotWorldPopulationMgr::GetDungeonRole(Player* bot) const
{
    if (!bot)
        return "dps";

    if (Group* group = bot->GetGroup())
    {
        uint8 roles = group->GetLfgRoles(bot->GetGUID());
        if (roles & lfg::PLAYER_ROLE_TANK)
            return "tank";
        if (roles & lfg::PLAYER_ROLE_HEALER)
            return "healer";
    }

    std::string botRole = sBotMgr->GetBotRoleName(bot->GetGUID());
    if (botRole.find("holy") != std::string::npos || botRole.find("healer") != std::string::npos)
        return "healer";
    if (botRole.find("tank") != std::string::npos)
        return "tank";

    if (QueryResult result = CharacterDatabase.PQuery("SELECT role FROM character_bot_pool WHERE guid = %u LIMIT 1", bot->GetGUID().GetCounter()))
    {
        std::string poolRole = result->Fetch()[0].GetString();
        std::transform(poolRole.begin(), poolRole.end(), poolRole.begin(), [](unsigned char c) { return std::tolower(c); });
        if (poolRole.find("healer") != std::string::npos || poolRole.find("heal") != std::string::npos || poolRole.find("holy") != std::string::npos)
            return "healer";
        if (poolRole.find("tank") != std::string::npos || poolRole.find("prot") != std::string::npos || poolRole.find("blood") != std::string::npos)
            return "tank";
        if (poolRole.find("dps") != std::string::npos || poolRole.find("damage") != std::string::npos)
            return "dps";
    }

    if (Group* group = bot->GetGroup())
        if (group->GetLfgRoles(bot->GetGUID()) & lfg::PLAYER_ROLE_DAMAGE)
            return "dps";

    switch (bot->getClass())
    {
        case CLASS_WARRIOR:
        case CLASS_DEATH_KNIGHT:
            return "tank";
        case CLASS_PRIEST:
            return "healer";
        default:
            return "dps";
    }
}

uint32 BotWorldPopulationMgr::SelectInterruptSpell(Player* bot) const
{
    if (!bot)
        return 0;

    uint32 candidates[4] = { 0, 0, 0, 0 };
    switch (bot->getClass())
    {
        case CLASS_WARRIOR: candidates[0] = 6552; break;       // Pummel
        case CLASS_ROGUE: candidates[0] = 1766; break;         // Kick
        case CLASS_MAGE: candidates[0] = 2139; break;          // Counterspell
        case CLASS_SHAMAN: candidates[0] = 57994; break;       // Wind Shear
        case CLASS_DEATH_KNIGHT: candidates[0] = 47528; break; // Mind Freeze
        case CLASS_PALADIN: candidates[0] = 96231; break;      // Rebuke
        case CLASS_DRUID: candidates[0] = 80965; break;        // Skull Bash
        default: break;
    }

    for (uint32 spellId : candidates)
        if (spellId && bot->HasSpell(spellId))
            return spellId;

    return 0;
}

uint32 BotWorldPopulationMgr::SelectHealSpell(Player* bot, Unit* target, bool instantOnly) const
{
    if (!bot || !target)
        return 0;

    std::string role = GetDungeonRole(bot);
    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role.c_str());
    RoleSaturationState saturation = BuildRoleSaturationState(bot, target, role.c_str());
    std::string roleGoal = BotProgressionGoalPolicy::RoleGoal(role);
    std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile);
    BotActionCandidate* best = nullptr;
    for (BotActionCandidate& candidate : candidates)
    {
        uint32 injuredPlayers = 0;
        if (Group* group = bot->GetGroup())
            for (GroupReference* itr = group->GetFirstMember(); itr; itr = itr->next())
                if (Player* member = itr->GetSource())
                    if (member->IsAlive() && member->GetMap() == bot->GetMap()
                        && UnitHealthPct(member) < candidate.Profile.InjuredHealthPct)
                        ++injuredPlayers;
        if (candidate.Category != BotCombatActionCategory::HealFast
            && candidate.Category != BotCombatActionCategory::HealEfficient
            && candidate.Category != BotCombatActionCategory::HealAoe)
        {
            candidate.RejectReason = "not_healing_action";
            continue;
        }
        if (!candidate.RejectReason.empty())
            continue;
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
        if (instantOnly && spellInfo && spellInfo->CalcCastTime(bot->getLevel()) > 0)
        {
            candidate.RejectReason = "movement_requires_instant_heal";
            continue;
        }
        if (spellInfo && (target->IsImmunedToSpell(spellInfo, bot)
                || (spellInfo->HasOnlyDamageEffects() && target->IsImmunedToDamage(spellInfo))))
        {
            candidate.RejectReason = "target_immune";
            continue;
        }
        float targetHp = UnitHealthPct(target);
        if (targetHp < candidate.Profile.MinTargetHealthPct || targetHp > candidate.Profile.MaxTargetHealthPct)
            candidate.RejectReason = "target_health_gate";
        else if (candidate.Profile.MinInjuredPlayers > injuredPlayers)
            candidate.RejectReason = "injured_player_count_too_low";
        else if (candidate.Profile.MaxInjuredPlayers && injuredPlayers > candidate.Profile.MaxInjuredPlayers)
            candidate.RejectReason = "injured_player_count_too_high";
        else if ((bot->GetMaxPower(POWER_MANA) ? float(bot->GetPower(POWER_MANA)) / float(bot->GetMaxPower(POWER_MANA)) : 0.0f) < candidate.Profile.MinManaPct
            || (bot->GetMaxPower(POWER_MANA) ? float(bot->GetPower(POWER_MANA)) / float(bot->GetMaxPower(POWER_MANA)) : 0.0f) > candidate.Profile.MaxManaPct)
            candidate.RejectReason = "mana_gate";
        else if (!best || candidate.Score > best->Score)
        {
            candidate.Reason = "db_profile_healing_policy";
            best = &candidate;
        }
    }

    uint32 botKey = bot->GetGUID().GetCounter();
    std::ostringstream rejectionJson;
    rejectionJson << '[';
    bool firstReject = true;
    for (BotActionCandidate const& candidate : candidates)
    {
        if (!candidate.SpellId || candidate.RejectReason.empty())
            continue;
        if (!firstReject)
            rejectionJson << ',';
        firstReject = false;
        rejectionJson << "{\"spell_id\":" << candidate.SpellId
                      << ",\"reason\":\"" << JsonEscape(candidate.RejectReason) << "\"}";
    }
    rejectionJson << ']';
    Party().LastCombatRejectsByBot[botKey] = rejectionJson.str();
    Party().LastSaturationByBot[botKey] = saturation;
    Party().LastCombatMaskByBot[botKey] = BotClassSpecActionProfileStore::CandidateMaskJson(candidates, profile, roleGoal.c_str(), saturation.ToJson().c_str());
    Party().LastChosenCombatByBot[botKey] = BotClassSpecActionProfileStore::ChosenActionJson(best, profile, roleGoal.c_str(), BotRoleSaturationPolicy::ToString(saturation.RecommendedBalanceMode), saturation.ExperimentConfidence);
    Party().LastActionCategoryByBot[botKey] = best ? BotCombatActionCatalog::ToString(best->Category) : "wait";
    return best ? best->SpellId : 0;
}

bool BotWorldPopulationMgr::TryCastFriendlySpell(Player* bot, Unit* target, uint32 spellId, std::string* failureReason)
{
    auto fail = [failureReason](char const* reason) -> bool
    {
        if (failureReason)
            *failureReason = reason;
        return false;
    };

    if (!bot)
        return fail("missing_bot");
    if (!target)
        return fail("missing_target");
    if (!spellId)
        return fail("missing_spell");
    if (!target->IsAlive())
        return fail("target_dead");
    if (!bot->IsValidAssistTarget(target))
        return fail("invalid_assist_target");

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo)
        return fail("missing_spell_info");
    uint64 const ownerGuid = bot->GetGUID().GetRawValue();
    if (BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid)
        && !spellInfo->IsPositive())
        return fail("raid_offense_suppressed");
    if (Creature const* creature = target->ToCreature();
        creature && BotRaidAreaAuthority::IsProtectedEncounterTarget(
            ownerGuid, creature->GetEntry(), creature->GetSpawnId(),
            creature->GetGUID().GetRawValue()))
        return fail("future_encounter_target_forbidden");
    if (HasNearbyProtectedEncounterTarget(bot, target)
        && SpellHasHostileMultiTargetSemantics(spellInfo))
        return fail("future_encounter_splash_forbidden");
    if (!bot->IsWithinLOSInMap(target))
        return fail("line_of_sight");

    float maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    if (!bot->IsWithinDistInMap(target, maxRange))
        return fail("out_of_range");

    if (bot->HasUnitState(UNIT_STATE_CASTING))
        return fail("already_casting");
    if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
        return fail("global_cooldown");
    if (!bot->GetSpellHistory()->IsReady(spellInfo))
        return fail("spell_not_ready");

    if (!HasPowerForSpell(bot, spellInfo))
        return fail("insufficient_power");

    if (spellInfo->CalcCastTime(bot->getLevel()) > 0)
    {
        bot->StopMoving();
        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        bot->GetMotionMaster()->MoveIdle();
    }

    // Install the cast identity before CastSpell: instant spells can finish synchronously.
    uint64 pendingCastId = BeginPendingHealCast(bot, target, spellId);
    SpellCastResult castResult = bot->CastSpell(target, spellId, false);
    if (castResult != SPELL_CAST_OK)
    {
        CancelBotSpellStart(pendingCastId, bot, "cast_submission_failed");
        if (failureReason)
            *failureReason = "spell_cast_result_" + std::to_string(uint32(castResult));
        return false;
    }

    if (failureReason)
        failureReason->clear();
    return true;
}

bool BotWorldPopulationMgr::TryNativeSelfResurrection(WorldBotState& state, Player* bot)
{
    if (!bot || bot->IsAlive() || bot->HasAuraType(SPELL_AURA_PREVENT_RESURRECTION))
        return false;

    uint64 const nowMs = NowMs();
    uint32 const spellId = bot->GetUInt32Value(PLAYER_SELF_RES_SPELL);
    if (!spellId || (state.NativeResurrectionRejectedSpellId == spellId
        && state.NativeResurrectionRetryAfterMs > nowMs))
        return false;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo || !spellInfo->HasEffect(SPELL_EFFECT_SELF_RESURRECT)
        || !bot->GetSpellHistory()->IsReady(spellInfo))
        return false;

    std::string raw = BuildRawJson(bot, bot);
    std::string semantic = BuildSemanticJson(bot, bot, "native_self_resurrection");
    SpellCastResult castResult = bot->CastSpell(bot, spellId, false);
    if (castResult == SPELL_CAST_OK)
    {
        state.NativeResurrectionRejectedSpellId = 0;
        state.NativeResurrectionRejectedCastResult = 0;
        state.NativeResurrectionRetryAfterMs = 0;
        state.NativeResurrectionConsecutiveFailures = 0;
        RecordEvent(state, bot, "validation_route_resurrection", bot, "native_self_resurrection_submitted",
            raw.c_str(), semantic.c_str(), 0.0f, 0, spellId);
        return true;
    }

    bool sameFailure = state.NativeResurrectionRejectedSpellId == spellId
        && state.NativeResurrectionRejectedCastResult == uint32(castResult);
    state.NativeResurrectionConsecutiveFailures = sameFailure
        ? uint8(std::min<uint32>(255, uint32(state.NativeResurrectionConsecutiveFailures) + 1)) : 1;
    state.NativeResurrectionRejectedTargetGuid = bot->GetGUID();
    state.NativeResurrectionRejectedSpellId = spellId;
    state.NativeResurrectionRejectedCastResult = uint32(castResult);
    state.NativeResurrectionRetryAfterMs = nowMs + (state.NativeResurrectionConsecutiveFailures >= 2 ? 60000 : 5000);
    std::string resultLabel = "native_self_resurrection_result_" + std::to_string(uint32(castResult));
    RecordEvent(state, bot, "validation_route_resurrection", bot, resultLabel.c_str(),
        raw.c_str(), semantic.c_str(), 0.0f, 0, spellId);
    return false;
}
