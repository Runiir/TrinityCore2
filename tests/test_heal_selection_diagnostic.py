from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def test_heal_selection_diagnostic_is_deterministic_and_bounded(
    tmp_path: Path,
) -> None:
    source = tmp_path / "heal_selection_diagnostic.cpp"
    binary = tmp_path / "heal_selection_diagnostic"
    source.write_text(
        r'''
#include "Bots/BotHealSelectionDiagnostic.h"

#include <iostream>
#include <vector>

int main()
{
    BotHealSelection::Diagnostic outOfRange;
    outOfRange.ActorGuid = 30009;
    outOfRange.TargetGuid = 30001;
    outOfRange.TargetDistance = 44.25f;
    outOfRange.LineOfSight = true;
    outOfRange.InstantOnly = true;
    outOfRange.ProfileClassId = 2;
    outOfRange.ProfileSpecTag = "holy_paladin";
    outOfRange.ProfileRole = "healer";
    outOfRange.ProfileSource = "db_rotation_profile";
    outOfRange.ProfileGeneration = 17;
    outOfRange.ProfileContentHash = "profile-sha";
    outOfRange.HealingCandidateCount = 1;
    outOfRange.SetRejections({ { 20473, "out_of_range" } });
    std::cout << outOfRange.ToJson() << '\n';

    std::vector<BotHealSelection::Rejection> descending;
    for (std::uint32_t spellId = 1020; spellId-- > 1000;)
        descending.push_back({ spellId, "out_of_range" });
    descending.push_back({ 1000, "out_of_range" });
    descending.push_back({ 0, "ignored" });
    descending.push_back({ 1001, "" });

    BotHealSelection::Diagnostic bounded;
    bounded.HealingCandidateCount = 20;
    bounded.SetRejections(descending);
    std::string const firstJson = bounded.ToJson();

    BotHealSelection::Diagnostic reordered;
    reordered.HealingCandidateCount = 20;
    reordered.SetRejections(std::vector<BotHealSelection::Rejection>(
        descending.rbegin(), descending.rend()));
    if (firstJson != reordered.ToJson())
        return 2;
    std::cout << firstJson << '\n';

    BotHealSelection::Diagnostic selected;
    selected.ActorGuid = 30009;
    selected.TargetGuid = 30001;
    selected.TargetDistance = 18.75f;
    selected.LineOfSight = false;
    selected.InstantOnly = false;
    selected.ProfileClassId = 2;
    selected.ProfileSpecTag = "holy_paladin";
    selected.ProfileRole = "healer";
    selected.ProfileSource = "db_rotation_profile";
    selected.ProfileGeneration = 19;
    selected.ProfileContentHash = "selected-profile-sha";
    selected.SelectedSpellId = 20473;
    selected.HealingCandidateCount = 2;
    selected.SetRejections({ { 19750, "target_health_gate" } });
    BotHealSelection::CastFailureReceipt const lineOfSightFailure =
        BotHealSelection::MakeCastFailureReceipt(
            selected, "line_of_sight");
    std::cout << lineOfSightFailure.RetryReason << '\t'
              << lineOfSightFailure.DetailJson << '\n';
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
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
    output = subprocess.run(
        [str(binary)], check=True, cwd=ROOT, capture_output=True, text=True
    ).stdout.splitlines()
    assert len(output) == 3

    out_of_range = json.loads(output[0])
    assert out_of_range["schema"] == "bot_heal_selection_diagnostic_v1"
    assert out_of_range["actor_guid"] == 30009
    assert out_of_range["target_guid"] == 30001
    assert out_of_range["target_distance"] == 44.25
    assert out_of_range["line_of_sight"] is True
    assert out_of_range["instant_only"] is True
    assert out_of_range["profile"] == {
        "class_id": 2,
        "spec_tag": "holy_paladin",
        "role": "healer",
        "source": "db_rotation_profile",
        "generation": 17,
        "content_hash": "profile-sha",
    }
    assert out_of_range["selection"]["summary_reason"] == "out_of_range"
    assert out_of_range["selection"]["rejections"] == [
        {"spell_id": 20473, "reason": "out_of_range"}
    ]
    assert "no_trained_heal" not in output[0]

    bounded = json.loads(output[1])["selection"]
    assert bounded["summary_reason"] == "out_of_range"
    assert bounded["unique_rejection_count"] == 20
    assert bounded["unique_reason_count"] == 1
    assert bounded["reported_rejection_count"] == 16
    assert bounded["omitted_rejection_count"] == 4
    assert [item["spell_id"] for item in bounded["rejections"]] == list(
        range(1000, 1016)
    )

    retry_reason, selected_detail_json = output[2].split("\t", 1)
    assert retry_reason == "line_of_sight"
    selected_detail = json.loads(selected_detail_json)
    assert selected_detail == {
        "schema": "bot_heal_selection_diagnostic_v1",
        "actor_guid": 30009,
        "target_guid": 30001,
        "target_distance": 18.75,
        "line_of_sight": False,
        "instant_only": False,
        "profile": {
            "class_id": 2,
            "spec_tag": "holy_paladin",
            "role": "healer",
            "source": "db_rotation_profile",
            "generation": 19,
            "content_hash": "selected-profile-sha",
        },
        "selection": {
            "selected_spell_id": 20473,
            "summary_reason": "selected",
            "healing_candidate_count": 2,
            "unique_rejection_count": 1,
            "unique_reason_count": 1,
            "reported_rejection_count": 1,
            "omitted_rejection_count": 0,
            "rejections": [
                {"spell_id": 19750, "reason": "target_health_gate"}
            ],
        },
    }


def test_adaptive_heal_resolve_records_typed_selection_detail() -> None:
    support = (BOTS / "BotWorldPopulationMgrCombatSupport.cpp").read_text(
        encoding="utf-8"
    )
    candidates = (
        BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
    ).read_text(encoding="utf-8")
    diagnostics = (
        BOTS / "BotWorldPopulationMgrCombatDiagnostics.cpp"
    ).read_text(encoding="utf-8")
    state = (BOTS / "BotWorldPopulationMgrBotState.h").read_text(encoding="utf-8")

    selection = _function_body(
        support, "uint32 BotWorldPopulationMgr::SelectHealSpell("
    )
    for observed_field in (
        "ActorGuid",
        "TargetGuid",
        "TargetDistance",
        "LineOfSight",
        "InstantOnly",
        "ProfileSpecTag",
        "ProfileRole",
        "ProfileSource",
        "ProfileGeneration",
        "ProfileContentHash",
    ):
        assert f"selectionDiagnostic->{observed_field}" in selection
    assert "candidate.RejectReason" in selection
    assert "selectionDiagnostic->SetRejections" in selection

    resolve_start = candidates.index("BotHealSelection::Diagnostic healSelection;")
    resolve = candidates[resolve_start : resolve_start + 2200]
    assert "BotHealSelection::Diagnostic healSelection;" in resolve
    assert "&healSelection" in resolve
    assert "healSelection.SummaryReason()" in resolve
    assert "healSelection.ToJson()" in resolve
    assert "selectionJson.c_str()" in resolve
    # The diagnostic label changes, but the existing retry outcome remains
    # untouched so this observation-only patch cannot change arbitration.
    assert '"no_instant_heal_while_moving"' in resolve
    assert '"no_trained_heal"' in resolve

    cast_failure_start = candidates.index(
        "BotHealSelection::CastFailureReceipt const failure ="
    )
    cast_failure = candidates[cast_failure_start : cast_failure_start + 1000]
    assert "MakeCastFailureReceipt(" in cast_failure
    assert "healSelection" in cast_failure
    assert '"heal_cast_retryable"' in cast_failure
    assert "failure.RetryReason.c_str(), nullptr" in cast_failure
    assert "failure.DetailJson.c_str()" in cast_failure
    assert "Outcome::Retryable(\n                            failure.RetryReason)" in cast_failure

    assert 'std::string DetailJson = "{}";' in state
    assert "std::string DiagnosticReason;" in state
    assert '<< ",\\"detail\\":"' in diagnostics
    assert '<< ",\\"retry_reason\\":\\""' in diagnostics
    assert "diagnostic.DetailJson = detailJson" in diagnostics
