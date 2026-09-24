"""Per-kill Magmaw 10N duty receipts from closed validation runs (human play mode, phase 0).

    pixi run python -m tools.raid_program.magmaw_duty_receipts --kill <tar-or-dir> [--kill ...] --output <json>

Each --kill is a closed run dir or a scoreboard evidence tarball. Only
latest.json and combat_log.json are read; from a tarball only those two
members are extracted into a temporary directory that is deleted afterwards.

  latest.json      the baiter_rotation object with the largest last_revision
                   (every bot's diagnosis carries a copy): primary/alternate
                   mage, hunter, per-wave history and completed waves.
  combat_log.json  action_outcomes rows on route node bwd.magmaw.encounter:
                   casters of Wild Mushroom (88747) and Detonate (88751), taunt
                   casters and spell ids, and casters of Bloodlust/Heroism/Time
                   Warp (2825/32182/80353) and Misdirection (34477); a duty with
                   no row is recorded as empty lists.

A caster is an actor with a successful cast row (phase "cast", result "ok" or
"casting"); actors with only failed rows are listed under attempted_by.

--fixture-label LABEL writes the magmaw_full_roster_duties_v1 fixture instead:
the kills are matched to that scoreboard label's records by run-dir name, and
the roster identity and a per-item consistency summary are added.
--receipts merges earlier outputs of this command, so a batch can be pulled,
read and evicted one tarball at a time.
"""
from __future__ import annotations

import argparse
import json
import re
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RECEIPTS_SCHEMA = "magmaw_duty_receipts_v1"
FIXTURE_SCHEMA = "magmaw_full_roster_duties_v1"
SCENARIO = "blackwing_descent_10n_magmaw"
ROUTE_SCENARIO = "blackwing_descent_10n_magmaw_diagnostic"
ENCOUNTER_NODE = "bwd.magmaw.encounter"
ROUTES_PATH = "dataset/validation_scenarios/validation_routes.jsonl"
WILD_MUSHROOM, DETONATE, MISDIRECTION = 88747, 88751, 34477
LUST_SPELLS = (2825, 32182, 80353)  # Bloodlust, Heroism, Time Warp
SUCCESS_RESULTS = frozenset({"ok", "casting"})
NEEDED = ("latest.json", "combat_log.json")
_MEMBER = re.compile(r"^(?:\./)?(?P<run>[^/]+)/(?P<file>latest\.json|combat_log\.json)$")
CODE_DERIVED = ["hook_riders", "pull_tank", "bloodlust_owner"]
# Present in each receipt but not evidence of absence: Bloodlust casts do not
# log an action_outcomes row, and Misdirection is cast on the Chainwielder
# node, outside the encounter-node filter.
UNOBSERVABLE = {
    "bloodlust_casters": "the Bloodlust path logs no action_outcomes row; see bloodlust_owner (code-derived)",
    "misdirection_casters": "cast on bwd.magmaw.chainwielder, outside the encounter-node filter",
}
CODE_DERIVED_NOTE = ("Not observable in these receipts (hook riders and the pull tank leave no action_outcomes "
                     "row, and the Bloodlust path does not log one); tests/test_magmaw_duty_plan.py derives them "
                     "from the code.")


def _walk_baiter_rotations(value: Any) -> list[dict[str, Any]]:
    found, stack = [], [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            rotation = node.get("baiter_rotation")
            if isinstance(rotation, dict):
                found.append(rotation)
            stack.extend(child for child in node.values() if isinstance(child, (dict, list)))
        elif isinstance(node, list):
            stack.extend(child for child in node if isinstance(child, (dict, list)))
    return found


def baiter_receipt(latest: dict[str, Any]) -> dict[str, Any] | None:
    """The newest baiter_rotation (largest last_revision), reduced to its duty fields."""
    rotations = _walk_baiter_rotations(latest)
    if not rotations:
        return None
    rotation = max(rotations, key=lambda row: int(row.get("last_revision") or 0))
    history = sorted((row for row in rotation.get("history") or [] if isinstance(row, dict)),
                     key=lambda row: int(row.get("wave") or 0))
    return {
        "primary_mage_guid": rotation.get("primary_mage_guid"),
        "alternate_mage_guid": rotation.get("alternate_mage_guid"),
        "hunter_guid": rotation.get("hunter_guid"),
        "completed_waves": rotation.get("completed_waves"),
        "last_revision": rotation.get("last_revision"),
        "history": [{"wave": row.get("wave"), "mage_guid": row.get("mage_guid"), "reason": row.get("reason")}
                    for row in history],
    }


def _spell_receipt(rows: list[dict[str, Any]]) -> dict[str, Any]:
    casters, attempted, casts, spells = set(), set(), 0, set()
    by_caster: defaultdict[int, set[int]] = defaultdict(set)
    for row in rows:
        actor = int(row.get("actor_guid") or 0)
        attempted.add(actor)
        if row.get("phase") == "cast" and row.get("result") in SUCCESS_RESULTS:
            casters.add(actor)
            casts += int(row.get("count") or 1)
            spell = int(row.get("spell_id") or 0)
            spells.add(spell)
            by_caster[actor].add(spell)
    return {"casters": sorted(casters), "cast_count": casts, "attempted_by": sorted(attempted - casters),
            "spell_ids": sorted(spells), "by_caster": {str(actor): sorted(ids) for actor, ids in sorted(by_caster.items())}}


def action_receipts(combat_log: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in combat_log.get("action_outcomes") or []
            if isinstance(row, dict) and row.get("route_node_id") == ENCOUNTER_NODE]

    def spell(*ids: int) -> list[dict[str, Any]]:
        return [row for row in rows if int(row.get("spell_id") or 0) in ids]

    return {
        "encounter_action_rows": len(rows),
        "wild_mushroom": _spell_receipt(spell(WILD_MUSHROOM)),
        "detonate": _spell_receipt(spell(DETONATE)),
        "taunt": _spell_receipt([row for row in rows if row.get("action_name") == "taunt"]),
        "bloodlust": _spell_receipt(spell(*LUST_SPELLS)),
        "misdirection": _spell_receipt(spell(MISDIRECTION)),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text()) if path.is_file() else None


def receipts_from_run_dir(run_dir: Path, source: str | None = None) -> dict[str, Any]:
    latest, log = _read_json(run_dir / "latest.json"), _read_json(run_dir / "combat_log.json")
    return {"source": source or str(run_dir), "run_dir_name": run_dir.name,
            "missing": [name for name, value in zip(NEEDED, (latest, log)) if value is None],
            "baiter_rotation": baiter_receipt(latest) if latest else None,
            **action_receipts(log or {})}


def extract_duty_receipts(run_dir_or_tarball: str | Path) -> dict[str, Any]:
    """Duty receipts of one closed run dir or scoreboard evidence tarball."""
    path = Path(run_dir_or_tarball)
    if path.is_dir():
        return receipts_from_run_dir(path)
    if not path.is_file():
        raise FileNotFoundError(f"no run dir or tarball at {path}")
    with tarfile.open(path, "r:*") as tar:
        members = [member for member in tar.getmembers() if member.isfile() and _MEMBER.match(member.name)]
        runs = sorted({_MEMBER.match(member.name)["run"] for member in members})
        if len(runs) > 1:
            raise ValueError(f"{path}: more than one run dir holds latest.json/combat_log.json: {runs}")
        with tempfile.TemporaryDirectory(prefix="magmaw-duty-receipts-") as temp:
            tar.extractall(temp, members=members, filter="data")
            run_dir = Path(temp) / (runs[0] if runs else "missing-run-dir")
            receipt = receipts_from_run_dir(run_dir, source=path.name)
    return receipt


# --- fixture -------------------------------------------------------------------------------------

def roster_identity(root: Path) -> list[dict[str, Any]]:
    for line in (root / ROUTES_PATH).read_text().splitlines():
        row = json.loads(line) if line.strip() else {}
        if row.get("scenario_id") == ROUTE_SCENARIO and row.get("route_node_id") == ENCOUNTER_NODE:
            return list(row["roster_identity"])
    raise ValueError(f"{ROUTES_PATH} has no {ROUTE_SCENARIO} {ENCOUNTER_NODE} roster_identity")


def _agreement(values: dict[str, Any]) -> dict[str, Any]:
    """value when every kill agrees; observed groups kill ids by each distinct value.

    For list values (casters, spell ids) a kill without any row is common (no taunt was
    needed), so consistent_when_present also compares only the kills that have one.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for kill_id, value in values.items():
        groups[json.dumps(value, sort_keys=True)].append(kill_id)
    consistent = len(groups) == 1 and None not in values.values()
    result = {"value": next(iter(values.values())) if consistent else None, "consistent": consistent,
              "observed": [{"value": json.loads(key), "kills": sorted(ids)} for key, ids in sorted(groups.items())]}
    if all(isinstance(value, list) for value in values.values()):
        present = [value for value in values.values() if value]
        result |= {"kills_with_value": len(present), "kills": len(values),
                   "union": sorted({item for value in present for item in value}),
                   "consistent_when_present": bool(present) and all(value == present[0] for value in present)}
    return result


def wave_alternation(baiter: dict[str, Any] | None) -> bool | None:
    """Wave 1 goes to the primary mage (reason initial), then the mage alternates every wave."""
    if not baiter or not baiter.get("history"):
        return None
    primary, alternate = baiter.get("primary_mage_guid"), baiter.get("alternate_mage_guid")
    for index, row in enumerate(baiter["history"]):
        expected = primary if index % 2 == 0 else alternate
        if row.get("wave") != index + 1 or row.get("mage_guid") != expected:
            return False
        if index == 0 and row.get("reason") != "initial":
            return False
    return primary != alternate


def evidence_confirmed(per_kill: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def field(pick) -> dict[str, Any]:
        return _agreement({kill_id: pick(receipt) for kill_id, receipt in per_kill.items()})

    def baiter(key):
        return lambda receipt: (receipt.get("baiter_rotation") or {}).get(key)

    return {
        "baiter_primary_mage_guid": field(baiter("primary_mage_guid")),
        "baiter_alternate_mage_guid": field(baiter("alternate_mage_guid")),
        "baiter_hunter_guid": field(baiter("hunter_guid")),
        "baiter_per_wave_alternation": field(lambda receipt: wave_alternation(receipt.get("baiter_rotation"))) | {
            "rule": "wave 1 primary mage (reason initial), then primary/alternate mage alternate every wave"},
        "baiter_completed_waves": field(baiter("completed_waves")),
        "wild_mushroom_casters": field(lambda receipt: receipt["wild_mushroom"]["casters"]),
        "detonate_casters": field(lambda receipt: receipt["detonate"]["casters"]),
        "taunt_casters": field(lambda receipt: receipt["taunt"]["casters"]),
        "taunt_spell_ids": field(lambda receipt: receipt["taunt"]["spell_ids"]),
    }


def _slim(receipt: dict[str, Any]) -> dict[str, Any]:
    """The fixture keeps casters, counts, attempts and spell ids; by_caster only where it adds information."""
    out = {key: value for key, value in receipt.items() if key not in ("source", "missing")}
    for duty in ("wild_mushroom", "detonate", "bloodlust", "misdirection"):
        out[duty] = {key: value for key, value in receipt[duty].items() if key != "by_caster"}
    return out


def build_fixture(root: Path, label: str, receipts: dict[str, dict[str, Any]],
                  scenario: str = SCENARIO) -> dict[str, Any]:
    """Match receipts (keyed by run-dir name) to the label's scoreboard kills and summarise them."""
    from tools.raid_program.scoreboard_core import label_kills, load_records
    kills = label_kills(load_records(root, scenario), label)
    if not kills:
        raise ValueError(f"no kills recorded under {label} in {scenario}")
    per_kill, missing = {}, []
    for record in kills:
        receipt = receipts.get(Path(str(record.get("run_dir"))).name)
        if receipt is None:
            missing.append(record["kill_id"])
            continue
        per_kill[record["kill_id"]] = _slim(receipt) | {
            "evidence_dvc_pointer": record.get("evidence_dvc_pointer"), "native_clear": record.get("native_clear")}
    if missing:
        raise ValueError(f"no receipts for kills {', '.join(missing)} of {label}")
    return {"schema": FIXTURE_SCHEMA, "scenario": scenario, "label": label,
            "route": {"scenario_id": ROUTE_SCENARIO, "route_node_id": ENCOUNTER_NODE},
            "caster_rule": "phase cast with result ok/casting on route node " + ENCOUNTER_NODE,
            "roster_identity": roster_identity(root), "per_kill": per_kill,
            "evidence_confirmed": evidence_confirmed(per_kill),
            "unobservable_in_receipts": UNOBSERVABLE,
            "code_derived_not_in_evidence": CODE_DERIVED, "code_derived_note": CODE_DERIVED_NOTE}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--kill", type=Path, action="append", default=[], help="closed run dir or evidence tarball")
    parser.add_argument("--receipts", type=Path, action="append", default=[],
                        help="earlier output of this command to merge (magmaw_duty_receipts_v1)")
    parser.add_argument("--fixture-label", help=f"write the {FIXTURE_SCHEMA} fixture for this scoreboard label")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.kill and not args.receipts:
        parser.error("give at least one --kill or --receipts")
    receipts: dict[str, dict[str, Any]] = {}
    for path in args.receipts:
        earlier = json.loads(path.read_text())
        if earlier.get("schema") != RECEIPTS_SCHEMA:
            parser.error(f"{path} is not {RECEIPTS_SCHEMA}")
        receipts.update(earlier["kills"])
    for path in args.kill:
        receipt = extract_duty_receipts(path)
        receipts[receipt["run_dir_name"]] = receipt
    if args.fixture_label:
        payload = build_fixture(args.root.resolve(), args.fixture_label, receipts)
    else:
        payload = {"schema": RECEIPTS_SCHEMA, "kills": dict(sorted(receipts.items()))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.output} ({len(receipts)} kill(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
