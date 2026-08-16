from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CATALOG_BUILDER = ROOT / "tools/bot_ml/build_all_spec_phase1_catalogs.py"


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def test_warlock_pet_profiles_use_exact_ordinary_summons() -> None:
    source = WORLD.read_text()
    setup = _function_body(
        source, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )

    assert 'profile.SpecTag == "affliction_warlock"' in setup
    assert "requiredPet.RequiredSummonSpellId = 691" in setup
    assert "requiredPet.RequiredCreatedBySpellId = 691" in setup
    assert "requiredPet.RequiredEntry = ENTRY_FELHUNTER" in setup
    assert "requiredPet.RequiredFamilyId = CREATURE_FAMILY_FELHUNTER" in setup
    assert 'requiredPetName = "summon_felhunter"' in setup

    assert 'profile.SpecTag == "demonology_warlock"' in setup
    assert "requiredPet.RequiredSummonSpellId = 30146" in setup
    assert "requiredPet.RequiredCreatedBySpellId = 30146" in setup
    assert "requiredPet.RequiredEntry = ENTRY_FELGUARD" in setup
    assert "requiredPet.RequiredFamilyId = CREATURE_FAMILY_FELGUARD" in setup
    assert 'requiredPetName = "summon_felguard"' in setup


def test_warlock_summons_are_canonical_persistent_setup_spells() -> None:
    builder = CATALOG_BUILDER.read_text()
    setup_spells = builder[
        builder.index("PERSISTENT_SETUP_SPELL_IDS = {") : builder.index(
            "RUNTIME_ACTION_SPELL_IDS = {"
        )
    ]
    assert '"affliction_warlock": [691]' in setup_spells
    assert '"demonology_warlock": [30146]' in setup_spells


def test_warlock_pet_setup_is_learned_native_cast_not_manufacture() -> None:
    source = WORLD.read_text()
    setup = _function_body(
        source, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )
    native_pet = setup[
        setup.index("if (petSetup.RequiredSummonSpellId)") : setup.index(
            "if (bot->getClass() == CLASS_MAGE)"
        )
    ]

    assert "bot->HasSpell(petSetup.RequiredSummonSpellId)" in setup
    assert "ResolvedBotAction nativeAction" in native_pet
    assert "executor.Execute(\n            bot, bot, nativeAction)" in native_pet
    assert "BotActionResult::Ok" in native_pet
    for forbidden in (
        "SummonCreature(",
        "SummonPet(",
        "AddAura(",
        "LearnSpell(",
        "learnSpell(",
        "SetHealth(",
        "SetFullHealth(",
        "SetPower(",
        "RemovePet(",
        "UnSummon(",
    ):
        assert forbidden not in native_pet


def test_warlock_pet_receipt_is_submit_finish_then_later_observation() -> None:
    source = WORLD.read_text()
    header = HEADER.read_text()
    setup = _function_body(
        source, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )
    finished = _function_body(
        source, "void BotWorldPopulationMgr::NotifyBotSpellFinished"
    )

    for field in (
        "NativeCastSubmittedAtMs",
        "NativeCastFinishedAtMs",
        "NativeCastFinishedSuccessfully",
        "NativeCastObservedAtMs",
    ):
        assert field in header
    assert "petSetup.RequiredSummonSpellId != spellId" in finished
    assert "petSetup.NativeCastFinishedAtMs = NowMs()" in finished
    assert "petSetup.NativeCastFinishedSuccessfully = success" in finished
    assert "petSetup.NativeCastObservedAtMs = nowMs" in setup
    assert "petSetup.NativeCastObservedAtMs\n                < petSetup.NativeCastFinishedAtMs" in setup


def test_previous_window_exposes_complete_live_pet_identity() -> None:
    source = WORLD.read_text()
    required_json_fields = {
        "required_pet_spell_id",
        "required_pet_created_by_spell_id",
        "required_pet_entry",
        "required_pet_family_id",
        "pet_spell_known",
        "pet_native_cast_submitted",
        "pet_native_cast_finished",
        "pet_native_cast_observed",
        "pet_native_cast_submitted_at_ms",
        "pet_native_cast_finished_at_ms",
        "pet_native_cast_observed_at_ms",
        "pet_guid",
        "pet_entry",
        "pet_family_id",
        "pet_type",
        "pet_created_by_spell_id",
        "pet_present",
        "pet_in_world",
        "pet_alive",
        "pet_owned",
        "pet_permanent",
        "pet_health",
        "pet_max_health",
        "pet_power_type",
        "pet_power",
        "pet_max_power",
        "pet_ready_ticks",
        "pet_observation_ticks",
        "pet_uptime_ratio",
        "pet_spellbook_sha256",
        "pet_spellbook",
        "pet_autocast_spell_ids",
    }
    for field in required_json_fields:
        assert f'\\"{field}\\"' in source

    observation = source[
        source.index("OrdinaryPetSetupSnapshot ObserveOrdinaryPetSetup") :
        source.index("bool OrdinaryPersistentPetMatches")
    ]
    assert "pet->GetOwner() == bot" in observation
    assert "pet->IsPermanentPetFor" in observation
    assert "pet->getPetType() == SUMMON_PET" in observation
    assert "snapshot.PetType = uint32(pet->getPetType())" in observation
    assert "pet->m_spells" in observation
    assert "pet->m_autospells" in observation


def test_scored_window_observes_required_pet_uptime_without_repair() -> None:
    source = WORLD.read_text()
    header = HEADER.read_text()
    calibration = _function_body(
        source, "void BotWorldPopulationMgr::UpdateCalibrationBot"
    )

    assert "uint32 RequiredPetReadyTicks = 0" in header
    assert "++metrics.TickCount" in calibration
    assert "++metrics.RequiredPetReadyTicks" in calibration
    assert "ObserveOrdinaryPetSetup(bot)" in calibration
    assert "CalibrationPetObservationReady(petObservation" in calibration
    for forbidden in ("SummonPet(", "SetHealth(", "SetPower(", "AddAura("):
        assert forbidden not in calibration


def test_setup_precedes_calibration_scoring_and_normal_combat_resolution() -> None:
    source = WORLD.read_text()
    calibration = _function_body(
        source, "void BotWorldPopulationMgr::UpdateCalibrationBot"
    )
    combat = _function_body(
        source, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction("
        "WorldBotState* state"
    )

    assert calibration.index("TryEnsurePersistentCombatSetup(state, bot, target)") < (
        calibration.index("metrics.WindowStartedMs = Cohort().CalibrationScoredStartedMs")
    )
    assert combat.index("TryEnsurePersistentCombatSetup(*state, bot, target)") < (
        combat.index("ResolveProfileCombatAction(")
    )
