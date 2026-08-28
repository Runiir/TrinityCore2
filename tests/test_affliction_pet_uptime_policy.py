from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
PET_COMBAT = BOT_DIR / "BotWorldPopulationMgrAfflictionPetCombat.cpp"
EXECUTOR = BOT_DIR / "BotActionExecutor.cpp"
MIGRATION = ROOT / "sql/custom/world/2026_08_28_01_affliction_single_target_density.sql"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_affliction_density_migration_is_idempotent_and_single_target_only() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    assert "GREATEST(`version`, 5)" in migration
    assert "`action`.`max_enemies` = 0" in migration
    assert "`action`.`category` NOT IN ('aoe', 'cleave')" in migration
    for spell_id in (603, 172, 30108, 48181, 6353, 1120, 77799, 47897, 686):
        assert str(spell_id) in migration
    assert "DELETE" not in migration
    assert "INSERT" not in migration


def test_affliction_pet_attack_is_an_independent_native_candidate() -> None:
    pet_combat = PET_COMBAT.read_text(encoding="utf-8")
    start = pet_combat.index("BotClassSpecActionProfile const profile =")
    candidate = pet_combat[start:]

    assert 'profile.SpecTag != "affliction_warlock"' in candidate
    assert "BotActionArbitration::Resource::Pet" in candidate
    resources = candidate.split("petAttack.Attempt", 1)[0]
    assert "Resource::Target" not in resources
    assert "!context.Bot->IsInCombat() && !context.Target->IsInCombat()" in candidate
    assert "BotNativeAction::PetCommand" in candidate
    assert "ExecuteNativeActionIntent" in candidate
    for marker in (
        "context.Bot->GetPet()",
        "pet->IsInWorld()",
        "pet->IsAlive()",
        "pet->GetCharmerOrOwnerPlayerOrPlayerItself()",
        "pet->GetCharmInfo()",
        "pet->IsValidAttackTarget(target)",
        "COMMAND_ATTACK",
    ):
        assert marker in candidate
    assert "CastSpell" not in candidate
    assert "SetHealth" not in candidate
    assert "AddAura" not in candidate
    assert "BotWorldPopulationMgrAfflictionPetCombat.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )


def test_existing_combat_pet_command_uses_the_ordinary_primary_pet() -> None:
    executor = EXECUTOR.read_text(encoding="utf-8")
    start = executor.index(
        "// Command the player's primary pet through the same validated handler"
    )
    end = executor.index("if (Pet* pet = bot->GetPet())", start)
    command = executor[start:end]
    assert "Pet* pet = bot->GetPet()" in command
    assert "GetFirstControlled" not in command
    assert "HandlePetActionHelper" in command
    assert "IsCommandAttack()" in command
