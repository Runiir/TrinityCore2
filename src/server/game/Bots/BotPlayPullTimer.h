#ifndef TRINITY_BOT_PLAY_PULL_TIMER_H
#define TRINITY_BOT_PLAY_PULL_TIMER_H

#include "Bots/BotPlaySession.h"
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
inline constexpr uint32 MaxSeconds = 300;
// After zero the pull stays open this long for the bots to engage; a timer
// never lingers into a later pull (review of 1f4405f1dc).
inline constexpr uint64 ReleaseWindowMs = 30000;

// Counting down: bots move to the boss and stage.
inline bool Running(uint64 pullAtMs, uint64 nowMs)
{
    return pullAtMs && nowMs < pullAtMs;
}

// Zero reached and the release window still open: the pull tank engages.
inline bool Released(uint64 pullAtMs, uint64 nowMs)
{
    return pullAtMs && nowMs >= pullAtMs && nowMs < pullAtMs + ReleaseWindowMs;
}

// Boss fight edges for the status the leader reads. The fight spends the
// timer that led to it, so an engaged or finished fight never reads as an
// expired pull window. It ends as a kill when more bosses are DONE than at
// the pull, else as a reset that needs a new timer. "" means no edge.
inline std::string ObserveEncounter(BotPlaySession& session, bool inProgress,
    uint32 bossesDone, uint64 nowMs)
{
    if (inProgress == session.BossEngaged)
        return {};
    session.BossEngaged = inProgress;
    if (!inProgress)
        return bossesDone > session.BossesDoneAtEngage
            ? "boss_killed" : "boss_reset:start_a_new_pull_timer";
    session.BossesDoneAtEngage = bossesDone;
    char const* how = Released(session.PullAtMs, nowMs) ? "pull_timer"
        : Running(session.PullAtMs, nowMs) ? "before_timer" : "without_timer";
    session.PullAtMs = 0;
    return std::string("boss_engaged:") + how;
}

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
    // A timer longer than bots can honour is ignored rather than shortened.
    if (seconds > MaxSeconds)
        return std::nullopt;
    Signal signal;
    // Both addons cancel a running pull timer with a zero-second timer.
    signal.Cancel = seconds == 0;
    signal.Seconds = seconds;
    return signal;
}
}

// DBM-Core addon sync under prefix "D4" (later "D5" with sender and
// protocol fields first). Cataclysm-era `/dbm pull N` sends a pizza timer
// "U\t<seconds>\tPull in" plus a raid warning "Pull in N sec" (ParseChat);
// Mists-era DBM added "PT\t<seconds>". `/dbm pull 0` cancels.
inline std::optional<Signal> ParseDbm(std::string_view prefix, std::string_view message)
{
    if (prefix != "D4" && prefix != "D5")
        return std::nullopt;
    std::vector<std::string> const fields = Detail::Split(message,
        [](char c) { return c == '\t'; });
    for (size_t index = 0; index + 1 < fields.size(); ++index)
    {
        bool const pullTimer = fields[index] == "PT";
        bool const pizzaPull = fields[index] == "U" && index + 2 < fields.size()
            && fields[index + 2].rfind("Pull", 0) == 0;
        if (pullTimer || pizzaPull)
            if (std::optional<uint32> const seconds = Detail::Number(fields[index + 1]))
                return Detail::FromSeconds(*seconds);
    }
    return std::nullopt;
}

// BigWigs pull sync ("T:BWPull 10" in old versions, "P^Pull^10" later).
// Custom bars that merely mention "Pull" are not pull timers.
inline std::optional<Signal> ParseBigWigs(std::string_view prefix, std::string_view message)
{
    if (prefix != "BigWigs")
        return std::nullopt;
    std::vector<std::string> const tokens = Detail::Split(message,
        [](char c) { return !std::isalnum(static_cast<unsigned char>(c)); });
    for (size_t index = 0; index + 1 < tokens.size(); ++index)
    {
        bool const oldSync = tokens[index] == "BWPull";
        bool const newSync = index == 1 && tokens[0] == "P" && tokens[index] == "Pull";
        if (oldSync || newSync)
            if (std::optional<uint32> const seconds = Detail::Number(tokens[index + 1]))
                return Detail::FromSeconds(*seconds);
    }
    return std::nullopt;
}

inline std::optional<Signal> ParseAddon(std::string_view prefix, std::string_view message)
{
    if (std::optional<Signal> const dbm = ParseDbm(prefix, message))
        return dbm;
    return ParseBigWigs(prefix, message);
}

// Raid chat or raid warning from the leader: "pull 10", "pull in 10",
// "Pull in 10 sec" (DBM's raid warning), "pull now", "cancel pull".
// A number counts only when it ends the call or is followed by seconds, so
// "pull 1 more pack" or "pull in 5 min" never start a timer.
inline std::optional<Signal> ParseChat(std::string_view text)
{
    // Questions never start or stop a pull ("can I pull now?").
    if (text.find('?') != std::string_view::npos)
        return std::nullopt;
    std::vector<std::string> const words = BotRaidDuty::NormalizeWords(text);
    if (words.size() > 8)
        return std::nullopt;
    auto isSecondsUnit = [](std::string const& word)
    {
        return word == "s" || word == "sec" || word == "secs" || word == "second"
            || word == "seconds";
    };
    for (size_t index = 0; index < words.size(); ++index)
    {
        if (words[index] != "pull" && words[index] != "pulling")
            continue;
        // "don't pull now", "do not pull in 10", "wait, hold the pull": the
        // leader is holding the raid, so a running timer is cancelled.
        auto holds = [](std::string const& word)
        {
            return word == "cancel" || word == "stop" || word == "no" || word == "dont"
                || word == "don" || word == "not" || word == "never" || word == "cant"
                || word == "wait" || word == "hold";
        };
        bool const cancelBefore = (index > 0 && holds(words[index - 1]))
            || (index > 1 && holds(words[index - 2]));
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
            // "pull now" only as the whole call (DBM's "Pull now!").
            if (words[next] == "now")
                return next + 1 == words.size() ? std::optional<Signal>(Signal{}) : std::nullopt;
            std::optional<uint32> const seconds = Detail::Number(words[next]);
            bool const endsCall = next + 1 == words.size()
                || isSecondsUnit(words[next + 1]);
            if (seconds && endsCall && *seconds <= MaxSeconds)
            {
                Signal signal;
                signal.Seconds = *seconds;
                return signal;
            }
        }
    }
    return std::nullopt;
}
}

#endif
