"""Play-mode evidence guard and its wiring into the scoring, acceptance and archive tools.

Synthetic payloads, run dirs and tarballs only; nothing here launches a server or touches DVC.
"""
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

from tools.raid_program import graph_acceptance as acceptance
from tools.raid_program import play_mode_guard as guard
from tools.raid_program import scoreboard_run
from tools.raid_program.development_graph import GraphError
from tools.raid_program.play_mode_guard import (
    PlayModeConfigRefused, PlayModeEvidenceRefused, find_play_markers, is_play, play_mode_config_enabled,
    refuse_play,
)
from tools.raid_program.scoreboard import evaluate_target, load_records, main as scoreboard_main
from tools.raid_program.scoreboard_core import append_record, counted_kills, exclusion_reason, scoreboard_path
from tools.raid_program.scoreboard_record import outcome_summary, record_from_summary
from tests.test_development_graph import case  # noqa: F401 - fixture used by assessing
from tests.test_graph_acceptance import (  # noqa: F401 - fixtures
    assessing, assessment, cite, kill as verdict_kill, make_verdict, scoreboard, validating,
)
from tests.test_raid_scoreboard import SCENARIO, fakes, kill, root, run_cli, write_run  # noqa: F401 - fixtures

PLAY = {"cohort_purpose": "play", "play_session_id": "ps-20260924-a"}


def play_run_dir(folder: Path, how: str = "marker") -> Path:
    """A closed validation-shaped run dir that is play by one marker."""
    write_run(folder)
    if how == "marker":
        (folder / "latest.json").write_text(json.dumps({"status": {"cohort_purpose": "play"}}))
    elif how == "session_file":
        (folder / "play_session.json").write_text("{}")
    return folder


# --- guard semantics ----------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"cohort_purpose": "play"},
    {"status": {"cohort": [{"cohort_purpose": "play"}]}},
    {"rows": [[{"play_session_id": "ps-1"}]]},
    [{"deep": {"deeper": ({"play_session_id": "x"},)}}],
])
def test_in_memory_play_markers_at_any_depth(payload):
    assert is_play(payload)
    assert find_play_markers(payload)


@pytest.mark.parametrize("payload", [
    {"cohort_purpose": "validation", "play_mode_enabled": False},
    {"play_session_id": ""},
    {"play_session_id": None},
    {"cohort_purpose": "Play-ish", "text": "cohort_purpose play"},
    {},
    [],
])
def test_validation_or_absent_markers_are_not_play(payload):
    assert not is_play(payload)
    refuse_play(payload, "validation payload")  # does not raise


def test_refusal_names_context_and_reasons():
    with pytest.raises(PlayModeEvidenceRefused, match=r"scoreboard ingest: refusing play-mode evidence") as error:
        refuse_play({"status": PLAY}, "scoreboard ingest")
    assert isinstance(error.value, ValueError)
    assert '"cohort_purpose": "play"' in str(error.value) and "ps-20260924-a" in str(error.value)


def test_raw_text_payloads_are_scanned():
    assert is_play(b'{"a": {"cohort_purpose" : "play"}}')
    assert is_play('{"play_session_id":"ps-2"}')
    assert not is_play('{"cohort_purpose":"validation","play_session_id":""}')


def test_run_dir_markers(tmp_path):
    validation = write_run_dir(tmp_path / "validation", {"cohort_purpose": "validation"})
    assert find_play_markers(validation) == []
    marked = write_run_dir(tmp_path / "marked", {"nested": {"cohort_purpose": "play"}})
    assert is_play(marked) and is_play(str(marked))
    session = write_run_dir(tmp_path / "session", {"cohort_purpose": "validation"})
    (session / "sub").mkdir()
    (session / "sub" / "play_session.json").write_text("{}")
    assert any("play session file" in reason for reason in find_play_markers(session))
    under = write_run_dir(tmp_path / "artifacts" / "play_sessions" / "ps-3", {})
    assert any("artifacts/play_sessions" in reason for reason in find_play_markers(under))
    assert not is_play(tmp_path / "does-not-exist")


def write_run_dir(folder: Path, latest: dict) -> Path:
    folder.mkdir(parents=True)
    (folder / "latest.json").write_text(json.dumps(latest))
    (folder / "worldserver_output.log").write_text('"cohort_purpose":"play"')  # logs are not scanned in a dir
    return folder


def test_big_file_is_scanned_as_text_across_chunk_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(json, "loads", lambda *a, **k: pytest.fail("the guard must not parse files"))
    marker = b'"cohort_purpose": "play"'
    filler = b'{"rows": "' + b"x" * (guard._CHUNK - 20)  # the marker starts 10 bytes before the first chunk ends
    big = tmp_path / "latest.json"
    big.write_bytes(filler + marker + b"y" * (2 * guard._CHUNK) + b'"}')
    assert big.stat().st_size > 3 * guard._CHUNK
    assert find_play_markers(big) == [f'{big}: "cohort_purpose": "play"']
    session = tmp_path / "report.json"
    session.write_bytes(b"z" * (guard._CHUNK - 20) + b'\\"play_session_id\\": \\"ps-escaped\\"' + b"z" * 100)
    assert find_play_markers(session) == [f'{session}: "play_session_id": "ps-escaped"']
    clean = tmp_path / "combat_log.json"
    clean.write_bytes(b'{"cohort_purpose": "validation", "play_session_id": ""' + b" " * (2 * guard._CHUNK) + b"}")
    assert not is_play(clean)


def write_tarball(path: Path, members: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_tarballs(tmp_path):
    clean = write_tarball(tmp_path / "clean.tar.gz", {"run/latest.json": b'{"cohort_purpose": "validation"}',
                                                     "run/worldserver_output.log": b'"cohort_purpose":"play"'})
    assert not is_play(clean)
    session = write_tarball(tmp_path / "session.tar.gz", {"run/play_session.json": b"{}"})
    assert any("play session file" in reason for reason in find_play_markers(session))
    marked = write_tarball(tmp_path / "marked.tar.gz", {"run/report.json": b'{"a": [{"play_session_id": "ps-9"}]}'})
    assert find_play_markers(marked) == [f'{marked}!run/report.json: "play_session_id": "ps-9"']


@pytest.mark.parametrize("text,enabled", [
    ("BotWorld.PlayMode.Enable = 1\n", True),
    ('BotWorld.PlayMode.Enable = "1"\n', True),
    ("  BotWorld.PlayMode.Enable=true  # humans\n", True),
    ("BotWorld.PlayMode.Enable = 0\n", False),
    ("#BotWorld.PlayMode.Enable = 1\n", False),
    ("BotWorld.ValidationRoute.Enable = 1\n", False),
    ("", False),
])
def test_play_mode_config_detection(text, enabled):
    assert play_mode_config_enabled(text) is enabled


# --- scoreboard ---------------------------------------------------------------------------------

def test_exclusion_reason_excludes_a_kill_record_with_a_play_marker(root):
    assert exclusion_reason(kill("a", "k1", cohort_purpose="validation")) is None
    assert exclusion_reason(kill("a", "k1", cohort_purpose="play")) == "play_mode_run"
    assert exclusion_reason(kill("a", "k1", play={"play_session_id": "ps-1"}, voided={"reason": "x"})) == "play_mode_run"
    append_record(root, SCENARIO, kill("mix", "k1"))
    append_record(root, SCENARIO, kill("mix", "k2", cohort_purpose="play"))
    assert [row["kill_id"] for row in counted_kills(load_records(root, SCENARIO))] == ["mix-k1"]
    try:
        details = evaluate_target(root, SCENARIO, "mix")["kills_detail"]
    except ValueError as error:  # scoreboard_verdict.REASON_ORDER lacks play_mode_run: the label cannot be judged
        assert "unknown reason code play_mode_run" in str(error)
    else:
        assert [(row["counted"], row["exclusion_reason"]) for row in details] == [(True, None), (False, "play_mode_run")]


def test_ingest_refuses_a_play_run_dir_and_writes_nothing(root, tmp_path):
    for how in ("marker", "session_file"):
        run_dir = play_run_dir(tmp_path / f"play-{how}", how)
        with pytest.raises(PlayModeEvidenceRefused, match="scoreboard ingest --run-dir"):
            scoreboard_main(["--root", str(root), "ingest", "--scenario", SCENARIO, "--label", "play",
                             "--run-dir", str(run_dir)])
    assert not scoreboard_path(root, SCENARIO).exists()


def test_ingest_refuses_a_play_summary(root, tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"schema": "magmaw_spell_queue_run_summary_v1", "run_dir": "/tmp/x", **PLAY}))
    with pytest.raises(PlayModeEvidenceRefused, match="scoreboard ingest --summary"):
        scoreboard_main(["--root", str(root), "ingest", "--scenario", SCENARIO, "--label", "play",
                         "--summary", str(summary)])
    assert not scoreboard_path(root, SCENARIO).exists()


def test_record_builders_refuse_play(root, tmp_path):
    with pytest.raises(PlayModeEvidenceRefused, match="scoreboard record"):
        outcome_summary(play_run_dir(tmp_path / "run"), None, "bwd.magmaw.encounter")
    with pytest.raises(PlayModeEvidenceRefused, match="scoreboard record k1"):
        record_from_summary({"actors": [], **PLAY}, root=root, target={}, scenario=SCENARIO, label="l",
                            kill_id="k1", deaths={})
    write_run(tmp_path / "validation")
    assert outcome_summary(tmp_path / "validation", None, "bwd.magmaw.encounter")["report_present"] is True


def test_scoreboard_run_refuses_a_play_run_before_recording_or_archiving(root, fakes, monkeypatch):
    install, worldserver = fakes
    harness, archive = install([{}])
    original = scoreboard_run.subprocess.Popen

    def play_popen(argv, **kwargs):
        process = original(argv, **kwargs)
        (Path(argv[argv.index("--output-dir") + 1]) / "play_session.json").write_text("{}")
        return process
    monkeypatch.setattr(scoreboard_run.subprocess, "Popen", play_popen)
    with pytest.raises(PlayModeEvidenceRefused, match=r"scoreboard run play-k1-.*evidence kept at"):
        run_cli(root, worldserver, "play", 1)
    assert load_records(root, SCENARIO) == [] and archive.names == []
    assert any((root / "runs").iterdir())  # the evidence is left where the harness wrote it


def test_archive_evidence_refuses_play_sources(root, tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard_run.subprocess, "run", lambda *a, **k: pytest.fail("must not archive"))
    run_dir = play_run_dir(tmp_path / "run")
    pointer, error = scoreboard_run.archive_evidence(root, SCENARIO, "k1", [run_dir], set())
    assert pointer is None and "scoreboard evidence archive for k1: refusing play-mode evidence" in error


# --- graph acceptance ---------------------------------------------------------------------------

def test_play_mode_is_an_unattributable_terminal_class():
    assert guard.PLAY_TERMINAL_REASON in acceptance.UNATTRIBUTABLE


def test_assessment_refuses_a_verdict_with_play_kills(assessing, scoreboard):
    root, state, evidence = assessing
    kills = [verdict_kill(1), verdict_kill(2), verdict_kill(3),
             verdict_kill(4, counted=False) | {"exclusion_reason": "play_mode_run"}]
    scoreboard["batch1"] = make_verdict(root, kills=kills)
    with pytest.raises(GraphError, match="play-mode evidence is never accepted"):
        acceptance.verify_verdict(root, state["development_graph"], cite(root, scoreboard["batch1"]))


def test_assessment_receipt_with_a_play_marker_is_refused(assessing, scoreboard):
    root, state, evidence = assessing
    g = state["development_graph"]
    r = {"attempt_id": g["run"]["attempt_id"], "verdict": cite(root, scoreboard["batch1"]), "encounter_clear": True,
         "accepted_requirements": ["actor_1"], "notes": {"cohort_purpose": "play"}}
    with pytest.raises(GraphError, match="assessment: play-mode evidence is never accepted"):
        acceptance.assess(root, g, r)


def test_run_receipt_and_verdict_refuse_a_label_with_play_kills(case, scoreboard):  # noqa: F811
    root, state = validating(case, scoreboard)
    scoreboard["batch1"] = make_verdict(root, kills=[verdict_kill(1), verdict_kill(2) | {"cohort_purpose": "play"}])
    with pytest.raises(GraphError, match="label batch1: play-mode evidence is never accepted"):
        acceptance.write_run_receipt(root, "batch1", producer="coordinator", cleanup_verified=True)
    with pytest.raises(GraphError, match="play-mode evidence is never accepted"):
        acceptance.write_verdict(root, "batch1", write=False)
    assert not (root / acceptance.VERDICT_DIR).exists()


# --- evidence archive ---------------------------------------------------------------------------

def test_archive_run_evidence_refuses_play_runs(tmp_path, monkeypatch):
    from experiments import archive_run_evidence
    assert str(tmp_path).startswith("/tmp/")  # the tool only archives /tmp sources
    monkeypatch.setattr(archive_run_evidence, "DIRECTORY", tmp_path / "archive")
    monkeypatch.setattr(archive_run_evidence, "_pack", lambda *a: pytest.fail("must not pack play evidence"))
    run_dir = play_run_dir(tmp_path / "run", "session_file")
    monkeypatch.setattr(sys, "argv", ["archive_run_evidence", "--name", "play_attempt", str(run_dir)])
    with pytest.raises(SystemExit, match="archive_run_evidence --name play_attempt: refusing play-mode evidence"):
        archive_run_evidence.main()
    assert run_dir.exists() and not (tmp_path / "archive").exists()


# --- validation harness config ------------------------------------------------------------------

def test_validation_config_forces_play_mode_off_and_refuses_an_enabled_input(tmp_path):
    from tools.bot_ml.run_live_bot_validation import write_validation_config
    base = tmp_path / "base.conf"
    base.write_text("BotWorld.AutoStart = 0\nBotWorld.PlayMode.Enable = 0\n")
    generated = write_validation_config(base, tmp_path / "run", pool_tag="magmaw")
    text = generated.read_text()
    assert text.count("BotWorld.PlayMode.Enable") == 1 and "BotWorld.PlayMode.Enable = 0" in text
    # An absent key already means off; the generated config stays byte-identical
    # to earlier runs (config identity is part of runtime evidence).
    absent = tmp_path / "absent.conf"
    absent.write_text("BotWorld.AutoStart = 0\n")
    assert "BotWorld.PlayMode" not in write_validation_config(absent, tmp_path / "run2", pool_tag="m").read_text()
    enabled = tmp_path / "enabled.conf"
    enabled.write_text("BotWorld.PlayMode.Enable = 1\n")
    with pytest.raises(PlayModeConfigRefused, match="validation runs never start in play mode"):
        write_validation_config(enabled, tmp_path / "run3", pool_tag="magmaw")
    with pytest.raises(PlayModeConfigRefused):  # the pass-through path (no scenario scoping) refuses too
        write_validation_config(enabled, tmp_path / "run4")
    assert not (tmp_path / "run3" / "worldserver.validation.conf").exists() and not (tmp_path / "run4").exists()
    assert write_validation_config(base, tmp_path / "run5") == base  # pass-through unchanged when play is off


def test_verdict_and_keep_rules_treat_play_records_as_excluded_non_gameplay() -> None:
    from tools.raid_program.scoreboard_compare import NON_GAMEPLAY_EXCLUSIONS
    from tools.raid_program.scoreboard_verdict import REASON_ORDER

    assert "play_mode_run" in REASON_ORDER
    assert "play_mode_run" in NON_GAMEPLAY_EXCLUSIONS
