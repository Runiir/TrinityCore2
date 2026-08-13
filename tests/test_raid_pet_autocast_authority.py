from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = (ROOT / "src/server/game/Bots/BotRaidAreaAuthority.h").read_text(encoding="utf-8")
PET_AI = (ROOT / "src/server/game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
EXECUTOR = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text(encoding="utf-8")
RUNTIME = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
BOT_MGR = (ROOT / "src/server/game/Bots/BotMgr.cpp").read_text(encoding="utf-8")


def test_raid_area_authority_is_transient_and_pet_ai_enforced():
    assert "inline std::unordered_set<uint64> SuppressedOwners" in AUTHORITY
    assert "BotRaidAreaAuthority::IsSuppressed(owner->GetGUID().GetRawValue())" in PET_AI
    assert "SpellHasHostileMultiTargetSemantics(spellInfo)" in PET_AI
    assert "BotRaidAreaAuthority::Set(ownerGuid, action.SuppressAreaDamage);" in EXECUTOR
    assert "BotRaidAreaAuthority::Clear(state.Guid.GetRawValue());" in RUNTIME
    assert "ToggleAutocast" not in PET_AI


def test_controlled_aoe_authority_stays_closed_until_live_release_gate():
    initial_gate = RUNTIME.index("bool const suppressAreaDamage = !raidAdapter.AllowAreaDamage")
    target_scan = RUNTIME.index("bool const controlledAoeReleased = raidAdapter.ContractResolved")
    release = RUNTIME.index("reconcileRaidAreaAutocasts(!controlledAoeReleased);")
    assert initial_gate < target_scan < release
    assert 'raidAdapter.TargetControl == "controlled_aoe";' in RUNTIME[
        initial_gate:target_scan
    ]


def test_every_world_bot_removal_clears_transient_owner_authority_first():
    lines = RUNTIME.splitlines()
    removal_lines = [index for index, line in enumerate(lines) if "sBotMgr->RemoveWorldBot(" in line]
    assert removal_lines
    for index in removal_lines:
        nearby = "\n".join(lines[max(0, index - 4):index])
        assert "BotRaidAreaAuthority::Clear(" in nearby


def test_central_bot_cleanup_clears_transient_owner_authority():
    cleanup = BOT_MGR[BOT_MGR.index("void BotMgr::CleanupBot("):]
    guard = cleanup.index("if (botGuid.IsEmpty()")
    clear = cleanup.index("BotRaidAreaAuthority::Clear(botGuid.GetRawValue());")
    teardown = cleanup.index("_worldBots.erase(botGuid);")
    assert guard < clear < teardown


def test_pet_ai_authority_does_not_mutate_persistent_pet_spell_state():
    marker = "BotRaidAreaAuthority::IsSuppressed(owner->GetGUID().GetRawValue())"
    authority_block = PET_AI[
        PET_AI.index(marker) - 80:
        PET_AI.index(marker) + 180
    ]
    assert "continue;" in authority_block
    assert "SetSpellAutocast" not in authority_block
    assert "ToggleCreatureAutocast" not in authority_block
    assert "ToggleAutocast" not in authority_block
