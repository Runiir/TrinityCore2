#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilHighDensityPositioning.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Entities/Object/Position.h"
#include "Map.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <string>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

bool Context::Run(HighDensityPositioningRequest const& request)
{
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    BotProgressionStage stage = request.Stage;
    BotProgressionActivity activity = request.Activity;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
    Unit* add = request.Add;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    uint32 addCount = discovery.AddCount;
    uint32 nearbyAddCount = discovery.NearbyAddCount;
    float addX = discovery.AddX;
    float addY = discovery.AddY;
    bool highDensityPhase = density.HighDensityPhase;
    std::string const& role = density.Role;
    BotClassSpecActionProfile const& profile = density.Profile;
    Player* densityTank = density.DensityTank;
    Player* densityHealer = density.DensityHealer;
    Player* densityDefenseTarget = density.DensityDefenseTarget;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;

    float densityHealerRange = 0.0f;
    if (densityHealer)
    {
        BotClassSpecActionProfile healerProfile = BotClassSpecActionProfileStore::Build(densityHealer, "healer");
        for (BotActionProfileSpell const& spell : healerProfile.Spells)
        {
            if (!spell.SpellId || !densityHealer->HasSpell(spell.SpellId)
                || (spell.Category != BotCombatActionCategory::HealFast
                    && spell.Category != BotCombatActionCategory::HealEfficient
                    && spell.Category != BotCombatActionCategory::HealAoe))
                continue;
            float spellRange = spell.MaxRange;
            if (spellRange <= 0.0f)
                if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId))
                    spellRange = spellInfo->GetMaxRange(true);
            densityHealerRange = std::max(densityHealerRange, spellRange);
        }
    }

    bool escapeCohortValid = densityTank && densityHealer && densityHealerRange > 3.0f;
    if (manager.Party().ValidationRouteBossAddEscapeActive && escapeCohortValid)
    {
        escapeCohortValid = densityTank->GetExactDist(manager.Party().ValidationRouteBossAddEscapeX,
                manager.Party().ValidationRouteBossAddEscapeY, manager.Party().ValidationRouteBossAddEscapeZ) <= densityHealerRange - 1.0f
            && densityHealer->GetExactDist(manager.Party().ValidationRouteBossAddEscapeX,
                manager.Party().ValidationRouteBossAddEscapeY, manager.Party().ValidationRouteBossAddEscapeZ) <= densityHealerRange - 1.0f
            && densityTank->IsWithinLOS(manager.Party().ValidationRouteBossAddEscapeX, manager.Party().ValidationRouteBossAddEscapeY, manager.Party().ValidationRouteBossAddEscapeZ)
            && densityHealer->IsWithinLOS(manager.Party().ValidationRouteBossAddEscapeX, manager.Party().ValidationRouteBossAddEscapeY, manager.Party().ValidationRouteBossAddEscapeZ);
    }
    if (manager.Party().ValidationRouteBossAddEscapeActive && !escapeCohortValid)
        manager.ResetValidationRouteBossAddEscapeState();

    if (highDensityPhase && bot == densityTank && addCount >= 3 && !densityDefenseTarget)
    {
        float centroidX = addX / float(addCount);
        float centroidY = addY / float(addCount);
        float centroidDistance = densityTank->GetExactDist2d(centroidX, centroidY);
        if (centroidDistance > 4.0f && !densityTank->HasUnitState(UNIT_STATE_CASTING) && !densityTank->IsFalling())
        {
            Map* map = densityTank->GetMap();
            float centroidZ = densityTank->GetPositionZ();
            if (map)
            {
                float floorZ = map->GetHeight(densityTank->GetPhaseShift(), centroidX, centroidY, centroidZ + 4.0f, true, 10.0f);
                if (floorZ > INVALID_HEIGHT && std::fabs(floorZ - centroidZ) <= 10.0f)
                    centroidZ = floorZ;
            }
            bool moved = densityTank->IsWithinLOS(centroidX, centroidY, centroidZ)
                && manager.MoveBotToPoint(state, densityTank, centroidX, centroidY, centroidZ);
            std::string raw = manager.BuildRawJson(bot, add);
            std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            manager.RecordEvent(state, bot, "boss_add_density", add,
                moved ? "tank_move_to_add_centroid" : "tank_add_centroid_path_rejected",
                raw.c_str(), semantic.c_str(), centroidDistance, addCount);
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = moved ? "tank_move_to_add_centroid" : "hold_tank_add_centroid";
            return true;
        }
    }

    // Healing at maximum range makes newly spawned adds run away from the
    // tank's Consecration/Hammer radius. Issue one pickup-stack movement,
    // then allow normal instant healing while that path remains active.
    // Exact hazard exits run before this branch and remain authoritative.
    if (highDensityPhase && role == "healer" && densityTank
        && observedListedAttackerCount(bot)
        && UnitHealthPct(bot) > 0.45f && UnitHealthPct(densityTank) > 0.40f
        && bot->GetExactDist2d(densityTank) > 6.0f
        && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling()
        && !(state.ActivePathValid && state.IsMoving))
    {
        Unit* approachFrom = add ? add : densityTank;
        Position pickup = densityTank->GetFirstCollisionPosition(4.0f,
            approachFrom->GetAngle(densityTank) - densityTank->GetOrientation());
        if (manager.MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
        {
            std::string raw = manager.BuildRawJson(bot, add);
            std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            manager.RecordEvent(state, bot, "boss_adds", add, "healer_stack_for_swarm_pickup",
                raw.c_str(), semantic.c_str(), bot->GetExactDist2d(densityTank), addCount);
            state.TargetGuid = densityTank->GetVictim()
                ? densityTank->GetVictim()->GetGUID() : (add ? add->GetGUID() : ObjectGuid::Empty);
            target = densityTank->GetVictim() ? densityTank->GetVictim() : add;
            situation = "dungeon_boss";
            action = "healer_stack_for_swarm_pickup";
            return true;
        }
    }

    if (highDensityPhase && role == "healer" && request.TryRouteGroupHeal(bot, add))
        return true;

    if (highDensityPhase
        && nearbyAddCount >= 3
        && !profile.MissingProfile
        && profile.MovementDirective != "melee"
        && manager.Party().ValidationRouteBossAddEscapeActive
        && manager.Party().ValidationRouteBossAddEscapeGeneration == manager.Party().ValidationRouteGeneration
        && !bot->HasUnitState(UNIT_STATE_CASTING)
        && !bot->IsFalling())
    {
        bool reachedEscape = bot->GetExactDist2d(manager.Party().ValidationRouteBossAddEscapeX, manager.Party().ValidationRouteBossAddEscapeY) <= 2.5f;
        bool escapeIssued = manager.Party().ValidationRouteBossAddEscapeIssuedGuids.find(bot->GetGUID()) != manager.Party().ValidationRouteBossAddEscapeIssuedGuids.end();
        constexpr float escapePathEpsilon = 0.5f;
        bool escapePathPending = state.ActivePathValid
            && state.IsMoving
            && std::fabs(state.ActivePathToX - manager.Party().ValidationRouteBossAddEscapeX) <= escapePathEpsilon
            && std::fabs(state.ActivePathToY - manager.Party().ValidationRouteBossAddEscapeY) <= escapePathEpsilon
            && std::fabs(state.ActivePathToZ - manager.Party().ValidationRouteBossAddEscapeZ) <= escapePathEpsilon;
        bool shouldIssueEscape = !reachedEscape && !escapePathPending;
        if (!reachedEscape && shouldIssueEscape
            && manager.MoveBotToPoint(state, bot, manager.Party().ValidationRouteBossAddEscapeX, manager.Party().ValidationRouteBossAddEscapeY, manager.Party().ValidationRouteBossAddEscapeZ))
        {
            std::string raw = manager.BuildRawJson(bot, add);
            std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
            manager.RecordEvent(state, bot, "boss_add_density", add, escapeIssued ? "reissue_shared_escape_unreached" : "move_to_shared_escape", raw.c_str(), semantic.c_str(), float(nearbyAddCount), addCount);
            manager.Party().ValidationRouteBossAddEscapeIssuedGuids.insert(bot->GetGUID());
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = "move_to_boss_add_density_escape";
            return true;
        }
        if (!reachedEscape && escapePathPending)
        {
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = "continue_to_boss_add_density_escape";
            return true;
        }
    }
    if (role == "healer")
    {
        if (request.ReturnFalse)
            *request.ReturnFalse = true;
        return false;
    }
    return false;
}

bool TryHighDensityPositioning(
    HighDensityPositioningRequest const& request)
{
    return Context::Run(request);
}
}
