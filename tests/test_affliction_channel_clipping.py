from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE_HEADER = ROOT / "src/server/game/Bots/BotClassSpecActionProfile.h"
PROFILE = ROOT / "src/server/game/Bots/BotClassSpecActionProfile.cpp"
TYPES = ROOT / "src/server/game/Bots/BotTypes.h"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
SQL = ROOT / "sql/custom/world/2026_08_23_04_affliction_interruptible_channel_clipping.sql"


def may_clip_channel(
    active_channel_spell: int | None,
    active_channel_is_tagged: bool,
    active_channel_priority: int,
    candidate_spell: int,
    candidate_priority: int,
) -> bool:
    """Mirror the declarative boundary used by BuildCandidates."""

    return bool(
        active_channel_spell
        and active_channel_is_tagged
        and candidate_spell != active_channel_spell
        and candidate_priority < active_channel_priority
    )


def test_channel_clipping_boundaries_are_strict() -> None:
    assert may_clip_channel(1120, True, 9, 77799, 8)
    assert not may_clip_channel(1120, True, 9, 1120, 1)
    assert not may_clip_channel(1120, True, 9, 77799, 9)
    assert not may_clip_channel(1120, True, 9, 77799, 10)
    assert not may_clip_channel(1120, False, 9, 77799, 8)
    assert not may_clip_channel(None, True, 9, 77799, 8)


def test_build_candidates_uses_only_tagged_current_channel_and_strict_priority() -> None:
    source = PROFILE.read_text(encoding="utf-8")

    assert "GetCurrentSpell(CURRENT_CHANNELED_SPELL)" in source
    assert 'HasMechanicTag(profileSpell.MechanicTags, "interruptible_channel")' in source
    assert "spell.SpellId != currentChanneledSpellId" in source
    assert "spell.PriorityBucket < currentChanneledProfileSpell->PriorityBucket" in source
    assert (
        "bot->HasUnitState(UNIT_STATE_CASTING) && !interruptsCurrentChanneledSpell"
        in source
    )
    assert "1120" not in source


def test_channel_clip_is_typed_through_resolution_and_cancelled_before_native_cast() -> None:
    profile_header = PROFILE_HEADER.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    resolver = RESOLVER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")

    assert "bool InterruptCurrentChanneledSpell = false;" in profile_header
    assert "bool InterruptCurrentChanneledSpell = false;" in types
    assert "action.InterruptCurrentChanneledSpell = best->InterruptCurrentChanneledSpell;" in resolver
    assert "action.InterruptCurrentChanneledSpell = livingBomb->InterruptCurrentChanneledSpell;" in resolver

    preflight = executor.index(
        "BotActionResult BotActionExecutor::CheckHostileSpell"
    )
    preflight_end = executor.index(
        "BotActionResult BotActionExecutor::CheckRecipe", preflight
    )
    preflight_body = executor[preflight:preflight_end]
    assert "bool interruptCurrentChanneledSpell" in preflight_body
    assert "GetCurrentSpell(CURRENT_CHANNELED_SPELL)" in preflight_body
    assert "GetCurrentSpell(CURRENT_GENERIC_SPELL)" in preflight_body
    assert "action.InterruptCurrentChanneledSpell" in executor[
        executor.index("CheckHostileSpell(owner, bot, target, action.SpellId") : preflight
    ]

    cancel = executor.index("bot->InterruptSpell(CURRENT_CHANNELED_SPELL, false);")
    native_cast = executor.index("bot->CastSpell(target, action.SpellId, castArgs)")
    assert "action.InterruptCurrentChanneledSpell" in executor[cancel - 120 : cancel]
    assert executor.index("CheckHostileSpell(owner, bot, target, action.SpellId") < cancel
    assert cancel < native_cast


def test_sql_tags_only_affliction_drain_soul() -> None:
    migration = SQL.read_text(encoding="utf-8")

    assert "CONCAT_WS(',', `action`.`mechanic_tags`, 'interruptible_channel')" in migration
    assert "`profile`.`class_id` = 9" in migration
    assert "`profile`.`spec_tag` = 'affliction_warlock'" in migration
    assert "`profile`.`role` = 'dps'" in migration
    assert "`action`.`spell_id` = 1120" in migration
    assert "FIND_IN_SET('interruptible_channel', `action`.`mechanic_tags`) = 0" in migration
    assert re.findall(r"`action`\.`spell_id`\s*=\s*(\d+)", migration) == ["1120"]
    assert "77799" not in migration
    assert "bot_rotation_profile` AS `profile`" in migration
