"""Round 2 package M: shard runs of raid_shard_plan_v1 cohorts (provisioning, plan checks, layout)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.test_shard_coordinator import MAGMAW, MALORIAK, MALORIAK_LOCKOUT, FakeWorld, fast_watchdog, shard_row
from tools.raid_program import shard_coordinator as sc

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "dataset/validation_scenarios"
RUN_PLAN = ROOT / "experiments/configs/shard_runs/bwd_10n_round2_canonical_c0_v1.json"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
BOSSES = ("magmaw", "omnotron", "chimaeron", "atramedes", "maloriak", "nefarian")


@pytest.fixture(scope="module")
def generated() -> dict:
    from tools.raid_program.raid_shard_scenarios import build_plan
    return build_plan(COMPOSITION)


def _source(tmp_path: Path, plan: dict) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def test_round2_run_plan_runs_every_bwd_c0_shard_from_the_generated_plan(generated):
    plan = sc.load_run_plan(RUN_PLAN)
    assert [spec.cohort_id for spec in plan.shards] == [f"blackwing_descent_10n_{boss}_c0" for boss in BOSSES]
    assert len(plan.shards) == sc.MAX_SHARDS
    assert plan.source_plan == ROOT / "dataset/raid_shard_provisioning/blackwing_descent_10n_canonical_v1/plan.json"
    for spec in plan.shards:
        assert spec.profile == spec.scenario_id == spec.pool_tag == spec.cohort_id + "_diagnostic"
    fresh = {spec.boss_key for spec in plan.shards if spec.lockout is None}
    assert fresh == {"magmaw", "omnotron"}
    assert plan.shards[-1].lockout.seed_argument == "magmaw,omnotron,chimaeron,atramedes,maloriak"
    # The run plan is exactly the generated cohorts (identities and lockouts).
    source = {shard["scenario_id"]: shard for shard in generated["shards"]}
    sc.check_against_source_plan(plan, source)
    assert len(plan.plan_backed(source)) == 6


def test_run_plan_drift_from_the_generated_plan_is_refused(generated):
    source = {shard["scenario_id"]: shard for shard in generated["shards"]}
    plan = sc.load_run_plan(RUN_PLAN)
    maloriak = next(spec for spec in plan.shards if spec.boss_key == "maloriak")
    for drifted in (sc.ShardSpec(**{**maloriak.__dict__, "lockout": sc.LockoutRequest("blackwing_descent", "10n", ("magmaw",))}),
                    sc.ShardSpec(**{**maloriak.__dict__, "lockout": None}),
                    sc.ShardSpec(**{**maloriak.__dict__, "boss_key": "nefarian"})):
        with pytest.raises(sc.ShardPlanError, match="differs from its generated plan shard"):
            sc.check_against_source_plan(sc.ShardRunPlan(shards=(drifted,), source_plan=plan.source_plan), source)


def test_run_plan_source_path_must_be_repository_relative(tmp_path):
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"schema": sc.RUN_PLAN_SCHEMA, "raid_shard_plan": "/tmp/plan.json",
                                "shards": [shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW)]}))
    with pytest.raises(sc.ShardPlanError, match="repository-relative"):
        sc.load_run_plan(path)


def test_a_generated_plan_is_its_own_source(tmp_path, generated):
    path = _source(tmp_path, generated)
    plan = sc.load_run_plan(path, select=["blackwing_descent_10n_maloriak_c0", "blackwing_descent_10n_full_c0"])
    assert plan.source_plan == path
    maloriak, full = plan.shards
    assert maloriak.lockout.boss_keys == ("magmaw", "omnotron")
    assert full.profile == full.scenario_id == full.pool_tag == "blackwing_descent_10n_full_c0"
    # A generated shard without predecessors is a fresh instance, not a seeded "none" lockout.
    assert full.lockout is None and not full.seeded
    magmaw = sc.load_run_plan(path, select=["blackwing_descent_10n_magmaw_c0"]).shards[0]
    assert magmaw.lockout is None
    sc.check_against_source_plan(plan, sc.source_plan_shards(path))


def _recorders(monkeypatch):
    calls: dict[str, Any] = {"legacy": [], "bind": [], "reset": [], "plan": []}
    monkeypatch.setattr(sc.harness, "prepare_validation_provisioning",
                        lambda *args, **kwargs: calls["legacy"].append((args, kwargs)) or {"legacy": True})
    monkeypatch.setattr(sc.harness, "bind_validation_provisioning_sql",
                        lambda config, provisioning: calls["bind"].append(provisioning))
    monkeypatch.setattr(sc.harness, "prepare_bot_pool_reset",
                        lambda root, config, tags, **kwargs: calls["reset"].append((tags, kwargs)) or {"tags": tags})
    return calls


def _provisioner(calls):
    def provision(plan, specs, **kwargs):
        calls["plan"].append(([spec.scenario_id for spec in specs], kwargs))
        return {"passed": True, "selected_scenario_ids": [spec.scenario_id for spec in specs]}
    return provision


def test_legacy_only_runs_keep_the_unchanged_110_character_path(tmp_path, monkeypatch):
    calls = _recorders(monkeypatch)
    plan = sc.ShardRunPlan(shards=(sc.parse_shard(shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW)),
                                   sc.parse_shard(shard_row("blackwing_descent_10n_maloriak_c0", MALORIAK,
                                                            MALORIAK_LOCKOUT))))
    result = sc.prepare_databases(plan, config=tmp_path / "w.conf", run_root=tmp_path, provisioning_config=Path("p.json"),
                                  gear_profiles=Path("g.json"), apply=True, plan_provisioner=_provisioner(calls))
    assert list(result) == ["validation_provisioning", "bot_pool_reset"]
    assert calls["legacy"] == [((tmp_path / "preparation", Path("p.json"), Path("g.json"), tmp_path / "w.conf"),
                                {"apply": True})]
    assert calls["bind"] == [{"legacy": True}] and calls["plan"] == []
    assert [tags for tags, _ in calls["reset"]] == [[MAGMAW], [MALORIAK]]
    assert all(kwargs == {"apply": True, "reset_positions": False, "reset_quests": True, "reset_memory": True}
               for _, kwargs in calls["reset"])


def test_plan_cohorts_use_the_guarded_path_and_skip_the_legacy_apply(tmp_path, monkeypatch, generated):
    calls = _recorders(monkeypatch)
    source = _source(tmp_path, generated)
    plan = sc.load_run_plan(source, select=["blackwing_descent_10n_magmaw_c0", "blackwing_descent_10n_nefarian_c0"])
    result = sc.prepare_databases(plan, config=tmp_path / "w.conf", run_root=tmp_path, provisioning_config=Path("p.json"),
                                  gear_profiles=Path("g.json"), apply=True, plan_provisioner=_provisioner(calls))
    assert result["validation_provisioning"] == {"skipped": "no_legacy_shards"} and calls["legacy"] == []
    assert calls["plan"][0][0] == ["blackwing_descent_10n_magmaw_c0_diagnostic", "blackwing_descent_10n_nefarian_c0_diagnostic"]
    assert calls["plan"][0][1]["root"] == tmp_path / "preparation" and calls["plan"][0][1]["apply"] is True
    assert result["raid_shard_provisioning"]["passed"] is True
    assert len(calls["reset"]) == 2


def test_mixed_runs_provision_both_paths(tmp_path, monkeypatch, generated):
    calls = _recorders(monkeypatch)
    source = _source(tmp_path, generated)
    plan = sc.ShardRunPlan(shards=(sc.parse_shard(shard_row("blackwing_descent_10n_magmaw_c1", MAGMAW)),
                                   sc.parse_shard({**generated["shards"][4], "lockout": MALORIAK_LOCKOUT})),
                           source_plan=source)
    result = sc.prepare_databases(plan, config=tmp_path / "w.conf", run_root=tmp_path, provisioning_config=Path("p.json"),
                                  gear_profiles=Path("g.json"), apply=True, plan_provisioner=_provisioner(calls))
    assert result["validation_provisioning"] == {"legacy": True} and len(calls["legacy"]) == 1
    assert calls["plan"][0][0] == ["blackwing_descent_10n_maloriak_c0_diagnostic"]


def test_a_missing_generated_plan_stops_before_any_provisioning(tmp_path, monkeypatch):
    calls = _recorders(monkeypatch)
    plan = sc.ShardRunPlan(shards=(sc.parse_shard(shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW)),),
                           source_plan=tmp_path / "absent.json")
    with pytest.raises(sc.ShardPlanError, match="reproduce the raid_shard_provisioning DVC stage"):
        sc.prepare_databases(plan, config=tmp_path / "w.conf", run_root=tmp_path, provisioning_config=Path("p.json"),
                             gear_profiles=Path("g.json"), apply=True, plan_provisioner=_provisioner(calls))
    assert calls == {"legacy": [], "bind": [], "reset": [], "plan": []}


def test_plan_scenario_rows_are_checked_against_the_generated_plan(tmp_path, monkeypatch, generated):
    source = _source(tmp_path, generated)
    config = tmp_path / "w.conf"
    config.write_text('BotWorld.ProfileManifest = "dataset/bot_runtime_profiles/profiles.json"\n')
    plan = sc.load_run_plan(source, select=["blackwing_descent_10n_magmaw_c0", "blackwing_descent_10n_full_c0"])
    report = sc.check_plan_scenario_rows(plan, config)
    assert report["all_passed"] and report["checked"] == ["blackwing_descent_10n_magmaw_c0_diagnostic",
                                                          "blackwing_descent_10n_full_c0"]
    drifted = json.loads(source.read_text())
    drifted["shards"][0]["role_counts"] = {"tank": 1, "healer": 3, "dps": 6}
    source.write_text(json.dumps(drifted))
    with pytest.raises(sc.ShardPlanError, match="scenario rows drifted"):
        sc.check_plan_scenario_rows(plan, config)
    assert sc.check_plan_scenario_rows(sc.ShardRunPlan(shards=plan.shards[:1]), config) is None


def test_flat_layout_puts_the_only_shard_in_the_run_root(tmp_path):
    world = FakeWorld()
    plan = sc.ShardRunPlan(shards=(sc.parse_shard(shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW)),),
                           watchdog=sc.WatchdogPolicy(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=30))
    summary = sc.ShardCoordinator(plan, sc.SerializedConsole(world), tmp_path, scenario_dir=SCENARIOS,
                                  sleep=fast_watchdog(), flat=True).run()
    assert summary["terminal_reason"] == "completed", summary
    assert (tmp_path / "report.json").is_file() and (tmp_path / "shard_run.json").is_file()
    assert not (tmp_path / "shards").exists()
    assert summary["ingest"][0][-1] == str(tmp_path)
    two = sc.ShardRunPlan(shards=(plan.shards[0], sc.parse_shard(shard_row("blackwing_descent_10n_maloriak_c0", MALORIAK))))
    with pytest.raises(sc.ShardPlanError, match="exactly one shard"):
        sc.ShardCoordinator(two, sc.SerializedConsole(world), tmp_path, flat=True)


def _targets(tmp_path: Path) -> tuple[Path, Path]:
    folder, sidecars = tmp_path / "raid_targets", tmp_path / "raid_target_roster_variants"
    folder.mkdir()
    sidecars.mkdir()
    for scenario, validation in (
            ("blackwing_descent_10n_magmaw", MAGMAW),
            ("blackwing_descent_10n_omnotron_defense_system", "blackwing_descent_10n_omnotron_c0_diagnostic"),
            ("blackwing_descent_10n_maloriak", "blackwing_descent_10n_maloriak_c0_diagnostic")):
        (folder / f"{scenario}.json").write_text(json.dumps({"scenario": scenario, "validation_scenario_id": validation}))
    (sidecars / "blackwing_descent_10n_magmaw.json").write_text(json.dumps({
        "schema": "raid_target_roster_variants_v1", "target_scenario": "blackwing_descent_10n_magmaw",
        "variants": [{"validation_scenario_id": "blackwing_descent_10n_magmaw_c0_diagnostic"}]}))
    for broken in (folder, sidecars):
        (broken / "broken.json").write_text("{")
    return folder, sidecars


@pytest.mark.parametrize("cohort,profile,scenario", [
    ("blackwing_descent_10n_magmaw_c0", "blackwing_descent_10n_magmaw_c0_diagnostic", "blackwing_descent_10n_magmaw"),
    ("blackwing_descent_10n_magmaw_c0", MAGMAW, "blackwing_descent_10n_magmaw"),  # the round-1 proof shape
    ("blackwing_descent_10n_omnotron_c0", "blackwing_descent_10n_omnotron_c0_diagnostic",
     "blackwing_descent_10n_omnotron_defense_system"),  # the target names the scenario, not the key
    ("blackwing_descent_10n_maloriak_c0", MALORIAK, "blackwing_descent_10n_maloriak"),
    ("blackwing_descent_10n_maloriak_c3", "blackwing_descent_10n_maloriak_c3_diagnostic", "blackwing_descent_10n_maloriak"),
    ("blackwing_descent_10n_full_c0", "blackwing_descent_10n_full_c0", "blackwing_descent_10n_full"),
])
def test_ingest_uses_the_boss_raid_target_scenario(tmp_path, cohort, profile, scenario):
    spec = sc.parse_shard(shard_row(cohort, profile))
    assert sc.raid_target_scenario(spec, *_targets(tmp_path)) == scenario
    assert sc.raid_target_scenario(spec, tmp_path / "absent", tmp_path / "absent") == cohort.rsplit("_c", 1)[0]


def test_committed_targets_and_sidecars_name_every_round2_boss_target():
    expected = {"magmaw": "blackwing_descent_10n_magmaw"}
    for spec in sc.load_run_plan(RUN_PLAN).shards:
        if spec.boss_key in expected:
            assert sc.raid_target_scenario(spec) == expected[spec.boss_key]


def test_full_raid_shards_have_no_boss_scoreboard_ingest(tmp_path):
    full = sc.parse_shard(shard_row("blackwing_descent_10n_full_c0", "blackwing_descent_10n_full_c0"))
    assert sc.is_full_raid_shard(full)
    assert sc.ingest_command(sc.ShardOutcome(spec=full, shard_dir=tmp_path, route=None, transport=None)) is None
    boss = sc.parse_shard(shard_row("blackwing_descent_10n_maloriak_c0", MALORIAK))
    assert not sc.is_full_raid_shard(boss)
    assert sc.ingest_command(sc.ShardOutcome(spec=boss, shard_dir=tmp_path, route=None, transport=None))


def test_ingest_command_names_the_committed_magmaw_target(tmp_path):
    spec = sc.parse_shard(shard_row("blackwing_descent_10n_magmaw_c0", "blackwing_descent_10n_magmaw_c0_diagnostic"))
    command = sc.ingest_command(sc.ShardOutcome(spec=spec, shard_dir=tmp_path, route=None, transport=None))
    assert command[command.index("--scenario") + 1] == "blackwing_descent_10n_magmaw"
    assert command[-1] == str(tmp_path)


ACCEPTED_MAGMAW_TARGET_SHA256 = "46c17523fec43f26350d414a8fc5bf66c930109094ac3821bea0c87ff6b36ef2"


def test_magmaw_target_keeps_the_legacy_roster_and_its_sidecar_names_the_c0_variant(generated):
    import hashlib

    path = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_magmaw.json"
    # The accepted verdicts (b2-b5) and the saved graph pin these exact bytes.
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ACCEPTED_MAGMAW_TARGET_SHA256
    target = json.loads(path.read_text())
    assert target["validation_scenario_id"] == MAGMAW and "roster_variants" not in target
    assert sorted(target["roster"]) == [str(guid) for guid in range(30001, 30011)]
    sidecar = json.loads((ROOT / "experiments/configs/raid_target_roster_variants/blackwing_descent_10n_magmaw.json")
                         .read_text())
    assert sidecar["schema"] == "raid_target_roster_variants_v1"
    assert sidecar["target_scenario"] == target["scenario"]
    assert ROOT / sidecar["target_path"] == path
    (variant,) = sidecar["variants"]
    magmaw = next(shard for shard in generated["shards"] if shard["cohort_id"] == "blackwing_descent_10n_magmaw_c0")
    assert variant["validation_scenario_id"] == magmaw["scenario_id"]
    assert variant["roster"] == {str(bot["character_guid"]): {"name": bot["name"], "spec": bot["class_spec"],
                                                              "role": bot["role"]} for bot in magmaw["bots"]}
    argv = variant["run_plan"]["argv_template"]
    assert argv[argv.index("--shard") + 1] == magmaw["cohort_id"] and "--flat-shard-dir" in argv
    assert Path(ROOT / argv[argv.index("--plan") + 1]) == RUN_PLAN


def test_the_saved_magmaw_graph_still_accepts_its_verdict():
    """graph_acceptance.check_inputs of the saved Magmaw graph and verdict b5 (review blocker 1)."""
    from tools.raid_program import graph_acceptance

    unit = json.loads((ROOT / "experiments/configs/cata_raid_active_work_unit_v1.json").read_text())
    verdict_path = ROOT / "artifacts/cata_raid_program/verdicts/blackwing_descent_10n_magmaw-b5-d1898555-7fcea04e9dd3.json"
    if not verdict_path.is_file():
        pytest.skip("accepted Magmaw verdict not hydrated")
    verdict = json.loads(verdict_path.read_text())
    assert verdict["target_sha256"] == ACCEPTED_MAGMAW_TARGET_SHA256
    graph_acceptance.check_inputs(ROOT, unit["development_graph"], verdict)


def _recorded_plan(tmp_path: Path, generated: dict) -> Path:
    folder = tmp_path / "composition"
    folder.mkdir()
    plan = dict(generated)
    return _source(folder, plan)


def test_verify_source_plan_refuses_unrecorded_drifted_and_unverified_plans(tmp_path, monkeypatch, generated):
    from tools.raid_program import raid_loadout_sql, raid_shard_provisioning as rsp

    path = _recorded_plan(tmp_path, generated)
    gear = ROOT / "dataset/validation_gear_profiles/profiles.json"
    # The committed generator records every materialization input and source file.
    monkeypatch.setattr(raid_loadout_sql, "verify_plan_outputs", lambda *args: ([], {"output_sha256": {}}))
    if not (ROOT / "dataset/world_knowledge/trainers.jsonl").is_file() or not gear.is_file():
        pytest.skip("trainers or gear profiles not hydrated")
    assert rsp.verify_source_plan(path, gear_profiles=gear)["verified"] is True
    # A plan built before the materialization inputs were recorded (the stale local plan shape).
    stale = json.loads(path.read_text())
    stale["sources"] = {key: value for key, value in stale["sources"].items() if key != "trainers"}
    path.write_text(json.dumps(stale))
    with pytest.raises(rsp.RaidShardProvisioningError, match="plan_source_unrecorded:trainers"):
        rsp.verify_source_plan(path, gear_profiles=gear)
    # A recorded source file (the composition) changed after generation.
    drifted = json.loads(json.dumps(generated))
    drifted["sources"]["composition"]["sha256"] = "0" * 64
    path.write_text(json.dumps(drifted))
    with pytest.raises(rsp.RaidShardProvisioningError, match="plan_source_drift:composition"):
        rsp.verify_source_plan(path, gear_profiles=gear)
    # Written outputs or manifest.json that do not match a regeneration.
    path.write_text(json.dumps(generated))
    monkeypatch.setattr(raid_loadout_sql, "verify_plan_outputs",
                        lambda *args: ([{"check": "raid_shard_manifest_output_hash", "path": "plan.json"}], {}))
    with pytest.raises(rsp.RaidShardProvisioningError, match="plan_outputs_unverified:raid_shard_manifest_output_hash"):
        rsp.verify_source_plan(path, gear_profiles=gear)


def test_the_dry_run_refuses_a_stale_or_missing_generated_plan(tmp_path, monkeypatch, capsys, generated):
    from tools.raid_program import raid_shard_provisioning as rsp

    path = _recorded_plan(tmp_path, generated)
    argv = ["--plan", str(path), "--shard", "blackwing_descent_10n_magmaw_c0", "--output-dir", str(tmp_path / "out"),
            "--dry-run"]

    def refuse(plan_path, **kwargs):
        raise rsp.RaidShardProvisioningError("plan_source_drift:scenario_starts", {})
    monkeypatch.setattr(rsp, "verify_source_plan", refuse)
    assert sc.main(argv) == 1
    shown = json.loads(capsys.readouterr().out)
    assert shown["source_plan_verified"] is False and shown["source_plan_refusal"] == "plan_source_drift:scenario_starts"
    assert shown["shards"][0]["lockout"] == "fresh" and shown["shards"][0]["provisioning"] == "raid_shard_plan"
    monkeypatch.setattr(rsp, "verify_source_plan", lambda plan_path, **kwargs: {"verified": True})
    assert sc.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["source_plan_verified"] is True
    run_plan = tmp_path / "run.json"
    run_plan.write_text(json.dumps({"schema": sc.RUN_PLAN_SCHEMA, "raid_shard_plan": "dataset/absent/plan.json",
                                    "shards": [shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW)]}))
    assert sc.main(["--plan", str(run_plan), "--output-dir", str(tmp_path / "out"), "--dry-run"]) == 1
    assert json.loads(capsys.readouterr().out)["source_plan_refusal"].startswith("source_plan_missing")


def test_live_plan_provisioning_verifies_the_generated_plan_first(tmp_path, monkeypatch, generated):
    from tools.raid_program import raid_shard_provisioning as rsp

    path = _recorded_plan(tmp_path, generated)
    plan = sc.load_run_plan(path, select=["blackwing_descent_10n_magmaw_c0"])
    calls = []

    def refuse(plan_path, **kwargs):
        raise rsp.RaidShardProvisioningError("plan_outputs_unverified:raid_shard_output_content", {"plan": str(plan_path)})
    monkeypatch.setattr(rsp, "verify_source_plan", refuse)
    monkeypatch.setattr(rsp, "provision_plan_cohorts", lambda *args, **kwargs: calls.append(args) or {"passed": True})
    with pytest.raises(rsp.RaidShardProvisioningError, match="plan_outputs_unverified"):
        sc.provision_plan_shards(plan, plan.shards, config=tmp_path / "w.conf", root=tmp_path,
                                 gear_profiles=Path("g.json"), apply=True)
    assert calls == []
