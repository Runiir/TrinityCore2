"""Regression coverage for the declarative BWD recovery entrance binding."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from tools.bot_ml.build_validation_scenario_manifests import build_manifests


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
RUNTIME = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationCohortRuntime.cpp"

BWD_MAP_ID = 669
EXPECTED_RECOVERY_ENTRANCE = (6581, 0, BWD_MAP_ID)


def _configured_scenarios(config: dict) -> list[dict]:
    return list(config.get("scenarios") or []) + list(config.get("diagnostic_scenarios") or [])


def _provisioning_report(config: dict) -> dict:
    """Give the production manifest builder complete role-shaped inputs."""
    rows: dict[str, dict] = {}
    for scenario in _configured_scenarios(config):
        scenario_id = str(scenario["id"])
        provisioning_id = str(scenario.get("provisioning_scenario_id") or scenario_id)
        roles = {str(role): int(count) for role, count in (scenario.get("required_roles") or {}).items()}
        rows[provisioning_id] = {
            "scenario_id": provisioning_id,
            "ready": True,
            "missing": [],
            "role_counts": roles,
        }
    return {"all_ready": True, "scenarios": list(rows.values())}


def _bwd_manifest_rows() -> tuple[list[dict], list[dict]]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifests = build_manifests(
        config,
        _provisioning_report(config),
        {"all_passed": True},
        json.loads(
            (ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    configured_bwd = [
        scenario
        for scenario in _configured_scenarios(config)
        if int(scenario.get("map_id") or 0) == BWD_MAP_ID
    ]
    route_rows = [
        row for row in manifests["validation_routes"] if int(row.get("map_id") or 0) == BWD_MAP_ID
    ]
    return configured_bwd, route_rows


def test_every_generated_bwd_route_carries_the_exact_recovery_entrance() -> None:
    configured_bwd, route_rows = _bwd_manifest_rows()

    assert len(configured_bwd) == 7
    assert {str(scenario["id"]) for scenario in configured_bwd} == {
        str(row["scenario_id"]) for row in route_rows
    }
    assert route_rows

    for row in route_rows:
        assert (
            int(row["recovery_entrance_area_trigger_id"]),
            int(row["recovery_entrance_source_map_id"]),
            int(row["recovery_entrance_target_map_id"]),
        ) == EXPECTED_RECOVERY_ENTRANCE

    first_route = min(
        (row for row in route_rows if row["scenario_id"] == "blackwing_descent_10n"),
        key=lambda row: int(row["step"]),
    )
    assert int(first_route["step"]) == 1
    assert (
        int(first_route["recovery_entrance_area_trigger_id"]),
        int(first_route["recovery_entrance_source_map_id"]),
        int(first_route["recovery_entrance_target_map_id"]),
    ) == EXPECTED_RECOVERY_ENTRANCE


def _production_tracker_segment() -> str:
    source = RUNTIME.read_text(encoding="utf-8")
    start_marker = "    if (raid.WipeGeneration > 0)\n        for (auto& [guid, signal] : raid.NativeSignalsByGuid)"
    end_marker = "\n\n    auto signalComplete"
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    segment = source[start:end]
    for marker in (
        "releaseLandingIdentityBound",
        "progressedFromReleaseLanding",
        "signal.RunbackSequence = ++raid.EvidenceSequence",
        "signal.ReentrySequence = ++raid.EvidenceSequence",
        "signal.ResurrectionSequence = ++raid.EvidenceSequence",
    ):
        assert marker in segment
    return segment


def _compile_tracker_replay(tmp_path: Path, first_route: dict, request) -> Path:
    request.addfinalizer(lambda: shutil.rmtree(tmp_path, ignore_errors=True))
    source = tmp_path / "bwd_recovery_tracker_replay.cpp"
    binary = tmp_path / "bwd_recovery_tracker_replay"
    trigger = int(first_route["recovery_entrance_area_trigger_id"])
    source_map = int(first_route["recovery_entrance_source_map_id"])
    target_map = int(first_route["recovery_entrance_target_map_id"])
    segment = _production_tracker_segment()

    prefix = r'''#include <cassert>
#include <cmath>
#include <cstdint>
#include <map>
#include <vector>

using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

constexpr uint32 kGeneratedRecoveryEntranceAreaTriggerId = '''
    prefix += f"{trigger}u;\n"
    prefix += f"constexpr uint32 kGeneratedRecoveryEntranceSourceMapId = {source_map}u;\n"
    prefix += f"constexpr uint32 kGeneratedRecoveryEntranceTargetMapId = {target_map}u;\n"
    prefix += r'''

struct ObjectGuidStub
{
    uint32 Counter = 0;

    uint32 GetCounter() const
    {
        return Counter;
    }
};

struct WorldBotState
{
    ObjectGuidStub Guid;
    bool NativeReleaseRequested = false;
    uint32 NativeRunbackAreaTriggerId = 0;
    bool NativeReleaseLandingObserved = false;
    uint32 NativeReleaseLandingMapId = 0;
    uint32 NativeReleaseLandingInstanceId = 0;
    uint64 NativeReleaseLandingWipeGeneration = 0;
    float NativeReleaseLandingX = 0.0f;
    float NativeReleaseLandingY = 0.0f;
    float NativeReleaseLandingZ = 0.0f;
};

struct RaidNativeSignalState
{
    bool Initialized = false;
    bool Alive = false;
    bool HasCorpse = false;
    bool Released = false;
    bool OutsideOriginalInstance = false;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    uint64 WipeGeneration = 0;
    uint64 DeathSequence = 0;
    uint64 CorpseSequence = 0;
    uint64 ReleaseSequence = 0;
    uint64 RunbackSequence = 0;
    uint64 ReentrySequence = 0;
    uint64 ResurrectionSequence = 0;
};

struct RaidRuntime
{
    std::map<uint32, RaidNativeSignalState> NativeSignalsByGuid;
    uint32 AdmissionRecoveryEntranceAreaTriggerId = 0;
    uint32 AdmissionRecoveryEntranceSourceMapId = 0;
    uint32 AdmissionRecoveryEntranceTargetMapId = 0;
    uint64 WipeGeneration = 0;
    uint64 EvidenceSequence = 0;
};

struct NativeFrame
{
    uint32 Guid = 0;
    bool Alive = false;
    bool HasCorpse = false;
    bool Released = false;
    bool OutsideOriginalInstance = false;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    uint64 WipeGeneration = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
};

float Distance2d(float ax, float ay, float bx, float by)
{
    float const dx = ax - bx;
    float const dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}

struct PartyState
{
    std::vector<WorldBotState> Bots;
};

class RecoveryTrackerFixture
{
public:
    RaidRuntime raid;
    PartyState party;

    PartyState& Party()
    {
        return party;
    }

    void ObserveNativeFrames(std::vector<NativeFrame> const& frames)
    {
        // The real caller snapshots prior native signals before projecting
        // this tick's observations.  The tracker below is copied verbatim
        // from BotWorldPopulationMgrValidationCohortRuntime.cpp.
        auto const previousNativeSignals = raid.NativeSignalsByGuid;
        for (NativeFrame const& frame : frames)
        {
            RaidNativeSignalState& signal = raid.NativeSignalsByGuid[frame.Guid];
            signal.Initialized = true;
            signal.Alive = frame.Alive;
            signal.HasCorpse = frame.HasCorpse;
            signal.Released = frame.Released;
            signal.OutsideOriginalInstance = frame.OutsideOriginalInstance;
            signal.MapId = frame.MapId;
            signal.InstanceId = frame.InstanceId;
            signal.WipeGeneration = frame.WipeGeneration;
            signal.X = frame.X;
            signal.Y = frame.Y;
            signal.Z = frame.Z;
        }
'''
    suffix = r'''
    }
};

static std::vector<NativeFrame> FrameForAllBots(
    bool alive, bool hasCorpse, bool released, bool outside,
    float x, float y, float z, uint64 wipeGeneration)
{
    std::vector<NativeFrame> frames;
    for (uint32 guid = 1; guid <= 10; ++guid)
        frames.push_back({guid, alive, hasCorpse, released, outside,
            0, 0, wipeGeneration, x, y, z});
    return frames;
}

static RecoveryTrackerFixture ValidFixture(uint32 admissionTrigger,
    uint64 raidWipeGeneration = 7, uint64 landingWipeGeneration = 7,
    uint32 botRunbackTrigger = kGeneratedRecoveryEntranceAreaTriggerId)
{
    RecoveryTrackerFixture fixture;
    fixture.raid.AdmissionRecoveryEntranceAreaTriggerId = admissionTrigger;
    fixture.raid.AdmissionRecoveryEntranceSourceMapId =
        kGeneratedRecoveryEntranceSourceMapId;
    fixture.raid.AdmissionRecoveryEntranceTargetMapId =
        kGeneratedRecoveryEntranceTargetMapId;
    fixture.raid.WipeGeneration = raidWipeGeneration;
    for (uint32 guid = 1; guid <= 10; ++guid)
    {
        WorldBotState bot;
        bot.Guid.Counter = guid;
        bot.NativeReleaseRequested = true;
        bot.NativeRunbackAreaTriggerId = botRunbackTrigger;
        bot.NativeReleaseLandingObserved = true;
        bot.NativeReleaseLandingMapId = 0;
        bot.NativeReleaseLandingInstanceId = 0;
        bot.NativeReleaseLandingWipeGeneration = landingWipeGeneration;
        bot.NativeReleaseLandingX = 10.0f;
        bot.NativeReleaseLandingY = 20.0f;
        bot.NativeReleaseLandingZ = 30.0f;
        fixture.party.Bots.push_back(bot);
    }
    return fixture;
}

static void AssertAllReleased(RecoveryTrackerFixture const& fixture)
{
    assert(fixture.raid.NativeSignalsByGuid.size() == 10);
    for (auto const& row : fixture.raid.NativeSignalsByGuid)
    {
        RaidNativeSignalState const& signal = row.second;
        assert(signal.DeathSequence > 0);
        assert(signal.CorpseSequence > signal.DeathSequence);
        assert(signal.ReleaseSequence > signal.CorpseSequence);
        assert(signal.RunbackSequence == 0);
    }
}

static void AssertAllComplete(RecoveryTrackerFixture const& fixture)
{
    for (auto const& row : fixture.raid.NativeSignalsByGuid)
    {
        RaidNativeSignalState const& signal = row.second;
        assert(signal.DeathSequence < signal.CorpseSequence);
        assert(signal.CorpseSequence < signal.ReleaseSequence);
        assert(signal.ReleaseSequence < signal.RunbackSequence);
        assert(signal.RunbackSequence < signal.ReentrySequence);
        assert(signal.ReentrySequence < signal.ResurrectionSequence);
    }
}

static void ReplayValidRecovery()
{
    RecoveryTrackerFixture fixture = ValidFixture(
        kGeneratedRecoveryEntranceAreaTriggerId);
    assert(kGeneratedRecoveryEntranceSourceMapId == 0);
    assert(kGeneratedRecoveryEntranceTargetMapId == 669);

    // A native release landing is observed, but no movement has happened.
    fixture.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 10.0f, 20.0f, 30.0f, 7));
    AssertAllReleased(fixture);

    // The next native frame is beyond the production two-yard progress gate.
    fixture.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 12.1f, 20.0f, 30.0f, 7));
    for (auto const& row : fixture.raid.NativeSignalsByGuid)
        assert(row.second.RunbackSequence > row.second.ReleaseSequence);

    // Native re-entry and resurrection arrive together in the observed
    // inside/alive frame after the outside ghost progress sample.
    fixture.ObserveNativeFrames(FrameForAllBots(
        true, false, false, false, 12.1f, 20.0f, 30.0f, 7));
    AssertAllComplete(fixture);
}

static void ReplayRejectedRecoveryCases()
{
    // Admission without a trigger keeps the tracker blocked even when the
    // native observations otherwise look like a moved ghost.
    RecoveryTrackerFixture zeroAdmission = ValidFixture(0);
    zeroAdmission.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 10.0f, 20.0f, 30.0f, 7));
    zeroAdmission.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 12.1f, 20.0f, 30.0f, 7));
    for (auto const& row : zeroAdmission.raid.NativeSignalsByGuid)
        assert(row.second.RunbackSequence == 0);

    RecoveryTrackerFixture wrongTrigger = ValidFixture(9999);
    wrongTrigger.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 10.0f, 20.0f, 30.0f, 7));
    wrongTrigger.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 12.1f, 20.0f, 30.0f, 7));
    for (auto const& row : wrongTrigger.raid.NativeSignalsByGuid)
        assert(row.second.RunbackSequence == 0);

    RecoveryTrackerFixture wrongWipe = ValidFixture(
        kGeneratedRecoveryEntranceAreaTriggerId, 8, 7);
    wrongWipe.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 10.0f, 20.0f, 30.0f, 8));
    wrongWipe.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 12.1f, 20.0f, 30.0f, 8));
    for (auto const& row : wrongWipe.raid.NativeSignalsByGuid)
        assert(row.second.RunbackSequence == 0);

    RecoveryTrackerFixture noMovement = ValidFixture(
        kGeneratedRecoveryEntranceAreaTriggerId);
    noMovement.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 10.0f, 20.0f, 30.0f, 7));
    noMovement.ObserveNativeFrames(FrameForAllBots(
        false, true, true, true, 10.0f, 20.0f, 30.0f, 7));
    for (auto const& row : noMovement.raid.NativeSignalsByGuid)
        assert(row.second.RunbackSequence == 0);
}

int main()
{
    ReplayValidRecovery();
    ReplayRejectedRecoveryCases();
    return 0;
}
'''
    source.write_text(prefix + segment + suffix, encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    return binary


def test_compiled_tracker_replays_generated_entrance_across_native_ticks(
    tmp_path: Path, request
) -> None:
    _, route_rows = _bwd_manifest_rows()
    first_route = min(
        (row for row in route_rows if row["scenario_id"] == "blackwing_descent_10n"),
        key=lambda row: int(row["step"]),
    )
    binary = _compile_tracker_replay(tmp_path, first_route, request)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
