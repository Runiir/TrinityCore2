#ifndef TRINITY_BOT_RAID_DUTY_CLAIMS_H
#define TRINITY_BOT_RAID_DUTY_CLAIMS_H

#include "ObjectGuid.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <map>
#include <string>
#include <string_view>
#include <vector>

// Human duty callouts for play cohorts (docs/bot_raids/human_play_mode.md).
// A human says "I do chains" in raid chat; the claimed duty is then external
// owned and bots never perform it until someone says "bots do chains".
// Without a claim, bots own every duty exactly as in validation.
namespace BotRaidDuty
{
// Keywords are lower-case single words or two-word phrases.
struct DutyKeywords
{
    std::string_view Duty;
    std::vector<std::string_view> Keywords;
};

inline constexpr std::string_view Bloodlust = "bloodlust";
inline constexpr std::string_view BattleRes = "battle_res";

// Raid-wide duties shared by every encounter.
inline std::vector<DutyKeywords> const& SharedDutyKeywords()
{
    static std::vector<DutyKeywords> const table{
        { Bloodlust, { "lust", "bloodlust", "bl", "hero", "heroism",
            "timewarp", "time warp" } },
        { BattleRes, { "brez", "bres", "brezz", "rebirth", "battle res",
            "battle rez", "combat res", "combat rez" } },
    };
    return table;
}

enum class CalloutIntent : uint8
{
    Claim,
    Release
};

struct Callout
{
    std::string Duty;
    CalloutIntent Intent = CalloutIntent::Claim;
};

// Lower-case words; apostrophes are dropped ("I'll" -> "ill") and any other
// non-alphanumeric character separates words.
inline std::vector<std::string> NormalizeWords(std::string_view text)
{
    std::vector<std::string> words;
    std::string word;
    for (std::size_t index = 0; index < text.size(); ++index)
    {
        unsigned char const c = static_cast<unsigned char>(text[index]);
        if (c == '\'')
            continue;
        // UTF-8 right single quotation mark (U+2019).
        if (c == 0xE2 && index + 2 < text.size()
            && static_cast<unsigned char>(text[index + 1]) == 0x80
            && static_cast<unsigned char>(text[index + 2]) == 0x99)
        {
            index += 2;
            continue;
        }
        if (std::isalnum(c))
            word.push_back(char(std::tolower(c)));
        else if (!word.empty())
        {
            words.push_back(word);
            word.clear();
        }
    }
    if (!word.empty())
        words.push_back(word);
    return words;
}

namespace Detail
{
inline bool IsOneOf(std::string const& word,
    std::initializer_list<std::string_view> values)
{
    return std::find(values.begin(), values.end(), word) != values.end();
}

inline bool IsFirstPerson(std::string const& word)
{
    return IsOneOf(word, { "i", "ill", "im", "ive", "id", "me" });
}

inline bool IsBotWord(std::string const& word)
{
    return IsOneOf(word, { "bot", "bots" });
}

inline bool IsNegation(std::string const& word)
{
    return IsOneOf(word, { "not", "no", "dont", "cant", "wont", "never",
        "cannot", "isnt", "stop" });
}

inline bool IsReleaseVerb(std::string const& word)
{
    return IsOneOf(word, { "release", "unclaim", "drop" });
}

// A request or question for the duty, never a claim of it.
inline bool IsRequest(std::string const& word)
{
    return IsOneOf(word, { "need", "needs", "want", "who", "someone",
        "anyone", "somebody", "anybody", "please", "pls", "plz" });
}

struct Mention
{
    std::size_t Index;
    std::size_t Length;
    std::string_view Duty;
};

inline std::vector<Mention> FindMentions(std::vector<std::string> const& words,
    std::vector<DutyKeywords> const& table)
{
    std::vector<Mention> mentions;
    for (std::size_t index = 0; index < words.size(); ++index)
    {
        for (DutyKeywords const& duty : table)
        {
            std::size_t length = 0;
            for (std::string_view keyword : duty.Keywords)
            {
                std::size_t const space = keyword.find(' ');
                if (space == std::string_view::npos && words[index] == keyword)
                    length = 1;
                else if (space != std::string_view::npos
                    && index + 1 < words.size()
                    && words[index] == keyword.substr(0, space)
                    && words[index + 1] == keyword.substr(space + 1))
                    length = 2;
                if (length)
                    break;
            }
            if (length)
            {
                mentions.push_back({ index, length, duty.Duty });
                index += length - 1;
                break;
            }
        }
    }
    return mentions;
}
}

// Returns one callout per distinct duty named in the message, all with the
// message's single intent, or nothing when the message is not a callout.
// Claims need a first-person speaker ("I do chains", "chains on me");
// releases hand the duty back to bots ("bots do chains", "I can't do
// chains", "release chains"). Questions and requests never claim.
inline std::vector<Callout> ParseCallouts(std::string_view text,
    std::vector<DutyKeywords> const& table)
{
    std::vector<std::string> const words = NormalizeWords(text);
    std::vector<Detail::Mention> const mentions =
        Detail::FindMentions(words, table);
    if (mentions.empty() || text.find('?') != std::string_view::npos)
        return {};
    if (std::any_of(words.begin(), words.end(), Detail::IsRequest))
        return {};

    // The subject nearest the first duty word decides: "no bots, I do
    // chains" claims, "I'll let bots do chains" releases.
    std::size_t const first = mentions.front().Index;
    bool const releaseVerb = std::any_of(words.begin(),
        words.begin() + first, Detail::IsReleaseVerb);
    bool bots = false;
    bool firstPerson = false;
    bool negated = false;
    bool negationSeen = false;
    for (std::size_t index = first; index-- > 0;)
    {
        if (Detail::IsBotWord(words[index]))
        {
            bots = true;
            break;
        }
        if (Detail::IsFirstPerson(words[index]))
        {
            firstPerson = true;
            negated = negationSeen;
            break;
        }
        negationSeen = negationSeen || Detail::IsNegation(words[index]);
    }
    // "chains on me", "chains mine", "chains me".
    std::size_t const after = mentions.back().Index + mentions.back().Length;
    bool const suffixClaim = (after < words.size()
            && (words[after] == "mine" || words[after] == "me"))
        || (after + 1 < words.size() && words[after] == "on"
            && words[after + 1] == "me");

    CalloutIntent intent;
    if (bots || releaseVerb || (firstPerson && negated))
        intent = CalloutIntent::Release;
    else if (firstPerson || suffixClaim)
        intent = CalloutIntent::Claim;
    else
        return {};

    std::vector<Callout> callouts;
    for (Detail::Mention const& mention : mentions)
        if (std::none_of(callouts.begin(), callouts.end(),
                [&mention](Callout const& callout)
                {
                    return callout.Duty == mention.Duty;
                }))
            callouts.push_back({ std::string(mention.Duty), intent });
    return callouts;
}

// External owners of claimed duties. Empty for validation cohorts.
class Claims
{
public:
    struct Entry
    {
        ObjectGuid Owner;
        uint64 ClaimedAtMs = 0;
    };

    void Claim(std::string const& duty, ObjectGuid owner, uint64 atMs)
    {
        _entries[duty] = { owner, atMs };
    }

    bool Release(std::string const& duty)
    {
        return _entries.erase(duty) > 0;
    }

    // Returns true when the claim set changed.
    bool Apply(Callout const& callout, ObjectGuid speaker, uint64 atMs)
    {
        if (callout.Intent == CalloutIntent::Release)
            return Release(callout.Duty);
        auto existing = _entries.find(callout.Duty);
        if (existing != _entries.end() && existing->second.Owner == speaker)
            return false;
        Claim(callout.Duty, speaker, atMs);
        return true;
    }

    bool IsClaimed(std::string_view duty) const
    {
        return _entries.find(std::string(duty)) != _entries.end();
    }

    ObjectGuid Owner(std::string_view duty) const
    {
        auto entry = _entries.find(std::string(duty));
        return entry == _entries.end() ? ObjectGuid() : entry->second.Owner;
    }

    // A member who leaves the raid gives up every duty it claimed.
    std::size_t ReleaseAllOwnedBy(ObjectGuid owner)
    {
        std::size_t released = 0;
        for (auto entry = _entries.begin(); entry != _entries.end();)
        {
            if (entry->second.Owner == owner)
            {
                entry = _entries.erase(entry);
                ++released;
            }
            else
                ++entry;
        }
        return released;
    }

    bool Empty() const { return _entries.empty(); }
    std::map<std::string, Entry> const& Entries() const { return _entries; }

private:
    std::map<std::string, Entry> _entries;
};
}

#endif
