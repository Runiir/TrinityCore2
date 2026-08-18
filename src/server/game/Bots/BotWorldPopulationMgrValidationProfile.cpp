#include "Bots/BotWorldPopulationMgr.h"

#include "Config.h"
#include "DatabaseEnv.h"
#include "Group.h"
#include "Log.h"

#include <algorithm>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

namespace
{
constexpr uint32 BlackwingDescentMapId = 669;

std::string ReadSmallTextFile(std::string const& path, size_t maxBytes = 4 * 1024 * 1024)
{
    if (path.empty())
        return "";

    std::ifstream input(path.c_str(), std::ios::in | std::ios::binary);
    if (!input)
        return "";

    std::ostringstream data;
    data << input.rdbuf();
    std::string value = data.str();
    if (value.size() > maxBytes)
        return "";
    return value;
}

std::vector<std::string> SplitSqlStatements(std::string const& sql)
{
    std::vector<std::string> statements;
    std::string current;
    bool inString = false;
    bool escaped = false;
    bool inLineComment = false;
    bool inBlockComment = false;
    for (size_t i = 0; i < sql.size(); ++i)
    {
        char c = sql[i];
        char next = i + 1 < sql.size() ? sql[i + 1] : '\0';

        if (inLineComment)
        {
            if (c == '\n' || c == '\r')
            {
                inLineComment = false;
                current.push_back('\n');
            }
            continue;
        }

        if (inBlockComment)
        {
            if (c == '*' && next == '/')
            {
                inBlockComment = false;
                ++i;
                current.push_back(' ');
            }
            continue;
        }

        if (inString)
        {
            current.push_back(c);
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '\'')
                inString = false;
            continue;
        }

        if ((c == '-' && next == '-') || c == '#')
        {
            inLineComment = true;
            if (c == '-')
                ++i;
            continue;
        }

        if (c == '/' && next == '*')
        {
            inBlockComment = true;
            ++i;
            continue;
        }

        if (c == '\'')
        {
            inString = true;
            current.push_back(c);
            continue;
        }

        if (c == ';')
        {
            if (current.find_first_not_of(" \t\r\n") != std::string::npos)
                statements.push_back(current);
            current.clear();
            continue;
        }

        current.push_back(c);
    }
    if (current.find_first_not_of(" \t\r\n") != std::string::npos)
        statements.push_back(current);
    return statements;
}

template<class ConnectionType>
bool ExecuteSqlFile(DatabaseWorkerPool<ConnectionType>& database, std::string const& path, char const* label)
{
    std::string sql = ReadSmallTextFile(path, 64 * 1024 * 1024);
    if (sql.empty())
    {
        TC_LOG_ERROR("server", "BotWorld validation prepare failed label=%s path=%s reason=sql_file_unreadable", label ? label : "", path.c_str());
        return false;
    }

    uint32 count = 0;
    for (std::string const& statement : SplitSqlStatements(sql))
    {
        database.DirectExecute(statement.c_str());
        ++count;
    }

    TC_LOG_INFO("server", "BotWorld validation prepare applied label=%s path=%s statements=%u", label ? label : "", path.c_str(), count);
    return true;
}

}

bool BotWorldPopulationMgr::IsValidationProfileName(std::string const& name) const
{
    if (name == "stonecore_5n" || name == "stonecore_5h" || name == "blackwing_descent_10n")
        return true;

    // Validation profiles are data-owned. Boss-shard names must not be
    // added to this predicate one by one: the profile manifest is the
    // authority for whether a named profile has an executable route. The
    // manifest is loaded before start/prepare consumes this predicate.
    auto profile = Cohort().RuntimeProfiles.find(name);
    if (profile == Cohort().RuntimeProfiles.end())
        return false;

    BotWorldExperimentProfile const& candidate = profile->second;
    return candidate.HasValidationRouteEnable && candidate.Config.ValidationRouteEnable
        && candidate.HasValidationRouteManifestPath && !candidate.Config.ValidationRouteManifestPath.empty()
        && candidate.HasValidationRouteScenarioId && candidate.Config.ValidationRouteScenarioId == name
        && candidate.HasTargetPopulation && candidate.Config.TargetPopulation == 10
        && candidate.HasPoolTagFilter && candidate.Config.PoolTagFilter == name
        && candidate.HasAllowRaids && candidate.Config.AllowRaids
        && candidate.HasRaidSize && candidate.Config.RaidSize == 10
        && candidate.HasRaidDifficulty && candidate.Config.RaidDifficulty == RAID_DIFFICULTY_10MAN_NORMAL
        && (!candidate.HasMapId || candidate.Config.MapId == BlackwingDescentMapId);
}

std::string BotWorldPopulationMgr::PrepareValidationProfile(std::string const& name, std::string const& poolTag,
    std::vector<std::string> const& classSpecs)
{
    if (!sConfigMgr->GetBoolDefault("BotWorld.Enable", false) || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return "{\"ok\":false,\"action\":\"botauto_prepare\",\"failure_reason\":\"botworld_or_playerbot_disabled\"}";

    std::string profileName = name.empty() ? Cohort().SelectedProfileName : name;
    if (profileName.empty())
        return "{\"ok\":false,\"action\":\"botauto_prepare\",\"failure_reason\":\"profile_required\"}";
    EnsureRuntimeProfilesLoaded();
    auto selectedProfile = Cohort().RuntimeProfiles.find(profileName);
    if (selectedProfile == Cohort().RuntimeProfiles.end())
        return "{\"ok\":false,\"action\":\"botauto_prepare\",\"failure_reason\":\"unknown_profile\"}";
    BotWorldExperimentProfile const& profile = selectedProfile->second;
    if (!IsValidationProfileName(profileName))
        return "{\"ok\":false,\"action\":\"botauto_prepare\",\"failure_reason\":\"not_executable_validation_profile\"}";
    bool const exactPartyRequested = !classSpecs.empty();
    // The profile owns the default pool.  A fully specified exact-party
    // request may instead lease canonical members from the shared all-spec
    // pool; the size, uniqueness, target identities, and resulting leases are
    // validated below and again after admission.  A bare pool override remains
    // forbidden.
    if (!poolTag.empty() && !exactPartyRequested
        && (!profile.HasPoolTagFilter || profile.Config.PoolTagFilter != poolTag))
        return "{\"ok\":false,\"action\":\"botauto_prepare\",\"failure_reason\":\"pool_tag_profile_mismatch\"}";
    if (!classSpecs.empty())
    {
        std::set<std::string> uniqueSpecs(classSpecs.begin(), classSpecs.end());
        uint32 expectedSize = profile.HasTargetPopulation ? profile.Config.TargetPopulation : 0;
        if (poolTag.empty() || !expectedSize || classSpecs.size() != expectedSize || uniqueSpecs.size() != classSpecs.size()
            || std::any_of(classSpecs.begin(), classSpecs.end(), [](std::string const& value) { return value.empty(); }))
            return "{\"ok\":false,\"action\":\"botauto_prepare\",\"failure_reason\":\"invalid_exact_party_contract\"}";
    }

    std::string selectResult = SelectRuntimeProfile(profileName);
    if (selectResult.find("\"ok\":true") == std::string::npos)
        return selectResult;

    Cohort().PreparedPoolTagFilter = poolTag;
    Cohort().PreparedClassSpecs = classSpecs;
    LoadConfig(profileName, nullptr);
    bool const exactTagSelected = !poolTag.empty() && Cohort().Config.PoolTagFilter == poolTag;
    bool const profileTagSelected = poolTag.empty() && !Cohort().Config.PoolTagFilter.empty();
    bool ok = Cohort().Config.ValidationRouteEnable && IsValidationProfileName(Cohort().Config.Name)
        && (exactTagSelected || profileTagSelected)
        && PrepareCurrentValidationProfile("manual_prepare");
    std::ostringstream json;
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_prepare\""
         << ",\"profile\":\"" << JsonEscape(profileName) << "\""
         << ",\"pool_tag_filter\":\"" << JsonEscape(Cohort().Config.PoolTagFilter) << "\""
         << ",\"exact_party_class_specs\":[";
    for (size_t index = 0; index < Cohort().Config.PoolClassSpecFilter.size(); ++index)
    {
        if (index)
            json << ',';
        json << '\"' << JsonEscape(Cohort().Config.PoolClassSpecFilter[index]) << '\"';
    }
    json << "]"
         << ",\"failure_reason\":" << (ok ? "null" : ("\"" + JsonEscape(Cohort().LastPopulationFailureReason.empty() ? "validation_prepare_failed" : Cohort().LastPopulationFailureReason) + "\"")) << "}";
    return json.str();
}

bool BotWorldPopulationMgr::PrepareCurrentValidationProfile(char const* reason)
{
    if (!Cohort().Config.ValidationRouteEnable || Cohort().Config.PoolTagFilter.empty())
    {
        Cohort().LastPopulationFailureReason = "validation_profile_required";
        return false;
    }

    // LoadConfig resolves the selected profile and loads its route before any
    // provisioning, leases, or bot population changes. A named validation
    // profile must never degrade to anchor-only autonomy when that immutable
    // route is absent or contains no native-loadable node.
    if (Cohort().Config.ValidationRouteScenarioId != Cohort().Config.Name
        || !Party().ValidationRouteManifestLoadError.empty()
        || Party().ValidationRouteManifest.empty()
        || Party().ValidationRouteGeneration != 1)
    {
        Cohort().LastPopulationFailureReason = !Party().ValidationRouteManifestLoadError.empty()
            ? "validation_route_" + Party().ValidationRouteManifestLoadError
            : "validation_route_not_initialized";
        return false;
    }

    if (sConfigMgr->GetBoolDefault("BotWorld.ValidationProvisionOnPrepare", false)
        && !ApplyValidationProvisioningSql(reason))
        return false;

    return ResetValidationBotPool(reason);
}

bool BotWorldPopulationMgr::ApplyValidationProvisioningSql(char const* reason)
{
    std::string accountPath = sConfigMgr->GetStringDefault("BotWorld.ValidationProvisionAccountsSql", "dataset/validation_provisioning/provision_accounts.sql");
    std::string characterPath = sConfigMgr->GetStringDefault("BotWorld.ValidationProvisionCharactersSql", "dataset/validation_provisioning/provision_characters.sql");
    TC_LOG_INFO("server", "BotWorld validation prepare provisioning begin profile=%s tag=%s reason=%s", Cohort().Config.Name.c_str(), Cohort().Config.PoolTagFilter.c_str(), reason ? reason : "");
    if (!ExecuteSqlFile(LoginDatabase, accountPath, "validation_accounts"))
    {
        Cohort().LastPopulationFailureReason = "validation_account_provisioning_failed";
        return false;
    }
    if (!ExecuteSqlFile(CharacterDatabase, characterPath, "validation_characters"))
    {
        Cohort().LastPopulationFailureReason = "validation_character_provisioning_failed";
        return false;
    }
    return true;
}

bool BotWorldPopulationMgr::ResetValidationBotPool(char const* reason)
{
    std::string tag = Cohort().Config.PoolTagFilter;
    CharacterDatabase.EscapeString(tag);
    std::vector<std::string> escapedSpecs = Cohort().Config.PoolClassSpecFilter;
    for (std::string& spec : escapedSpecs)
        CharacterDatabase.EscapeString(spec);

    std::ostringstream query;
    query << "SELECT cbp.`guid`, cbp.`role`, cbp.`class_spec` FROM `character_bot_pool` cbp "
          << "INNER JOIN `characters` c ON c.`guid` = cbp.`guid` "
          << "WHERE cbp.`enabled` = 1 AND c.`level` = 85 AND cbp.`experiment_tags` = '" << tag << "'";
    if (!escapedSpecs.empty())
    {
        query << " AND cbp.`class_spec` IN (";
        for (size_t index = 0; index < escapedSpecs.size(); ++index)
        {
            if (index)
                query << ',';
            query << '\'' << escapedSpecs[index] << '\'';
        }
        query << ") ORDER BY FIELD(cbp.`class_spec`";
        for (std::string const& spec : escapedSpecs)
            query << ",'" << spec << '\'';
        query << "), cbp.`guid`";
    }
    else
        query << " ORDER BY cbp.`guid`";

    QueryResult result = CharacterDatabase.Query(query.str().c_str());
    if (!result)
    {
        Cohort().LastPopulationFailureReason = "validation_pool_empty";
        return false;
    }

    std::vector<uint32> guids;
    std::vector<std::string> observedSpecs;
    uint32 tankCount = 0;
    uint32 healerCount = 0;
    uint32 dpsCount = 0;
    do
    {
        Field* fields = result->Fetch();
        guids.push_back(fields[0].GetUInt32());
        std::string role = fields[1].GetString();
        observedSpecs.push_back(fields[2].GetString());
        if (role == "tank")
            ++tankCount;
        else if (role == "healer")
            ++healerCount;
        else if (role == "dps")
            ++dpsCount;
    } while (result->NextRow());

    // A named validation profile owns an exact pool partition.  Resetting a
    // tag must never silently accept a partial shard or a mixed-role pool and
    // leave admission to discover the mismatch after leases/spawns begin.
    uint32 expectedPoolSize = Cohort().Config.TargetPopulation;
    if (!Party().ValidationRouteManifest.empty()
        && Party().ValidationRouteManifest.front().ExpectedBotCount)
        expectedPoolSize = Party().ValidationRouteManifest.front().ExpectedBotCount;
    if (!expectedPoolSize || guids.size() != expectedPoolSize)
    {
        Cohort().LastPopulationFailureReason = "validation_pool_exact_size_mismatch";
        return false;
    }
    if (Cohort().Config.AllowRaids)
    {
        std::vector<RaidRosterPlanSlot> const rosterPlan = BuildRosterPlan();
        uint32 expectedTanks = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
            [](RaidRosterPlanSlot const& slot) { return slot.Role == "tank"; }));
        uint32 expectedHealers = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
            [](RaidRosterPlanSlot const& slot) { return slot.Role == "healer"; }));
        uint32 expectedDps = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
            [](RaidRosterPlanSlot const& slot) { return slot.Role == "dps"; }));
        if (rosterPlan.size() != expectedPoolSize || tankCount != expectedTanks
            || healerCount != expectedHealers || dpsCount != expectedDps)
        {
            Cohort().LastPopulationFailureReason = "validation_pool_exact_raid_composition_mismatch";
            return false;
        }
    }
    else if (Cohort().Config.ValidationRouteEnable && expectedPoolSize == MAXGROUPSIZE
        && (tankCount != 1 || healerCount != 1 || dpsCount != 3))
    {
        Cohort().LastPopulationFailureReason = "validation_pool_exact_party_composition_mismatch";
        return false;
    }

    if (!Cohort().Config.PoolClassSpecFilter.empty())
    {
        bool exactClassSpecs = observedSpecs == Cohort().Config.PoolClassSpecFilter;
        if (Cohort().Config.AllowRaids)
        {
            std::vector<RaidRosterPlanSlot> const rosterPlan = BuildRosterPlan();
            uint32 expectedTanks = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
                [](RaidRosterPlanSlot const& slot) { return slot.Role == "tank"; }));
            uint32 expectedHealers = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
                [](RaidRosterPlanSlot const& slot) { return slot.Role == "healer"; }));
            uint32 expectedDps = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
                [](RaidRosterPlanSlot const& slot) { return slot.Role == "dps"; }));
            exactClassSpecs = exactClassSpecs && guids.size() == rosterPlan.size()
                && tankCount == expectedTanks && healerCount == expectedHealers && dpsCount == expectedDps;
        }
        else
            exactClassSpecs = exactClassSpecs && guids.size() == 5
                && tankCount == 1 && healerCount == 1 && dpsCount == 3;
        if (!exactClassSpecs)
        {
            Cohort().LastPopulationFailureReason = "exact_party_pool_mismatch";
            return false;
        }
    }

    std::ostringstream guidList;
    for (size_t index = 0; index < guids.size(); ++index)
    {
        if (index)
            guidList << ',';
        guidList << guids[index];
    }
    std::string guidSelect = guidList.str();
    std::string poolPredicate = "p.`guid` IN (" + guidSelect + ")";

    std::lock_guard<std::mutex> guard(_leaseMutex);
    for (uint32 guid : guids)
    {
        if (_guidLeases.find(guid) != _guidLeases.end())
        {
            Cohort().LastPopulationFailureReason = "validation_pool_guid_leased";
            return false;
        }
    }

    CharacterDatabase.DirectExecute(("UPDATE `character_bot_pool` p SET p.`in_use` = 0 WHERE " + poolPredicate).c_str());
    CharacterDatabase.DirectExecute(("UPDATE `characters` c JOIN `character_bot_pool` p ON p.`guid` = c.`guid` SET c.`online` = 0 WHERE " + poolPredicate).c_str());
    CharacterDatabase.DirectExecute(("DELETE FROM `character_instance` WHERE `guid` IN (" + guidSelect + ")").c_str());
    CharacterDatabase.DirectExecute(("DELETE gi FROM `group_instance` gi JOIN `groups` g ON g.`guid` = gi.`guid` WHERE g.`leaderGuid` IN (" + guidSelect + ") OR g.`guid` IN (SELECT gm.`guid` FROM `group_member` gm WHERE gm.`memberGuid` IN (" + guidSelect + "))").c_str());
    CharacterDatabase.DirectExecute(("DELETE gm FROM `group_member` gm WHERE gm.`memberGuid` IN (" + guidSelect + ") OR gm.`guid` IN (SELECT g.`guid` FROM `groups` g WHERE g.`leaderGuid` IN (" + guidSelect + "))").c_str());
    CharacterDatabase.DirectExecute(("DELETE g FROM `groups` g WHERE g.`leaderGuid` IN (" + guidSelect + ")").c_str());
    CharacterDatabase.DirectExecute(("DELETE pc FROM `pet_spell_cooldown` pc JOIN `character_pet` cp ON cp.`id` = pc.`guid` WHERE cp.`owner` IN (" + guidSelect + ")").c_str());
    CharacterDatabase.DirectExecute(("DELETE pa FROM `pet_aura` pa JOIN `character_pet` cp ON cp.`id` = pa.`guid` WHERE cp.`owner` IN (" + guidSelect + ")").c_str());
    CharacterDatabase.DirectExecute(("DELETE FROM `mail_items` WHERE `receiver` IN (" + guidSelect + ")").c_str());
    CharacterDatabase.DirectExecute(("DELETE FROM `mail` WHERE `receiver` IN (" + guidSelect + ")").c_str());

    TC_LOG_INFO("server", "BotWorld validation prepare reset profile=%s tag=%s cohort=%s attempt=%llu reason=%s",
        Cohort().Config.Name.c_str(), Cohort().Config.PoolTagFilter.c_str(), Cohort().Id.c_str(),
        static_cast<unsigned long long>(Cohort().AttemptId), reason ? reason : "");
    return true;
}

