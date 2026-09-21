#ifndef TRINITY_BOT_BLOOD_DECISION_OBSERVATION_H
#define TRINITY_BOT_BLOOD_DECISION_OBSERVATION_H

#include "Bots/BotClassSpecActionProfile.h"
#include "Player.h"
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace BotBloodDecisionObservation
{
struct ReadyRunes
{
    uint8 Total = 0;
    uint8 Blood = 0;
    uint8 Unholy = 0;
    uint8 Frost = 0;
    uint8 Death = 0;
};

inline ReadyRunes ObserveReadyRunes(Player const* actor)
{
    ReadyRunes observation;
    if (!actor || actor->getClass() != CLASS_DEATH_KNIGHT)
        return observation;
    for (uint8 rune = 0; rune < MAX_RUNES; ++rune)
        if (std::abs(actor->GetRuneCooldown(rune)) <= 0.0001f)
        {
            ++observation.Total;
            switch (actor->GetCurrentRune(rune))
            {
                case RuneType::Blood: ++observation.Blood; break;
                case RuneType::Unholy: ++observation.Unholy; break;
                case RuneType::Frost: ++observation.Frost; break;
                case RuneType::Death: ++observation.Death; break;
                default: break;
            }
        }
    return observation;
}

inline std::string JsonEscape(std::string const& value)
{
    std::ostringstream escaped;
    for (unsigned char c : value)
        switch (c)
        {
            case '\"': escaped << "\\\""; break;
            case '\\': escaped << "\\\\"; break;
            case '\b': escaped << "\\b"; break;
            case '\f': escaped << "\\f"; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default:
                if (c < 0x20)
                    escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << uint32(c)
                            << std::dec << std::setfill(' ');
                else
                    escaped << c;
        }
    return escaped.str();
}

inline void AppendCandidate(std::ostringstream& json, char const* name,
    BotActionCandidate const* candidate)
{
    json << "\"" << name << "\":{";
    if (!candidate)
    {
        json << "\"present\":false,\"valid\":null,\"reject_reason\":null,"
             << "\"priority_bucket\":null,\"final_score\":null}";
        return;
    }
    json << "\"present\":true,\"valid\":" << (candidate->RejectReason.empty() ? "true" : "false")
         << ",\"reject_reason\":\"" << JsonEscape(candidate->RejectReason) << "\""
         << ",\"priority_bucket\":" << uint32(candidate->Profile.PriorityBucket)
         << ",\"final_score\":" << candidate->Score << '}';
}

inline bool IsRelevantSelection(uint32 spellId)
{
    return spellId == 49998 || spellId == 55050 || spellId == 48721 || spellId == 43265;
}

inline bool Attach(Player const* actor, std::vector<BotActionCandidate>& candidates,
    BotActionCandidate* selected, std::string const& specTag,
    uint64 evaluationStartedAtMs, char const* selectedMode, std::string& actionObservationJson)
{
    if (!actor || actor->getClass() != CLASS_DEATH_KNIGHT
        || (specTag != "blood_death_knight" && specTag != "blood") || !selected
        || !IsRelevantSelection(selected->SpellId))
        return false;

    BotActionCandidate const* deathStrike = nullptr;
    BotActionCandidate const* heartStrike = nullptr;
    for (BotActionCandidate const& candidate : candidates)
    {
        if (candidate.SpellId == 49998)
            deathStrike = &candidate;
        else if (candidate.SpellId == 55050)
            heartStrike = &candidate;
    }
    if (!deathStrike && !heartStrike)
        return false;
    ReadyRunes const runes = ObserveReadyRunes(actor);
    std::ostringstream json;
    json << std::setprecision(std::numeric_limits<float>::max_digits10)
         << "{\"schema\":\"blood_survival_candidate_observation_v1\""
         << ",\"phase\":\"pre_native_submission\""
         << ",\"evaluation_started_at_ms\":" << evaluationStartedAtMs
         << ",\"selected_spell_id\":" << selected->SpellId
         << ",\"selected_mode\":\"" << JsonEscape(selectedMode ? selectedMode : "") << "\""
         << ",\"health\":{\"current\":" << actor->GetHealth()
         << ",\"maximum\":" << actor->GetMaxHealth() << "}"
         << ",\"ready_runes\":{\"total\":" << uint32(runes.Total)
         << ",\"blood\":" << uint32(runes.Blood)
         << ",\"unholy\":" << uint32(runes.Unholy)
         << ",\"frost\":" << uint32(runes.Frost)
         << ",\"death\":" << uint32(runes.Death) << "},\"candidates\":{";
    AppendCandidate(json, "death_strike", deathStrike);
    json << ',';
    AppendCandidate(json, "heart_strike", heartStrike);
    json << "}}";
    selected->ObservationJson = json.str();
    actionObservationJson = selected->ObservationJson;
    if (!candidates.empty() && &candidates.front() != selected)
        candidates.front().ObservationJson = selected->ObservationJson;
    return true;
}
}

#endif
