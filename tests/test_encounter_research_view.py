import pytest
from tools.raid_program.encounter_research_view import project


def test_absent_coverage_does_not_claim_completion():
    result = project({"unresolved": []})
    assert result["coverage_present"] is False
    assert result["warning"]


def test_claim_projection_preserves_conflict_and_exact_sources():
    ledger = {"values": [{"key": "hooks", "source_refs": ["client"], "value": 3}],
              "unresolved": [{"key": "hooks", "source_refs": ["guide"], "value": 1}],
              "source_catalog": [{"id": "client"}, {"id": "guide"}, {"id": "unrelated"}]}
    result = project(ledger, "hooks")
    assert set(result["claims"]) == {"values", "unresolved"}
    assert result["sources"] == [{"id": "client"}, {"id": "guide"}]
    with pytest.raises(ValueError, match="Unknown claim"):
        project(ledger, "hook_typo")


def test_claim_projection_tolerates_string_rows_and_a_dict_source_catalog():
    # Omnotron/Atramedes/Maloriak ledgers: unresolved holds bare key strings, source_catalog is keyed by id.
    ledger = {"values": [{"key": "hooks", "source_refs": ["client"], "value": 3}],
              "unresolved": ["hooks", "heroic_cadence"],
              "source_catalog": {"client": {"kind": "db2"}, "unrelated": {"kind": "guide"}}}
    result = project(ledger, "hooks")
    assert set(result["claims"]) == {"values"}
    assert result["sources"] == [{"kind": "db2", "id": "client"}]
    listed = project({"values": [{"key": "hooks", "source_refs": ["client"]}],
                      "source_catalog": [{"id": "client"}, {"id": "unrelated"}]}, "hooks")
    assert listed["sources"] == [{"id": "client"}]
