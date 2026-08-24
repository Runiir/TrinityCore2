from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
RECOVERY = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.cpp"
RUNTIME = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidRuntime.cpp"
DIAGNOSTIC = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeSpacingDiagnostic.h"
ROUTE_STATE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRouteState.h"


def test_first_spacing_failure_is_structured_bounded_and_scope_reset(tmp_path) -> None:
    source = tmp_path / "drudge_spacing_diagnostic.cpp"
    binary = tmp_path / "drudge_spacing_diagnostic"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeSpacingDiagnostic.h"

#include <cassert>

int main()
{
    using namespace BotRaidDrudgeGeometry;
    using namespace BotRaidDrudgeSpacing;

    Scope firstScope{11, 2, 7, 669, 14, 250140, 250141};
    Failure failure;
    PredicateEvidence first{
        30003, 1, -303.373f, -49.9592f, 30007, 2.75f, "cached",
        true, true, true, false, false };
    assert(RecordFirstFailure(failure, firstScope, first, 1787582537490));
    assert(failure.Recorded);
    assert(failure.Scope == firstScope);
    assert(failure.MemberGuid == 30003);
    assert(failure.CandidateIndex == 1);
    assert(failure.CandidateX == -303.373f);
    assert(failure.CandidateY == -49.9592f);
    assert(failure.SameLanePeerGuid == 30007);
    assert(failure.SameLanePeerDistance == 2.75f);
    assert(failure.PeerCoordinateSource == "cached");
    assert(failure.Source0Safe && failure.Source1Safe && failure.LaneSafe);
    assert(!failure.SameLaneSpacingSafe && !failure.GroupPositionSafe);
    assert(failure.FirstFailedPredicate == "same_lane_spacing_safe");

    PredicateEvidence later = first;
    later.CandidateIndex = 2;
    later.CandidateX = -301.0f;
    later.SameLanePeerGuid = 30009;
    assert(!RecordFirstFailure(failure, firstScope, later, 1787582538490));
    assert(failure.SuppressedCount == 1);
    assert(failure.CandidateIndex == 1);
    assert(failure.SameLanePeerGuid == 30007);

    Scope secondScope{11, 3, 7, 669, 14, 250140, 250141};
    PredicateEvidence sourceFailure{
        30004, 0, -310.0f, -48.0f, 0, 0.0f, "none",
        false, true, true, true, false };
    assert(RecordFirstFailure(failure, secondScope, sourceFailure, 1787582540000));
    assert(failure.Scope == secondScope);
    assert(failure.SuppressedCount == 0);
    assert(failure.MemberGuid == 30004);
    assert(failure.FirstFailedPredicate == "source0_safe");
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/common"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_spacing_failure_reuses_charge_observation_trace_and_stays_bounded() -> None:
    geometry = GEOMETRY.read_text(encoding="utf-8")
    recovery = RECOVERY.read_text(encoding="utf-8")
    spacing = (DIAGNOSTIC.parent / "BotWorldPopulationMgrValidationRouteDrudgeSpacing.cpp").read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")
    diagnostic = DIAGNOSTIC.read_text(encoding="utf-8")
    route_state = ROUTE_STATE.read_text(encoding="utf-8")
    for field in (
        "member_guid",
        "candidate_index",
        "candidate_x",
        "candidate_y",
        "same_lane_peer_guid",
        "same_lane_peer_distance",
        "peer_coordinate_source",
        "source0_safe",
        "source1_safe",
        "lane_safe",
        "same_lane_spacing_safe",
        "group_position_safe",
    ):
        assert field in runtime
    assert "FirstSpacingFailure" in runtime
    assert '<< ",\\"first_spacing_failure\\":{\\"recorded\\":"' in runtime
    assert '<< ",\\"first_spacing_failure\\":{"recorded\\":"' not in runtime
    assert "EvaluateRecoveryCandidateSpacing" in recovery
    assert "EvaluateAndRecordCandidateSpacing" in geometry
    assert "RecordFirstFailure" in spacing
    assert "FirstSpacingFailure" in route_state
    assert "RecordFirstFailure" in diagnostic
    assert len(diagnostic.splitlines()) < 200
    assert len(GEOMETRY.read_text(encoding="utf-8").splitlines()) <= 999
