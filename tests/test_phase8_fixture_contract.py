from __future__ import annotations

import hashlib
import re
from pathlib import Path

from tools.bot_ml.cata_dps_consumables import controlled_consumable_profile
from tools.bot_ml.phase8_fixture_contract import (
    DEFAULT_AUTHORED_CONTRACT_PATH,
    DEFAULT_MATERIALIZED_CONTRACT_PATH,
    DEFAULT_TARGET_CATALOG_PATH,
    LIFECYCLE_FINAL_FOR_OFFLINE_REFERENCE_GENERATION,
    LIFECYCLE_REQUIRES_GENERATION,
    build_materialized_fixture_contract,
    canonical_materialized_bytes,
    load_fixture_contract,
)


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotCalibrationFixtureContractGenerated.h"
UNIT = ROOT / "src/server/game/Entities/Unit/Unit.cpp"


def test_canonical_fixture_target_is_exact_passive_and_content_addressed() -> None:
    contract, digest = load_fixture_contract()
    assert contract["authority"]["lifecycle_status"] in {
        LIFECYCLE_REQUIRES_GENERATION,
        LIFECYCLE_FINAL_FOR_OFFLINE_REFERENCE_GENERATION,
    }
    assert contract["authority"][
        "promotion_requires_live_clean_state_receipt"
    ] is True
    target = contract["target"]
    assert target["entry"] == 44548
    assert target["level"] == 88
    assert target["armor"] == 11977
    assert target["creature_type"] == 9
    assert target["creature_type_name"] == "mechanical"
    assert target["simulator_mob_type"] == 7
    assert target["live_max_health"] == 1_000_000_000
    assert target["live_target_attacks"] is False
    assert all(
        target[key] == 0
        for key in (
            "simulator_attack_power",
            "simulator_swing_speed_seconds",
            "simulator_min_base_damage",
            "simulator_damage_spread",
        )
    )
    assert digest in HEADER.read_text(encoding="utf-8")


def test_every_spec_has_exact_native_start_and_controlled_consumables() -> None:
    contract, _digest = load_fixture_contract()
    for spec, row in contract["specs"].items():
        native = row["native_request"]
        assert native["professions"] == [
            "ProfessionUnknown",
            "ProfessionUnknown",
        ]
        assert native["player_fields"] == {"dark_intent_uptime": 0.0}
        transform = native["apl_transform_policy"]
        assert transform["policy"] == "recursive_remove_matching_action"
        assert transform["empty_node_policy"].startswith("remove_empty_")
        assert "OtherActionPotion" not in transform["forbidden_action_kinds"]
        assert "OtherActionSwapItem" not in transform["forbidden_action_kinds"]
        native_fields = {
            value["native_field"]
            for value in transform["forbidden_generic_operations"]
        }
        assert native_fields == {
            "autocast_other_cooldowns",
            "cast_all_stat_buff_cooldowns",
            "activate_all_stat_buff_proc_auras",
            "item_swap",
            "activate_aura",
            "activate_aura_with_stacks",
            "trigger_icd",
            "cancel_aura",
        }
        assert transform["forbidden_state_mutation_instances"] == [
            {"native_field": "activate_aura", "spell_id": 1784},
            {"native_field": "activate_aura", "spell_id": 74221, "tag": 2},
            {
                "native_field": "activate_aura_with_stacks",
                "spell_id": 96929,
                "stacks": 5,
            },
            {"native_field": "trigger_icd", "spell_id": 97125},
            {"native_field": "cancel_aura", "spell_id": 45529},
        ]
        assert transform["unlisted_state_mutation_instance_policy"] == "reject"
        assert {
            2825,
            10060,
            20572,
            26297,
            28730,
            33697,
            33702,
            69041,
            82174,
        } <= set(
            transform["forbidden_cast_spell_ids"]
        )
        profile = controlled_consumable_profile(spec)
        potion_item_id = profile["combat_potion"]["item_id"]
        assert transform["forbidden_cast_item_ids"] == sorted({
            36799,
            59461,
            62464,
            62469,
            68972,
            69002,
            69113,
            70142,
            77116,
        } | ({58091, 58145, 58146} - {potion_item_id}))
        assert transform["allowed_cast_item_ids"] == [potion_item_id]
        assert transform["unlisted_cast_item_policy"] == "reject"
        assert transform["prepull_replacement_policy"]["mode"] == (
            "replace_entire_source_with_fixture_exact_list"
        )
        assert transform["prepull_replacement_policy"][
            "source_prepull_policy"
        ] == "record_and_remove_all"
        condition_policy = transform["condition_rewrite_policy"]
        assert condition_policy["schema"] == (
            "phase8_exact_native_condition_payload_rewrite_v2"
        )
        assert condition_policy["matching_semantics"] == (
            "canonical_full_native_payload_equality"
        )
        leaves = condition_policy["unavailable_condition_leaves"]
        assert sum(len(leaf["payloads"]) for leaf in leaves) == 40
        assert all("id_kind" not in leaf and "ids" not in leaf for leaf in leaves)
        active_payloads = next(
            leaf["payloads"]
            for leaf in leaves
            if leaf["native_field"] == "aura_is_active"
        )
        assert {"aura_id": {"spell_id": 2825, "tag": -1}} in active_payloads
        assert {
            "aura_id": {"spell_id": 16511},
            "source_unit": {"type": "CurrentTarget"},
        } in active_payloads
        assert {"aura_id": {"spell_id": 16511}} not in active_payloads
        assert row["item_swap"] == {"enabled": False, "items": []}
        setup = row["prepull_setup"]
        assert setup["flask"]["item_id"] == profile["flask"]["item_id"]
        assert setup["food"]["item_id"] == profile["food"]["item_id"]
        assert setup["prepot"]["item_id"] == profile["prepot"]["item_id"]
        assert setup["combat_potion"]["item_id"] == potion_item_id
        assert native["consumables"] == {
            "battle_elixir_id": 0,
            "conjured_id": 0,
            "explosive_id": 0,
            "flask_id": profile["flask"]["item_id"],
            "food_id": profile["food"]["item_id"],
            "guardian_elixir_id": 0,
            "pot_id": potion_item_id,
            "prepot_id": profile["prepot"]["item_id"],
            "tinker_id": 0,
        }
        assert native["rotation_prepull_actions"][-1]["action"]["cast_spell"][
            "spell_id"
        ] == {"other_id": "OtherActionPotion"}
        assert row["prepull_setup"]["tinker"]["item_id"] == 0
        assert row["prepull_setup"]["racial"]["spell_id"] == 0, spec


def test_native_summoned_pet_identities_are_content_addressed_and_complete() -> None:
    contract, _digest = load_fixture_contract()
    expected = {
        "affliction_warlock": {
            "spell": 691,
            "entry": 417,
            "family": 15,
            "created_by": 691,
            "power_type": 0,
            "spellbook_sha256": "a79474903199c668e360560dde291357bfedd88f2369d72a9a0f47be1196b0cc",
            "autocasts": [19647, 54049, 54424],
        },
        "demonology_warlock": {
            "spell": 30146,
            "entry": 17252,
            "family": 29,
            "created_by": 30146,
            "power_type": 0,
            "spellbook_sha256": "1d412525118a6ef2ec72aa75977f9139e355d4998a902c42748e671c9d763005",
            "autocasts": [30151, 30213],
        },
        "unholy_death_knight": {
            "spell": 46584,
            "entry": 26125,
            "family": 40,
            "created_by": 52150,
            "power_type": 3,
            "spellbook_sha256": "a1d3751417bb084fee0205478cd3bbf3eded507a4247c91a2f67f839808694d2",
            "autocasts": [47468, 47481, 47482],
        },
    }
    for spec, identity in expected.items():
        authored = contract["specs"][spec]["pet_setup"]
        runtime = contract["specs"][spec]["runtime_expected"]["pet_setup"]
        assert authored["identity_evidence"] == {
            "dvc_pointer": "artifacts/all_spec_program/phase8_native_pet_identity_smoke_20260816.json.dvc",
            "artifact_sha256": "d81f32b74f68cdc3dd7de61b53446f12a087bf758dcabf78262f5878e533e695",
        }
        assert runtime["schema"] == "phase8_native_summoned_pet_identity_v1"
        assert runtime["runtime_projection_complete"] is True
        assert runtime["required_pet_spell_id"] == identity["spell"]
        assert runtime["required_pet_entry"] == identity["entry"]
        assert runtime["required_pet_family_id"] == identity["family"]
        assert runtime["required_pet_created_by_spell_id"] == identity["created_by"]
        assert runtime["required_pet_power_type"] == identity["power_type"]
        assert runtime["pet_spellbook_sha256"] == identity["spellbook_sha256"]
        assert runtime["pet_autocast_spell_ids"] == identity["autocasts"]
        assert runtime["pet_spellbook"]


def test_affliction_uses_the_short_ranged_shadowflame_lane() -> None:
    contract, _digest = load_fixture_contract()
    distance = contract["distance_contracts"]["short_ranged"]
    affliction = contract["specs"]["affliction_warlock"]

    assert distance == {
        "simulator_yards": 8.0,
        "runtime_min_yards": 7.5,
        "runtime_max_yards": 8.5,
    }
    assert affliction["lane"] == "short_ranged"
    assert affliction["simulator_options"]["starting_distance_yards"] == 8.0
    assert affliction["runtime_expected"]["target_distance"] == distance


def test_shadow_external_windows_are_exact_and_non_stochastic() -> None:
    contract, _digest = load_fixture_contract()
    external = contract["reference_environment"][
        "shadow_priest_external_windows"
    ]
    shadow = contract["specs"]["shadow_priest"]["native_request"]
    assert external["dark_intent_proc_uptime_pct"] == 0
    assert shadow["player_fields"]["dark_intent_uptime"] == 0.0
    assert external["dark_intent_base_enabled"] is False
    assert external["power_infusion_source_count"] == 0
    assert external["power_infusion_windows_ms"] == []
    assert "synapse_springs_spell_id" not in external
    assert "synapse_springs_windows_ms" not in external
    native_windows = shadow["external_windows"]
    assert native_windows == contract["specs"]["shadow_priest"][
        "runtime_expected"
    ]["external_windows"]
    assert native_windows["heroism"] == {
        "source_count": 0,
        "spell_id": 2825,
        "windows_ms": [],
    }
    assert native_windows["power_infusion"] == {
        "source_count": 0,
        "spell_id": 10060,
        "windows_ms": [],
    }
    assert native_windows["dark_intent_proc"] == {
        "base_spell_id": 85767,
        "base_enabled": False,
        "proc_spell_id": 85759,
        "uptime_pct": 0,
    }
    assert native_windows["synapse_springs"] == {
        "spell_id": 96230,
        "windows_ms": [],
    }


def test_materialized_fixture_is_canonical_and_reconstructs_without_ambient_reads(
    tmp_path: Path,
) -> None:
    payload = DEFAULT_MATERIALIZED_CONTRACT_PATH.read_bytes()
    contract, digest = load_fixture_contract(DEFAULT_MATERIALIZED_CONTRACT_PATH)
    assert payload == canonical_materialized_bytes(contract)
    assert digest == hashlib.sha256(payload).hexdigest()
    authority = contract["materialization"]
    assert set(authority["live_target_catalog"]["selected_rows"]) == set(
        contract["specs"]
    )
    assert authority["glyph_translation_authority"]["item_to_property"]
    assert authority["glyph_translation_authority"]["property_to_aura"]

    detached = tmp_path / "fixture.materialized.json"
    detached.write_bytes(payload)
    assert load_fixture_contract(detached)[1] == digest

    rebuilt = build_materialized_fixture_contract(
        DEFAULT_AUTHORED_CONTRACT_PATH,
        target_catalog_path=DEFAULT_TARGET_CATALOG_PATH,
    )
    assert canonical_materialized_bytes(rebuilt) == payload


def test_live_receipts_cover_target_resources_gear_and_external_windows() -> None:
    source = WORLD.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")
    for receipt in (
        '"fixture_contract"',
        '"observed_at_provisioning"',
        '"observed_before_scoring"',
        '"target_attack_observation_sample_count"',
        '"target_attack_event_count"',
        '"initial_resources"',
        '"item_swap_observation"',
        '"pre_score_state"',
        '"external_window_observation"',
        '"unexpected_active_samples"',
        '"pet_observed_owner_guid"',
        '"pet_observation_window_started_at_ms"',
        '"pet_last_observation_at_ms"',
        '"pet_admission_spellbook_sha256"',
        '"pet_first_observed_guid"',
        '"pet_guid_mismatch_sample_count"',
        '"pet_identity_mismatch_sample_count"',
        '"server_epoch"',
        '"attempt_id"',
        '"first_sample_at_ms"',
        '"last_sample_at_ms"',
        '"maximum_sample_gap_ms"',
        '"pet_maximum_observation_gap_ms"',
    ):
        assert receipt.replace('"', '\\"') in source
    assert "CalibrationFixtureTargetAttackEventCount" in source
    assert "CalibrationFixtureTargetOriginatedDamageEventCount" in source
    assert "NotifyCombatAttackAttempt(this, victim)" in unit
    assert "GearIdentityMismatchSampleCount" in source
    assert "UnexpectedDarkIntentProcSamples" in source
    assert "UnexpectedDarkIntentBaseSamples" in source
    assert "UnexpectedSynapseSpringsSamples" in source
    for spell_id in (2825, 10060, 85767, 85759, 96230):
        assert f"bot->AddAura({spell_id}, bot)" not in source
        assert f"bot->RemoveAurasDueToSpell({spell_id})" not in source


def test_live_reference_observation_covers_every_configured_setup_aura() -> None:
    contract, _digest = load_fixture_contract()
    required_setup_auras = {
        int(spell_id)
        for row in contract["specs"].values()
        for spell_id in row["prepull_setup"]["form_presence"][
            "required_aura_spell_ids"
        ]
    }
    source = WORLD.read_text(encoding="utf-8")
    match = re.search(
        r"PlayerAuraUniverse\s*=\s*\{(?P<body>.*?)\n\s*\};",
        source,
        flags=re.DOTALL,
    )
    assert match is not None
    body_without_comments = re.sub(r"//.*", "", match.group("body"))
    observed_aura_universe = {
        int(value) for value in re.findall(r"\b[1-9][0-9]*\b", body_without_comments)
    }
    assert required_setup_auras <= observed_aura_universe


def test_warlock_reference_requires_native_fel_armor() -> None:
    contract, _digest = load_fixture_contract()

    for spec in ("affliction_warlock", "demonology_warlock"):
        row = contract["specs"][spec]
        assert row["prepull_setup"]["form_presence"] == {
            "required_aura_spell_ids": [28176]
        }
        assert row["runtime_expected"]["form_presence"] == {
            "required_aura_spell_ids": [28176]
        }
        # WoWSims applies Fel Armor as a permanent class aura, so it must not
        # be represented by an extra simulator prepull cast.
        assert all(
            int(
                action.get("action", {})
                .get("cast_spell", {})
                .get("spell_id", {})
                .get("spell_id", 0)
            )
            != 28176
            for action in row["native_request"]["rotation_prepull_actions"]
        )


def test_disabled_racial_actions_are_counted_and_observed_if_they_leak() -> None:
    contract, _digest = load_fixture_contract()
    transform = next(iter(contract["specs"].values()))["native_request"][
        "apl_transform_policy"
    ]
    forbidden_cast_spells = set(transform["forbidden_cast_spell_ids"])
    disabled_racial_spells = {
        20572,
        26297,
        28730,
        33697,
        33702,
        58984,
        69041,
    }
    assert disabled_racial_spells <= forbidden_cast_spells

    source = WORLD.read_text(encoding="utf-8")

    def observed_array(name: str) -> set[int]:
        match = re.search(
            rf"{name}\s*=\s*\{{(?P<body>.*?)\n\s*\}};",
            source,
            flags=re.DOTALL,
        )
        assert match is not None
        body_without_comments = re.sub(r"//.*", "", match.group("body"))
        return {
            int(value)
            for value in re.findall(
                r"\b[1-9][0-9]*\b", body_without_comments
            )
        }

    assert disabled_racial_spells <= observed_array("PlayerAuraUniverse")
    assert disabled_racial_spells <= observed_array(
        "DisabledDynamicAuraUniverse"
    )
    assert disabled_racial_spells <= observed_array("DisabledRacialSpells")


def test_scored_bot_update_has_no_fixture_admin_state_manufacture() -> None:
    source = WORLD.read_text(encoding="utf-8")
    body = source.split(
        "void BotWorldPopulationMgr::UpdateCalibrationBot", 1
    )[1].split("\nvoid BotWorldPopulationMgr::", 1)[0]
    for forbidden in (
        "SetPower(",
        "SetHealth(",
        "SetFullHealth(",
        "AddAura(",
        "RemoveAurasDueToSpell(",
        "SummonCreature(",
        "LearnSpell(",
    ):
        assert forbidden not in body
    assert "Position{ target->GetPositionX()" not in body
