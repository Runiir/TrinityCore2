"""Generate the compile-time all-spec admission identity authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
DEFAULT_GEAR_PROFILES = REPO_ROOT / "dataset/validation_gear_profiles/profiles.json"
DEFAULT_WOWSIMS_GEAR_PROFILES = (
    REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
)
DEFAULT_OUTPUT = REPO_ROOT / "src/server/game/Bots/BotAdmissionIdentityGenerated.h"
PET_GUID_BASE = 8_700_000
GENERATOR_SCHEMA = "bot_admission_identity_generated_v1"


class AdmissionIdentityGenerationError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_descriptor(
    targets_path: Path = DEFAULT_TARGETS,
    gear_profiles_path: Path = DEFAULT_GEAR_PROFILES,
    wowsims_gear_profiles_path: Path = DEFAULT_WOWSIMS_GEAR_PROFILES,
) -> dict[str, Any]:
    return {
        "schema": GENERATOR_SCHEMA,
        "pet_guid_base": PET_GUID_BASE,
        "sources": {
            "all_spec_targets_cata_p4_v1.json": _file_sha256(targets_path),
            "validation_gear_profiles/profiles.json": _file_sha256(
                gear_profiles_path
            ),
            "wowsims_cata_p4_gear_profiles.json": _file_sha256(
                wowsims_gear_profiles_path
            ),
        },
    }


def source_content_sha256(
    targets_path: Path = DEFAULT_TARGETS,
    gear_profiles_path: Path = DEFAULT_GEAR_PROFILES,
    wowsims_gear_profiles_path: Path = DEFAULT_WOWSIMS_GEAR_PROFILES,
) -> str:
    return canonical_sha256(source_descriptor(
        targets_path, gear_profiles_path, wowsims_gear_profiles_path
    ))


def load_gear_profiles(
    gear_profiles_path: Path,
    wowsims_gear_profiles_path: Path,
) -> dict[str, Any]:
    document = json.loads(gear_profiles_path.read_text(encoding="utf-8"))
    profiles = dict(document.get("profiles") or {})
    overlay = json.loads(wowsims_gear_profiles_path.read_text(encoding="utf-8"))
    slot_map = [int(slot) for slot in overlay.get("slot_map") or []]
    if not slot_map:
        raise AdmissionIdentityGenerationError("missing WoWSims slot map")
    for name, source_profile in (overlay.get("profiles") or {}).items():
        equipment: list[dict[str, Any]] = []
        for index, source_item in enumerate(source_profile.get("items") or []):
            if not source_item or int(source_item.get("id") or 0) <= 0:
                continue
            if index >= len(slot_map):
                raise AdmissionIdentityGenerationError(
                    f"{name}: WoWSims item exceeds slot map"
                )
            equipment.append(
                {
                    "slot": slot_map[index],
                    "item_id": int(source_item["id"]),
                    "enchant_id": int(source_item.get("enchant") or 0),
                    "reforge_id": int(source_item.get("reforging") or 0),
                    "gem_item_ids": [
                        int(gem) for gem in source_item.get("gems") or []
                    ],
                }
            )
        profiles[str(name)] = {"equipment": equipment}
    return profiles


def canonical_gear_manifest(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise AdmissionIdentityGenerationError(f"{label}: equipment must be a list")
    rows: list[dict[str, Any]] = []
    slots: set[int] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise AdmissionIdentityGenerationError(f"{label}: invalid equipment row")
        slot = raw.get("slot")
        item_id = raw.get("item_id")
        if isinstance(slot, bool) or not isinstance(slot, int) \
                or isinstance(item_id, bool) or not isinstance(item_id, int) \
                or slot < 0 or slot > 18 or slot in slots or item_id <= 0:
            raise AdmissionIdentityGenerationError(f"{label}: invalid slot/item identity")
        slots.add(slot)
        gems = raw.get("gem_item_ids") or []
        if not isinstance(gems, list) or any(
            isinstance(gem, bool) or not isinstance(gem, int) or gem < 0
            for gem in gems
        ):
            raise AdmissionIdentityGenerationError(f"{label}: invalid gem identity")
        normalized_gems = list(gems)
        while normalized_gems and normalized_gems[-1] == 0:
            normalized_gems.pop()
        rows.append(
            {
                "slot": slot,
                "item_id": item_id,
                "enchant_id": int(raw.get("enchant_id") or 0),
                "reforge_id": int(raw.get("reforge_id") or 0),
                "gem_item_ids": normalized_gems,
            }
        )
    rows.sort(key=lambda row: row["slot"])
    if len(rows) < 16:
        raise AdmissionIdentityGenerationError(f"{label}: incomplete equipment")
    return rows


def _talent_spell_ids(target: Mapping[str, Any], provisioning: Mapping[str, Any]) -> list[int]:
    talents = provisioning.get("talents")
    if not isinstance(talents, list):
        raise AdmissionIdentityGenerationError("missing provisioning talents")
    spell_ids: list[int] = []
    for row in talents:
        if not isinstance(row, Mapping):
            raise AdmissionIdentityGenerationError("invalid provisioning talent")
        spell_id = row.get("spell_id")
        if isinstance(spell_id, bool) or not isinstance(spell_id, int) or spell_id <= 0:
            raise AdmissionIdentityGenerationError("invalid provisioning talent spell")
        spell_ids.append(spell_id)
    spell_ids.sort()
    if not spell_ids or len(spell_ids) != len(set(spell_ids)):
        raise AdmissionIdentityGenerationError("empty or duplicate talent spell identity")
    declared = target.get("talent_build")
    if not isinstance(declared, Mapping):
        raise AdmissionIdentityGenerationError("missing declared talent build")
    declared_spells = sorted(
        int(row.get("spell_id") or 0)
        for row in declared.get("talents") or []
        if isinstance(row, Mapping)
    )
    if declared_spells != spell_ids:
        raise AdmissionIdentityGenerationError("declared/provisioned talent mismatch")
    return spell_ids


def _pet_identity(provisioning: Mapping[str, Any]) -> dict[str, Any] | None:
    pet = provisioning.get("pet")
    if pet is None:
        return None
    if not isinstance(pet, Mapping):
        raise AdmissionIdentityGenerationError("invalid pet identity")
    id_offset = pet.get("id_offset")
    entry = pet.get("entry")
    if isinstance(id_offset, bool) or not isinstance(id_offset, int) or id_offset <= 0 \
            or isinstance(entry, bool) or not isinstance(entry, int) or entry <= 0:
        raise AdmissionIdentityGenerationError("invalid pet id/entry")
    spellbook: list[tuple[int, int]] = []
    for raw in pet.get("spells") or []:
        if isinstance(raw, bool):
            raise AdmissionIdentityGenerationError("invalid pet spell")
        if isinstance(raw, int):
            spell_id, active = raw, 1
        elif isinstance(raw, Mapping):
            spell_id, active = raw.get("id"), raw.get("active", 1)
        else:
            raise AdmissionIdentityGenerationError("invalid pet spell")
        if isinstance(spell_id, bool) or not isinstance(spell_id, int) \
                or isinstance(active, bool) or not isinstance(active, int) \
                or spell_id <= 0 or active < 0 or active > 255:
            raise AdmissionIdentityGenerationError("invalid pet spell identity")
        spellbook.append((spell_id, active))
    spellbook.sort()
    if not spellbook or len({spell_id for spell_id, _ in spellbook}) != len(spellbook):
        raise AdmissionIdentityGenerationError("empty or duplicate pet spellbook")
    canonical = ";".join(f"{spell_id}:{active}" for spell_id, active in spellbook)
    return {
        "pet_id": PET_GUID_BASE + id_offset,
        "pet_entry": entry,
        "spellbook": spellbook,
        "spellbook_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def build_identity_catalog(
    targets_path: Path = DEFAULT_TARGETS,
    gear_profiles_path: Path = DEFAULT_GEAR_PROFILES,
    wowsims_gear_profiles_path: Path = DEFAULT_WOWSIMS_GEAR_PROFILES,
) -> dict[str, Any]:
    targets_document = json.loads(targets_path.read_text(encoding="utf-8"))
    gear_document = json.loads(gear_profiles_path.read_text(encoding="utf-8"))
    if targets_document.get("schema") != "all_spec_targets_cata_p4_v1":
        raise AdmissionIdentityGenerationError("unexpected target catalog schema")
    if gear_document.get("schema") != "bot_validation_gear_profiles_v1":
        raise AdmissionIdentityGenerationError("unexpected gear catalog schema")
    targets = targets_document.get("targets")
    profiles = load_gear_profiles(
        gear_profiles_path, wowsims_gear_profiles_path
    )
    if not isinstance(targets, list) or not isinstance(profiles, Mapping):
        raise AdmissionIdentityGenerationError("missing target/gear identities")

    identities: list[dict[str, Any]] = []
    seen_specs: set[str] = set()
    for target in targets:
        if not isinstance(target, Mapping):
            raise AdmissionIdentityGenerationError("invalid target row")
        spec = str(target.get("spec_target_id") or "")
        provisioning = target.get("provisioning_bot")
        if not re.fullmatch(r"[a-z0-9_]+", spec) or spec in seen_specs \
                or not isinstance(provisioning, Mapping):
            raise AdmissionIdentityGenerationError("invalid/duplicate target identity")
        seen_specs.add(spec)
        if str(target.get("runtime_join_key") or "") != spec \
                or str(provisioning.get("class_spec") or "") != spec:
            raise AdmissionIdentityGenerationError(f"{spec}: runtime identity mismatch")
        class_id = target.get("class_id")
        provisioned_class_id = provisioning.get("class")
        tree_id = provisioning.get("primary_talent_tree_id")
        if isinstance(class_id, bool) or not isinstance(class_id, int) or class_id <= 0 \
                or provisioned_class_id != class_id \
                or isinstance(tree_id, bool) or not isinstance(tree_id, int) or tree_id <= 0:
            raise AdmissionIdentityGenerationError(f"{spec}: class/tree identity mismatch")
        declared_tree_id = (target.get("talent_build") or {}).get(
            "primary_talent_tree_id"
        )
        if declared_tree_id != tree_id:
            raise AdmissionIdentityGenerationError(f"{spec}: declared tree mismatch")
        gear_profile_id = str(target.get("gear_profile_id") or "")
        if not gear_profile_id \
                or str(provisioning.get("gear_profile_id") or "") != gear_profile_id \
                or str(provisioning.get("gear_profile") or "") != gear_profile_id:
            raise AdmissionIdentityGenerationError(f"{spec}: gear profile mismatch")
        profile = profiles.get(gear_profile_id)
        if not isinstance(profile, Mapping):
            raise AdmissionIdentityGenerationError(f"{spec}: missing gear profile")
        gear_manifest = canonical_gear_manifest(
            profile.get("equipment"), label=f"{spec}:{gear_profile_id}"
        )
        identities.append(
            {
                "class_spec": spec,
                "class_id": class_id,
                "primary_talent_tree_id": tree_id,
                "talent_spell_ids": _talent_spell_ids(target, provisioning),
                "gear_profile_id": gear_profile_id,
                "gear_manifest_sha256": canonical_sha256(gear_manifest),
                "pet": _pet_identity(provisioning),
            }
        )
    if len(identities) != int(targets_document.get("target_count") or 0) \
            or len(identities) != 31:
        raise AdmissionIdentityGenerationError("all-spec catalog is incomplete")
    return {
        "schema": GENERATOR_SCHEMA,
        "source": source_descriptor(
            targets_path, gear_profiles_path, wowsims_gear_profiles_path
        ),
        "source_content_sha256": source_content_sha256(
            targets_path, gear_profiles_path, wowsims_gear_profiles_path
        ),
        "identities": identities,
    }


def render_header(catalog: Mapping[str, Any]) -> str:
    identities = catalog.get("identities")
    if not isinstance(identities, list):
        raise AdmissionIdentityGenerationError("missing generated identities")
    talent_ids: list[int] = []
    pet_spells: list[tuple[int, int]] = []
    rendered_rows: list[str] = []
    for identity in identities:
        talents = list(identity["talent_spell_ids"])
        pet = identity.get("pet")
        spellbook = list(pet["spellbook"]) if isinstance(pet, Mapping) else []
        talent_offset = len(talent_ids)
        pet_spell_offset = len(pet_spells)
        talent_ids.extend(talents)
        pet_spells.extend(spellbook)
        rendered_rows.append(
            "        { \"%s\", %u, %u, %u, %u, \"%s\", \"%s\", %u, %u, %u, %u, \"%s\" },"
            % (
                identity["class_spec"],
                identity["class_id"],
                identity["primary_talent_tree_id"],
                talent_offset,
                len(talents),
                identity["gear_profile_id"],
                identity["gear_manifest_sha256"],
                pet["pet_id"] if isinstance(pet, Mapping) else 0,
                pet["pet_entry"] if isinstance(pet, Mapping) else 0,
                pet_spell_offset,
                len(spellbook),
                pet["spellbook_sha256"] if isinstance(pet, Mapping) else "",
            )
        )
    talent_lines = [
        "        " + ", ".join(str(value) for value in talent_ids[index:index + 12]) + ","
        for index in range(0, len(talent_ids), 12)
    ]
    pet_lines = [
        "        " + ", ".join(
            f"{{ {spell_id}, {active} }}"
            for spell_id, active in pet_spells[index:index + 6]
        ) + ","
        for index in range(0, len(pet_spells), 6)
    ]
    descriptor = catalog["source"]
    targets_hash = descriptor["sources"]["all_spec_targets_cata_p4_v1.json"]
    gear_hash = descriptor["sources"]["validation_gear_profiles/profiles.json"]
    wowsims_gear_hash = descriptor["sources"][
        "wowsims_cata_p4_gear_profiles.json"
    ]
    return "\n".join(
        [
            "// Generated by tools/bot_ml/generate_bot_admission_identities.py.",
            "// Do not edit by hand; regenerate from the pinned all-spec catalogs.",
            "#ifndef TRINITY_BOT_ADMISSION_IDENTITY_GENERATED_H",
            "#define TRINITY_BOT_ADMISSION_IDENTITY_GENERATED_H",
            "",
            "#include <array>",
            "#include <cstdint>",
            "",
            "namespace BotAdmissionIdentityGenerated",
            "{",
            "struct PetSpellIdentity",
            "{",
            "    std::uint32_t SpellId;",
            "    std::uint8_t Active;",
            "};",
            "",
            "struct Identity",
            "{",
            "    char const* ClassSpec;",
            "    std::uint8_t ClassId;",
            "    std::uint32_t PrimaryTalentTreeId;",
            "    std::uint32_t TalentOffset;",
            "    std::uint32_t TalentCount;",
            "    char const* GearProfileId;",
            "    char const* GearManifestSha256;",
            "    std::uint32_t PetId;",
            "    std::uint32_t PetEntry;",
            "    std::uint32_t PetSpellOffset;",
            "    std::uint32_t PetSpellCount;",
            "    char const* PetSpellbookSha256;",
            "};",
            "",
            f"inline constexpr char SourceContentSha256[] = \"{catalog['source_content_sha256']}\";",
            f"inline constexpr char TargetsSourceSha256[] = \"{targets_hash}\";",
            f"inline constexpr char GearProfilesSourceSha256[] = \"{gear_hash}\";",
            f"inline constexpr char WowsimsGearProfilesSourceSha256[] = \"{wowsims_gear_hash}\";",
            "",
            f"inline constexpr std::array<std::uint32_t, {len(talent_ids)}> TalentSpellIds =",
            "{{",
            *talent_lines,
            "}};",
            "",
            f"inline constexpr std::array<PetSpellIdentity, {len(pet_spells)}> PetSpells =",
            "{{",
            *pet_lines,
            "}};",
            "",
            f"inline constexpr std::array<Identity, {len(identities)}> Identities =",
            "{{",
            *rendered_rows,
            "}};",
            "}",
            "",
            "#endif",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--gear-profiles", type=Path, default=DEFAULT_GEAR_PROFILES)
    parser.add_argument(
        "--wowsims-gear-profiles",
        type=Path,
        default=DEFAULT_WOWSIMS_GEAR_PROFILES,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rendered = render_header(build_identity_catalog(
        args.targets, args.gear_profiles, args.wowsims_gear_profiles
    ))
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("generated bot admission identity header is stale")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
