from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
SPELL = ROOT / "src/server/game/Spells/Spell.cpp"
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


def test_unholy_uses_learned_raise_dead_and_unholy_presence() -> None:
    builder = CATALOG_BUILDER.read_text(encoding="utf-8")
    setup_catalog = builder[
        builder.index("PERSISTENT_SETUP_SPELL_IDS = {") : builder.index(
            "RUNTIME_ACTION_SPELL_IDS = {"
        )
    ]
    assert '"unholy_death_knight": [46584, 48265]' in setup_catalog

    setup = _function_body(
        WORLD.read_text(encoding="utf-8"),
        "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup",
    )
    assert 'profile.SpecTag == "unholy_death_knight"' in setup
    assert (
        '{ CLASS_DEATH_KNIGHT, "dps", "unholy_death_knight", '
        '48265, 48265, 0, "unholy_presence" }'
    ) in setup
    assert "requiredPet.RequiredSummonSpellId = 46584" in setup
    assert "requiredPet.RequiredEntry = ENTRY_GHOUL" in setup
    assert "requiredPet.RequiredPetType = uint32(SUMMON_PET)" in setup
    assert "requiredPet.RequiredPowerType = uint32(POWER_ENERGY)" in setup
    assert "bot->HasAura(52143)" in setup
    assert "persistent_setup_unholy_master_of_ghouls_missing:52143" in setup


def test_unholy_pet_created_by_and_family_come_from_runtime_authority() -> None:
    setup = _function_body(
        WORLD.read_text(encoding="utf-8"),
        "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup",
    )
    assert "sObjectMgr->GetCreatureTemplate(" in setup
    assert "ENTRY_GHOUL)->family" in setup
    assert "sSpellMgr->GetSpellInfo(46584)" in setup
    assert "raiseDead->Effects[EFFECT_1].CalcValue(bot)" in setup
    assert "requiredPet.RequiredCreatedBySpellId" in setup
    assert "CREATURE_FAMILY_NONE" in setup


def test_native_pet_receipt_is_submit_finish_then_later_observation() -> None:
    world = WORLD.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    setup = _function_body(
        world, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )
    finished = _function_body(
        world, "void BotWorldPopulationMgr::NotifyBotSpellFinished"
    )

    assert "struct NativePersistentPetSetupReceipt" in header
    assert "NativeCastSubmittedAtMs" in header
    assert "NativeCastFinishedAtMs" in header
    assert "NativeCastObservedAtMs" in header
    assert "petSetup.NativeCastSubmittedAtMs = nowMs" in setup
    assert "executor.Execute(\n            bot, bot, nativeAction)" in setup
    assert "petSetup.RequiredSummonSpellId != spellId" in finished
    assert "petSetup.NativeCastFinishedAtMs = NowMs()" in finished
    assert "petSetup.NativeCastFinishedSuccessfully = success" in finished
    assert "petSetup.NativeCastObservedAtMs = nowMs" in setup
    assert "NotifyBotSpellFinished(playerCaster, m_spellInfo->Id, ok)" in SPELL.read_text(
        encoding="utf-8"
    )


def test_unholy_native_pet_setup_never_manufactures_or_refills_state() -> None:
    world = WORLD.read_text(encoding="utf-8")
    setup = _function_body(
        world,
        "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup",
    )
    native_pet = setup[
        setup.index("if (petSetup.RequiredSummonSpellId)") : setup.index(
            "if (bot->getClass() == CLASS_MAGE)"
        )
    ]
    assert "persistent_setup_preexisting_pet_without_native_receipt" in native_pet
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

    reset = _function_body(world, "void BotWorldPopulationMgr::ResetCalibrationScoredWindow")
    pet_reset = reset[
        reset.index("if (pet)") : reset.index(
            "std::vector<Unit*> controlledUnits"
        )
    ]
    assert "pet->SetFullHealth()" not in pet_reset
    assert 'std::string_view(unitKind) != "pet"' in reset


def test_unholy_pet_readiness_gates_scoring_and_emits_identity_uptime() -> None:
    world = WORLD.read_text(encoding="utf-8")
    update = _function_body(world, "void BotWorldPopulationMgr::Update(uint32 diff)")
    calibration = _function_body(
        world, "void BotWorldPopulationMgr::UpdateCalibrationBot"
    )

    assert 'CalibrationTargetSpec == "unholy_death_knight"' in update
    assert "calibrationState.PersistentPetSetup" in update
    assert "OrdinaryPersistentPetMatches(" in update
    assert update.index("calibrationState.PersistentPetSetup") < update.index(
        "ResetCalibrationScoredWindow()"
    )
    assert "++metrics.RequiredPetReadyTicks" in calibration
    assert "ObserveOrdinaryPetSetup(bot)" in calibration
    assert "CalibrationPetObservationReady(petObservation" in calibration

    for field in (
        "required_pet_created_by_spell_id",
        "required_pet_type",
        "required_pet_power_type",
        "pet_entry",
        "pet_family_id",
        "pet_type",
        "pet_created_by_spell_id",
        "pet_health",
        "pet_max_health",
        "pet_power_type",
        "pet_power",
        "pet_max_power",
        "pet_spellbook_sha256",
        "pet_spellbook",
        "pet_autocast_spell_ids",
        "pet_ready_ticks",
        "pet_observation_ticks",
        "pet_uptime_ratio",
    ):
        assert f'\\"{field}\\"' in world
