#ifndef TRINITY_BOT_VALIDATION_PREPULL_CHECKPOINT_H
#define TRINITY_BOT_VALIDATION_PREPULL_CHECKPOINT_H

#include "Bots/BotActionArbiter.h"

#include <cstdint>
#include <map>
#include <sstream>
#include <string>
#include <utility>

namespace BotValidationPrepullCheckpoint
{
enum class Phase : uint8_t { Disabled, Staging, Ready, Released };

inline char const* ToString(Phase phase)
{
    switch (phase)
    {
        case Phase::Disabled: return "disabled";
        case Phase::Staging: return "staging";
        case Phase::Ready: return "ready";
        case Phase::Released: return "released";
    }
    return "disabled";
}

struct Scope
{
    std::string Cohort;
    uint64_t Attempt = 0;
    uint64_t RouteGeneration = 0;
    std::string Node;

    bool operator==(Scope const& other) const
    {
        return Cohort == other.Cohort && Attempt == other.Attempt
            && RouteGeneration == other.RouteGeneration && Node == other.Node;
    }

    std::string Key() const
    {
        return Cohort + ":" + std::to_string(Attempt) + ":"
            + std::to_string(RouteGeneration) + ":" + Node;
    }
};

struct MemberReceipt
{
    uint32_t Guid = 0;
    bool Alive = false;
    bool OutOfCombat = false;
    bool Formed = false;
    bool Flask = false;
    bool Food = false;
    bool Prepot = false;

    bool Ready() const
    {
        return Guid && Alive && OutOfCombat && Formed && Flask && Food && Prepot;
    }
};

class Checkpoint
{
public:
    void Configure(bool enabled, Scope scope, uint32_t expectedMembers)
    {
        if (!enabled)
        {
            *this = {};
            return;
        }
        if (_phase != Phase::Disabled && _scope == scope
            && _expectedMembers == expectedMembers)
            return;
        _scope = std::move(scope);
        _expectedMembers = expectedMembers;
        _members.clear();
        _releaseCount = 0;
        _phase = Phase::Staging;
    }

    bool Observe(Scope const& scope, MemberReceipt receipt)
    {
        if (_phase == Phase::Disabled || _phase == Phase::Released
            || !(scope == _scope) || !receipt.Guid)
            return false;
        _members[receipt.Guid] = receipt;
        if (_phase == Phase::Staging && AllReady())
            _phase = Phase::Ready;
        return true;
    }

    bool Release(Scope const& scope)
    {
        if (_phase != Phase::Ready || !(scope == _scope)
            || _releaseCount || !AllReady())
            return false;
        _phase = Phase::Released;
        ++_releaseCount;
        return true;
    }

    bool Enabled() const { return _phase != Phase::Disabled; }
    bool Released() const { return _phase == Phase::Released; }
    Phase CurrentPhase() const { return _phase; }
    uint32_t ReleaseCount() const { return _releaseCount; }
    Scope const& CurrentScope() const { return _scope; }
    std::map<uint32_t, MemberReceipt> const& Members() const { return _members; }

    std::string AdmissionReason(
        BotActionArbitration::Candidate const&,
        BotActionArbitration::AdmissionMetadata const* admission) const
    {
        if (!Enabled() || Released())
            return {};
        if (!admission || admission->ScopeKey != _scope.Key())
            return "validation_prepull_checkpoint_stale_scope";
        using BotActionArbitration::AdmissionClass;
        switch (admission->Classification)
        {
            case AdmissionClass::FormationMovement:
            case AdmissionClass::FriendlyHealing:
            case AdmissionClass::BagConsumable:
            case AdmissionClass::OffenseSuppression:
                return {};
            case AdmissionClass::Unknown:
                return "validation_prepull_checkpoint_hostile_or_unknown";
        }
        return "validation_prepull_checkpoint_hostile_or_unknown";
    }

    std::string ToJson() const
    {
        uint32_t alive = 0, idle = 0, formed = 0, flask = 0, food = 0;
        uint32_t prepot = 0, ready = 0;
        std::ostringstream members;
        bool first = true;
        for (auto const& [guid, receipt] : _members)
        {
            alive += receipt.Alive;
            idle += receipt.OutOfCombat;
            formed += receipt.Formed;
            flask += receipt.Flask;
            food += receipt.Food;
            prepot += receipt.Prepot;
            ready += receipt.Ready();
            if (!first)
                members << ',';
            first = false;
            members << "{\"guid\":" << guid
                << ",\"alive\":" << (receipt.Alive ? "true" : "false")
                << ",\"out_of_combat\":" << (receipt.OutOfCombat ? "true" : "false")
                << ",\"formed\":" << (receipt.Formed ? "true" : "false")
                << ",\"flask\":" << (receipt.Flask ? "true" : "false")
                << ",\"food\":" << (receipt.Food ? "true" : "false")
                << ",\"prepot\":" << (receipt.Prepot ? "true" : "false") << '}';
        }
        std::ostringstream json;
        json << "{\"enabled\":" << (Enabled() ? "true" : "false")
            << ",\"phase\":\"" << ToString(_phase) << "\""
            << ",\"scope_key\":\"" << _scope.Key() << "\""
            << ",\"expected_members\":" << _expectedMembers
            << ",\"member_count\":" << _members.size()
            << ",\"alive_count\":" << alive
            << ",\"out_of_combat_count\":" << idle
            << ",\"formed_count\":" << formed
            << ",\"flask_count\":" << flask
            << ",\"food_count\":" << food
            << ",\"prepot_count\":" << prepot
            << ",\"ready_count\":" << ready
            << ",\"all_ready\":" << (AllReady() ? "true" : "false")
            << ",\"release_count\":" << _releaseCount
            << ",\"members\":[" << members.str() << "]}";
        return json.str();
    }

private:
    bool AllReady() const
    {
        if (!_expectedMembers || _members.size() != _expectedMembers)
            return false;
        for (auto const& [guid, receipt] : _members)
            if (guid != receipt.Guid || !receipt.Ready())
                return false;
        return true;
    }

    Phase _phase = Phase::Disabled;
    Scope _scope;
    uint32_t _expectedMembers = 0;
    uint32_t _releaseCount = 0;
    std::map<uint32_t, MemberReceipt> _members;
};

inline void InstallAdmissionPolicy(BotActionArbitration::Kernel& kernel,
    Checkpoint const& checkpoint)
{
    if (!checkpoint.Enabled() || checkpoint.Released())
        return;
    kernel.SetAdmissionPolicy([&checkpoint](
        BotActionArbitration::Candidate const& candidate,
        BotActionArbitration::AdmissionMetadata const* admission)
    {
        return checkpoint.AdmissionReason(candidate, admission);
    });
}
}

#endif
