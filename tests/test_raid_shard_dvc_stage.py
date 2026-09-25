"""The raid_shard_provisioning DVC stage and its wiring into validation_scenarios."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
STAGES = yaml.safe_load((ROOT / "dvc.yaml").read_text(encoding="utf-8"))["stages"]
PLAN = "dataset/raid_shard_provisioning/blackwing_descent_10n_canonical_v1/plan.json"
REPORT = "dataset/raid_shard_provisioning/blackwing_descent_10n_canonical_v1/report.json"


def _argv(stage: str) -> list[str]:
    return shlex.split(" ".join(STAGES[stage]["cmd"].split()))


def _option(argv: list[str], name: str) -> list[str]:
    return [argv[index + 1] for index, token in enumerate(argv) if token == name]


def test_raid_shard_provisioning_stage_names_every_materialization_input():
    stage = STAGES["raid_shard_provisioning"]
    argv = _argv("raid_shard_provisioning")
    assert argv[:3] == ["python", "-m", "tools.raid_program.raid_shard_plan"]
    assert _option(argv, "--trainers") == ["dataset/world_knowledge/trainers.jsonl"]
    assert _option(argv, "--gear-profiles") == ["dataset/validation_gear_profiles/profiles.json"]
    assert _option(argv, "--dbc-dir") == ["data/dbc/enUS"]
    assert _option(argv, "--output-dir") == ["dataset/raid_shard_provisioning"]
    assert "--composition" not in argv  # every composition: no raid-specific stage
    assert "--check" not in argv
    deps = set(stage["deps"])
    for required in ("tools/raid_program/raid_loadout_spells.py", "tools/raid_program/raid_shard_preflight.py",
                     "dataset/world_knowledge/trainers.jsonl", "data/dbc/enUS/SkillLineAbility.dbc",
                     "data/dbc/enUS/SpellEffect.dbc", "data/dbc/enUS/NamesProfanity.dbc",
                     "data/dbc/enUS/NamesReserved.dbc", "experiments/configs/raid_compositions",
                     "experiments/configs/raid_prerequisites", "experiments/configs/validation_scenarios_cata_001.json",
                     "experiments/configs/cata_blood_permanent_enchant_overlays_v1.json",
                     "dataset/validation_gear_profiles"):
        assert required in deps, required
    for option in ("--prerequisites-dir", "--provisioning-config", "--scenario-config"):
        assert set(_option(argv, option)) <= deps, option
    assert stage["outs"] == ["dataset/raid_shard_provisioning"]


def test_every_imported_tools_module_is_a_stage_dependency():
    program = ("import sys, json\n"
               "import tools.raid_program.raid_shard_plan, tools.raid_program.raid_loadout_sql\n"
               "import tools.raid_program.raid_loadout, tools.raid_program.raid_loadout_readback\n"
               "print(json.dumps(sorted(m.__file__ for n, m in sys.modules.items()\n"
               "                        if n.startswith('tools.') and getattr(m, '__file__', None))))\n")
    files = json.loads(subprocess.run([sys.executable, "-c", program], cwd=ROOT, check=True,
                                      capture_output=True, text=True).stdout)
    modules = {Path(path).resolve().relative_to(ROOT).as_posix() for path in files}
    modules -= {"tools/bot_ml/__init__.py", "tools/raid_program/__init__.py",
                "tools/raid_program/raid_loadout_readback.py"}  # readback is not a stage input
    missing = sorted(modules - set(STAGES["raid_shard_provisioning"]["deps"]))
    assert missing == []


def test_every_stage_dependency_exists_or_is_an_upstream_output():
    outputs = {out if isinstance(out, str) else next(iter(out)) for stage in STAGES.values()
               for out in stage.get("outs") or []}
    for dep in STAGES["raid_shard_provisioning"]["deps"]:
        upstream = any(dep == out or dep.startswith(out + "/") for out in outputs)
        if dep.startswith("data/") and not (ROOT / dep).exists():
            pytest.skip("client DBCs not hydrated")
        assert upstream or (ROOT / dep).exists(), dep


def test_validation_scenarios_reads_the_generated_plan_and_its_readiness_report():
    argv = _argv("validation_scenarios")
    assert _option(argv, "--raid-shard-plan") == [PLAN]
    deps = set(STAGES["validation_scenarios"]["deps"])
    assert {PLAN, REPORT} <= deps
    composition = json.loads((ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json").read_text())
    assert Path(PLAN).parent.name == composition["composition_id"]
    # The legacy inputs are unchanged.
    for legacy in ("--provisioning-report", "--provisioning-verification", "--bwd-diagnostic-shard-fixture"):
        assert len(_option(argv, legacy)) == 1


def test_provisioning_stage_runs_in_check_mode_without_writing(tmp_path):
    if not (ROOT / "dataset/world_knowledge/trainers.jsonl").is_file() or not (ROOT / "data/dbc/enUS/Item-sparse.db2").is_file():
        pytest.skip("trainers or client DBCs not hydrated")
    argv = _argv("raid_shard_provisioning")
    argv[argv.index("--output-dir") + 1] = str(tmp_path / "out")
    result = subprocess.run([sys.executable, *argv[1:], "--check"], cwd=ROOT, check=True,
                            capture_output=True, text=True)
    summary = json.loads(result.stdout)
    assert [row["composition_id"] for row in summary] == ["blackwing_descent_10n_canonical_v1"]
    # Six boss shards plus the end-to-end cohort of the composition's full_raid entry.
    assert summary[0]["shard_count"] == 7 and summary[0]["bot_count"] == 70 and summary[0]["output_dir"] is None
    assert not (tmp_path / "out").exists()
