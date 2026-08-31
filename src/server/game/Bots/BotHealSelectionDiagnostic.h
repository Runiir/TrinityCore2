#ifndef TRINITY_BOT_HEAL_SELECTION_DIAGNOSTIC_H
#define TRINITY_BOT_HEAL_SELECTION_DIAGNOSTIC_H

#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace BotHealSelection
{
constexpr std::size_t MaxReportedRejections = 16;

struct Rejection
{
    std::uint32_t SpellId = 0;
    std::string Reason;

    friend bool operator<(Rejection const& left, Rejection const& right)
    {
        return std::tie(left.SpellId, left.Reason)
            < std::tie(right.SpellId, right.Reason);
    }

    friend bool operator==(Rejection const& left, Rejection const& right)
    {
        return left.SpellId == right.SpellId && left.Reason == right.Reason;
    }
};

struct Diagnostic
{
    std::uint64_t ActorGuid = 0;
    std::uint64_t TargetGuid = 0;
    float TargetDistance = 0.0f;
    bool LineOfSight = false;
    bool InstantOnly = false;
    std::uint8_t ProfileClassId = 0;
    std::string ProfileSpecTag;
    std::string ProfileRole;
    std::string ProfileSource;
    std::uint64_t ProfileGeneration = 0;
    std::string ProfileContentHash;
    std::uint32_t SelectedSpellId = 0;
    std::size_t HealingCandidateCount = 0;
    std::size_t UniqueRejectionCount = 0;
    std::size_t UniqueReasonCount = 0;
    std::vector<Rejection> Rejections;

    void SetRejections(std::vector<Rejection> rejections)
    {
        rejections.erase(std::remove_if(rejections.begin(), rejections.end(),
            [](Rejection const& rejection)
            {
                return !rejection.SpellId || rejection.Reason.empty();
            }), rejections.end());
        std::sort(rejections.begin(), rejections.end());
        rejections.erase(std::unique(rejections.begin(), rejections.end()),
            rejections.end());
        UniqueRejectionCount = rejections.size();
        std::vector<std::string> reasons;
        reasons.reserve(rejections.size());
        for (Rejection const& rejection : rejections)
            reasons.push_back(rejection.Reason);
        std::sort(reasons.begin(), reasons.end());
        reasons.erase(std::unique(reasons.begin(), reasons.end()), reasons.end());
        UniqueReasonCount = reasons.size();
        if (rejections.size() > MaxReportedRejections)
            rejections.resize(MaxReportedRejections);
        Rejections = std::move(rejections);
    }

    std::string SummaryReason() const
    {
        if (SelectedSpellId)
            return "selected";
        if (!HealingCandidateCount)
            return "no_healing_profile_actions";
        if (Rejections.empty())
            return "selection_failed_without_rejection";
        return UniqueReasonCount == 1
            ? Rejections.front().Reason : "multiple_candidate_rejections";
    }

    std::string ToJson() const
    {
        std::ostringstream json;
        json << std::fixed << std::setprecision(3)
             << "{\"schema\":\"bot_heal_selection_diagnostic_v1\""
             << ",\"actor_guid\":" << ActorGuid
             << ",\"target_guid\":" << TargetGuid
             << ",\"target_distance\":" << TargetDistance
             << ",\"line_of_sight\":" << (LineOfSight ? "true" : "false")
             << ",\"instant_only\":" << (InstantOnly ? "true" : "false")
             << ",\"profile\":{\"class_id\":" << std::uint32_t(ProfileClassId)
             << ",\"spec_tag\":\"" << Escape(ProfileSpecTag) << "\""
             << ",\"role\":\"" << Escape(ProfileRole) << "\""
             << ",\"source\":\"" << Escape(ProfileSource) << "\""
             << ",\"generation\":" << ProfileGeneration
             << ",\"content_hash\":\"" << Escape(ProfileContentHash) << "\"}"
             << ",\"selection\":{\"selected_spell_id\":" << SelectedSpellId
             << ",\"summary_reason\":\"" << Escape(SummaryReason()) << "\""
             << ",\"healing_candidate_count\":" << HealingCandidateCount
             << ",\"unique_rejection_count\":" << UniqueRejectionCount
             << ",\"unique_reason_count\":" << UniqueReasonCount
             << ",\"reported_rejection_count\":" << Rejections.size()
             << ",\"omitted_rejection_count\":"
             << (UniqueRejectionCount - Rejections.size())
             << ",\"rejections\":[";
        for (std::size_t index = 0; index < Rejections.size(); ++index)
        {
            if (index)
                json << ',';
            json << "{\"spell_id\":" << Rejections[index].SpellId
                 << ",\"reason\":\"" << Escape(Rejections[index].Reason)
                 << "\"}";
        }
        json << "]}}";
        return json.str();
    }

private:
    static std::string Escape(std::string const& value)
    {
        std::string escaped;
        escaped.reserve(value.size());
        for (unsigned char character : value)
        {
            switch (character)
            {
                case '\\': escaped += "\\\\"; break;
                case '"': escaped += "\\\""; break;
                case '\b': escaped += "\\b"; break;
                case '\f': escaped += "\\f"; break;
                case '\n': escaped += "\\n"; break;
                case '\r': escaped += "\\r"; break;
                case '\t': escaped += "\\t"; break;
                default:
                    if (character < 0x20)
                    {
                        std::ostringstream codepoint;
                        codepoint << "\\u" << std::hex << std::setw(4)
                                  << std::setfill('0') << std::uint32_t(character);
                        escaped += codepoint.str();
                    }
                    else
                        escaped += char(character);
                    break;
            }
        }
        return escaped;
    }
};

struct CastFailureReceipt
{
    std::string RetryReason;
    std::string DetailJson;
};

inline CastFailureReceipt MakeCastFailureReceipt(
    Diagnostic const& selection, std::string retryReason)
{
    return { std::move(retryReason), selection.ToJson() };
}
}

#endif
