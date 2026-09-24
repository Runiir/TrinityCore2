#ifndef TRINITY_BOT_PLAY_PULL_TIMER_H
#define TRINITY_BOT_PLAY_PULL_TIMER_H

#include "Bots/BotRaidDutyClaims.h"

#include <algorithm>
#include <cctype>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

// Pull timers a human raid leader starts in a play raid
// (docs/bot_raids/human_play_mode.md). Bots engage the boss when the timer
// reaches zero or when anyone pulls, whichever comes first.
namespace BotPlayPullTimer
{
inline constexpr uint32 MaxSeconds = 60;

struct Signal
{
    bool Cancel = false;
    uint32 Seconds = 0;
};

namespace Detail
{
inline std::vector<std::string> Split(std::string_view text, bool (*separator)(char))
{
    std::vector<std::string> tokens;
    std::string token;
    for (char c : text)
    {
        if (separator(c))
        {
            if (!token.empty())
                tokens.push_back(token);
            token.clear();
        }
        else
            token.push_back(c);
    }
    if (!token.empty())
        tokens.push_back(token);
    return tokens;
}

inline std::optional<uint32> Number(std::string const& token)
{
    if (token.empty() || token.size() > 4)
        return std::nullopt;
    uint32 value = 0;
    for (char c : token)
    {
        if (!std::isdigit(static_cast<unsigned char>(c)))
            return std::nullopt;
        value = value * 10 + uint32(c - '0');
    }
    return value;
}

inline std::optional<Signal> FromSeconds(uint32 seconds)
{
    Signal signal;
    // Both addons cancel a running pull timer with a zero-second timer.
    signal.Cancel = seconds == 0;
    signal.Seconds = std::min(seconds, MaxSeconds);
    return signal;
}
}

// DBM-Core addon sync. 4.3.4-era DBM sends prefix "D4" with
// "PT\t<seconds>[\t...]"; later DBM uses "D5" with sender and protocol
// fields before the same "PT\t<seconds>" pair. `/dbm pull 0` cancels.
inline std::optional<Signal> ParseDbm(std::string_view prefix, std::string_view message)
{
    if (prefix != "D4" && prefix != "D5")
        return std::nullopt;
    std::vector<std::string> const fields = Detail::Split(message,
        [](char c) { return c == '\t'; });
    for (size_t index = 0; index + 1 < fields.size(); ++index)
        if (fields[index] == "PT")
            if (std::optional<uint32> const seconds = Detail::Number(fields[index + 1]))
                return Detail::FromSeconds(*seconds);
    return std::nullopt;
}

// BigWigs pull sync ("T:BWPull 10" in old versions, "P^Pull^10" later).
inline std::optional<Signal> ParseBigWigs(std::string_view prefix, std::string_view message)
{
    if (prefix != "BigWigs")
        return std::nullopt;
    std::vector<std::string> const tokens = Detail::Split(message,
        [](char c) { return !std::isalnum(static_cast<unsigned char>(c)); });
    for (size_t index = 0; index + 1 < tokens.size(); ++index)
        if (tokens[index] == "Pull" || tokens[index] == "BWPull")
            if (std::optional<uint32> const seconds = Detail::Number(tokens[index + 1]))
                return Detail::FromSeconds(*seconds);
    return std::nullopt;
}

inline std::optional<Signal> ParseAddon(std::string_view prefix, std::string_view message)
{
    if (std::optional<Signal> const dbm = ParseDbm(prefix, message))
        return dbm;
    return ParseBigWigs(prefix, message);
}

// Raid chat or raid warning from the leader: "pull 10", "pull in 10",
// "pulling in 5 sec", "pull now", "cancel pull" / "pull cancelled".
inline std::optional<Signal> ParseChat(std::string_view text)
{
    std::vector<std::string> const words = BotRaidDuty::NormalizeWords(text);
    for (size_t index = 0; index < words.size(); ++index)
    {
        if (words[index] != "pull" && words[index] != "pulling")
            continue;
        bool const cancelBefore = index > 0
            && (words[index - 1] == "cancel" || words[index - 1] == "stop"
                || words[index - 1] == "no");
        bool const cancelAfter = index + 1 < words.size()
            && (words[index + 1] == "cancelled" || words[index + 1] == "canceled"
                || words[index + 1] == "cancel");
        if (cancelBefore || cancelAfter)
        {
            Signal signal;
            signal.Cancel = true;
            return signal;
        }
        size_t next = index + 1;
        if (next < words.size() && words[next] == "in")
            ++next;
        if (next < words.size())
        {
            if (words[next] == "now")
                return Signal{};
            if (std::optional<uint32> const seconds = Detail::Number(words[next]))
            {
                Signal signal;
                signal.Seconds = std::min(*seconds, MaxSeconds);
                return signal;
            }
        }
    }
    return std::nullopt;
}
}

#endif
