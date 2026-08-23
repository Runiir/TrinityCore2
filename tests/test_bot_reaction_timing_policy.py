from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
PROFILE_HEADER = (BOT_DIR / "BotClassSpecActionProfile.h").read_text(encoding="utf-8")
PROFILE_SOURCE = (BOT_DIR / "BotClassSpecActionProfile.cpp").read_text(encoding="utf-8")
CALIBRATION = (BOT_DIR / "BotWorldPopulationMgrCalibrationBot.cpp").read_text(encoding="utf-8")
PREPARATION = (
    BOT_DIR / "BotWorldPopulationMgrUpdateBotPreparation.cpp"
).read_text(encoding="utf-8")


def test_reaction_policy_is_canonical_and_preserves_pinned_specs() -> None:
    assert "ReactionTimeMsForSpec(char const* specTag)" in PROFILE_HEADER
    policy_start = PROFILE_SOURCE.index(
        "uint32 BotClassSpecActionProfileStore::ReactionTimeMsForSpec"
    )
    policy_end = PROFILE_SOURCE.index(
        "BotClassSpecActionProfile BotClassSpecActionProfileStore::BuildForSpec",
        policy_start,
    )
    policy = PROFILE_SOURCE[policy_start:policy_end]

    assert "CanonicalSpecTag" in policy
    for spec in ("affliction_warlock", "shadow_priest", "balance_druid"):
        assert f'"{spec}"' in policy
    assert "? 100 : 500" in policy


def test_calibration_and_ordinary_combat_share_spec_reaction_policy() -> None:
    assert (
        "ReactionTimeMsForSpec(\n            Cohort().CalibrationTargetSpec.c_str())"
        in CALIBRATION
    )
    assert "bool const fixtureReactionTime = reactionTimeMs == 100;" in CALIBRATION
    assert (
        "BotClassSpecActionProfileStore::Build(context.Bot, GetDungeonRole(context.Bot))"
        in PREPARATION
    )
    assert (
        "ReactionTimeMsForSpec(\n        cadenceProfile.SpecTag.c_str())" in PREPARATION
    )
    assert "responsiveSpecCombat" in PREPARATION
    assert "HasAura(15473)" not in PREPARATION


def test_policy_values_cover_affliction_shadow_balance_and_generic_fallback() -> None:
    responsive_specs = {"affliction_warlock", "shadow_priest", "balance_druid"}
    for spec in responsive_specs:
        assert spec in PROFILE_SOURCE
    assert "return canonicalSpecTag == \"affliction_warlock\"" in PROFILE_SOURCE
    assert "|| canonicalSpecTag == \"shadow_priest\"" in PROFILE_SOURCE
    assert "|| canonicalSpecTag == \"balance_druid\"" in PROFILE_SOURCE
    assert "? 100 : 500;" in PROFILE_SOURCE
