"""Load one canonical raid composition and resolve its per-boss spec selections.

A composition declares the characters of one raid size/difficulty. Each
character carries one or two catalog specs (two talent/glyph groups); the
per-boss `spec_selection` chooses which spec a boss shard activates before
login. Specs come only from the pinned all-spec target catalog.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.raid_program.raid_shard_identity import (
    MAX_BOSS_NUMBER,
    MAX_SLOTS,
    RAID_NAME_CODES,
    mode_info,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_DIR = REPO_ROOT / "experiments/configs/raid_compositions"
WOWSIMS_GEAR_PROFILES = REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
BASE_GEAR_PROFILES = REPO_ROOT / "dataset/validation_gear_profiles/profiles.json"
REFERENCE_REQUESTS = REPO_ROOT / "experiments/configs/wowsims_cata_dps_reference_requests_v1.json"
LEGACY_BWD_FIXTURE = REPO_ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
COMPOSITION_SCHEMA = "raid_composition_v1"
SELECTION_STATUSES = {"provisional", "accepted"}
ROLES = ("tank", "healer", "dps")


class CompositionError(ValueError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repo_path(reference: str) -> Path:
    path = Path(reference)
    return path if path.is_absolute() else REPO_ROOT / path


def load_catalog(composition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = read_json(repo_path(str(composition["spec_source"])))
    targets = payload.get("targets", [])
    if len(targets) != int(payload.get("target_count") or 0):
        raise CompositionError("spec_catalog_incomplete")
    return {str(row["spec_target_id"]): row for row in targets}


def catalog_bot(catalog: dict[str, dict[str, Any]], spec: str) -> dict[str, Any]:
    row = catalog.get(spec)
    if row is None:
        raise CompositionError(f"spec_missing_from_catalog:{spec}")
    bot = copy.deepcopy(row["provisioning_bot"])
    build = row.get("talent_build") or {}
    if (bot.get("class_spec") != spec
            or str(bot.get("gear_profile_id") or "") != str(row.get("gear_profile_id") or "")
            or not bot.get("gear_profile_id")
            or bot.get("gear_profile") != bot.get("gear_profile_id")):
        raise CompositionError(f"catalog_spec_identity_invalid:{spec}")
    for key in ("primary_talent_tree_id", "talents", "primary_tree_spells"):
        if key not in bot and key in build:
            bot[key] = copy.deepcopy(build[key])
        if key in build and bot.get(key) != build[key]:
            raise CompositionError(f"catalog_talent_build_drift:{spec}:{key}")
    if not bot.get("talents") or not int(bot.get("primary_talent_tree_id") or 0):
        raise CompositionError(f"catalog_spec_talents_missing:{spec}")
    return bot


def spec_role(catalog: dict[str, dict[str, Any]], spec: str) -> str:
    role = str(catalog[spec].get("role") or catalog[spec]["provisioning_bot"].get("role") or "")
    if role not in ROLES:
        raise CompositionError(f"catalog_spec_role_invalid:{spec}:{role}")
    return role


def validate_composition(composition: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Fail closed on any identity, spec, or per-boss selection defect."""
    failures: list[dict[str, Any]] = []
    if composition.get("schema") != COMPOSITION_SCHEMA:
        failures.append({"check": "schema"})
    raid = str(composition.get("raid") or "")
    if raid not in RAID_NAME_CODES:
        failures.append({"check": "raid", "raid": raid})
    try:
        size = int(mode_info(str(composition.get("mode")))["size"])
    except ValueError:
        size = 0
        failures.append({"check": "mode", "mode": composition.get("mode")})
    if int(composition.get("raid_size") or 0) != size or size > MAX_SLOTS:
        failures.append({"check": "raid_size", "expected": size, "actual": composition.get("raid_size")})
    if int(composition.get("talent_groups_count") or 0) != 2:
        failures.append({"check": "talent_groups_count_must_be_2"})
    characters = composition.get("characters") if isinstance(composition.get("characters"), list) else []
    if len(characters) != size:
        failures.append({"check": "character_count", "expected": size, "actual": len(characters)})
    keys = [str(row.get("character_key") or "") for row in characters]
    slots = [row.get("slot") for row in characters]
    if len(set(keys)) != len(keys) or any(not re.fullmatch(r"[a-z][a-z_]*", key) for key in keys):
        failures.append({"check": "character_keys", "keys": keys})
    if sorted(slot for slot in slots if isinstance(slot, int)) != list(range(1, len(characters) + 1)):
        failures.append({"check": "character_slots", "slots": slots})
    multi_spec: dict[str, list[str]] = {}
    for row in characters:
        key = str(row.get("character_key") or "")
        specs = [str(spec) for spec in row.get("specs") or []]
        if not 1 <= len(specs) <= 2 or len(set(specs)) != len(specs):
            failures.append({"check": "character_specs", "character_key": key, "specs": specs})
            continue
        try:
            bots = [catalog_bot(catalog, spec) for spec in specs]
            for spec in specs:
                spec_role(catalog, spec)
        except CompositionError as exc:
            failures.append({"check": "character_catalog_specs", "character_key": key, "reason": str(exc)})
            continue
        if len({int(bot["class"]) for bot in bots}) != 1:
            failures.append({"check": "character_specs_share_class", "character_key": key})
        if len({(int(bot["race"]), int(bot.get("gender", 0))) for bot in bots}) != 1:
            failures.append({"check": "character_specs_share_race_and_gender", "character_key": key})
        if len(specs) == 2:
            multi_spec[key] = specs
    bosses = composition.get("bosses") if isinstance(composition.get("bosses"), list) else []
    if not bosses:
        failures.append({"check": "bosses_missing"})
    for field in ("boss_key", "boss_number", "name_code"):
        values = [row.get(field) for row in bosses]
        if len(set(map(str, values))) != len(values):
            failures.append({"check": f"duplicate_boss_{field}"})
    aliases = [alias for row in bosses for alias in row.get("aliases") or []]
    if len(set(aliases)) != len(aliases) or set(aliases) & {row.get("boss_key") for row in bosses}:
        failures.append({"check": "boss_aliases_not_unique"})
    for row in bosses:
        boss = str(row.get("boss_key") or "")
        number = row.get("boss_number")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", boss):
            failures.append({"check": "boss_key", "boss_key": boss})
        if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= MAX_BOSS_NUMBER:
            failures.append({"check": "boss_number", "boss_key": boss})
        if not re.fullmatch(r"[a-z]{3}", str(row.get("name_code") or "")):
            failures.append({"check": "boss_name_code", "boss_key": boss})
        if row.get("selection_status") not in SELECTION_STATUSES:
            failures.append({"check": "selection_status", "boss_key": boss})
        selection = row.get("spec_selection") if isinstance(row.get("spec_selection"), dict) else {}
        if set(selection) != set(multi_spec):
            failures.append({"check": "spec_selection_characters", "boss_key": boss,
                             "expected": sorted(multi_spec), "actual": sorted(selection)})
        for key, spec in selection.items():
            if spec not in multi_spec.get(key, []):
                failures.append({"check": "spec_selection_value", "boss_key": boss, "character_key": key, "spec": spec})
        if not failures:
            counts = role_counts(composition, catalog, row)
            if counts["tank"] < 1 or counts["healer"] < 1 or sum(counts.values()) != size:
                failures.append({"check": "boss_role_counts", "boss_key": boss, "role_counts": counts})
    bag = composition.get("off_spec_bag") if isinstance(composition.get("off_spec_bag"), dict) else {}
    if (not int(bag.get("item_id") or 0) or int(bag.get("bag_slot") or 0) not in range(19, 23)
            or int(bag.get("container_slots") or 0) < 19):
        failures.append({"check": "off_spec_bag"})
    if failures:
        raise CompositionError(json.dumps({"composition_id": composition.get("composition_id"),
                                           "failures": failures}, sort_keys=True))
    return {"all_passed": True, "characters": len(characters), "bosses": len(bosses),
            "multi_spec_characters": sorted(multi_spec)}


def selected_specs(composition: dict[str, Any], boss: dict[str, Any]) -> dict[str, str]:
    selection = boss.get("spec_selection") or {}
    result = {}
    for row in composition["characters"]:
        key = str(row["character_key"])
        specs = [str(spec) for spec in row["specs"]]
        result[key] = str(selection[key]) if len(specs) > 1 else specs[0]
    return result


def role_counts(composition: dict[str, Any], catalog: dict[str, dict[str, Any]], boss: dict[str, Any]) -> dict[str, int]:
    counts = {role: 0 for role in ROLES}
    for spec in selected_specs(composition, boss).values():
        counts[spec_role(catalog, spec)] += 1
    return counts


def composition_specs(composition: dict[str, Any]) -> list[str]:
    specs: list[str] = []
    for row in composition["characters"]:
        for spec in row["specs"]:
            if spec not in specs:
                specs.append(str(spec))
    return specs


def legacy_bwd_specs(path: Path = LEGACY_BWD_FIXTURE) -> list[str]:
    if not Path(path).is_file():
        return []
    specs: list[str] = []
    for shard in read_json(path).get("shards", []):
        for bot in shard.get("bots", []):
            if bot.get("class_spec") and bot["class_spec"] not in specs:
                specs.append(str(bot["class_spec"]))
    return specs


def gear_coverage_report(
    specs: list[str],
    catalog: dict[str, dict[str, Any]],
    wowsims_payload: dict[str, Any],
    base_payload: dict[str, Any] | None,
    reference_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify each spec's gear authority without inventing gear.

    A spec is covered when its catalog gear profile is a pinned WoWSims P4
    preset. Otherwise the report records whether a heuristic
    player-acquisition profile exists, which is a gap to list, not fill.
    """
    wowsims = wowsims_payload.get("profiles", {})
    base = (base_payload or {}).get("profiles", {})
    references = {str(row.get("target_spec")) for row in (reference_payload or {}).get("requests", [])}
    rows: dict[str, Any] = {}
    for spec in specs:
        target = catalog.get(spec)
        if target is None:
            rows[spec] = {"authority": "missing_catalog_target", "covered": False}
            continue
        profile_id = str(target.get("gear_profile_id") or "")
        row: dict[str, Any] = {"gear_profile_id": profile_id, "role": target.get("role"),
                               "wowsims_dps_reference_request": spec in references}
        if profile_id in wowsims:
            source = wowsims[profile_id].get("source") or {}
            row.update({"authority": "wowsims_p4_preset", "covered": True,
                        "source_path": source.get("path"), "source_sha256": source.get("sha256"),
                        "provider_revision": source.get("commit")})
        elif profile_id in base:
            profile = base[profile_id]
            row.update({"authority": "heuristic_player_acquisition_profile", "covered": False,
                        "all_selected_items_player_accessible": profile.get("all_selected_items_player_accessible"),
                        "missing_slots": profile.get("missing_slots", [])})
        else:
            row.update({"authority": "missing_gear_profile", "covered": False})
        rows[spec] = row
    return {
        "schema": "raid_composition_gear_coverage_v1",
        "specs": rows,
        "covered": sorted(spec for spec, row in rows.items() if row.get("covered")),
        "gaps": sorted(spec for spec, row in rows.items() if not row.get("covered")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a raid composition and report its gear coverage.")
    parser.add_argument("--composition", type=Path, default=COMPOSITION_DIR / "blackwing_descent_10n.json")
    parser.add_argument("--include-legacy-bwd-specs", action="store_true")
    args = parser.parse_args()
    composition = read_json(args.composition)
    catalog = load_catalog(composition)
    summary = validate_composition(composition, catalog)
    specs = composition_specs(composition)
    if args.include_legacy_bwd_specs:
        specs += [spec for spec in legacy_bwd_specs() if spec not in specs]
    coverage = gear_coverage_report(
        specs, catalog, read_json(WOWSIMS_GEAR_PROFILES),
        read_json(BASE_GEAR_PROFILES) if BASE_GEAR_PROFILES.is_file() else None,
        read_json(REFERENCE_REQUESTS) if REFERENCE_REQUESTS.is_file() else None)
    per_boss = {row["boss_key"]: {"specs": selected_specs(composition, row),
                                  "role_counts": role_counts(composition, catalog, row),
                                  "selection_status": row["selection_status"]}
                for row in composition["bosses"]}
    print(json.dumps({"validation": summary, "per_boss": per_boss, "gear_coverage": coverage},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
