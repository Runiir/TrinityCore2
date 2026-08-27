from __future__ import annotations

import math
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
DRUDGE = (
    ROOT
    / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
)


def test_seed_combat_envelope_replays_canary35_and_exact_boundary(tmp_path: Path) -> None:
    source = tmp_path / "drudge_combat_envelope.cpp"
    binary = tmp_path / "drudge_combat_envelope"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeCombatEnvelope.h"
#include <cassert>
#include <string>
#include <vector>

int main()
{
    using namespace BotRaidDrudgeCombatEnvelope;
    std::vector<std::uint32_t> seeds{ 8, 6 };
    std::vector<std::uint32_t> laneA{ 1, 3, 4, 6, 7 };
    std::vector<std::uint32_t> laneB{ 2, 5, 8, 9, 10 };
    Point2d source0{ -297.355f, -80.0307f };
    Point2d source1{ -329.248f, -61.8282f };

    assert(!AcceptsConfiguredSeed(8, seeds, laneA, laneB, source0, source1,
        35.0f, { -343.177f, -126.937f }));
    assert(AcceptsConfiguredSeed(8, seeds, laneA, laneB, source0, source1,
        35.0f, { source1.X + 34.99f, source1.Y }));
    assert(!AcceptsConfiguredSeed(8, seeds, laneA, laneB, source0, source1,
        35.0f, { source1.X + 35.01f, source1.Y }));
    assert(AcceptsConfiguredSeed(7, seeds, laneA, laneB, source0, source1,
        35.0f, { -500.0f, -500.0f }));
    assert(AcceptsConfiguredSeed(8, seeds, laneA, laneB, source0, source1,
        35.0f, { -311.5f, -78.0f }));
    assert(std::string(RejectionReason()) == "drudge_anchor_combat_range_unsafe");
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
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_room_side_home_envelope_precedes_cache_and_native_path_admission() -> None:
    geometry = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    group = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGroupSafety.cpp").read_text(
        encoding="utf-8"
    )
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text(encoding="utf-8")

    assert "NonTankEntranceEnvelopeSafe" in group
    envelope = group[group.index("NonTankEntranceEnvelopeSafe("):
                     group.index("ComputeGroupPositionSafe(")]
    assert "DeclaredRecoveryMemberAnchorFor(slot)" in envelope
    assert "source->GetHomePosition()" in envelope
    assert "pointDistance + tolerance < entranceDistance" in envelope
    assert "SourceUnionSafe(x, y)" not in envelope
    assert "AcceptsConfiguredSeed" not in group
    assert group.index("NonTankEntranceEnvelopeSafe(") < group.index(
        "DynamicGroupPositionSafe("
    )
    cache = geometry[geometry.index("auto cacheUsable"):geometry.index("if (cacheUsable())")]
    assert "NonTankEntranceEnvelopeSafe" in cache
    selector = geometry[
        geometry.index("for (size_t candidateIndex = 0;"):
        geometry.index("State.ValidationRouteDrudgeAnchorX =")
    ]
    assert selector.index("combatEnvelopeSafe") < selector.index("SelectAnchorPathSearch")
    assert '"drudge_anchor_combat_range_unsafe"' in selector
    assert selector.index('"drudge_anchor_combat_range_unsafe"') < selector.index(
        "StrictNativePath"
    )
    assert "BotWorldPopulationMgrValidationRouteDrudgeGroupSafety.cpp" in cmake


def test_established_entrance_hold_survives_native_rush_displacement() -> None:
    actions = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )
    group = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGroupSafety.cpp").read_text(
        encoding="utf-8"
    )

    assert "tankStage.InvalidateAnchor && !RecoveryFormationActive" in actions
    assert "rushTargetContractSafe = RecoveryFormationActive" in actions
    assert "entranceFormation || SourceUnionSafeAt(" in group
    assert "NonTankEntranceEnvelopeSafe(" in group


def test_cached_non_tank_anchor_replays_rush_against_home_envelope() -> None:
    geometry = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    cached = geometry[geometry.index("CachedAnchorSafe = [this]"):geometry.index(
        "GroupPositionSafe = [this]"
    )]

    # Canary59 replay: a landed Rush can stand on slot 8's fixed entrance
    # anchor. The live source union rejects that point, while the reviewed
    # source-home envelope accepts it at the same distance as the anchor.
    homes = [(-298.833, -50.349), (-307.913, -49.5694)]
    entrance = (-315.0, -118.0)
    live_sources = [homes[0], entrance]
    stable_home_envelope = lambda point: all(
        math.dist(point, home) + 2.0 >= math.dist(entrance, home)
        for home in homes
    )
    assert any(math.dist(entrance, source) < 15.0 for source in live_sources)
    assert stable_home_envelope(entrance)
    assert not stable_home_envelope((-315.0, -100.0))

    assert 'if (memberRoster->second.Role != "tank")' in cached
    assert "bool const cachedAnchorSafe = IsRecoveryFormationActive()" in cached
    recovery = cached.index("NonTankEntranceEnvelopeSafe(memberSlot,")
    live = cached.index("SourceUnionSafe(anchorState.ValidationRouteDrudgeAnchorX")
    assert recovery < live
    assert "route[nextIndex].TargetEntry != 41570" in geometry


def test_prepull_keeps_non_tanks_at_entrance_and_guards_magmaw() -> None:
    geometry = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp").read_text(
        encoding="utf-8"
    )
    actions = (DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp").read_text(
        encoding="utf-8"
    )

    anchor = geometry[geometry.index("UniqueGroupAnchor ="):geometry.index(
        "AnchorCandidatesFor ="
    )]
    assert "dynamicRecovery || !tankSlot" in anchor
    assert "DeclaredRecoveryMemberAnchorFor(slot)" in anchor
    assert "DeclaredNavigationTankAnchorFor(slot)" in anchor
    assert "route[nextIndex].TargetEntry != 41570" in geometry
    assert "RunDrudgeSeedCoordinator()" not in actions


def test_native_entrance_ownership_uses_simple_balanced_combat_and_safety_movement() -> None:
    lane_selection = (
        DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"
    ).read_text(encoding="utf-8")
    combat = (
        DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeCombat.cpp"
    ).read_text(encoding="utf-8")
    geometry = (
        DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
    ).read_text(encoding="utf-8")

    run = lane_selection[
        lane_selection.index("bool DrudgeLaneContext::Run()"):
        lane_selection.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::BuildContract()")
    ]
    build = run.index("result = BuildAnchorPolicies();")
    established = run.index("if (IsEntrancePullEstablished())")
    pull = run.index("result = RunEntrancePullActions();", established)
    combat_branch = run.index("return RunEntranceCombat() == PhaseResult::Handled;", pull)
    assert build < established < pull < combat_branch
    assert "return RunEntranceCombat() == PhaseResult::Handled;" in run[established:]
    assert "ShouldHoldLowerLane" not in combat
    assert "drudge_kill_sync_hold_lower_health_lane" not in combat
    assert "drudge_tank_health_sync_hold" not in combat
    assert "split_lane_target_switch" in combat
    assert "ResolveProfileCombatAction" in combat
    assert "false, false, true, false, false" in combat
    assert "drudge_entrance_lane_action" in combat
    assert "return PhaseResult::Handled;" in combat
    assert "ordinaryEntranceCombat = IsEntrancePullEstablished()" in geometry
    entrance_guard = geometry.index("if (ordinaryEntranceCombat)")
    assert entrance_guard < geometry.index("moved = Manager.MoveBotToPoint")
    assert "return false;" in geometry[entrance_guard:entrance_guard + 80]
    assert "specializedLaneMovement = drudgeProfile" in geometry
    assert "specializedLaneMovement, exactPrepullStaged" in geometry
    assert "specializedLaneMovement, IsLandedRushPending()" in geometry


def test_established_entrance_maintenance_has_its_native_callbacks_bound() -> None:
    lane_selection = (
        DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"
    ).read_text(encoding="utf-8")
    entrance_pull = (
        DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeEntrancePull.cpp"
    ).read_text(encoding="utf-8")
    geometry = (
        DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
    ).read_text(encoding="utf-8")

    run = lane_selection[
        lane_selection.index("bool DrudgeLaneContext::Run()"):
        lane_selection.index("DrudgeLaneContext::PhaseResult DrudgeLaneContext::BuildContract()")
    ]
    established = run.index("if (IsEntrancePullEstablished())")
    build = run.index("result = BuildAnchorPolicies();")

    # Canary67 entered this branch after both tanks owned their Drudges. The
    # maintenance path invokes these callbacks, so their setup must precede
    # the branch and its first pull action.
    assert build < established
    assert "StrictNativePath(" in entrance_pull
    assert "DeclaredAnchorFor(pullOwnerSlot)" in entrance_pull
    assert geometry.index("StrictNativePath =") >= 0
    assert lane_selection.index("DeclaredAnchorFor =") >= 0


def test_entrance_pull_stacks_at_cleared_chainwielder_position() -> None:
    entrance = (
        DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeEntrancePull.cpp"
    ).read_text(encoding="utf-8")

    assert "static std::array<MemberAnchor, 10> const entranceAnchors" in entrance
    assert "-344.0f, -101.0f" in entrance
    assert "-352.0f, -110.0f" in entrance
    assert "config.ValidationRouteSplitRecoveryMemberAnchors" not in entrance
    assert "DoorwayArrivalToleranceYards = 20.0f" in entrance
    assert entrance.count("DoorwayArrivalToleranceYards)") >= 4
    pull_started = entrance[entrance.index("if (pullStarted)"):]
    assert "IsLandedRushPending()" not in pull_started
    assert pull_started.index("drudge_entrance_return_move") < pull_started.index(
        "drudge_entrance_native_pack_link_wait"
    )


def test_drudge_cpp_files_remain_below_one_thousand_lines() -> None:
    for path in DRUDGE.glob("*.[ch]*"):
        if path.suffix in {".c", ".cc", ".cpp", ".h", ".hpp"}:
            assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path
