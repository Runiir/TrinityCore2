from __future__ import annotations

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
OBSERVER = BOT_DIR / "BotWorldPopulationMgrEncounterHazards.cpp"
PLANNER = (
    BOT_DIR
    / "Content/Raids/Shared/Trash/BotAdaptiveRaidHazardPlanner.cpp"
)
PLANNER_HEADER = (
    BOT_DIR
    / "Content/Raids/Shared/Trash/BotAdaptiveRaidHazardPlanner.h"
)
GEOMETRY = BOT_DIR / "BotWorldPopulationMgrValidationHazards.cpp"
KERNEL = BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_shared_observer_captures_native_hazard_sources_and_expiry() -> None:
    observer = OBSERVER.read_text(encoding="utf-8")
    assert len(observer.splitlines()) < 1000
    for marker in (
        "DynamicObject",
        "AreaTrigger",
        "GAMEOBJECT_TYPE_TRAP",
        "trap.radius",
        "IsTrigger",
        "UNIT_FLAG_NOT_SELECTABLE",
        "GetSpellId",
        "GetDuration",
        "GetRadius",
        "board.Regions",
        "RegionGeneration",
    ):
        assert marker in observer
    assert "std::vector<Player*> const& observers" in observer
    assert "for (Player* observer : observers)" in observer
    assert "std::unique(board.Regions.begin()" in observer
    assert "BotWorldPopulationMgrEncounterHazards.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )


def test_blackboard_passes_all_same_map_cohort_observers() -> None:
    blackboard = (BOT_DIR / "BotWorldPopulationMgrEncounterBlackboard.cpp").read_text(
        encoding="utf-8"
    )
    assert "std::vector<Player*> hazardObservers" in blackboard
    assert "hazardObservers.push_back(candidate)" in blackboard
    assert "BotEncounterHazards::Populate(*snapshot, hazardObservers, nowMs)" in blackboard
    assert "break;" not in blackboard[blackboard.index("Player* observer"):
        blackboard.index("if (!observer)")]


def test_shared_observer_filters_only_known_friendly_sources() -> None:
    observer = OBSERVER.read_text(encoding="utf-8")
    for marker in (
        "IsKnownFriendlyToEveryObserver",
        "dynamicObject->GetCaster()",
        "gameObject->GetOwner()",
        "creature->GetCharmerOrOwner()",
        "observer->IsFriendlyTo(reactionSource)",
        "reactionSource->IsFriendlyTo(observer)",
    ):
        assert marker in observer

    dynamic_branch = observer[observer.index("if (DynamicObject* dynamicObject"):
        observer.index("else if (AreaTrigger* areaTrigger")]
    area_trigger_branch = observer[observer.index("else if (AreaTrigger* areaTrigger"):
        observer.index("else if (GameObject* gameObject")]
    assert "IsKnownFriendlyToEveryObserver" in dynamic_branch
    # AreaTrigger has no stored caster in this core and must remain unknown.
    assert "IsKnownFriendlyToEveryObserver" not in area_trigger_branch


def test_shared_planner_uses_bounded_deterministic_fan_and_strict_path_gate() -> None:
    planner = PLANNER.read_text(encoding="utf-8")
    geometry = GEOMETRY.read_text(encoding="utf-8")
    kernel = KERNEL.read_text(encoding="utf-8")
    assert len(planner.splitlines()) < 1000
    assert len(PLANNER_HEADER.read_text(encoding="utf-8").splitlines()) < 1000
    for marker in (
        "float(M_PI_4)",
        "-float(M_PI_4)",
        "float(M_PI_2)",
        "-float(M_PI_2)",
        "PositionsOutside",
        "PathOutside",
        "CandidateSelected",
        "PathRejected",
        "Owner::Hazard",
        "Priority::Hazard",
        "ScopeKey",
        "EventGeneration",
    ):
        assert marker in planner or marker in geometry or marker in kernel
    assert "PATHFIND_INCOMPLETE" in geometry
    assert "PATHFIND_SHORTCUT" in geometry
    assert "PATHFIND_FARFROMPOLY" in geometry


def test_fan_is_stable_and_requires_the_union_endpoint_to_be_safe() -> None:
    offsets = (0.0, math.pi / 4.0, -math.pi / 4.0, math.pi / 2.0, -math.pi / 2.0)
    bot = (0.0, 0.0)
    hazards = ((2.0, 0.0, 4.0),)
    base_angle = math.pi
    escape_distance = max(
        4.0,
        *(
            max(0.0, radius - math.hypot(hx - bot[0], hy - bot[1])) + 2.0
            for hx, hy, radius in hazards
            if math.hypot(hx - bot[0], hy - bot[1]) <= radius
        ),
    )

    def outside_union(x: float, y: float) -> bool:
        return all(math.hypot(x - hx, y - hy) > radius for hx, hy, radius in hazards)

    endpoints = [
        (
            bot[0] + escape_distance * math.cos(base_angle + offset),
            bot[1] + escape_distance * math.sin(base_angle + offset),
        )
        for offset in offsets
    ]
    assert escape_distance == 4.0
    assert all(math.hypot(x - bot[0], y - bot[1]) <= 4.0 for x, y in endpoints)
    assert all(outside_union(x, y) for x, y in endpoints)


def test_overlapping_hazards_skip_unsafe_first_fan_candidate() -> None:
    offsets = (0.0, math.pi / 4.0, -math.pi / 4.0, math.pi / 2.0, -math.pi / 2.0)
    bot = (0.0, 0.0)
    # The bot is in the first hazard. The second overlaps its edge but does
    # not contain the bot, so the aggregate away vector points at its center.
    # The first fan endpoint is unsafe and +45 degrees is selected.
    hazards = ((3.0, 0.0, 5.0), (-4.0, 0.0, 3.0))
    distances = [math.hypot(hx - bot[0], hy - bot[1]) for hx, hy, _ in hazards]
    escape_distance = max(
        4.0,
        *(max(0.0, radius - distance) + 2.0
          for (_, _, radius), distance in zip(hazards, distances)
          if distance <= radius),
    )
    base_angle = math.pi

    def outside_union(x: float, y: float) -> bool:
        return all(math.hypot(x - hx, y - hy) > radius for hx, hy, radius in hazards)

    endpoints = [
        (
            bot[0] + escape_distance * math.cos(base_angle + offset),
            bot[1] + escape_distance * math.sin(base_angle + offset),
        )
        for offset in offsets
    ]
    safe_indexes = [index for index, endpoint in enumerate(endpoints)
        if outside_union(*endpoint)]
    assert escape_distance == 4.0
    assert math.hypot(*endpoints[0]) <= 4.0
    assert not outside_union(*endpoints[0])
    assert safe_indexes[0] == 1
    assert endpoints[1] == endpoints[safe_indexes[0]]
