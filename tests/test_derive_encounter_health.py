import pytest

from tools.raid_program.derive_encounter_health import COLUMNS, derive


def capture():
    return dict(report="reference", fight=7, mode="10H", actor_id=42,
                url="https://classic.warcraftlogs.com/reports/reference?fight=7",
                columns=COLUMNS, consecutive_no_healing_or_overkill=True,
                initial_full_health=True,
                observations=[["00:01.000", 100, 1.0], ["00:02.000", 200, 3.0],
                              ["00:03.000", 300, 6.0], ["00:04.000", 400, 10.0]])


def test_derivation_uses_consecutive_differences_without_assuming_initial_hp():
    row = capture()
    row["initial_full_health"] = False
    row["observations"][0][1] = 99  # Unknown health before capture must not enter an estimate.
    result = derive(row)
    assert result["derived_max_health"] == 10000
    assert result["estimates"] == [10000, 10000, 10000]
    assert result["target_cutoff_compatibility"] == "not_established_by_this_calculation"


def test_first_full_health_assumption_is_cross_checked():
    row = capture()
    row["observations"][0][1] = 99
    with pytest.raises(ValueError, match="Inconsistent"):
        derive(row)


@pytest.mark.parametrize("percent", [0, 100, float("nan"), float("inf"), True])
def test_rejects_invalid_or_lethal_health_rows(percent):
    row = capture()
    row["observations"][1][2] = percent
    with pytest.raises(ValueError, match="percentage"):
        derive(row)


def test_gap_or_wrong_damage_field_cannot_be_silently_averaged():
    row = capture()
    row["observations"][2][1] += 100
    with pytest.raises(ValueError, match="Inconsistent"):
        derive(row)
    row = capture()
    row["consecutive_no_healing_or_overkill"] = False
    with pytest.raises(ValueError, match="consecutive"):
        derive(row)


def test_rejects_out_of_order_and_insufficient_captures():
    row = capture()
    row["observations"][2][0] = "00:00.500"
    with pytest.raises(ValueError, match="ordered"):
        derive(row)
    row = capture()
    row["observations"] = row["observations"][:2]
    with pytest.raises(ValueError, match="three independent"):
        derive(row)
