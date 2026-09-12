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
