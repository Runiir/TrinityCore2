#include "Bots/BotWorldPopulationMgr.h"

#include "DataStores/DBCStores.h"
#include "Player.h"
#include "Unit.h"

#include <string>

bool BotWorldPopulationMgr::TryValidationRouteActivation(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, Unit* seenTarget, char const* reason)
{
    (void)reason;
    if ((!Cohort().Config.ValidationRouteActivationAreaTriggerId
        && !Cohort().Config.ValidationRouteActivationDataId
        && !Cohort().Config.ValidationRouteActivationSpawnGroupId
        && (!Cohort().Config.ValidationRouteActivationActionEntry || !Cohort().Config.ValidationRouteActivationActionId)
        && !Cohort().Config.ValidationRouteActivationSummonEntry
        && !Cohort().Config.ValidationRouteOpenerSummonEntry) || !bot
        || !bot->GetSession())
        return false;

    // A real client reports DBC area-trigger crossings with
    // CMSG_AREATRIGGER. Server-side bots have a native WorldSession but no
    // client process, so walking through the volume alone cannot start
    // encounters such as Corborus or Slabhide. Submit the same opcode only
    // after the native radius check accepts the tank's real position. This
    // preserves the encounter script as authority and never falls back to
    // privileged InstanceScript::SetData activation.
    if (uint32 triggerId = Cohort().Config.ValidationRouteActivationAreaTriggerId)
    {
        if (std::string(GetDungeonRole(bot)) != "tank")
            return false;

        AreaTriggerEntry const* trigger = sAreaTriggerStore.LookupEntry(triggerId);
        if (!trigger || trigger->ContinentID != bot->GetMapId())
        {
            if (!state.ValidationRouteActivationAttempts)
            {
                state.ValidationRouteActivationAttempts = 1;
                std::string raw = BuildRawJson(bot, seenTarget);
                std::string semantic = BuildSemanticJson(bot, seenTarget,
                    "validation_route_activation", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_activation", seenTarget,
                    "native_area_trigger_unavailable", raw.c_str(),
                    semantic.c_str(), 0.0f, triggerId);
            }
            return false;
        }

        if (!bot->IsInAreaTriggerRadius(trigger))
        {
            BotActionArbitration::Outcome moveOutcome =
                ExecuteNativeActionIntent(state, bot,
                BotNativeAction::Move{ trigger->Pos.X, trigger->Pos.Y,
                    trigger->Pos.Z },
                BotMovementArbitration::Owner::Route,
                BotMovementArbitration::Priority::Route);
            bool moved = moveOutcome.Result
                == BotActionArbitration::Disposition::Committed;
            if (!state.ValidationRouteActivationAttempts)
            {
                state.ValidationRouteActivationAttempts = 1;
                std::string raw = BuildRawJson(bot, seenTarget);
                std::string semantic = BuildSemanticJson(bot, seenTarget,
                    "validation_route_activation", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_activation", seenTarget,
                    moved ? "native_area_trigger_path" : "native_area_trigger_path_rejected",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(trigger->Pos.X, trigger->Pos.Y,
                        trigger->Pos.Z), triggerId);
            }
            return moved;
        }

        BotActionArbitration::Outcome activationOutcome =
            ExecuteNativeActionIntent(state, bot,
                BotNativeAction::AreaTrigger{ triggerId },
                BotMovementArbitration::Owner::Route,
                BotMovementArbitration::Priority::Route);
        if (activationOutcome.Result
            != BotActionArbitration::Disposition::Committed)
            return false;
        ++Party().ValidationRouteActivationAttempts;
        Party().ValidationRouteActivationApplied = true;
        state.ValidationRouteActivationAttempts =
            Party().ValidationRouteActivationAttempts;
        state.ValidationRouteActivationApplied = true;
        std::string raw = BuildRawJson(bot, seenTarget);
        std::string semantic = BuildSemanticJson(bot, seenTarget,
            "validation_route_activation", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_activation", seenTarget,
            "native_area_trigger_submitted", raw.c_str(), semantic.c_str(),
            0.0f, triggerId);
        return true;
    }

    // These legacy fields describe privileged server-side activation
    // (SetData, SpawnGroupSpawn, AI::DoAction, or SummonCreature). They are
    // never executed by autonomous bots. Encounter modules must instead
    // propose normal gossip/spell-click/attack/area-trigger interactions.
    if (!state.ValidationRouteActivationAttempts)
    {
        state.ValidationRouteActivationAttempts = 1;
        std::string raw = BuildRawJson(bot, seenTarget);
        std::string semantic = BuildSemanticJson(bot, seenTarget,
            "validation_route_activation", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_activation", seenTarget,
            "native_player_interaction_required", raw.c_str(),
            semantic.c_str(), 0.0f,
            Cohort().Config.ValidationRouteActivationActionEntry);
    }
    return false;
}

