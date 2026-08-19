#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveTankPreparation.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Creature.h"
#include "Player.h"
#include "Spell.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <functional>
#include <limits>
#include <vector>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

AddWaveTankPreparationResult Context::Run(
    AddWaveTankPreparationRequest const& request)
{
    AddWaveTankPreparationResult result;
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;

    Unit* add = density.Add;
    bool sharedFocusValid = density.SharedFocusValid;
    uint32 addCount = discovery.AddCount;
    uint32 engagedAddCount = discovery.EngagedAddCount;
    bool cohortSwarmActive = discovery.CohortSwarmActive;
    std::vector<Creature*> const& localAdds = discovery.LocalAdds;
    std::function<bool(Player*, Unit*)> const& isUsableListedAdd =
        discovery.IsUsableListedAdd;
    std::string const& role = density.Role;
    BotClassSpecActionProfile const& profile = density.Profile;
    Player* densityHealer = density.DensityHealer;
    Player* densityDefenseTarget = density.DensityDefenseTarget;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;

    // Aim area threat at a representative of the densest listed attacker
    // cluster. Selecting only the closest healer attacker could place a
    // ground effect on the edge of an Azil wave and move self-centered AoE
    // away from most of the swarm. Distance and GUID remain deterministic
    // tie-breakers after local cluster coverage.
    static constexpr float TankDensityClusterRadius = 10.0f;
    if (role == "tank" && densityDefenseTarget)
    {
        std::vector<Unit*> densityDefenseAttackers;
        for (Creature* candidate : localAdds)
            if (candidate && candidate->GetVictim() == densityDefenseTarget
                && bot->IsWithinLOSInMap(candidate))
                densityDefenseAttackers.push_back(candidate);
        if (densityDefenseAttackers.empty())
            for (Unit* attacker : densityDefenseTarget->getAttackers())
                if (isUsableListedAdd(bot, attacker) && bot->IsWithinLOSInMap(attacker))
                    densityDefenseAttackers.push_back(attacker);

        Unit* densityClusterAttacker = nullptr;
        uint32 densityClusterCount = 0;
        float densityClusterDistance = std::numeric_limits<float>::max();
        uint32 densityClusterGuid = std::numeric_limits<uint32>::max();
        for (Unit* attacker : densityDefenseAttackers)
        {
            uint32 localClusterCount = 0;
            for (Unit* neighbor : densityDefenseAttackers)
                if (attacker->GetExactDist2d(neighbor) <= TankDensityClusterRadius)
                    ++localClusterCount;

            float distance = bot->GetExactDist(attacker);
            uint32 guid = attacker->GetGUID().GetCounter();
            if (!densityClusterAttacker || localClusterCount > densityClusterCount
                || (localClusterCount == densityClusterCount
                    && (distance < densityClusterDistance
                        || (distance == densityClusterDistance && guid < densityClusterGuid))))
            {
                densityClusterAttacker = attacker;
                densityClusterCount = localClusterCount;
                densityClusterDistance = distance;
                densityClusterGuid = guid;
            }
        }
        if (densityClusterAttacker)
        {
            add = densityClusterAttacker;
            sharedFocusValid = false;
        }
    }

    // Rerun64 proved that passive-cluster preposition can hand a large wave
    // to the Feral quickly enough to expose an ordering gap: pickup actions
    // continued while native defensives were suppressed by healer ownership,
    // and the tank died after acquiring most of a 60-follower wave. Feral
    // defensives are off the global cooldown, so submit one at the existing
    // health/add thresholds and continue through the same decision to native
    // threat pickup. Exact hazard movement has already run before this block.
    if (role == "tank" && profile.SpecTag == "feral_druid_tank"
        && cohortSwarmActive && addCount >= 12
        && UnitHealthPct(bot) <= 0.90f
        && !bot->HasAura(61336) && !bot->HasAura(22812))
    {
        std::array<uint32, 2> defensiveSpells = { 61336, 22812 };
        for (uint32 defensiveSpellId : defensiveSpells)
            if (bot->HasSpell(defensiveSpellId)
                && manager.TryCastFriendlySpell(bot, bot, defensiveSpellId))
            {
                std::string raw = manager.BuildRawJson(bot, add);
                std::string semantic = manager.BuildSemanticJson(
                    bot, add, "dungeon_boss", &power,
                    request.Stage, request.Activity);
                manager.RecordEvent(state, bot, "defensive", bot,
                    "tank_swarm_defensive", raw.c_str(), semantic.c_str(),
                    UnitHealthPct(bot), addCount, defensiveSpellId);
                break;
            }
    }

    // Build native Roar pickup as a deferred action. Charge ownership and
    // arrival proof run first below; otherwise a legal edge Roar can preempt
    // the bounded charge one decision after launch. Cast only once the tank
    // is centered on the stationary healer's melee ring or already covers a
    // deterministic majority of the healer-owned wave. This preserves the
    // passive split-cluster pickup while avoiding low-coverage edge casts.
    // Rerun98 passed both Feral retention gates, but two Azil waves cleared
    // at 3018 ms and 3012 ms. Rerun100 then began 60/60 tank-owned and lost
    // 29 followers to the healer exactly 3013 ms after activation; waiting
    // for healer ownership before lowering the cadence was already too
    // late for the first acquisition-eligible snapshot. Sample any real
    // active three-or-more-add Feral swarm at the established lower bound.
    if (role == "tank" && profile.SpecTag == "feral_druid_tank"
        && cohortSwarmActive)
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 500);

    // Rerun148 observed twenty already-engaged Azil followers remain in a
    // pre-victim state for four decisions while the Feral preserved an
    // ordinary stable melee approach. The wave was older than the strict
    // acquisition grace when healing threat assigned nineteen followers
    // at once. Poll only that declared high-density, zero-healer-attacker
    // window at the established specialized pickup cadence so the existing
    // native area resolver can submit as soon as two followers enter range.
    // No target, victim, path, spell, or threat semantics change here.
    if (role == "tank" && profile.SpecTag == "feral_druid_tank"
        && engagedAddCount >= 12 && densityHealer
        && observedListedAttackerCount(densityHealer) == 0)
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);

    // Rerun162 proved the same bounded Protection pickup cadence is needed
    // for a declared healer-density handoff even when the encounter has not
    // classified the wave as a cohort swarm. The density healer plus two
    // listed attackers (or twelve engaged adds) remains the narrow gate.
    // Spell order, movement, victims, cooldowns, legality, and threat remain
    // unchanged below.
    if (role == "tank" && profile.SpecTag == "protection"
        && densityHealer
        && (engagedAddCount >= 12
            || observedListedAttackerCount(densityHealer) >= 2))
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);

    result.Add = add;
    result.SharedFocusValid = sharedFocusValid;
    return result;
}

AddWaveTankPreparationResult PrepareAddWaveTank(
    AddWaveTankPreparationRequest const& request)
{
    return Context::Run(request);
}
}
