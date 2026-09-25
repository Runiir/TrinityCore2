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
// exactly once per publication, after the snapshot is complete, dispatching
// each encounter module by route node; modules set latches from that snapshot
// only. Bots never write latches; they read the published view (same revision
// as the blackboard they decide on), so a bot whose decision tick skipped a
// short-lived condition still agrees with the rest of the raid.
//
// Boss-neutral: every module (one per encounter, or one per unit of a
// multi-unit encounter) owns its own sub-store with its own subject, so
// binding one module's subject never clears another module's latches.
namespace BotEncounter
{
struct EncounterLatch
{
    uint64 SetAtMs = 0;
    uint64 SetAtRevision = 0;
    uint64 Value = 0;
};

struct EncounterLatchModuleView
{
    // The encounter object the latches belong to (normally the boss).
    ObjectGuid Subject;
    std::map<std::string, EncounterLatch, std::less<>> Latches;

    EncounterLatch const* Find(std::string_view name) const
    {
        auto itr = Latches.find(name);
        return itr == Latches.end() ? nullptr : &itr->second;
    }
};

struct EncounterLatchView
{
    // Scope identity: cohort, attempt, wipe, route generation, node, map,
    // instance and encounter, plus the server and native encounter epochs.
    // The native encounter epoch is authoritative only for Magmaw today
    // (ObserveMagmawLifecycle); for every other boss it is 0 until a generic
    // native epoch exists, so modules must also reset on disengage.
    std::string ScopeKey;
    // Blackboard revision and time of the publication that produced the view.
    uint64 Revision = 0;
    uint64 ObservedAtMs = 0;
    std::map<std::string, EncounterLatchModuleView, std::less<>> Modules;

    EncounterLatchModuleView const* Module(std::string_view module) const
    {
        auto itr = Modules.find(module);
        return itr == Modules.end() ? nullptr : &itr->second;
    }
};

inline std::string EncounterLatchScopeKey(std::string const& scopeKey,
    uint64 serverEpoch, uint64 encounterEpoch)
{
    return scopeKey + ":" + std::to_string(serverEpoch) + ":"
        + std::to_string(encounterEpoch);
}

// Mutable handle on one module's sub-store, valid for one publication.
class EncounterLatchModule
{
public:
    // Another subject (a respawned boss object) starts from no latches.
    void BindSubject(ObjectGuid subject)
    {
        if (subject == _view->Subject)
            return;
        _view->Subject = subject;
        _view->Latches.clear();
    }

    // The subject disengaged (evade with survivors, compatibility respawn
    // keeping the same GUID): nothing carries into the next pull.
    void Reset()
    {
        _view->Subject.Clear();
        _view->Latches.clear();
    }

    // Sets a latch once; later calls keep the first publication's values.
    EncounterLatch const& Latch(std::string_view name, uint64 value = 0)
    {
        auto [itr, inserted] = _view->Latches.try_emplace(std::string(name));
        if (inserted)
            itr->second = { _nowMs, _revision, value };
        return itr->second;
    }

    void Clear(std::string_view name)
    {
        auto itr = _view->Latches.find(name);
        if (itr != _view->Latches.end())
            _view->Latches.erase(itr);
    }

    EncounterLatch const* Find(std::string_view name) const
    {
        return _view->Find(name);
    }

    ObjectGuid Subject() const
    {
        return _view->Subject;
    }

    uint64 NowMs() const
    {
        return _nowMs;
    }

private:
    friend class EncounterLatchStore;
    EncounterLatchModule(EncounterLatchModuleView& view, uint64 revision, uint64 nowMs)
        : _view(&view), _revision(revision), _nowMs(nowMs) { }

    EncounterLatchModuleView* _view;
    uint64 _revision;
    uint64 _nowMs;
};

class EncounterLatchStore
{
public:
    // Once per blackboard publication, before any module runs. A new scope
    // (next attempt, wipe, route node, native encounter epoch) clears every
    // module.
    void BeginPublication(std::string const& scopeKey, uint64 revision, uint64 nowMs)
    {
        if (scopeKey != _view.ScopeKey)
        {
            _view.ScopeKey = scopeKey;
            _view.Modules.clear();
        }
        _view.Revision = revision;
        _view.ObservedAtMs = nowMs;
    }

    EncounterLatchModule Module(std::string_view module)
    {
        auto [itr, inserted] = _view.Modules.try_emplace(std::string(module));
        (void)inserted;
        return EncounterLatchModule(itr->second, _view.Revision, _view.ObservedAtMs);
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
