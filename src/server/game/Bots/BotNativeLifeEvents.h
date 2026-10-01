#ifndef TRINITY_BOT_NATIVE_LIFE_EVENTS_H
#define TRINITY_BOT_NATIVE_LIFE_EVENTS_H

// Per-bot native life edges (round 2, Blackwing Descent 10N, Nefarian).
//
// The wipe-scoped native_recovery sequences (death_sequence ...
// resurrection_sequence) are sampled by the raid runtime and only advance
// inside a wipe generation, so a bot that died, released and was brought back
// between two samples left no native trace: run 6bf52232 recorded 0 deaths
// beside 1103 lethal combat-log events.  This registry counts every observed
// alive -> dead and dead -> alive edge per bot:
// - UpdateBot observes the bot on entry and on exit.  A dead bot acts only
//   inside its own update, so a death is seen before it can release, and an
//   in-update revive (release, corpse reclaim, self-resurrection) is seen
//   before the next map update can kill it again.
// - The native death itself: a lethal landed hit (DealDamage's bot callback,
//   NotifyCombatDamage, runs just before Unit::Kill sets JUST_DIED).  A
//   lethal hit on a bot the registry still holds dead proves an unobserved
//   resurrection in between, so it counts that resurrection and the death:
//   every resurrection is counted however it happened, at the latest when the
//   bot next dies.
// - A caster's resurrection acceptance (BotNativeAction::CombatResAccept,
//   inside the caster's update) observes the target before the native
//   response and again after its teleport acknowledgement, when the delayed
//   DELAYED_RESURRECT_PLAYER operation has run.
//
// Counts are scoped to one cohort lifecycle (Scope: a process-unique
// lifecycle id and the cohort AttemptId).  ResetCombatLog, which only a true
// start or restart calls, begins a new lifecycle for the cohort with the next
// value of one process-wide counter (BeginLifecycle), so two cohorts, or a
// cohort recreated under the same id, never share a scope even though their
// own CombatLogEpoch/AttemptId counters can coincide.  The 15-minute
// recording-window rotation does not reset the combat log, so counts stay
// continuous through it.  A bot observed under a new scope (a GUID leased by
// another cohort) starts from a fresh baseline; readers of an older scope see
// nothing.
//
// Observation only: nothing here changes gameplay.  The counts are exported
// beside the existing sequences as native_death_count and
// native_resurrection_count; the wipe-scoped sequences keep their meaning.

#include "Define.h"

#include <mutex>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace BotNativeLifeEvents
{
struct Scope
{
    uint64 LifecycleId = 0;
    uint64 AttemptId = 0;

    bool operator==(Scope const& other) const
    {
        return LifecycleId == other.LifecycleId && AttemptId == other.AttemptId;
    }
};

struct Counts
{
    Scope Of;
    uint64 Deaths = 0;
    uint64 Resurrections = 0;
    uint64 LastDeathMs = 0;
    uint64 LastResurrectionMs = 0;
    bool Observed = false;
    bool Dead = false;
};

// One native full-wipe edge (every roster member dead in one raid sample),
// recorded where UpdateValidationCohortRaidRuntime increments WipeGeneration
// (BWD 10N round 4, diag_r3 Q3/Q5).  The harness closes a boss window at the
// first full wipe inside it: the attempt is judged a wipe, and the observer
// (whose reporter is a living bot) is only required to cover it up to here.
struct FullWipe
{
    uint64 WipeGeneration = 0;
    uint64 AtMs = 0;
    uint64 RouteGeneration = 0;
    std::string NodeId;
    std::string NodeKind;
    bool EncounterInProgress = false;
};

struct FullWipeLedger
{
    Scope Of;
    std::vector<FullWipe> Rows;
};

constexpr size_t MaxFullWipesPerLifecycle = 32;

struct Registry
{
    std::mutex Lock;
    std::unordered_map<uint32, Counts> ByGuid;
    std::unordered_map<std::string, FullWipeLedger> FullWipesByCohort;
    std::unordered_map<std::string, uint64> LifecycleByCohort;
    uint64 LastLifecycleId = 0;
};

inline Registry& Instance()
{
    static Registry registry;
    return registry;
}

// A true cohort start (ResetCombatLog): the cohort's next process-unique lifecycle.
inline uint64 BeginLifecycle(std::string const& cohortId)
{
    Registry& registry = Instance();
    std::lock_guard<std::mutex> guard(registry.Lock);
    return registry.LifecycleByCohort[cohortId] = ++registry.LastLifecycleId;
}

// The scope of this cohort's current lifecycle and attempt.
inline Scope LifecycleScope(std::string const& cohortId, uint64 attemptId)
{
    Registry& registry = Instance();
    std::lock_guard<std::mutex> guard(registry.Lock);
    auto const found = registry.LifecycleByCohort.find(cohortId);
    return { found == registry.LifecycleByCohort.end() ? 0 : found->second, attemptId };
}

// Pure edge step: the first observation in a scope only sets the baseline;
// later observations count each alive -> dead and dead -> alive edge once.
inline void Step(Counts& counts, Scope const& scope, bool alive, uint64 nowMs)
{
    if (!counts.Observed || !(counts.Of == scope))
    {
        counts = Counts{};
        counts.Of = scope;
        counts.Observed = true;
        counts.Dead = !alive;
        return;
    }
    if (alive == !counts.Dead)
        return;
    counts.Dead = !alive;
    if (alive)
    {
        ++counts.Resurrections;
        counts.LastResurrectionMs = nowMs;
    }
    else
    {
        ++counts.Deaths;
        counts.LastDeathMs = nowMs;
    }
}

// A lethal landed hit on a living bot: the native death edge.  A bot the
// registry still holds dead was resurrected unobserved in between.
inline void StepLethal(Counts& counts, Scope const& scope, uint64 nowMs)
{
    if (!counts.Observed || !(counts.Of == scope))
    {
        counts = Counts{};
        counts.Of = scope;
        counts.Observed = true;
    }
    else if (counts.Dead)
    {
        ++counts.Resurrections;
        counts.LastResurrectionMs = nowMs;
    }
    ++counts.Deaths;
    counts.LastDeathMs = nowMs;
    counts.Dead = true;
}

inline void ObserveLethal(uint32 guid, Scope const& scope, uint64 nowMs)
{
    if (!guid)
        return;
    Registry& registry = Instance();
    std::lock_guard<std::mutex> guard(registry.Lock);
    StepLethal(registry.ByGuid[guid], scope, nowMs);
}

inline void Observe(uint32 guid, Scope const& scope, bool alive, uint64 nowMs)
{
    if (!guid)
        return;
    Registry& registry = Instance();
    std::lock_guard<std::mutex> guard(registry.Lock);
    Step(registry.ByGuid[guid], scope, alive, nowMs);
}

// This scope's counts; a bot last observed in another run reads as unobserved.
inline Counts Get(uint32 guid, Scope const& scope)
{
    Registry& registry = Instance();
    std::lock_guard<std::mutex> guard(registry.Lock);
    auto const found = registry.ByGuid.find(guid);
    if (found == registry.ByGuid.end() || !(found->second.Of == scope))
        return Counts{};
    return found->second;
}

// Record a full wipe for this cohort's lifecycle scope (bounded; a new scope
// starts an empty ledger).
inline void ObserveFullWipe(std::string const& cohortId, Scope const& scope, FullWipe const& wipe)
{
    Registry& registry = Instance();
    std::lock_guard<std::mutex> guard(registry.Lock);
    FullWipeLedger& ledger = registry.FullWipesByCohort[cohortId];
    if (!(ledger.Of == scope))
        ledger = FullWipeLedger{ scope, {} };
    if (ledger.Rows.size() < MaxFullWipesPerLifecycle)
        ledger.Rows.push_back(wipe);
}

inline std::vector<FullWipe> FullWipes(std::string const& cohortId, Scope const& scope)
{
    Registry& registry = Instance();
    std::lock_guard<std::mutex> guard(registry.Lock);
    auto const found = registry.FullWipesByCohort.find(cohortId);
    if (found == registry.FullWipesByCohort.end() || !(found->second.Of == scope))
        return {};
    return found->second.Rows;
}

// The raid_runtime "full_wipes" field (leading comma), or nothing without a
// full wipe in this scope, so a run that never wiped exports unchanged bytes.
inline std::string FullWipesJsonField(std::string const& cohortId, Scope const& scope)
{
    std::vector<FullWipe> const rows = FullWipes(cohortId, scope);
    if (rows.empty())
        return {};
    auto escaped = [](std::string const& value)
    {
        std::string out;
        for (char character : value)
        {
            if (character == '"' || character == '\\')
                out += '\\';
            if (static_cast<unsigned char>(character) >= 0x20)
                out += character;
        }
        return out;
    };
    std::ostringstream out;
    out << ",\"full_wipes\":[";
    for (size_t index = 0; index < rows.size(); ++index)
    {
        FullWipe const& row = rows[index];
        out << (index ? "," : "") << "{\"wipe_generation\":" << row.WipeGeneration
            << ",\"at_ms\":" << row.AtMs
            << ",\"route_generation\":" << row.RouteGeneration
            << ",\"route_node_id\":\"" << escaped(row.NodeId) << "\""
            << ",\"route_node_kind\":\"" << escaped(row.NodeKind) << "\""
            << ",\"encounter_in_progress\":" << (row.EncounterInProgress ? "true" : "false") << "}";
    }
    out << "]";
    return out.str();
}

// The native_recovery.members fields (leading comma, no braces).
inline std::string MemberJsonFields(uint32 guid, Scope const& scope)
{
    Counts const life = Get(guid, scope);
    std::ostringstream out;
    out << ",\"native_death_count\":" << life.Deaths
        << ",\"native_resurrection_count\":" << life.Resurrections
        << ",\"native_last_death_ms\":" << life.LastDeathMs
        << ",\"native_last_resurrection_ms\":" << life.LastResurrectionMs
        << ",\"native_dead\":" << (life.Dead ? "true" : "false");
    return out.str();
}
}

#endif
