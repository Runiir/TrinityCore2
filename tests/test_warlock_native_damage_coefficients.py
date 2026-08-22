from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_missing_cataclysm_warlock_coefficients_use_native_spell_info_corrections() -> None:
    source = (ROOT / "src/server/game/Spells/SpellMgr.cpp").read_text()

    assert "ApplySpellFix({ 6353 }" in source
    assert "BonusMultiplier = 0.726f" in source
    assert "ApplySpellFix({ 48181 }" in source
    assert "BonusMultiplier = 0.5577f" in source
    assert "ApplySpellFix({ 54049 }" in source
    assert "BonusMultiplier = 1.228f" in source


def test_shadow_bite_scales_from_owned_warlock_dots_without_damage_injection() -> None:
    source = (ROOT / "src/server/scripts/Spells/spell_warlock.cpp").read_text()

    assert "class spell_warl_shadow_bite : public SpellScript" in source
    assert "GetAuraEffectsByType(SPELL_AURA_PERIODIC_DAMAGE)" in source
    assert "effect->GetCasterGUID() == owner->GetGUID()" in source
    assert "spellInfo->SpellFamilyName == SPELLFAMILY_WARLOCK" in source
    assert "AddPct(pctMod, int32(30 * activeDots.size()))" in source
    assert "SetHitDamage" not in source[source.index("class spell_warl_shadow_bite") : source.index("// 755 - Health Funnel")]


def test_shadow_bite_script_binding_is_idempotent() -> None:
    migration = (
        ROOT / "sql/custom/world/2026_08_16_02_warlock_native_damage_coefficients.sql"
    ).read_text()

    assert "VALUES (54049, 'spell_warl_shadow_bite')" in migration
    assert "ON DUPLICATE KEY UPDATE" in migration


def test_affliction_soulburn_window_consumes_once_and_requires_live_shards() -> None:
    profile_source = (
        ROOT / "src/server/game/Bots/BotClassSpecActionProfile.cpp"
    ).read_text()
    native_source = (ROOT / "src/server/scripts/Spells/spell_warlock.cpp").read_text()
    migration = (
        ROOT
        / "sql/custom/world/2026_08_23_00_affliction_soulburn_soul_fire_gate.sql"
    ).read_text()

    assert 'HasMechanicTag(spell.MechanicTags, "soul_shard")' in profile_source
    assert "bot->GetPower(POWER_SOUL_SHARDS) < 1" in profile_source
    assert 'return "insufficient_soul_shards"' in profile_source
    assert "SPELL_WARLOCK_SOUL_FIRE" in native_source
    assert "target->RemoveAurasDueToSpell(SPELL_WARLOCK_SOULBURN);" in native_source
    assert "soulburn,soul_shard,live_resource,apl_priority_2" in migration
    assert "soul_fire,soulburn,live_aura,apl_priority_1_12" in migration
    assert "`action`.`required_self_aura` = 74434" in migration


def test_affliction_soulburn_native_consumer_is_bound_and_one_charge() -> None:
    migration = (
        ROOT
        / "sql/custom/world/2026_08_23_01_affliction_soulburn_native_binding.sql"
    ).read_text()

    assert "`spell_id` = 74434" in migration
    assert "'spell_warl_soulburn'" in migration
    assert "DELETE FROM `spell_proc` WHERE `SpellId` = 74434" in migration
    assert "`SpellFamilyMask0`" in migration
    assert "`SpellFamilyMask1`" in migration
    assert "`Charges`, `Chance`" in migration
    assert "7, 1, 0, 0, 0, 1, 100" in migration


def test_affliction_modifier_diagnostics_observe_native_auras_without_applying_them() -> None:
    source = "\n".join(
        (
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(),
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrAffliction.cpp").read_text(),
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp").read_text(),
        )
    )
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text()

    assert "AfflictionModifierObservationTicks" in header
    assert 'Cohort().CalibrationTargetSpec == "affliction_warlock"' in source
    assert "bot->HasAura(87339)" in source
    assert "bot->HasAura(77215)" in source
    assert "fixtureTarget->HasAura(48181, bot->GetGUID())" in source
    assert "fixtureTarget->GetAura(32389," in source
    assert "hauntModifier->IsAffectingSpell(corruption)" in source
    assert "shadowEmbraceModifier->IsAffectingSpell(corruption)" in source
    assert "fixtureTarget->SpellDamageBonusTaken(bot, corruption," in source
    assert "minimum_corruption_taken_multiplier_ppm" in source
    assert '\\"affliction_modifier_observation\\"' in source
    assert "CastSpell(32389" not in source
    assert "AddAura(32389" not in source


def test_shadow_embrace_restores_canonical_all_ranks_native_proc_binding() -> None:
    migration = (
        ROOT
        / "sql/custom/world/2026_08_23_02_affliction_shadow_embrace_native_proc.sql"
    ).read_text()

    assert "DELETE FROM `spell_proc` WHERE `SpellId` = -32385" in migration
    assert "`SpellFamilyName`, `SpellFamilyMask0`" in migration
    assert "`SpellFamilyMask1`, `SpellFamilyMask2`" in migration
    assert "`SpellPhaseMask`" in migration
    assert "(-32385, 0, 5, 0x00000001, 0x00040000, 0, 0, 0, 2" in migration
    assert "CastSpell(32389" not in migration
    assert "AddAura(32389" not in migration


def test_shadow_embrace_restores_rank_chain_with_native_proc_and_no_cheat_injection() -> None:
    migration = (
        ROOT
        / "sql/custom/world/2026_08_23_02_affliction_shadow_embrace_native_proc.sql"
    ).read_text()

    assert (
        "DELETE FROM `spell_ranks`\n"
        "WHERE `first_spell_id` = 32385\n"
        "   OR `spell_id` IN (32385, 32387, 32392);"
    ) in migration
    assert (
        "INSERT INTO `spell_ranks` (`first_spell_id`, `spell_id`, `rank`) VALUES\n"
        "    (32385, 32385, 1),\n"
        "    (32385, 32387, 2),\n"
        "    (32385, 32392, 3);"
    ) in migration
    assert "DELETE FROM `spell_proc` WHERE `SpellId` = -32385" in migration
    assert "(-32385, 0, 5, 0x00000001, 0x00040000, 0, 0, 0, 2" in migration

    for forbidden in (
        "spell_script_names",
        "bot_rotation_action",
        "CastSpell",
        "AddAura",
        "LearnSpell",
    ):
        assert forbidden not in migration


def test_pet_resource_contract_waits_for_native_regeneration_without_refilling() -> None:
    source = "\n".join(
        (
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdate.cpp").read_text(),
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReset.cpp").read_text(),
        )
    )

    assert "fixtureContract->PetResourceRequired" in source
    assert 'std::string_view(power.UnitKind) != "pet"' in source
    assert "pet->GetPower(powerType)" in source
    assert "populationReady = petResourceReady" in source
    assert 'std::string_view(unitKind) != "pet"' in source
    assert "unit->SetPower(power, int32(expectedNative))" in source


def test_isolated_single_target_allows_one_target_shadowflame_without_multidot() -> None:
    source = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
    ).read_text()

    assert "independently requires one damaged target plus zero off-target damage" in source
    assert "bool const forbidArea = false;" in source
    assert "bool const allowMultidot = !strictSingleTarget;" in source
    assert "false, forbidArea, allowMultidot" in source


def test_profile_range_prefilter_preserves_native_combat_reach() -> None:
    profile_source = (
        ROOT / "src/server/game/Bots/BotClassSpecActionProfile.cpp"
    ).read_text()
    world_source = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
    ).read_text()
    executor_source = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text()

    assert "ProfileSpellMaximumRange" in profile_source
    assert "maximumRange + bot->GetCombatReach() + target->GetCombatReach()" in profile_source
    assert "effectiveSpellMaxRange" in world_source
    assert "nativeMaxRange += bot->GetCombatReach() + target->GetCombatReach()" in world_source
    assert "std::min(configuredMaxRange, nativeMaxRange)" in world_source
    assert "A profile maximum is a policy cap" in world_source
    assert "float minRange = bot->GetSpellMinRangeForTarget(target, spellInfo);" in executor_source
    assert "float maxRange = bot->GetSpellMaxRangeForTarget(target, spellInfo);" in executor_source
    assert "minRange += bot->GetMeleeRange(target);" in executor_source
    assert "maxRange += bot->GetCombatReach() + target->GetCombatReach();" in executor_source


def test_higher_priority_short_range_action_moves_before_long_range_filler() -> None:
    source = "\n".join(
        (
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp").read_text(),
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatMovement.cpp").read_text(),
        )
    )

    assert "BotActionCandidate* bestRangeRecovery = nullptr;" in source
    assert 'candidate.RejectReason == "out_of_range"' in source
    assert "candidatePreferred(candidate, bestRangeRecovery)" in source
    assert "candidatePreferred(*bestRangeRecovery, best)" in source
    assert "bool const preciseMaximumRangeApproach = action && minRange <= 0.0f" in source
    assert "maxRange - maximumRangeSafetyMargin" in source
    assert "minimumTravelDistance = preciseMaximumRangeApproach" in source
    assert "minimumMovementDistance = preciseMaximumRangeApproach" in source
    assert "desiredPlanarDistance = std::sqrt(std::max(0.0f" in source
    assert "for (float const nativePathSegment : { 1.5f, 3.0f, 5.0f, 7.0f })" in source
    assert "float const lateralAngle = std::acos(cosine);" in source
    assert "PathGenerator approachPath(bot);" in source
    assert "completeNativeApproach" in source
    assert "uint32(std::ceil(segmentLength / 0.5f))" in source
    assert "candidateRange > desiredRange" in source
    assert "Preserve its native path height" in source
    assert "target-centered ring points" in source
    assert "reference->GetPositionZ() + 4.0f" in source
    assert "candidateRange > maxRange - maximumRangeSafetyMargin" in source
    assert source.index("PathGenerator approachPath(bot);") < source.index(
        "for (float const nativePathSegment : { 1.5f, 3.0f, 5.0f, 7.0f })"
    )
    assert "BotMovementArbitration::Priority::Combat))" in source
    assert "moveToTerrainProjectedPoint(x, y, bot->GetPositionZ())" in source


def test_shadowflame_uses_a_self_cast_with_a_hostile_range_anchor() -> None:
    source = "\n".join(
        (
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatExecution.cpp").read_text(),
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp").read_text(),
            (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationRows.cpp").read_text(),
        )
    )
    migration = (
        ROOT / "sql/custom/world/2026_08_16_01_affliction_warlock_apl_rotation.sql"
    ).read_text()
    short_lane_migration = (
        ROOT / "sql/custom/world/2026_08_16_04_affliction_short_ranged_lane.sql"
    ).read_text()

    assert "selfCenteredHostileRangeAction" in source
    assert '"self_centered_position_reconcile"' in source
    assert "bot->SetFacingToObject(target);" in source
    assert "action.MaxRange = selfTarget" in source
    assert "'self', 'ranged', 'none', 0, 8" in migration
    assert "SET `action`.`min_range` = 0" in short_lane_migration
    assert "`action`.`target_selector` = 'enemy'" in short_lane_migration
    assert "`action`.`min_range` = 12" in short_lane_migration
    assert '\\\"movement_diagnostic\\\"' in source
