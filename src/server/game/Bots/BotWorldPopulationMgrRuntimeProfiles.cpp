#include "Bots/BotWorldPopulationMgr.h"

#include "Config.h"
#include "Log.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

namespace
{
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

std::string ExtractJsonStringField(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (std::regex_search(json, match, pattern) && match.size() > 1)
        return match[1].str();
    return "";
}

std::string ExtractJsonObjectField(std::string const& json, std::string const& key)
{
    std::string needle = "\"" + key + "\"";
    size_t keyPos = json.find(needle);
    if (keyPos == std::string::npos)
        return "";
    size_t colon = json.find(':', keyPos + needle.size());
    if (colon == std::string::npos)
        return "";
    size_t start = json.find('{', colon);
    if (start == std::string::npos)
        return "";

    uint32 depth = 0;
    bool inString = false;
    bool escaped = false;
    for (size_t i = start; i < json.size(); ++i)
    {
        char c = json[i];
        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '"')
                inString = false;
            continue;
        }

        if (c == '"')
            inString = true;
        else if (c == '{')
            ++depth;
        else if (c == '}')
        {
            if (!depth)
                return "";
            --depth;
            if (!depth)
                return json.substr(start, i - start + 1);
        }
    }
    return "";
}


std::string ExtractJsonArrayField(std::string const& json, std::string const& key)
{
    std::string needle = "\"" + key + "\"";
    size_t keyPos = json.find(needle);
    if (keyPos == std::string::npos)
        return "";
    size_t colon = json.find(':', keyPos + needle.size());
    if (colon == std::string::npos)
        return "";
    size_t start = json.find('[', colon);
    if (start == std::string::npos)
        return "";

    uint32 depth = 0;
    bool inString = false;
    bool escaped = false;
    for (size_t i = start; i < json.size(); ++i)
    {
        char c = json[i];
        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '"')
                inString = false;
            continue;
        }

        if (c == '"')
            inString = true;
        else if (c == '[')
            ++depth;
        else if (c == ']')
        {
            if (!depth)
                return "";
            --depth;
            if (!depth)
                return json.substr(start, i - start + 1);
        }
    }
    return "";
}


std::vector<std::string> ExtractJsonObjectArrayItems(std::string const& arrayJson)
{
    std::vector<std::string> items;
    uint32 depth = 0;
    bool inString = false;
    bool escaped = false;
    size_t start = std::string::npos;
    for (size_t i = 0; i < arrayJson.size(); ++i)
    {
        char c = arrayJson[i];
        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '"')
                inString = false;
            continue;
        }

        if (c == '"')
            inString = true;
        else if (c == '{')
        {
            if (!depth)
                start = i;
            ++depth;
        }
        else if (c == '}')
        {
            if (depth)
            {
                --depth;
                if (!depth && start != std::string::npos)
                    items.push_back(arrayJson.substr(start, i - start + 1));
            }
        }
    }
    return items;
}

bool ExtractJsonNumberField(std::string const& json, std::string const& key, float& value)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)");
    std::smatch match;
    if (std::regex_search(json, match, pattern) && match.size() > 1)
    {
        value = float(std::atof(match[1].str().c_str()));
        return true;
    }
    return false;
}

bool ExtractJsonIntField(std::string const& json, std::string const& key, int& value)
{
    float number = 0.0f;
    if (!ExtractJsonNumberField(json, key, number))
        return false;
    value = int(number);
    return true;
}

bool JsonHasField(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:");
    return std::regex_search(json, pattern);
}

bool ExtractJsonBoolField(std::string const& json, std::string const& key, bool& value)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*(true|false)");
    std::smatch match;
    if (std::regex_search(json, match, pattern) && match.size() > 1)
    {
        value = match[1].str() == "true";
        return true;
    }
    return false;
}

bool JsonFieldIsString(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*\"");
    return std::regex_search(json, pattern);
}

bool JsonFieldIsNumber(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?");
    return std::regex_search(json, pattern);
}

bool JsonFieldIsBool(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*(true|false)");
    return std::regex_search(json, pattern);
}
}

std::string BotWorldPopulationMgr::RuntimeProfilesJson(char const* action) const
{
    std::ostringstream json;
    json << "{\"ok\":" << (Cohort().ProfileManifestLoadError.empty() ? "true" : "false")
         << ",\"action\":\"" << (action && *action ? action : "botauto_profiles") << "\""
         << ",\"manifest_path\":\"" << JsonEscape(Cohort().ProfileManifestPath) << "\""
         << ",\"active_profile\":" << (Cohort().SelectedProfileName.empty() ? "null" : ("\"" + JsonEscape(Cohort().SelectedProfileName) + "\""))
         << ",\"profile_count\":" << Cohort().RuntimeProfiles.size()
         << ",\"loaded\":" << (Cohort().RuntimeProfilesLoaded ? "true" : "false")
         << ",\"failure_reason\":" << (Cohort().ProfileManifestLoadError.empty() ? "null" : ("\"" + JsonEscape(Cohort().ProfileManifestLoadError) + "\""))
         << ",\"profiles\":[";
    bool first = true;
    for (std::string const& name : Cohort().RuntimeProfileOrder)
    {
        auto itr = Cohort().RuntimeProfiles.find(name);
        if (itr == Cohort().RuntimeProfiles.end())
            continue;
        if (!first)
            json << ",";
        first = false;
        BotWorldExperimentProfile const& profile = itr->second;
        json << "{\"name\":\"" << JsonEscape(profile.Name) << "\""
             << ",\"description\":\"" << JsonEscape(profile.Description) << "\""
             << ",\"target_population\":" << (profile.HasTargetPopulation ? profile.Config.TargetPopulation : 0)
             << ",\"pool_tag_filter\":\"" << JsonEscape(profile.HasPoolTagFilter ? profile.Config.PoolTagFilter : "") << "\""
             << ",\"spawn_mode\":\"" << JsonEscape(profile.HasSpawnMode ? profile.Config.SpawnMode : "") << "\""
             << ",\"validation_route_manifest_path\":\"" << JsonEscape(profile.HasValidationRouteManifestPath ? profile.Config.ValidationRouteManifestPath : "") << "\""
             << ",\"validation_route_scenario_id\":\"" << JsonEscape(profile.HasValidationRouteScenarioId ? profile.Config.ValidationRouteScenarioId : "") << "\"}";
    }
    json << "]}";
    return json.str();
}

bool BotWorldPopulationMgr::EnsureRuntimeProfilesLoaded()
{
    if (Cohort().RuntimeProfilesLoaded)
        return Cohort().ProfileManifestLoadError.empty();
    return LoadRuntimeProfiles(nullptr);
}

bool BotWorldPopulationMgr::LoadRuntimeProfiles(std::string* failureReason)
{
    Cohort().ProfileManifestPath = sConfigMgr->GetStringDefault("BotWorld.ProfileManifest", Cohort().ProfileManifestPath.empty() ? "dataset/bot_runtime_profiles/profiles.json" : Cohort().ProfileManifestPath);
    Cohort().RuntimeProfiles.clear();
    Cohort().RuntimeProfileOrder.clear();
    Cohort().ProfileManifestLoadError.clear();
    Cohort().RuntimeProfilesLoaded = true;

    if (Cohort().ProfileManifestPath.empty())
        return true;

    std::string manifestJson = ReadSmallTextFile(Cohort().ProfileManifestPath);
    if (manifestJson.empty())
    {
        Cohort().ProfileManifestLoadError = "profile_manifest_unreadable";
        if (failureReason)
            *failureReason = Cohort().ProfileManifestLoadError;
        return false;
    }

    std::string profilesJson = ExtractJsonArrayField(manifestJson, "profiles");
    if (profilesJson.empty())
    {
        Cohort().ProfileManifestLoadError = "profile_manifest_profiles_missing";
        if (failureReason)
            *failureReason = Cohort().ProfileManifestLoadError;
        return false;
    }

    auto fail = [this, failureReason](std::string const& reason) -> bool
    {
        Cohort().RuntimeProfiles.clear();
        Cohort().RuntimeProfileOrder.clear();
        Cohort().ProfileManifestLoadError = reason;
        if (failureReason)
            *failureReason = reason;
        return false;
    };

    auto readString = [&fail](std::string const& objectJson, char const* key, std::string& value, bool& present) -> bool
    {
        present = JsonHasField(objectJson, key);
        if (!present)
            return true;
        if (!JsonFieldIsString(objectJson, key))
            return fail(std::string("profile_bad_type_") + key);
        value = ExtractJsonStringField(objectJson, key);
        return true;
    };
    auto readBool = [&fail](std::string const& objectJson, char const* key, bool& value, bool& present) -> bool
    {
        present = JsonHasField(objectJson, key);
        if (!present)
            return true;
        if (!JsonFieldIsBool(objectJson, key) || !ExtractJsonBoolField(objectJson, key, value))
            return fail(std::string("profile_bad_type_") + key);
        return true;
    };
    auto readUInt = [&fail](std::string const& objectJson, char const* key, uint32& value, bool& present) -> bool
    {
        present = JsonHasField(objectJson, key);
        if (!present)
            return true;
        if (!JsonFieldIsNumber(objectJson, key))
            return fail(std::string("profile_bad_type_") + key);
        int parsed = 0;
        if (!ExtractJsonIntField(objectJson, key, parsed) || parsed < 0)
            return fail(std::string("profile_bad_type_") + key);
        value = uint32(parsed);
        return true;
    };
    auto readFloat = [&fail](std::string const& objectJson, char const* key, float& value, bool& present) -> bool
    {
        present = JsonHasField(objectJson, key);
        if (!present)
            return true;
        if (!JsonFieldIsNumber(objectJson, key) || !ExtractJsonNumberField(objectJson, key, value))
            return fail(std::string("profile_bad_type_") + key);
        return true;
    };

    for (std::string const& profileJson : ExtractJsonObjectArrayItems(profilesJson))
    {
        BotWorldExperimentProfile profile;
        profile.Config = BotWorldExperimentConfig();
        bool present = false;
        if (!readString(profileJson, "name", profile.Name, present))
            return false;
        if (!present || profile.Name.empty())
            return fail("profile_missing_name");
        if (Cohort().RuntimeProfiles.find(profile.Name) != Cohort().RuntimeProfiles.end())
            return fail("profile_duplicate_name");

        if (!readString(profileJson, "description", profile.Description, present)) return false;
        uint32 uintValue = 0;
        float floatValue = 0.0f;
        bool boolValue = false;
        std::string stringValue;

        if (!readUInt(profileJson, "target_population", uintValue, profile.HasTargetPopulation)) return false;
        if (profile.HasTargetPopulation) profile.Config.TargetPopulation = std::max<uint32>(1, uintValue);
        if (!readUInt(profileJson, "map", uintValue, profile.HasMapId)) return false;
        if (profile.HasMapId) profile.Config.MapId = uintValue;
        if (!readUInt(profileJson, "zone", uintValue, profile.HasZoneId)) return false;
        if (profile.HasZoneId) profile.Config.ZoneId = uintValue;
        bool hasX = false, hasY = false, hasZ = false;
        if (!readFloat(profileJson, "center_x", profile.Config.CenterX, hasX)) return false;
        if (!readFloat(profileJson, "center_y", profile.Config.CenterY, hasY)) return false;
        if (!readFloat(profileJson, "center_z", profile.Config.CenterZ, hasZ)) return false;
        profile.HasCenter = hasX || hasY || hasZ;
        if (!readFloat(profileJson, "radius", floatValue, profile.HasRadius)) return false;
        if (profile.HasRadius) profile.Config.Radius = std::max(1.0f, floatValue);
        if (!readBool(profileJson, "allow_combat", boolValue, profile.HasAllowCombat)) return false;
        if (profile.HasAllowCombat) profile.Config.AllowCombat = boolValue;
        if (!readBool(profileJson, "allow_grinding", boolValue, profile.HasAllowGrinding)) return false;
        if (profile.HasAllowGrinding) profile.Config.AllowGrinding = boolValue;
        if (!readBool(profileJson, "allow_questing", boolValue, profile.HasAllowQuesting)) return false;
        if (profile.HasAllowQuesting) profile.Config.AllowQuesting = boolValue;
        if (!readBool(profileJson, "allow_dungeons", boolValue, profile.HasAllowDungeons)) return false;
        if (profile.HasAllowDungeons) profile.Config.AllowDungeons = boolValue;
        if (!readBool(profileJson, "allow_raids", boolValue, profile.HasAllowRaids)) return false;
        if (profile.HasAllowRaids) profile.Config.AllowRaids = boolValue;
        if (!readUInt(profileJson, "dungeon_difficulty", uintValue, profile.HasDungeonDifficulty)) return false;
        if (profile.HasDungeonDifficulty)
        {
            if (uintValue >= MAX_DUNGEON_DIFFICULTY)
                return fail("profile_bad_dungeon_difficulty");
            profile.Config.DungeonDifficulty = uint8(uintValue);
        }
        if (!readUInt(profileJson, "raid_size", uintValue, profile.HasRaidSize)) return false;
        if (profile.HasRaidSize)
        {
            if (uintValue != 10 && uintValue != 25)
                return fail("profile_bad_raid_size");
            profile.Config.RaidSize = uint8(uintValue);
        }
        if (!readUInt(profileJson, "raid_difficulty", uintValue, profile.HasRaidDifficulty)) return false;
        if (profile.HasRaidDifficulty)
        {
            if (uintValue >= MAX_RAID_DIFFICULTY)
                return fail("profile_bad_raid_difficulty");
            profile.Config.RaidDifficulty = uint8(uintValue);
        }
        if (!readBool(profileJson, "track_heroic_raid_progression", boolValue, profile.HasTrackHeroicRaidProgression)) return false;
        if (profile.HasTrackHeroicRaidProgression) profile.Config.TrackHeroicRaidProgression = boolValue;
        if (!readBool(profileJson, "enable_progression", boolValue, profile.HasEnableProgression)) return false;
        if (profile.HasEnableProgression) profile.Config.EnableProgression = boolValue;
        if (!readBool(profileJson, "record_decisions", boolValue, profile.HasRecordDecisions)) return false;
        if (profile.HasRecordDecisions) profile.Config.RecordDecisions = boolValue;
        if (!readBool(profileJson, "record_perception", boolValue, profile.HasRecordPerception)) return false;
        if (profile.HasRecordPerception) profile.Config.RecordPerception = boolValue;
        if (!readBool(profileJson, "smart_sampling", boolValue, profile.HasSmartSampling)) return false;
        if (profile.HasSmartSampling) profile.Config.SmartSampling = boolValue;
        if (!readString(profileJson, "pool_tag_filter", stringValue, profile.HasPoolTagFilter)) return false;
        if (profile.HasPoolTagFilter) profile.Config.PoolTagFilter = stringValue;
        if (!readString(profileJson, "spawn_mode", stringValue, profile.HasSpawnMode)) return false;
        if (profile.HasSpawnMode) profile.Config.SpawnMode = stringValue;
        if (!readBool(profileJson, "allow_configured_center_fallback", boolValue, profile.HasAllowConfiguredCenterFallback)) return false;
        if (profile.HasAllowConfiguredCenterFallback) profile.Config.AllowConfiguredCenterFallback = boolValue;
        if (!readBool(profileJson, "use_saved_position", boolValue, profile.HasUseSavedPosition)) return false;
        if (profile.HasUseSavedPosition) profile.Config.UseSavedPosition = boolValue;
        if (!readFloat(profileJson, "near_player_radius", floatValue, profile.HasNearPlayerRadius)) return false;
        if (profile.HasNearPlayerRadius) profile.Config.NearPlayerRadius = std::max(1.0f, floatValue);
        if (!readString(profileJson, "death_recovery_mode", stringValue, profile.HasDeathRecoveryMode)) return false;
        if (profile.HasDeathRecoveryMode) profile.Config.DeathRecoveryMode = stringValue;
        if (!readBool(profileJson, "auto_start_recording", boolValue, profile.HasAutoStartRecording)) return false;
        if (profile.HasAutoStartRecording) profile.Config.AutoStartRecording = boolValue;
        if (!readUInt(profileJson, "auto_recording_window_minutes", uintValue, profile.HasAutoRecordingWindowMinutes)) return false;
        if (profile.HasAutoRecordingWindowMinutes) profile.Config.AutoRecordingWindowMinutes = std::max<uint32>(1, uintValue);
        if (!readString(profileJson, "auto_recording_name_prefix", stringValue, profile.HasAutoRecordingNamePrefix)) return false;
        if (profile.HasAutoRecordingNamePrefix) profile.Config.AutoRecordingNamePrefix = stringValue;

        std::string routeJson = ExtractJsonObjectField(profileJson, "validation_route");
        std::string const& routeSource = routeJson.empty() ? profileJson : routeJson;
        if (!readBool(routeSource, "enable", boolValue, profile.HasValidationRouteEnable)) return false;
        if (profile.HasValidationRouteEnable) profile.Config.ValidationRouteEnable = boolValue;
        if (!readString(routeSource, "manifest_path", stringValue, profile.HasValidationRouteManifestPath)) return false;
        if (profile.HasValidationRouteManifestPath) profile.Config.ValidationRouteManifestPath = stringValue;
        if (!readString(routeSource, "advance_mode", stringValue, profile.HasValidationRouteAdvanceMode)) return false;
        if (profile.HasValidationRouteAdvanceMode) profile.Config.ValidationRouteAdvanceMode = stringValue;
        if (!readString(routeSource, "scenario_id", stringValue, profile.HasValidationRouteScenarioId)) return false;
        if (profile.HasValidationRouteScenarioId) profile.Config.ValidationRouteScenarioId = stringValue;
        if (!readString(routeSource, "node_id", stringValue, profile.HasValidationRouteNodeId)) return false;
        if (profile.HasValidationRouteNodeId) profile.Config.ValidationRouteNodeId = stringValue;
        if (!readString(routeSource, "label", stringValue, profile.HasValidationRouteLabel)) return false;
        if (profile.HasValidationRouteLabel) profile.Config.ValidationRouteLabel = stringValue;
        if (!readString(routeSource, "kind", stringValue, profile.HasValidationRouteKind)) return false;
        if (profile.HasValidationRouteKind) profile.Config.ValidationRouteKind = stringValue;
        if (!readString(routeSource, "mechanic_profile", stringValue, profile.HasValidationRouteMechanicProfile)) return false;
        if (profile.HasValidationRouteMechanicProfile) profile.Config.ValidationRouteMechanicProfile = stringValue;

        Cohort().RuntimeProfileOrder.push_back(profile.Name);
        Cohort().RuntimeProfiles[profile.Name] = profile;
    }

    if (Cohort().RuntimeProfiles.empty())
        return fail("profile_manifest_profiles_empty");

    if (!Cohort().SelectedProfileName.empty() && Cohort().RuntimeProfiles.find(Cohort().SelectedProfileName) == Cohort().RuntimeProfiles.end())
    {
        Cohort().SelectedProfileName.clear();
        Cohort().RuntimeProfileDirty = true;
        Cohort().RuntimeProfileSelectionPending = false;
    }
    return true;
}

std::string BotWorldPopulationMgr::GetRuntimeProfilesJson()
{
    EnsureRuntimeProfilesLoaded();
    return RuntimeProfilesJson("botauto_profiles");
}

std::string BotWorldPopulationMgr::SelectRuntimeProfile(std::string const& name)
{
    EnsureRuntimeProfilesLoaded();
    if (name.empty())
        return "{\"ok\":false,\"action\":\"botauto_profile\",\"failure_reason\":\"usage: .botauto profile <name>|clear|reload\"}";
    auto itr = Cohort().RuntimeProfiles.find(name);
    if (itr == Cohort().RuntimeProfiles.end())
        return "{\"ok\":false,\"action\":\"botauto_profile\",\"failure_reason\":\"unknown_profile\",\"profile\":\"" + JsonEscape(name) + "\"}";

    Cohort().SelectedProfileName = name;
    Cohort().RuntimeProfileDirty = true;
    Cohort().RuntimeProfileSelectionPending = true;
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_profile\",\"active_profile\":\"" << JsonEscape(Cohort().SelectedProfileName)
         << "\",\"cohort_id\":\"" << JsonEscape(Cohort().Id)
         << "\",\"profile_count\":" << Cohort().RuntimeProfiles.size()
         << ",\"failure_reason\":null}";
    return json.str();
}

std::string BotWorldPopulationMgr::ClearRuntimeProfile()
{
    Cohort().SelectedProfileName.clear();
    Cohort().RuntimeProfileDirty = true;
    Cohort().RuntimeProfileSelectionPending = false;
    // Clearing the selected runtime profile is a destructive recording
    // lifecycle boundary. Route-node advancement is not: its transition
    // event and any unexported rows must remain in the same monotonic stream.
    ResetTraceStreams();
    ResetValidationRouteRuntimeState("runtime_profile_clear");
    return "{\"ok\":true,\"action\":\"botauto_profile_clear\",\"active_profile\":null,\"failure_reason\":null}";
}

std::string BotWorldPopulationMgr::ReloadRuntimeProfiles()
{
    std::string failure;
    bool ok = LoadRuntimeProfiles(&failure);
    Cohort().RuntimeProfileDirty = true;
    return RuntimeProfilesJson(ok ? "botauto_profile_reload" : "botauto_profile_reload");
}

bool BotWorldPopulationMgr::SelectConfiguredRuntimeProfile()
{
    std::string configuredProfile = sConfigMgr->GetStringDefault("BotWorld.RuntimeProfile", "");
    if (configuredProfile.empty())
        return true;

    EnsureRuntimeProfilesLoaded();
    auto profileItr = Cohort().RuntimeProfiles.find(configuredProfile);
    if (profileItr == Cohort().RuntimeProfiles.end())
    {
        TC_LOG_ERROR("server", "BotWorld configured runtime profile missing profile=%s manifest=%s failure_reason=%s",
            configuredProfile.c_str(), Cohort().ProfileManifestPath.c_str(), Cohort().ProfileManifestLoadError.empty() ? "unknown_profile" : Cohort().ProfileManifestLoadError.c_str());
        return false;
    }

    Cohort().SelectedProfileName = configuredProfile;
    return true;
}

