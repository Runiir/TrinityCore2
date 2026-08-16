from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
UNIT = ROOT / "src/server/game/Entities/Unit/Unit.cpp"

WINDOW_RE = re.compile(
    r'\{\s*"(?P<phase>[^"]+)",\s*'
    r'(?P<start>\d+),\s*(?P<end>\d+),\s*(?P<health>\d+),\s*'
    r'(?P<lower>\d+),\s*(?P<lower_inclusive>true|false),\s*'
    r'(?P<upper>\d+),\s*(?P<upper_inclusive>true|false)\s*\}'
)


def _windows(source: str) -> list[dict[str, int | str | bool]]:
    initializer = source.split(
        "CalibrationExecuteHealthWindows = {{", 1
    )[1].split("}};", 1)[0]
    rows: list[dict[str, int | str | bool]] = []
    for match in WINDOW_RE.finditer(initializer):
        row: dict[str, int | str | bool] = {
            "phase": match.group("phase"),
            "start": int(match.group("start")),
            "end": int(match.group("end")),
            "health": int(match.group("health")),
            "lower": int(match.group("lower")),
            "lower_inclusive": match.group("lower_inclusive") == "true",
            "upper": int(match.group("upper")),
            "upper_inclusive": match.group("upper_inclusive") == "true",
        }
        rows.append(row)
    return rows


def _phase_at(rows: list[dict[str, int | str | bool]], elapsed_ms: int) -> dict:
    return next(row for row in rows if elapsed_ms < int(row["end"]))


def _inside_gate(row: dict[str, int | str | bool]) -> bool:
    health = int(row["health"])
    lower = int(row["lower"])
    upper = int(row["upper"])
    lower_ok = health >= lower if row["lower_inclusive"] else health > lower
    upper_ok = health <= upper if row["upper_inclusive"] else health < upper
    return lower_ok and upper_ok


def test_exact_wowsims_single_target_health_schedule_and_boundaries() -> None:
    source = WORLD.read_text(encoding="utf-8")
    rows = _windows(source)

    assert [
        (row["phase"], row["start"], row["end"], row["health"])
        for row in rows
    ] == [
        ("above_90", 0, 30_000, 95),
        ("between_35_90", 30_000, 195_000, 50),
        ("between_25_35", 195_000, 225_000, 30),
        ("between_20_25", 225_000, 240_000, 22),
        ("below_20", 240_000, 300_000, 19),
    ]
    assert rows[0]["start"] == 0
    assert rows[-1]["end"] == 300_000
    assert all(left["end"] == right["start"] for left, right in zip(rows, rows[1:]))
    assert all(_inside_gate(row) for row in rows)

    assert _phase_at(rows, 0)["phase"] == "above_90"
    assert _phase_at(rows, 29_999)["phase"] == "above_90"
    assert _phase_at(rows, 30_000)["phase"] == "between_35_90"
    assert _phase_at(rows, 194_999)["phase"] == "between_35_90"
    assert _phase_at(rows, 195_000)["phase"] == "between_25_35"
    assert _phase_at(rows, 225_000)["phase"] == "between_20_25"
    assert _phase_at(rows, 240_000)["phase"] == "below_20"
    assert _phase_at(rows, 299_999)["phase"] == "below_20"


def test_health_schedule_is_fixture_only_and_records_raw_target_reads() -> None:
    source = WORLD.read_text(encoding="utf-8")
    manager_update = source.split(
        "void BotWorldPopulationMgr::Update(uint32 diff)", 1
    )[1].split(
        "bool BotWorldPopulationMgr::CurrentCombatResOwnerUsable", 1
    )[0]
    schedule = source.split(
        "void BotWorldPopulationMgr::UpdateCalibrationTargetHealthSchedule(uint64 nowMs)", 1
    )[1].split("void BotWorldPopulationMgr::UpdateCalibrationBot", 1)[0]
    assert 'Cohort().CalibrationMode != "single_target_300"' in schedule
    assert "Cohort().RuntimeMode != BotWorldRuntimeMode::CalibrationFixture" in schedule
    assert "Cohort().NonCertifyingAssistance" in schedule
    assert "windowElapsedMs >= CalibrationSingleTargetDurationMs" in schedule
    assert "target->SetHealth(desiredHealth)" in schedule
    assert "uint64 const observedHealth = target->GetHealth()" in schedule
    assert "uint64 const observedMaxHealth = target->GetMaxHealth()" in schedule
    assert "TargetHealthPhaseObservations[phaseIndex]" in schedule
    assert manager_update.index("UpdateCalibrationTargetHealthSchedule(NowMs());") < (
        manager_update.index("UpdateCalibrationControlledDamage();")
    )
    assert manager_update.index("UpdateCalibrationTargetHealthSchedule(NowMs());") < (
        manager_update.index("UpdateCalibrationBot(*itr, diff);")
    )
    assert "windowElapsedMs >= 240000" not in schedule


def test_damage_between_schedule_updates_is_observed_before_health_mutation() -> None:
    source = WORLD.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")
    notify = source.split(
        "void BotWorldPopulationMgr::NotifyCombatDamage", 1
    )[1].split("void BotWorldPopulationMgr::NotifyCombatHeal", 1)[0]

    assert "primaryTargetDamage" in notify
    assert notify.index("UpdateCalibrationTargetHealthSchedule(nowMs);") < notify.index(
        "uint64 const preDamageHealth = victim->GetHealth()"
    )
    assert "CalibrationExecuteHealthWindowIndex(windowElapsedMs)" in notify
    assert "uint64 const preDamageHealth = victim->GetHealth()" in notify
    assert "preDamageHealth - damage" in notify
    assert "DamageEventSampleCount" in notify
    assert "MinimumProjectedPostDamageHealth" in notify
    assert "MinimumDamageEventMaxHealth" in notify
    callback = unit.index("sBotWorldPopulationMgr->NotifyCombatDamage")
    applied_damage = unit.index("victim->ModifyHealth(-(int32)damage)", callback)
    assert callback < applied_damage


def test_damage_scoring_uses_the_same_half_open_300s_boundary() -> None:
    source = WORLD.read_text(encoding="utf-8")
    notify = source.split(
        "void BotWorldPopulationMgr::NotifyCombatDamage", 1
    )[1].split("void BotWorldPopulationMgr::NotifyCombatHeal", 1)[0]

    assert "windowElapsedMs < CalibrationSingleTargetDurationMs" in notify
    assert "windowElapsedMs >= CalibrationSingleTargetDurationMs" in notify
    assert "calibration boundary damage excluded" in notify
    assert "++Cohort().CalibrationExcludedBoundaryDamageEventCount" in notify
    assert notify.index("windowElapsedMs < CalibrationSingleTargetDurationMs") < (
        notify.index("calibration->second.Damage += measuredDamage")
    )
    assert notify.index("++Cohort().CalibrationExcludedBoundaryDamageEventCount") < (
        notify.index("++Cohort().CalibrationCrossWindowEventCount")
    )
    assert notify.index("++Cohort().CalibrationCrossWindowEventCount") < (
        notify.index("calibration->second.Damage += measuredDamage")
    )
    boundary_branch = notify.split(
        "windowElapsedMs >= CalibrationSingleTargetDurationMs", 1
    )[1].split("CalibrationWindowComplete", 1)[0]
    assert "CalibrationExcludedBoundaryDamageEventCount" in boundary_branch
    assert "CalibrationCrossWindowEventCount" not in boundary_branch
    assert "<= 300000" not in notify
    scored = lambda elapsed_ms: elapsed_ms < 300_000
    assert scored(299_999) is True
    assert scored(300_000) is False


def test_status_exposes_reconstructable_observations_without_a_pass_flag() -> None:
    source = WORLD.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    status = source.split(
        "std::string BotWorldPopulationMgr::GetCombatCalibrationJson() const", 1
    )[1].split(
        "void BotWorldPopulationMgr::EnsureCalibrationPopulation", 1
    )[0]

    assert "std::array<TargetHealthPhaseObservation, 5>" in header
    assert "minimum_observed_health" in status
    assert "maximum_observed_health" in status
    assert "minimum_observed_max_health" in status
    assert "maximum_observed_max_health" in status
    assert "first_elapsed_ms" in status
    assert "last_elapsed_ms" in status
    assert "sample_count" in status
    assert "damage_event_sample_count" in status
    assert "minimum_pre_damage_health" in status
    assert "minimum_projected_post_damage_health" in status
    assert "minimum_damage_event_max_health" in status
    assert "maximum_damage_event" in status
    assert "source_execute_proportions" in status
    assert '\\"90\\":0.9,\\"35\\":0.35,\\"25\\":0.25,\\"20\\":0.2' in status
    assert "execute_schedule_passed" not in status
    assert "all_windows_observed" not in status
