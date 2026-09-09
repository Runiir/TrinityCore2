from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from tools.bot_ml.generate_bot_admission_identities import (
    DEFAULT_GEAR_PROFILES,
    DEFAULT_OUTPUT,
    DEFAULT_TARGETS,
    DEFAULT_WOWSIMS_GEAR_PROFILES,
    build_identity_catalog,
    render_header,
    source_content_sha256,
)


ROOT = Path(__file__).resolve().parents[1]


def test_generated_admission_identity_header_is_byte_identical_and_source_bound() -> None:
    catalog = build_identity_catalog()
    checked_in = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    assert render_header(catalog) == checked_in
    assert len(catalog["identities"]) == 31
    assert len({row["class_spec"] for row in catalog["identities"]}) == 31
    assert all(row["talent_spell_ids"] for row in catalog["identities"])
    assert all(len(row["gear_manifest_sha256"]) == 64 for row in catalog["identities"])
    assert sum(row["pet"] is not None for row in catalog["identities"]) == 3

    source_match = re.search(
        r'SourceContentSha256\[\] = "([0-9a-f]{64})"', checked_in
    )
    assert source_match
    assert source_match.group(1) == source_content_sha256()
    assert source_match.group(1) == catalog["source_content_sha256"]
    expected_file_hashes = {
        "all_spec_targets_cata_p4_v1.json": hashlib.sha256(
            DEFAULT_TARGETS.read_bytes()
        ).hexdigest(),
        "validation_gear_profiles/profiles.json": hashlib.sha256(
            DEFAULT_GEAR_PROFILES.read_bytes()
        ).hexdigest(),
        "wowsims_cata_p4_gear_profiles.json": hashlib.sha256(
            DEFAULT_WOWSIMS_GEAR_PROFILES.read_bytes()
        ).hexdigest(),
    }
    assert catalog["source"]["sources"] == expected_file_hashes


def test_any_pinned_source_byte_change_requires_header_regeneration(
    tmp_path: Path,
) -> None:
    changed_targets = tmp_path / "all_spec_targets.json"
    document = json.loads(DEFAULT_TARGETS.read_text(encoding="utf-8"))
    document["source_revision"] = str(document.get("source_revision") or "") + ":drift"
    changed_targets.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    changed_catalog = build_identity_catalog(
        changed_targets, DEFAULT_GEAR_PROFILES, DEFAULT_WOWSIMS_GEAR_PROFILES
    )
    assert changed_catalog["source_content_sha256"] != source_content_sha256()
    assert render_header(changed_catalog) != DEFAULT_OUTPUT.read_text(encoding="utf-8")


def test_native_admission_uses_only_the_generated_all_spec_table() -> None:
    # Admission consumers were split out of the manager translation unit.
    # Keep the contract over all manager modules, including forbidden copies.
    modules = sorted((ROOT / "src/server/game/Bots").glob("BotWorldPopulationMgr*.cpp"))
    assert modules
    source = "\n".join(path.read_text(encoding="utf-8") for path in modules)
    assert '#include "Bots/BotAdmissionIdentityGenerated.h"' in source
    assert "BotAdmissionIdentityGenerated::Identities" in source
    assert "BotAdmissionIdentityGenerated::TalentSpellIds" in source
    assert "BotAdmissionIdentityGenerated::PetSpells" in source
    assert "BotAdmissionIdentityGenerated::SourceContentSha256" in source
    assert "struct ExpectedBotSpecIdentity" not in source
    assert "struct ExpectedBotGearIdentity" not in source
    assert "petId = 8700113" not in source


def test_hunter_producer_provisioning_and_admission_pin_native_saved_fixed_point() -> None:
    from tools.bot_ml.build_all_spec_phase1_catalogs import pet_for
    from tools.bot_ml.build_validation_provisioning import build_character_insert_sql

    expected_spellbook = [
        (1742, 193), (2649, 193), (17253, 193), (23145, 193),
        (24604, 193), (53184, 1), (53186, 1), (53205, 1),
        (53401, 193), (53434, 193), (61681, 1), (61683, 1),
        (62760, 1), (65220, 1),
    ]
    expected_autocasts = [1742, 2649, 17253, 23145, 24604, 53401, 53434]
    expected_actionbar = "7 2 7 1 7 4 193 2649 193 17253 193 23145 193 53401 6 3 6 1 6 0"
    canonical = ";".join(f"{spell}:{active}" for spell, active in expected_spellbook)
    expected_digest = "bc3322f102216e3308dc94e4fa30e2960641678949109ccbda1a90063e684ce8"
    assert hashlib.sha256(canonical.encode()).hexdigest() == expected_digest
    identities = {row["class_spec"]: row for row in build_identity_catalog()["identities"]}
    targets = json.loads(DEFAULT_TARGETS.read_text())["targets"]
    hunters = [row for row in targets if row["class_name"] == "hunter"]
    assert {row["spec_target_id"] for row in hunters} == {
        "beast_mastery_hunter", "marksmanship_hunter", "survival_hunter",
    }
    for target in hunters:
        spec = target["spec_target_id"]
        bot = target["provisioning_bot"]
        pet = bot["pet"]
        assert pet == pet_for(spec, pet["id_offset"] - 100)
        assert pet["actionbar"] == expected_actionbar
        assert len(pet["actionbar"].split()) == 20
        identity = identities[spec]["pet"]
        assert identity["spellbook"] == expected_spellbook
        assert identity["spellbook_sha256"] == expected_digest
        assert [spell for spell, active in identity["spellbook"] if active == 193] == expected_autocasts
        sql = build_character_insert_sql({
            "pet_guid_base": 8700000,
            "scenarios": [{
                "id": "all_spec_candidate_pool",
                "start_position": {"map_id": 0, "x": 1, "y": 2, "z": 3},
                "bots": [bot],
            }],
        })
        pet_insert = next(line for line in sql.splitlines()
                          if line.startswith("INSERT INTO `characters`.`character_pet`"))
        assert f"UNIX_TIMESTAMP(), '{expected_actionbar}' FROM" in pet_insert
        persisted_spells = [
            (int(match[1]), int(match[2]))
            for match in re.finditer(
                rf"INSERT INTO `characters`.`pet_spell` .*?VALUES \({identity['pet_id']}, (\d+), (\d+)\)", sql
            )
        ]
        assert sorted(persisted_spells) == expected_spellbook


def test_calibration_pet_consumers_keep_exact_spellbook_digest_and_autocast_checks() -> None:
    # These unchanged comparisons reject missing/extra ordinary rows, altered
    # active bytes, digest drift, and different autocast membership on load.
    for module in ("Reset", "Bot", "Completion"):
        source = (ROOT / f"src/server/game/Bots/BotWorldPopulationMgrCalibration{module}.cpp").read_text()
        start = source.index("bool LoadedBotMatchesPinnedHunterPet(")
        body = source[start:source.index("\n}", start)]
        assert "&& observed.Spellbook == expectedSpellbook" in body
        assert "&& observed.SpellbookSha256 == HunterPetSpellbookSha256(expectedSpellbook)" in body
        assert "&& observed.AutocastSpellIds == expectedAutocastSpellIds" in body
        assert "if (active == ACT_ENABLED)" in body
