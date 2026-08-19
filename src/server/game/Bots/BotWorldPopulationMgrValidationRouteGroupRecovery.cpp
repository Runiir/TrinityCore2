#include "Bots/BotWorldPopulationMgrValidationRouteGroupRecovery.h"

#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotActionArbiter.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Group.h"
#include "GroupReference.h"
#include "MotionMaster.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <sstream>
#include <string>

using BotWorldPopulationMgrNativeHelpers::Distance2d;
using BotWorldPopulationMgrNativeHelpers::HasPowerForSpell;
using BotWorldPopulationMgrNativeHelpers::IsNativeCombatResSpell;
using BotWorldPopulationMgrSpellSemantics::NowMs;

bool BotWorldPopulationMgr::TryValidationRouteGroupRecovery(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action, Unit*& target, bool discoveryLeg,
    ValidationRouteGroupRecoveryCallbacks const& callbacks)
{
    BotWorldPopulationMgrValidationRoute::GroupRecoveryRequest request;
    request.Manager = this;
    request.State = &state;
    request.Bot = bot;
    request.Power = &power;
    request.Stage = stage;
    request.Activity = activity;
    request.Situation = &situation;
    request.Action = &action;
    request.Target = &target;
    request.DiscoveryLeg = discoveryLeg;
    request.Callbacks = callbacks;
    return BotWorldPopulationMgrValidationRoute::TryValidationRouteGroupRecovery(
        request);
}

namespace BotWorldPopulationMgrValidationRoute
{
GroupRecoveryContext::GroupRecoveryContext(GroupRecoveryRequest const& request)
    : Manager(*request.Manager), State(*request.State), Bot(request.Bot),
      Power(*request.Power), Stage(request.Stage), Activity(request.Activity),
      Situation(*request.Situation), Action(*request.Action),
      Target(*request.Target), DiscoveryLeg(request.DiscoveryLeg),
      Callbacks(request.Callbacks)
{
}

bool GroupRecoveryContext::Run()
{
    bool currentLivePackCanContinue =
        Manager.CurrentLiveValidationRoutePackCanContinue(
            Callbacks.PersistedPackHasLiveMembers,
            Callbacks.IsPackEntry,
            Callbacks.ResolvedTransitionAura);
    // Refresh discovery-pack membership before any recovery/terminal branch.
    // Active target selection can bypass findTrashClusterThreatTarget once a
    // persisted member exists, so relying on that resolver alone leaves a
    // newly engaged adjacent creature outside the shared pack ledger.
    if (DiscoveryLeg)
        Callbacks.EnrollEngagedPackMembers();
    // If most of the party or a critical role is dead and no living class can
    // legally resurrect in combat, continuing at the abandoned pack cannot
    // recover the group. Retreat through ordinary movement so the hostile
    // exceeds its home leash, then end the survivors' combat references together
    // at the fallback anchor so native out-of-combat resurrection can run.
    if (Bot->IsAlive() && Bot->GetGroup())
    {
        uint32 aliveMembers = 0;
        uint32 deadMembers = 0;
        bool criticalRoleDead = false;
        bool groupCombatActive = false;
        bool livingCombatResurrectionCaster = false;
        Unit* retreatThreat = nullptr;
        for (GroupReference* itr = Bot->GetGroup()->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != Bot->GetMap())
                continue;
            if (member->IsAlive())
            {
                ++aliveMembers;
                groupCombatActive = groupCombatActive || member->IsInCombat() || member->GetVictim() || !member->getAttackers().empty();
                if (!retreatThreat && std::string(Manager.GetDungeonRole(member)) == "tank")
                    retreatThreat = member->GetVictim();
                for (auto const& [spellId, playerSpell] : member->GetSpellMap())
                {
                    if (playerSpell.state == PLAYERSPELL_REMOVED || playerSpell.disabled || !playerSpell.active || !member->HasSpell(spellId))
                        continue;
                    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
                    if (IsNativeCombatResSpell(spellInfo)
                        && member->GetSpellHistory()->IsReady(spellInfo) && HasPowerForSpell(member, spellInfo))
                    {
                        livingCombatResurrectionCaster = true;
                        break;
                    }
                }
            }
            else
            {
                ++deadMembers;
                std::string role = Manager.GetDungeonRole(member);
                criticalRoleDead = criticalRoleDead || role == "tank" || role == "healer";
            }
        }
        bool majorityDead = aliveMembers <= 2 && deadMembers >= 3;
        // The Drudge lane contract is a native-mechanics observation, not a
        // recoverable trash route.  Once any exact roster member dies while
        // the pack is active, hold only newly issued bot offense and leave
        // threat, movement, corpses, and reset authority to the encounter.
        // This keeps a four-death tactical retreat from masquerading as a
        // clean lane generation; the native wipe gate will terminate it.
        if (Manager.Cohort().Config.ValidationRouteMechanicProfile == "trash_two_tank_charge_lanes"
            && Manager.Cohort().Config.ValidationRouteBossRecovery
                == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
            && deadMembers > 0)
        {
            bool const threatSeedCompleteForCurrentScope =
                Manager.Party().ValidationRouteDrudgeThreatSeedComplete
                && !Manager.Party().ValidationRouteDrudgeThreatSeedFailure
                && Manager.Party().ValidationRouteDrudgeThreatSeedAttemptId == Manager.Cohort().AttemptId
                && Manager.Party().ValidationRouteDrudgeThreatSeedWipeGeneration
                    == Manager.Cohort().Raid.WipeGeneration
                && Manager.Party().ValidationRouteDrudgeThreatSeedRouteGeneration
                    == Manager.Party().ValidationRouteGeneration;
            if (!threatSeedCompleteForCurrentScope)
            {
                for (WorldBotState const& cohortState : Manager.Party().Bots)
                    if (Player* cohortBot = Manager.GetLoadedBot(cohortState))
                        BotRaidAreaAuthority::SetAllOffenseSuppressed(
                            cohortBot->GetGUID().GetRawValue(), true);
                Manager.Cohort().ValidationAttemptFailureReason =
                    "drudge_partial_death_before_threat_seed";
                Manager.Cohort().ValidationAttemptFailureAttemptId = Manager.Cohort().AttemptId;
                Manager.Cohort().ValidationAttemptFailureRouteGeneration =
                    Manager.Party().ValidationRouteGeneration;
                Callbacks.MarkTrashFailed(retreatThreat,
                    "drudge_partial_death_before_threat_seed",
                    "validation_route_recovery", float(aliveMembers), deadMembers,
                    -1.0f, 0, 0);
                State.LastRecoveryMode = "terminal_restart_required";
                State.LastRecoveryResult = "drudge_partial_death_before_threat_seed";
                State.LastRecoveryMs = NowMs();
                Situation = "validation_route_recovery";
                Action = "validation_route_failed";
                Target = retreatThreat;
                return true;
            }
            if (groupCombatActive)
            {
                for (WorldBotState const& cohortState : Manager.Party().Bots)
                    if (Player* cohortBot = Manager.GetLoadedBot(cohortState))
                        BotRaidAreaAuthority::SetAllOffenseSuppressed(
                            cohortBot->GetGUID().GetRawValue(), true);
                std::string raw = Manager.BuildRawJson(Bot, retreatThreat);
                std::ostringstream gateRaw;
                gateRaw << "{\"base\":" << raw
                        << ",\"drudge_native_recovery_gate\":{\"policy\":\"native_full_wipe_only\""
                        << ",\"authority\":\"native_encounter\""
                        << ",\"assistance\":\"none\""
                        << ",\"direct_respawn\":false"
                        << ",\"direct_state_manufacture\":false"
                        << ",\"alive_members\":" << aliveMembers
                        << ",\"dead_members\":" << deadMembers << "}}";
                std::string semantic = Manager.BuildSemanticJson(Bot, retreatThreat, "validation_route_recovery", &Power, Stage, Activity);
                Manager.RecordEvent(State, Bot, "validation_route_recovery", retreatThreat,
                    "drudge_native_full_wipe_hold_partial_death", gateRaw.str().c_str(), semantic.c_str(),
                    float(aliveMembers), deadMembers);
                State.LastRecoveryMode = "native_full_wipe_only";
                State.LastRecoveryResult = "drudge_native_full_wipe_hold_partial_death";
                State.LastRecoveryMs = NowMs();
                State.LastNoProgressReason = "drudge_native_full_wipe_hold_partial_death";
                Situation = "validation_route_recovery";
                Action = "native_full_wipe_hold";
                Target = retreatThreat;
                return true;
            }
        }
        if ((majorityDead || criticalRoleDead) && groupCombatActive && !livingCombatResurrectionCaster
            && !currentLivePackCanContinue)
        {
            if (Manager.Cohort().Config.ValidationRouteBossRecovery == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly)
            {
                std::string raw = Manager.BuildRawJson(Bot, retreatThreat);
                std::ostringstream gateRaw;
                gateRaw << "{\"base\":" << raw
                        << ",\"native_recovery_gate\":{\"policy\":\"native_full_wipe_only\""
                        << ",\"authority\":\"native_encounter\""
                        << ",\"assistance\":\"none\""
                        << ",\"direct_respawn\":false"
                        << ",\"direct_state_manufacture\":false"
                        << ",\"alive_members\":" << aliveMembers
                        << ",\"dead_members\":" << deadMembers
                        << ",\"critical_role_dead\":" << (criticalRoleDead ? "true" : "false") << "}}";
                std::string semantic = Manager.BuildSemanticJson(Bot, retreatThreat, "validation_route_recovery", &Power, Stage, Activity);
                Manager.RecordEvent(State, Bot, "validation_route_recovery", retreatThreat,
                    "native_full_wipe_hold_partial_death", gateRaw.str().c_str(), semantic.c_str(),
                    float(aliveMembers), deadMembers);
                State.LastRecoveryMode = "native_full_wipe_only";
                State.LastRecoveryResult = "native_full_wipe_hold_partial_death";
                State.LastRecoveryMs = NowMs();
                State.LastNoProgressReason = "native_full_wipe_hold_partial_death";
                Situation = "validation_route_recovery";
                Action = "native_full_wipe_hold";
                Target = retreatThreat;
                return true;
            }

            if (!retreatThreat)
                retreatThreat = Bot->GetVictim();
            float retreatX = Manager.Cohort().Config.ValidationRouteX;
            float retreatY = Manager.Cohort().Config.ValidationRouteY;
            float retreatZ = Manager.Cohort().Config.ValidationRouteZ;
            char const* retreatDestination = "route_anchor";
            if (Manager.Party().ValidationRouteManifestIndex > 0
                && Manager.Party().ValidationRouteManifestIndex < Manager.Party().ValidationRouteManifest.size())
            {
                ValidationRouteManifestNode const& previousNode = Manager.Party().ValidationRouteManifest[Manager.Party().ValidationRouteManifestIndex - 1];
                if ((!previousNode.MapId || previousNode.MapId == Bot->GetMapId())
                    && Distance2d(previousNode.NavigationAnchorX, previousNode.NavigationAnchorY,
                        Manager.Cohort().Config.ValidationRouteX, Manager.Cohort().Config.ValidationRouteY) > 20.0f)
                {
                    // The manifest anchor is a previously traversed, accepted
                    // route point. A straight-line inset toward the next node
                    // can cross disconnected terrain and synthesize an invalid
                    // Z before pathfinding gets a chance to validate the route.
                    retreatX = previousNode.NavigationAnchorX;
                    retreatY = previousNode.NavigationAnchorY;
                    retreatZ = previousNode.NavigationAnchorZ;
                    retreatDestination = "previous_route_anchor";
                }
            }

            bool livingMembersAtRetreatAnchor = true;
            for (GroupReference* itr = Bot->GetGroup()->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != Bot->GetMap())
                    continue;
                if (member->GetExactDist(retreatX, retreatY, retreatZ) > 5.0f)
                {
                    livingMembersAtRetreatAnchor = false;
                    break;
                }
            }

            uint64 nowMs = NowMs();
            if (livingMembersAtRetreatAnchor)
            {
                for (WorldBotState& cohortState : Manager.Party().Bots)
                {
                    // Bind every living cohort member to the same ordinary
                    // movement rendezvous. Native combat/evade and corpse
                    // recovery remain authoritative.
                    cohortState.ValidationRouteAnchorOverrideValid = true;
                    cohortState.ValidationRouteAnchorOverrideUntilMs = nowMs + 120000;
                    cohortState.ValidationRouteAnchorOverrideX = retreatX;
                    cohortState.ValidationRouteAnchorOverrideY = retreatY;
                    cohortState.ValidationRouteAnchorOverrideZ = retreatZ;
                    cohortState.ValidationRouteAnchorOverrideReason = "validation_route_partial_wipe_retreat_rendezvous";

                    Player* cohortBot = Manager.GetLoadedBot(cohortState);
                    if (!cohortBot || !cohortBot->IsAlive() || cohortBot->GetMap() != Bot->GetMap())
                        continue;
                    Manager.SubmitMeleeAutoAttackIntent(cohortState,
                        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                        BotMeleeAutoAttack::Owner::Recovery,
                        BotActionArbitration::Priority::Survival,
                        "partial_wipe_retreat_rendezvous");
                    cohortState.TargetGuid.Clear();
                    cohortBot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                    cohortState.WasInCombat = cohortBot->IsInCombat();
                    cohortState.ActivePathValid = false;
                    cohortState.IsMoving = false;
                }

                std::string raw = Manager.BuildRawJson(Bot, retreatThreat);
                std::string semantic = Manager.BuildSemanticJson(Bot, retreatThreat, "validation_route_recovery", &Power, Stage, Activity);
                std::string retreatReason = std::string("partial_wipe_retreat_arrived_") + retreatDestination;
                Manager.RecordEvent(State, Bot, "validation_route_recovery", retreatThreat,
                    retreatReason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, deadMembers);
                State.LastRecoveryMode = "tactical_retreat_no_combat_res";
                State.LastRecoveryResult = std::string("retreat_arrived_") + retreatDestination;
                State.LastRecoveryMs = nowMs;
                ++State.RecoveryAttemptCount;
                Situation = "validation_route_recovery";
                Action = "validation_route_retreat_arrived";
                Target = nullptr;
                return true;
            }

            Manager.SubmitMeleeAutoAttackIntent(State,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Recovery,
                BotActionArbitration::Priority::Survival,
                "tactical_retreat_no_combat_res");
            State.TargetGuid.Clear();
            bool moved = Manager.MoveBotToPoint(State, Bot, retreatX, retreatY, retreatZ);
            if (State.LastRecoveryMode != "tactical_retreat_no_combat_res" || nowMs - State.LastRecoveryMs >= 5000)
            {
                std::string raw = Manager.BuildRawJson(Bot, retreatThreat);
                std::string semantic = Manager.BuildSemanticJson(Bot, retreatThreat, "validation_route_recovery", &Power, Stage, Activity);
                std::string retreatReason = std::string(moved ? "tactical_retreat_no_combat_res_" : "hold_tactical_retreat_no_combat_res_") + retreatDestination;
                Manager.RecordEvent(State, Bot, "validation_route_recovery", retreatThreat,
                    retreatReason.c_str(), raw.c_str(), semantic.c_str(), Bot->GetExactDist(retreatX, retreatY, retreatZ), deadMembers);
                State.LastRecoveryMode = "tactical_retreat_no_combat_res";
                State.LastRecoveryResult = std::string(moved ? "moving_" : "holding_") + retreatDestination;
                State.LastRecoveryMs = nowMs;
                ++State.RecoveryAttemptCount;
            }
            Situation = "validation_route_recovery";
            Action = moved ? "validation_route_tactical_retreat" : "validation_route_hold_retreat";
            Target = nullptr;
            return true;
        }
    }
    Callbacks.RetireStalePackMembers();
    return false;
}

bool TryValidationRouteGroupRecovery(GroupRecoveryRequest const& request)
{
    GroupRecoveryContext context(request);
    return context.Run();
}
}
