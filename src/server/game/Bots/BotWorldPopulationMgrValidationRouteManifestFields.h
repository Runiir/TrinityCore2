#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_MANIFEST_FIELDS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_MANIFEST_FIELDS_H

// Legacy regex/brace field readers used by the validation route manifest
// loader. Kept byte-for-byte equivalent to the historical in-file helpers so
// accepted route rows parse exactly as before; native route contracts use the
// structural reader in BotValidationRouteNativeJson.h instead.

#include "Define.h"

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

namespace BotValidationRouteManifestFields
{
inline std::string ReadSmallTextFile(std::string const& path, size_t maxBytes = 4 * 1024 * 1024)
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

inline std::string ExtractJsonStringField(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (std::regex_search(json, match, pattern) && match.size() > 1)
        return match[1].str();
    return "";
}


inline std::string ExtractJsonObjectField(std::string const& json, std::string const& key)
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


inline std::string ExtractJsonArrayField(std::string const& json, std::string const& key)
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


inline std::vector<std::string> ExtractJsonObjectArrayItems(std::string const& arrayJson)
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


inline std::set<std::string> ExtractJsonTopLevelKeys(std::string const& objectJson)
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


inline bool ExtractJsonNumberField(std::string const& json, std::string const& key, float& value)
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


inline bool ExtractJsonIntField(std::string const& json, std::string const& key, int& value)
{
    float number = 0.0f;
    if (!ExtractJsonNumberField(json, key, number))
        return false;
    value = int(number);
    return true;
}


inline std::vector<uint32> ParseUIntList(std::string const& text)
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


inline std::vector<uint32> ExtractJsonUIntArrayField(std::string const& json, std::string const& key)
{
    return ParseUIntList(ExtractJsonArrayField(json, key));
}


inline bool ExtractJsonStrictUIntArrayField(std::string const& json, std::string const& key,
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

inline bool JsonHasField(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:");
    return std::regex_search(json, pattern);
}


inline bool ExtractJsonBoolField(std::string const& json, std::string const& key, bool& value)
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

inline bool JsonFieldIsString(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*\"");
    return std::regex_search(json, pattern);
}

inline bool JsonFieldIsNumber(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?");
    return std::regex_search(json, pattern);
}

inline bool JsonFieldIsBool(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*(true|false)");
    return std::regex_search(json, pattern);
}


inline std::vector<std::string> ExtractJsonLineObjects(std::string const& text)
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

#endif
