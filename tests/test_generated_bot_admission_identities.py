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
    source = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
    ).read_text(encoding="utf-8")
    assert '#include "Bots/BotAdmissionIdentityGenerated.h"' in source
    assert "BotAdmissionIdentityGenerated::Identities" in source
    assert "BotAdmissionIdentityGenerated::TalentSpellIds" in source
    assert "BotAdmissionIdentityGenerated::PetSpells" in source
    assert "BotAdmissionIdentityGenerated::SourceContentSha256" in source
    assert "struct ExpectedBotSpecIdentity" not in source
    assert "struct ExpectedBotGearIdentity" not in source
    assert "petId = 8700113" not in source
