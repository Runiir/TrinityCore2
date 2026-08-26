#include "Bots/BotWorldPopulationMgr.h"

#include "Cryptography/CryptoHash.h"
#include "Util.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <regex>
#include <set>
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


std::set<std::string> ExtractJsonTopLevelKeys(std::string const& objectJson)
{
    std::set<std::string> keys;
    uint32 depth = 0;
    bool inString = false;
    bool escaped = false;
    size_t stringStart = std::string::npos;
    for (size_t i = 0; i < objectJson.size(); ++i)
    {
        char const c = objectJson[i];
        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '"')
            {
                inString = false;
                if (depth == 1 && stringStart != std::string::npos)
                {
                    size_t next = i + 1;
                    while (next < objectJson.size() && std::isspace(static_cast<unsigned char>(objectJson[next])))
                        ++next;
                    if (next < objectJson.size() && objectJson[next] == ':')
                        keys.insert(objectJson.substr(stringStart, i - stringStart));
                }
            }
            continue;
        }
        if (c == '"')
        {
            inString = true;
            stringStart = i + 1;
        }
        else if (c == '{' || c == '[')
            ++depth;
        else if ((c == '}' || c == ']') && depth)
            --depth;
    }
    return keys;
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


std::vector<uint32> ParseUIntList(std::string const& text)
{
    std::vector<uint32> values;
    std::regex pattern("([0-9]+)");
    for (std::sregex_iterator itr(text.begin(), text.end(), pattern), end; itr != end; ++itr)
    {
        uint32 value = uint32(std::strtoul((*itr)[1].str().c_str(), nullptr, 10));
        if (value && std::find(values.begin(), values.end(), value) == values.end())
            values.push_back(value);
    }
    return values;
}


std::vector<uint32> ExtractJsonUIntArrayField(std::string const& json, std::string const& key)
{
    return ParseUIntList(ExtractJsonArrayField(json, key));
}


bool ExtractJsonStrictUIntArrayField(std::string const& json, std::string const& key,
    std::vector<uint32>& values)
{
    values.clear();
    std::string const array = ExtractJsonArrayField(json, key);
    if (array.size() < 2 || array.front() != '[')
        return false;

    size_t index = 1;
    auto skipWhitespace = [&]()
    {
        while (index < array.size()
            && std::isspace(static_cast<unsigned char>(array[index])))
            ++index;
    };
    skipWhitespace();
    if (index < array.size() && array[index] == ']')
    {
        ++index;
        skipWhitespace();
        return index == array.size();
    }

    while (index < array.size())
    {
        if (!std::isdigit(static_cast<unsigned char>(array[index])))
            return false;
        uint64 value = 0;
        while (index < array.size()
            && std::isdigit(static_cast<unsigned char>(array[index])))
        {
            uint64 const digit = uint64(array[index] - '0');
            if (value > (std::numeric_limits<uint32>::max() - digit) / 10)
                return false;
            value = value * 10 + digit;
            ++index;
        }
        values.push_back(uint32(value));
        skipWhitespace();
        if (index >= array.size())
            return false;
        if (array[index] == ']')
        {
            ++index;
            skipWhitespace();
            return index == array.size();
        }
        if (array[index] != ',')
            return false;
        ++index;
        skipWhitespace();
    }
    return false;
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


std::vector<std::string> ExtractJsonLineObjects(std::string const& text)
{
    std::vector<std::string> items;
    std::istringstream input(text);
    std::string line;
    while (std::getline(input, line))
    {
        size_t first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos || line[first] != '{')
            continue;
        items.push_back(line.substr(first));
    }
    return items;
}

}

void BotWorldPopulationMgr::LoadValidationRouteManifest()
{
    Party().ValidationRoutePendingFinalTransitionGuids.clear();
    Party().ValidationRouteFinalTransitionGuids.clear();
    Party().ValidationRouteManifestSha256.clear();
    if (Cohort().Config.ValidationRouteManifestPath.empty())
        return;

    std::string manifestJson = ReadSmallTextFile(Cohort().Config.ValidationRouteManifestPath);
    if (manifestJson.empty())
    {
        Party().ValidationRouteManifestLoadError = "manifest_unreadable";
        return;
    }
    Party().ValidationRouteManifestSha256 = ByteArrayToHexStr(
        Trinity::Crypto::SHA256::GetDigestOf(manifestJson));
    std::transform(
        Party().ValidationRouteManifestSha256.begin(),
        Party().ValidationRouteManifestSha256.end(),
        Party().ValidationRouteManifestSha256.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });

    std::string routesJson = ExtractJsonArrayField(manifestJson, "routes");
    std::vector<std::string> routeObjects = routesJson.empty()
        ? ExtractJsonLineObjects(manifestJson)
        : ExtractJsonObjectArrayItems(routesJson);
    if (routeObjects.empty())
    {
        Party().ValidationRouteManifestLoadError = "manifest_routes_missing";
        return;
    }

    auto readInt = [](std::string const& objectJson, char const* key) -> int
    {
        int value = 0;
        ExtractJsonIntField(objectJson, key, value);
        return value;
    };
    auto readFloat = [](std::string const& objectJson, char const* key) -> float
    {
        float value = 0.0f;
        ExtractJsonNumberField(objectJson, key, value);
        return value;
    };

    for (std::string const& routeJson : routeObjects)
    {
        ValidationRouteManifestNode node;
        node.ScenarioId = ExtractJsonStringField(routeJson, "scenario_id");
        if (!Cohort().Config.ValidationRouteScenarioId.empty() && node.ScenarioId != Cohort().Config.ValidationRouteScenarioId)
            continue;
        node.RuntimeProfileId = ExtractJsonStringField(routeJson, "runtime_profile_id");
        // Diagnostic partitions are profile-owned. A missing or foreign
        // profile binding must stop native admission before any lease or bot
        // spawn; the historical canonical manifest is allowed to omit this
        // field for compatibility with its frozen identity contract.
        bool const dynamicValidationProfile = Cohort().Config.Name != "stonecore_5n"
            && Cohort().Config.Name != "blackwing_descent_10n";
        if ((dynamicValidationProfile && node.RuntimeProfileId.empty())
            || (!node.RuntimeProfileId.empty() && node.RuntimeProfileId != Cohort().Config.Name))
        {
            Party().ValidationRouteManifestLoadError = "manifest_runtime_profile_identity_mismatch";
            return;
        }
        node.NodeId = ExtractJsonStringField(routeJson, "route_node_id");
        node.Label = ExtractJsonStringField(routeJson, "label");
        node.Kind = ExtractJsonStringField(routeJson, "kind");
        node.NodeKind = ExtractJsonStringField(routeJson, "node_kind");
        node.DescentAction = ExtractJsonStringField(routeJson, "descent_action");
        node.MechanicProfile = ExtractJsonStringField(routeJson, "mechanic_profile");
        std::string const bossRecoveryPolicy = ExtractJsonStringField(routeJson, "boss_recovery_policy");
        if (bossRecoveryPolicy == "native_full_wipe_only")
            node.BossRecoveryPolicy = ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly;
        else
            node.BossRecoveryPolicy = ValidationRouteBossRecoveryPolicy::NativeEncounter;
        std::string const mechanicContract = ExtractJsonObjectField(routeJson, "mechanic_contract");
        if (!mechanicContract.empty())
        {
            static std::set<std::string> const AllowedMechanicContractFields =
            {
                "id", "formation_family", "formation_anchor", "formation_scope", "formation_orientation",
                "spacing_yards", "minimum_distance_yards", "radius_yards", "arc_radians", "lane_count",
                "arrival_tolerance_yards", "target_control", "target_entries", "allow_area_damage",
                "allow_multidot", "controlled_aoe_minimum_targets", "kill_sync_tolerance_pct",
                "kill_sync_execution_floor_pct", "tank_swap_trigger", "tank_swap_aura_id",
                "tank_swap_aura_stacks", "tank_swap_interval_ms", "tank_swap_trigger_spell_id",
                "tank_swap_add_entry", "tank_swap_phase", "interrupt_owner_slot", "interrupt_backup_slot",
                "interrupt_trigger_spell_id", "dispel_aura_id", "dispel_owner_slot", "dispel_backup_slot",
                "healer_ownership", "healer_owner_slots", "cooldown_category", "cooldown_owner_slot",
                "cooldown_backup_slot", "cooldown_trigger_spell_id", "cooldown_target", "soak_roster_slots",
                "soak_minimum_count", "soak_radius_yards", "soak_trigger_spell_id", "soak_trigger_aura_id",
                "soak_immunity_spell_id", "soak_personal_cooldown_spell_id", "battle_resurrection_policy",
                "battle_resurrection_slots", "interaction_kind", "interactable_entry", "vehicle_entry",
                "transport_entry", "jump_pad_entry", "extra_action_spell_id", "extra_action_trigger_aura_id",
                "movement_link", "transfer_area_trigger_id", "platform_policy", "platform_destination_map_id",
                "platform_destination_area_id", "platform_minimum_z", "platform_maximum_z"
            };
            for (std::string const& key : ExtractJsonTopLevelKeys(mechanicContract))
                if (AllowedMechanicContractFields.find(key) == AllowedMechanicContractFields.end())
                {
                    node.MechanicContractError = "unknown_field:" + key;
                    break;
                }
            node.MechanicContractId = ExtractJsonStringField(mechanicContract, "id");
            node.FormationFamily = ExtractJsonStringField(mechanicContract, "formation_family");
            node.FormationAnchor = ExtractJsonStringField(mechanicContract, "formation_anchor");
            node.FormationScope = ExtractJsonStringField(mechanicContract, "formation_scope");
            if (node.FormationScope.empty())
                node.FormationScope = "raid";
            node.FormationOrientation = ExtractJsonStringField(mechanicContract, "formation_orientation");
            node.TargetControl = ExtractJsonStringField(mechanicContract, "target_control");
            node.FormationSpacingYards = readFloat(mechanicContract, "spacing_yards");
            node.FormationMinimumDistanceYards = readFloat(mechanicContract, "minimum_distance_yards");
            node.FormationRadiusYards = readFloat(mechanicContract, "radius_yards");
            node.FormationArcRadians = readFloat(mechanicContract, "arc_radians");
            node.FormationArrivalToleranceYards = readFloat(mechanicContract, "arrival_tolerance_yards");
            node.FormationLaneCount = uint32(std::max(0, readInt(mechanicContract, "lane_count")));
            ExtractJsonBoolField(mechanicContract, "allow_area_damage", node.AllowAreaDamage);
            ExtractJsonBoolField(mechanicContract, "allow_multidot", node.AllowMultidot);
            node.TargetEntries = ExtractJsonUIntArrayField(mechanicContract, "target_entries");
            node.ControlledAoeMinimumTargets = uint32(std::max(0, readInt(mechanicContract, "controlled_aoe_minimum_targets")));
            node.KillSyncTolerancePct = readFloat(mechanicContract, "kill_sync_tolerance_pct");
            node.KillSyncExecutionFloorPct = readFloat(mechanicContract, "kill_sync_execution_floor_pct");
            node.TankSwapTrigger = ExtractJsonStringField(mechanicContract, "tank_swap_trigger");
            node.TankSwapAuraId = uint32(std::max(0, readInt(mechanicContract, "tank_swap_aura_id")));
            node.TankSwapAuraStacks = uint32(std::max(0, readInt(mechanicContract, "tank_swap_aura_stacks")));
            node.TankSwapIntervalMs = uint32(std::max(0, readInt(mechanicContract, "tank_swap_interval_ms")));
            node.TankSwapTriggerSpellId = uint32(std::max(0, readInt(mechanicContract, "tank_swap_trigger_spell_id")));
            node.TankSwapAddEntry = uint32(std::max(0, readInt(mechanicContract, "tank_swap_add_entry")));
            node.TankSwapPhase = ExtractJsonStringField(mechanicContract, "tank_swap_phase");
            node.InterruptOwnerSlot = uint32(std::max(0, readInt(mechanicContract, "interrupt_owner_slot")));
            node.InterruptBackupSlot = uint32(std::max(0, readInt(mechanicContract, "interrupt_backup_slot")));
            node.InterruptTriggerSpellId = uint32(std::max(0, readInt(mechanicContract, "interrupt_trigger_spell_id")));
            node.InteractableEntry = uint32(std::max(0, readInt(mechanicContract, "interactable_entry")));
            node.VehicleEntry = uint32(std::max(0, readInt(mechanicContract, "vehicle_entry")));
            node.TransportEntry = uint32(std::max(0, readInt(mechanicContract, "transport_entry")));
            node.TransferAreaTriggerId = uint32(std::max(0, readInt(mechanicContract, "transfer_area_trigger_id")));
            node.ExtraActionSpellId = uint32(std::max(0, readInt(mechanicContract, "extra_action_spell_id")));
            node.ExtraActionTriggerAuraId = uint32(std::max(0, readInt(mechanicContract, "extra_action_trigger_aura_id")));
            node.DispelAuraId = uint32(std::max(0, readInt(mechanicContract, "dispel_aura_id")));
            node.DispelOwnerSlot = uint32(std::max(0, readInt(mechanicContract, "dispel_owner_slot")));
            node.DispelBackupSlot = uint32(std::max(0, readInt(mechanicContract, "dispel_backup_slot")));
            node.CooldownCategory = ExtractJsonStringField(mechanicContract, "cooldown_category");
            node.CooldownOwnerSlot = uint32(std::max(0, readInt(mechanicContract, "cooldown_owner_slot")));
            node.CooldownBackupSlot = uint32(std::max(0, readInt(mechanicContract, "cooldown_backup_slot")));
            node.CooldownTriggerSpellId = uint32(std::max(0, readInt(mechanicContract, "cooldown_trigger_spell_id")));
            node.CooldownTarget = ExtractJsonStringField(mechanicContract, "cooldown_target");
            if (node.CooldownTarget.empty())
                node.CooldownTarget = "self";
            node.HealerOwnership = ExtractJsonStringField(mechanicContract, "healer_ownership");
            if (node.HealerOwnership.empty())
                node.HealerOwnership = "raid_triage";
            node.HealerOwnerSlots = ExtractJsonUIntArrayField(mechanicContract, "healer_owner_slots");
            node.SoakRosterSlots = ExtractJsonUIntArrayField(mechanicContract, "soak_roster_slots");
            node.SoakMinimumCount = uint32(std::max(0, readInt(mechanicContract, "soak_minimum_count")));
            node.SoakRadiusYards = readFloat(mechanicContract, "soak_radius_yards");
            node.SoakTriggerSpellId = uint32(std::max(0, readInt(mechanicContract, "soak_trigger_spell_id")));
            node.SoakTriggerAuraId = uint32(std::max(0, readInt(mechanicContract, "soak_trigger_aura_id")));
            node.SoakImmunitySpellId = uint32(std::max(0, readInt(mechanicContract, "soak_immunity_spell_id")));
            node.SoakPersonalCooldownSpellId = uint32(std::max(0, readInt(mechanicContract, "soak_personal_cooldown_spell_id")));
            node.BattleResurrectionPolicy = ExtractJsonStringField(mechanicContract, "battle_resurrection_policy");
            if (node.BattleResurrectionPolicy.empty())
                node.BattleResurrectionPolicy = "native_rotation";
            node.BattleResurrectionSlots = ExtractJsonUIntArrayField(mechanicContract, "battle_resurrection_slots");
            node.InteractionKind = ExtractJsonStringField(mechanicContract, "interaction_kind");
            if (node.InteractionKind.empty())
                node.InteractionKind = "none";
            node.JumpPadEntry = uint32(std::max(0, readInt(mechanicContract, "jump_pad_entry")));
            node.MovementLink = ExtractJsonStringField(mechanicContract, "movement_link");
            if (node.MovementLink.empty())
                node.MovementLink = "none";
            node.PlatformPolicy = ExtractJsonStringField(mechanicContract, "platform_policy");
            if (node.PlatformPolicy.empty())
                node.PlatformPolicy = "ground";
            node.PlatformDestinationMapId = uint32(std::max(0, readInt(mechanicContract, "platform_destination_map_id")));
            node.PlatformDestinationAreaId = uint32(std::max(0, readInt(mechanicContract, "platform_destination_area_id")));
            node.PlatformMinimumZ = readFloat(mechanicContract, "platform_minimum_z");
            node.PlatformMaximumZ = readFloat(mechanicContract, "platform_maximum_z");
            bool const knownFormation = node.FormationFamily.empty()
                || node.FormationFamily == "stack" || node.FormationFamily == "spread"
                || node.FormationFamily == "pair" || node.FormationFamily == "lane"
                || node.FormationFamily == "quadrant" || node.FormationFamily == "ring"
                || node.FormationFamily == "cone" || node.FormationFamily == "behind"
                || node.FormationFamily == "front_exclusion";
            bool const knownAnchor = node.FormationFamily.empty()
                || node.FormationAnchor == "route_anchor" || node.FormationAnchor == "boss"
                || node.FormationAnchor == "main_tank" || node.FormationAnchor == "raid_leader"
                || node.FormationAnchor == "role" || node.FormationAnchor == "subgroup";
            bool const knownScope = node.FormationScope == "raid" || node.FormationScope == "role"
                || node.FormationScope == "subgroup";
            bool const knownOrientation = node.FormationFamily.empty()
                || node.FormationOrientation == "route" || node.FormationOrientation == "boss_facing"
                || node.FormationOrientation == "anchor_to_boss";
            bool const formationResolved = node.FormationFamily.empty()
                || (node.FormationArrivalToleranceYards > 0.0f
                    && (node.FormationFamily == "stack" || node.FormationSpacingYards > 0.0f
                        || node.FormationRadiusYards > 0.0f || node.FormationMinimumDistanceYards > 0.0f)
                    && (node.FormationFamily != "lane" || node.FormationLaneCount > 0)
                    && ((node.FormationFamily != "cone" && node.FormationFamily != "behind"
                            && node.FormationFamily != "front_exclusion")
                        || node.FormationArcRadians > 0.0f));
            bool const targetResolved = node.TargetControl.empty()
                || ((node.TargetControl == "focus_fire" || node.TargetControl == "multidot"
                        || node.TargetControl == "do_not_damage") && !node.TargetEntries.empty()
                    && (node.TargetControl != "focus_fire" || (!node.AllowMultidot && !node.AllowAreaDamage)))
                || (node.TargetControl == "controlled_aoe" && node.AllowAreaDamage
                    && !node.AllowMultidot && node.ControlledAoeMinimumTargets > 0
                    && !node.TargetEntries.empty())
                || (node.TargetControl == "kill_sync" && node.KillSyncTolerancePct > 0.0f
                    && node.KillSyncExecutionFloorPct > 0.0f && !node.TargetEntries.empty());
            bool const tankSwapResolved = node.TankSwapTrigger.empty()
                || (node.TankSwapTrigger == "debuff_stacks" && node.TankSwapAuraId > 0 && node.TankSwapAuraStacks > 0)
                || (node.TankSwapTrigger == "timer" && node.TankSwapIntervalMs > 0)
                || (node.TankSwapTrigger == "boss_cast" && node.TankSwapTriggerSpellId > 0)
                || (node.TankSwapTrigger == "add_spawn" && node.TankSwapAddEntry > 0)
                || (node.TankSwapTrigger == "phase_transition" && !node.TankSwapPhase.empty());
            bool const interruptResolved = !node.InterruptOwnerSlot
                || (node.InterruptBackupSlot > 0 && node.InterruptOwnerSlot != node.InterruptBackupSlot
                    && node.InterruptTriggerSpellId > 0);
            bool const dispelResolved = !node.DispelAuraId
                || (node.DispelOwnerSlot > 0 && node.DispelBackupSlot > 0
                    && node.DispelOwnerSlot != node.DispelBackupSlot);
            bool const cooldownResolved = node.CooldownCategory.empty()
                || (node.CooldownOwnerSlot > 0 && node.CooldownTriggerSpellId > 0
                    && (node.CooldownTarget == "self" || node.CooldownTarget == "tank"
                        || node.CooldownTarget == "lowest" || node.CooldownTarget == "subgroup"));
            bool const soakResolved = node.SoakRosterSlots.empty()
                || (node.SoakMinimumCount > 0 && node.SoakRadiusYards > 0.0f
                    && node.SoakMinimumCount <= node.SoakRosterSlots.size());
            bool const extraActionResolved = !node.ExtraActionSpellId || node.ExtraActionTriggerAuraId > 0;
            bool const knownHealerOwnership = node.HealerOwnership == "raid_triage"
                || node.HealerOwnership == "subgroup" || node.HealerOwnership == "tank"
                || node.HealerOwnership == "tank_and_subgroup";
            bool const knownBattleRes = node.BattleResurrectionPolicy == "native_rotation"
                || node.BattleResurrectionPolicy == "tank_then_healer_then_dps"
                || node.BattleResurrectionPolicy == "assigned_only";
            std::set<uint32> const uniqueBattleResSlots(
                node.BattleResurrectionSlots.begin(), node.BattleResurrectionSlots.end());
            bool const battleResSlotsValid = node.BattleResurrectionSlots.empty()
                || (uniqueBattleResSlots.size() == node.BattleResurrectionSlots.size()
                    && std::all_of(node.BattleResurrectionSlots.begin(), node.BattleResurrectionSlots.end(),
                        [this](uint32 slot) { return slot > 0 && slot <= Cohort().Config.RaidSize; }));
            bool const battleResResolved = node.BattleResurrectionPolicy != "assigned_only"
                ? battleResSlotsValid : (!node.BattleResurrectionSlots.empty() && battleResSlotsValid);
            bool const knownInteraction = node.InteractionKind == "none" || node.InteractionKind == "object"
                || node.InteractionKind == "extra_action" || node.InteractionKind == "vehicle"
                || node.InteractionKind == "transport" || node.InteractionKind == "jump_pad";
            bool const interactionResolved = (node.InteractionKind == "none")
                || (node.InteractionKind == "object" && node.InteractableEntry > 0)
                || (node.InteractionKind == "extra_action" && node.ExtraActionSpellId > 0 && extraActionResolved)
                || (node.InteractionKind == "vehicle" && node.VehicleEntry > 0)
                || (node.InteractionKind == "transport" && node.TransportEntry > 0)
                || (node.InteractionKind == "jump_pad" && (node.JumpPadEntry > 0 || node.TransferAreaTriggerId > 0));
            bool const knownMovement = node.MovementLink == "none" || node.MovementLink == "encounter_link"
                || node.MovementLink == "cross_platform" || node.MovementLink == "regroup";
            bool const knownPlatform = node.PlatformPolicy == "ground" || node.PlatformPolicy == "platform"
                || node.PlatformPolicy == "altitude" || node.PlatformPolicy == "flying";
            bool const platformResolved = node.PlatformPolicy == "ground"
                || node.PlatformDestinationMapId > 0 || node.PlatformDestinationAreaId > 0
                || node.PlatformMaximumZ > node.PlatformMinimumZ;
            bool const jumpTransferResolved = node.InteractionKind != "jump_pad"
                || (node.MovementLink != "none" && node.MovementLink != "regroup"
                    && node.PlatformPolicy != "ground"
                    && (node.PlatformDestinationMapId > 0 || node.PlatformDestinationAreaId > 0
                        || node.PlatformMaximumZ > node.PlatformMinimumZ));
            node.MechanicContractResolved = !node.MechanicContractId.empty()
                && node.MechanicContractError.empty() && knownFormation && knownAnchor && knownScope
                && knownOrientation && formationResolved && targetResolved && tankSwapResolved
                && interruptResolved && dispelResolved && cooldownResolved && soakResolved
                && knownHealerOwnership && knownBattleRes && battleResResolved
                && knownInteraction && interactionResolved
                && knownMovement && knownPlatform && platformResolved && jumpTransferResolved;
            if (!node.MechanicContractResolved && node.MechanicContractError.empty())
                node.MechanicContractError = "unsupported_or_incomplete_contract";
        }
        std::string const nativeInteractionContract =
            ExtractJsonObjectField(routeJson, "interaction_contract");
        if (!nativeInteractionContract.empty())
        {
            static std::set<std::string> const AllowedInteractionFields =
                { "action", "entry", "menu", "menus", "option" };
            for (std::string const& key : ExtractJsonTopLevelKeys(nativeInteractionContract))
                if (AllowedInteractionFields.find(key) == AllowedInteractionFields.end())
                {
                    Party().ValidationRouteManifestLoadError =
                        "native_interaction_unknown_field:" + key;
                    return;
                }
            node.NativeInteractionAction =
                ExtractJsonStringField(nativeInteractionContract, "action");
            node.NativeInteractionEntry = uint32(std::max(
                0, readInt(nativeInteractionContract, "entry")));
            node.NativeInteractionMenus =
                ExtractJsonUIntArrayField(nativeInteractionContract, "menus");
            uint32 const singleMenu = uint32(std::max(
                0, readInt(nativeInteractionContract, "menu")));
            if (singleMenu)
                node.NativeInteractionMenus.push_back(singleMenu);
            node.NativeInteractionOption = uint32(std::max(
                0, readInt(nativeInteractionContract, "option")));

            bool const interactionShapeValid =
                (node.NativeInteractionAction == "gameobject_use"
                    && node.NativeInteractionEntry > 0
                    && node.NativeInteractionMenus.empty())
                || ((node.NativeInteractionAction == "gossip_select"
                        || node.NativeInteractionAction == "gossip_select_sequence")
                    && node.NativeInteractionEntry > 0
                    && !node.NativeInteractionMenus.empty());
            if (!interactionShapeValid)
            {
                Party().ValidationRouteManifestLoadError =
                    "native_interaction_contract_invalid";
                return;
            }
        }

        std::string const nativeCompletionContract =
            ExtractJsonObjectField(routeJson, "completion_contract");
        if (!nativeCompletionContract.empty())
        {
            static std::set<std::string> const AllowedCompletionFields =
                { "kind", "entry", "spell_id" };
            for (std::string const& key : ExtractJsonTopLevelKeys(nativeCompletionContract))
                if (AllowedCompletionFields.find(key) == AllowedCompletionFields.end())
                {
                    Party().ValidationRouteManifestLoadError =
                        "native_completion_unknown_field:" + key;
                    return;
                }
            node.NativeCompletionKind =
                ExtractJsonStringField(nativeCompletionContract, "kind");
            node.NativeCompletionEntry = uint32(std::max(
                0, readInt(nativeCompletionContract, "entry")));
            node.NativeCompletionSpellId = uint32(std::max(
                0, readInt(nativeCompletionContract, "spell_id")));

            bool const completionShapeValid =
                ((node.NativeCompletionKind == "gameobject_selectable"
                    || node.NativeCompletionKind == "boss_summoned"
                    || node.NativeCompletionKind == "creature_summoned"
                    || node.NativeCompletionKind == "creature_aggressive_with_victim"
                    || node.NativeCompletionKind == "creature_grounded_aggressive_or_engaged"
                    || node.NativeCompletionKind == "intro_complete_and_elevator_ready")
                    && node.NativeCompletionEntry > 0)
                || (node.NativeCompletionKind == "aura_present"
                    && node.NativeCompletionEntry > 0
                    && node.NativeCompletionSpellId > 0)
                || node.NativeCompletionKind == "player_in_nefarian_arena";
            if (!completionShapeValid)
            {
                Party().ValidationRouteManifestLoadError =
                    "native_completion_contract_invalid";
                return;
            }
        }
        node.MapId = uint32(std::max(0, readInt(routeJson, "map_id")));
        node.RecoveryEntranceAreaTriggerId = uint32(std::max(0,
            readInt(routeJson, "recovery_entrance_area_trigger_id")));
        node.RecoveryEntranceSourceMapId = uint32(std::max(0,
            readInt(routeJson, "recovery_entrance_source_map_id")));
        node.RecoveryEntranceTargetMapId = uint32(std::max(0,
            readInt(routeJson, "recovery_entrance_target_map_id")));
        node.X = readFloat(routeJson, "x");
        node.Y = readFloat(routeJson, "y");
        node.Z = readFloat(routeJson, "z");
        node.O = readFloat(routeJson, "o");
        node.NavigationAnchorX = node.X;
        node.NavigationAnchorY = node.Y;
        node.NavigationAnchorZ = node.Z;
        node.NavigationAnchorO = node.O;
        ExtractJsonNumberField(routeJson, "navigation_anchor_x", node.NavigationAnchorX);
        ExtractJsonNumberField(routeJson, "navigation_anchor_y", node.NavigationAnchorY);
        ExtractJsonNumberField(routeJson, "navigation_anchor_z", node.NavigationAnchorZ);
        ExtractJsonNumberField(routeJson, "navigation_anchor_o", node.NavigationAnchorO);
        node.BotStartMapId = uint32(std::max(0, readInt(routeJson, "bot_start_map_id")));
        node.BotStartX = readFloat(routeJson, "bot_start_x");
        node.BotStartY = readFloat(routeJson, "bot_start_y");
        node.BotStartZ = readFloat(routeJson, "bot_start_z");
        node.BotStartO = readFloat(routeJson, "bot_start_o");
        node.TargetEntry = uint32(std::max(0, readInt(routeJson, "source_entry")));
        std::string targetSpawnIdText = ExtractJsonStringField(routeJson, "source_guid");
        if (!targetSpawnIdText.empty())
            node.TargetSpawnId = ObjectGuid::LowType(strtoull(targetSpawnIdText.c_str(), nullptr, 10));
        else
            node.TargetSpawnId = ObjectGuid::LowType(std::max(0, readInt(routeJson, "source_guid")));
        node.OpenerTargetEntry = uint32(std::max(0, readInt(routeJson, "opener_target_entry")));
        node.AlternateTargetEntries = ExtractJsonUIntArrayField(routeJson, "alternate_target_entries");
        node.AddTargetEntries = ExtractJsonUIntArrayField(routeJson, "add_target_entries");
        node.PackTargetEntries = ExtractJsonUIntArrayField(routeJson, "pack_target_entries");
        node.ScriptedEventEntries = ExtractJsonUIntArrayField(routeJson, "scripted_event_entries");
        node.ScriptedEventTransitionAuraIds = ExtractJsonUIntArrayField(routeJson, "scripted_event_transition_aura_ids");
        ExtractJsonBoolField(routeJson, "scripted_event_require_passive", node.ScriptedEventRequirePassive);
        node.HazardSourceEntry = uint32(std::max(0, readInt(routeJson, "hazard_source_entry")));
        node.HazardDetectionSpellId = uint32(std::max(0, readInt(routeJson, "hazard_detection_spell_id")));
        node.HazardDamageSpellId = uint32(std::max(0, readInt(routeJson, "hazard_damage_spell_id")));
        node.HazardShape = ExtractJsonStringField(routeJson, "hazard_shape");
        node.HazardRadiusYards = readFloat(routeJson, "hazard_radius_yards");
        node.HazardSafetyMarginYards = readFloat(routeJson, "hazard_safety_margin_yards");
        node.MinimumDistanceSourceEntry = uint32(std::max(0, readInt(routeJson, "minimum_distance_source_entry")));
        node.MinimumDistanceYards = readFloat(routeJson, "minimum_distance_yards");
        node.SplitSourceGuids = ExtractJsonUIntArrayField(routeJson, "split_source_guids");
        node.SplitLaneARosterSlots = ExtractJsonUIntArrayField(routeJson, "split_lane_a_roster_slots");
        node.SplitLaneBRosterSlots = ExtractJsonUIntArrayField(routeJson, "split_lane_b_roster_slots");
        node.SplitLaneTankSlots = ExtractJsonUIntArrayField(routeJson, "split_lane_tank_slots");
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_member_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitMemberAnchors.push_back(anchor);
        }
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_recovery_member_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitRecoveryMemberAnchors.push_back(anchor);
        }
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_tank_combat_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitTankCombatAnchors.push_back(anchor);
        }
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_tank_navigation_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitTankNavigationAnchors.push_back(anchor);
        }
        for (std::string const& anchorJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "split_tank_recovery_anchors")))
        {
            ValidationRouteMemberAnchor anchor;
            anchor.RosterSlot = uint32(std::max(0, readInt(anchorJson, "roster_slot")));
            anchor.X = readFloat(anchorJson, "x");
            anchor.Y = readFloat(anchorJson, "y");
            anchor.Z = readFloat(anchorJson, "z");
            node.SplitTankRecoveryAnchors.push_back(anchor);
        }
        node.SplitMinimumSeparationYards = readFloat(routeJson, "split_minimum_separation_yards");
        node.SplitNavigationMarginYards = readFloat(routeJson, "split_navigation_margin_yards");
        node.SplitArrivalToleranceYards = readFloat(routeJson, "split_arrival_tolerance_yards");
        node.SplitTankArrivalToleranceYards = readFloat(routeJson, "split_tank_arrival_tolerance_yards");
        node.SplitNativeMeleeStopYards = readFloat(routeJson, "split_native_melee_stop_yards");
        if (!ExtractJsonStrictUIntArrayField(
            routeJson, "split_healer_roster_slots", node.SplitHealerRosterSlots))
            node.SplitHealerRosterSlots.clear();
        if (!ExtractJsonStrictUIntArrayField(
            routeJson, "split_seed_roster_slots", node.SplitSeedRosterSlots))
            node.SplitSeedRosterSlots.clear();
        node.SplitSeedMaxRangeYards = readFloat(routeJson, "split_seed_max_range_yards");
        node.SplitTankThreatHeadroomMultiplier = readFloat(
            routeJson, "split_tank_threat_headroom_multiplier");
        node.ThunderclapSpellId = uint32(std::max(0, readInt(routeJson, "thunderclap_spell_id")));
        node.ChargeSpellId = uint32(std::max(0, readInt(routeJson, "charge_spell_id")));
        node.ChargeRangeYards = readFloat(routeJson, "charge_range_yards");
        node.ChargeNativeIntervalMs = uint32(std::max(0, readInt(routeJson, "charge_native_interval_ms")));
        node.VengefulRageSpellId = uint32(std::max(0, readInt(routeJson, "vengeful_rage_spell_id")));
        node.ClusterRadiusYards = readFloat(routeJson, "cluster_radius_yards");
        node.PatrolPullPolicy = ExtractJsonStringField(routeJson, "patrol_pull_policy");
        node.PatrolWaitX = readFloat(routeJson, "patrol_wait_x");
        node.PatrolWaitY = readFloat(routeJson, "patrol_wait_y");
        node.PatrolWaitZ = readFloat(routeJson, "patrol_wait_z");
        node.PatrolWaitToleranceYards = readFloat(routeJson, "patrol_wait_tolerance_yards");
        node.PatrolAnchorToleranceYards = readFloat(routeJson, "patrol_anchor_tolerance_yards");
        node.PatrolEngageRadiusYards = readFloat(routeJson, "patrol_engage_radius_yards");
        node.PatrolFutureGuardMarginYards = readFloat(routeJson, "patrol_future_guard_margin_yards");
        node.PatrolPullOwnerRosterSlot = uint32(std::max(0, readInt(routeJson, "patrol_pull_owner_roster_slot")));
        node.ExpectedAliveCount = uint32(std::max(0, readInt(routeJson, "expected_alive_count")));
        node.ActivationAreaTriggerId = uint32(std::max(0, readInt(routeJson, "activation_area_trigger_id")));
        node.ActivationDataId = uint32(std::max(0, readInt(routeJson, "activation_data_id")));
        node.ActivationDataValue = uint32(std::max(0, readInt(routeJson, "activation_data_value")));
        node.ActivationSpawnGroupId = uint32(std::max(0, readInt(routeJson, "activation_spawn_group_id")));
        node.ActivationActionEntry = uint32(std::max(0, readInt(routeJson, "activation_action_entry")));
        node.ActivationActionId = readInt(routeJson, "activation_action_id");
        node.ActivationSummonEntry = uint32(std::max(0, readInt(routeJson, "activation_summon_entry")));
        node.ActivationSummonX = readFloat(routeJson, "activation_summon_x");
        node.ActivationSummonY = readFloat(routeJson, "activation_summon_y");
        node.ActivationSummonZ = readFloat(routeJson, "activation_summon_z");
        node.ActivationSummonO = readFloat(routeJson, "activation_summon_o");
        node.OpenerSummonEntry = uint32(std::max(0, readInt(routeJson, "opener_summon_entry")));
        node.OpenerSummonX = readFloat(routeJson, "opener_summon_x");
        node.OpenerSummonY = readFloat(routeJson, "opener_summon_y");
        node.OpenerSummonZ = readFloat(routeJson, "opener_summon_z");
        node.OpenerSummonO = readFloat(routeJson, "opener_summon_o");
        node.ExpectedBotCount = uint32(std::max(0, readInt(routeJson, "expected_bot_count")));
        for (std::string const& identityJson : ExtractJsonObjectArrayItems(
            ExtractJsonArrayField(routeJson, "roster_identity")))
        {
            ValidationRouteManifestNode::RosterIdentity identity;
            identity.RosterSlotId = ExtractJsonStringField(identityJson, "roster_slot_id");
            identity.Guid = uint32(std::max(0, readInt(identityJson, "guid")));
            identity.Name = ExtractJsonStringField(identityJson, "name");
            identity.Role = ExtractJsonStringField(identityJson, "role");
            identity.ClassSpec = ExtractJsonStringField(identityJson, "class_spec");
            node.ExpectedRoster.push_back(std::move(identity));
        }
        if (!node.NodeId.empty() && !node.Kind.empty())
            Party().ValidationRouteManifest.push_back(node);
    }

    if (Party().ValidationRouteManifest.empty())
    {
        Party().ValidationRouteManifestLoadError = "manifest_routes_empty";
        return;
    }

    ApplyValidationRouteManifestNode(0, "manifest_load");
}
