"""Full-raid route composition, drift repair and Magmaw shard neutrality."""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
from pathlib import Path

import pytest

from tools.raid_program import raid_route_composer as composer
from tools.raid_program.canonical_route_catalog import ALLOWED_ROUTE_KINDS
from tools.raid_program.raid_route_kinds import ALLOWED_ROUTE_KINDS as ROUTE_KINDS


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
COMPOSITION = ROOT / "experiments/configs/raid_route_compositions/blackwing_descent_10n.json"
MAGMAW_SHARD = "blackwing_descent_10n_magmaw_diagnostic"
FULL = "blackwing_descent_10n"

# Pinned from the accepted Magmaw 10N shard at 0e793b9943 (before round 1).
MAGMAW_SCENARIO_SHA256 = "3a09b1bcfcc5df82478407694c57c891128f80d29591f01f34260d7a0b97a1c7"
MAGMAW_TEXT_SHA256 = "82edb2027630ea2208f10175e39be6adb5598276bc682b9bb0d0fbcac172f610"
MAGMAW_RUNTIME_ROWS_SHA256 = "e83dbc78e10e56c212daeb25c5d35acae309256f846c67c8d9de97edf971cb00"


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _composition() -> dict:
    return json.loads(COMPOSITION.read_text(encoding="utf-8"))


def _scenario(config: dict, scenario_id: str) -> dict:
    return composer.scenarios_by_id(config)[scenario_id]


def test_route_kinds_are_one_contract_and_include_native_nodes() -> None:
    assert ALLOWED_ROUTE_KINDS is ROUTE_KINDS
    assert {"interaction", "transport"} <= set(ROUTE_KINDS)
    assert {"trash", "boss", "travel", "regroup", "descent"} <= set(ROUTE_KINDS)


def test_accepted_magmaw_shard_is_byte_identical() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    config = json.loads(text)
    shard = _scenario(config, MAGMAW_SHARD)
    canonical = json.dumps(shard, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canonical.encode()).hexdigest() == MAGMAW_SCENARIO_SHA256

    lines = text.splitlines(keepends=True)
    start = next(
        index for index, line in enumerate(lines)
        if f'"id": "{MAGMAW_SHARD}"' in line
    ) - 1
    end = next(index for index in range(start + 1, len(lines)) if lines[index].rstrip("\n") == "    },")
    span = "".join(lines[start:end + 1])
    assert hashlib.sha256(span.encode()).hexdigest() == MAGMAW_TEXT_SHA256


def test_accepted_magmaw_runtime_rows_are_byte_identical() -> None:
    """Rebuild the shard's runtime rows exactly as the DVC stage does."""

    provisioning = ROOT / "dataset/validation_provisioning/report.json"
    verification = ROOT / "dataset/validation_provisioning_verification/report.json"
    if not provisioning.exists() or not verification.exists():
        pytest.skip("provisioning reports are not materialized locally")
    from tools.bot_ml.build_validation_scenario_manifests import build_manifests, load_json

    manifests = build_manifests(
        _config(),
        load_json(provisioning),
        load_json(verification),
        load_json(ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"),
    )
    rows = [row for row in manifests["validation_routes"] if row["scenario_id"] == MAGMAW_SHARD]
    payload = "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows)
    assert len(rows) == 4
    assert hashlib.sha256(payload.encode()).hexdigest() == MAGMAW_RUNTIME_ROWS_SHA256


def test_materialized_full_route_has_no_drift_from_its_node_sets() -> None:
    config = _config()
    composed = composer.compose(config, _composition())
    assert composer.drift(config, composed) == []
    assert composer.main(["--check"]) == 0


def test_full_route_order_node_ids_and_drift_repairs() -> None:
    config = _config()
    full = _scenario(config, FULL)
    node_ids = [row["node_id"] for row in full["route"]]
    assert node_ids == [
        "bwd.entry.regroup", "bwd.magmaw.chainwielder", "bwd.magmaw.drudges",
        "bwd.magmaw.encounter", "bwd.omnotron.regroup", "bwd.omnotron.sentries",
        "bwd.omnotron.encounter", "bwd.transit.lower_wing_elevator",
        "bwd.maloriak.regroup", "bwd.maloriak.lab_trash", "bwd.maloriak.encounter",
        "bwd.atramedes.north_spirits", "bwd.atramedes.south_spirits",
        "bwd.atramedes.bell_ready", "bwd.atramedes.bell", "bwd.atramedes.intro_wait",
        "bwd.atramedes.regroup", "bwd.atramedes.encounter", "bwd.chimaeron.regroup",
        "bwd.chimaeron.finkle", "bwd.chimaeron.wake_wait", "bwd.chimaeron.encounter",
        "bwd.nefarian.orb_regroup", "bwd.nefarian.orb_gossip", "bwd.nefarian.intro_wait",
        "bwd.nefarian.descent", "bwd.nefarian.encounter",
    ]
    assert [row["step"] for row in full["route"]] == list(range(1, len(node_ids) + 1))
    assert all(row["kind"] in ROUTE_KINDS for row in full["route"])
    # Every boss strategy looks up its exact encounter node ID.
    for boss in ("magmaw", "omnotron", "maloriak", "atramedes", "chimaeron", "nefarian"):
        assert f"bwd.{boss}.encounter" in node_ids

    shards = {
        row["node_id"]: row
        for scenario in config["diagnostic_scenarios"]
        for row in scenario["route"]
    }
    by_id = {row["node_id"]: row for row in full["route"]}
    variants = {"bwd.magmaw.drudges", "bwd.magmaw.encounter"}
    for node_id, row in by_id.items():
        if node_id in shards and node_id not in variants:
            expected = {k: v for k, v in shards[node_id].items() if k != "step"}
            assert {k: v for k, v in row.items() if k != "step"} == expected, node_id

    drudges = by_id["bwd.magmaw.drudges"]
    assert drudges["mechanic_profile"] == "trash_two_tank_charge_lanes"
    assert drudges["split_lane_tank_slots"] == [1, 2]
    assert len(drudges["split_member_anchors"]) == 10
    contract = by_id["bwd.magmaw.encounter"]["mechanic_contract"]
    assert (contract["main_tank_roster_slot"], contract["off_tank_roster_slot"]) == (2, 1)
    assert contract["tank_swap_trigger"] == "debuff_stacks"
    assert contract["tank_swap_aura_id"] == 78199

    shard = _scenario(config, MAGMAW_SHARD)
    shard_by_id = {row["node_id"]: row for row in shard["route"]}
    assert shard_by_id["bwd.magmaw.drudges"]["mechanic_profile"] == "trash_ground_danger_movement"
    assert "main_tank_roster_slot" not in shard_by_id["bwd.magmaw.encounter"]["mechanic_contract"]
    assert set(full["mechanic_profiles"]) == {
        row["mechanic_profile"] for row in full["route"] if row.get("mechanic_profile")
    }


def test_native_bwd_prerequisites_use_generic_contracts() -> None:
    by_id = {row["node_id"]: row for row in _scenario(_config(), FULL)["route"]}
    orb = by_id["bwd.nefarian.orb_gossip"]
    assert orb["interaction_contract"]["owner_role"] == "dps"
    # The orb's despawn alone is weak proof (GossipSelect despawns it even
    # when Nefarius cannot start the intro): Nefarian's summon is required.
    assert orb["completion_contract"] == {
        "kind": "all_of",
        "contracts": [
            {"kind": "gameobject_despawned", "entry": 203254, "spawn_id": 239510},
            {"kind": "creature_summoned", "entry": 41376},
        ],
    }
    intro = by_id["bwd.nefarian.intro_wait"]["completion_contract"]
    assert intro["kind"] == "all_of"
    assert intro["timeout_ms"] == 120000
    assert {"kind": "transport_at_stop", "transport_entry": 207834, "stop_frame": 0} in intro["contracts"]
    # Every declared contract is bounded in time.
    for row in by_id.values():
        for field in ("interaction_contract", "transport_contract"):
            if field in row:
                assert row[field]["timeout_ms"] > 0, (row["node_id"], field)
        if "completion_contract" in row and "interaction_contract" not in row and "transport_contract" not in row:
            assert row["completion_contract"]["timeout_ms"] > 0, row["node_id"]

    descent = by_id["bwd.nefarian.descent"]
    assert descent["kind"] == "transport"
    assert "descent_action" not in descent
    assert descent["transport_contract"]["entry"] == 207834
    assert descent["transport_contract"]["board_stop_frame"] == 0

    elevator = by_id["bwd.transit.lower_wing_elevator"]
    contract = elevator["transport_contract"]
    assert elevator["kind"] == "transport"
    assert (contract["entry"], contract["spawn_id"]) == (203716, 235178)
    assert contract["board_transport_z"] - contract["exit_transport_z"] == pytest.approx(112.6704, abs=1e-3)
    assert "native_walk_jump_or_fall" not in CONFIG.read_text(encoding="utf-8")
    for retired in ("intro_complete_and_elevator_ready", "player_in_nefarian_arena"):
        assert retired not in CONFIG.read_text(encoding="utf-8")


def _base_config() -> dict:
    def row(node_id: str, kind: str = "trash", **extra) -> dict:
        return {"step": 0, "node_id": node_id, "kind": kind, "label": node_id, "x": 1.0, **extra}

    return {
        "scenarios": [{"id": "full", "route": [], "mechanic_profiles": {}}],
        "diagnostic_scenarios": [
            {"id": "a", "route": [row("r.entry", "regroup"), row("r.a.boss", "boss", mechanic_profile="p1")],
             "mechanic_profiles": {"p1": ["adds"]}},
            {"id": "b", "route": [row("r.entry", "regroup"), row("r.b.boss", "boss", mechanic_profile="p2")],
             "mechanic_profiles": {"p2": ["raid_aoe"]}},
        ],
    }


def _base_composition() -> dict:
    return {
        "schema": composer.COMPOSITION_SCHEMA,
        "scenario_id": "full",
        "node_sets": [{"id": "a", "source_scenario_id": "a"}, {"id": "b", "source_scenario_id": "b"}],
    }


def test_composer_reports_duplicates_and_keeps_one_authoritative_order() -> None:
    composed = composer.compose(_base_config(), _base_composition())
    assert [row["node_id"] for row in composed.route] == ["r.entry", "r.a.boss", "r.b.boss"]
    assert [row["step"] for row in composed.route] == [1, 2, 3]
    assert composed.duplicates == [{"node_id": "r.entry", "kept_from": "a", "duplicate_in": "b"}]
    assert composed.mechanic_profiles == {"p1": ["adds"], "p2": ["raid_aoe"]}


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda c, s: c["diagnostic_scenarios"][1]["route"][0].update(x=2.0), "conflicting_rows:r.entry"),
        (lambda c, s: c["diagnostic_scenarios"][1]["mechanic_profiles"].update(p1=["stack"]), "mechanic_profile_conflict:p1"),
        (lambda c, s: c["diagnostic_scenarios"][1]["route"][1].update(kind="teleport"), "route_kind_not_executable"),
        (lambda c, s: c["diagnostic_scenarios"][1]["route"][1].update(node_id="Bad Id"), "node_id_invalid"),
        (lambda c, s: c["diagnostic_scenarios"][1]["route"][1].update(mechanic_profile="p9"), "mechanic_profile_missing:p9"),
        (lambda c, s: s["node_sets"].append({"id": "a", "source_scenario_id": "a"}), "node_set_id_invalid_or_duplicate:a"),
        (lambda c, s: s["node_sets"].append({"id": "x", "rows": [{"node_id": "r.x", "kind": "travel"}]}), "node_set_reason_missing:x"),
        (lambda c, s: s["node_sets"].append({"id": "x", "reason": "r", "rows": [{"step": 1, "node_id": "r.x", "kind": "travel"}]}), "inline_row_declares_step:x"),
        (lambda c, s: s["node_sets"].append({"id": "x", "source_scenario_id": "full"}), "node_set_source_invalid:x"),
        (lambda c, s: s["node_sets"].append({"id": "x", "source_scenario_id": "a", "rows": []}), "node_set_source_ambiguous:x"),
        (lambda c, s: s["node_sets"][0].update(node_ids=["r.nope"]), "node_set_node_missing:a:r.nope"),
        (lambda c, s: s.update(variants=[{"node_id": "r.a.boss", "set": {"x": 3.0}}]), "variant_reason_missing"),
        (lambda c, s: s.update(variants=[{"node_id": "r.none", "reason": "r", "set": {"x": 3.0}}]), "variant_node_missing"),
        (lambda c, s: s.update(variants=[{"node_id": "r.a.boss", "reason": "r", "set": {"x": 1.0}}]), "variant_noop:r.a.boss"),
        (lambda c, s: s.update(variants=[{"node_id": "r.a.boss", "reason": "r", "set": {"node_id": "r.z"}}]), "variant_identity_field"),
        (lambda c, s: s.update(variants=[{"node_id": "r.a.boss", "reason": "r", "unset": ["missing"]}]), "variant_unset_missing"),
        (lambda c, s: s.update(extra=True), "composition_unknown_field:extra"),
        (lambda c, s: s.update(schema="v0"), "composition_schema"),
    ],
)
def test_composer_fails_closed(mutate, reason: str) -> None:
    config = _base_config()
    composition = _base_composition()
    mutate(config, composition)
    with pytest.raises(composer.RaidRouteCompositionError, match=reason):
        composer.compose(config, composition)


def test_variants_change_only_declared_fields() -> None:
    composition = _base_composition()
    composition["variants"] = [{"node_id": "r.a.boss", "reason": "two tanks", "set": {"x": 5.0, "extra": [1]}}]
    composition["mechanic_profiles"] = {"p1": ["adds"]}
    composed = composer.compose(_base_config(), composition)
    boss = next(row for row in composed.route if row["node_id"] == "r.a.boss")
    assert boss["x"] == 5.0 and boss["extra"] == [1]
    assert composed.variants == [{"node_id": "r.a.boss", "reason": "two tanks", "changed_fields": ["extra", "x"]}]


def test_materialize_rewrites_only_the_target_blocks(tmp_path: Path) -> None:
    text = CONFIG.read_text(encoding="utf-8")
    config = json.loads(text)
    composed = composer.compose(config, _composition())
    # Idempotent on the committed file.
    assert composer.materialize_text(text, composed) == text

    stale = copy.deepcopy(composed)
    stale.route = stale.route[:-1]
    stale.route[-1] = {**stale.route[-1], "label": "changed"}
    rewritten = composer.materialize_text(text, stale)
    before_lines = text.splitlines()
    after_lines = rewritten.splitlines()
    full_route_lines = {
        index for index, line in enumerate(before_lines)
        if '"node_id": "bwd.' in line and index < before_lines.index('  "diagnostic_scenarios": [')
    }
    opcodes = [
        opcode for opcode in difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False).get_opcodes()
        if opcode[0] != "equal"
    ]
    assert opcodes
    for _, first, last, _, _ in opcodes:
        assert set(range(first, last)) <= full_route_lines
    assert len(after_lines) == len(before_lines) - 1
    reloaded = composer.scenarios_by_id(json.loads(rewritten))
    assert reloaded[FULL]["route"] == stale.route
    assert reloaded[MAGMAW_SHARD] == _scenario(config, MAGMAW_SHARD)

    config_path = tmp_path / "config.json"
    config_path.write_text(rewritten, encoding="utf-8")
    assert composer.main(["--config", str(config_path), "--composition", str(COMPOSITION), "--check"]) == 1
    assert composer.main(["--config", str(config_path), "--composition", str(COMPOSITION), "--write"]) == 0
    assert config_path.read_text(encoding="utf-8") == text
