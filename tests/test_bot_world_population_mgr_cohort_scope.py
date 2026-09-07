from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"


def test_cohort_scope_resolver_and_scheduler_contract(tmp_path: Path) -> None:
    source = tmp_path / "cohort_scope_contract.cpp"
    binary = tmp_path / "cohort_scope_contract"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrCohortScope.h"

#include <cassert>
#include <vector>

using namespace BotWorldCohortScope;

RuntimeIdentity Runtime(char const* id, std::uint64_t attempt,
    std::uint32_t map, std::uint32_t instance)
{
    return { id, 91, attempt, map, instance, true, true };
}

ActorIdentity Actor(std::uint32_t map, std::uint32_t instance,
    char const* cohort = nullptr, std::uint64_t attempt = 0)
{
    ActorIdentity actor;
    actor.Present = true;
    actor.MapId = map;
    actor.InstanceId = instance;
    if (cohort)
    {
        actor.RequiresLease = true;
        actor.Lease = { true, 91, cohort, attempt };
    }
    return actor;
}

int main()
{
    int first = 1;
    int second = 2;
    int* selected = &first;
    {
        ScopedOverride<int> outer(selected, &second);
        assert(outer && selected == &second);
        {
            ScopedOverride<int> failed(selected, nullptr);
            assert(!failed && selected == nullptr);
        }
        assert(selected == &second);
    }
    assert(selected == &first);

    std::vector<RuntimeIdentity> runtimes = {
        Runtime("a", 7, 669, 101), Runtime("b", 9, 669, 202) };
    Resolution leased = Resolve(91, runtimes,
        { Actor(669, 101, "a", 7), Actor(669, 101) });
    assert(leased && leased.CohortId == "a");
    ActorIdentity unleasedPeer = Actor(669, 101);
    unleasedPeer.RequiresLease = true;
    Resolution leasedWithForeignPeer = Resolve(91, runtimes,
        { Actor(669, 101, "a", 7), unleasedPeer });
    assert(leasedWithForeignPeer
        && leasedWithForeignPeer.CohortId == "a");

    Resolution conflict = Resolve(91, runtimes,
        { Actor(669, 101, "a", 7), Actor(669, 101, "b", 9) });
    assert(conflict.Status == ResolutionStatus::ConflictingOwners);

    ActorIdentity stale = Actor(669, 101, "a", 7);
    stale.Lease.ServerEpoch = 90;
    assert(Resolve(91, runtimes, { stale }).Status
        == ResolutionStatus::StaleLease);
    assert(Resolve(91, runtimes, { Actor(669, 101, "a", 8) }).Status
        == ResolutionStatus::AttemptMismatch);

    ActorIdentity foreignPlayer = Actor(669, 101);
    foreignPlayer.RequiresLease = RequiresPlayerLease(
        false, false, true, false);
    assert(Resolve(91, runtimes, { foreignPlayer }).Status
        == ResolutionStatus::MissingOwner);
    Resolution creature = Resolve(91, runtimes, { Actor(669, 202) });
    assert(creature && creature.CohortId == "b");
    assert(RequiresPlayerLease(false, false, true, false));
    assert(RequiresPlayerLease(false, false, false, true));
    assert(RequiresPlayerLease(false, true, false, false));
    assert(!RequiresPlayerLease(false, false, false, false));

    LeaseIdentity released;
    assert(AllowsDiagnosticCleanup(91, "a", 7, released));
    LeaseIdentity current{ true, 91, "a", 7 };
    assert(AllowsDiagnosticCleanup(91, "a", 7, current));
    LeaseIdentity foreign{ true, 91, "b", 9 };
    assert(!AllowsDiagnosticCleanup(91, "a", 7, foreign));
    LeaseIdentity staleAttempt{ true, 91, "a", 6 };
    assert(!AllowsDiagnosticCleanup(91, "a", 7, staleAttempt));
    LeaseIdentity staleEpoch{ true, 90, "a", 7 };
    assert(!AllowsDiagnosticCleanup(91, "a", 7, staleEpoch));

    std::vector<RuntimeIdentity> ambiguous = {
        Runtime("a", 7, 0, 0), Runtime("b", 9, 0, 0) };
    assert(Resolve(91, ambiguous, { Actor(0, 0) }).Status
        == ResolutionStatus::AmbiguousMapInstance);
    Resolution openWorld = Resolve(91, ambiguous,
        { Actor(0, 0, "b", 9) });
    assert(openWorld && openWorld.CohortId == "b");
    assert(Resolve(91, runtimes,
        { Actor(669, 101, "a", 7), Actor(669, 202) }).Status
        == ResolutionStatus::MapInstanceMismatch);

    assert(AllowsConcurrentAdmission(0, 2, 8));
    assert(AllowsConcurrentAdmission(1, 2, 0));
    assert(AllowsConcurrentAdmission(1, 2, 1));
    assert(!AllowsConcurrentAdmission(1, 2, 2));
    assert(!AllowsConcurrentAdmission(2, 2, 1));
    assert(MatchesPendingOwnership("a", 7, "a", 7));
    assert(!MatchesPendingOwnership("a", 7, "b", 7));
    assert(!MatchesPendingOwnership("a", 7, "a", 8));

    struct RuntimeState { bool Active; int Updates; };
    RuntimeState a{ true, 0 }, b{ true, 0 }, c{ false, 0 };
    std::vector<RuntimeState*> registered = { &a, &b, &c };
    std::vector<RuntimeState*> frozen = FreezeActive(registered,
        [](RuntimeState const& runtime) { return runtime.Active; });
    for (RuntimeState* runtime : frozen)
    {
        ++runtime->Updates;
        if (runtime == &a)
        {
            b.Active = false;
            c.Active = true;
        }
    }
    assert(a.Updates == 1 && b.Updates == 1 && c.Updates == 0);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            str(source),
            str(BOT_DIR / "BotWorldPopulationMgrCohortScopeContract.cpp"),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_all_native_callbacks_bind_scope_before_cohort_access() -> None:
    callback_sources = {
        "NotifyBotSpellStarted": "BotWorldPopulationMgrCombatLog.cpp",
        "CancelBotSpellStart": "BotWorldPopulationMgrCombatLog.cpp",
        "NotifyCreatureDeath": "BotWorldPopulationMgrCombatLog.cpp",
        "NotifyBotHeal": "BotWorldPopulationMgrCombatLog.cpp",
        "NotifyNativeCreatureSpellStarted": "BotWorldPopulationMgrCombatLog.cpp",
        "NotifyNativeCreatureSpellLanded": "BotWorldPopulationMgrCombatLog.cpp",
        "NotifyCombatAttackAttempt": "BotWorldPopulationMgrCombatNotifications.cpp",
        "NotifyCombatHeal": "BotWorldPopulationMgrCombatNotifications.cpp",
        "PrepareCombatPeriodicOutcome": "BotWorldPopulationMgrCombatNotifications.cpp",
        "NotifyCombatDamage": "BotWorldPopulationMgrCombatNotifications.cpp",
        "NotifyBotSpellFinished": "BotWorldPopulationMgrSemantic.cpp",
        "NotifyBotItemSpellFinished": "BotWorldPopulationMgrSemantic.cpp",
        "NotifyDragonwrathCopyProcAttempt": "BotWorldPopulationMgrDragonwrath.cpp",
    }
    for method, filename in callback_sources.items():
        text = (BOT_DIR / filename).read_text(encoding="utf-8")
        start = text.index(f"BotWorldPopulationMgr::{method}")
        next_method = text.find("BotWorldPopulationMgr::", start + len(method))
        body = text[start : next_method if next_method >= 0 else len(text)]
        scope = body.index("ScopeCallbackCohort")
        cohort = body.find("Cohort()")
        party = body.find("Party()")
        assert cohort < 0 or scope < cohort
        assert party < 0 or scope < party


def test_scheduler_admission_shutdown_and_magmaw_wiring() -> None:
    cohort = (BOT_DIR / "BotWorldPopulationMgrCohort.cpp").read_text(
        encoding="utf-8"
    )
    update = (BOT_DIR / "BotWorldPopulationMgrUpdate.cpp").read_text(
        encoding="utf-8"
    )
    lifecycle = (BOT_DIR / "BotWorldPopulationMgrLifecycle.cpp").read_text(
        encoding="utf-8"
    )
    magmaw = (BOT_DIR / "BotWorldPopulationMgrMagmawBloodlust.cpp").read_text(
        encoding="utf-8"
    )
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text(encoding="utf-8")
    assert "MaxActiveCohorts = 2" in (
        BOT_DIR / "BotWorldPopulationMgr.h"
    ).read_text(encoding="utf-8")
    assert "AllowsConcurrentAdmission(activeCohorts" in cohort
    assert "_selectedCohortId = previous;\n    return started;" in cohort
    assert "FreezeActive(registeredCohorts" in update
    assert "ScopeCohort(runtime)" in update
    assert "void BotWorldPopulationMgr::UpdateCohort" in update
    assert "void BotWorldPopulationMgr::ShutdownCohort" in lifecycle
    assert "ScopeCohort(runtime)" in lifecycle
    shutdown = lifecycle.split(
        "void BotWorldPopulationMgr::ShutdownCohort()", 1
    )[1].split("bool BotWorldPopulationMgr::SpawnAutonomyBots", 1)[0]
    assert "if (!Cohort().Active)\n        return;" not in shutdown
    assert "bool const wasActive = Cohort().Active;" in shutdown
    assert shutdown.index("LeaseOwnedByCurrentCohort") < shutdown.index(
        "BotRaidAreaAuthority::Clear"
    )
    assert "ReleaseCohortLeases();" in shutdown
    assert "Party() = PartyRuntime();" in shutdown
    assert lifecycle.count("AllowsConcurrentAdmission(") >= 2
    assert "std::string const cohortId = Cohort().Id;" in magmaw
    header = (BOT_DIR / "BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    assert "_runningCohortId" not in header + cohort + magmaw
    assert "BotWorldPopulationMgrCohortScope.cpp" in cmake
    assert "BotWorldPopulationMgrCohortScopeContract.cpp" in cmake
