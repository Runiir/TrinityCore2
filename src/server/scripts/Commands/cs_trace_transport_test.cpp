#include "Bots/BotWorldPopulationMgr.h"
#include "Chat.h"
#include "RBAC.h"
#include "ScriptMgr.h"

#include <cstdlib>
#include <string>
#include <vector>

class trace_transport_test_commandscript : public CommandScript
{
public:
    trace_transport_test_commandscript()
        : CommandScript("trace_transport_test_commandscript") { }

    std::vector<ChatCommand> GetCommands() const override
    {
        static std::vector<ChatCommand> commandTable =
        {
            { "botautotracepressure", rbac::RBAC_PERM_COMMAND_HEALERBOT, true,
                &HandleTracePressureCommand, "" },
        };
        return commandTable;
    }

private:
    static bool HandleTracePressureCommand(ChatHandler* handler, char const* args)
    {
        std::string countText = args ? args : "";
        size_t const first = countText.find_first_not_of(' ');
        size_t const last = countText.find_last_not_of(' ');
        countText = first == std::string::npos
            ? "" : countText.substr(first, last - first + 1);
        uint32 requestedCount = 0;
        if (!countText.empty() && countText.size() <= 3
            && countText.find_first_not_of("0123456789") == std::string::npos)
            requestedCount = uint32(std::strtoul(countText.c_str(), nullptr, 10));

        std::string const cohortId = sBotWorldPopulationMgr->ResolveGlobalCohortId();
        std::string const result = sBotWorldPopulationMgr
            ->ApplyTraceTransportTestPressureForCohort(cohortId, requestedCount);
        handler->SendSysMessage(result.c_str());
        return true;
    }
};

void AddSC_trace_transport_test_commandscript()
{
    new trace_transport_test_commandscript();
}
