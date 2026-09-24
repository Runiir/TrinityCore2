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
// Keywords are lower-case single words or two-word phrases. A mention is
// ignored when the next word is in NotFollowedBy ("chain heal") or the
// previous word is in NotPrecededBy ("the hero").
struct DutyKeywords
{
    std::string_view Duty;
    std::vector<std::string_view> Keywords;
    std::vector<std::string_view> NotFollowedBy = {};
    std::vector<std::string_view> NotPrecededBy = {};
};

inline constexpr std::string_view Bloodlust = "bloodlust";
inline constexpr std::string_view BattleRes = "battle_res";

// Raid-wide duties shared by every encounter.
inline std::vector<DutyKeywords> const& SharedDutyKeywords()
{
    static std::vector<DutyKeywords> const table{
        { Bloodlust, { "lust", "bloodlust", "bl", "hero", "heroism",
            "timewarp", "time warp" }, {}, { "the", "a" } },
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
    // "I can't do chains" releases only the speaker's own claim; "bots do
    // chains" and "release chains" release anyone's.
    bool Personal = false;
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

// "me" is not a subject: "brez me" and "give me lust" are requests.
inline bool IsFirstPerson(std::string const& word)
{
    return IsOneOf(word, { "i", "ill", "im", "ive", "id" });
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
                std::size_t const next = index + length;
                bool const excluded = (next < words.size()
                        && std::find(duty.NotFollowedBy.begin(),
                            duty.NotFollowedBy.end(), words[next])
                            != duty.NotFollowedBy.end())
                    || (index > 0 && std::find(duty.NotPrecededBy.begin(),
                            duty.NotPrecededBy.end(), words[index - 1])
                            != duty.NotPrecededBy.end());
                if (!excluded)
                    mentions.push_back({ index, length, duty.Duty });
                index += length - 1;
                break;
            }
        }
    }
    return mentions;
}
}

// One clause: every duty it names gets the clause's single intent. Claims
// need a first-person speaker ("I do chains") or "on me"/"mine" after the
// duty; releases hand the duty back to bots ("bots do chains", "I can't do
// chains", "release chains"). Requests never claim.
inline std::vector<Callout> ParseClause(std::vector<std::string> const& words,
    std::vector<DutyKeywords> const& table)
{
    std::vector<Detail::Mention> const mentions =
        Detail::FindMentions(words, table);
    if (mentions.empty()
        || std::any_of(words.begin(), words.end(), Detail::IsRequest))
        return {};

    // The subject nearest the first duty word decides: "no bots I do
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
    std::size_t const after = mentions.back().Index + mentions.back().Length;
    bool const suffixClaim = (after < words.size() && words[after] == "mine")
        || (after + 1 < words.size() && words[after] == "on"
            && words[after + 1] == "me");

    Callout base;
    if (bots || releaseVerb)
        base.Intent = CalloutIntent::Release;
    else if (firstPerson && negated)
    {
        base.Intent = CalloutIntent::Release;
        base.Personal = true;
    }
    else if (firstPerson || suffixClaim)
        base.Intent = CalloutIntent::Claim;
    else
        return {};

    std::vector<Callout> callouts;
    for (Detail::Mention const& mention : mentions)
        if (std::none_of(callouts.begin(), callouts.end(),
                [&mention](Callout const& callout)
                {
                    return callout.Duty == mention.Duty;
                }))
        {
            Callout callout = base;
            callout.Duty = std::string(mention.Duty);
            callouts.push_back(callout);
        }
    return callouts;
}

// Splits a raid-chat message into clauses at , ; . ! and "but", so "bots
// do chains, I do bait" releases chains and claims bait. A later clause
// overrides an earlier one for the same duty. Questions never count.
inline std::vector<Callout> ParseCallouts(std::string_view text,
    std::vector<DutyKeywords> const& table)
{
    if (text.find('?') != std::string_view::npos)
        return {};
    std::vector<Callout> callouts;
    auto merge = [&callouts](std::vector<Callout> const& clause)
    {
        for (Callout const& callout : clause)
        {
            auto existing = std::find_if(callouts.begin(), callouts.end(),
                [&callout](Callout const& other)
                {
                    return other.Duty == callout.Duty;
                });
            if (existing == callouts.end())
                callouts.push_back(callout);
            else
                *existing = callout;
        }
    };
    std::size_t start = 0;
    while (start <= text.size())
    {
        std::size_t const stop = text.find_first_of(",;.!", start);
        std::string_view const segment = text.substr(start,
            stop == std::string_view::npos ? std::string_view::npos : stop - start);
        std::vector<std::string> clause;
        for (std::string const& word : NormalizeWords(segment))
        {
            if (word == "but")
            {
                merge(ParseClause(clause, table));
                clause.clear();
            }
            else
                clause.push_back(word);
        }
        merge(ParseClause(clause, table));
        if (stop == std::string_view::npos)
            break;
        start = stop + 1;
    }
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
        {
            if (callout.Personal && Owner(callout.Duty) != speaker)
                return false;
            return Release(callout.Duty);
        }
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
