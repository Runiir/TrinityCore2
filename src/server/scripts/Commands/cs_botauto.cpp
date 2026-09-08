/*
 * Bot-auto and bot-experiment commands.
 */

#include "ScriptMgr.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotMgr.h"
#include "Bots/BotTypes.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Base64.h"
#include "Chat.h"
#include "Config.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "RBAC.h"
#include "WorldSession.h"
#include <algorithm>
#include <atomic>
#include <charconv>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <map>
#include <sstream>
#include <string>
#include <system_error>
#include <vector>

class botauto_commandscript : public CommandScript
{
public:
    botauto_commandscript() : CommandScript("botauto_commandscript") { }

    std::vector<ChatCommand> GetCommands() const override
    {
        static std::vector<ChatCommand> botExpCommandTable =
        {
            { "start",  rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStartCommand,  "" },
            { "stop",   rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStopCommand,   "" },
            { "status", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleStatusCommand, "" },
            { "summary", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleSummaryCommand, "" },
            { "export", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleExportCommand, "" },
            { "replay", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleReplayCommand, "" },
            { "comparebrain", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleCompareBrainCommand, "" },
        };

        static std::vector<ChatCommand> botAutoCommandTable =
        {
            { "create",  rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoCreateCommand,  "" },
            { "cohorts", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoCohortsCommand, "" },
            { "ownership", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoOwnershipCommand, "" },
            { "start",   rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoStartCommand,   "" },
            { "prepare", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoPrepareCommand, "" },
            { "stop",    rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoStopCommand,    "" },
            { "status",  rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoStatusCommand,  "" },
            { "readycheck", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoReadyCheckCommand, "" },
            { "profiles", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoProfilesCommand, "" },
            { "profile", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoProfileCommand,  "" },
            { "rotations", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoRotationsCommand, "" },
            { "debug",   rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoDebugCommand,   "" },
            { "diagnose", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoDiagnoseCommand, "" },
            { "trace",   rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoTraceCommand,   "" },
            { "combatlog", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoCombatLogCommand, "" },
            { "calibrate", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoCalibrateCommand, "" },
            { "spawn",   rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoSpawnCommand,   "" },
            { "despawn", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, &HandleAutoDespawnCommand, "" },
        };

        static std::vector<ChatCommand> commandTable =
        {
            { "botexp", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, nullptr, "", botExpCommandTable },
            { "botauto", rbac::RBAC_PERM_COMMAND_HEALERBOT, true, nullptr, "", botAutoCommandTable },
        };

        return commandTable;
    }

private:
    static std::string FirstArg(char const* args)
    {
        if (!args)
            return "";

        std::string input = args;
        std::vector<char> buffer(input.begin(), input.end());
        buffer.push_back('\0');
        if (char* token = strtok(buffer.data(), " "))
            return token;

        return "";
    }

    static std::vector<std::string> Tokenize(char const* args)
    {
        std::vector<std::string> tokens;
        if (!args)
            return tokens;

        std::string input = args;
        std::vector<char> buffer(input.begin(), input.end());
        buffer.push_back('\0');
        for (char* token = strtok(buffer.data(), " "); token; token = strtok(nullptr, " "))
            tokens.push_back(token);

        return tokens;
    }

    static bool ParseUint64Token(std::string const& token, uint64& value)
    {
        if (token.empty() || token.front() == '-')
            return false;

        uint64 parsed = 0;
        char const* first = token.data();
        char const* last = first + token.size();
        auto const result = std::from_chars(first, last, parsed, 10);
        if (result.ec != std::errc() || result.ptr != last)
            return false;

        value = parsed;
        return true;
    }

    static bool SendAutoResult(ChatHandler* handler, std::string const& result)
    {
        bool ok = result.find("\"ok\":true") != std::string::npos;
        if (handler)
        {
            handler->PSendSysMessage("%s", result.c_str());
            if (!ok)
                handler->SetSentErrorMessage(true);
        }
        return ok;
    }

    static bool SendCalibrationStatusResult(ChatHandler* handler, std::string const& cohortId,
        std::string const& result)
    {
        // Base64 plus the JSON envelope must remain well below ChatHandler's
        // formatted-message buffer. Twelve raw KiB expands to roughly 16 KiB.
        static constexpr size_t RawChunkSize = 12 * 1024;
        if (!handler || result.size() <= RawChunkSize)
            return SendAutoResult(handler, result);

        bool ok = result.find("\"ok\":true") != std::string::npos;
        size_t chunkCount = (result.size() + RawChunkSize - 1) / RawChunkSize;
        for (size_t sequence = 0; sequence < chunkCount; ++sequence)
        {
            size_t offset = sequence * RawChunkSize;
            size_t length = std::min(RawChunkSize, result.size() - offset);
            std::vector<uint8> raw(result.begin() + offset, result.begin() + offset + length);
            std::string encoded = Trinity::Encoding::Base64::Encode(raw);
            handler->PSendSysMessage(
                "{\"ok\":true,\"action\":\"botauto_calibrate_status_chunk\",\"cohort_id\":\"%s\","
                "\"calibration_status_chunk_schema_version\":1,\"sequence\":%zu,\"chunk_count\":%zu,"
                "\"encoding\":\"base64\",\"data\":\"%s\"}",
                cohortId.c_str(), sequence, chunkCount, encoded.c_str());
        }
        handler->PSendSysMessage(
            "{\"ok\":true,\"action\":\"botauto_calibrate_status_complete\",\"cohort_id\":\"%s\","
            "\"calibration_status_chunk_schema_version\":1,\"chunk_count\":%zu,\"total_bytes\":%zu,"
            "\"payload_ok\":%s}",
            cohortId.c_str(), chunkCount, result.size(), ok ? "true" : "false");
        if (!ok)
            handler->SetSentErrorMessage(true);
        return ok;
    }

    static bool SendCombatLogFrames(ChatHandler* handler, std::string const& cohortId,
        std::string const& combatLog, char const* exportKind)
    {
        if (!handler)
            return true;

        static constexpr size_t RawChunkSize = 12 * 1024;
        static std::atomic<uint64> nextExportId{0};
        uint64 const exportId = ++nextExportId;
        size_t chunkCount = std::max<size_t>(1, (combatLog.size() + RawChunkSize - 1) / RawChunkSize);
        for (size_t sequence = 0; sequence < chunkCount; ++sequence)
        {
            size_t offset = sequence * RawChunkSize;
            size_t length = std::min(RawChunkSize, combatLog.size() - offset);
            std::vector<uint8> raw(combatLog.begin() + offset, combatLog.begin() + offset + length);
            std::string encoded = Trinity::Encoding::Base64::Encode(raw);
            handler->PSendSysMessage(
                "{\"ok\":true,\"action\":\"botauto_combatlog_chunk\",\"cohort_id\":\"%s\",\"combat_log_chunk_schema_version\":1,"
                "\"export_id\":%llu,\"export_kind\":\"%s\",\"sequence\":%zu,\"chunk_count\":%zu,\"encoding\":\"base64\",\"data\":\"%s\"}",
                cohortId.c_str(), static_cast<unsigned long long>(exportId), exportKind, sequence, chunkCount, encoded.c_str());
        }
        handler->PSendSysMessage(
            "{\"ok\":true,\"action\":\"botauto_combatlog_complete\",\"cohort_id\":\"%s\",\"combat_log_chunk_schema_version\":1,"
            "\"export_id\":%llu,\"export_kind\":\"%s\",\"chunk_count\":%zu,\"total_bytes\":%zu}",
            cohortId.c_str(), static_cast<unsigned long long>(exportId), exportKind, chunkCount, combatLog.size());
        return true;
    }

    static bool SendCombatLogDeltaFailure(ChatHandler* handler, std::string const& cohortId,
        char const* reason)
    {
        std::string result = "{\"ok\":false,\"action\":\"botauto_combatlog_delta\"";
        if (!cohortId.empty())
            result += ",\"cohort_id\":\"" + cohortId + "\"";
        result += ",\"failure_reason\":\"";
        result += reason ? reason : "invalid_request";
        result += "\"}";
        return SendAutoResult(handler, result);
    }

    static std::string ResolveGlobalAutoCohort(ChatHandler* handler, char const* action)
    {
        std::string cohortId = sBotWorldPopulationMgr->ResolveGlobalCohortId();
        if (!cohortId.empty())
            return cohortId;

        std::string result = std::string("{\"ok\":false,\"action\":\"") + action
            + "\",\"failure_reason\":\"ambiguous_global_cohort\",\"hint\":\"provide_cohort_id\"}";
        SendAutoResult(handler, result);
        return "";
    }

    static bool HandleAutoCreateCommand(ChatHandler* handler, char const* args)
    {
        std::string cohortId = FirstArg(args);
        if (cohortId.empty())
            return SendAutoResult(handler, "{\"ok\":false,\"action\":\"botauto_create\",\"failure_reason\":\"usage: .botauto create <cohort_id>\"}");
        return SendAutoResult(handler, sBotWorldPopulationMgr->CreateCohort(cohortId));
    }

    static bool HandleAutoCohortsCommand(ChatHandler* handler, char const* /*args*/)
    {
        return SendAutoResult(handler, sBotWorldPopulationMgr->GetCohortRegistryJson());
    }

    static bool HandleAutoOwnershipCommand(ChatHandler* handler, char const* /*args*/)
    {
        return SendAutoResult(handler, sBotWorldPopulationMgr->GetCohortIsolationContractJson());
    }

    static bool HandleStartCommand(ChatHandler* handler, char const* args)
    {
        std::string name = FirstArg(args);
        if (name.empty())
            name = "autonomous_zone_10";

        if (!sBotWorldPopulationMgr->Start(name))
        {
            if (handler)
            {
                handler->PSendSysMessage("{\"ok\":false,\"action\":\"botexp_start\",\"failure_reason\":\"botworld_or_playerbot_disabled_or_no_pool_character\"}");
                handler->SetSentErrorMessage(true);
            }
            return false;
        }

        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetStatusJson().c_str());
        return true;
    }

    static bool HandleStopCommand(ChatHandler* handler, char const* /*args*/)
    {
        sBotWorldPopulationMgr->Stop();
        if (handler)
            handler->PSendSysMessage("{\"ok\":true,\"action\":\"botexp_stop\",\"failure_reason\":null}");
        return true;
    }

    static bool HandleAutoStartCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        std::string cohortId;
        std::string profileName;
        if (!tokens.empty() && sBotWorldPopulationMgr->HasCohort(tokens[0]))
        {
            cohortId = tokens[0];
            if (tokens.size() > 1)
                profileName = tokens[1];
        }
        else
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_start");
            if (cohortId.empty())
                return false;
            if (!tokens.empty())
                profileName = tokens[0];
        }

        if (!profileName.empty()
            && !SendAutoResult(handler, sBotWorldPopulationMgr->SelectRuntimeProfileForCohort(cohortId, profileName)))
            return false;

        if (!sBotWorldPopulationMgr->StartAutonomyForCohort(cohortId))
            return SendAutoResult(handler, "{\"ok\":false,\"action\":\"botauto_start\",\"cohort_id\":\"" + cohortId
                + "\",\"failure_reason\":\"max_active_cohorts_or_runtime_start_failed\"}");

        return SendAutoResult(handler, sBotWorldPopulationMgr->GetStatusJsonForCohort(cohortId));
    }

    static bool HandleAutoPrepareCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        std::string cohortId;
        std::string profileName;
        std::string poolTag;
        std::vector<std::string> classSpecs;
        if (tokens.size() >= 2 && sBotWorldPopulationMgr->HasCohort(tokens[0]))
        {
            cohortId = tokens[0];
            profileName = tokens[1];
            if (tokens.size() > 2)
                poolTag = tokens[2];
            if (tokens.size() > 3)
                classSpecs.assign(tokens.begin() + 3, tokens.end());
        }
        else
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_prepare");
            if (cohortId.empty())
                return false;
            profileName = tokens.empty() ? "" : tokens[0];
            if (tokens.size() > 1)
                poolTag = tokens[1];
            if (tokens.size() > 2)
                classSpecs.assign(tokens.begin() + 2, tokens.end());
        }
        return SendAutoResult(handler, sBotWorldPopulationMgr->PrepareValidationProfileForCohort(
            cohortId, profileName, poolTag, classSpecs));
    }

    static bool HandleAutoProfilesCommand(ChatHandler* handler, char const* /*args*/)
    {
        if (ResolveGlobalAutoCohort(handler, "botauto_profiles").empty())
            return false;
        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetRuntimeProfilesJson().c_str());
        return true;
    }

    static bool HandleAutoProfileCommand(ChatHandler* handler, char const* args)
    {
        if (ResolveGlobalAutoCohort(handler, "botauto_profile").empty())
            return false;
        std::vector<std::string> tokens = Tokenize(args);
        std::string result;
        if (tokens.empty())
            result = "{\"ok\":false,\"action\":\"botauto_profile\",\"failure_reason\":\"usage: .botauto profile <name>|clear|reload\"}";
        else if (tokens[0] == "clear")
            result = sBotWorldPopulationMgr->ClearRuntimeProfile();
        else if (tokens[0] == "reload")
            result = sBotWorldPopulationMgr->ReloadRuntimeProfiles();
        else
            result = sBotWorldPopulationMgr->SelectRuntimeProfile(tokens[0]);

        if (handler)
        {
            handler->PSendSysMessage("%s", result.c_str());
            if (result.find("\"ok\":true") == std::string::npos)
                handler->SetSentErrorMessage(true);
        }
        return result.find("\"ok\":true") != std::string::npos;
    }

    static bool HandleAutoRotationsCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        std::string result;
        if (tokens.empty() || tokens[0] == "list")
            result = BotClassSpecActionProfileStore::DbProfilesJson();
        else if (tokens[0] == "reload")
            result = BotClassSpecActionProfileStore::ReloadDbProfiles();
        else if (tokens[0] == "rollback")
            result = BotClassSpecActionProfileStore::RollbackDbProfiles();
        else if (tokens[0] == "dump" && tokens.size() >= 4)
            result = BotClassSpecActionProfileStore::DbProfileDumpJson(uint8(std::atoi(tokens[1].c_str())), tokens[2], tokens[3]);
        else
            result = "{\"ok\":false,\"action\":\"botauto_rotations\",\"failure_reason\":\"usage: .botauto rotations list|reload|rollback|dump <class_id> <spec_tag> <role>\"}";

        if (handler)
        {
            handler->PSendSysMessage("%s", result.c_str());
            if (result.find("\"ok\":true") == std::string::npos)
                handler->SetSentErrorMessage(true);
        }
        return result.find("\"ok\":true") != std::string::npos;
    }

    static bool HandleAutoStopCommand(ChatHandler* handler, char const* args)
    {
        std::string cohortId = FirstArg(args);
        if (cohortId.empty())
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_stop");
            if (cohortId.empty())
                return false;
        }
        if (!sBotWorldPopulationMgr->HasCohort(cohortId))
            return SendAutoResult(handler, "{\"ok\":false,\"action\":\"botauto_stop\",\"cohort_id\":\"" + cohortId + "\",\"failure_reason\":\"unknown_cohort\"}");
        return SendAutoResult(handler, sBotWorldPopulationMgr->StopAutonomyForCohort(cohortId));
    }

    static bool HandleAutoSpawnCommand(ChatHandler* handler, char const* args)
    {
        if (ResolveGlobalAutoCohort(handler, "botauto_spawn").empty())
            return false;
        std::vector<std::string> tokens = Tokenize(args);
        uint32 count = 1;
        if (!tokens.empty() && tokens[0].find_first_not_of("0123456789") == std::string::npos)
            count = std::max<uint32>(1, uint32(strtoul(tokens[0].c_str(), nullptr, 10)));

        if (!sBotWorldPopulationMgr->SpawnAutonomyBots(count))
        {
            if (handler)
            {
                handler->PSendSysMessage("{\"ok\":false,\"action\":\"botauto_spawn\",\"failure_reason\":\"autonomy_not_active\"}");
                handler->SetSentErrorMessage(true);
            }
            return false;
        }

        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetStatusJson().c_str());
        return true;
    }

    static bool HandleAutoDespawnCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        if (tokens.empty() || tokens[0] != "all")
        {
            if (handler)
            {
                handler->PSendSysMessage("{\"ok\":false,\"action\":\"botauto_despawn\",\"failure_reason\":\"usage: .botauto despawn all\"}");
                handler->SetSentErrorMessage(true);
            }
            return false;
        }
        if (ResolveGlobalAutoCohort(handler, "botauto_despawn").empty())
            return false;

        sBotWorldPopulationMgr->StopAutonomy();
        if (handler)
            handler->PSendSysMessage("{\"ok\":true,\"action\":\"botauto_despawn\",\"scope\":\"all\",\"failure_reason\":null}");
        return true;
    }

    static bool HandleAutoDebugCommand(ChatHandler* handler, char const* args)
    {
        if (ResolveGlobalAutoCohort(handler, "botauto_debug").empty())
            return false;
        std::vector<std::string> tokens = Tokenize(args);
        std::string selector = tokens.empty() ? "" : tokens[0];
        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetBotDebugJson(selector).c_str());
        return true;
    }

    static bool HandleAutoDiagnoseCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        std::string cohortId;
        std::string selector = "all";
        if (!tokens.empty() && sBotWorldPopulationMgr->HasCohort(tokens[0]))
        {
            cohortId = tokens[0];
            if (tokens.size() > 1)
                selector = tokens[1];
        }
        else
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_diagnose");
            if (cohortId.empty())
                return false;
            if (!tokens.empty())
                selector = tokens[0];
        }
        return SendAutoResult(handler, sBotWorldPopulationMgr->GetBotDiagnosisJsonForCohort(cohortId, selector));
    }

    static bool HandleAutoTraceCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        std::string cohortId;
        if (!tokens.empty() && sBotWorldPopulationMgr->HasCohort(tokens[0]))
        {
            cohortId = tokens[0];
            tokens.erase(tokens.begin());
        }
        else
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_trace");
            if (cohortId.empty())
                return false;
        }

        std::string selector = tokens.empty() ? "" : tokens[0];
        uint32 limit = 20;
        if (tokens.size() > 1 && tokens[1].find_first_not_of("0123456789") == std::string::npos)
            limit = std::max<uint32>(1, uint32(strtoul(tokens[1].c_str(), nullptr, 10)));
        else if (tokens.size() == 1 && tokens[0].find_first_not_of("0123456789") == std::string::npos)
        {
            limit = std::max<uint32>(1, uint32(strtoul(tokens[0].c_str(), nullptr, 10)));
            selector.clear();
        }
        bool delta = tokens.size() > 2 && tokens[2] == "delta";
        return SendAutoResult(handler, sBotWorldPopulationMgr->GetBotTraceJsonForCohort(cohortId, selector, limit, delta));
    }

    static bool HandleAutoCombatLogCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        if (tokens.size() > 1 && tokens[1] == "delta")
        {
            std::string cohortId = tokens[0];
            if (tokens.size() != 4)
                return SendCombatLogDeltaFailure(handler, cohortId,
                    "usage: .botauto combatlog <cohort_id> delta <cursor> <limit>");
            if (!sBotWorldPopulationMgr->HasCohort(cohortId))
                return SendCombatLogDeltaFailure(handler, cohortId, "unknown_cohort");

            uint64 cursor = 0;
            uint64 requestedLimit = 0;
            if (!ParseUint64Token(tokens[2], cursor))
                return SendCombatLogDeltaFailure(handler, cohortId, "invalid_cursor");
            if (!ParseUint64Token(tokens[3], requestedLimit)
                || requestedLimit == 0 || requestedLimit > 4096)
                return SendCombatLogDeltaFailure(handler, cohortId, "invalid_limit");

            if (handler && handler->GetSession())
            {
                handler->PSendSysMessage("{\"ok\":false,\"action\":\"botauto_combatlog_delta\",\"failure_reason\":\"console_only_bounded_export\"}");
                handler->SetSentErrorMessage(true);
                return false;
            }
            if (handler)
                SendCombatLogFrames(handler, cohortId,
                    sBotWorldPopulationMgr->GetCombatLogDeltaJsonForCohort(
                        cohortId, cursor, uint32(requestedLimit)), "delta");
            return true;
        }

        std::string cohortId = tokens.empty() ? "" : tokens[0];
        if (cohortId.empty())
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_combatlog");
            if (cohortId.empty())
                return false;
        }
        if (!sBotWorldPopulationMgr->HasCohort(cohortId))
            return SendAutoResult(handler, "{\"ok\":false,\"action\":\"botauto_combatlog\",\"cohort_id\":\"" + cohortId + "\",\"failure_reason\":\"unknown_cohort\"}");

        if (handler && handler->GetSession())
        {
            handler->PSendSysMessage("{\"ok\":false,\"action\":\"botauto_combatlog\",\"failure_reason\":\"console_only_bounded_export\"}");
            handler->SetSentErrorMessage(true);
            return false;
        }
        if (handler)
            SendCombatLogFrames(handler, cohortId,
                sBotWorldPopulationMgr->GetCombatLogJsonForCohort(cohortId), "full");
        return true;
    }

    static bool HandleAutoCalibrateCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        std::string cohortId;
        if (!tokens.empty() && sBotWorldPopulationMgr->HasCohort(tokens[0]))
        {
            cohortId = tokens[0];
            tokens.erase(tokens.begin());
        }
        else
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_calibrate");
            if (cohortId.empty())
                return false;
        }

        std::string operation = tokens.empty() ? "status" : tokens[0];
        std::string result;
        if (operation == "start")
        {
            std::string mode = tokens.size() > 1 ? tokens[1] : "";
            std::string targetSpec = tokens.size() > 2 ? tokens[2] : "";
            uint32 seed = tokens.size() > 3 ? std::max<uint32>(1, uint32(strtoul(tokens[3].c_str(), nullptr, 10))) : 1;
            result = sBotWorldPopulationMgr->StartCombatCalibrationForCohort(cohortId, mode, targetSpec, seed);
        }
        else if (operation == "stop")
            result = sBotWorldPopulationMgr->StopCombatCalibrationForCohort(cohortId);
        else if (operation == "status")
            result = sBotWorldPopulationMgr->GetCombatCalibrationJsonForCohort(cohortId);
        else
            result = "{\"ok\":false,\"action\":\"botauto_calibrate\",\"failure_reason\":\"usage: .botauto calibrate [cohort_id] start <mode> <target_spec> [seed]|stop|status\"}";
        if (operation == "status")
            return SendCalibrationStatusResult(handler, cohortId, result);
        return SendAutoResult(handler, result);
    }

    static bool HandleAutoStatusCommand(ChatHandler* handler, char const* args)
    {
        std::string cohortId = FirstArg(args);
        if (cohortId.empty())
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_status");
            if (cohortId.empty())
                return false;
        }
        return SendAutoResult(handler, sBotWorldPopulationMgr->GetStatusJsonForCohort(cohortId));
    }

    static bool HandleAutoReadyCheckCommand(ChatHandler* handler, char const* args)
    {
        std::string cohortId = FirstArg(args);
        if (cohortId.empty())
        {
            cohortId = ResolveGlobalAutoCohort(handler, "botauto_readycheck");
            if (cohortId.empty())
                return false;
        }
        return SendAutoResult(
            handler, sBotWorldPopulationMgr->RequestNativeRaidReadyCheckForCohort(cohortId));
    }

    static bool HandleStatusCommand(ChatHandler* handler, char const* /*args*/)
    {
        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetStatusJson().c_str());
        return true;
    }

    static bool HandleSummaryCommand(ChatHandler* handler, char const* /*args*/)
    {
        if (handler)
            handler->PSendSysMessage("%s", sBotWorldPopulationMgr->GetSummaryJson().c_str());
        return true;
    }

    static bool HandleExportCommand(ChatHandler* handler, char const* /*args*/)
    {
        if (handler)
            handler->PSendSysMessage("{\"ok\":true,\"action\":\"botexp_export\",\"storage\":\"character_database_tables\",\"tables\":[\"experiment_bot_runs\",\"experiment_bot_segments\",\"experiment_bot_events\",\"experiment_bot_decisions\",\"experiment_bot_activities\",\"experiment_bot_replay_records\",\"experiment_bot_clips\",\"experiment_bot_clip_frames\",\"bot_semantic_outcome_stats\",\"bot_memory_pois\",\"bot_memory_danger_zones\",\"bot_memory_failed_paths\",\"bot_memory_safe_positions\",\"bot_memory_objective_clusters\",\"bot_memory_recipe_sources\",\"bot_memory_material_sources\",\"bot_memory_daily_cooldowns\",\"bot_memory_transport_usage\",\"bot_memory_decision_fingerprints\",\"bot_policy_models\",\"bot_policy_evaluations\"],\"embedding_feature_schema\":\"bot_semantic_phase6_v1\",\"policy_feature_schema\":\"bot_policy_features_v1\",\"failure_reason\":null}");
        return true;
    }

    static bool HandleReplayCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        std::string replayType = "failure";
        std::string selector = "latest";
        std::string brainVersion;
        if (!tokens.empty())
        {
            if (tokens[0].find_first_not_of("0123456789") == std::string::npos)
            {
                selector = tokens[0];
                brainVersion = tokens.size() > 1 ? tokens[1] : "";
            }
            else
            {
                replayType = tokens[0];
                selector = tokens.size() > 1 ? tokens[1] : "latest";
                brainVersion = tokens.size() > 2 ? tokens[2] : "";
            }
        }

        std::string result = sBotWorldPopulationMgr->Replay(replayType, selector, brainVersion);
        if (handler)
            handler->PSendSysMessage("%s", result.c_str());

        if (result.find("\"ok\":true") == std::string::npos)
        {
            if (handler)
                handler->SetSentErrorMessage(true);
            return false;
        }
        return true;
    }

    static bool HandleCompareBrainCommand(ChatHandler* handler, char const* args)
    {
        std::vector<std::string> tokens = Tokenize(args);
        if (tokens.size() < 4 || tokens[0] != "replay" || tokens[1].find_first_not_of("0123456789") != std::string::npos)
        {
            if (handler)
            {
                handler->PSendSysMessage("{\"ok\":false,\"action\":\"botexp_comparebrain\",\"failure_reason\":\"usage: .botexp comparebrain replay <id> <brain_a> <brain_b>\"}");
                handler->SetSentErrorMessage(true);
            }
            return false;
        }

        uint64 replayId = uint64(strtoull(tokens[1].c_str(), nullptr, 10));
        std::string result = sBotWorldPopulationMgr->CompareBrains(replayId, tokens[2], tokens[3]);
        if (handler)
            handler->PSendSysMessage("%s", result.c_str());

        if (result.find("\"ok\":true") == std::string::npos)
        {
            if (handler)
                handler->SetSentErrorMessage(true);
            return false;
        }
        return true;
    }
};


void RegisterBotAutoCommands()
{
    new botauto_commandscript();
}
