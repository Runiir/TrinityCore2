"""Atramedes ledger: the air-catch parity summary states what the five chases show.

Round-3 fix packet maloriak_release (review v3, P3). The ledger summary claimed the air catch timing matches the
native Building Speed time ramp "within 1 s over five chases", but Aiada's redirected chase was caught at 20.0 s
against 16-17 s predicted. Only the wording is checked here; no claim status changes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/atramedes_ledger_v1.json"
WITHIN_S = 1.0


def load() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def speed_claim(document: dict) -> dict:
    return next(claim for claim in document["unresolved"] if claim["key"] == "breath_speed_scaling_with_sound")


def observed_and_predicted(evidence: str) -> dict[str, tuple[float, tuple[float, float]]]:
    """Chase name -> (observed seconds after Tracking, predicted (low, high)) from the claim's evidence text."""
    observed = {name: float(value) for name, value in re.findall(
        r"(Vahan|Rubælia|Aduktai|Jonson|Aiada)[^.;]*? (\d+(?:\.\d+)?) s(?: \(| after Tracking|,)", evidence)}
    predicted_text = re.search(r"in a straight-line chase predicts ([\d.\-, and]+) s;", evidence)
    assert predicted_text, "the predicted catch times are not stated"
    ranges = []
    for part in re.findall(r"\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?", predicted_text.group(1)):
        low, _, high = part.partition("-")
        ranges.append((float(low), float(high or low)))
    names = ["Vahan", "Rubælia", "Aduktai", "Jonson", "Aiada"]
    assert len(ranges) == 5 and all(name in observed for name in names), (observed, ranges)
    return {name: (observed[name], ranges[index]) for index, name in enumerate(names)}


def outside_s(observed: float, predicted: tuple[float, float]) -> float:
    """Seconds by which the observed catch lies outside the predicted range (0 inside), signed late-positive."""
    low, high = predicted
    return observed - high if observed > high else observed - low if observed < low else 0.0


def test_declared_one_second_air_catch_parity_matches_all_five_rows() -> None:
    document = load()
    claim = speed_claim(document)
    chases = observed_and_predicted(claim["evidence_gap"])
    assert chases["Aiada"][0] == 20.0 and chases["Aiada"][1] == (16.0, 17.0)
    within = [name for name, (seen, predicted) in chases.items() if abs(outside_s(seen, predicted)) <= WITHIN_S]
    exceptions = [name for name in chases if name not in within]
    assert within == ["Vahan", "Rubælia", "Aduktai", "Jonson"] and exceptions == ["Aiada"]
    assert round(outside_s(*chases["Aiada"]), 3) == 3.0  # caught 3.0-4.0 s later than predicted

    known = next(row for row in document["research_completion"] if "Breath targets are random" in row.get("known", ""))["known"]
    assert "within 1 s over five chases" not in known
    assert "within 1 s in four of five chases" in known
    assert "0.0-0.8 s outside the predicted range" in known
    assert round(max(abs(outside_s(*chases[name])) for name in within), 3) == 0.8
    assert "Aiada's redirected chase" in known and "caught later than predicted (20.0 s observed against 16-17 s)" in known
    assert "within 1 s over five chases" not in json.dumps(document)


def test_the_parity_wording_fix_changes_no_claim_status() -> None:
    document = load()
    claim = speed_claim(document)
    assert claim["status"] == "resolved_10n_by_user_bound_other_modes_unobserved"
    assert claim["modes"] == ["10H", "25N", "25H"]
