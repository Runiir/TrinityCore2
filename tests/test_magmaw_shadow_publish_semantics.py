from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrEncounterBlackboard.cpp"


def test_shadow_cache_preserves_legacy_snapshot_refresh_order() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    body = text[text.index("void BotWorldPopulationMgr::PublishEncounterBlackboard") :]
    fast_path = (
        "if (Cohort().EncounterSnapshot && nowMs < "
        "Cohort().EncounterSnapshotNextRefreshMs)\n        return;"
    )
    assert body.index(fast_path) < body.index("Player* observer = nullptr;")
    assert body.index("if (!observer)") < body.index(
        "auto snapshot = std::make_shared<BotEncounter::Blackboard>();"
    )
    assert body.index("Cohort().MagmawFacts.reset();") < body.index(
        "auto snapshot = std::make_shared<BotEncounter::Blackboard>();"
    )
    assert body.index("MagmawFactsCache::ForSnapshot") > body.index(
        "BotEncounterHazards::Populate(*snapshot"
    )
    assert "currentScope.EncounterEpoch = 0;" in body
    assert "currentScope.EncounterEpoch = Cohort().Raid.BossResetGeneration" not in body
    refresh_prefix = body[: body.index("Player* observer = nullptr;")]
    assert "MagmawFacts" not in refresh_prefix
