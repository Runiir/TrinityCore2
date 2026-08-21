from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationCohortGroup.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_cohort_group_module_is_bounded_and_registered():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationCohortGroup.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()


def test_validation_cohort_group_gate_is_not_left_in_monolith():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    signature = "void BotWorldPopulationMgr::EnsureValidationCohortGroup()"
    assert signature not in source
    assert signature in module


def test_validation_cohort_group_keeps_native_admission_receipts():
    module = MODULE.read_text()
    for marker in (
        "ServerProvisioningComplete",
        "AdmissionReceiptByGuid",
        "BotActionsEnabled",
        "validation_active_group_identity_drift",
        "ObserveActiveOrdinaryHunterPet",
    ):
        assert marker in module


def test_validation_cohort_group_adopts_leader_seed_group_before_creating():
    module = MODULE.read_text()
    assert "sBotMgr->FindSeedRaidGroupForLeader(leader->GetGUID())" in module
    assert "BotWorld validation cohort group adopted" in module
    assert "leader->SetGroup(group, group->GetMemberGroup(leader->GetGUID()))" in module
    # Adoption of an existing leader-owned seed group must be attempted
    # before any new-group creation fallback.
    assert module.index("FindSeedRaidGroupForLeader") < module.index("new Group()")
    assert "FindSeedRaidGroupForLeader" in (
        ROOT / "src/server/game/Bots/BotMgr.h"
    ).read_text()


def test_validation_cohort_group_reconciles_hunter_pet_against_frozen_receipt():
    module = MODULE.read_text()
    # Shard rosters own disjoint pet rows: the pinned hunter pet identity is
    # the cohort's own admission receipt, not the reference-world catalog row.
    assert "!LoadedBotMatchesPinnedHunterPet(member, row.ClassSpec)" in module
    assert "Diagnostic shards own disjoint pet rows" in module
    for marker in (
        "frozenPet.PetId == observedPet.PetId",
        "frozenPet.PetEntry == observedPet.PetEntry",
        "frozenPet.PetSpellCount == observedPet.Spellbook.size()",
        "frozenPet.PetSpellbook == observedPet.Spellbook",
        "frozenPet.PetSpellbookSha256 == observedPet.SpellbookSha256",
        '"validation_active_hunter_pet_admission_identity_drift"',
    ):
        assert marker in module
    assert "ResolveExpectedHunterPetIdentity" not in module
    assert '"validation_active_hunter_pet_canonical_identity_drift"' not in module
