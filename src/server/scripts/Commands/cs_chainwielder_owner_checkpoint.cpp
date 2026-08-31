#include "Bots/BotWorldPopulationMgr.h"
#include "Chat.h"
#include "RBAC.h"
#include "ScriptMgr.h"

#include <sstream>
#include <string>
#include <vector>

class chainwielder_owner_checkpoint_commandscript : public CommandScript
{
public:
    chainwielder_owner_checkpoint_commandscript()
        : CommandScript("chainwielder_owner_checkpoint_commandscript") { }

    std::vector<ChatCommand> GetCommands() const override
    {
        static std::vector<ChatCommand> commandTable =
        {
            { "botautochaincheckpoint",
                rbac::RBAC_PERM_COMMAND_HEALERBOT, true,
                &HandleCheckpointCommand, "" },
            { "botautonativepathcheckpoint",
                rbac::RBAC_PERM_COMMAND_HEALERBOT, true,
                &HandleNativePathCheckpointCommand, "" },
        };
        return commandTable;
    }

private:
    static bool HandleNativePathCheckpointCommand(
        ChatHandler* handler, char const* args)
    {
        std::istringstream parser(args ? args : "");
        std::string action;
        parser >> action;
        std::string const cohortId =
            sBotWorldPopulationMgr->ResolveGlobalCohortId();
        std::string result;
        if (action == "status")
            result = sBotWorldPopulationMgr
                ->GetNativePathCheckpointJsonForCohort(cohortId);
        else if (action == "arm")
        {
            uint32 actorGuid = 0;
            std::string caseId;
            std::string sealSha256;
            std::string sourceCommit;
            std::string extra;
            parser >> actorGuid >> caseId >> sealSha256
                >> sourceCommit >> extra;
            if (!actorGuid || caseId.empty() || sealSha256.empty()
                || sourceCommit.empty() || !extra.empty())
                result = "{\"ok\":false,\"action\":"
                    "\"botauto_native_path_checkpoint\","
                    "\"failure_reason\":\"invalid_arguments\"}";
            else
                result = sBotWorldPopulationMgr
                    ->ArmNativePathCheckpointForCohort(cohortId, actorGuid,
                        caseId, sealSha256, sourceCommit);
        }
        else
            result = "{\"ok\":false,\"action\":"
                "\"botauto_native_path_checkpoint\","
                "\"failure_reason\":\"arm_or_status_required\"}";
        handler->SendSysMessage(result.c_str());
        return true;
    }

    static bool HandleCheckpointCommand(
        ChatHandler* handler, char const* args)
    {
        std::string input = args ? args : "";
        std::istringstream parser(input);
        std::string action;
        parser >> action;
        std::string const cohortId =
            sBotWorldPopulationMgr->ResolveGlobalCohortId();
        std::string result;
        if (action == "status")
        {
            result = sBotWorldPopulationMgr
                ->GetChainwielderOwnerCheckpointJsonForCohort(cohortId);
        }
        else if (action == "start-held")
        {
            uint32 actorGuid = 0;
            std::string fixtureId;
            std::string sealSha256;
            std::string sourceCommit;
            std::string extra;
            parser >> actorGuid >> fixtureId >> sealSha256
                >> sourceCommit >> extra;
            if (!actorGuid || fixtureId.empty() || sealSha256.empty()
                || sourceCommit.empty() || !extra.empty())
            {
                result = "{\"ok\":false,\"action\":"
                    "\"botauto_controller_route_hold\","
                    "\"failure_reason\":\"invalid_arguments\"}";
            }
            else
            {
                result = sBotWorldPopulationMgr
                    ->StartAutonomyHeldForCohort(cohortId, actorGuid,
                        fixtureId, sealSha256, sourceCommit);
            }
        }
        else if (action == "arm")
        {
            uint32 actorGuid = 0;
            std::string sealSha256;
            std::string sourceCommit;
            std::string extra;
            parser >> actorGuid >> sealSha256 >> sourceCommit >> extra;
            if (!actorGuid || sealSha256.empty()
                || sourceCommit.empty() || !extra.empty())
            {
                result = "{\"ok\":false,\"action\":"
                    "\"botauto_chainwielder_checkpoint\","
                    "\"failure_reason\":\"invalid_arguments\"}";
            }
            else
            {
                result = sBotWorldPopulationMgr
                    ->ArmChainwielderOwnerCheckpointForCohort(
                        cohortId, actorGuid, sealSha256, sourceCommit);
            }
        }
        else if (action == "release")
        {
            uint32 actorGuid = 0;
            std::string sealSha256;
            std::string sourceCommit;
            std::string extra;
            parser >> actorGuid >> sealSha256 >> sourceCommit >> extra;
            if (!actorGuid || sealSha256.empty()
                || sourceCommit.empty() || !extra.empty())
            {
                result = "{\"ok\":false,\"action\":"
                    "\"botauto_controller_route_hold\","
                    "\"failure_reason\":\"invalid_arguments\"}";
            }
            else
            {
                result = sBotWorldPopulationMgr
                    ->ReleaseControllerRouteHoldForCohort(
                        cohortId, actorGuid, sealSha256, sourceCommit);
            }
        }
        else
        {
            result = "{\"ok\":false,\"action\":"
                "\"botauto_chainwielder_checkpoint\","
                "\"failure_reason\":"
                "\"start_held_arm_release_or_status_required\"}";
        }
        handler->SendSysMessage(result.c_str());
        return true;
    }
};

void AddSC_chainwielder_owner_checkpoint_commandscript()
{
    new chainwielder_owner_checkpoint_commandscript();
}
