from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.raid_program import workflow_build


def _ref(root: Path, relative: str, payload: object) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_preflight_passes_declared_tank_mode_to_reference_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_build, "ROOT", tmp_path)
    captured: dict[str, str] = {}

    def fake_reference_preflight(**kwargs):
        captured.update(
            {
                "calibration_mode": kwargs["calibration_mode"],
                "target_spec": kwargs["target_spec"],
            }
        )
        return {"required": False, "valid": True, **captured}

    monkeypatch.setattr(
        "tools.bot_ml.run_live_bot_validation.preflight_calibration_reference_binding",
        fake_reference_preflight,
    )
    assignment = {
        "policy": _ref(tmp_path, "policy.json", json.loads((Path(__file__).resolve().parents[1] / "experiments/configs/cata_raid_build_resource_policy_host12_v1.json").read_text())),
        "validation_identity": {
            "scenario_kind": "dummy",
            "mode": "tank_threat_300",
            "spec": "blood_death_knight",
            "reference": _ref(tmp_path, "reference.json", {"spec": "blood"}),
            "roster": _ref(tmp_path, "roster.json", {"size": 25}),
            "runtime_profile": _ref(tmp_path, "runtime.sql", "profile"),
        },
    }

    result = workflow_build.preflight(tmp_path, assignment)

    assert result["valid"] is True
    assert captured == {
        "calibration_mode": "tank_threat_300",
        "target_spec": "blood_death_knight",
    }
