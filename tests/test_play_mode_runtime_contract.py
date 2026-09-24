from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_play_mode_is_default_off() -> None:
    # worldserver.conf.dist is hash-pinned by tracked_runtime_config_derivation
    # (TEMPLATE_SHA256), so the key stays out of it: absent means off, and
    # only the play launcher sets it.
    dist = _read(ROOT / "src/server/worldserver/worldserver.conf.dist")
    assert "BotWorld.PlayMode.Enable" not in dist
    config = _read(BOTS / "BotWorldPopulationMgrConfig.cpp")
    assert 'GetBoolDefault("BotWorld.PlayMode.Enable", false)' in config
    assert "bool PlayModeEnable = false;" in _read(BOTS / "BotWorldPopulationMgrConfig.h")


def test_cohorts_default_to_validation_and_nothing_starts_play_yet() -> None:
    contracts = _read(BOTS / "BotWorldPopulationMgrRuntimeContracts.h")
    assert "CohortPurpose Purpose = CohortPurpose::Validation;" in contracts
    # Phase 1 is inert for validation: no runtime path can select Play.
    writers = [
        path.relative_to(ROOT).as_posix()
        for path in BOTS.rglob("*")
        if path.suffix in {".h", ".cpp"}
        and path.name != "BotCohortPurpose.h"
        and re.search(r"Purpose\s*=\s*CohortPurpose::Play", _read(path))
    ]
    assert writers == []


def test_status_and_diagnose_publish_purpose_and_duty_plan() -> None:
    status = _read(BOTS / "BotWorldPopulationMgrStatus.cpp")
    assert '\\"cohort_purpose\\":\\"" << CohortPurposeName(Cohort().Purpose)' in status
    assert '\\"play_mode_enabled\\":' in status
    assert "BuildMagmawDutyPlanStatusJson(" in status
    diagnosis = _read(BOTS / "BotWorldPopulationMgrDiagnosis.cpp")
    assert '\\"cohort_purpose\\":\\"" << CohortPurposeName(Cohort().Purpose)' in diagnosis


def test_external_members_stay_out_of_duty_selectors() -> None:
    blackboard = _read(BOTS / "BotEncounterBlackboard.h")
    assert "std::vector<ActorSnapshot> ExternalPlayers;" in blackboard
    # FindActor searches external members last, so bot, hostile, summon and
    # interactable lookups keep their precedence.
    assert blackboard.index("findIn(Interactables)") < blackboard.index(
        "findIn(ExternalPlayers)"
    )
    magmaw = BOTS / "Content/Raids/BlackwingDescent/Encounters/Magmaw"
    readers = [
        path.name
        for path in magmaw.rglob("*")
        if path.suffix in {".h", ".cpp"} and "ExternalPlayers" in _read(path)
    ]
    assert readers == []
