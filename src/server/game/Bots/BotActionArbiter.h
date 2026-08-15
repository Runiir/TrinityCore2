#ifndef TRINITY_BOT_ACTION_ARBITER_H
#define TRINITY_BOT_ACTION_ARBITER_H

#include "Bots/BotTypes.h"
#include "Define.h"
#include <algorithm>
#include <functional>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace BotActionArbitration
{
enum class Priority : uint8
{
    Idle = 0,
    RouteMovement = 20,
    CombatMovement = 40,
    TrainedDamage = 60,
    ThreatControl = 80,
    Support = 100,
    Interrupt = 120,
    Mechanic = 140,
    Survival = 160,
    Terminal = 180
};

enum class Disposition : uint8
{
    NotApplicable,
    Retryable,
    Unsafe,
    Committed,
    Terminal
};

// Lifecycle is deliberately independent from Disposition.  Disposition tells
// the arbiter whether another candidate may run during this tick; Phase tells
// telemetry and a future learned scorer what actually happened to the action.
enum class Phase : uint8
{
    Proposed,
    Deferred,
    Selected,
    Submitted,
    Started,
    Progressed,
    Completed,
    Failed,
    Terminal
};

struct Outcome
{
    Disposition Result = Disposition::NotApplicable;
    // Candidate callbacks often build the reason from frame-local resolver
    // state. Own it so the trace cannot retain a dangling string_view after
    // the callback returns to Resolve().
    std::string Reason = "not_applicable";
    Phase LifecyclePhase = Phase::Deferred;

    static Outcome NotApplicable(std::string_view reason = "not_applicable")
    {
        return { Disposition::NotApplicable, std::string(reason), Phase::Deferred };
    }

    static Outcome Retryable(std::string_view reason)
    {
        return { Disposition::Retryable, std::string(reason), Phase::Failed };
    }

    static Outcome Unsafe(std::string_view reason)
    {
        return { Disposition::Unsafe, std::string(reason), Phase::Failed };
    }

    static Outcome Committed(std::string_view reason)
    {
        return { Disposition::Committed, std::string(reason), Phase::Completed };
    }

    static Outcome Started(std::string_view reason)
    {
        return { Disposition::Committed, std::string(reason), Phase::Started };
    }

    static Outcome Progressed(std::string_view reason)
    {
        return { Disposition::Committed, std::string(reason), Phase::Progressed };
    }

    static Outcome Terminal(std::string_view reason)
    {
        return { Disposition::Terminal, std::string(reason), Phase::Terminal };
    }
};

inline Outcome FromBotActionResult(BotActionResult result)
{
    switch (result)
    {
        case BotActionResult::Ok:
            return Outcome::Committed("ok");
        case BotActionResult::Casting:
            return Outcome::Started("casting");
        case BotActionResult::GlobalCooldown:
            return Outcome::Started("global_cooldown");
        case BotActionResult::NoOwner:
            return Outcome::Terminal("owner_unavailable");
        case BotActionResult::NoBot:
            return Outcome::Terminal("bot_unavailable");
        case BotActionResult::InvalidTarget:
            return Outcome::Retryable("invalid_target");
        case BotActionResult::NotFriendly:
            return Outcome::Retryable("target_not_friendly");
        case BotActionResult::DeadTarget:
            return Outcome::Retryable("target_dead");
        case BotActionResult::OutOfRange:
            return Outcome::Retryable("out_of_range");
        case BotActionResult::NoLineOfSight:
            return Outcome::Retryable("no_line_of_sight");
        case BotActionResult::Cooldown:
            return Outcome::Retryable("cooldown");
        case BotActionResult::NoMana:
            return Outcome::Retryable("no_power");
        case BotActionResult::BadSpell:
            return Outcome::Retryable("spell_unavailable");
        case BotActionResult::CastFailed:
            return Outcome::Retryable("cast_failed");
        case BotActionResult::Throttled:
            return Outcome::Retryable("throttled");
        case BotActionResult::Disabled:
            return Outcome::NotApplicable("disabled");
        case BotActionResult::NoAction:
            return Outcome::NotApplicable("no_action");
    }

    return Outcome::Retryable("unknown_action_result");
}

enum class Resource : uint16
{
    None = 0,
    GlobalCooldown = 1 << 0,
    Cast = 1 << 1,
    Movement = 1 << 2,
    Target = 1 << 3,
    Interaction = 1 << 4,
    Pet = 1 << 5
};

using ResourceMask = uint16;

constexpr ResourceMask Uses(Resource resource)
{
    return ResourceMask(resource);
}

template <typename... Resources>
constexpr ResourceMask Uses(Resource first, Resources... rest)
{
    return ResourceMask(ResourceMask(first) | Uses(rest...));
}

constexpr bool Conflicts(ResourceMask left, ResourceMask right)
{
    return (left & right) != 0;
}

struct Candidate
{
    std::string Key;
    std::string Source;
    Priority ActionPriority = Priority::Idle;
    float UtilityScore = 0.0f;
    float PolicyScore = 0.0f;
    float PolicyWeight = 0.0f;
    ResourceMask RequiredResources = Uses(Resource::None);
    uint64 ExpiresAtMs = 0;
    uint32 RetryBaseMs = 100;
    uint32 RetryMaxMs = 3000;
    uint8 EscalateAfter = 5;
    bool Allowed = true;
    std::string RejectReason;
    std::function<Outcome()> Attempt;

    float Score() const
    {
        return UtilityScore + PolicyScore * PolicyWeight;
    }
};

struct Lifecycle
{
    Phase CurrentPhase = Phase::Proposed;
    Disposition LastDisposition = Disposition::NotApplicable;
    std::string LastReason = "not_attempted";
    uint64 FirstFailureAtMs = 0;
    uint64 LastAttemptAtMs = 0;
    uint64 LastProgressAtMs = 0;
    uint64 RetryAfterMs = 0;
    uint32 AttemptCount = 0;
    uint32 ConsecutiveFailures = 0;
    uint8 EscalateAfter = 5;
};

struct CandidateTrace
{
    std::string Key;
    std::string Source;
    std::string Status;
    std::string Reason;
    Priority ActionPriority = Priority::Idle;
    float Score = 0.0f;
    ResourceMask RequiredResources = Uses(Resource::None);
    Phase LifecyclePhase = Phase::Proposed;
};

struct Resolution
{
    bool AnyCommitted = false;
    bool Terminal = false;
    ResourceMask ClaimedResources = Uses(Resource::None);
    std::vector<std::string> CommittedCandidates;
    std::vector<CandidateTrace> Trace;
};

inline char const* ToString(Disposition disposition)
{
    switch (disposition)
    {
        case Disposition::NotApplicable: return "not_applicable";
        case Disposition::Retryable: return "retryable";
        case Disposition::Unsafe: return "unsafe";
        case Disposition::Committed: return "committed";
        case Disposition::Terminal: return "terminal";
    }
    return "unknown";
}

inline char const* ToString(Phase phase)
{
    switch (phase)
    {
        case Phase::Proposed: return "proposed";
        case Phase::Deferred: return "deferred";
        case Phase::Selected: return "selected";
        case Phase::Submitted: return "submitted";
        case Phase::Started: return "started";
        case Phase::Progressed: return "progressed";
        case Phase::Completed: return "completed";
        case Phase::Failed: return "failed";
        case Phase::Terminal: return "terminal";
    }
    return "unknown";
}

// A small, deterministic utility kernel.  Producers may submit candidates in
// any order.  Resolve applies hard masks first, then priority and score, and
// permits multiple committed actions only when their resource lanes do not
// conflict.  Retryable failures back off only their own key, leaving useful
// alternatives eligible during the same tick.
class Kernel
{
public:
    void Begin(uint64 nowMs)
    {
        _nowMs = nowMs;
        _nextSerial = 0;
        _candidates.clear();
        _lastResolution = {};
    }

    bool Submit(Candidate candidate)
    {
        if (candidate.Key.empty() || !candidate.Attempt)
            return false;

        QueuedCandidate queued{ std::move(candidate), _nextSerial++ };
        auto existing = std::find_if(_candidates.begin(), _candidates.end(),
            [&queued](QueuedCandidate const& row)
            {
                return row.Value.Key == queued.Value.Key;
            });
        if (existing == _candidates.end())
        {
            _candidates.push_back(std::move(queued));
            return true;
        }

        // Deduplicate trigger-like proposals by stable action key.  Preserve
        // the earliest serial for deterministic ties while retaining the most
        // valuable form of the candidate.
        if (Better(queued, *existing))
        {
            queued.Serial = existing->Serial;
            *existing = std::move(queued);
        }
        return true;
    }

    Resolution const& Resolve()
    {
        std::stable_sort(_candidates.begin(), _candidates.end(), Better);
        for (QueuedCandidate& queued : _candidates)
        {
            Candidate& candidate = queued.Value;
            Lifecycle& lifecycle = _lifecycles[candidate.Key];
            lifecycle.EscalateAfter = candidate.EscalateAfter;
            lifecycle.CurrentPhase = Phase::Proposed;

            if (!candidate.Allowed)
            {
                Trace(candidate, "hard_masked",
                    candidate.RejectReason.empty() ? "hard_safety_mask" : candidate.RejectReason,
                    Phase::Deferred);
                continue;
            }
            if (candidate.ExpiresAtMs && candidate.ExpiresAtMs <= _nowMs)
            {
                Trace(candidate, "expired", "candidate_expired", Phase::Deferred);
                continue;
            }
            if (lifecycle.RetryAfterMs > _nowMs)
            {
                Trace(candidate, "backoff", lifecycle.LastReason, Phase::Deferred);
                continue;
            }
            if (Conflicts(candidate.RequiredResources, _lastResolution.ClaimedResources))
            {
                Trace(candidate, "resource_conflict", "resource_lane_owned", Phase::Deferred);
                continue;
            }

            lifecycle.CurrentPhase = Phase::Selected;
            ++lifecycle.AttemptCount;
            lifecycle.LastAttemptAtMs = _nowMs;
            Outcome outcome = candidate.Attempt();
            Observe(candidate.Key, outcome, _nowMs, candidate.RetryBaseMs,
                candidate.RetryMaxMs, candidate.EscalateAfter);
            Trace(candidate, "attempted", outcome.Reason, outcome.LifecyclePhase);

            if (outcome.Result == Disposition::Committed)
            {
                _lastResolution.AnyCommitted = true;
                _lastResolution.ClaimedResources |= candidate.RequiredResources;
                _lastResolution.CommittedCandidates.push_back(candidate.Key);
            }
            else if (outcome.Result == Disposition::Terminal)
            {
                _lastResolution.Terminal = true;
                break;
            }
        }
        // Candidate callbacks commonly capture frame-local controller state.
        // Never retain those closures beyond the resolution boundary.
        _candidates.clear();
        return _lastResolution;
    }

    void Observe(std::string const& key, Outcome outcome, uint64 nowMs,
        uint32 retryBaseMs = 100, uint32 retryMaxMs = 3000,
        uint8 escalateAfter = 5)
    {
        Lifecycle& lifecycle = _lifecycles[key];
        lifecycle.CurrentPhase = outcome.LifecyclePhase;
        lifecycle.LastDisposition = outcome.Result;
        lifecycle.LastReason = std::string(outcome.Reason);
        lifecycle.LastAttemptAtMs = nowMs;
        lifecycle.EscalateAfter = escalateAfter;

        if (outcome.Result == Disposition::Committed)
        {
            lifecycle.ConsecutiveFailures = 0;
            lifecycle.FirstFailureAtMs = 0;
            lifecycle.RetryAfterMs = 0;
            lifecycle.LastProgressAtMs = nowMs;
            return;
        }
        if (outcome.Result == Disposition::NotApplicable)
        {
            lifecycle.ConsecutiveFailures = 0;
            lifecycle.FirstFailureAtMs = 0;
            lifecycle.RetryAfterMs = 0;
            return;
        }

        if (!lifecycle.ConsecutiveFailures)
            lifecycle.FirstFailureAtMs = nowMs;
        ++lifecycle.ConsecutiveFailures;
        uint32 shift = std::min<uint32>(lifecycle.ConsecutiveFailures - 1, 8);
        uint64 delay = uint64(retryBaseMs) << shift;
        lifecycle.RetryAfterMs = nowMs + std::min<uint64>(retryMaxMs, delay);
    }

    bool ShouldEscalate(std::string const& key, uint64 nowMs,
        uint64 minimumFailureDurationMs = 5000) const
    {
        auto itr = _lifecycles.find(key);
        if (itr == _lifecycles.end())
            return false;
        Lifecycle const& lifecycle = itr->second;
        return lifecycle.ConsecutiveFailures >= lifecycle.EscalateAfter
            && lifecycle.FirstFailureAtMs
            && nowMs >= lifecycle.FirstFailureAtMs + minimumFailureDurationMs;
    }

    void MarkProgress(std::string const& key, uint64 nowMs,
        std::string_view reason = "semantic_progress")
    {
        Observe(key, Outcome::Progressed(reason), nowMs);
    }

    Lifecycle const* FindLifecycle(std::string const& key) const
    {
        auto itr = _lifecycles.find(key);
        return itr == _lifecycles.end() ? nullptr : &itr->second;
    }

    Resolution const& LastResolution() const { return _lastResolution; }

    std::string LastResolutionJson() const
    {
        std::ostringstream out;
        out << "{\"committed\":" << (_lastResolution.AnyCommitted ? "true" : "false")
            << ",\"terminal\":" << (_lastResolution.Terminal ? "true" : "false")
            << ",\"claimed_resources\":" << _lastResolution.ClaimedResources
            << ",\"committed_candidates\":[";
        for (size_t index = 0; index < _lastResolution.CommittedCandidates.size(); ++index)
        {
            if (index)
                out << ',';
            out << '\"' << Escape(_lastResolution.CommittedCandidates[index]) << '\"';
        }
        out << "],\"candidates\":[";
        for (size_t index = 0; index < _lastResolution.Trace.size(); ++index)
        {
            CandidateTrace const& trace = _lastResolution.Trace[index];
            if (index)
                out << ',';
            out << "{\"key\":\"" << Escape(trace.Key)
                << "\",\"source\":\"" << Escape(trace.Source)
                << "\",\"status\":\"" << Escape(trace.Status)
                << "\",\"reason\":\"" << Escape(trace.Reason)
                << "\",\"priority\":" << uint32(trace.ActionPriority)
                << ",\"score\":" << trace.Score
                << ",\"resources\":" << trace.RequiredResources
                << ",\"phase\":\"" << ToString(trace.LifecyclePhase) << "\"}";
        }
        out << "]}";
        return out.str();
    }

private:
    struct QueuedCandidate
    {
        Candidate Value;
        uint64 Serial = 0;
    };

    static bool Better(QueuedCandidate const& left, QueuedCandidate const& right)
    {
        if (left.Value.ActionPriority != right.Value.ActionPriority)
            return uint8(left.Value.ActionPriority) > uint8(right.Value.ActionPriority);
        if (left.Value.Score() != right.Value.Score())
            return left.Value.Score() > right.Value.Score();
        if (left.Value.Source != right.Value.Source)
            return left.Value.Source < right.Value.Source;
        if (left.Value.Key != right.Value.Key)
            return left.Value.Key < right.Value.Key;
        return left.Serial < right.Serial;
    }

    static std::string Escape(std::string_view value)
    {
        std::string escaped;
        escaped.reserve(value.size());
        for (char character : value)
        {
            if (character == '\\' || character == '\"')
                escaped.push_back('\\');
            if (character == '\n')
            {
                escaped += "\\n";
                continue;
            }
            escaped.push_back(character);
        }
        return escaped;
    }

    void Trace(Candidate const& candidate, std::string status,
        std::string_view reason, Phase phase)
    {
        _lastResolution.Trace.push_back(CandidateTrace{
            candidate.Key,
            candidate.Source,
            std::move(status),
            std::string(reason),
            candidate.ActionPriority,
            candidate.Score(),
            candidate.RequiredResources,
            phase,
        });
    }

    uint64 _nowMs = 0;
    uint64 _nextSerial = 0;
    std::vector<QueuedCandidate> _candidates;
    std::unordered_map<std::string, Lifecycle> _lifecycles;
    Resolution _lastResolution;
};

// Candidates are submitted in descending priority. A retryable, unsafe, or
// inapplicable candidate never resolves the tick: the caller immediately tries
// the next compatible action. This deliberately keeps execution at the call
// site so encounter actions do not require heap-allocated type erasure.
class Tick
{
public:
    template <typename Attempt>
    Outcome Try(Priority priority, std::string_view candidate, Attempt&& attempt)
    {
        if (_resolved)
            return _outcome;

        uint8 const numericPriority = uint8(priority);
        if (_attemptCount && numericPriority > _lastPriority)
        {
            _candidate = candidate;
            _outcome = Outcome::Terminal("action_priority_inversion");
            _resolved = true;
            _orderingValid = false;
            return _outcome;
        }

        _lastPriority = numericPriority;
        ++_attemptCount;
        _candidate = candidate;
        _outcome = attempt();
        if (_outcome.Result == Disposition::Committed
            || _outcome.Result == Disposition::Terminal)
            _resolved = true;
        return _outcome;
    }

    bool Resolved() const { return _resolved; }
    bool OrderingValid() const { return _orderingValid; }
    uint16 AttemptCount() const { return _attemptCount; }
    std::string_view Candidate() const { return _candidate; }
    Outcome const& LastOutcome() const { return _outcome; }

private:
    uint8 _lastPriority = uint8(Priority::Terminal);
    uint16 _attemptCount = 0;
    bool _resolved = false;
    bool _orderingValid = true;
    std::string_view _candidate;
    Outcome _outcome;
};
}

#endif
