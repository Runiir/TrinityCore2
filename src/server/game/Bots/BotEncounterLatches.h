#ifndef TRINITY_BOT_ENCOUNTER_LATCHES_H
#define TRINITY_BOT_ENCOUNTER_LATCHES_H

#include "Define.h"
#include "ObjectGuid.h"

#include <functional>
#include <map>
#include <string>
#include <string_view>

// Cohort-scoped encounter latches: facts that must survive one blackboard
// revision ("the burn was released at t", "Pain Suppression was cast at t")
// and must read the same for every bot of the cohort.
//
// The cohort owns one EncounterLatchStore. The blackboard publisher updates it
// exactly once per publication, after the snapshot is complete, and boss
// modules set latches from that snapshot only. Bots never write latches; they
// read the published view (same revision as the blackboard they decide on), so
// a bot whose decision tick skipped a short-lived condition still agrees with
// the rest of the raid. Boss-neutral: latch names carry the boss prefix.
namespace BotEncounter
{
struct EncounterLatch
{
    uint64 SetAtMs = 0;
    uint64 SetAtRevision = 0;
    uint64 Value = 0;
};

struct EncounterLatchView
{
    // Scope identity (cohort, attempt, wipe, route generation, node, map,
    // instance, encounter, server and native encounter epochs).
    std::string ScopeKey;
    // Blackboard revision and time of the publication that produced the view.
    uint64 Revision = 0;
    uint64 ObservedAtMs = 0;
    // The encounter object the latches belong to (normally the boss).
    ObjectGuid Subject;
    std::map<std::string, EncounterLatch, std::less<>> Latches;

    EncounterLatch const* Find(std::string_view name) const
    {
        auto itr = Latches.find(name);
        return itr == Latches.end() ? nullptr : &itr->second;
    }
};

inline std::string EncounterLatchScopeKey(std::string const& scopeKey,
    uint64 serverEpoch, uint64 encounterEpoch)
{
    return scopeKey + ":" + std::to_string(serverEpoch) + ":"
        + std::to_string(encounterEpoch);
}

class EncounterLatchStore
{
public:
    // Once per blackboard publication, before any boss module runs. A new
    // scope (next attempt, wipe, route node, native encounter epoch) clears
    // every latch.
    void BeginPublication(std::string const& scopeKey, uint64 revision, uint64 nowMs)
    {
        if (scopeKey != _view.ScopeKey)
        {
            _view.ScopeKey = scopeKey;
            _view.Subject.Clear();
            _view.Latches.clear();
        }
        _view.Revision = revision;
        _view.ObservedAtMs = nowMs;
    }

    // A boss module binds its subject; another subject (a respawned boss
    // object) starts from no latches.
    void BindSubject(ObjectGuid subject)
    {
        if (subject == _view.Subject)
            return;
        _view.Subject = subject;
        _view.Latches.clear();
    }

    // The subject disengaged (evade with survivors, compatibility respawn
    // keeping the same GUID): nothing carries into the next pull.
    void Reset()
    {
        _view.Subject.Clear();
        _view.Latches.clear();
    }

    // Sets a latch once; later calls keep the first publication's time.
    EncounterLatch const& Latch(std::string_view name, uint64 value = 0)
    {
        auto [itr, inserted] = _view.Latches.try_emplace(std::string(name));
        if (inserted)
            itr->second = { _view.ObservedAtMs, _view.Revision, value };
        return itr->second;
    }

    void Clear(std::string_view name)
    {
        auto itr = _view.Latches.find(name);
        if (itr != _view.Latches.end())
            _view.Latches.erase(itr);
    }

    EncounterLatch const* Find(std::string_view name) const
    {
        return _view.Find(name);
    }

    EncounterLatchView const& View() const
    {
        return _view;
    }

private:
    EncounterLatchView _view;
};
}

#endif
