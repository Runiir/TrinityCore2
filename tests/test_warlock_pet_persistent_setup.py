import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
BOT_STATE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBotState.h"
CATALOG_BUILDER = ROOT / "tools/bot_ml/build_all_spec_phase1_catalogs.py"
AFFLICTION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrAffliction.cpp"
PERSISTENT_SETUP = ROOT / "src/server/game/Bots/BotWorldPopulationMgrPersistentSetup.cpp"
SEMANTIC = ROOT / "src/server/game/Bots/BotWorldPopulationMgrSemantic.cpp"
COMBAT_DIAGNOSTICS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatDiagnostics.cpp"
UPDATE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdate.cpp"
CALIBRATION_BOT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
CALIBRATION_BOT_JSON = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBotJson.cpp"
CALIBRATION_REFERENCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
CALIBRATION_RESET = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReset.cpp"
CALIBRATION_ROWS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationRows.cpp"
COMBAT_EXECUTION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatExecution.cpp"
COMBAT_NOTIFICATIONS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatNotifications.cpp"


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


def _source(*paths: Path) -> str:
    return "\n".join(path.read_text() for path in paths)


def test_warlock_pet_profiles_use_exact_ordinary_summons() -> None:
    source = PERSISTENT_SETUP.read_text()
    affliction = AFFLICTION.read_text()
    setup = _function_body(
        source, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )

    assert 'profile.SpecTag == "affliction_warlock"' in setup
    assert "requiredPet.RequiredSummonSpellId = 691" in affliction
    assert "requiredPet.RequiredCreatedBySpellId = 691" in affliction
    assert "requiredPet.RequiredEntry = ENTRY_FELHUNTER" in affliction
    assert "requiredPet.RequiredFamilyId = CREATURE_FAMILY_FELHUNTER" in affliction
    assert 'requiredPetName = "summon_felhunter"' in affliction

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
    assert '"affliction_warlock": [691, 28176]' in setup_spells
    assert '"demonology_warlock": [28176, 30146]' in setup_spells


def test_warlock_fel_armor_is_native_persistent_setup_and_observed() -> None:
    source = _source(PERSISTENT_SETUP, CALIBRATION_REFERENCE)
    setup = _function_body(
        source, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )

    assert '{ CLASS_WARLOCK, nullptr, nullptr, 28176, 28176, 0, "fel_armor" }' in setup
    assert "bot->HasSpell(buff.SpellId)" in setup
    assert "executor.ExecuteCombat(bot, bot, action)" in setup
    assert "46> PlayerAuraUniverse" in source
    assert re.search(r"PlayerAuraUniverse\s*=\s*\{.*?\b28176\b", source, re.DOTALL)


def test_warlock_pet_setup_is_learned_native_cast_not_manufacture() -> None:
    source = PERSISTENT_SETUP.read_text()
    setup = _function_body(
        source, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )
    native_pet = setup[
        setup.index("if (petSetup.RequiredSummonSpellId)") : setup.index(
            "if (bot->getClass() == CLASS_MAGE"
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
    source = _source(PERSISTENT_SETUP, SEMANTIC)
    header = _source(HEADER, BOT_STATE_HEADER)
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


def test_pre_score_resource_request_uses_one_real_native_resummon() -> None:
    source = _source(
        PERSISTENT_SETUP, SEMANTIC, BOT_STATE_HEADER, CALIBRATION_ROWS, UPDATE
    )
    setup = _function_body(
        source, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )
    native_pet = setup[
        setup.index("if (petSetup.RequiredSummonSpellId)") : setup.index(
            "// Mana Gem creation is optional consumable preparation"
        )
    ]
    finished = _function_body(
        source, "void BotWorldPopulationMgr::NotifyBotSpellFinished"
    )

    assert "preScoreResummonPending" in native_pet
    assert native_pet.count("&& !preScoreResummonPending") == 2
    assert "petSetup.PreScoreResummonSubmittedAtMs = nowMs;" in native_pet
    assert native_pet.index(
        "petSetup.PreScoreResummonSubmittedAtMs = nowMs;"
    ) < native_pet.index("executor.Execute(\n            bot, bot, nativeAction)")
    assert "petSetup.PreScoreResummonFinishedAtMs" in finished
    assert "petSetup.PreScoreResummonObservedAtMs = nowMs;" in native_pet
    assert "persistent_pre_score_pet_resummon_native_rejected_" in native_pet
    assert source.count("|| petSetup.PreScoreResummonObservedAtMs)") == 2
    assert "state.ReadinessRetryUntilMs[attemptKey]" in native_pet
    assert native_pet.index(
        "persistent_pre_score_pet_resummon_native_rejected_"
    ) < native_pet.index("state.ReadinessRetryUntilMs[attemptKey]")
    for key in (
        r'\"pet_pre_score_resummon\"',
        r'\"resource_before\"',
        r'\"resource_maximum_before\"',
        r'\"resource_after\"',
        r'\"resource_maximum_after\"',
    ):
        assert key in source


def test_final_resource_mismatch_requests_setup_without_submitting() -> None:
    reset = _function_body(
        CALIBRATION_RESET.read_text(),
        "void BotWorldPopulationMgr::ResetCalibrationScoredWindow",
    )
    final_boundary = reset[
        reset.index("bool consumablesSettled = true;") : reset.index(
            'if (Cohort().CalibrationMode == "single_target_300")',
            reset.index("bool consumablesSettled = true;"),
        )
    ]

    assert final_boundary.index("pet->UpdatePetScalingAuras();") < (
        final_boundary.index("ResetCalibrationInitialResources(bot, metrics);")
    )
    assert 'row.UnitKind == "pet"' in final_boundary
    assert "row.ExpectedMaximum" in final_boundary
    assert "row.ObservedNativeValue" in final_boundary
    assert "row.ObservedMaximumNativeValue" in final_boundary
    assert "petSetup.PreScoreResummonRequestedAtMs = NowMs();" in final_boundary
    assert "petSetup.NativeCastSubmittedAtMs = 0;" in final_boundary
    assert "persistentSetupRequested = true;" in final_boundary
    assert "executor.Execute" not in final_boundary


def test_affliction_calibration_accepts_exact_preexisting_felhunter_observation() -> None:
    source = _source(PERSISTENT_SETUP, COMBAT_DIAGNOSTICS, UPDATE)
    setup = _function_body(
        source, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"
    )
    native_pet = setup[
        setup.index("if (petSetup.RequiredSummonSpellId)") : setup.index(
            "// Mana Gem creation is optional consumable preparation"
        )
    ]

    # A calibration fixture may load the exact ordinary Felhunter before the
    # manager can observe a native summon receipt.  Admission remains scoped
    # to Affliction and still requires the learned spell plus the exact pet.
    assert "allowPreexistingAfflictionPet" in native_pet
    assert 'Cohort().CalibrationTargetSpec == "affliction_warlock"' in native_pet
    assert 'profile.SpecTag == "affliction_warlock"' in native_pet
    assert "petSetup.RequiredSummonSpellId == 691" in native_pet
    assert "petSetup.RequiredCreatedBySpellId == 691" in native_pet
    assert "petSetup.RequiredEntry == ENTRY_FELHUNTER" in native_pet
    assert "petSetup.SummonSpellKnown" in native_pet
    assert "OrdinaryPersistentPetMatches" in native_pet
    assert "state.LastRecoveryResult.clear()" in native_pet
    resolver = _function_body(
        source, "bool BotWorldPopulationMgr::TryResolveBotBlocker"
    )
    assert "persistent_preexisting_affliction_pet_observed" in resolver

    update = _function_body(source, "void BotWorldPopulationMgr::Update(uint32 diff)")
    readiness = update[
        update.index("bool const nativePetReady") : update.index(
            "if (populationReady && calibrationBot\n                && Cohort().CalibrationMode"
        )
    ]
    assert "preexistingAfflictionPetReady" in readiness
    assert "!petSetup.NativeCastSubmittedAtMs" in readiness
    assert "populationReady = nativePetReady || preexistingAfflictionPetReady;" in readiness


def test_previous_window_exposes_complete_live_pet_identity() -> None:
    source = _source(PERSISTENT_SETUP, CALIBRATION_BOT_JSON, CALIBRATION_ROWS)
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
    source = CALIBRATION_BOT.read_text()
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


def test_affliction_pet_diagnostic_separates_execution_state_and_damage_events() -> None:
    source = _source(
        CALIBRATION_BOT,
        COMBAT_NOTIFICATIONS,
        CALIBRATION_ROWS,
        CALIBRATION_BOT_JSON,
    )
    header = HEADER.read_text()

    # Pet health alone cannot explain a lower pet numerator. The scored
    # timeline must retain the native victim/command/current-spell state, while
    # damage events must identify the exact ordinary pet rather than any other
    # controlled unit owned by the warlock.
    for field in (
        "PetVictimGuid",
        "PetCurrentGenericSpellId",
        "PetCurrentChanneledSpellId",
        "PetCurrentAutorepeatSpellId",
        "PetCommandState",
        "PetCommandAttack",
        "PrimaryPetSpellDamage",
        "PrimaryPetSpellDamageEvents",
    ):
        assert field in header
    assert "capturePetTimelineState" in source
    assert "entry.PetVictimGuid = pet->GetVictim()" in source
    assert "entry.PetCommandAttack = charmInfo->IsCommandAttack()" in source
    assert "entry.PetCurrentAutorepeatSpellId" in source
    assert "bool const exactPetDamage = owner->GetPet() == attacker" in source
    assert "calibration->second.PrimaryPetSpellDamage[spellId]" in source
    assert '\\"pet_execution_observation\\"' in source
    assert '\\"primary_pet_spell_damage\\"' in source


def test_setup_precedes_calibration_scoring_and_normal_combat_resolution() -> None:
    source = _source(CALIBRATION_BOT, COMBAT_EXECUTION)
    calibration = _function_body(
        source, "void BotWorldPopulationMgr::UpdateCalibrationBot"
    )
    combat = _function_body(
        source, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction("
        "WorldBotState* state"
    )

    assert calibration.index("TryEnsurePersistentCombatSetup(state, bot, target,") < (
        calibration.index("metrics.WindowStartedMs = Cohort().CalibrationScoredStartedMs")
    )
    assert combat.index("TryEnsurePersistentCombatSetup(*state, bot, target)") < (
        combat.index("ResolveProfileCombatAction(")
    )
