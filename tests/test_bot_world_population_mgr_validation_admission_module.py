from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationAdmission.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_admission_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationAdmission.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    assert "BotWorldPopulationMgr::EnsureValidationRaidAdmission" in text
    assert "EnsureValidationRaidAdmission" in HEADER.read_text()


def test_population_controller_is_bounded_after_admission_split():
    text = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrPopulation.cpp").read_text()
    assert len(text.splitlines()) <= 1000
    assert "void BotWorldPopulationMgr::EnsurePopulation(" in text
    assert "EnsureValidationRaidAdmission(rosterPlan, expectedPopulation)" in text
    assert "BotWorldPopulationMgr::EnsurePopulation(" not in SOURCE.read_text()


def test_validation_admission_keeps_transaction_and_identity_contract():
    text = MODULE.read_text()
    for marker in (
        "validation_raid_admission_claim_failed",
        "validation_raid_admission_identity_drift",
        "validation_raid_preflight_exact_roster_missing",
        "validation_raid_preflight_initial_recovery_state",
        "validation_raid_admission_exact_group_or_alive_state_failed",
        "ValidationAdmissionBatchSealed",
        "ValidationRaidAdmissionComplete",
        "ValidationGhostCharacterFlag",
        "BotRaidAreaAuthority::SetAllOffenseSuppressed",
        "ProvisionWorldBotInGroup",
        "RecordRaidTelemetry",
        "rollbackAdmission",
    ):
        assert marker in text


def test_validation_admission_seeds_raid_leader_before_map_entry():
    text = MODULE.read_text()
    # The first planned member must seed the cohort raid instead of entering
    # a raid map ungrouped, which fails closed on CANNOT_ENTER_NOT_IN_RAID.
    assert "ProvisionWorldBotRaidSeed" in text
    assert "placementMap->IsRaid()" in text
    bot_mgr = (
        __import__("pathlib").Path("src/server/game/Bots/BotMgr.cpp").read_text()
    )
    assert "PlayerBot raid seed group created" in bot_mgr
    assert "seedRaidLeader" in bot_mgr
    assert "CANNOT_ENTER_NOT_IN_RAID && seedRaidLeader" in bot_mgr


def test_validation_admission_seed_divergence_fails_closed():
    bot_mgr = (
        __import__("pathlib").Path("src/server/game/Bots/BotMgr.cpp").read_text()
    )
    # After Group::Create the leader reference must still point at the seed;
    # divergence is logged with both guids and the seed is cleaned fail-closed.
    assert "bot->GetGroup() == seed" in bot_mgr
    assert "PlayerBot raid seed group diverged" in bot_mgr
    assert "sGroupMgr->RemoveGroup(seed)" in bot_mgr
    assert "_seedRaidGroupsByLeader" in bot_mgr
    # A diverged seed skips the re-entry probe so NOT_IN_RAID persists.
    assert "if (!seedDiverged)" in bot_mgr


def test_validation_admission_rollback_disbands_ghost_seed_group():
    text = MODULE.read_text()
    assert "FindSeedRaidGroupForLeader(spawnedGuids.front())" in text
    assert "ghostCohortGroup->Disband()" in text
    # The ghost disband runs only after every spawned bot was removed.
    assert text.index("RemoveWorldBot(*itr)") < text.index(
        "ghostCohortGroup->Disband()"
    )


def test_validation_admission_exact_state_failure_names_conditions():
    text = MODULE.read_text()
    # The post-loop verification must log one line per failing bot naming the
    # exact failed conditions instead of collapsing into an opaque rollback.
    assert 'TC_LOG_ERROR("server", "BotWorld validation raid admission exact state failed' in text
    for marker in (
        '"loaded_bot_missing"',
        '"not_in_world"',
        '"not_alive"',
        '"ghost_flag"',
        '"corpse"',
        '"native_group_missing"',
        '"cohort_not_locked"',
        '"map_mismatch:"',
        '"zero_instance_id"',
        '"horizontal_drift:"',
        '"vertical_drift:"',
        '"frozen_map_mismatch:"',
        '"frozen_instance_mismatch:"',
        "conditions=split_native_group",
    ):
        assert marker in text
    # Fail-closed semantics are unchanged: diagnostics precede the rollback.
    assert text.index("conditions=%s") < text.index(
        "validation_raid_admission_exact_group_or_alive_state_failed"
    )


def test_validation_seed_group_survives_native_map_entry():
    lfg_scripts = (
        ROOT / "src/server/game/DungeonFinding/LFGScripts.cpp"
    ).read_text()
    # The LFG solo-residue disband must not fire for non-LFG groups; a fresh
    # one-member raid seed would otherwise be disbanded inside AddPlayerToMap
    # and the cohort would split across two native instances.
    assert "group->isLFGGroup() && group->GetMembersCount() == 1" in lfg_scripts
