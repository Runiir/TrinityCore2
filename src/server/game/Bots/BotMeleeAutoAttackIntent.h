#ifndef TRINITY_BOT_MELEE_AUTO_ATTACK_INTENT_H
#define TRINITY_BOT_MELEE_AUTO_ATTACK_INTENT_H

#include "Bots/BotActionArbiter.h"
#include "ObjectGuid.h"
#include <algorithm>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace BotMeleeAutoAttack
{
// This is a continuous player-toggle lane. It deliberately does not share
// the one-shot GCD, cast, target, or movement lanes: a player may keep auto
// attack enabled while running and casting instant abilities.
enum class Kind : uint8
{
    StartOrSwitch = 0,
    Stop = 1,
    Suppress = 2
};

enum class Owner : uint8
{
    Profile = 0,
    TargetSelection = 1,
    Route = 2,
    Threat = 3,
    Mechanic = 4,
    Recovery = 5,
    Safety = 6
};

inline char const* ToString(Kind kind)
{
    switch (kind)
    {
        case Kind::StartOrSwitch: return "start_or_switch";
        case Kind::Stop: return "stop";
        case Kind::Suppress: return "suppress";
    }
    return "unknown";
}

inline char const* ToString(Owner owner)
{
    switch (owner)
    {
        case Owner::Profile: return "profile";
        case Owner::TargetSelection: return "target_selection";
        case Owner::Route: return "route";
        case Owner::Threat: return "threat";
        case Owner::Mechanic: return "mechanic";
        case Owner::Recovery: return "recovery";
        case Owner::Safety: return "safety";
    }
    return "unknown";
}

struct Intent
{
    Kind Toggle = Kind::Stop;
    Owner IntentOwner = Owner::Profile;
    BotActionArbitration::Priority ActionPriority =
        BotActionArbitration::Priority::Idle;
    ObjectGuid Target;
    std::string Reason;
    uint64 ExpiresAtMs = 0;

    BotActionArbitration::ResourceMask Resources() const
    {
        return BotActionArbitration::Uses(
            BotActionArbitration::Resource::AutoAttackToggle);
    }

};

// Deterministic one-winner arbitration for the persistent toggle. Submission
// order is intentionally irrelevant. At equal priority a safety suppression
// beats a stop, and a stop beats a start/switch; remaining ties use stable
// typed identity. The world manager performs the sole native reconciliation
// after this lane resolves.
class Lane
{
public:
    void Begin(uint64 nowMs)
    {
        _nowMs = nowMs;
        // A party observation may enqueue a safety intent for a cohort peer
        // after that peer's UpdateBot scope has run. Preserve such typed work
        // until the peer's sole scope-exit resolution on its next world tick.
        // Every normal resolution clears the lane, so ordinary candidates do
        // not accumulate across ticks.
    }

    bool Submit(Intent intent)
    {
        if (intent.Reason.empty()
            || (intent.Toggle == Kind::StartOrSwitch
                && intent.Target.IsEmpty()))
            return false;

        auto existing = std::find_if(_candidates.begin(), _candidates.end(),
            [&intent](Intent const& row)
            {
                return row.Toggle == intent.Toggle
                    && row.IntentOwner == intent.IntentOwner
                    && row.Target == intent.Target
                    && row.Reason == intent.Reason;
            });
        if (existing == _candidates.end())
            _candidates.push_back(std::move(intent));
        else if (Better(intent, *existing))
            *existing = std::move(intent);
        return true;
    }

    std::optional<Intent> Resolve()
    {
        _candidates.erase(std::remove_if(_candidates.begin(),
            _candidates.end(), [this](Intent const& intent)
            {
                return intent.ExpiresAtMs && intent.ExpiresAtMs <= _nowMs;
            }), _candidates.end());
        std::sort(_candidates.begin(), _candidates.end(), Better);
        std::optional<Intent> selected;
        if (!_candidates.empty())
            selected = _candidates.front();
        _candidates.clear();
        return selected;
    }

    size_t CandidateCount() const { return _candidates.size(); }

private:
    static uint8 KindRank(Kind kind)
    {
        switch (kind)
        {
            case Kind::Suppress: return 2;
            case Kind::Stop: return 1;
            case Kind::StartOrSwitch: return 0;
        }
        return 0;
    }

    static bool Better(Intent const& left, Intent const& right)
    {
        if (left.ActionPriority != right.ActionPriority)
            return uint8(left.ActionPriority) > uint8(right.ActionPriority);
        if (KindRank(left.Toggle) != KindRank(right.Toggle))
            return KindRank(left.Toggle) > KindRank(right.Toggle);
        return std::tie(left.IntentOwner, left.Reason, left.Target)
            < std::tie(right.IntentOwner, right.Reason, right.Target);
    }

    uint64 _nowMs = 0;
    std::vector<Intent> _candidates;
};
}

#endif
