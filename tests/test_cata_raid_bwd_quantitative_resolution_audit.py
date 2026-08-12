from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "experiments/configs/cata_raid_bwd_quantitative_resolution_audit_v1.json"
LEDGER_DIR = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"

EXPECTED = {
    "atramedes",
    "chimaeron",
    "magmaw",
    "maloriak",
    "nefarian",
    "omnotron_defense_system",
}
CLASSES = {
    "resolvable_from_client_rows",
    "resolvable_from_server_db_source",
    "resolvable_from_official_cutoff_docs",
    "still_requires_exact_4.4.2_logs_or_authoritative_hotfix_evidence",
}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def ledger_keys(ledger: dict) -> set[str]:
    keys: set[str] = set()
    for item in ledger["unresolved"]:
        keys.add(item if isinstance(item, str) else item["key"])
    return keys


def test_bwd_quantitative_resolution_audit_reconciles_all_52_ledger_blockers() -> None:
    report = load(REPORT)
    bosses = report["bosses"]
    assert {boss["boss_slug"] for boss in bosses} == EXPECTED

    findings = [finding for boss in bosses for finding in boss["blockers"]]
    assert len(findings) == report["scope"]["blocker_count"] == 52
    assert len({(boss["boss_slug"], finding["key"]) for boss in bosses for finding in boss["blockers"]}) == 52

    for boss in bosses:
        slug = boss["boss_slug"]
        ledger_path = ROOT / boss["ledger_path"]
        ledger = load(ledger_path)
        assert boss["ledger_unresolved_material_count"] == ledger["unresolved_material_count"]
        assert len(boss["blockers"]) == ledger["unresolved_material_count"]
        assert {finding["key"] for finding in boss["blockers"]} == ledger_keys(ledger)
        for finding in boss["blockers"]:
            assert finding["original_status"] in {"fidelity_blocked", "unresolved"}
            assert finding["resolution_class"] in CLASSES
            assert finding["resolution_state"]
            assert finding["remaining_gap"]
            assert finding["evidence_refs"]
            for evidence_ref in finding["evidence_refs"]:
                assert evidence_ref in report["evidence_catalog"]

    counts = Counter(finding["resolution_class"] for finding in findings)
    assert counts == {
        "resolvable_from_official_cutoff_docs": 6,
        "resolvable_from_client_rows": 3,
        "resolvable_from_server_db_source": 6,
        "still_requires_exact_4.4.2_logs_or_authoritative_hotfix_evidence": 37,
    }
    assert report["resolution_counts"]["total_blockers"] == 52
    for key, count in counts.items():
        assert report["resolution_counts"][key] == count


def test_bwd_quantitative_resolution_audit_pins_identity_and_fails_closed() -> None:
    report = load(REPORT)
    identity = report["target_identity"]
    assert identity["patch"] == "4.4.2"
    assert identity["client_build"] == 59185
    assert identity["hotfix_cutoff_utc"] == "2025-02-20T23:00:00Z"
    assert identity["client_extract_pointer"].endswith(
        "phase0_client_spell_rows_442_59185_20260812.json.dvc"
    )
    assert identity["client_extract_dvc_md5"] == "eff38325fc3aeac0fa15d0c81b2be901"

    catalog = report["evidence_catalog"]
    assert "SpellDuration.ID=468 Duration=26000 MaxDuration=26000" in " ".join(
        catalog["client_reroute"]["rows"]
    )
    assert "SpellEffect.ID=94853 SpellID=91307 EffectAura=3 EffectAuraPeriod=1000 EffectBasePoints=2000" in " ".join(
        catalog["client_mocking_shadows"]["rows"]
    )
    assert catalog["warcraftlogs_gap"]["row_or_field"] == "status=unresolved_no_pinned_reports"
    assert report["gate"]["authoritative_4_4_2_quantitative_acceptance"] is False
    assert report["gate"]["no_values_promoted_to_ledgers"] is True
    assert report["resolution_counts"]["fully_resolved_retail_fidelity_claims"] == 0
