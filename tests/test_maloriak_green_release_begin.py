"""Maloriak 10N Green Release Aberrations begin: the native draw covers every observed first begin.

Round-3 fix packet maloriak_release (2026-09-30). The first round-3 closure kept the Green Release at a fixed 9 s
and omitted a canceled Begin Cast 6.415 s after Slime Imbued (7PT6hQ3wBqXmdtcH fight 49). EVENT_RELEASE_ABERRATIONS
fires when the 1.5 s cast begins, so every observed first Release after Slime Imbued is compared as a begin: a Begin
Cast row is a begin as logged (canceled ones included), a Cast row is a begin after subtracting the 1.5 s cast.
"""

from __future__ import annotations

import json
import re
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENCOUNTER = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"
LEDGER = ENCOUNTER / "maloriak_ledger_v1.json"
CONTRACT = ENCOUNTER / "maloriak_v1.json"
ROUND2 = ENCOUNTER / "maloriak_wcl_boss_timelines_round2_v1.json"
FIGHT13 = ENCOUNTER / "maloriak_wcl_cast_timelines_fight13_v1.json"
AUDIT = ROOT / "experiments/configs/cata_raid_bwd_quantitative_resolution_audit_v1.json"
DOSSIER = ROOT / "docs/bot_raids/strategies/t11/blackwing_descent/maloriak.md"
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
SHARED = SCRIPTS / "boss_maloriak_shared.h"
BOSS = SCRIPTS / "boss_maloriak.cpp"
ARCHIVES = ROOT / "artifacts/cata_raid_program"
POST_ARCHIVE = ARCHIVES / "wcl_round3_maloriak_bwd10n_20260930.tar.gz"
POST_MEMBER = "wcl_r3fix/maloriak_r3fix.json"
CENSUS_ARCHIVE = ARCHIVES / "wcl_round3_captures_bwd10n_20260930.tar.gz"

RELEASE_CAST_S = 1.5  # Spell.dbc 77569 (1500 ms)
# A Release cast row this close after its Begin Cast row completes that begin; a later one is a begin of its own.
PAIR_WINDOW_S = 2.0
# The first row of one of these after Slime Imbued ends the Green phase (phase two, or the next vial's throw).
PHASE_END = {"Release All Minions", "Throw Red Bottle", "Throw Blue Bottle", "Throw Black Bottle",
             "Fire Imbued", "Frost Imbued"}
POST_CUTOFF = "wcl_maloriak_10n_post_cutoff_20260930"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def archive_json(archive: Path, member: str) -> dict:
    if not archive.exists():
        pytest.skip(f"{archive.name} is a DVC artifact that is not hydrated here (dvc pull)")
    with tarfile.open(archive) as tar:
        handle = tar.extractfile(member)
        assert handle is not None, member
        return json.load(handle)


def shared_constant(name: str) -> int:
    match = re.search(rf"constexpr uint32 {name} = (\d+);", SHARED.read_text(encoding="utf-8"))
    assert match, name
    return int(match.group(1))


def ledger_release() -> dict:
    row = next((value for value in load(LEDGER)["values"] if value["key"] == "green_release_begins_10N"), None)
    assert row is not None, "the ledger has no green_release_begins_10N row table"
    return row


def green_phases(report: str, fight: int, rows: list[tuple[float, str, str, bool]], period: str) -> list[dict]:
    """Every Green phase of one kill: its Slime Imbued time, the Release begins in it (first = the draw), and the
    phase-two begin when no Release began. `rows` are (t, kind, ability, canceled), kind Begin Cast or Cast."""
    phases = []
    for imbue in sorted(t for t, _, ability, _ in rows if ability == "Slime Imbued"):
        ends = [t for t, _, ability, _ in rows if ability in PHASE_END and t > imbue]
        end = min(ends) if ends else float("inf")
        begins: list[dict] = []
        for t, kind, ability, canceled in rows:
            if ability != "Release Aberrations" or not imbue < t < end:
                continue
            if kind == "Cast" and begins and begins[-1]["row_type"] == "Begin Cast" \
                    and t - begins[-1]["row_s"] <= PAIR_WINDOW_S:
                begins[-1]["completed"] = True
                continue
            begin = round(t - imbue - (RELEASE_CAST_S if kind == "Cast" else 0.0), 3)
            begins.append({"report": report, "fight": fight, "period": period, "imbue_s": imbue, "row_type": kind,
                           "row_s": t, "canceled": canceled, "begin_s": begin, "completed": False})
        phase_two = None
        if not begins:
            minions = [(t, kind) for t, kind, ability, _ in rows if ability == "Release All Minions" and t > imbue]
            if minions:
                t, kind = min(minions)
                phase_two = t - (RELEASE_CAST_S if kind == "Cast" else 0.0)
        phases.append({"report": report, "fight": fight, "period": period, "imbue_s": imbue, "begins": begins,
                       "phase_two_begin_s": phase_two})
    return phases


def round2_phases() -> list[dict]:
    phases = []
    for fight in load(ROUND2)["fights"]:
        rows = [(e["t"], e["type"], e["ability"], False) for e in fight["events"]]
        phases += green_phases(fight["report"], fight["fight"], rows, "pre_cutoff")
    return phases


def fight13_phases() -> list[dict]:
    rows = [(e["t"], e["event"], e["ability"], False) for e in load(FIGHT13)["boss_timeline"]]
    return green_phases("VL3fW9wNm2PRJDYt", 13, rows, "pre_cutoff")


def post_cutoff_phases() -> list[dict]:
    capture = archive_json(POST_ARCHIVE, POST_MEMBER)
    phases = []
    for fight in capture["part_b"] + capture["part_b_supplemental"]:
        rows = [(e["t"], e.get("event_type") or "Cast", e["ability"], bool(e.get("canceled")))
                for e in fight["boss_casts"] if e.get("event_type") != "Apply Debuff"]
        phases += green_phases(fight["report"], fight["fight"], rows, "post_cutoff")
    return phases


def census_phases() -> list[dict]:
    """The two long pre-cutoff kills (NYcJZtHd6baDC41p 28, cDQCyb4B71Wj9dV8 15) with a vial after Green."""
    census = archive_json(CENSUS_ARCHIVE, "maloriak_wcl_r3/resultG.json")
    phases = []
    for fight in census["fourth_vial"]:
        rows = [(e["t"], e["type"], e["ability"], bool(e.get("canceled"))) for e in fight["rows"]]
        phases += green_phases(fight["report"], fight["fight"], rows, "pre_cutoff")
    return phases


def key(row: dict) -> tuple:
    return row["report"], row["fight"]


def test_green_release_draw_is_the_exact_span_of_every_first_begin() -> None:
    """The constants are the minimum and maximum of the ledger's first Release begins over both periods, unrounded
    (both bounds are Begin Cast rows); the span includes the canceled 6.415 s begin the first closure omitted."""
    release = ledger_release()
    rows = release["rows"]
    assert {row["period"] for row in rows} == {"pre_cutoff", "post_cutoff"}
    assert sum(row["period"] == "pre_cutoff" for row in rows) == 4 and sum(row["period"] == "post_cutoff" for row in rows) == 4
    for row in rows:
        shift = RELEASE_CAST_S if row["row_type"] == "Cast" else 0.0
        assert row["begin_s"] == round(row["row_s"] - row["imbue_s"] - shift, 3), row
        assert not (row["row_type"] == "Cast" and row["canceled"]), row  # a canceled cast is only a Begin Cast row

    lowest = min(rows, key=lambda row: row["begin_s"])
    highest = max(rows, key=lambda row: row["begin_s"])
    assert (lowest["report"], lowest["begin_s"], lowest["row_type"], lowest["canceled"]) == (
        "7PT6hQ3wBqXmdtcH", 6.415, "Begin Cast", True)
    assert (highest["report"], highest["begin_s"], highest["row_type"]) == ("NYcJZtHd6baDC41p", 10.505, "Begin Cast")
    assert release["bounds_s"] == {"min": 6.415, "max": 10.505}
    assert shared_constant("GREEN_RELEASE_10N_MIN_MS") == round(lowest["begin_s"] * 1000) == 6415
    assert shared_constant("GREEN_RELEASE_10N_MAX_MS") == round(highest["begin_s"] * 1000) == 10505
    # Canceled Begin Cast rows are begins like any other: all three are in the table and inside the drawn span.
    canceled = sorted(row["begin_s"] for row in rows if row["canceled"])
    assert canceled == [6.415, 8.888, 9.312]
    assert all(shared_constant("GREEN_RELEASE_10N_MIN_MS") <= round(value * 1000) <= shared_constant("GREEN_RELEASE_10N_MAX_MS")
               for value in (row["begin_s"] for row in rows))
    # The storm range ends before it, so the draw never puts the Release ahead of the storm.
    assert shared_constant("GREEN_STORM_10N_MAX_MS") < shared_constant("GREEN_RELEASE_10N_MIN_MS")
    # The repeat begins follow the repeat timer, not the draw: each is 17-18 s after a first begin of its kill.
    first = {key(row): row["begin_s"] for row in rows}
    for repeat in release["repeats"]:
        gap = repeat["begin_s"] - first[key(repeat)]
        assert 17.0 <= gap <= 18.0 or repeat["report"] == "cDQCyb4B71Wj9dV8", repeat  # cDQC waited for a storm channel


def test_pre_cutoff_rows_match_the_repository_timelines() -> None:
    """The pre-cutoff rows recomputed from the round-2 and fight-13 capture files in the repository: every Green
    phase that logged a Release has its first begin in the ledger (including the 7.299 s round-2 row that the old
    7.7-10.5 s range left out) and every phase without one is recorded as censored."""
    release = ledger_release()
    by_key = {key(row): row for row in release["rows"]}
    censored = {key(row): row for row in release["censored"]}
    computed = round2_phases() + fight13_phases()
    assert {key(phase) for phase in computed} == {
        ("XzVpNLkxaAFG3DjW", 18), ("3pvXdMVntcjxygW4", 13), ("hmAcWCt3njMR4HFT", 12), ("VL3fW9wNm2PRJDYt", 13)}
    for phase in computed:
        if phase["begins"]:
            first = phase["begins"][0]
            row = by_key[key(phase)]
            assert (row["row_type"], row["row_s"], row["begin_s"], row["imbue_s"]) == (
                first["row_type"], first["row_s"], first["begin_s"], first["imbue_s"]), key(phase)
            assert key(phase) not in censored
        else:
            assert round(phase["phase_two_begin_s"] - phase["imbue_s"], 3) == censored[key(phase)]["no_release_begin_before_s"]
            assert key(phase) not in by_key
    assert by_key[("3pvXdMVntcjxygW4", 13)]["begin_s"] == 7.299


def test_post_cutoff_rows_match_the_raw_capture_including_canceled_begins() -> None:
    """The post-cutoff rows recomputed from the raw capture (report 7PT6hQ3wBqXmdtcH fight 49 and four more kills):
    every first Release in a Green phase is a ledger row, canceled Begin Cast rows included."""
    release = ledger_release()
    by_key = {key(row): row for row in release["rows"] if row["period"] == "post_cutoff"}
    censored = {key(row): row for row in release["censored"] if row["period"] == "post_cutoff"}
    computed = post_cutoff_phases()
    assert len(computed) == 5
    canceled_seen = []
    for phase in computed:
        if not phase["begins"]:
            assert round(phase["phase_two_begin_s"] - phase["imbue_s"], 3) == censored[key(phase)]["no_release_begin_before_s"]
            continue
        first = phase["begins"][0]
        row = by_key[key(phase)]
        assert (row["row_type"], row["row_s"], row["begin_s"], row["canceled"], row["imbue_s"]) == (
            first["row_type"], first["row_s"], first["begin_s"], first["canceled"], first["imbue_s"]), key(phase)
        canceled_seen += [begin["begin_s"] for begin in phase["begins"] if begin["canceled"]]
        # Later Release rows of the phase are the repeat timer's, and each is in the ledger's repeats.
        for later in phase["begins"][1:]:
            assert any(key(repeat) == key(phase) and repeat["begin_s"] == later["begin_s"]
                       and repeat["canceled"] == later["canceled"] for repeat in release["repeats"]), later
    assert len(by_key) == 4 and len(censored) == 1
    assert 6.415 in canceled_seen and by_key[("7PT6hQ3wBqXmdtcH", 49)]["canceled"] is True
    assert min(row["begin_s"] for row in by_key.values()) == 6.415


def test_census_rows_match_the_round3_captures_and_the_canceled_label() -> None:
    """The two long pre-cutoff kills (Begin Cast rows 7.666 and 10.505 s) and the Begin Cast of VL3fW9wNm2PRJDYt
    fight 13 that the round-3 census displayed as Canceled."""
    release = ledger_release()
    by_key = {key(row): row for row in release["rows"]}
    computed = {key(phase): phase for phase in census_phases()}
    assert set(computed) == {("NYcJZtHd6baDC41p", 28), ("cDQCyb4B71Wj9dV8", 15)}
    for phase in computed.values():
        first, row = phase["begins"][0], by_key[key(phase)]
        assert (row["row_type"], row["row_s"], row["begin_s"], row["imbue_s"]) == (
            first["row_type"], first["row_s"], first["begin_s"], first["imbue_s"]), key(phase)
        for later in phase["begins"][1:]:
            assert any(key(repeat) == key(phase) and repeat["begin_s"] == later["begin_s"] for repeat in release["repeats"])
    census = archive_json(CENSUS_ARCHIVE, "maloriak_wcl_r3/resultB.json")
    assert any("Release Aberrations begin at 134.010 is displayed as Canceled" in note for note in census["limitations"])
    assert by_key[("VL3fW9wNm2PRJDYt", 13)]["canceled"] is True and by_key[("VL3fW9wNm2PRJDYt", 13)]["row_s"] == 134.01


def test_the_written_closure_states_the_drawn_release_range_everywhere() -> None:
    """Ledger, contract, audit row and dossier name the Release draw and no longer claim a fixed 9 s Release or the
    old 7.7-10.5 s pre-cutoff range; the omitted canceled begin is recorded."""
    ledger, contract = load(LEDGER), load(CONTRACT)
    corroboration = next(row for row in ledger["values"] if row["key"] == "target_era_corroboration_10N")
    mechanic = next(row for row in corroboration["mechanics"] if row["mechanic"] == "green_release_and_remedy")
    assert mechanic["status"] == "modelled_by_native_draw"
    assert "green_release_begins_10N" in mechanic["ledger_values"]
    for field in ("pre_cutoff", "post_cutoff", "note"):
        assert mechanic[field]
    assert "7.3-10.5 s" in mechanic["pre_cutoff"] and "7.299" in mechanic["pre_cutoff"]
    assert "6.415" in mechanic["post_cutoff"] and "canceled Begin Cast" in mechanic["post_cutoff"]
    assert "6.415-10.505 s" in mechanic["note"] and "stays a fixed 9 s" not in mechanic["note"]

    timer_ledger = next(claim for claim in ledger["unresolved"] if claim["key"].startswith("live_timer"))
    timer_contract = next(claim for claim in contract["unresolved"] if claim["key"].startswith("live_timer"))
    for claim in (timer_ledger, timer_contract):
        gap = claim["evidence_gap"]
        for fragment in ("6.415-10.505 s", "6.415 s after the imbue", "canceled Begin Cast", "7PT6hQ3wBqXmdtcH 49",
                         "green_release_begins_10N", "either order"):
            assert fragment in gap, fragment
        assert "Release Aberrations stays at 9 s" not in gap and "fixed 9 s already sits inside" not in gap
        assert claim["target_era_10N"]["status"] == "closed_target_era"
        assert "6.415-10.505 s" in claim["target_era_10N"]["summary"]
    for text in (json.dumps(ledger), json.dumps(contract)):
        assert "Release stays 9 s" not in text and "Release stays at 9 s" not in text
        assert "stays a fixed 9 s after Slime Imbued" not in text

    green = next(row for row in ledger["values"] if row["key"] == "green_phase_10N")
    assert "Release Aberrations begin 7.3-10.5 s (native 9 s" in green["value"] and "6.415 (a canceled Begin Cast)" in green["value"]
    assert "6.415-10.505 s" in green["native_comparison"]
    item = next(row for row in ledger["native_fidelity_items"] if row["key"] == "green_arcane_storm_offset_10N")
    assert "6.415-10.505 s" in item["native"] and "6.415-10.505 s" in item["next"]
    source = ledger["source_catalog"][POST_CUTOFF]
    assert source["raw_capture"].endswith("wcl_round3_maloriak_bwd10n_20260930.tar.gz")
    assert "6.415-10.505 s" in ledger["fidelity_state_by_mode_note"] and "6.415-10.505 s" in contract["fidelity_state_by_mode_note"]
    assert any("Release begin 6.415-10.505 s" in row for row in ledger["acceptance_observations"])

    audit = next(boss for boss in load(AUDIT)["bosses"] if boss["boss_slug"] == "maloriak")
    timer_row = next(row for row in audit["blockers"] if row["key"].startswith("live_timer"))
    assert "6.415-10.505 s" in timer_row["remaining_gap"] and "canceled Begin Cast" in timer_row["remaining_gap"]
    assert "Release Aberrations stays" not in timer_row["remaining_gap"]
    dossier = DOSSIER.read_text(encoding="utf-8")
    for fragment in ("6.415-10.505 s", "6.415 (canceled)", "green_release_begins_10N", "either order"):
        assert fragment in dossier, fragment
    assert "Release Aberrations stays at 9 s" not in dossier and "Release stays 9 s" not in dossier


def test_release_and_remedy_may_fall_in_either_order_and_events_wait_while_casting() -> None:
    """Release (6.415-10.505 s) and Remedy (7.3-14.2 s) are drawn independently and overlap, as they did before the
    draw (fixed 9 s against a 7.5 s Remedy in the other modes): only the storm is ordered before them. A due event
    waits while Maloriak casts, because UpdateAI runs no event until the cast ends."""
    shared, boss = SHARED.read_text(encoding="utf-8"), BOSS.read_text(encoding="utf-8")
    release = (shared_constant("GREEN_RELEASE_10N_MIN_MS"), shared_constant("GREEN_RELEASE_10N_MAX_MS"))
    remedy = (shared_constant("GREEN_REMEDY_10N_MIN_MS"), shared_constant("GREEN_REMEDY_10N_MAX_MS"))
    assert release[0] < remedy[1] and remedy[0] < release[1]
    asserts = re.findall(r"static_assert\(([^;]*?),\s*\"", shared)
    assert "GREEN_STORM_10N_MAX_MS < GREEN_REMEDY_10N_MIN_MS" in asserts
    assert "GREEN_STORM_10N_MAX_MS < GREEN_RELEASE_10N_MIN_MS" in asserts
    assert not [line for line in asserts if "RELEASE" in line and "REMEDY" in line]
    update = boss[boss.index("events.Update(diff);"):]
    assert update.index("if (me->HasUnitState(UNIT_STATE_CASTING))\n            return;") < update.index("while (uint32 eventId = events.ExecuteEvent())")
    remedy_case = boss[boss.index("case EVENT_REMEDY:"):boss.index("case EVENT_RELEASE_ABERRATIONS:")]
    release_case = boss[boss.index("case EVENT_RELEASE_ABERRATIONS:"):boss.index("case EVENT_FACE_TO_CAULDRON:")]
    assert "EVENT_RELEASE_ABERRATIONS" not in remedy_case and "EVENT_REMEDY" not in release_case
