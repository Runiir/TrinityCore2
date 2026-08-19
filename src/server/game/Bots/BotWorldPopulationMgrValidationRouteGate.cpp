#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Map.h"
#include "MotionMaster.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::HasPowerForSpell;
using BotWorldPopulationMgrSpellSemantics::NowMs;

bool BotWorldPopulationMgr::TryValidationRouteObjectiveGate(
    WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power,
    BotProgressionStage stage, BotProgressionActivity activity,
    std::string& situation, std::string& action, Unit*& target,
    bool& arrivalRoute)
{
    arrivalRoute = false;
    if (!bot)
        return false;

    uint64 const raidAuthorityOwner = bot->GetGUID().GetRawValue();
    if (!Cohort().Config.ValidationRouteEnable)
    {
        BotRaidAreaAuthority::Clear(raidAuthorityOwner);
        return false;
    }

    // A native full-wipe recovery is an evidence gate, not a route decision.
    // Keep every exact-roster member stationary and all hostile authority
    // suppressed until corpse, release, runback, re-entry, resurrection, the
    // native reset, and the post-recovery ready check have all been observed.
    if (IsNativeRaidRecoveryEvidencePending())
    {
        SuppressNativeRaidRecovery(state, bot);
        target = nullptr;
        situation = "native_recovery_evidence";
        action = "hold_native_recovery_evidence";
        return true;
    }

    ConfigureValidationRouteCombatAuthority(bot);

    arrivalRoute = Cohort().Config.ValidationRouteKind == "travel" || Cohort().Config.ValidationRouteKind == "regroup" || Cohort().Config.ValidationRouteKind == "descent";
    situation = Cohort().Config.ValidationRouteKind == "boss"
        ? (bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss")
        : (arrivalRoute ? "validation_route_regroup" : "validation_route");
    action = "validation_route";

    if (Cohort().Config.ValidationRouteMapId && bot->GetMapId() != Cohort().Config.ValidationRouteMapId)
    {
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_wrong_map", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_failed", nullptr, "wrong_map", raw.c_str(), semantic.c_str(), float(Cohort().Config.ValidationRouteMapId), bot->GetMapId());
        action = "validation_route_wrong_map";
        return true;
    }

    if (Party().ValidationRouteManifestComplete)
    {
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Stop, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Route,
            BotActionArbitration::Priority::Mechanic,
            "validation_route_manifest_complete");
        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        state.ActivePathValid = false;
        state.IsMoving = false;
        state.StuckTimer = 0;
        state.TargetGuid.Clear();
        state.WasInCombat = false;
        state.ValidationRouteTerminalState = true;
        state.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
        if (!state.ValidationRouteTerminalAtMs)
            state.ValidationRouteTerminalAtMs = NowMs();
        if (state.ValidationRouteTerminalReason.empty())
            state.ValidationRouteTerminalReason = "all_routes_complete";
        state.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
        situation = "validation_route_manifest";
        action = "validation_route_complete";
        return true;
    }

    BotClassSpecActionProfile cadenceProfile = BotClassSpecActionProfileStore::Build(bot, GetDungeonRole(bot));
    if (cadenceProfile.SpecTag == "feral_druid_tank")
    {
        Creature* healerThreatAttacker = nullptr;
        uint32 healerThreatAttackerCount = 0;
        float healerThreatDistance = std::numeric_limits<float>::max();
        uint32 healerThreatGuid = std::numeric_limits<uint32>::max();
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 45.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 45.0f);
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            Player* victim = creature && creature->GetVictim()
                ? creature->GetVictim()->ToPlayer() : nullptr;
            if (!creature || !creature->IsAlive() || !creature->GetHealth()
                || !bot->IsValidAttackTarget(creature)
                || !victim || GetDungeonRole(victim) != "healer"
                || (bot->GetGroup()
                    ? victim->GetGroup() != bot->GetGroup()
                    : victim != bot))
                continue;

            ++healerThreatAttackerCount;
            float distance = bot->GetExactDist(creature);
            uint32 guid = creature->GetGUID().GetCounter();
            if (!healerThreatAttacker || distance < healerThreatDistance
                || (distance == healerThreatDistance && guid < healerThreatGuid))
            {
                healerThreatAttacker = creature;
                healerThreatDistance = distance;
                healerThreatGuid = guid;
            }
        }

        if (healerThreatAttacker)
        {
            // Rerun134 proved the specialized handoff and hazard branches poll at
            // 250 ms, but generic route and density transitions can still consume
            // a full second while a current hostile remains on the healer. Change
            // only the next-decision cadence while that exact exposure is visible.
            state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);

            // Rerun168 observed a post-recovery pair already attacking the healer
            // while this Feral tank was out of combat and out of Bear Form. The
            // ordinary route profile spent 2556 ms approaching before restoring
            // the form, so the first Growl arrived after the 3000-ms dwell ceiling.
            // Restore only the native tank form while exact healer threat is
            // visible, then let the unchanged 250-ms recovery cadence retry.
            if (!bot->HasAura(5487) && bot->HasSpell(5487)
                && TryCastFriendlySpell(bot, bot, 5487))
            {
                std::string raw = BuildRawJson(bot, healerThreatAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, healerThreatAttacker,
                    "validation_route_threat_pickup",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    healerThreatAttacker,
                    "feral_bear_form_healer_threat_before_recovery",
                    raw.c_str(), semantic.c_str(), healerThreatDistance,
                    Cohort().Config.ValidationRouteTargetEntry, 5487);
                target = healerThreatAttacker;
                situation = "validation_route_threat_pickup";
                action = "feral_bear_form_healer_threat_before_recovery";
                return true;
            }

            // Rerun147's only dwell failure was one remote healer attacker.
            // Growl became legal in the same decision that this global cadence
            // block submitted Stampeding Roar; the speed cast consumed the GCD,
            // then the existing remote handoff consumed the first post-GCD
            // decision. Preserve the movement accelerator for clusters, but
            // give the exact single-hostile native taunt its normal priority.
            if (healerThreatAttackerCount == 1 && bot->HasSpell(6795)
                && TryCastCombatSpell(bot, healerThreatAttacker, 6795))
            {
                std::string raw = BuildRawJson(bot, healerThreatAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, healerThreatAttacker,
                    "validation_route_threat_pickup",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    healerThreatAttacker,
                    "feral_growl_single_healer_threat_before_roar",
                    raw.c_str(), semantic.c_str(), healerThreatDistance,
                    Cohort().Config.ValidationRouteTargetEntry, 6795);
                state.WasInCombat = true;
                target = healerThreatAttacker;
                situation = "validation_route_threat_pickup";
                action = "feral_growl_single_healer_threat_before_roar";
                return true;
            }

            // Rerun136 closed the cadence gap but spent the failed 3.3-5.6 second
            // episodes preserving already-accepted handoff, swarm-approach, and
            // hazard-exit paths. Accelerate only that existing motion with the
            // native Bear-form speed action; never create, replace, or redirect a
            // path here, and fall through unchanged when the spell is unavailable.
            bool const reservedHealerThreatHandoff =
                state.FeralHealerThreatHandoffUntilMs > NowMs()
                && !state.FeralHealerThreatHandoffTargetGuid.IsEmpty()
                && !state.FeralHealerThreatHandoffAnchorGuid.IsEmpty();
            bool const activePathValid = state.ActivePathValid;
            bool const stateMoving = state.IsMoving;
            bool const hasSpell = bot->HasSpell(77761);
            bool const hasAura = bot->HasAura(77761);
            bool nativeChargeReadyForHealerThreat = false;
            if (healerThreatDistance > 8.0f && bot->HasSpell(16979)
                && bot->IsWithinLOSInMap(healerThreatAttacker)
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling())
                if (SpellInfo const* chargeInfo =
                        sSpellMgr->GetSpellInfo(16979))
                    nativeChargeReadyForHealerThreat =
                        healerThreatDistance
                            <= bot->GetSpellMaxRangeForTarget(
                                healerThreatAttacker, chargeInfo)
                        && !bot->GetSpellHistory()->HasGlobalCooldown(
                            chargeInfo)
                        && bot->GetSpellHistory()->IsReady(chargeInfo)
                        && HasPowerForSpell(bot, chargeInfo);
            bool castAttempted = false;
            bool castSubmitted = false;
            std::string failureReason;
            // Rerun168's active remote-cluster handoff was replaced by this
            // speed cast one decision before its native Charge branch. The cast
            // consumed the GCD, then the one-second reservation expired into
            // generic density movement while twelve hostiles owned the healer.
            // Preserve the exact bounded handoff so its existing identity checks
            // and Charge-first ordering remain authoritative.
            if (reservedHealerThreatHandoff)
                failureReason = "reserved_healer_threat_handoff";
            // Rerun176 observed the same ordering gap before a new reservation
            // existed: Stampeding Roar consumed the GCD while one remote Flayer
            // owned the healer, so the already-ready native Charge could not
            // submit and ground pickup crossed the strict grace window. Preserve
            // the downstream identity-scoped Charge controller whenever this
            // exact attacker is already inside its native legal band.
            else if (nativeChargeReadyForHealerThreat)
                failureReason = "native_charge_ready_for_healer_threat";
            // Rerun198's fourteen-healer Azil wave reached this global cadence
            // block while its native Charge was unavailable. Stampeding Roar
            // consumed the first GCD, so the specialized area pickup below did
            // not submit Demoralizing Roar until 1536 ms after exposure. Keep
            // the movement accelerator for one- and two-hostile recovery, but
            // reserve three-plus healer attackers for the existing native area
            // pickup controller. No victim or threat is changed here.
            else if (healerThreatAttackerCount >= 3)
                failureReason = "multi_healer_wave_native_pickup_reserved";
            else if (!activePathValid)
                failureReason = "inactive_path";
            else if (!stateMoving)
                failureReason = "state_not_moving";
            else if (!hasSpell)
                failureReason = "missing_spell";
            else if (hasAura)
                failureReason = "aura_active";
            else
            {
                castAttempted = true;
                castSubmitted = TryCastFriendlySpell(
                    bot, bot, 77761, &failureReason);
            }

            // Rerun138 provisioned the spell but observed neither a submission
            // nor enough evidence to distinguish the existing gates from a cast
            // rejection. Record every unchanged gate and the exact helper result
            // before preserving the original success or fallthrough behavior.
            std::ostringstream diagnosticRaw;
            diagnosticRaw
                << "{\"schema\":\"feral_stampeding_roar_gate_v1\""
                << ",\"healer_attacker_detected\":true"
                << ",\"healer_attacker_guid\":" << healerThreatGuid
                << ",\"healer_attacker_entry\":"
                << healerThreatAttacker->GetEntry()
                << ",\"healer_attacker_distance\":" << healerThreatDistance
                << ",\"reserved_healer_threat_handoff\":"
                << (reservedHealerThreatHandoff ? "true" : "false")
                << ",\"active_path_valid\":"
                << (activePathValid ? "true" : "false")
                << ",\"state_is_moving\":"
                << (stateMoving ? "true" : "false")
                << ",\"has_spell_77761\":"
                << (hasSpell ? "true" : "false")
                << ",\"has_aura_77761\":"
                << (hasAura ? "true" : "false")
                << ",\"cast_attempted\":"
                << (castAttempted ? "true" : "false")
                << ",\"cast_submitted\":"
                << (castSubmitted ? "true" : "false")
                << ",\"failure_reason\":\""
                << JsonEscape(failureReason) << "\"}";
            std::string diagnosticSemantic = BuildSemanticJson(
                bot, healerThreatAttacker,
                "validation_route_threat_pickup_diagnostic",
                &power, stage, activity);
            // Rerun139 proved rawJson does not survive this route's RunId-free
            // capture path. Keep the structured payload, but also bind the
            // already-computed rejection to the bounded trace result that does.
            std::string diagnosticResult = castSubmitted
                ? "feral_stampeding_roar_submitted"
                : "feral_stampeding_roar_not_submitted:" + failureReason;
            RecordEvent(state, bot,
                "validation_route_threat_pickup_diagnostic",
                healerThreatAttacker, diagnosticResult.c_str(),
                diagnosticRaw.str().c_str(), diagnosticSemantic.c_str(),
                healerThreatDistance,
                Cohort().Config.ValidationRouteTargetEntry,
                castAttempted ? 77761 : 0);

            if (castSubmitted)
            {
                std::string raw = BuildRawJson(bot, healerThreatAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, healerThreatAttacker, "validation_route_threat_pickup",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    healerThreatAttacker,
                    "feral_stampeding_roar_healer_threat_reposition",
                    raw.c_str(), semantic.c_str(), healerThreatDistance,
                    Cohort().Config.ValidationRouteTargetEntry, 77761);
                state.WasInCombat = true;
                target = healerThreatAttacker;
                situation = "validation_route_threat_pickup";
                action = "feral_stampeding_roar_healer_threat_reposition";
                return true;
            }
        }
    }
    return true;
}
