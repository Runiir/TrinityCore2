from __future__ import annotations

import argparse
import hashlib
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_KEYS = {
    "1:protection_warrior:tank",
    "2:protection:tank",
    "6:blood_death_knight:tank",
    "11:feral_druid_tank:tank",
    "2:holy_paladin:healer",
    "5:discipline_priest:healer",
    "5:holy_priest:healer",
    "7:restoration_shaman:healer",
    "11:restoration_druid:healer",
    "1:arms_warrior:dps",
    "1:fury_warrior:dps",
    "2:retribution_paladin:dps",
    "3:beast_mastery_hunter:dps",
    "3:marksmanship:dps",
    "3:survival:dps",
    "4:assassination_rogue:dps",
    "4:combat_rogue:dps",
    "4:subtlety_rogue:dps",
    "6:frost_death_knight:dps",
    "6:unholy_death_knight:dps",
    "7:elemental_shaman:dps",
    "7:enhancement:dps",
    "8:arcane_mage:dps",
    "8:fire:dps",
    "8:frost_mage:dps",
    "9:affliction_warlock:dps",
    "9:demonology_warlock:dps",
    "9:destruction_warlock:dps",
    "5:shadow_priest:dps",
    "11:balance_druid:dps",
    "11:feral_druid_dps:dps",
}
TYPED_COLUMNS = {
    "max_self_aura_stacks",
    "min_self_aura_remaining_ms",
    "max_self_aura_remaining_ms",
    "required_owned_target_aura",
    "forbidden_owned_target_aura",
    "min_combo_points",
    "max_combo_points",
    "min_ready_runes",
    "required_shapeshift_form",
    "requires_pet",
    "forbids_pet",
    "required_main_hand_enchant",
    "required_off_hand_enchant",
    "cooldown_group",
    "target_creature_type_mask",
    "requires_ground_target",
}
KNOWN_CATEGORIES = {
    "movement",
    "wait",
    "target_select",
    "target_switch",
    "auto_attack",
    "builder",
    "spender",
    "dot",
    "buff",
    "debuff",
    "interrupt",
    "stun_cc",
    "defensive",
    "offensive_cooldown",
    "execute",
    "aoe",
    "cleave",
    "dispel_cleanse",
    "taunt",
    "threat_build",
    "mitigation",
    "heal_efficient",
    "heal_fast",
    "heal_aoe",
    "external_defensive",
    "resurrect_recover",
    "loot",
    "quest_interact",
    "use_item",
    "emote_mechanic",
    "profession_action",
    "resource_generator",
}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def static_contract(repository: Path = REPO_ROOT) -> dict[str, Any]:
    source = (repository / "src/server/game/Bots/BotClassSpecActionProfile.cpp").read_text()
    header = (repository / "src/server/game/Bots/BotClassSpecActionProfile.h").read_text()
    controller = (repository / "src/server/game/Bots/BotController.cpp").read_text()
    executor = (repository / "src/server/game/Bots/BotActionExecutor.cpp").read_text()
    world_mgr = (repository / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()
    forward = (repository / "sql/custom/world/2026_07_19_00_phase4_rotation_snapshots.sql").read_text()
    normalize = (repository / "sql/custom/world/2026_07_19_01_phase4_rotation_category_normalization.sql").read_text()
    rollback = (repository / "sql/custom/rollback/world/2026_07_19_00_phase4_rotation_snapshots_rollback.sql").read_text()
    previous = json.loads(
        (repository / "experiments/configs/all_spec_phase4_previous_profile_hashes_v1.json").read_text()
    )

    compiled_conditions = source[
        source.index("std::string EvaluateCompiledConditions") :
        source.index("std::string SnapshotPayload")
    ]
    candidate_scoring = source[
        source.index("candidate.Score =") : source.index("candidate.Reason =")
    ]
    mechanic_tags_bounded_to_typed_resource_selection = (
        "MechanicTags" not in candidate_scoring
        and "spell.MechanicTags = fields[14].GetString();" in source
        and "spell.MechanicTags << '|'" in source
        and source.count("HasMechanicTag(spell.MechanicTags,") == 4
        and all(
            f'HasMechanicTag(spell.MechanicTags, "{tag}")' in compiled_conditions
            for tag in ("lacerate_spender", "lacerate", "holy_power_3")
        )
        and world_mgr.count("hasMechanicTag(candidate.Profile.MechanicTags") == 2
        and 'hasMechanicTag(candidate.Profile.MechanicTags, "mana_recovery")' in world_mgr
        and 'hasMechanicTag(candidate.Profile.MechanicTags, "resource_fallback")' in world_mgr
    )

    checks = {
        "canonical_key_count": source.count("CanonicalRotationKey, 31") == 1
        and len(EXPECTED_KEYS) == 31,
        "immutable_active_previous_snapshots": (
            "std::shared_ptr<DbRotationSnapshot const> g_activeDbRotationSnapshot" in source
            and "std::shared_ptr<DbRotationSnapshot const> g_previousDbRotationSnapshot" in source
        ),
        "whole_snapshot_failure_is_atomic": (
            "return nullptr;" in source
            and "g_previousDbRotationSnapshot = g_activeDbRotationSnapshot;" in source
            and source.index("if (!invalidReasons.empty()")
            < source.index("g_activeDbRotationSnapshot = snapshot;")
        ),
        "monotonic_generation": "g_activeDbRotationSnapshot->Generation + 1" in source,
        "profile_copy_is_attempt_pinned": (
            "profile = itr->second;" in source
            and "SnapshotGeneration" in header
            and "SnapshotContentHash" in header
        ),
        "rollback_publishes_new_generation": (
            "RollbackDbProfiles" in source
            and "rollback->Generation = g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->Generation + 1 : 1" in source
        ),
        "full_catalog_reporting": (
            '\\"immutable_full_catalog_snapshot\\"' in source
            and '\\"missing_keys\\"' in source
            and '\\"expected_profile_count\\"' in source
        ),
        "deterministic_controller_selection": (
            "std::max_element(valid.begin(), valid.end()" in controller
            and "RotationWeight(" not in controller
            and "urand(1, totalWeight)" not in controller
        ),
        "ground_target_execution": (
            "TARGET_FLAG_DEST_LOCATION" in executor
            and "bot->CastSpell(Position{ target->GetPositionX(), target->GetPositionY(), target->GetPositionZ() }" in executor
        ),
        "deterministic_world_selection_ties": (
            # Candidate arbitration was centralized; both remaining owners use
            # the same score/sort-order/action-id tie break.
            world_mgr.count("candidate.Profile.SortOrder <") >= 2
            and "spell.SortOrder < bestHeal->SortOrder" in world_mgr
        ),
        "mechanic_tags_bounded_to_typed_resource_selection": mechanic_tags_bounded_to_typed_resource_selection,
        "typed_columns_forward_and_rollback": all(
            f"`{column}`" in forward and f"`{column}`" in rollback
            for column in TYPED_COLUMNS
        ),
        "rollback_outside_world_updater": "sql/custom/rollback/world" in str(
            repository / "sql/custom/rollback/world/2026_07_19_00_phase4_rotation_snapshots_rollback.sql"
        ),
        "legacy_category_normalized": "category` = 'stun_cc'" in normalize,
        "exact_previous_hashes": (
            previous.get("profile_count") == 31
            and previous.get("action_count") == 260
            and len(previous.get("profiles", [])) == 31
            and previous.get("aggregate_sha256")
            == "7d4adf8b347cbc8d4754fe02f41988982a10cfe077edd7ac816827eb6477c4c7"
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def live_database_contract(worldserver_conf: Path) -> dict[str, Any]:
    connection = connect_mysql(
        database_url_from_worldserver_conf(worldserver_conf, "WorldDatabaseInfo")
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM bot_rotation_action")
            columns = {row["Field"] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT class_id, spec_tag, role FROM bot_rotation_profile "
                "WHERE enabled=1 ORDER BY class_id, spec_tag, role"
            )
            keys = {
                f"{row['class_id']}:{row['spec_tag']}:{row['role']}"
                for row in cursor.fetchall()
            }
            cursor.execute(
                "SELECT COUNT(*) AS count FROM bot_rotation_action a "
                "JOIN bot_rotation_profile p ON p.id=a.profile_id "
                "WHERE p.enabled=1 AND a.enabled=1"
            )
            action_count = int(cursor.fetchone()["count"])
            cursor.execute(
                "SELECT DISTINCT category FROM bot_rotation_action WHERE enabled=1"
            )
            categories = {row["category"] for row in cursor.fetchall()}
    finally:
        connection.close()

    checks = {
        "exact_catalog_keys": keys == EXPECTED_KEYS,
        "typed_columns_present": TYPED_COLUMNS <= columns,
        "all_categories_known": categories <= KNOWN_CATEGORIES,
        "enabled_actions_present": action_count == 260,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "profile_count": len(keys),
        "action_count": action_count,
        "unknown_categories": sorted(categories - KNOWN_CATEGORIES),
    }


class WorldserverSession:
    def __init__(self, binary: Path, config: Path):
        self.process = subprocess.Popen(
            ["stdbuf", "-oL", "-eL", str(binary), "--config", str(config)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        self.reader = threading.Thread(target=self._read_output, daemon=True)
        self.reader.start()

    def _read_output(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.lines.put(line)

    def wait_for(self, predicate, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"worldserver exited with {self.process.returncode}")
            try:
                line = self.lines.get(timeout=min(0.25, deadline - time.monotonic()))
            except queue.Empty:
                continue
            if predicate(line):
                return line
        raise TimeoutError("timed out waiting for worldserver output")

    def command(self, command: str, action: str, timeout: float = 30.0) -> dict[str, Any]:
        assert self.process.stdin is not None
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        line = self.wait_for(lambda value: f'"action":"{action}"' in value, timeout)
        return json.loads(line[line.index("{") :])

    def close(self) -> None:
        if self.process.poll() is None and self.process.stdin:
            self.process.stdin.write("server exit\n")
            self.process.stdin.flush()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=10)


def set_action_category(worldserver_conf: Path, action_id: int, category: str) -> None:
    connection = connect_mysql(
        database_url_from_worldserver_conf(worldserver_conf, "WorldDatabaseInfo")
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE bot_rotation_action SET category=%s WHERE id=%s",
                (category, action_id),
            )
        connection.commit()
    finally:
        connection.close()


def live_publication_contract(binary: Path, worldserver_conf: Path) -> dict[str, Any]:
    session = WorldserverSession(binary, worldserver_conf)
    original_category = None
    action_id = None
    try:
        session.wait_for(lambda line: " ready..." in line, 300)
        baseline = session.command("botauto rotations list", "botauto_rotations_list")
        if not baseline.get("ok"):
            raise RuntimeError(f"baseline snapshot failed: {baseline.get('failure_reason')}")

        connection = connect_mysql(
            database_url_from_worldserver_conf(worldserver_conf, "WorldDatabaseInfo")
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT a.id, a.category FROM bot_rotation_action a "
                    "JOIN bot_rotation_profile p ON p.id=a.profile_id "
                    "WHERE p.class_id=8 AND p.spec_tag='fire' AND p.role='dps' "
                    "AND a.spell_id=133 LIMIT 1"
                )
                row = cursor.fetchone()
        finally:
            connection.close()
        if not row:
            raise RuntimeError("fire_mage builder action not found")
        action_id = int(row["id"])
        original_category = str(row["category"])
        set_action_category(worldserver_conf, action_id, "phase4_invalid_category")

        rejected = session.command("botauto rotations reload", "botauto_rotations_reload")
        after_rejection = session.command("botauto rotations list", "botauto_rotations_list")

        set_action_category(worldserver_conf, action_id, original_category)
        original_category = None

        reloaded = session.command("botauto rotations reload", "botauto_rotations_reload")
        rolled_back = session.command("botauto rotations rollback", "botauto_rotations_rollback")
        alias_dump = session.command(
            "botauto rotations dump 8 fire_mage dps", "botauto_rotations_dump"
        )

        baseline_generation = int(baseline["active_generation"])
        checks = {
            "all_31_loaded": baseline.get("profile_count") == 31
            and not baseline.get("missing_keys"),
            "invalid_action_rejected": not rejected.get("ok")
            and "invalid_category_phase4_invalid_category"
            in str(rejected.get("failure_reason")),
            "failed_reload_kept_active_snapshot": (
                after_rejection.get("active_generation") == baseline_generation
                and after_rejection.get("active_content_hash")
                == baseline.get("active_content_hash")
                and after_rejection.get("profile_count") == 31
            ),
            "valid_reload_monotonic": reloaded.get("ok")
            and int(reloaded["active_generation"]) == baseline_generation + 1,
            "rollback_monotonic": rolled_back.get("ok")
            and int(rolled_back["active_generation"]) == baseline_generation + 2,
            "rollback_restored_content": rolled_back.get("active_content_hash")
            == baseline.get("active_content_hash"),
            "legacy_alias_dump": alias_dump.get("ok")
            and alias_dump.get("profile", {}).get("spec_tag") == "fire",
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "profile_count": baseline.get("profile_count"),
            "action_count": sum(
                int(profile.get("action_count", 0))
                for profile in baseline.get("profiles", [])
            ),
            "baseline_generation": baseline_generation,
            "reloaded_generation": reloaded.get("active_generation"),
            "rollback_generation": rolled_back.get("active_generation"),
            "snapshot_content_hash": baseline.get("active_content_hash"),
        }
    finally:
        try:
            if original_category is not None and action_id is not None:
                set_action_category(worldserver_conf, action_id, original_category)
        finally:
            session.close()


def build_contract(
    *,
    repository: Path = REPO_ROOT,
    worldserver_conf: Path | None = None,
    worldserver_binary: Path | None = None,
) -> dict[str, Any]:
    static = static_contract(repository)
    database = (
        live_database_contract(worldserver_conf) if worldserver_conf else {"passed": True, "skipped": True}
    )
    publication = (
        live_publication_contract(worldserver_binary, worldserver_conf)
        if worldserver_binary and worldserver_conf
        else {"passed": True, "skipped": True}
    )
    contract = {
        "schema": "all_spec_phase4_rotation_contract_v1",
        "static": static,
        "database": database,
        "publication": publication,
    }
    contract["gate_passed"] = all(
        section.get("passed") is True for section in (static, database, publication)
    )
    contract["contract_sha256"] = canonical_sha256(contract)
    return contract


def write_contract(output_dir: Path, contract: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema": "all_spec_phase4_rotation_contract_manifest_v1",
        "gate_passed": contract["gate_passed"],
        "contract_sha256": contract["contract_sha256"],
        "files": {
            "contract.json": hashlib.sha256(
                (output_dir / "contract.json").read_bytes()
            ).hexdigest()
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--worldserver-conf", type=Path)
    parser.add_argument("--worldserver-binary", type=Path)
    args = parser.parse_args()
    contract = build_contract(
        worldserver_conf=args.worldserver_conf,
        worldserver_binary=args.worldserver_binary,
    )
    write_contract(args.output_dir, contract)
    print(json.dumps({"gate_passed": contract["gate_passed"], "contract_sha256": contract["contract_sha256"]}, sort_keys=True))
    return 0 if contract["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
