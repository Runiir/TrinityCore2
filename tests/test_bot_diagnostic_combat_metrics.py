from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
STATUS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrStatus.cpp"
METRICS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatMetrics.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_diagnose_embeds_bounded_combat_metrics() -> None:
    status = STATUS.read_text(encoding="utf-8")
    assert '",\\\"combat_metrics\\\":" << BuildCombatMetricsJson()' in status
    assert "std::string BuildCombatMetricsJson() const;" in HEADER.read_text(
        encoding="utf-8"
    )
    assert "Bots/BotWorldPopulationMgrCombatMetrics.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )


def test_metrics_match_post_run_active_combat_denominator() -> None:
    source = METRICS.read_text(encoding="utf-8")
    for contract in (
        "bot_combat_metrics_v1",
        "active_party_damage_seconds",
        "Party().ValidationRouteGeneration",
        "CombatLogPerspective::DamageDone",
        "CombatLogPerspective::HealingDone",
        "partyDamageSeconds.size()",
        "active_party_damage_seconds",
        "party_dps",
        "party_hps",
        "pet_damage",
        "pet_damage_included_in_owner",
    ):
        assert contract in source


def test_metrics_module_stays_small_and_separate_from_diagnosis_policy() -> None:
    source = METRICS.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 200
    assert "BuildBotDiagnosis" not in source
