"""Native contracts behind parallel boss shards (full-raid round 1, package B).

Up to six cohorts share one worldserver: Cohort() needs an explicit scope,
legacy commands scope the default cohort, process-wide mutations are refused
while cohorts run, inserted row IDs never come from another pooled connection,
unkeyed learning is frozen for shard runs, and per-cohort encounter ledgers are
dropped when a cohort stops.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
COMMANDS = ROOT / "src/server/scripts/Commands"
MAGMAW = BOTS / "Content/Raids/BlackwingDescent/Encounters/Magmaw"
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]
# Public methods that act on "the" cohort without naming it. Outside the
# manager they may only run inside ScopeCohortById (the legacy default cohort,
# or the sole registered cohort resolved by ResolveGlobalAutoCohort).
LEGACY_UNQUALIFIED = (
    "Start", "Stop", "StartAutonomy", "StopAutonomy", "SpawnAutonomyBots",
    "StartCombatCalibration", "StopCombatCalibration", "GetCombatCalibrationJson",
    "GetRuntimeProfilesJson", "SelectRuntimeProfile", "ClearRuntimeProfile",
    "ReloadRuntimeProfiles", "PrepareValidationProfile", "GetStatus", "GetStatusJson",
    "GetSummaryJson", "GetBotDebugJson", "GetBotDiagnosisJson", "GetBotTraceJson",
    "GetCombatLogJson", "GetCombatLogDeltaJson", "Replay", "CompareBrains",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function(text: str, signature: str) -> str:
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(f"unterminated {signature}")


def _handlers(text: str) -> dict[str, str]:
    names = re.findall(r"static bool (Handle\w+)\(ChatHandler\* handler", text)
    return {name: _function(text, f"static bool {name}(") for name in names}


def test_capacity_is_six_and_admission_stays_serialized() -> None:
    api = _read(BOTS / "BotWorldPopulationMgrCohortScopeApi.h")
    assert "static constexpr uint32 MaxActiveCohorts = 6;" in api
    assert 'static constexpr char const* DefaultCohortId = "default";' in api
    contract = _read(BOTS / "BotWorldPopulationMgrCohortScopeContract.cpp")
    admission = _function(contract, "bool AllowsConcurrentAdmission(")
    assert "activeCohorts >= maximumActiveCohorts" in admission
    assert "activeCohorts == 0 || mapWorkerThreads <= 1" in admission
    cohort = _read(BOTS / "BotWorldPopulationMgrCohort.cpp")
    registry = _function(cohort, "std::string BotWorldPopulationMgr::GetCohortRegistryJson() const")
    for field in ("max_active_cohorts", "map_worker_threads", "concurrent_admission_open", "shard_isolation"):
        assert f'\\"{field}\\"' in registry
    ownership = _function(cohort, "std::string BotWorldPopulationMgr::GetCohortIsolationContractJson()")
    # The Phase 5 contract builder requires this check name; it now means "at least two".
    assert '{ "two_active_cohorts_supported", MaxActiveCohorts >= 2 }' in ownership
    assert '{ "shard_active_cohorts_supported", MaxActiveCohorts >= 6 }' in ownership
    assert "ScopeCohort(&first)" in ownership and "ScopeCohort(&second)" in ownership


def test_cohort_state_requires_an_explicit_scope() -> None:
    cohort = _read(BOTS / "BotWorldPopulationMgrCohort.cpp")
    for signature in ("BotWorldPopulationMgr::CohortRuntime& BotWorldPopulationMgr::Cohort()",
                      "BotWorldPopulationMgr::CohortRuntime const& BotWorldPopulationMgr::Cohort() const"):
        body = _function(cohort, signature)
        assert "if (!_scopedCohort)" in body and "ABORT_MSG(" in body
        assert "_cohorts" not in body
    members = _read(BOTS / "BotWorldPopulationMgrCohortScopeMembers.h")
    assert "static thread_local CohortRuntime* _scopedCohort;" in members
    assert "_selectedCohortId" not in members and "SelectCohort" not in members
    # No caller outside the manager can start autonomy without naming a cohort.
    assert "bool StartAutonomy(BotWorldExperimentConfig const* overrideConfig = nullptr);" in members
    header = _read(BOTS / "BotWorldPopulationMgr.h")
    assert '#include "Bots/BotWorldPopulationMgrCohortScopeApi.h"' in header
    assert '#include "Bots/BotWorldPopulationMgrCohortScopeMembers.h"' in header
    assert "class BotWorldPopulationMgr::CohortScope final" in header
    assert "bool StartAutonomy(" not in header
    # Every cohort-qualified wrapper binds its scope before touching state.
    for signature in re.findall(r"^\S.*BotWorldPopulationMgr::(\w+ForCohort)\(", cohort, re.MULTILINE):
        body = _function(cohort, f"BotWorldPopulationMgr::{signature}(")
        scope = min(body.find("ScopeCohortById(cohortId)"), body.find("ScopeCohort(runtime)"),
                    key=lambda value: value if value >= 0 else 1 << 30)
        assert scope < (1 << 30), signature
        for access in ("Cohort()", "Party()"):
            if access in body:
                assert scope < body.index(access), signature
    scope_cpp = _read(BOTS / "BotWorldPopulationMgrCohortScope.cpp")
    by_id = _function(scope_cpp, "BotWorldPopulationMgr::CohortScope BotWorldPopulationMgr::ScopeCohortById(")
    assert "nullptr" in by_id  # an unknown cohort yields an empty scope, never another cohort


def test_manager_translation_units_have_no_selected_cohort() -> None:
    owned = [BOTS / name for name in (
        "BotWorldPopulationMgr.h", "BotWorldPopulationMgrCohort.cpp", "BotWorldPopulationMgrCohortScope.cpp",
        "BotWorldPopulationMgrLifecycle.cpp", "BotWorldPopulationMgrUpdate.cpp", "BotWorldPopulationMgrPlay.cpp",
        "BotWorldPopulationMgrCohortScopeApi.h", "BotWorldPopulationMgrCohortScopeMembers.h")]
    for path in owned:
        text = _read(path)
        assert "_selectedCohortId" not in text, path.name
        assert "SelectCohort(" not in text, path.name
    play = _read(BOTS / "BotWorldPopulationMgrPlay.cpp")
    for signature in ("std::string Context::Fill(", "std::string Context::Go(", "std::string Context::Status("):
        assert "mgr.ScopeCohort(cohort)" in _function(play, signature), signature


def test_whole_tree_has_no_selected_cohort_after_patch_requests() -> None:
    """Fails until the coordinator applies package B's patch_requests.

    The checkpoint and trace-pressure modules (not owned by package B) still
    swap the removed member; the build fails on them for the same reason.
    """
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src/server").rglob("*"))
        if path.suffix in {".cpp", ".h"} and "_selectedCohortId" in _read(path)
    ]
    assert offenders == []


def test_botauto_commands_scope_every_unqualified_call() -> None:
    handlers = _handlers(_read(COMMANDS / "cs_botauto.cpp"))
    pattern = re.compile(r"sBotWorldPopulationMgr->(" + "|".join(LEGACY_UNQUALIFIED) + r")\(")
    checked = 0
    for name, body in handlers.items():
        for match in pattern.finditer(body):
            scope = body.find("ScopeCohortById(")
            assert 0 <= scope < match.start(), (name, match.group(1))
            checked += 1
    assert checked >= 12


def test_external_legacy_callers_scope_the_default_cohort() -> None:
    """cs_healerbot's BotWorld.AutoStart path needs its patch request applied."""
    pattern = re.compile(r"sBotWorldPopulationMgr->(" + "|".join(LEGACY_UNQUALIFIED) + r")\(")
    offenders = []
    for path in sorted((ROOT / "src/server").rglob("*.cpp")):
        if path.parent == BOTS or BOTS in path.parents:
            continue
        text = _read(path)
        for match in pattern.finditer(text):
            window = text[max(0, match.start() - 1500):match.start()]
            if "ScopeCohortById(" not in window:
                offenders.append(f"{path.relative_to(ROOT)}:{text.count(chr(10), 0, match.start()) + 1}:{match.group(1)}")
    assert offenders == []


def test_process_wide_mutations_refused_while_cohorts_run() -> None:
    handlers = _handlers(_read(COMMANDS / "cs_botauto.cpp"))
    rotations = handlers["HandleAutoRotationsCommand"]
    guard = rotations.index('(tokens[0] == "reload" || tokens[0] == "rollback") && sBotWorldPopulationMgr->IsActive()')
    assert guard < rotations.index("ReloadDbProfiles()") and guard < rotations.index("RollbackDbProfiles()")
    assert "active_cohorts_present" in rotations
    for name, action, default_only in (("HandleStartCommand", "botexp_start", False),
                                       ("HandleReplayCommand", "botexp_replay", False),
                                       ("HandleCompareBrainCommand", "botexp_comparebrain", False),
                                       ("HandleStopCommand", "botexp_stop", True)):
        body = handlers[name]
        call = f'RefuseWhileCohortsActive(handler, "{action}"' + (", true)" if default_only else ")")
        assert call in body, name
        assert body.index(call) < body.index("ScopeCohortById(")
    refuse = _function(_read(COMMANDS / "cs_botauto.cpp"), "static bool RefuseWhileCohortsActive(")
    assert "HasActiveCohortOtherThan(BotWorldPopulationMgr::DefaultCohortId)" in refuse
    assert "GetActiveCohortCount()" in refuse
    # Read-only heartbeat commands (.botexp summary/status) stay available.
    for name in ("HandleSummaryCommand", "HandleStatusCommand"):
        assert "RefuseWhileCohortsActive" not in handlers[name]


def test_inserted_ids_are_read_back_by_the_owning_bot() -> None:
    for name, table in (("BotExperimentCoordinator.cpp", "experiment_bot_segments"),
                        ("BotTelemetryBuffer.cpp", "experiment_bot_clips")):
        text = _read(BOTS / name)
        assert 'Query("SELECT LAST_INSERT_ID()")' not in text, name
        assert f"SELECT MAX(id) FROM {table} WHERE bot_guid = %u" in text, name
        assert f"SELECT id FROM {table} WHERE bot_guid = %u AND id > " in text, name
        insert = text.index(f"INSERT INTO {table}")
        high_water = text.index("HighWaterId(", text.index("uint64 const highWaterId"))
        assert high_water < insert, name
    segments = _read(BOTS / "BotExperimentCoordinator.cpp")
    assert "parent_run_id <=> %s" in segments and "status = 'running'" in segments
    clips = _read(BOTS / "BotTelemetryBuffer.cpp")
    assert "run_id = \" UI64FMTD \" AND status = 'open'" in clips


def test_learning_and_semantic_writes_freeze_under_shard_isolation() -> None:
    policy = _read(BOTS / "BotExperienceLearningPolicy.cpp")
    assert 'sConfigMgr->GetBoolDefault("BotWorld.ShardIsolation", false)' in policy
    scores = re.findall(r"BotLearnedScore BotExperienceLearningPolicy::(Score\w+)\(", policy)
    assert len(scores) == 7
    for name in scores:
        body = _function(policy, f"BotLearnedScore BotExperienceLearningPolicy::{name}(")
        assert "if (!LearningEnabled(config) ||" in body.splitlines()[2], name
        assert "config.Enabled" not in body, name
    assert "!config.Enabled" not in policy
    local = _function(policy, "float LocalDanger(")
    assert "GlobalMemoryFallbackAllowed(config)" in local and "config.AllowGlobalMemoryFallback" not in local
    semantic = _read(BOTS / "BotWorldPopulationMgrSemantic.cpp")
    for signature in ("void BotWorldPopulationMgr::UpdateSemanticOutcomeStats(",
                      "void BotWorldPopulationMgr::UpdateSemanticStatsFromEvent("):
        body = _function(semantic, signature)
        assert body.index("ShardIsolationEnabled()") < body.index("UpdateSemanticOutcomeStats(bot" if "FromEvent" in signature
                                                                  else "INSERT INTO bot_semantic_outcome_stats")
    # Default unchanged: the key is absent from shipped configs (off).
    for config in (ROOT / "trinity-worldserver-test.conf", ROOT / "src/server/worldserver/worldserver.conf.dist"):
        assert "BotWorld.ShardIsolation" not in _read(config)


def test_stopping_a_cohort_drops_its_encounter_ledgers() -> None:
    lifecycle = _read(BOTS / "BotWorldPopulationMgrLifecycle.cpp")
    release = _function(lifecycle, "void BotWorldPopulationMgr::ReleaseCohortEncounterState()")
    assert "MagmawBaiterRotationRegistry::ClearCohort(Cohort().Id)" in release
    stop = _function(lifecycle, "void BotWorldPopulationMgr::Stop()")
    assert stop.rstrip("}").rstrip().endswith("ReleaseCohortEncounterState();")
    autonomy = _function(lifecycle, "void BotWorldPopulationMgr::StopAutonomy()")
    assert autonomy.rstrip("}").rstrip().endswith("ReleaseCohortEncounterState();")
    shutdown = _function(lifecycle, "void BotWorldPopulationMgr::ShutdownCohort()")
    assert shutdown.rstrip("}").rstrip().endswith("ReleaseCohortEncounterState();")


BAITER_PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBaiterRotation.h"
#include <cstdio>
#include <string>

using namespace BotEncounter;

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

static ActorSnapshot Player(uint32 guid, char const* role, char const* spec)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Kind = ActorKind::Player;
    player.Role = role;
    player.ClassSpec = spec;
    player.Position = { 30.0f, 0.0f, 210.0f };
    player.HealthPct = 100.0f;
    player.Alive = true;
    return player;
}

static Blackboard Board(char const* cohort, uint32 instance)
{
    Blackboard board;
    board.CurrentScope = Scope{ cohort, 7, 0, 4, "bwd.magmaw.encounter", 669, instance, "magmaw" };
    board.Revision = 21;
    board.ObservedAtMs = 1790220781549;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Players = {
        Player(30001, "dps", "balance_druid"), Player(30002, "tank", "blood_death_knight"),
        Player(30003, "healer", "restoration_druid"), Player(30004, "healer", "holy_paladin"),
        Player(30005, "healer", "discipline_priest"), Player(30006, "dps", "fire_mage"),
        Player(30007, "dps", "fire_mage"), Player(30008, "dps", "affliction_warlock"),
        Player(30009, "dps", "survival_hunter"), Player(30010, "dps", "elemental_shaman"),
    };
    return board;
}

int main()
{
    using Registry = MagmawBaiterRotationRegistry;
    Blackboard const first = Board("blackwing_descent_10n_magmaw_c0", 101);
    Blackboard const second = Board("blackwing_descent_10n_magmaw_c1", 202);
    Registry::ObserveBaiters(first);
    Registry::ObserveBaiters(second);
    if (Registry::CohortCount() != 2)
        return std::fprintf(stderr, "two cohorts expected\n"), 1;
    if (!Registry::Find(first.CurrentScope.Key()) || !Registry::Find(second.CurrentScope.Key()))
        return std::fprintf(stderr, "both ledgers expected\n"), 1;
    Registry::ClearCohort("blackwing_descent_10n_magmaw_c0");
    if (Registry::CohortCount() != 1 || Registry::Find(first.CurrentScope.Key()))
        return std::fprintf(stderr, "stopped cohort still bound\n"), 1;
    if (!Registry::Find(second.CurrentScope.Key()))
        return std::fprintf(stderr, "other shard's ledger was dropped\n"), 1;
    Registry::ClearCohort("unknown_cohort");
    if (Registry::CohortCount() != 1)
        return std::fprintf(stderr, "unknown cohort clear changed the registry\n"), 1;
    return 0;
}
'''


def test_baiter_registry_clear_drops_only_the_stopped_cohort(tmp_path: Path) -> None:
    source = tmp_path / "baiter.cpp"
    binary = tmp_path / "baiter"
    source.write_text(BAITER_PROGRAM, encoding="utf-8")
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


@pytest.mark.parametrize("path", [
    "src/server/game/Bots/BotWorldPopulationMgr.h",
    "src/server/game/Bots/BotWorldPopulationMgrCohortScopeApi.h",
    "src/server/game/Bots/BotWorldPopulationMgrCohortScopeMembers.h",
    "src/server/game/Bots/BotWorldPopulationMgrCohort.cpp",
    "src/server/game/Bots/BotWorldPopulationMgrLifecycle.cpp",
    "src/server/game/Bots/BotWorldPopulationMgrPlay.cpp",
    "src/server/game/Bots/BotWorldPopulationMgrSemantic.cpp",
    "src/server/scripts/Commands/cs_botauto.cpp",
])
def test_changed_native_modules_stay_below_the_size_limit(path: str) -> None:
    assert len(_read(ROOT / path).splitlines()) < 1000
