from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"


class SourceAggregate(str):
    """Expose a deterministic, read-only view of split implementation modules."""

    def __new__(
        cls,
        paths: tuple[Path, ...],
        families: dict[str, tuple[Path, ...]] | None = None,
    ):
        paths = tuple(paths)
        sources = tuple(
            (path, path.read_text(encoding="utf-8")) for path in paths
        )
        value = "\n".join(source for _, source in sources)
        instance = str.__new__(cls, value)
        instance._paths = paths
        instance._sources = sources
        instance._families = families or {}
        return instance

    def read_text(self, *, encoding: str = "utf-8") -> "SourceAggregate":
        if encoding != "utf-8":
            raise ValueError("SourceAggregate requires UTF-8 source files")
        return type(self)(self._paths, self._families)

    def resolve(self, signature: str) -> tuple[Path, str]:
        """Resolve a function to its unique owning translation unit.

        A split-family aggregate is useful for whole-manager assertions, but
        ``str.index`` is not a function-owner lookup: ``Update`` also matches
        ``UpdateBot`` and ``UpdateCalibrationBot``.  Keep the owner decision
        deterministic and fail closed when a signature is ambiguous.
        """
        candidates = [
            (path, source)
            for path, source in self._sources
            if _contains_function_signature(source, signature)
        ]
        preferred_owner = SOURCE_FUNCTION_OWNER_OVERRIDES.get(signature)
        if preferred_owner is not None:
            candidates = [
                (path, source)
                for path, source in candidates
                if path.name == preferred_owner
            ]
        if len(candidates) != 1:
            owners = ", ".join(path.name for path, _ in candidates) or "none"
            raise AssertionError(
                f"expected one owner for {signature!r}, found {owners}"
            )
        return candidates[0]

    def resolve_body(self, signature: str) -> str:
        """Return one owner body or one explicitly named split-family view."""

        family = self._families.get(signature)
        if family is not None:
            return "\n".join(
                path.read_text(encoding="utf-8") for path in family
            )
        _, source = self.resolve(signature)
        return _extract_function_body(source, signature)


def source_modules(pattern: str) -> SourceAggregate:
    paths = tuple(sorted(BOT_DIR.glob(pattern)))
    if not paths:
        raise AssertionError(f"no source modules matched {pattern!r}")
    return SourceAggregate(paths)


def module_family(*patterns: str, include: tuple[Path, ...] = ()) -> tuple[Path, ...]:
    paths = set(include)
    for pattern in patterns:
        paths.update(BOT_DIR.glob(pattern))
    if not paths:
        raise AssertionError(f"no source modules matched family {patterns!r}")
    return tuple(sorted(paths))


UPDATE_BOT_FAMILY = tuple(
    BOT_DIR / name
    for name in (
        "BotWorldPopulationMgrUpdateBot.cpp",
        "BotWorldPopulationMgrUpdateBotPreparation.cpp",
        "BotWorldPopulationMgrUpdateBotDecision.cpp",
        "BotWorldPopulationMgrUpdateBotFinalization.cpp",
        "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp",
        "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
        "BotWorldPopulationMgrUpdateBotKernelFallback.cpp",
        "BotWorldPopulationMgrUpdateBotLegacy.cpp",
    )
)
ROUTE_OBJECTIVE_FAMILY = module_family(
    "BotWorldPopulationMgrValidation*.cpp",
    "BotWorldPopulationMgrDungeon*.cpp",
    "BotWorldPopulationMgrMovement*.cpp",
    "Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/*.cpp",
    include=(
        BOT_DIR / "BotWorldPopulationMgr.cpp",
        BOT_DIR / "BotWorldPopulationMgrCombatMovement.cpp",
    ),
)
_ROUTE_PRIORITY_MODULES = (
    BOT_DIR / "BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp",
    BOT_DIR / "BotWorldPopulationMgr.cpp",
    BOT_DIR / "BotWorldPopulationMgrValidationRouteSharedFocusAction.cpp",
    BOT_DIR / "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp",
    BOT_DIR / "BotWorldPopulationMgrValidationRouteActiveCombat.cpp",
)
ROUTE_OBJECTIVE_FAMILY = _ROUTE_PRIORITY_MODULES + tuple(
    path for path in ROUTE_OBJECTIVE_FAMILY if path not in _ROUTE_PRIORITY_MODULES
)
MOVEMENT_FAMILY = module_family(
    "BotWorldPopulationMgrMovement*.cpp",
    include=(
        BOT_DIR / "BotWorldPopulationMgrCombatMovement.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheckActions.cpp",
    ),
)
CALIBRATION_FAMILY = module_family(
    "BotWorldPopulationMgrCalibration*.cpp",
    include=(BOT_DIR / "BotWorldPopulationMgr.cpp",),
)
BOT_MGR_FAMILIES = {
    "void BotWorldPopulationMgr::UpdateBot": UPDATE_BOT_FAMILY,
    "bool BotWorldPopulationMgr::TryValidationRouteObjective": ROUTE_OBJECTIVE_FAMILY,
    "bool BotWorldPopulationMgr::MoveBotToPoint": MOVEMENT_FAMILY,
    "std::string BotWorldPopulationMgr::GetCombatCalibrationJson() const": CALIBRATION_FAMILY,
}


BOT_COMMANDS = ROOT / "src/server/scripts/Commands/cs_healerbot.cpp"
SERVER_COMMANDS = ROOT / "src/server/scripts/Commands/cs_server.cpp"
BOT_MGR_CORE = BOT_DIR / "BotWorldPopulationMgr.cpp"
BOT_ACTION_EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
UPDATE_BOT_PREPARATION = BOT_DIR / "BotWorldPopulationMgrUpdateBotPreparation.cpp"
UPDATE_BOT_DEATH = BOT_DIR / "BotWorldPopulationMgrUpdateDeath.cpp"
COMBAT_RES = BOT_DIR / "BotWorldPopulationMgrCombatRes.cpp"
NATIVE_ACTION = BOT_DIR / "BotWorldPopulationMgrNativeAction.cpp"
QUEST_ACTIONS = BOT_DIR / "BotWorldPopulationMgrQuestActions.cpp"
MOVEMENT_EXECUTOR = BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp"
MOVEMENT_PLANNER = BOT_DIR / "BotWorldPopulationMgrMovementPlanner.cpp"
MOVEMENT_EVIDENCE = BOT_DIR / "BotWorldPopulationMgrMovementEvidence.cpp"
MOVEMENT_NATIVE_EXECUTOR = BOT_DIR / "BotWorldPopulationMgrMovementNativeExecutor.cpp"
TERMINAL_ARRIVAL = BOT_DIR / "BotWorldPopulationMgrValidationRouteTerminalArrival.cpp"
ROUTE_PACK = BOT_DIR / "BotWorldPopulationMgrValidationRoutePack.cpp"
GROUP_RECOVERY = BOT_DIR / "BotWorldPopulationMgrValidationRouteGroupRecovery.cpp"
TANK_FOCUS_ASSIST = BOT_DIR / "BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp"
VALIDATION_FOCUS = BOT_DIR / "BotWorldPopulationMgrValidationFocus.cpp"
VALIDATION_NO_PROGRESS = BOT_DIR / "BotWorldPopulationMgrValidationNoProgress.cpp"
VALIDATION_OUTCOMES = BOT_DIR / "BotWorldPopulationMgrValidationOutcomes.cpp"
VALIDATION_ACTIVATION = BOT_DIR / "BotWorldPopulationMgrValidationActivation.cpp"
VALIDATION_LIVE_PACK = BOT_DIR / "BotWorldPopulationMgrValidationLivePack.cpp"
VALIDATION_TERMINAL = BOT_DIR / "BotWorldPopulationMgrValidationTerminal.cpp"
TARGET_ENGAGEMENT = BOT_DIR / "BotWorldPopulationMgrValidationRouteTargetEngagement.cpp"
ACTIVE_COMBAT = BOT_DIR / "BotWorldPopulationMgrValidationRouteActiveCombat.cpp"
TARGETING = BOT_DIR / "BotWorldPopulationMgrValidationTargeting.cpp"
MOVEMENT_CHECK = BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.cpp"
MOVEMENT_CHECK_ACTIONS = BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheckActions.cpp"
FERAL_HANDOFF = BOT_DIR / "BotWorldPopulationMgrValidationRouteFeralTrashHandoff.cpp"
TANK_TRASH_RECOVERY = BOT_DIR / "BotWorldPopulationMgrValidationRouteTankTrashRecovery.cpp"
SWARM_APPROACH = BOT_DIR / "BotWorldPopulationMgrValidationSwarmApproach.cpp"
TRASH_INTERVENTION = BOT_DIR / "BotWorldPopulationMgrValidationRouteTrashIntervention.cpp"
VALIDATION_ROUTE_MOVEMENT_FAMILY = SourceAggregate(
    (
        BOT_DIR / "BotWorldPopulationMgrValidationHazards.h",
        BOT_DIR / "BotWorldPopulationMgrValidationHazards.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.cpp",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheckActions.cpp",
    )
)
_AZIL_DIR = BOT_DIR / "Content/Dungeons/Stonecore/Encounters/HighPriestessAzil"
AZIL_PASSIVE_SWARM = _AZIL_DIR / "HighPriestessAzilPassiveSwarmStaging.cpp"
AZIL_FERAL_REMOTE = _AZIL_DIR / "HighPriestessAzilFeralRemoteActions.cpp"
AZIL_FERAL_LOCAL = _AZIL_DIR / "HighPriestessAzilFeralLocalRetention.cpp"
AZIL_DENSITY_RESOLUTION = _AZIL_DIR / "HighPriestessAzilDensityCombatResolution.cpp"
AZIL_TANK_THREAT = _AZIL_DIR / "HighPriestessAzilTankThreatRecovery.cpp"
AZIL_ADD_DENSITY = _AZIL_DIR / "HighPriestessAzilAddWaveDensity.cpp"
AZIL_TANK_PREPARATION = _AZIL_DIR / "HighPriestessAzilAddWaveTankPreparation.cpp"
AZIL_ADD_DISCOVERY = _AZIL_DIR / "HighPriestessAzilAddWaveDiscovery.cpp"
ROUTE_GATE = BOT_DIR / "BotWorldPopulationMgrValidationRouteGate.cpp"
BOSS_MECHANICS = BOT_DIR / "BotWorldPopulationMgrBossMechanics.cpp"
_AZIL_MODULES = tuple(sorted(_AZIL_DIR.glob("*.cpp")))
_AZIL_PRIORITY_MODULES = (
    _AZIL_DIR / "HighPriestessAzilAddWaveDiscovery.cpp",
    _AZIL_DIR / "HighPriestessAzilAddWaveDensity.cpp",
    _AZIL_DIR / "HighPriestessAzilHunterThreatTransfer.cpp",
    _AZIL_DIR / "HighPriestessAzilHighDensityPositioning.cpp",
)
AZIL_ADD_WAVE_FAMILY = SourceAggregate(
    _AZIL_PRIORITY_MODULES
    + tuple(path for path in _AZIL_MODULES if path not in _AZIL_PRIORITY_MODULES)
)
TRASH_THREAT_FAMILY = SourceAggregate(
    (
        BOT_DIR / "BotWorldPopulationMgrValidationRouteTrashThreatControl.h",
        BOT_DIR / "BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp",
    )
)
BOT_MGR = SourceAggregate(
    tuple(sorted(
        set(BOT_DIR.glob("BotWorldPopulationMgr*.cpp"))
        | set((BOT_DIR / "Content").rglob("*.cpp"))
    )),
    BOT_MGR_FAMILIES,
)
PLAYER_BOT_MGR = source_modules("BotMgr*.cpp")
PLAYER_BOT_CONTROLLER = source_modules("BotController*.cpp")
PLAYER_BOT_TYPES = ROOT / "src/server/game/Bots/BotTypes.cpp"
PLAYER_BOT_ACTION_PROFILE_MODULES = (
    ROOT / "src/server/game/Bots/BotClassSpecActionProfile.cpp",
    ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp",
    ROOT / "src/server/game/Bots/BotClassSpecActionProfileDb.cpp",
    ROOT / "src/server/game/Bots/BotClassSpecActionProfileInternal.h",
)
PLAYER_BOT_EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
MELEE_AUTO_ATTACK_INTENT = ROOT / "src/server/game/Bots/BotMeleeAutoAttackIntent.h"
BOT_MGR_HEADER = source_modules("BotWorldPopulationMgr*.h")
PET_CPP = ROOT / "src/server/game/Entities/Pet/Pet.cpp"
STONECORE_ROTATION_SQL = ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql"
PRAYER_OF_MENDING_GUARD_SQL = ROOT / "sql/custom/world/2026_07_14_02_holy_priest_prayer_of_mending_aura_guard.sql"
PALADIN_AOE_THREAT_SQL = ROOT / "sql/custom/world/2026_07_14_03_stonecore_paladin_aoe_threat_priority.sql"
MARKSMAN_STATIONARY_SQL = ROOT / "sql/custom/world/2026_07_14_04_marksmanship_cast_time_stationary.sql"
EMERGENCY_ADD_THREAT_SQL = ROOT / "sql/custom/world/2026_07_15_01_stonecore_emergency_add_threat.sql"
WOWHEAD_GUIDE_ROTATION_SQL = ROOT / "sql/custom/world/2026_07_16_00_stonecore_wowhead_guide_rotations.sql"
PROTECTION_HOLY_WRATH_SELF_SQL = ROOT / "sql/custom/world/2026_08_09_00_phase9_protection_holy_wrath_self_center.sql"
FROST_PLAYER_OBSERVED_SQL = ROOT / "sql/custom/world/2026_08_16_00_frost_death_knight_player_observed_priority.sql"
BOT_POLICY = ROOT / "src/server/game/Bots/BotTelemetryPolicy.cpp"
BOT_BUFFER = ROOT / "src/server/game/Bots/BotTelemetryBuffer.cpp"
BOT_SEGMENTS = ROOT / "src/server/game/Bots/BotExperimentCoordinator.cpp"
WORLDSERVER_CONF = ROOT / "src/server/worldserver/worldserver.conf.dist"
CHASE_MOVEMENT = ROOT / "src/server/game/Movement/MovementGenerators/ChaseMovementGenerator.cpp"
MAP_CPP = ROOT / "src/server/game/Maps/Map.cpp"
PLAYER_CPP = ROOT / "src/server/game/Entities/Player/Player.cpp"
VALIDATION_SCENARIOS = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
PYTEST_CONFIG = ROOT / "pytest.ini"
AZIL_SCRIPT = ROOT / "src/server/scripts/Maelstrom/Stonecore/boss_high_priestess_azil.cpp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def lambda_body(source: str, marker: str) -> str:
    """Extract one named lambda from its current owning translation unit."""

    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    raise AssertionError(f"unterminated lambda body for {marker}")


def validation_route_lambda(marker: str) -> str:
    return lambda_body(read(BOT_MGR_CORE), marker)


def _contains_function_signature(source: str, signature: str) -> bool:
    """Match a function-name prefix without confusing a longer function."""

    start = 0
    while True:
        try:
            start = source.index(signature, start)
        except ValueError:
            return False
        end = start + len(signature)
        if end == len(source) or not signature[-1].isalnum():
            return True
        if not (source[end].isalnum() or source[end] == "_"):
            return True
        start = end


SOURCE_FUNCTION_OWNER_OVERRIDES = {
    "Player* CombatOwnerPlayer": "BotWorldPopulationMgrNativeHelpers.cpp",
    "bool UsesRangedAoeCalibrationLane": "BotWorldPopulationMgrCalibrationPopulation.cpp",
}


def _extract_function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    raise AssertionError(f"unterminated function body for {signature}")


def read_profile_sources() -> str:
    return "\n".join(read(path) for path in PLAYER_BOT_ACTION_PROFILE_MODULES)


def test_prayer_of_mending_profile_uses_the_applied_aura_as_its_guard() -> None:
    migration = read(PRAYER_OF_MENDING_GUARD_SQL)

    assert "`action`.`spell_id` = 33076" in migration
    assert "`action`.`forbidden_target_aura` = 41635" in migration
    assert "`action`.`maintain_aura_id` = 41635" in migration


def test_protection_paladin_prioritizes_multi_target_threat_actions() -> None:
    migration = read(PALADIN_AOE_THREAT_SQL)

    assert "`profile`.`spec_tag` = 'protection'" in migration
    assert "`action`.`spell_id` IN (53595, 26573) THEN 1" in migration
    assert "`action`.`spell_id` IN (53595, 26573, 2812)" in migration


def test_profile_taunts_require_a_real_non_tank_victim() -> None:
    manager = read(BOT_MGR)
    assert manager.count("(!target->GetVictim() || target->GetVictim() == bot)") >= 2

    fillers = read(ROOT / "sql/custom/world/2026_07_16_06_protection_single_target_fillers.sql")
    assert "`action`.`min_enemies`=1" in fillers
    assert "WHEN `action`.`spell_id`=26573 THEN 5" in fillers
    assert "WHEN `action`.`spell_id`=2812 THEN 6" in fillers


def test_combat_telemetry_attributes_player_totem_damage_to_its_owner() -> None:
    manager = read(BOT_MGR)
    owner_helper = function_body(manager, "Player* CombatOwnerPlayer")
    damage_hook = function_body(manager, "void BotWorldPopulationMgr::NotifyCombatDamage")

    assert "current->ToTotem()->GetOwner()" in owner_helper
    assert "depth < 4" in owner_helper
    assert "CombatOwnerPlayer(attacker)" in damage_hook


def test_marksmanship_cast_time_shots_require_stationary_execution() -> None:
    migration = read(MARKSMAN_STATIONARY_SQL)

    assert "`action`.`spell_id` IN (19434, 56641)" in migration
    assert "`action`.`requires_stationary` = 1" in migration


def test_frost_death_knight_uses_typed_player_observed_masterfrost_candidates() -> None:
    migration = read(FROST_PLAYER_OBSERVED_SQL)

    assert "`action`.`spell_id` = 48265" in migration
    assert "`action`.`maintain_aura_id` = 48265" in migration
    assert "player_observed_priority_v1" in migration
    assert "51124, 55078" in migration
    assert "1, 0, 59052" in migration
    assert "0.70, 1, 0" in migration
    assert "`action`.`maintain_aura_id` = 55078" in migration
    assert "`action`.`refresh_aura_below_ms` = 3000" in migration
    assert "maintain_owned_aura" in migration
    assert "`action`.`category` = 'resource_generator'" in migration
    assert "runic_power_filler,lowest_priority" in migration
    assert "`action`.`maintain_aura_id` = 0" in migration
    assert "EQUIPMENT_SLOT" not in migration
    assert "item_swap" not in migration


def test_frost_observations_change_the_winning_typed_alternate() -> None:
    migration = read(FROST_PLAYER_OBSERVED_SQL)
    profile = read_profile_sources()
    manager = read(BOT_MGR)

    def authored_priority(spell_id: int, marker: str) -> tuple[float, int]:
        match = re.search(
            rf"SELECT `profile`\.`id`, \d+, {spell_id}, .*?"
            rf"'[^']*{marker}[^']*',\s*([0-9.]+),\s*(\d+),",
            migration,
            flags=re.S,
        )
        assert match, (spell_id, marker)
        return float(match.group(1)), int(match.group(2))

    authored = {
        "frost_strike_cap": (*authored_priority(49143, "cap_protection"), 49143),
        "killing_machine_obliterate": (*authored_priority(49020, "killing_machine"), 49020),
        "rime_howling_blast": (*authored_priority(49184, "rime"), 49184),
    }

    # These are the same typed gates consumed by EvaluateCompiledConditions;
    # mechanic tags remain descriptive and never manufacture a proc/resource.
    assert 'return "missing_required_self_aura"' in profile
    assert 'return "ready_rune_gate"' in profile
    assert 'return "primary_power_gate"' in profile
    assert "candidate.Profile.PriorityBucket < current->Profile.PriorityBucket" in manager
    assert "candidate.Score > current->Score" in manager

    def choose(runic_power_ratio: float, killing_machine: bool, rime: bool) -> int | None:
        valid: list[tuple[int, float, int]] = []
        if runic_power_ratio >= 0.70:
            score, bucket, spell = authored["frost_strike_cap"]
            valid.append((bucket, -score, spell))
        if killing_machine and runic_power_ratio <= 0.70:
            score, bucket, spell = authored["killing_machine_obliterate"]
            valid.append((bucket, -score, spell))
        if rime and runic_power_ratio <= 0.90:
            score, bucket, spell = authored["rime_howling_blast"]
            valid.append((bucket, -score, spell))
        return min(valid)[2] if valid else None

    assert choose(0.85, killing_machine=True, rime=True) == 49143
    assert choose(0.50, killing_machine=True, rime=True) == 49020
    assert choose(0.50, killing_machine=False, rime=True) == 49184
    assert choose(0.50, killing_machine=False, rime=False) is None


def test_frost_candidate_telemetry_observes_resources_procs_and_owned_diseases() -> None:
    profile = read_profile_sources()

    assert 'profile.SpecTag == "frost_death_knight"' in profile
    assert '\\"bot_action_observation_v1\\"' in profile
    assert '\\"ready_runes\\"' in profile
    assert 'bot->HasAura(51124)' in profile
    assert 'bot->HasAura(59052)' in profile
    assert 'target->GetAura(55078, bot->GetGUID())' in profile
    assert 'target->GetAura(55095, bot->GetGUID())' in profile
    assert '\\"owned_55078_remaining_ms\\"' in profile
    assert '\\"owned_55095_remaining_ms\\"' in profile
    assert '\\"observation\\"' in profile
    assert '\\"priority_bucket\\"' in profile
    assert '\\"mechanic_tags\\"' in profile


def test_frost_free_rune_proc_uses_the_same_cost_modifiers_as_native_spell_checks() -> None:
    profile = read_profile_sources()
    executor = read(PLAYER_BOT_EXECUTOR)

    for source in (profile, executor):
        assert "GetSpellModOwner()" in source
        assert "SpellModOp::PowerCost0" in source
        assert "ApplySpellMod(spellInfo" in source


def test_frost_unholy_presence_is_bound_through_normal_provisioning_catalogs() -> None:
    actions = json.loads(read(ROOT / "experiments/configs/cata_434_action_profiles.json"))
    targets = json.loads(read(ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"))
    frost = next(
        row for row in targets["targets"]
        if row["spec_target_id"] == "frost_death_knight"
    )
    catalog_builder = read(ROOT / "tools/bot_ml/build_all_spec_phase1_catalogs.py")
    provisioner = read(ROOT / "tools/bot_ml/build_validation_provisioning.py")

    action_spells = actions["action_profile_spells_by_spec"]["frost_death_knight"]
    assert 48265 in action_spells
    assert 48266 not in action_spells
    assert 48265 in frost["action_profile_spell_ids"]
    assert 48266 not in frost["action_profile_spell_ids"]
    assert "unholy_presence" in frost["pet_form_stance_presence"]
    assert "frost_presence" not in frost["pet_form_stance_presence"]
    assert '"frost_death_knight": [48265]' in catalog_builder
    assert '"frost_death_knight": [45462, 47528, 48265' in catalog_builder
    assert "spec_profile_spells" in provisioner
    assert "profile_spells + spec_profile_spells + proficiency_spells" in provisioner
    assert "INSERT INTO `characters`.`character_spell`" in provisioner


def function_body(source: str | SourceAggregate, signature: str) -> str:
    if isinstance(source, SourceAggregate):
        return source.resolve_body(signature)
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    raise AssertionError(f"unterminated function body for {signature}")


def assert_ordered(text: str, *needles: str) -> None:
    cursor = -1
    for needle in needles:
        found = text.find(needle, cursor + 1)
        assert found != -1, needle
        cursor = found


def test_validation_scenario_trash_counts_are_descriptive_only():
    from tools.bot_ml.build_validation_scenario_manifests import build_manifests

    config = json.loads(read(VALIDATION_SCENARIOS))
    stonecore = next(scenario for scenario in config["scenarios"] if scenario["id"] == "stonecore_5n")
    trash_steps = [step for step in stonecore["route"] if step["kind"] == "trash"]
    assert all(
        "expected_alive_count" not in step
        if step.get("node_kind") == "discovery_leg"
        else step.get("expected_alive_count") != 0
        for step in trash_steps
    )

    manifest = build_manifests(config, {}, {"all_passed": True})
    generated_trash = [
        route
        for route in manifest["validation_routes"]
        if route["scenario_id"] == "stonecore_5n" and route["node_kind"] in {"trash_cluster", "discovery_leg"}
    ]
    assert generated_trash
    generated_by_step = {route["step"]: route for route in generated_trash}
    assert generated_by_step[1]["cluster_radius_yards"] == 0.0
    assert "expected_alive_count" not in generated_by_step[1]
    assert generated_by_step[1]["pack_target_entries"] == []
    assert generated_by_step[1]["completion_policy"] == "corridor_clear_after_engagement"
    assert all(route["expected_alive_count"] == len(route["pack_target_entries"]) for route in generated_trash if route["step"] != 1)
    assert all(route["expected_alive_count"] > 0 for route in generated_trash if route["node_kind"] == "trash_cluster")
    assert all(route["expected_alive_count_semantics"] == "descriptive_only" for route in generated_trash)
    assert all(route["completion_policy"] == "cluster_clear_after_pull" for route in generated_trash if route["step"] != 1)
    corborus = next(route for route in manifest["validation_routes"] if route["scenario_id"] == "stonecore_5n" and route["label"] == "Corborus")
    assert corborus["add_target_entries"] == [43917]


def test_validation_route_group_focus_reaches_profile_action_without_threat_rewait():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    group_focus_start = route_objective.index("if (Unit* focusTarget = routeGroupFocusTarget())")
    group_focus_end = route_objective.index('if (std::string(GetDungeonRole(bot)) != "tank"\n        && (', group_focus_start)
    group_focus = route_objective[group_focus_start:group_focus_end]
    later_threat_gate = 'if (routeTrashPackTarget && !botIsTank\n            && validationRouteHasLivingTank() && !routeFocusTankOwned(target))'

    assert_ordered(
        group_focus,
        "target = focusTarget;",
        "if (tryRouteGroupHeal(bot, target))",
        "ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);",
    )
    assert "routeFocusTankOwned(target)" not in group_focus
    assert route_objective.index(later_threat_gate) > group_focus_end


def test_decision_tick_caps_combat_and_validation_before_minimum_floor():
    update_bot = function_body(read(BOT_MGR), "void BotWorldPopulationMgr::UpdateBot")

    assert_ordered(
        update_bot,
        'uint32 decisionTickMs = sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000);',
        "if (context.Bot->IsInCombat() || Cohort().Config.ValidationRouteEnable)",
        "decisionTickMs = std::min<uint32>(decisionTickMs, responsiveSpecCombat ? reactionTimeMs : 1000);",
        "context.State.DecisionTimer = std::max<uint32>(responsiveSpecCombat ? reactionTimeMs : 500, decisionTickMs);",
    )


def test_pytest_excludes_generated_orchestrator_worktrees():
    pytest_config = read(PYTEST_CONFIG)
    assert re.search(r"^testpaths\s*=\s*tests$", pytest_config, re.MULTILINE)
    assert re.search(r"^norecursedirs\s*=\s*generated/orchestrator_worktrees$", pytest_config, re.MULTILINE)


def test_validation_route_has_no_forced_teacher_damage_or_expected_empty_terminal():
    route_objective = function_body(read(BOT_MGR_CORE), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    assert not re.search(r"\bUnit::(?:Kill|DealDamage)\s*\(", route_objective)
    assert "SetHealth(0" not in route_objective
    assert "JUST_DIED" not in route_objective
    assert "validation_route_teacher_assist" not in route_objective
    assert "trash_cluster_expected_empty" not in route_objective
    assert "&& !Cohort().Config.ValidationRouteExpectedAliveCount" not in route_objective


def test_validation_route_prerequisite_switch_resets_pack_progress_budget():
    target_switch = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::MaybeValidationPrerequisiteNoProgressAssist",
    )

    assert "A prerequisite switch is fresh progress context" in target_switch
    assert_ordered(
        target_switch,
        "state.ValidationRoutePackProgressTargetGuid = prerequisiteTarget->GetGUID();",
        "state.ValidationRoutePackBestHealthPct = healthPct;",
        "state.ValidationRoutePackNoProgressCount = 0;",
        "return false;",
    )


def test_unengaged_boss_prerequisite_cannot_latch_trash_failure_terminal():
    no_progress = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::MaybeValidationPrerequisiteNoProgressAssist",
    )

    assert '&& !isValidationRouteScriptTarget(creature)' in no_progress
    assert '&& !prerequisiteTarget->IsInCombat()' in no_progress
    assert '&& !prerequisiteTarget->GetVictim();' in no_progress
    assert_ordered(
        no_progress,
        "if (unengagedBossPrerequisite)",
        "resetCombatNoProgress();",
        "resetPackNoProgress();",
        'refreshRouteProgress("unengaged_boss_prerequisite_observed", 0);',
        "return false;",
    )
    assert "markValidationRouteTrashFailed" not in no_progress


def test_boss_prerequisites_use_trash_swarm_threat_security_without_intercepting_boss_adds():
    threat_security = read(TRASH_THREAT_FAMILY)

    assert "Boss nodes can still contain ordinary prerequisite packs" in threat_security
    assert "isValidationRouteScriptTarget(creature) || declaredBossAdd" in threat_security
    assert 'if (bot->getClass() == CLASS_HUNTER' in threat_security
    assert "bool useAreaTransfer = trashThreatControl.EngagedCount >= 2;" in threat_security
    assert 'if (std::string(GetDungeonRole(bot)) == "dps"' in threat_security
    assert '"prerequisite_swarm_emergency_defensive"' in threat_security
    assert '"spread_after_secure_prerequisite_threat"' in threat_security
    assert 'if (Cohort().Config.ValidationRouteKind != "boss"' not in threat_security


def test_server_start_autonomy_enabled_by_default_contract():
    conf = read(WORLDSERVER_CONF)
    commands = read(BOT_COMMANDS)
    server_commands = read(SERVER_COMMANDS)
    startup = function_body(commands, "void OnStartup() override")
    shutdown_initiate = function_body(commands, "void OnShutdownInitiate(ShutdownExitCode /*code*/, ShutdownMask /*mask*/) override")
    shutdown = function_body(commands, "void OnShutdown() override")
    server_exit = function_body(server_commands, "static bool HandleServerExitCommand")

    assert re.search(r"^PlayerBot\.Enable\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.Enable\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.FastExitAfterShutdown\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoStart\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.ProfileManifest\s*=\s*"dataset/bot_runtime_profiles/profiles\.json"$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoStartRecording\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoRecordingWindowMinutes\s*=\s*15$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.TargetPopulation\s*=\s*5$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.PoolTagFilter\s*=\s*""$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.Enable\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.ValidationRoute\.ManifestPath\s*=\s*""$', conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.ValidationRoute\.AdvanceMode\s*=\s*"disabled"$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.TargetEntry\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.ValidationRoute\.AlternateTargetEntries\s*=\s*""$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.ActivationDataId\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.ActivationAreaTriggerId\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.ActivationDataValue\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.ActivationSummonEntry\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.SpawnMode\s*=\s*"resume_or_race_start"$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AllowConfiguredCenterFallback\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.UseSavedPosition\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotProgression\.AllowQuesting\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotProgression\.AllowDungeons\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotProgression\.AllowRaids\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotLearning\.Enable\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotPolicyModel\.Enable\s*=\s*0$", conf, re.MULTILINE)
    assert "sBotMgr->ResetPoolUseState();" in startup
    assert 'sConfigMgr->GetBoolDefault("BotWorld.AutoStart", false)' in startup
    assert "sBotWorldPopulationMgr->StartAutonomy();" in startup
    assert "EnsurePopulation" not in startup
    assert "SpawnAutonomyBots" not in startup
    assert "StopAutonomy" not in shutdown_initiate
    assert "RemoveAll" not in shutdown_initiate
    assert "ResetPoolUseState" not in shutdown_initiate
    assert "deferred to final shutdown" in shutdown_initiate
    assert "sBotWorldPopulationMgr->Shutdown();" in shutdown
    assert "sBotWorldPopulationMgr->StopAutonomy();" not in shutdown
    assert "sBotMgr->RemoveAll();" in shutdown
    assert "sBotMgr->ResetPoolUseState();" in shutdown
    assert_ordered(
        server_exit,
        "sScriptMgr->OnShutdownInitiate(ShutdownExitCode(SHUTDOWN_EXIT_CODE), ShutdownMask(0));",
        "World::StopNow(SHUTDOWN_EXIT_CODE);",
    )


def test_playerbot_runtime_roles_drive_universal_profile_combat():
    bot_mgr = read(PLAYER_BOT_MGR)
    world_mgr = read(BOT_MGR)
    controller = read(PLAYER_BOT_CONTROLLER)
    role_types = read(PLAYER_BOT_TYPES)
    profiles = read_profile_sources()
    executor = read(PLAYER_BOT_EXECUTOR)

    assert "SELECT cbp.guid, c.account, cbp.role, cbp.class_spec" in bot_mgr
    assert "std::string selectedClassSpec = fields[3].GetString();" in bot_mgr
    assert "Register(owner, bot, botRole, selectedRole, selectedClassSpec" in bot_mgr
    assert "NormalizeBotRole(runtimeRole.empty() ? ToString(role) : runtimeRole)" in controller
    assert "normalized == \"tank\"" in role_types
    assert "normalized == \"healer\"" in role_types
    assert "normalized == \"dps\"" in role_types

    update = function_body(controller, "void BotController::Update")
    assert_ordered(
        update,
        "BotCombatState combatState = BuildCombatState(owner, bot, recentEvents);",
        'if (_runtimeRole == "healer")',
        "healerCommitted = TryResolveHealerAction",
        "ResolveProfileCombat(combatDecision, combatState, bot, target)",
    )

    decide = function_body(controller, "BotCombatDecision BotController::DecideSoloCombat")
    assert "CombatArchetypeForClass(state.ClassId, _runtimeRole, _classSpec)" in decide
    assert 'classSpec == "enhancement_shaman"' in controller
    assert "return BotCombatArchetype::MeleeDps;" in controller
    assert "GetSoloCombatArchetype(_role) != BotCombatArchetype::RangedCaster" not in decide

    select_profile = function_body(controller, "BotActionCandidate const* BotController::SelectProfileCombatAction")
    assert "_runtimeRole == \"tank\"" in select_profile
    assert "state.NearbyHostileCount >= 2" in select_profile
    assert "candidate.Category == BotCombatActionCategory::Taunt && target && target->GetVictim() == bot" in select_profile
    assert "requires_ally_target" in select_profile

    healer = function_body(controller, "bool BotController::TryResolveHealerAction")
    assert "BotClassSpecActionProfileStore::Build(bot, \"healer\")" in healer
    assert "BotCombatActionCategory::HealFast" in healer
    assert "HolyPaladinResolver" not in healer

    assert "profile.SpecTag = profile.Role == \"healer\" ? \"restoration_or_elemental_generic\" : \"enhancement_or_elemental_generic\";" in profiles
    assert "profile.SpecTag = profile.Role == \"healer\" ? \"holy_disc_generic\" : \"shadow_or_generic\";" in profiles
    assert 'candidate.RejectReason = "target_health_gate";' in world_mgr
    assert 'candidate.RejectReason = "self_health_gate";' in world_mgr
    assert 'candidate.RejectReason = "healer_triage_required";' in profiles
    assert 'candidate.RejectReason = "injured_player_count_too_low";' in profiles
    assert 'spell.MinInjuredPlayers' in profiles
    assert 'member->GetHealth()) / float(member->GetMaxHealth()) <= 0.94f' in profiles
    assert "SELECT class_spec FROM character_bot_pool WHERE guid" in profiles
    for alias in (
        '{ "protection_paladin", "protection" }',
        '{ "fire_mage", "fire" }',
        '{ "marksmanship_hunter", "marksmanship" }',
        '{ "survival_hunter", "survival" }',
        '{ "enhancement_shaman", "enhancement" }',
    ):
        assert alias in profiles
    assert "spellInfo->PowerType == POWER_RUNE && spellInfo->RuneCostID" in profiles
    assert "sSpellRuneCostStore.LookupEntry(spellInfo->RuneCostID)" in profiles
    assert "bot->GetRuneCooldown(i)" in profiles
    assert "spellInfo->NeedsComboPoints()" in profiles
    assert "bot->GetComboTarget() != comboTarget->GetGUID()" in profiles
    assert "proc_or_opener" in profiles
    for spell_id in ["53595", "31935", "26573", "53600", "56641", "2643", "8042", "17364", "60103", "421", "2120", "1449"]:
        assert spell_id in profiles

    assert "if (!action.Valid)" in executor
    assert "bot->GetPower(bot->GetPowerType())" in executor
    assert "target != bot && !bot->IsValidAttackTarget(target, spellInfo)" in executor
    assert "spellInfo->PowerType == POWER_RUNE && spellInfo->RuneCostID" in executor
    assert "sSpellRuneCostStore.LookupEntry(spellInfo->RuneCostID)" in executor
    assert "bot->GetRuneCooldown(i)" in executor
    assert "spellInfo->NeedsComboPoints()" in executor
    assert "bot->GetComboTarget() != target->GetGUID()" in executor
    execute_combat = function_body(executor, "BotActionResult BotActionExecutor::ExecuteCombat")
    assert_ordered(
        execute_combat,
        'action.AutoAttackMode == "melee"',
        "SubmitMeleeAutoAttack(bot, target)",
        "action.SpellId == 75",
        "CURRENT_AUTOREPEAT_SPELL",
        "BotActionResult check = CheckHostileSpell(owner, bot, target, action.SpellId,",
        "TARGET_FLAG_DEST_LOCATION",
        ": bot->CastSpell(target, action.SpellId, castArgs);",
    )
    assert "!bot->IsWithinMeleeRange(actionTarget)" in world_mgr


def test_bwd_validation_roster_has_rotation_profiles():
    sql = read(STONECORE_ROTATION_SQL)
    for spec_tag in [
        "protection_warrior",
        "blood_death_knight",
        "restoration_druid",
        "holy_paladin",
        "discipline_priest",
        "assassination_rogue",
        "affliction_warlock",
        "elemental_shaman",
    ]:
        assert f"'{spec_tag}'" in sql

    for spell_id in ["78", "355", "2565", "45462", "45477", "56222", "8936", "19750", "2061", "1752", "686", "403"]:
        assert re.search(rf", {spell_id}, '", sql)
    assert "'protection_warrior' AND `role`='tank'), 30, 355, 'taunt'" in sql
    assert "'blood_death_knight' AND `role`='tank'), 35, 56222, 'taunt'" in sql
    assert "'blood_death_knight' AND `role`='tank'), 45, 45477, 'threat_build'" in sql
    assert "'protection_warrior' AND `role`='tank'), 35, 2565, 'defensive'" in sql
    assert "'restoration_druid' AND `role`='healer'), 10, 8936, 'heal_fast', 'regrowth,triage,heal', 0, 0.92, 0.75, 1, 1, 0.82" in sql
    assert "'holy_paladin' AND `role`='healer'), 20, 19750, 'heal_fast', 'flash_of_light,triage,heal', 0, 0.94, 0.75, 1, 1, 0.82" in sql
    assert "'discipline_priest' AND `role`='healer'), 20, 2061, 'heal_fast', 'flash_heal,triage,heal', 0, 1.00, 0.85, 1, 1, 0.82" in sql
    update_sql = read(ROOT / "sql/custom/world/2026_07_02_01_bwd_tank_threat_profiles.sql")
    assert "p.`class_id` = 1 AND p.`spec_tag` = 'protection_warrior'" in update_sql
    assert "p.`class_id` = 6 AND p.`spec_tag` = 'blood_death_knight'" in update_sql
    assert "'protection_warrior' AND `role`='tank'), 30, 355, 'taunt'" in update_sql
    assert "'blood_death_knight' AND `role`='tank'), 35, 56222, 'taunt'" in update_sql
    assert "'blood_death_knight' AND `role`='tank'), 45, 45477, 'threat_build'" in update_sql
    healer_update_sql = read(ROOT / "sql/custom/world/2026_07_02_02_bwd_healer_triage_profiles.sql")
    assert "a.`spell_id` = 8936 THEN 0.82" in healer_update_sql
    assert "a.`spell_id` = 635 THEN 0.94" in healer_update_sql


def test_validation_blockers_require_matching_resolution_and_trace_episode_fields():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    blocked = function_body(mgr, "void BotWorldPopulationMgr::MarkBotBlocked")
    unstuck = function_body(mgr, "bool BotWorldPopulationMgr::TryResolveBotBlocker")
    execute_profile = function_body(mgr, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction")
    trace = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionTrace")
    diagnose = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")

    for symbol in [
        "BlockedEpisodeId",
        "BlockedFirstReason",
        "BlockedResolution",
        "BlockedResolvedBy",
        "BlockedResolvedMs",
    ]:
        assert symbol in header

    assert "++state.BlockedEpisodeId" in blocked
    assert "Blocked: \" + state.BlockedFirstReason" in blocked
    assert "reason == resolver" in unstuck
    assert "buff_cast_failed:" in unstuck
    assert "totem_cast_failed:" in unstuck
    assert "cast_succeeded" in unstuck
    assert "hunter_pet_unprovisioned" in unstuck
    assert "hunter_pet_db_row_absent:" in unstuck
    assert "hunter_pet_load_failed:" in unstuck
    assert "hunter_pet_missing" in unstuck
    assert "movement_progress" in unstuck
    assert "TryResolveBotBlocker(*state, bot, \"profile_action_valid\")" in execute_profile
    assert "TryResolveBotBlocker(*state, bot, \"cast_succeeded\")" in execute_profile
    assert "MarkBotUnstuck(*state, bot, action.DebugName.c_str())" not in execute_profile
    assert "entry.BlockedEpisodeId = state.BlockedEpisodeId" in trace
    assert "blocked_first_reason" in diagnose
    assert "blocked_resolution" in diagnose


def test_profile_blocker_debounce_rejects_alternation_and_accepts_stable_progress():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    blocked = function_body(mgr, "void BotWorldPopulationMgr::MarkBotBlocked")
    resolver = function_body(mgr, "bool BotWorldPopulationMgr::TryResolveBotBlocker")

    for symbol in [
        "BlockedResolutionCandidate",
        "BlockedResolutionCandidateCount",
    ]:
        assert symbol in header
        assert symbol in blocked
        assert symbol in resolver

    assert "constexpr uint32 ProfileActionStableSamples = 2;" in resolver
    assert "state.BlockedResolutionCandidateCount >= ProfileActionStableSamples" in resolver
    assert "state.BlockedResolutionCandidateCount > 0" in resolver
    assert "state.BlockedResolutionCandidate.clear();" in blocked
    assert "state.BlockedResolutionCandidateCount = 0;" in blocked

    def simulate(samples):
        blocked_state = False
        episode_count = 0
        candidate_count = 0
        resolution_count = 0
        semantic_progress_count = 0
        for sample in samples:
            if sample == "invalid":
                if not blocked_state:
                    blocked_state = True
                    episode_count += 1
                candidate_count = 0
                continue
            if not blocked_state:
                continue
            if sample == "valid":
                candidate_count += 1
                if candidate_count >= 2:
                    blocked_state = False
                    resolution_count += 1
                    semantic_progress_count += 1
            elif sample == "cast_succeeded" and candidate_count > 0:
                blocked_state = False
                resolution_count += 1
                semantic_progress_count += 1
        return episode_count, resolution_count, semantic_progress_count

    alternating = simulate(["invalid", "valid"] * 8)
    assert alternating == (1, 0, 0)

    stable = simulate(["invalid", "valid", "valid"])
    assert stable == (1, 1, 1)

    concrete_progress = simulate(["invalid", "valid", "cast_succeeded"])
    assert concrete_progress == (1, 1, 1)


def test_validation_route_readiness_buffs_party_and_hunter_pet_without_fallbacks():
    mgr = read(BOT_MGR)
    readiness = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteReadiness")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    trash = function_body(mgr, "BotWorldPopulationMgr::DungeonTrashActionResult BotWorldPopulationMgr::TryDungeonTrash")

    for spell_id in ["25780", "31801", "465", "20217", "13165", "982", "1130", "34477"]:
        assert spell_id in readiness

    assert "divine_plea_ready" not in readiness

    for buff_key in [
        "battle_shout_ready",
        "commanding_shout_ready",
        "power_word_fortitude_ready",
        "shadow_protection_ready",
        "horn_of_winter_ready",
        "arcane_brilliance_ready",
        "mark_of_the_wild_ready",
    ]:
        assert buff_key in readiness

    assert "if (bot->IsInCombat())" in readiness
    assert "state.GroupReadinessStableSinceMs = 0;" in readiness
    assert 'result.Action = "validation_route_readiness_wait";' in readiness
    assert "nowMs - state.GroupReadinessStableSinceMs < 10000" in readiness
    assert "hunterHasStoredPet" in readiness
    assert "(!bot->GetPet() || !bot->GetPet()->IsAlive())" in readiness
    assert "if (!urgentHunterPetRecovery)\n        for (ActiveBuffRequirement const& requirement" in readiness
    assert "Cohort().Config.ValidationRouteEnable || !bot" not in readiness
    assert "ActiveBuffRequirement" in readiness
    assert "blessing_of_kings_ready" in readiness
    assert "strength_of_earth_totem_ready" not in readiness
    assert "wrath_of_air_totem_ready" not in readiness
    assert "flametongue_totem_ready" not in readiness
    assert "std::string(requirement.PartyWide ? \"missing_party_buff:\" : \"missing_self_buff:\") + requirement.Key" in readiness
    assert "ReadinessRetryUntilMs" in readiness
    assert "ReadinessPartyCoverageSignature" in readiness
    assert "!bot->IsWithinDistInMap(member, maxRange)" in readiness
    assert "state.ReadinessPartyCoverageSignature[attemptKey] == signature" in readiness
    assert "state.ReadinessPartyCoverageSignature[attemptKey] = signature" in readiness
    assert "RecordEvent(state, bot, \"validation_route_readiness\", member, failedReason.c_str()" in readiness
    assert "deferAttempt(attemptKey, failedReason.c_str())" in readiness
    assert "TryReconcileHunterPetDataFromDB" not in mgr
    assert "TrySummonConfiguredHunterPet" not in mgr
    assert "bot->SummonPet(petData->Slot" not in mgr
    assert "static uint32 const callPetSpells[] = { 883, 83242, 83243, 83244, 83245 };" in readiness
    assert "bot->GetPlayerPetDataBySlot(slot)" in readiness
    assert "validation_route_readiness_call_pet" in readiness
    assert "hunter_pet_call_failed:" in readiness
    assert "hunter_pet_missing" in readiness
    assert "hunter_pet_dead" in readiness
    assert "buff_cast_failed:\" << readyReason << \":spell=\" << spellId << \":target=\"" in readiness
    assert "if (!canAttempt(attemptKey))\n            return true;" in readiness
    assert 'state.ReadinessPartyCoverageSignature[attemptKey] == "cast_once"' not in function_body(
        readiness, "auto castSelf"
    )
    assert "state.ReadinessRetryUntilMs[attemptKey] = nowMs + 5000;" in readiness
    assert "validation_route_readiness_misdirection" in readiness
    assert "for (GroupReference* itr = group->GetFirstMember()" in readiness
    assert "hasAnyAura(member, auraIds)" in readiness
    assert "validation_route_readiness_party_buff" in readiness
    assert "TryValidationRouteReadiness(state, bot, target" in route_objective
    assert "TryValidationRouteReadiness(state, bot, groupTarget" in trash
    assert "AttackStop" not in readiness
    assert "CombatStop" not in readiness


def test_headless_bot_spawn_forces_visibility_after_registration():
    bot_mgr = read(PLAYER_BOT_MGR)
    load = function_body(bot_mgr, "Player* BotMgr::LoadCharacterAsBotSession")

    assert_ordered(
        load,
        "bot->GetMap()->AddPlayerToMap(bot)",
        "ObjectAccessor::AddObject(bot)",
        "bot->LoadPetsFromDB(holder->GetPreparedResult(PLAYER_LOGIN_QUERY_LOAD_ALL_PETS))",
        "provisioning must assign a valid active pet",
        "bot->RemoveAurasByType(SPELL_AURA_MOUNTED)",
        "bot->LoadPet()",
        "bot->UpdateObjectVisibility(true)",
        "player->UpdateVisibilityOf(bot)",
        "SetBotCharacterOnline(guid, true)",
    )
    assert "Map::PlayerList const& players = map->GetPlayers()" in load
    assert "session->IsBotSession()" in load
    assert "bot->IsWithinDistInMap(player, bot->GetVisibilityRange())" in load
    assert "PlayerBot pets loaded" in load
    assert "PlayerBot dismounted before pet load" in load


def test_headless_hunter_requires_a_provisioned_active_pet_without_stable_mutation():
    bot_mgr = read(PLAYER_BOT_MGR)
    load = function_body(bot_mgr, "Player* BotMgr::LoadCharacterAsBotSession")

    assert_ordered(
        load,
        "bot->LoadPetsFromDB(holder->GetPreparedResult(PLAYER_LOGIN_QUERY_LOAD_ALL_PETS))",
        "if (bot->getClass() == CLASS_HUNTER)",
        "PlayerPetData const* currentPet = bot->GetPlayerPetDataCurrent()",
        "provisioning must assign a valid active pet",
        "bot->LoadPet()",
    )
    assert "isLoadableHunterPet" in load
    assert "creatureInfo->IsTameable(bot->CanTameExoticPets())" in load
    assert "PET_SLOT_FIRST_STABLE_SLOT" not in load
    assert "GetFirstUnusedActivePetSlot" not in load
    assert "UPDATE character_pet SET active" not in load
    assert "petData->Active = true" not in load
    assert "TryCastFriendlySpell(bot, bot, 883)" not in load


def test_persistent_pet_guid_uses_creature_entry_not_database_pet_id():
    pet_cpp = read(PET_CPP)
    create = function_body(pet_cpp, "bool Pet::Create(ObjectGuid::LowType")

    assert "Object::_Create(guidlow, Entry, HighGuid::Pet)" in create
    assert "Object::_Create(guidlow, petId, HighGuid::Pet)" not in create
    assert "m_charmInfo->SetPetNumber(petId" in function_body(pet_cpp, "bool Pet::LoadPetData")


def test_shaman_totems_are_combat_entry_setup_without_spam():
    mgr = read(BOT_MGR)
    totems = function_body(mgr, "bool BotWorldPopulationMgr::TryEnsureCombatTotems")
    execute_profile = function_body(mgr, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction")

    for spell_id in ["8075", "3599", "5394", "8512"]:
        assert spell_id in totems

    assert "bot->IsInCombat()" in totems
    assert "m_SummonSlot" in totems
    assert "Totem* totem = creature ? creature->ToTotem()" in totems
    assert "totem && totem->IsAlive()" in totems
    assert "totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == spellId" in totems
    assert "totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == 2894" in totems
    assert "totem->GetSpell() == spellId" not in totems
    assert "ReadinessRetryUntilMs" in totems
    assert "totem_cast_failed:" in totems
    assert "desiredTotems" in totems
    assert "individual_combat_totem" in totems
    assert "SUMMON_SLOT_TOTEM_FIRE" in totems
    assert "SUMMON_SLOT_TOTEM_EARTH" in totems
    assert "SUMMON_SLOT_TOTEM_WATER" in totems
    assert "SUMMON_SLOT_TOTEM_AIR" in totems
    assert "TryEnsureCombatTotems(*state, bot, target, forbidArea ? 1 : hostileCount)" in execute_profile
    assert "hostileCount >= 3 && bot->HasSpell(8190) ? 8190 : 3599" in totems
    assert "AI()->AttackStart" not in totems
    assert "UNIT_FLAG_PLAYER_CONTROLLED" not in totems

    totem_ai = read(ROOT / "src/server/game/AI/CoreAI/TotemAI.cpp")
    assert "me->ToTotem()->GetOwner()" in totem_ai
    assert "me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED)" in totem_ai
    assert "owner->IsValidAttackTarget(victim, spellInfo)" in totem_ai
    assert "TRIGGERED_IGNORE_TARGET_CHECK" in totem_ai
    assert "_lastCastResult = me->CastSpell" in totem_ai
    assert "++_updateCalls" in totem_ai
    assert "++_noTargetSkips" in totem_ai


def test_cobra_shot_extends_serpent_sting_periodic_tick_budget():
    hunter = read(ROOT / "src/server/scripts/Spells/spell_hunter.cpp")
    cobra = hunter[hunter.index("// 77767 - Cobra Shot"):hunter.index("// -53234 - Piercing Shots")]

    assert "aur->SetDuration(std::min(newDuration, aur->GetMaxDuration()), true)" in cobra
    assert "periodic->ResetTicks()" in cobra


def test_persistent_spec_setup_precedes_dummy_and_profile_rotations():
    mgr = read(BOT_MGR)
    setup = function_body(mgr, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup")
    calibration = function_body(mgr, "void BotWorldPopulationMgr::UpdateCalibrationBot")
    execute_profile = function_body(
        mgr,
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state, Player* bot, Unit* target",
    )

    for spell_id in ["25780", "31801", "465", "20217", "1459", "30482", "13165", "324", "8232", "8024", "1130"]:
        assert spell_id in setup
    assert "79058" in setup
    assert "79063" in setup
    assert "TEMP_ENCHANTMENT_SLOT" in setup
    assert "EQUIPMENT_SLOT_MAINHAND" in setup
    assert "EQUIPMENT_SLOT_OFFHAND" in setup
    assert "TEMP_ENCHANTMENT_SLOT" in setup
    assert "TryEnsurePersistentCombatSetup(state, bot, target," in calibration
    assert "Cohort().CalibrationTargetSpec.c_str()" in calibration
    assert "BotClassSpecActionProfileStore::BuildForSpec(" in calibration
    assert_ordered(calibration, "TryEnsurePersistentCombatSetup(state, bot, target,", "metrics.WindowStartedMs = Cohort().CalibrationScoredStartedMs")
    assert "TryEnsurePersistentCombatSetup(*state, bot, target)" in execute_profile

    calibration_json = function_body(mgr, "std::string BotWorldPopulationMgr::GetCombatCalibrationJson() const")
    assert '\\"persistent_setup\\"' in calibration_json
    assert '\\"mainhand_temp_enchant\\"' in calibration_json
    assert '\\"offhand_temp_enchant\\"' in calibration_json
    assert '\\"fire_totem\\"' in calibration_json
    assert '\\"last_cast_result\\"' in calibration_json
    assert '\\"cast_successes\\"' in calibration_json
    assert '\\"uses_totem_ai\\"' in calibration_json
    assert '\\"autorepeat_spell\\"' in calibration_json
    assert '\\"no_target_skips\\"' in calibration_json
    assert '\\"stats\\"' in calibration_json


def test_reference_calibration_reports_only_conditions_it_applies():
    mgr = read(BOT_MGR)
    calibration_json = function_body(mgr, "std::string BotWorldPopulationMgr::GetCombatCalibrationJson() const")

    assert '\\"flask\\"' in calibration_json
    assert '\\"potions\\":' in calibration_json
    assert '\\"engineering_cooldowns\\":' in calibration_json
    assert '\\"racial_cooldowns\\":' in calibration_json
    assert '\\"consumables\\":' in calibration_json
    assert 'IsSelfProvidedCalibrationBaseline() ? "true" : "false"' in calibration_json
    assert '\\"engineering_cooldowns\\":false' in calibration_json
    assert '\\"racial_cooldowns\\":false' in calibration_json
    assert '\\"dynamic_action_observation\\"' in calibration_json
    assert "actionAttemptCount(79476)" in calibration_json
    assert "actionAttemptCount(82174)" in calibration_json


def test_requested_wowhead_profiles_and_target_count_aware_misdirection_are_explicit():
    sql = read(WOWHEAD_GUIDE_ROTATION_SQL)
    manager = read(BOT_MGR)

    for token in [
        "'survival', 'dps', 'focus'",
        "53301, 'spender', 'explosive_shot",
        "3674, 'dot', 'black_arrow",
        "2643, 'aoe', 'multi_shot,aoe,misdirection_transfer'",
        "77767, 'resource_generator', 'cobra_shot",
        "11129,'spender','combustion",
        "51533,'offensive_cooldown','feral_spirit",
        "88625,'heal_fast','holy_word_serenity",
        "84963,'spender','inquisition",
    ]:
        assert token in sql
    assert "`action`.`required_self_aura_stacks` = CASE" in sql
    assert "WHEN `action`.`spell_id` IN (403,421) THEN 5" in sql
    assert "a.min_primary_power_pct, a.max_primary_power_pct" in read_profile_sources()
    assert "bool useAreaTransfer = trashThreatControl.EngagedCount >= 2;" in manager
    assert "bool useAreaTransfer = addCount >= 2;" in manager
    assert 'useAreaTransfer ? "misdirection_aoe_transfer" : "misdirection_single_target_transfer"' in manager
    assert "ResolveProfileCombatAction(bot, target, 1, false)" in manager


def test_dummy_calibration_tuning_gates_spenders_and_adds_measured_aoe_actions():
    root = Path(__file__).resolve().parents[1]
    sql = (root / "sql/custom/world/2026_07_16_03_dummy_dps_rotation_tuning.sql").read_text()
    manager = read(BOT_MGR)

    assert "11113,'aoe','blast_wave,aoe,on_cooldown'" in sql
    assert "`action`.`required_self_aura`=64343" in sql
    assert "`action`.`required_self_aura`=73683" in sql
    assert "POWER_HOLY_POWER" in manager
    assert 'candidate.SpellId == 53600 || candidate.SpellId == 84963' in manager
    assert "combustion_dot_window_not_ready" in manager
    assert "ignite->GetAmount() < 10000" in manager


def test_enhancement_unleash_flame_experiment_has_measured_rollback():
    experiment = read(ROOT / "sql/custom/world/2026_07_17_01_enhancement_unleash_flame_priority.sql")
    rollback = read(ROOT / "sql/custom/world/2026_07_17_02_enhancement_unleash_flame_rollback.sql")

    assert "`action`.`spell_id`=73680" in experiment
    assert "`action`.`required_self_aura`=73683" in experiment
    assert "`action`.`refresh_aura_below_ms`=9000" in experiment
    assert "`action`.`priority_bucket`=4" in rollback
    assert "`action`.`required_self_aura`=0" in rollback
    assert "`action`.`maintain_aura_id`=8050" in rollback
    assert "`action`.`refresh_aura_below_ms`=0" in rollback


def test_enhancement_uses_and_preserves_fire_elemental_before_searing_fallback():
    root = Path(__file__).resolve().parents[1]
    sql = (root / "sql/custom/world/2026_07_16_07_enhancement_fire_elemental.sql").read_text()
    provisioning = (root / "experiments/configs/validation_provisioning_cata_001.json").read_text()

    assert "2894,'offensive_cooldown','fire_elemental_totem" in sql
    provisioning_payload = json.loads(provisioning)
    assert sum(
        2894 in bot.get("spells", [])
        for scenario in provisioning_payload["scenarios"]
        for bot in scenario.get("bots", [])
    ) == 2

    elemental_ai = (root / "src/server/scripts/Pet/pet_shaman.cpp").read_text()
    assert "AcquireShamanOwnerVictim" in elemental_ai
    assert "owner->GetVictim()" in elemental_ai
    assert "UNIT_FLAG_PLAYER_CONTROLLED" in elemental_ai


def test_dummy_calibration_followup_spreads_living_bomb_and_avoids_refresh_waste():
    root = Path(__file__).resolve().parents[1]
    sql = (root / "sql/custom/world/2026_07_16_04_dummy_dps_rotation_followup.sql").read_text()
    resolver = function_body(read(BOT_MGR), "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction")

    assert "activeLivingBombs < 3" in resolver
    assert "spreadTarget->HasAura(44457, bot->GetGUID())" in resolver
    assert 'action.DebugName = "living_bomb_spread"' in resolver
    assert "`action`.`maintain_aura_id`=84963" in sql
    assert "`action`.`spell_id`=73680" in sql
    assert "`action`.`priority_bucket`=4" in sql


def test_dummy_calibration_uses_aura_refresh_threshold_for_serpent_sting():
    sql = read(ROOT / "sql/custom/world/2026_07_16_05_dummy_dps_aura_refresh.sql")
    profile = read_profile_sources()
    manager = read(BOT_MGR)

    assert "`action`.`maintain_aura_id`=1978" in sql
    assert "`action`.`refresh_aura_below_ms`=3000" in sql
    assert "MaintainedAuraBlocksRefresh" in profile
    assert "spell.RefreshAuraBelowMs" in profile
    assert "MaintainedProfileAuraBlocksRefresh" in manager
    assert "spell.RefreshAuraBelowMs" in manager


def test_stonecore_rotation_sql_declares_buffs_hunter_builder_and_aoe_gate():
    sql = read(STONECORE_ROTATION_SQL)

    for token in [
        "25780, 'buff', 'righteous_fury",
        "31801, 'buff', 'seal_of_truth",
        "20271, 'builder', 'judgement,threat,requires_seal'",
        "465, 'buff', 'devotion_aura",
        "20217, 'buff', 'blessing_of_kings",
        "13165, 'buff', 'aspect_of_the_hawk",
        "883, 'buff', 'call_pet",
        "34477, 'buff', 'misdirection",
        "56641, 'resource_generator', 'steady_shot,focus_builder",
    ]:
        assert token in sql

    assert "77767, 'builder'" not in sql
    assert "2120, 'aoe', 'flamestrike,aoe', 0.90, 0, 3, 4" in sql
    assert "'judgement,threat,requires_seal', 0.68, 0, 0.55, 0, 0, 4, 1, 0, 1, 1, 31801" in sql


def test_action_profile_hard_masks_enforce_aura_prerequisites():
    profile = read_profile_sources()

    assert 'spell.RequiredSelfAura && !selfAura' in profile
    assert 'spell.ForbiddenSelfAura && bot->HasAura(spell.ForbiddenSelfAura)' in profile
    assert 'spell.RequiredTargetAura && (!target || !target->HasAura(spell.RequiredTargetAura))' in profile
    assert 'spell.ForbiddenTargetAura && target && target->HasAura(spell.ForbiddenTargetAura)' in profile
    assert 'return "missing_required_self_aura"' in profile


def test_server_start_autonomy_enabled_spawns_from_pool_without_center_requirement():
    mgr = read(BOT_MGR)
    start_autonomy = function_body(
        mgr,
        "bool BotWorldPopulationMgr::StartAutonomy(BotWorldExperimentConfig const* overrideConfig)",
    )
    shutdown = function_body(mgr, "void BotWorldPopulationMgr::Shutdown")
    update = function_body(mgr, "void BotWorldPopulationMgr::Update")
    ensure_population = function_body(mgr, "void BotWorldPopulationMgr::EnsurePopulation")
    select_candidate = function_body(mgr, "uint32 BotWorldPopulationMgr::SelectPoolCandidateGuid(std::string const& rosterSlotId")
    resolve_placement = function_body(mgr, "bool BotWorldPopulationMgr::ResolveSpawnPlacement")

    assert 'LoadConfig("always_on_autonomy", overrideConfig);' in start_autonomy
    assert "if (Cohort().RuntimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy && !overrideConfig && !Cohort().RuntimeProfileDirty)" in start_autonomy
    assert "return true;" in start_autonomy
    assert "Cohort().RuntimeMode = BotWorldRuntimeMode::AlwaysOnAutonomy;" in start_autonomy
    assert "Cohort().RunId = 0;" in start_autonomy
    assert "Cohort().ExperimentId = 0;" in start_autonomy
    assert_ordered(start_autonomy, "Cohort().Active = true;", "EnsurePopulation();", "return Cohort().Active;")
    assert "RecordRunStop();" in shutdown
    assert "UPDATE character_bot_pool SET in_use = 0 WHERE guid" in shutdown
    assert "RemoveWorldBot" not in shutdown
    assert "PersistBotPosition" not in shutdown
    assert "spawned_bot_not_loaded" in update
    assert "UPDATE character_bot_pool SET in_use = 0 WHERE guid" in update
    assert "TryReattachValidationBot(*itr, loadedBot, \"population_update_loaded_not_in_world\")" in update
    assert "validation_same_instance_reattach_failed" in update
    assert "validation_artificial_reattach_blocked" not in mgr
    assert "session->HandleMoveWorldportAck();" in function_body(mgr, "bool BotWorldPopulationMgr::TryReattachValidationBot")
    assert "validationBotStillDeciding" in update
    assert "nowMs - itr->LastDecisionTickMs < 15000" in update
    assert "Cohort().Config.ValidationRouteEnable && itr->SpawnedMs && nowMs - itr->SpawnedMs >= 30000" in update
    assert "BotWorld active bot respawn deferred" in update
    assert "Cohort().FailedSpawnGuids.erase(prunedGuid.GetCounter())" in update
    assert "Party().ValidationRouteActivationApplied = false" in update

    assert "uint32 candidateGuid = SelectPoolCandidateGuid(rosterSlotId);" in ensure_population
    assert 'sBotMgr->SpawnWorldBotAtSavedPosition("any", std::to_string(candidateGuid))' in ensure_population
    assert 'sBotMgr->SpawnWorldBot("any", std::to_string(candidateGuid)' in ensure_population
    assert 'RecordEvent(Party().Bots.back(), bot, "bot_spawned"' in ensure_population
    assert "Cohort().Config.PoolTagFilter" in select_candidate
    assert "cbp.experiment_tags = '" in select_candidate
    assert_ordered(
        resolve_placement,
        "ResolveSavedSpawnPlacement(candidateGuid, placement)",
        "ResolveRaceStartSpawnPlacement(candidateGuid, placement)",
        "ResolveNearPlayerSpawnPlacement(placement)",
        "ResolveConfiguredCenterSpawnPlacement(placement)",
    )
    assert "Cohort().Config.UseSavedPosition" in resolve_placement
    assert "Cohort().Config.AllowConfiguredCenterFallback" in resolve_placement
    assert "resume_or_race_start" in resolve_placement
    assert "race_start_only" in resolve_placement


def test_stonecore_bot_instance_bind_does_not_wait_for_client_lock_prompt():
    map_cpp = read(MAP_CPP)
    add_player = function_body(map_cpp, "bool InstanceMap::AddPlayerToMap")

    assert '#include "WorldSession.h"' in map_cpp
    assert "player->GetSession()->IsBotSession()" in add_player
    assert "player->BindToInstance(mapSave, true, EXTEND_STATE_KEEP);" in add_player
    assert_ordered(
        add_player,
        "if (groupBind->perm)",
        "player->GetSession()->IsBotSession()",
        "player->BindToInstance(mapSave, true, EXTEND_STATE_KEEP);",
        "WorldPackets::Instance::PendingRaidLock pendingRaidLock;",
        "player->SetPendingBind(mapSave->GetInstanceId(), 60000);",
    )


def test_validation_bot_reattach_only_acks_typed_native_recovery_worldports():
    mgr = read(BOT_MGR)
    reattach = function_body(mgr, "bool BotWorldPopulationMgr::TryReattachValidationBot")
    update = function_body(mgr, "void BotWorldPopulationMgr::Update")

    assert "validation_artificial_reattach_blocked" not in mgr
    assert "IsNativeReleasedGhostWorldport(state, bot)" in reattach
    assert "IsNativeValidationRunbackWorldport(state, bot)" in reattach
    assert "nativeReleasedGhostWorldport || nativeValidationRunbackWorldport" in reattach
    assert "bot->IsBeingTeleportedFar()" in reattach
    assert "session->HandleMoveWorldportAck();" in reattach
    ack_gate = reattach.index("if (nativeRecoveryWorldport)")
    ack = reattach.index("session->HandleMoveWorldportAck();", ack_gate)
    untyped_reject = reattach.index(
        "An active validation bot may acknowledge only a typed native", ack
    )
    assert ack_gate < ack < untyped_reject
    assert "return false;" in reattach[untyped_reject:]
    assert "bot->CancelDelayedTeleport();" not in reattach
    assert "bot->SetSemaphoreTeleportFar(false);" not in reattach
    assert "AddPlayerToMap(" not in reattach
    assert "validation_same_instance_reattach_failed" in update


def test_bot_dungeon_summon_rejects_cross_map_detach():
    player_cpp = read(PLAYER_CPP)
    summon = function_body(player_cpp, "void Player::SummonIfPossible")

    assert re.search(
        r"bool Player::TeleportTo\(uint32.*?GetSession\(\)->IsBotSession\(\).*?GetMap\(\)->IsDungeon\(\).*?mapid != GetMapId\(\).*?return false;.*?DisableMgr::IsDisabledFor",
        player_cpp,
        re.DOTALL,
    )
    assert "GetSession()->IsBotSession()" in summon
    assert "GetMap()->IsDungeon()" in summon
    assert "m_summon_location.GetMapId() != GetMapId()" in summon
    assert_ordered(
        summon,
        "m_summon_location.GetMapId() != GetMapId()",
        "m_summon_expire = 0;",
        "return;",
        "TeleportTo(m_summon_location, TELE_TO_NONE, m_summon_instanceId);",
    )


def test_telemetry_policy_smoke_samples_normal_wander_and_keeps_critical_events():
    policy = read(BOT_POLICY)

    assert 'situation == "wander"' in function_body(policy, "bool IsSampleEvent")
    assert "return (sequence % rate) == 0;" in function_body(policy, "bool Sample")
    assert "? config.normalDecisionSampleRate : config.normalEventSampleRate" in policy
    assert "result.writeDecision = sampled;" in policy
    assert "result.writeEvent = sampled;" in policy
    assert "result.importance = BotTelemetryImportance::Drop;" in policy
    assert 'result.reason = "sampled_out";' in policy

    for event_type in ["death", "stuck_detected", "objective_failed"]:
        assert event_type in function_body(policy, "bool IsReplayEvent")
        assert event_type in function_body(policy, "bool IsKeepEvent")

    assert "failure && config.alwaysRecordFailures" in policy
    assert "input.intervention && config.alwaysRecordInterventions" in policy
    assert "input.rare && config.alwaysRecordRareStates" in policy


def test_bot_spawn_lifecycle_dummy_and_ability_objective_surface():
    mgr_header = read(BOT_MGR_HEADER)
    mgr = read(BOT_MGR)
    commands = read(BOT_COMMANDS)
    conf = read(WORLDSERVER_CONF)

    for symbol in [
        "ResolveRaceStartSpawnPlacement",
        "IsValidBotResumePosition",
        "PersistBotPosition",
        "RecordSpawnResolved",
        "IsTrainingDummy",
        "SelectQuestAbilityObjectiveTarget",
        "StopDisallowedDummyCombat",
        "GetBotDebugJson",
    ]:
        assert symbol in mgr_header

    resolve = function_body(mgr, "bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    assert "resume_or_race_start" in resolve
    assert "resume_only" in resolve
    assert "race_start_only" in resolve
    assert "saved_or_near_player" in resolve

    assert "spawn_resolved" in function_body(mgr, "void BotWorldPopulationMgr::RecordSpawnResolved")
    assert "spawn_resume_invalid" in function_body(mgr, "bool BotWorldPopulationMgr::ResolveSavedSpawnPlacement")
    assert "race_start" in function_body(mgr, "bool BotWorldPopulationMgr::ResolveRaceStartSpawnPlacement")
    assert "dummy_target_rejected" in function_body(mgr, "bool BotWorldPopulationMgr::StopDisallowedDummyCombat")

    questing = function_body(mgr, "BotWorldPopulationMgr::QuestActionResult BotWorldPopulationMgr::TryQuesting")
    assert "UseAbilityOnDummy" in questing
    assert "LastQuestProgressBefore" in questing
    assert "LastQuestProgressAfter" in questing
    assert "ability_objective_failed" in questing
    assert "blacklist_target_spell_pair" in questing

    select_safe = function_body(mgr, "Unit* BotWorldPopulationMgr::SelectSafeTarget")
    assert "IsTrainingDummy(target)" in select_safe

    assert '{ "debug",   rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "GetBotDebugJson" in commands
    assert "BotWorld.TrainingDummyEntries = \"\"" in conf
    assert "BotWorld.TeacherQuestKillAssist = 1" in conf


def test_quest_first_portfolio_routing_surface():
    mgr_header = read(BOT_MGR_HEADER)
    mgr = read(BOT_MGR)
    classify = function_body(mgr, "BotWorldPopulationMgr::QuestClassification BotWorldPopulationMgr::ClassifyQuestForBot")
    pickup_search = function_body(mgr, "bool BotWorldPopulationMgr::FindQuestPickupDestination")
    portfolio = function_body(mgr, "BotWorldPopulationMgr::QuestPortfolioPlan BotWorldPopulationMgr::BuildQuestPortfolioPlan")
    questing = function_body(mgr, "BotWorldPopulationMgr::QuestActionResult BotWorldPopulationMgr::TryQuesting")
    supported = function_body(mgr, "bool BotWorldPopulationMgr::HasSimpleSupportedObjective")
    select_objective = function_body(mgr, "Unit* BotWorldPopulationMgr::SelectQuestObjectiveTarget")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::ResolveObjectiveRoutePoint")
    tank_focus_assist = read(TANK_FOCUS_ASSIST)
    validation_focus = read(VALIDATION_FOCUS)
    validation_terminal = read(VALIDATION_TERMINAL)
    target_engagement = read(TARGET_ENGAGEMENT)
    active_combat = read(ACTIVE_COMBAT)
    legacy_decision = read(BOT_DIR / "BotWorldPopulationMgrUpdateBotLegacy.cpp")
    debug = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotDebugJson")
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")

    for symbol in [
        "QuestClassification",
        "QuestRoutePoint",
        "QuestObjectiveBucket",
        "QuestPortfolioPlan",
        "QuestSearchRadiusIndex",
        "QuestSearchDestination",
        "ActiveQuestClusterId",
        "QuestRouteDestination",
        "LastNoQuestReason",
        "LastQuestBucketReason",
        "ValidationRouteFocusGuid",
        "ValidationRouteFocusEntry",
        "ValidationRouteFocusSeenMs",
        "ValidationRouteAlternateTargetEntries",
    ]:
        assert symbol in mgr_header

    assert "HasSimpleSupportedObjective(quest)" in classify
    assert "GetNextQuestInChain()" in classify
    assert "GetNextQuestId()" in classify
    assert "GetBreadcrumbForQuestId()" in classify
    assert "creature_questender" in classify
    assert "gameobject_questender" in classify
    assert "quest->IsSeasonal()" in supported
    assert "QUEST_SPECIAL_FLAGS_KILL" in supported
    assert "UNIT_FLAG_NON_ATTACKABLE" in supported
    assert "ContainsInsensitive(tmpl->Name, \"DND\")" in supported
    assert "IsSimpleOpenWorldQuestMobAssistTarget" in mgr
    assert "objectiveType == BotWorldPopulationMgr::QuestObjectiveType::CollectItem" in mgr
    assert "creature->isElite()" in mgr
    assert "bot->GetMap()->IsDungeon() || bot->GetMap()->IsRaid()" in mgr
    validation_route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    facade_objective = function_body(
        read(BOT_MGR_CORE), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    add_discovery = read(AZIL_ADD_DISCOVERY)
    add_density_resolution = read(AZIL_DENSITY_RESOLUTION)
    movement_check = read(MOVEMENT_CHECK)
    route_core = read(BOT_MGR_CORE)
    trash_threat = str(TRASH_THREAT_FAMILY)
    assert "auto isValidationRouteEntry" in validation_route_objective
    assert "Cohort().Config.ValidationRouteAlternateTargetEntries.begin()" in validation_route_objective
    assert "isValidationRouteScriptTarget(creature)" in validation_route_objective
    script_target_block = validation_route_objective.split("auto isValidationRouteScriptTarget", 1)[1].split("auto isValidationRouteCombatTarget", 1)[0]
    assert 'if (Cohort().Config.ValidationRouteKind == "boss")' in script_target_block
    assert "isValidationRoutePackEntry(creature->GetEntry())" in script_target_block
    assert "creature->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) <= radius" in script_target_block

    assert "creature_loot_template" in select_objective
    assert "creature_loot_template" in route_objective
    assert "gameobject_loot_template" in route_objective
    assert "creature_loot_spawn" in route_objective
    assert "gameobject_loot_spawn" in route_objective
    assert_ordered(route_objective, "creature_loot_spawn", "quest_poi")

    assert "{ 100.0f, 250.0f, 500.0f, 900.0f, 1500.0f }" in pickup_search
    assert "creature_queststarter" in pickup_search
    assert "gameobject_queststarter" in pickup_search
    assert "ClassifyQuestForBot(bot, quest)" in pickup_search

    assert "constexpr float ClusterRadius = 180.0f;" in portfolio
    assert "ResolveObjectiveRoutePoint(bot, objective, route)" in portfolio
    assert "bucket->Objectives.push_back(objective)" in portfolio

    for event_type in [
        "quest_hub_sweep",
        "quest_pickup_search",
        "quest_bucket_selected",
        "objective_area_selected",
        "chain_step_accepted",
        "chain_step_turnin",
        "await_visible_quest_giver",
        "target_not_visible_travel_to_spawn",
    ]:
        assert event_type in questing

    assert_ordered(
        questing,
        "bot->CanCompleteQuest(state.QuestWork.ActiveQuestId)",
        "completed_counter_reconciled",
        "Cohort().Metrics.Kills += delta;",
        "RecordEvent(state, bot, \"mob_killed\", completedTarget, \"quest_counter_reconciled\"",
        "SetQuestWorkPhase(state, \"move_to_turnin\");",
    )
    quest_actions = read(QUEST_ACTIONS)
    legacy_update = read(BOT_DIR / "BotWorldPopulationMgrUpdateBotLegacy.cpp")
    assert_ordered(
        legacy_update,
        "uint32 progressBefore = context.State.LastQuestProgressBefore ? context.State.LastQuestProgressBefore : context.State.QuestWork.ProgressBefore;",
        "BotActionExecutor::LootResult loot = executor.AutoLoot(context.Bot, context.Target);",
        "VerifyQuestObjectiveProgress(context.State, context.Bot, lootPlan, context.Target, progressBefore, \"kill_or_loot_verified\"",
    )

    assert_ordered(
        questing,
        "ObjectAccessor::GetUnit(*bot, state.QuestWork.SelectedTargetGuid)",
        "selectedMatchesPlan",
        "VerifyQuestObjectiveProgress(state, bot, plan, selectedTarget, before, \"engaged_target_lost\"",
        "RecordQuestEvent(state, bot, \"objective_target_lost\"",
        "if (!objectiveTarget)",
        "objectiveTarget = SelectQuestObjectiveTarget(bot, plan);",
        "state.QuestWork.SelectedTargetGuid = objectiveTarget->GetGUID();",
        "state.TargetGuid = objectiveTarget->GetGUID();",
        "BotClassSpecActionProfileStore::Build(bot, role.c_str())",
        "result.Action = \"move_to_quest_mob\";",
        '"quest_melee_engagement"',
        "BotActionResult pull = actionSubmitted",
    )
    assert "teacher_quest_mob_assist" not in questing
    assert "teacher_kill_assist" not in questing
    assert "Unit::DealDamage(bot, objectiveTarget" not in questing

    assert "TrySmartGearDecision(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action)" in legacy_update
    assert "TryValidationRouteObjective(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action, context.Target)" in legacy_update
    assert "validation_route_prerequisite" in mgr
    assert "off_route_target" in mgr
    assert "routeEngageRange" in mgr
    assert "approach_target" in mgr
    assert "tryRouteGroupHeal" in mgr
    assert "validation_route_group_heal" in mgr
    assert "float maxApproachRange = Cohort().Config.ValidationRouteEnable && healer->GetMap() && healer->GetMap()->IsRaid() ? 35.0f : 18.0f;" in mgr
    assert "float approachRange = std::max(3.0f, std::min(healRange - 2.0f, maxApproachRange));" in mgr
    assert "healBlockedByCastState = true;" in mgr
    assert "heal_cast_state_pending" in mgr
    assert "validation_route_group_heal_pending" in mgr
    assert "buildRouteHealRaw" in mgr
    assert '\\"selected_heal_spell_id\\"' in mgr
    assert '\\"heal_target_guid\\"' in mgr
    assert '\\"heal_target_health_pct\\"' in mgr
    assert '\\"cast_failure_reason\\"' in mgr
    assert "bool cast = tryRouteFriendlySpell(" in mgr
    assert "healTarget, bestHeal->SpellId, &castFailureReason);" in mgr
    assert 'RecordEvent(state, healer, "validation_route_group_heal", healTarget, cast ? "ok" : castFailureReason.c_str(), raw.c_str(), semantic.c_str(), healTargetHealthPct, 0, bestHeal->SpellId);' in mgr
    assert "action = cast ? \"validation_route_group_heal\" : \"validation_route_group_heal_failed\";" in mgr
    assert "return cast || (allowMovement && feralTankApproachesHealerSwarm);" in mgr
    assert "return fail(\"line_of_sight\");" in mgr
    assert "return fail(\"global_cooldown\");" in mgr
    assert "if (spellInfo->CalcCastTime(bot->getLevel()) > 0)" in mgr
    assert "bot->StopMoving();" in mgr
    assert "bot->GetMotionMaster()->MoveIdle();" in mgr
    assert "*failureReason = \"spell_cast_result_\" + std::to_string(uint32(castResult));" in mgr
    assert_ordered(
        validation_route_objective,
        "target = routeTarget;",
        "state.TargetGuid = target->GetGUID();",
        "rememberValidationRouteFocus(target);",
        "if (tryRouteGroupHeal(bot, target))",
        "if (Cohort().Config.ValidationRouteKind == \"boss\" && tryValidationRouteInterrupt(target, \"route_target_interrupt\"))",
        "ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);",
    )
    assert "requires_ally_target" in mgr
    assert "threat_already_established" in mgr
    assert "routeGroupFocusTarget" in mgr
    assert "bestFocus" in mgr
    assert "voter->GetVictim() == focus" in mgr
    assert 'std::string(GetDungeonRole(member)) == "tank"' in mgr
    assert "auto activeTankFocus" in mgr
    assert "auto tankOwnsFocus" in validation_route_objective
    assert 'if (Cohort().Config.ValidationRouteKind != "boss" && !tankOwnsFocus(member, focus))' in validation_route_objective
    assert 'if (Cohort().Config.ValidationRouteKind == "boss" || activeTankFocus(focus))\n                return focus;' in validation_route_objective
    assert "if (!ownedByTank)" in validation_route_objective
    assert "routeFocusTankOwned" in validation_route_objective
    assert "wait_for_tank_threat" in validation_route_objective
    assert 'validationRouteHasLivingTank() && !routeFocusTankOwned(target)' in validation_route_objective
    assert "activeValidationRoutePackTarget" in validation_route_objective
    assert "if (Unit* packTarget = activeValidationRoutePackTarget())" in validation_route_objective
    assert "if (botIsTank && victim && !victimIsTank)" in validation_route_objective
    assert "score += 20000.0f;" in validation_route_objective
    assert "bool livingTankAvailable = false;" in validation_route_objective
    assert 'if (Cohort().Config.ValidationRouteKind != "boss" && !memberIsTank && livingTankAvailable)' in validation_route_objective
    assert '"tank_positioning", target, "route_trash_tank_focus"' in validation_route_objective
    rotation_profiles_sql = read(ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql")
    assert "blood_presence,self,tank_stance,mitigation" in rotation_profiles_sql
    assert "death_strike,self_heal,melee,threat" in rotation_profiles_sql
    assert "(8, 'fire', 'dps', 'mana', 'ranged', 'ranged', 'none', 0, 35" in rotation_profiles_sql
    assert "(3, 'marksmanship', 'dps', 'focus', 'ranged', 'ranged', 'ranged', 5, 35" in rotation_profiles_sql
    for spell_id in (19434, 56641, 53209):
        row = next(line for line in rotation_profiles_sql.splitlines() if f", {spell_id}," in line and "marksmanship" in line)
        assert row.rstrip().endswith(", 0),") or row.rstrip().endswith(", 0);")
    assert 'if (Cohort().Config.ValidationRouteKind == "boss" || activeTankFocus(focus))' in mgr
    assert 'if (Cohort().Config.ValidationRouteKind != "boss" && !memberIsTank && livingTankAvailable)' in mgr
    assert "move_to_validation_route_assist_target" in mgr
    assert "validation_route_prerequisite_assist" in mgr
    assert "assist_focus" in mgr
    assert 'bool routeTrashFocus = Cohort().Config.ValidationRouteKind != "boss";' in validation_route_objective
    assert 'action = routeTrashFocus ? "validation_route_trash_action" : "validation_route_prerequisite_assist";' in validation_route_objective
    assert 'RecordEvent(state, bot, routeTrashFocus ? "trash_action" : "validation_route_prerequisite"' in validation_route_objective
    assert "for (WorldBotState const& cohortState : Party().Bots)" in mgr
    assert "findCohortAnchor" in function_body(mgr, "Player* BotWorldPopulationMgr::FindDungeonAnchor")
    assert "for (WorldBotState const& state : Party().Bots)" in function_body(mgr, "Player* BotWorldPopulationMgr::FindDungeonAnchor")
    assert "std::string(GetDungeonRole(member)) != \"tank\"" in mgr
    assert "cohort_threat_established" in mgr
    assert "validation_route_regroup" in mgr
    assert "regroup_anchor_no_focus" in mgr
    assert "move_to_validation_route_anchor" in mgr
    assert "hold_anchor_no_focus" in mgr
    assert "validation_route_hold_anchor" in mgr
    assert "follow_anchor_before_prerequisite" in mgr
    assert "hold_anchor_before_prerequisite" in mgr
    assert 'if (Cohort().Config.ValidationRouteKind == "boss" && std::string(GetDungeonRole(bot)) != "tank")' in validation_route_objective
    assert (
        'if (Cohort().Config.ValidationRouteKind == "boss")\n'
        '                {\n'
        '                    RecordEvent(state, bot, "validation_route_regroup", anchor, "hold_anchor_before_prerequisite"'
    ) in validation_route_objective
    assert "routeTankFocusGuid" in mgr
    assert "routeTankFocusTarget" in mgr
    assert "rememberValidationRouteFocus" in mgr
    assert "clearValidationRouteKilledFocus" in mgr
    assert "cohortState.ValidationRouteCombatProgressTargetGuid.Clear();" in mgr
    assert "cohortState.ValidationRoutePackProgressTargetGuid.Clear();" in mgr
    assert "cohortState.ValidationRouteAnchorOverrideValid = false;" in mgr
    assert "cohortState.RecentDeathCount = 0;" in mgr
    assert "auto recordValidationRouteTrashKill" in validation_route_objective
    assert "if (!killedTarget || killedTarget->IsAlive() || killedTarget->GetHealth())" in validation_route_objective
    assert "clearValidationRouteKilledFocus(seenRouteTarget->GetGUID());" in mgr
    assert 'RecordEvent(state, bot, "mob_killed", killedTarget' in validation_route_objective
    assert 'if (!creature->IsAlive() || !creature->GetHealth())' in validation_route_objective
    assert 'recordValidationRouteTrashKill(seenRouteTarget, "target_seen_dead")' in validation_route_objective
    assert "activeCohortFocus" in mgr
    assert "member->IsInCombat() || focus->IsInCombat() || focus->GetVictim()" in mgr
    assert "authoritative_focus_state_target_inactive" in mgr
    assert "routeUsableCombatTarget(member->GetVictim())" in mgr
    assert "if (Unit* focus = routeUsableCombatTarget(member->GetVictim()))" in mgr
    assert "routeUsableValidationFocus(ObjectAccessor::GetUnit(*member, cohortState.TargetGuid))" in mgr
    assert "Player* loadedBot = GetLoadedBot(*itr)" in mgr
    assert "loaded_bot_not_in_world" in mgr
    assert "return bot && bot->IsInWorld() ? bot : nullptr;" in function_body(mgr, "Player* BotWorldPopulationMgr::GetBot")
    assert "member->GetVictim()" in mgr
    assert "force_tank_focus" in mgr
    assert "force_last_known_tank_focus" in mgr
    assert "findLastKnownFocusTarget" in mgr
    assert "return nullptr;" in function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    assert "creature->GetEntry() != Party().ValidationRouteFocusEntry" in mgr
    assert "auto routeFocusMemoryFresh" in validation_route_objective
    assert "routeFocusMemoryFresh()" in validation_route_objective
    assert "ObjectAccessor::GetUnit(*bot, Party().ValidationRouteFocusGuid)" in validation_route_objective
    assert "auto authoritativeRouteFocusActive" in validation_route_objective
    assert "if (routeFocusMemoryActive())" in tank_focus_assist
    assert "if (Cohort().Config.ValidationRouteKind != \"boss\")\n            continue;" in validation_focus
    assert 'return Cohort().Config.ValidationRouteKind == "boss" ? nearestMatchingEntry : nullptr;' in validation_route_objective
    assert 'if (Cohort().Config.ValidationRouteKind != "boss" && !Party().ValidationRouteFocusGuid.IsEmpty())' in validation_route_objective
    assert "Unit* rememberedFocus = loosePartyThreat ? threatFocus : findLastKnownFocusTarget();" in validation_route_objective
    assert "rememberedFocus = threatFocus;" in validation_route_objective
    assert "reject_non_authoritative_focus" in mgr
    assert "follow_anchor_non_authoritative_focus" in mgr
    assert "hold_unresolved_authoritative_focus" in mgr
    assert "hold_last_known_tank_focus" in mgr
    authoritative_memory = validation_route_objective.split("if (routeFocusMemoryActive())", 1)[1].split('if (std::string(GetDungeonRole(bot)) != "tank")', 1)[0]
    assert "follow_anchor_last_known_tank_focus" not in authoritative_memory
    assert "follow_last_known_tank_focus" not in authoritative_memory
    assert "FindDungeonAnchor(bot)" not in authoritative_memory
    assert "MoveBotToPoint(state, bot, Party().ValidationRouteFocusX" not in authoritative_memory
    assert_ordered(
        authoritative_memory,
        "if (tryRouteGroupHeal(bot, nullptr))",
        "float focusDistance = bot->GetExactDist(Party().ValidationRouteFocusX, Party().ValidationRouteFocusY, Party().ValidationRouteFocusZ);",
        "unresolved_authoritative_focus_recovery",
        "hold_unresolved_authoritative_focus",
        "hold_last_known_tank_focus",
    )
    assert "validation_route_hold_focus" in mgr
    assert "ValidationRouteUnresolvedFocusHoldCount" in mgr_header
    assert "ValidationRouteCombatNoProgressCount" in mgr_header
    assert "ValidationRouteBossSlowProgressCount" in mgr_header
    assert "ValidationRouteBossProgressTargetGuid" in mgr_header
    assert "ValidationRouteBossSlowProgressCount" in mgr_header
    assert "bool profileAllowsGenericCastMovement = Cohort().Config.ValidationRouteMechanicProfile.find(\"movement_check\") != std::string::npos" in validation_route_objective
    assert '|| Cohort().Config.ValidationRouteMechanicProfile.find("ground_danger") != std::string::npos;' in validation_route_objective
    assert "bool mechanicProfileRequiresMovement = profileAllowsGenericCastMovement || !hazardDefinitions.empty();" in validation_route_objective
    assert "if (!SpellLooksLikeGroundDanger(castSpell))" in validation_route_objective
    assert "for (auto const& [_, application] : bot->GetAppliedAuras())" in validation_route_objective
    assert "effect.Effect == SPELL_EFFECT_PERSISTENT_AREA_AURA" in validation_route_objective
    assert "effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE" in validation_route_objective
    assert "effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE_PERCENT" in validation_route_objective
    assert "if (!persistentPeriodicDamage)" in validation_route_objective
    assert "movementOrigin = aura->GetOwner();" in validation_route_objective
    assert "WorldObject const* dodgeOrigin = movementOrigin && movementOrigin != bot ? movementOrigin : caster;" in validation_route_objective
    assert "bot->GetRelativeAngle(dodgeOrigin) + float(M_PI)" in validation_route_objective
    assert 'ValidationRouteMechanicProfile.find("adds")' in validation_route_objective
    assert "ValidationRouteAddTargetEntries.empty()" in validation_route_objective
    assert "observer->IsValidAttackTarget(creature)" in validation_route_objective
    assert "ValidationRouteAddTargetEntries.end(), creature->GetEntry()" in validation_route_objective
    assert "BuildBossMechanicFeatures(bot, bossTarget)" not in validation_route_objective
    assert '"tank_density_autoattack_fallback"' in validation_route_objective
    assert '"boss_add_melee_engagement"' in validation_route_objective
    assert "if (result == BotActionResult::NoAction)\n        result = pull;" in target_engagement
    assert 'priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 2 : 1);' in validation_route_objective
    assert "priority == bestPriority && healthPct < bestHealthPct" in validation_route_objective
    assert "healthPct == bestHealthPct && guid < bestGuid" in validation_route_objective
    assert "if (manager.Party().ValidationRouteAddFocusGeneration\n        != manager.Party().ValidationRouteGeneration)" in add_discovery
    assert "else if (!isUsableListedAdd(bot, add))" in add_discovery
    assert "add = ObjectAccessor::GetUnit(*bot,\n            manager.Party().ValidationRouteAddFocusGuid);" in add_discovery
    assert "manager.Party().ValidationRouteAddFocusGuid = add->GetGUID();" in add_density_resolution
    assert "if (!add)" in add_discovery
    assert 'action = "hold_boss_add_focus";' in add_density_resolution
    assert "if (!add->IsAlive() || !add->GetHealth())" in add_discovery
    assert 'manager.RecordEvent(state, bot, "boss_add_killed", add,\n                "observed_dead"' in add_discovery
    assert 'event == "boss_adds" || event == "boss_add_killed"' in mgr
    assert 'eventName == "boss_add_killed"' in mgr
    assert_ordered(
        add_discovery + add_density_resolution,
        "if (!add->IsAlive() || !add->GetHealth())",
        "Party().ValidationRouteAddFocusGuid.Clear();",
        "Party().ValidationRouteAddFocusGuid = add->GetGUID();",
    )
    assert 'RecordEvent(state, bot, "boss_adds", add' in add_density_resolution
    assert_ordered(
        movement_check,
        "inspectCaster(preferredTarget);",
        "if (!caster && mechanicProfileRequiresMovement)",
        "if (!caster || !castSpell)",
        "for (float angleOffset : { 0.0f, float(M_PI_4), -float(M_PI_4), float(M_PI_2), -float(M_PI_2) })",
        "bot->GetFirstCollisionPosition(dodgeDistance, angle + angleOffset)",
    )
    assert "if (TryValidationRouteMovementCheck(state, bot, power, stage, activity," in route_core
    assert "if (tryValidationRouteAdds())" in trash_threat
    assert "if (tryRouteGroupHeal(bot, target))" in target_engagement
    assert "bot->GetFirstCollisionPosition(dodgeDistance, angle + angleOffset)" in validation_route_objective
    assert "if (MoveBotToPoint(state, bot, dodge.GetPositionX(), dodge.GetPositionY(), dodge.GetPositionZ()))" in validation_route_objective
    assert ': "movement_check_jump")' in validation_route_objective
    assert ': (configuredHazard ? "hazard_exit_failed" : "tactical_path_rejected");' in validation_route_objective
    assert 'action = moved ? (configuredHazard ? "move_out_of_hazard" : "movement_check_jump")' in validation_route_objective
    assert "routeHasActiveCombatIntent" in mgr
    assert "state.ValidationRouteAnchorOverrideValid && routeHasActiveCombatIntent" in mgr
    assert "else if (!routeHasActiveCombatIntent && repeatedDeathNearRoute" in mgr
    assert 'Cohort().Config.ValidationRouteKind == "boss" ? 60000 : 20000' in mgr
    assert "stale_focus_expired" in mgr
    assert "validation_route_recover_stale_focus" in mgr
    assert "findAuthoritativeRouteFocusTarget" in mgr
    assert "teacherAssistAuthoritativeFocus" in validation_route_objective
    assert "assist_unresolved_authoritative_focus" in mgr
    assert "assist_target_search_authoritative_focus" in mgr
    assert "authoritative_focus_guid_not_resolved" in mgr
    assert "authoritative_focus_reference_rejected" in mgr
    assert "authoritative_focus_no_same_map_cohort" in mgr
    assert "unresolved_authoritative_focus_unavailable" in mgr
    assert "validation_route_recover_unresolved_focus" in mgr
    assert "validation_route_teacher_assist" not in validation_route_objective
    assert "validation_route_prerequisite_no_progress" in mgr
    assert "boss_route_no_health_progress" in mgr
    assert "boss_route_slow_progress_teacher_assist" not in validation_route_objective
    assert "Party().ValidationRouteBossSlowProgressCount = 0;" in mgr
    assert "++Party().ValidationRouteBossSlowProgressCount;" in validation_route_objective
    assert "++state.ValidationRouteBossSlowProgressCount;" in validation_route_objective
    assert_ordered(
        validation_route_objective,
        'RecordEvent(state, bot, routeBossTarget ? (Cohort().Config.ValidationRouteKind == "boss" ? "boss_action" : "trash_action") : "validation_route_prerequisite"',
        'if (!routeBossTarget)\n            maybeValidationPrerequisiteNoProgressAssist(target, "current_combat_no_health_progress");',
        'if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss")\n        {\n            RecordEvent(state, bot, "boss_started"',
        'maybeValidationPrerequisiteNoProgressAssist(target, "boss_route_no_health_progress");\n        }\n        state.WasInCombat = true;',
    )
    assert 'contextText.rfind("route_target_", 0) == 0' in mgr
    assert "recordValidationRouteBossKill" in mgr
    assert "boss_death_unconfirmed" in validation_route_objective
    assert "Party().ValidationRouteConfirmedBossDeathGuid == killedTarget->GetGUID()" in validation_route_objective
    assert "isValidationRouteCombatEntry" in validation_route_objective
    assert "recordDefeatedValidationRouteTarget" in validation_route_objective
    assert 'recordDefeatedValidationRouteTarget(target, "stale_target_seen_dead")' in validation_route_objective
    assert 'recordDefeatedValidationRouteTarget(bot->GetVictim(), "stale_victim_seen_dead")' in validation_route_objective
    assert "if (!candidate || !candidate->IsAlive() || !candidate->GetHealth()" in validation_route_objective
    assert "makeExistingValidationRouteCombatReady" in validation_route_objective
    assert "target_ready_after_activation" in validation_route_objective
    assert "target_seen_activation_target" in validation_route_objective
    assert "boss_route_activation_no_visible_target_teacher_assist" not in validation_route_objective
    assert "validation_route_script_target_dead" in mgr
    assert "target_seen_not_attackable" in mgr
    assert "boss_killed" in mgr
    assert "raid_boss_killed" in mgr
    assert 'uint32 noProgressThreshold = bossRouteNoProgress ? 2 : (Cohort().Config.ValidationRouteKind == "boss" ? 4 : 12)' in mgr
    assert "validation_route_activation" in mgr
    assert "boss_route_early_activation" in mgr
    assert "boss_route_no_focus_activation_already_applied" in mgr
    assert "boss_route_wait_for_tank_activation" in mgr
    assert "boss_route_no_focus_activation_unavailable" not in mgr
    assert "advance_to_boss_route_no_focus" not in mgr
    assert "hasValidationRouteActivation" in mgr
    assert "routeDistance <= 220.0f" not in validation_route_objective
    assert_ordered(
        validation_route_objective,
        "|| routeDistance <= routeArrivalRadius",
        "&& tryValidationRouteActivation(nullptr, \"boss_route_early_activation\"))",
        "Unit* preAnchorTrashTarget = nullptr;",
        "preAnchorTrashTarget = findTrashClusterThreatTarget();",
        "if (routeDistance > routeArrivalRadius && !preAnchorTrashTarget)",
    )
    assert "ValidationRouteActivationApplied" in mgr_header
    assert "ValidationRouteTargetSearchMissCount" in mgr_header
    assert "reset_stale_boss_activation" not in mgr
    assert "MarkBotBlocked(state, bot, \"boss_route_activation_no_visible_target\")" in mgr
    assert "ValidationRouteActivationApplied" in mgr_header
    assert "ValidationRouteActivationAttempts" in mgr_header
    # This negative contract belongs to the facade itself.  The activation
    # reset is intentionally implemented by a separate runtime-state module,
    # so checking the split family would conflate two different owners.
    assert "Party().ValidationRouteActivationApplied = false;" not in facade_objective
    assert "if (Party().ValidationRouteActivationApplied)" in mgr
    assert "state.ValidationRouteActivationAttempts = Party().ValidationRouteActivationAttempts;" in mgr
    assert "Party().ValidationRouteActivationApplied = true;" in mgr
    assert "!creature || !creature->IsAlive()" in validation_focus
    assert "!isValidationRouteCombatTarget(creature) || !bot->IsValidAttackTarget(creature)" in validation_focus
    assert "RememberValidationRouteFocus(focus);" in validation_focus
    assert "isValidationRouteScriptTarget(creature)" in validation_focus
    assert "validation_route_stuck_no_fallback" in mgr
    assert "ValidationRouteOpenerTargetEntry" in mgr_header
    assert "ValidationRouteOpenerSummonEntry" in mgr_header
    assert "ValidationRouteActivationSpawnGroupId" in mgr_header
    assert "ValidationRouteActivationActionEntry" in mgr_header
    assert "ValidationRouteActivationActionId" in mgr_header
    assert "MarkValidationRouteTerminalAfterProgress" in validation_terminal
    assert "RecordEvent(state, bot, \"dungeon_trash_cleared\"" in mgr
    assert "RecordRouteProgress(context.State, context.Bot, context.Target, stuckReason" in read(
        BOT_DIR / "BotWorldPopulationMgrUpdateBotPreparation.cpp"
    )
    assert "BotWorld.ValidationRoute.OpenerTargetEntry" in mgr
    assert "BotWorld.ValidationRoute.OpenerSummonEntry" in mgr
    assert "BotWorld.ValidationRoute.ActivationSpawnGroupId" in mgr
    assert "BotWorld.ValidationRoute.ActivationActionEntry" in mgr

    get_dungeon_role = function_body(mgr, "char const* BotWorldPopulationMgr::GetDungeonRole")
    assert_ordered(
        get_dungeon_role,
        "if (roles & lfg::PLAYER_ROLE_HEALER)",
        "std::string botRole = sBotMgr->GetBotRoleName(bot->GetGUID());",
        'CharacterDatabase.PQuery("SELECT role FROM character_bot_pool',
        "if (Group* group = bot->GetGroup())",
        "if (group->GetLfgRoles(bot->GetGUID()) & lfg::PLAYER_ROLE_DAMAGE)",
    )
    assert "BotWorld.ValidationRoute.ActivationActionId" in mgr
    assert "isValidationRouteScriptTarget" in mgr
    assert "candidateOpener && !currentOpener" in mgr
    assert "SpawnGroupSpawn(Cohort().Config.ValidationRouteActivationSpawnGroupId" not in mgr
    assert "creature->AI()->DoAction(Cohort().Config.ValidationRouteActivationActionId)" not in mgr
    assert "bot->SummonCreature(Cohort().Config.ValidationRouteOpenerSummonEntry" not in mgr
    assert "SetData, SpawnGroupSpawn, AI::DoAction, or SummonCreature" in mgr
    assert "bot->SummonCreature(Cohort().Config.ValidationRouteTargetEntry, targetPos" not in mgr
    assert "routeTargetActivationFallback" not in mgr
    assert 'if (Cohort().Config.ValidationRouteKind == "boss" && std::string(GetDungeonRole(bot)) != "tank")' in mgr
    existing_activation = validation_route_objective.split("auto makeExistingValidationRouteCombatReady", 1)[1].split("auto tryValidationRouteActivation", 1)[0]
    assert "SetFaction" not in existing_activation
    assert "RemoveFlag" not in existing_activation
    assert "SetInCombatWith" not in existing_activation
    assert "AttackStart" not in existing_activation
    assert "float routeArrivalRadius =" in mgr
    assert "float routeArrivalRadius = 18.0f;" in validation_route_objective
    assert 'routeArrivalRadius = routeProfile.MovementDirective == "melee" ? 8.0f : 30.0f;' in validation_route_objective
    assert "bot->AttackStop();" not in facade_objective
    assert "SubmitMeleeAutoAttackIntent" in facade_objective
    assert "BotMeleeAutoAttack::Kind::Suppress" in facade_objective
    assert "ValidationRouteClusterRadiusYards > routeArrivalRadius" not in validation_route_objective
    assert "if (!preAnchorTrashTarget)\n            preAnchorTrashTarget = findNearestTrashClusterMob();" in validation_route_objective
    assert "if (routeDistance > routeArrivalRadius && !preAnchorTrashTarget)" in validation_route_objective
    assert "Cohort().Config.ValidationRouteActivationSpawnGroupId" in mgr
    assert "BotWorld.ValidationRoute.ActivationDataId" in mgr
    assert "BotWorld.ValidationRoute.ActivationSummonEntry" in mgr
    assert "activation_applied_no_visible_target" in mgr
    assert "InstanceScript* instance" in mgr
    assert "blocker_path_no_progress" in mgr
    assert "Unit::DealDamage(bot, prerequisiteTarget, damage" not in validation_route_objective
    assert "creature->IsInEvadeMode() || creature->HasUnitState(UNIT_STATE_EVADE)" in mgr
    assert "hasStrictPathToValidationRouteTarget(creature)" in mgr
    assert "isValidationRouteObjectiveTarget" in mgr
    assert 'return Cohort().Config.ValidationRouteKind == "boss"' in mgr
    assert "isEligibleTrashClusterMob(creature)" in mgr
    assert "markValidationRouteTrashFailed" in mgr
    assert "validation_trash_no_progress" in mgr
    assert "validation_trash_requires_damage_progress" in mgr
    assert "lastCombatAttemptTargetsDifferentPackMob" in mgr
    validation_no_progress = read(VALIDATION_NO_PROGRESS)
    assert_ordered(
        validation_no_progress,
        "bool trashRouteTargetContext",
        "if (trashRouteTargetContext)",
        'if (std::string(GetDungeonRole(bot)) != "tank")',
        "return false;",
    )
    assert "isValidationRoutePackEntry(state.LastCombatAttempt.TargetEntry)" in mgr
    assert "elapsedNoProgressSamples" in mgr
    assert "noProgressSampleIntervalMs = 5000" in mgr
    assert 'bot->GetMap() && bot->GetMap()->IsRaid() ? 2' not in mgr
    assert 'RecordCombatAttempt(*state, bot, target, "executor_check", &action, BotActionResult::Ok);' not in mgr
    assert "findTrashClusterThreatTarget" in mgr
    assert "validation_route_stuck_no_fallback" in mgr
    assert "state.ValidationRouteAnchorOverrideValid && routeHasActiveCombatIntent" in validation_route_objective
    assert "&& !routeHasCurrentGenerationLivePackAuthority)" in validation_route_objective
    assert 'uint32 routeTargetNoProgressThreshold = Cohort().Config.ValidationRouteKind == "boss" ? 5 : 20;' in mgr
    assert "Party().ValidationRouteFocusGuid.Clear();" in mgr
    assert "state.QuestWork.SelectedTargetGuid.Clear();" in mgr
    assert "regroup_tank_focus_mismatch" in mgr
    assert "follow_anchor_tank_focus_mismatch" in mgr
    assert "hold_anchor_tank_focus_mismatch" in mgr
    assert "nearestMatchingEntry" in mgr
    assert 'return Cohort().Config.ValidationRouteKind == "boss" ? nearestMatchingEntry : nullptr;' in mgr
    assert "Player* member = GetBot(cohortState)" in function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    assert "SELECT role FROM character_bot_pool WHERE guid" in mgr
    assert 'poolRole.find("tank")' in mgr
    assert "if (routeProximity > 120.0f)" in mgr
    assert 'if (std::string(GetDungeonRole(bot)) != "tank"\n        && (Cohort().Config.ValidationRouteKind != "boss" || routeDistance <= routeArrivalRadius))' in mgr
    assert 'if (std::string(GetDungeonRole(bot)) != "tank"\n        && (Cohort().Config.ValidationRouteKind != "boss" || routeDistance <= routeArrivalRadius))' in active_combat
    assert_ordered(
        target_engagement,
        "Unit* preAnchorTrashTarget = nullptr;",
        "moveToRouteAnchor();",
    )
    assert_ordered(
        function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective"),
        '&& !(Cohort().Config.ValidationRouteKind == "boss" && Party().ValidationRouteActivationApplied)',
        "MoveBotToPoint(state, bot, anchor->GetPositionX(), anchor->GetPositionY(), anchor->GetPositionZ());",
        'RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_no_focus"',
        "boss_route_wait_for_tank_activation",
        "action = \"validation_route_hold_anchor\";",
        "RecordEvent(state, bot, \"validation_route_regroup\", anchor, \"hold_anchor_no_focus\"",
    )
    assert_ordered(
        function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective"),
        "target = routeTarget;",
        "float engageRange = routeEngageRange(bot, target, spellId);",
        'action = moved ? "move_to_validation_route_target" : "hold_tactical_path_rejected";',
        'RecordEvent(state, bot, "validation_route_target_search", target, moved ? "approach_target" : "tactical_path_rejected"',
        "BotActionResult pull = profileAction.AutoAttackMode == \"melee\"",
        '"validation_route_melee_engagement"',
        "RecordEvent(state, bot, Cohort().Config.ValidationRouteKind == \"boss\" ? \"boss_action\"",
    )
    assert 'eventName.rfind("validation_route", 0) == 0' in mgr
    assert 'context.State.LastDecisionHandler = "smart_loot";' in legacy_decision
    assert_ordered(
        mgr,
        "if (!routeTarget && seenRouteTarget)",
        "RecordEvent(state, bot, \"validation_route_prerequisite\"",
        "action = \"validation_route_target_blocked\";",
    )
    assert_ordered(
        legacy_decision,
        "TryValidationRouteObjective(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action, context.Target)",
        "else if (context.CanInterleaveHubProfession && TryProfessionMemoryAction(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action))",
        "&& !(context.Target && !context.Target->IsAlive())",
        "&& (context.ChosenActivity.Activity == BotProgressionActivity::Questing || context.HasActiveQuestObjective || Cohort().Config.QuestFirst || context.State.NewlyAcceptedQuestId || context.HasNearbyQuestGiver)",
        "TryQuesting(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity)",
        "TrySmartGearDecision(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action)",
        "TryProfessionMemoryAction(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action)",
        "else if (!context.Bot->IsInCombat() && context.ChosenActivity.Activity == BotProgressionActivity::VendorRepairTrain)",
    )
    assert "BotGearUpgradeEvaluation evaluation = BotLongTermProgressionBrain::EvaluateGearUpgrade(bot);" in mgr
    assert "lootDecision = evaluation.Upgrade ? \"need_upgrade\" : (evaluation.CanEquip || hasValue ? \"greed_value\" : \"pass_invalid\")" in mgr
    assert "bot->EquipItem(equipDest, item, true);" in mgr
    assert "RecordEvent(state, bot, \"smart_loot_decision\"" in mgr
    assert "RecordGearEvaluation(state, bot, evaluation" in mgr
    assert "std::string(eventType) == \"smart_loot_decision\"" in mgr
    assert "EvaluateGearTemplate(Player const* bot, ItemTemplate const* proto" in read(ROOT / "src/server/game/Bots/BotLongTermProgressionBrain.h")
    progression = read(ROOT / "src/server/game/Bots/BotLongTermProgressionBrain.cpp")
    learning_policy = read(ROOT / "src/server/game/Bots/BotExperienceLearningPolicy.cpp")
    assert "BotLongTermProgressionBrain::EvaluateGearTemplate" in progression
    assert "score.LearnedScore = std::max(-30.0f, std::min(30.0f, learned.Score));" in progression
    assert "float avgReward = Clamp(stats.AvgReward, -25.0f, 25.0f);" in learning_policy
    assert "reward = Clamp(reward, -50.0f, 50.0f);" in learning_policy
    assert "FROM creature_loot_template clt INNER JOIN creature c ON c.id = clt.Entry" in mgr
    assert "FROM gameobject_loot_template glt INNER JOIN gameobject g ON g.id = glt.Entry" in mgr
    assert "smart_loot_candidates" in mgr
    assert "BotLongTermProgressionBrain::EvaluateGearTemplate(bot, proto)" in mgr
    assert "valid_action_mask" in mgr
    assert "RecordDecisionReplay(state, bot, nullptr, \"smart_loot_roll_policy\", lootDecision" in mgr
    assert "TryProfessionMemoryAction(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action)" in legacy_decision
    assert 'context.State.LastDecisionHandler = "profession_memory";' in legacy_decision
    assert "NextProfessionDecisionMs" in mgr_header
    assert "PreferMaterialMemoryAction" in mgr_header
    assert "SELECT source_type, source_entry, recipe_spell_id, item_id, map_id, zone_id, area_id, x, y, z FROM bot_memory_recipe_sources" in mgr
    assert "source\\\":\\\"world_recipe_source_index" in mgr
    assert "FROM creature_trainer ct INNER JOIN trainer_spell ts ON ts.TrainerId = ct.TrainerId INNER JOIN creature c ON c.id = ct.CreatureId" in mgr
    assert "FROM npc_vendor nv INNER JOIN creature c ON c.id = nv.entry" in mgr
    assert "recipe_candidates" in mgr
    assert "INSERT INTO bot_memory_recipe_sources" in mgr
    assert "RecordEvent(state, bot, \"profession_recipe_source\"" in mgr
    assert "PathGenerator path(bot);" in mgr
    assert "path.CalculatePath(x, y, z, false)" in mgr
    assert "PATHFIND_INCOMPLETE" in mgr
    assert "PATHFIND_SHORTCUT" in mgr
    assert "PATHFIND_FARFROMPOLY" in mgr
    assert "PATHFIND_NOT_USING_PATH" in mgr
    assert "route_destination_unreachable" in mgr
    assert "route_destination_partial_path" in mgr
    assert "route_destination_shortcut_path" in mgr
    assert "route_destination_off_mesh" in mgr
    assert "alternatePathScore" not in function_body(mgr, "bool BotWorldPopulationMgr::MoveBotToPoint")
    assert "state.PreferMaterialMemoryAction = true;" in mgr
    assert "state.NextProfessionDecisionMs = NowMs() + 3000;" in mgr
    assert "situation = \"profession_recipe_acquisition\";" in mgr
    assert "action = \"plan_trainer_recipe_source\";" in mgr
    assert "action = \"plan_vendor_recipe_source\";" in mgr
    assert "action = \"plan_profession_recipe_source\";" in mgr
    assert "SELECT source_type, source_entry, item_id, observed_count, map_id, x, y, z FROM bot_memory_material_sources" in mgr
    assert "source\\\":\\\"world_item_source_index" in mgr
    assert "FROM creature_loot_template clt INNER JOIN creature c ON c.id = clt.Entry" in mgr
    assert "FROM gameobject_loot_template glt INNER JOIN gameobject g ON g.id = glt.Entry" in mgr
    assert "ORDER BY ((x - %f) * (x - %f) + (y - %f) * (y - %f)) LIMIT 1" in mgr
    assert "INSERT INTO bot_memory_material_sources" in mgr
    assert "bool BotWorldPopulationMgr::MoveBotToPoint" in mgr
    movement_adapter = read(BOT_DIR / "BotWorldPopulationMgrMovement.cpp")
    movement_planner = read(MOVEMENT_PLANNER)
    assert 'return reject("route_destination_recently_failed",' in movement_planner
    assert "if (recentFailureMemory && !intent.AllowRecentFailureRetry)" in movement_planner
    assert "intent.AllowRecentFailureRetry = Cohort().Config.ValidationRouteEnable;" in movement_adapter
    assert "RecordEvent(state, bot, \"material_farming_source\"" in mgr
    assert "state.PreferMaterialMemoryAction = false;" in mgr
    assert "situation = \"material_farming\";" in mgr
    assert "action = \"plan_material_farming_source\";" in mgr
    assert_ordered(
        mgr,
        "if (state.PreferMaterialMemoryAction)",
        "if (emitMaterialSource())",
        "return emitRecipeSource();",
        "if (emitRecipeSource())",
        "if (emitMaterialSource())",
    )

    assert_ordered(
        questing,
        "SelectQuestGiver(bot, true, &questId, &state)",
        "turnin_counter_reconciled",
        "RecordEvent(state, bot, \"mob_killed\", nullptr, \"turnin_counter_reconciled\"",
        "SubmitNativeQuestReward(bot, turnIn, questId, rewardChoice)",
    )

    assert_ordered(
        questing,
        "SelectQuestGiver(bot, true, &questId, &state)",
        "FindQuestTurnInDestination(bot, questStatus.first, turnInRoute)",
        "quest_hub_sweep",
        "FindQuestObjective(bot, lastAcceptedQuestId, acceptedObjective)",
        "ResolveObjectiveRoutePoint(bot, acceptedObjective, route)",
        "MoveBotToPoint(state, bot, route.X, route.Y, route.Z);",
        "BuildQuestPortfolioPlan(bot, state)",
        "FindQuestPickupDestination(bot, state, pickup)",
    )
    assert "leave_unsupported_quest_giver" in questing
    assert 'state.LastObjectiveNotFoundReason != "chain_step_accepted"' in questing

    for field in [
        "active_quest_count",
        "quest_bucket_id",
        "quest_bucket_objective_count",
        "quest_bucket_center",
        "quest_search_radius",
        "quest_search_destination",
        "last_no_quest_reason",
        "last_quest_classification",
        "last_bucket_selection_reason",
    ]:
        assert field in debug


def test_move_bot_to_point_only_terminalizes_strategic_route_failures():
    mgr = read(BOT_MGR)
    move_bot_to_point = function_body(mgr, "bool BotWorldPopulationMgr::MoveBotToPoint")
    movement_evidence = read(MOVEMENT_EVIDENCE)
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "bool terminalOnFailure" in mgr
    assert "intent.TerminalOnFailure = terminalOnFailure;" in move_bot_to_point
    assert_ordered(
        movement_evidence,
        "if (intent.TerminalOnFailure)",
        "state.ValidationRouteTerminalState = true;",
        'RecordEvent(state, bot, "validation_route_recovery"',
    )
    assert "moveToRouteAnchor();" in read(TARGET_ENGAGEMENT)
    assert "Callbacks.MoveToRouteAnchor()" in read(TERMINAL_ARRIVAL)
    assert "auto moveToRouteAnchor = [&]() -> bool" in read(BOT_MGR_CORE)
    assert "float floorZ = routeMap->GetHeight(bot->GetPhaseShift(), routeAnchorX, routeAnchorY, routeAnchorZ + 2.0f, true, 8.0f);" in route_objective
    assert "if (floorZ > INVALID_HEIGHT && std::fabs(floorZ - routeAnchorZ) <= 8.0f)\n            routeAnchorZ = floorZ;" in route_objective
    assert 'bool terminalOnFailure = Cohort().Config.ValidationRouteKind != "descent";' in route_objective
    assert "return MoveBotToPoint(state, bot, routeAnchorX, routeAnchorY," in route_objective
    assert "routeAnchorZ, terminalOnFailure," in route_objective
    assert "BotMovementArbitration::Owner::Route" in route_objective
    assert "BotMovementArbitration::Priority::Route" in route_objective
    assert "MoveBotToProfileRange(state, bot, target, &profileAction)" in route_objective
    assert "hold_tactical_path_rejected" in route_objective
    assert 'moved ? "approach_target" : "tactical_path_rejected"' in route_objective
    assert "GetFirstCollisionPosition(profileAction.MinRange" not in route_objective


def test_walkable_descent_uses_native_paths_while_unresolved_falls_stay_fail_closed():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    anchor_move = route_objective.split("auto moveToRouteAnchor = [&]() -> bool", 1)[1].split("auto routeFocusTankOwned", 1)[0]
    arrival = read(TERMINAL_ARRIVAL)

    assert 'bool terminalOnFailure = Cohort().Config.ValidationRouteKind != "descent";' in anchor_move
    assert "MoveBotToPoint(state, bot, routeAnchorX, routeAnchorY," in anchor_move
    assert "routeAnchorZ, terminalOnFailure," in anchor_move
    assert "BotMovementArbitration::Owner::Route" in anchor_move
    assert "BotMovementArbitration::Priority::Route" in anchor_move
    assert_ordered(
        arrival,
        'if (Manager.Cohort().Config.ValidationRouteKind == "descent"',
        "&& !Manager.Cohort().Config.ValidationRouteDescentAction.empty()",
        'Action = "validation_route_descent_blocked";',
        "bool const moved = Callbacks.MoveToRouteAnchor();",
        'Action = moved ? "move_to_validation_route_anchor" : "validation_route_hold_anchor";',
    )
    assert "MoveJump(" not in arrival
    assert "TeleportTo(" not in arrival
    assert "state.ValidationRouteTerminalState = true;" not in anchor_move

    movement_adapter = read(BOT_DIR / "BotWorldPopulationMgrMovement.cpp")
    move_bot_to_point = read(MOVEMENT_PLANNER)
    for traversal_mode in (
        '"native_partial_path_backoff"',
        '"native_walkable_step"',
        '"native_walkable_step_backoff"',
    ):
        assert traversal_mode in move_bot_to_point
    assert 'Cohort().Config.ValidationRouteDescentAction\n            == "native_walkable_descent"' in movement_adapter
    assert "else if (!strictNativeDescent && progressiveStaticRoute" in move_bot_to_point
    assert "if (!segmentSelected && progressiveStaticRoute && !strictNativeDescent)" in move_bot_to_point
    assert 'return reject("native_descent_complete_path_required",' in move_bot_to_point
    assert '"native_bounded_descent_jump"' not in move_bot_to_point
    assert "MoveJump(" not in move_bot_to_point
    assert "MoveFall(" not in move_bot_to_point
    assert "HandleFall(" not in move_bot_to_point
    assert "SetFallInformation(" not in move_bot_to_point
    assert "TeleportTo(" not in move_bot_to_point
    assert "NearTeleportTo(" not in move_bot_to_point


def test_move_bot_to_point_keeps_matching_active_motion():
    move_bot_to_point = read(MOVEMENT_EXECUTOR)
    movement_lease = read(BOT_DIR / "BotWorldPopulationMgrMovementLease.cpp")
    assert "constexpr float ActiveDestinationEpsilon = 0.1f;" in movement_lease
    assert "GetMotionSlotType(MOTION_SLOT_ACTIVE)" in movement_lease
    assert "observation.NativePointPathActive = nativeActiveMotionType" in movement_lease
    assert "nativeActiveMotionType == CHASE_MOTION_TYPE" in movement_lease
    assert "static_cast<ChaseMovementGenerator*>(active)->GetTarget()" in movement_lease
    assert "state.ActivePathTargetGuid\n                == intent.DynamicTarget->GetGUID()" in movement_lease
    assert "state.IsMoving || active.NativePointPathActive" in move_bot_to_point
    assert "if (active.NativePointPathActive || active.NativeTargetChaseActive)" in move_bot_to_point
    assert_ordered(
        move_bot_to_point,
        "state.ActivePathValid",
        "active.ScopeMatches && active.MatchingDestination",
        "return true;",
        "bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);",
        "bot->GetMotionMaster()->MoveChase(intent.DynamicTarget);",
        "bot->GetMotionMaster()->MovePoint(0, intent.X, intent.Y, intent.Z",
    )
    assert "state.ActivePathSegmentToX = plan.SegmentX;" in read(MOVEMENT_EVIDENCE)
    assert "state.ActivePathTraversalMode = plan.TraversalMode;" in read(MOVEMENT_EVIDENCE)


def test_move_bot_to_profile_range_projects_approaches_to_terrain():
    profile_range = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::MoveBotToProfileRange")
    assert "auto moveToTerrainProjectedPoint = [&](float x, float y, float z)" in profile_range
    assert "Map* map = bot->GetMap();" in profile_range
    assert "map->GetHeight(bot->GetPhaseShift(), x, y, z + 2.0f, true, 64.0f)" in profile_range
    assert "if (floorZ == INVALID_HEIGHT)\n            return false;" in profile_range
    assert "return MoveBotToPoint(state, bot, x, y, floorZ, false," in profile_range
    assert "BotMovementArbitration::Priority::Combat, reference);" in profile_range
    assert "Player* partyRangedAnchor = nullptr;" in profile_range
    assert 'std::string(GetDungeonRole(member)) == "healer"' in profile_range
    assert "member->IsWithinLOSInMap(reference)" not in profile_range
    assert "for (float spread : { 3.0f, -3.0f, 0.0f })" in profile_range
    assert "partyRangedAnchor->GetPositionX() + std::cos(tangentAngle) * spread" in profile_range
    assert "float candidateRange = reference->GetExactDist(rangedPosition);" in profile_range
    assert_ordered(
        profile_range,
        "PathGenerator approachPath(bot);",
        "bool const completeNativeApproach",
        "if (MoveBotToPoint(state, bot, x, y, z, false,",
        "for (float const nativePathSegment",
    )
    assert "bool movingOutward = distance < desiredRange - 1.0f;" in profile_range
    assert "reference->GetAngle(bot) : bot->GetAngle(reference)" in profile_range
    assert "bot->GetFirstCollisionPosition(travelDistance, relativeBearing + angleOffset)" in profile_range
    assert "reference->GetFirstCollisionPosition(desiredRange" not in profile_range
    assert 'std::string(GetDungeonRole(member)) == "tank"' in profile_range
    assert "member->GetExactDist(reference) <= 12.0f" in profile_range
    assert "float ringRanges[] = { desiredRange, std::max(minimumRingRange, desiredRange - 2.0f) };" in profile_range
    assert "for (uint8 ringIndex = 0; ringIndex < 16; ++ringIndex)" in profile_range
    assert "reference->GetPositionX() + std::cos(angle) * ringRange" in profile_range
    assert "tankAnchor->GetFirstCollisionPosition" not in profile_range
    assert "MoveChase(reference, desiredRange)" not in profile_range
    assert "float minimumCandidateRange = movingOutward" in profile_range
    assert "if (candidateRange < minimumCandidateRange" in profile_range
    assert "|| bot->GetExactDist(rangedPosition) < minimumMovementDistance)" in profile_range
    assert "if (moveToTerrainProjectedPoint(rangedPosition.GetPositionX(), rangedPosition.GetPositionY(), rangedPosition.GetPositionZ()))" in profile_range
    assert "return true;" in profile_range


def test_confirmed_direct_boss_death_emits_route_terminal_without_manifest():
    confirmed_death = function_body(read(BOT_MGR), "void BotWorldPopulationMgr::NotifyCreatureDeath")
    terminal_block = confirmed_death.split('if (Cohort().Config.ValidationRouteKind == "boss")', 1)[1]
    assert 'state.ValidationRouteTerminalReason = "boss_killed";' in terminal_block
    assert 'RecordEvent(*reporterState, reporter, "validation_route_terminal"' in terminal_block
    assert_ordered(
        terminal_block,
        'state.ValidationRouteTerminalReason = "boss_killed";',
        'if (!Party().ValidationRouteManifest.empty() && Cohort().Config.ValidationRouteAdvanceMode == "terminal")',
        'RecordEvent(*reporterState, reporter, "validation_route_terminal"',
    )


def test_direct_route_config_loads_mechanics_without_manifest():
    load_config = function_body(read(BOT_MGR), "void BotWorldPopulationMgr::LoadConfig")
    for key in [
        "BotWorld.ValidationRoute.AddTargetEntries",
        "BotWorld.ValidationRoute.PackTargetEntries",
        "BotWorld.ValidationRoute.HazardSourceEntry",
        "BotWorld.ValidationRoute.HazardDetectionSpellId",
        "BotWorld.ValidationRoute.HazardDamageSpellId",
        "BotWorld.ValidationRoute.HazardShape",
        "BotWorld.ValidationRoute.HazardRadiusYards",
        "BotWorld.ValidationRoute.HazardSafetyMarginYards",
        "BotWorld.ValidationRoute.ClusterRadiusYards",
    ]:
        assert key in load_config


def test_active_hazard_exit_cannot_be_preempted_by_combat_movement():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    exit_guard = route_objective.split("else if (state.ActivePathValid && state.IsMoving)", 1)[1].split(
        "Unit* caster = nullptr;", 1
    )[0]
    assert 'situation = "validation_route_mechanic";' in exit_guard
    assert 'action = "move_out_of_hazard";' in exit_guard
    assert "return true;" in exit_guard


def test_completed_hazard_exit_holds_safe_side_while_hazard_is_active():
    movement = read(VALIDATION_ROUTE_MOVEMENT_FAMILY)

    assert "outsideHazard && hazardActive && state.ValidationRouteDodgeUntilMs > nowMs" in movement
    assert 'action = "hold_outside_hazard";' in movement
    assert 'configuredHazardShape == "radial" ? 6000 : 3000' in movement
    assert "if (!configuredHazard\n            && state.ValidationRouteDodgeCasterGuid == caster->GetGUID()" in movement


def test_trash_swarm_waits_for_secure_tank_threat_before_dps_release():
    route = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "trashThreatControl.SecureTankCount * 10 < trashThreatControl.EngagedCount * 9" in route
    assert "trashThreatControl.TankOwnedCount * 10 >= trashThreatControl.EngagedCount * 9" in route
    assert "tankThreat >= 2000.0f && tankThreat >= highestPartyThreat * 2.5f" in route
    assert '"hold_for_secure_trash_threat"' in route
    assert '"focused_damage_during_trash_threat_build"' in route
    assert "ResolveProfileCombatAction(bot, tankFocus, 1, false)" in route
    assert '"trash_focused_melee_engagement"' in route
    assert "BotActionResult result = focusedAction.AutoAttackMode == \"melee\"" in route
    assert 'action = moved ? "move_to_focused_trash_target"' in route
    assert "bot->InterruptNonMeleeSpells(false);" in route
    assert "pet->AttackStop();" in route
    assert '"trash_density_area_threat"' in route
    assert "trashThreatControl.EngagedCount, true" in route
    assert '"hand_of_salvation_healer_trash_threat_drop"' in route


def test_dungeon_healer_holds_pending_pull_and_blood_tank_taunts_healer_target():
    heal_helper = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteGroupHeal"
    )
    assert "pendingDungeonPullCount" in heal_helper
    assert "healer->GetExactDist2d(creature) > 35.0f" in heal_helper
    assert "focusedPendingPull = combatTarget" in heal_helper
    assert "healer->InterruptNonMeleeSpells(false)" in heal_helper
    assert '"healer_hold_for_pending_dungeon_pull"' in heal_helper
    assert '"healer_wait_for_pending_dungeon_pull"' in heal_helper
    assert_ordered(
        heal_helper,
        "pendingDungeonPullCount > 0",
        "MoveBotToPoint(state, healer",
        '"healer_hold_for_pending_dungeon_pull"',
        'return true;',
    )

    tank_branch = read(
        BOT_DIR / "BotWorldPopulationMgrValidationRouteTankTrashRecovery.cpp"
    )
    assert "CLASS_DEATH_KNIGHT" in tank_branch
    assert "CLASS_WARRIOR" in tank_branch
    assert "uint32 tauntSpell" in tank_branch
    assert "56222" in tank_branch
    assert "trashThreatControl.HealerOwnedTargets" in tank_branch
    assert "TryCastCombatSpell(bot, healerTauntTarget, tauntSpell)" in tank_branch
    assert '"dark_command_healer_trash_pickup"' in tank_branch
    assert '"taunt_healer_trash_pickup"' in tank_branch
    assert '"tank_trash_icebound_fortitude"' in tank_branch
    assert '"tank_trash_death_strike"' in tank_branch
    assert "TryCastFriendlySpell(bot, bot, 48792)" in tank_branch
    assert "TryCastCombatSpell(bot, deathStrikeTarget, 49998)" in tank_branch
    assert_ordered(
        tank_branch,
        "UnitHealthPct(bot) <= 0.75f",
        '"tank_trash_death_strike"',
        "UnitHealthPct(bot) <= 0.55f",
        '"tank_trash_icebound_fortitude"',
    )


def test_validation_route_exact_hazards_scope_secondary_generic_cast_dodges_to_current_pack():
    movement = read(VALIDATION_ROUTE_MOVEMENT_FAMILY)

    assert "bool currentNodeHasConfiguredHazard = Cohort().Config.ValidationRouteHazardSourceEntry != 0;" in movement
    assert "bool profileAllowsGenericCastMovement" in movement
    assert "profileAllowsGenericCastMovement || !hazardDefinitions.empty()" in movement
    assert "for (ValidationRouteManifestNode const& node : Party().ValidationRouteManifest)" not in movement
    assert 'bool active = definition->Shape == "radial"\n        && !bot->IsValidAttackTarget(hazard);' in movement
    scoped_candidate = movement[
        movement.index("auto isScopedGenericCastCandidate"):
        movement.index("uint64 const nowMs")
    ]
    assert "BotRaidHazard::ShouldInspectGenericCastCandidate" in scoped_candidate
    assert "Cohort().Config.ValidationRouteTargetEntry" in scoped_candidate
    assert "hazardDefinitionFor(creature->GetEntry(), 0) != nullptr" in scoped_candidate
    assert "Party().ValidationRoutePackGeneration" in scoped_candidate
    assert "== Party().ValidationRouteGeneration" in scoped_candidate
    assert "Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())" in scoped_candidate
    assert "Party().ValidationRoutePackDeathGuids.find(creature->GetGUID())" in scoped_candidate
    assert "Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID())" in scoped_candidate
    assert "callbacks.IsCombatLinked(creature)" in scoped_candidate
    assert "isScopedGenericCastCandidate(preferredTarget)" in movement
    assert "isScopedGenericCastCandidate(candidate) && inspectCaster(candidate)" in movement
    assert "if (!caster && !currentNodeHasConfiguredHazard && profileAllowsGenericCastMovement)" not in movement


def test_validation_route_hazard_exit_rejects_overlapping_active_sources():
    movement = read(VALIDATION_ROUTE_MOVEMENT_FAMILY)

    assert "struct Active" in movement
    assert "std::vector<ActiveHazard> activeHazards" in movement
    assert "refreshActiveHazards" in movement
    assert "positionOutsideActiveHazards" in movement
    assert "auto pathOutsideActiveHazards" in movement
    assert "PathGenerator path(bot);" in movement
    assert "dodgeCandidates.erase" in movement
    assert "return !positionOutsideActiveHazards(candidate);" in movement


def test_holy_priest_primes_chakra_and_gates_friendly_holy_word_on_serenity():
    mgr = read(BOT_MGR)
    healer = function_body(
        mgr, "bool BotWorldPopulationMgr::TryValidationRouteGroupHeal"
    )
    profile_sql = read(ROOT / "sql/custom/world/2026_07_16_00_stonecore_wowhead_guide_rotations.sql")
    serenity_sql = read(ROOT / "sql/custom/world/2026_07_16_01_stonecore_holy_priest_serenity.sql")
    direct_cast_sql = read(ROOT / "sql/custom/world/2026_07_16_02_stonecore_holy_word_serenity_cast.sql")

    assert "healer->HasSpell(14751)" in healer
    assert "!healer->HasAura(14751)" in healer
    assert "!healer->HasAura(81208)" in healer
    assert "tryRouteFriendlySpell(healer, 14751)" in healer
    assert '"chakra_serenity_primed"' in healer
    assert "88625,'heal_fast','holy_word_serenity,spot_heal'" in profile_sql
    assert "`action`.`required_self_aura` = 81208" in serenity_sql
    assert "`action`.`spell_id` = 88625" in serenity_sql
    assert "`action`.`spell_id` = 88684" in direct_cast_sql
    assert "AND `action`.`spell_id` = 88625" in direct_cast_sql


def test_applied_ground_danger_spell_shape_contract():
    persistent_area_aura = 27
    periodic_damage = 3
    periodic_damage_percent = 89

    def should_dodge(is_positive: bool, effects: list[tuple[int, int]]) -> bool:
        return not is_positive and any(
            effect == persistent_area_aura and aura in {periodic_damage, periodic_damage_percent}
            for effect, aura in effects
        )

    dampening_wave_82415 = [(2, 0), (6, 301)]
    crystal_barrage_86881 = [(persistent_area_aura, periodic_damage), (3, 0)]
    assert not should_dodge(False, dampening_wave_82415)
    assert should_dodge(False, crystal_barrage_86881)
    assert all(should_dodge(False, crystal_barrage_86881) for _party_member in range(2))
    assert not should_dodge(True, crystal_barrage_86881)
    assert not should_dodge(False, [])


def test_botauto_diagnosis_and_trace_surface():
    mgr_header = read(BOT_MGR_HEADER)
    mgr = read(BOT_MGR)
    commands = read(BOT_COMMANDS)
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    diagnose = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotDiagnosisJson")
    config_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildConfigJson")
    trace = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotTraceJson")
    build_diagnosis = function_body(mgr, "BotWorldPopulationMgr::BotDiagnosis BotWorldPopulationMgr::BuildBotDiagnosis")
    diagnosis_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")
    snapshot_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDecisionSnapshotJson")
    trace_entries = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotTraceEntriesJson")
    record_decision = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")
    record_event = function_body(mgr, "void BotWorldPopulationMgr::RecordEvent")
    update_outcome_stats = function_body(mgr, "void BotWorldPopulationMgr::UpdateSemanticOutcomeStats")
    record_trace = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionTrace")
    fingerprint = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionFingerprintMemory")
    persist_fingerprint = function_body(mgr, "void BotWorldPopulationMgr::PersistDecisionFingerprintDelta")
    debug = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotDebugJson")

    assert '{ "diagnose", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert '{ "trace",   rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "GetBotDiagnosisJson" in commands
    assert "GetBotTraceJson" in commands
    assert "combatOrCasting" in update_bot
    assert "context.Bot->IsInCombat() || context.Bot->HasUnitState(UNIT_STATE_CASTING)" in update_bot
    assert "context.Bot->GetVictim() && context.Bot->GetVictim()->IsAlive()" in update_bot
    assert "context.State.MovementProgressWindowDistance += moved" in update_bot
    assert "bool movementProgress = context.State.MovementProgressWindowDistance >= 0.2f" in update_bot
    assert "if (movementProgress || context.State.MovementProgressWindowMs >= 1000)" in update_bot
    assert_ordered(
        update_bot,
        "context.Target = context.State.TargetGuid.IsEmpty()",
        "bool combatOrCasting",
        "bool movementProgress",
        "bool validationRouteComplete = Cohort().Config.ValidationRouteEnable",
        "if (!combatOrCasting && moving && !movementProgress && !validationRouteComplete && !terminalRouteAction)",
        "if (!validationRouteComplete && !terminalRouteAction && context.State.StuckTimer >= 6000)",
    )

    for symbol in [
        "LastDecisionTickMs",
        "LastDecisionSituation",
        "LastDecisionAction",
        "LastDecisionActivity",
        "LastDecisionTargetGuid",
        "LastDecisionHandler",
        "DistanceMovedSinceLastDecision",
        "LastMovementProgressMs",
        "LastPathChangeMs",
        "ConsecutiveSameDecisionCount",
        "IdleDecisionRepeatCount",
        "TargetChurnCount",
        "LoopRecoveryCooldownUntilMs",
        "LastLoopGuardrailAction",
        "LastRecoveryMode",
        "DecisionTraceEntry",
        "BotDiagnosis",
    ]:
        assert symbol in mgr_header

    base_diagnose = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotDiagnosisJson(std::string const& selector)")
    assert "diagnosis_schema_version" in base_diagnose
    assert "BuildBotDecisionSnapshotJson(state, bot)" in base_diagnose
    assert "BuildBotDiagnosisObjectJson(state, bot)" in base_diagnose
    base_trace = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotTraceJson(std::string const& selector")
    assert "trace_schema_version" in base_trace
    assert '\\"bots\\":[' in base_trace
    assert "BuildBotTraceEntriesJson(state, normalizedLimit)" in base_trace
    assert "BuildBotTraceEntriesJson(*selected, normalizedLimit)" in base_trace

    for code in [
        "moving_but_not_progressing",
        "quest_pickup_unreachable",
        "no_supported_objective",
        "stuck_repath_loop",
        "waiting_decision_tick",
        "target_rejected",
        "dead_recovery",
        "idle_no_candidate",
        "validation_route_terminal",
        "route_destination_unreachable",
        "advance_validation_route_segment",
        "inspect_dungeon_trash_cleared_evidence",
        "fail_validation_route_segment",
        "repeated_decision_loop",
        "idle_loop_guardrail",
        "target_churn_loop",
    ]:
        assert code in build_diagnosis

    for field in [
        "diagnosis_code",
        "severity",
        "confidence",
        "intent",
        "current_action",
        "blocker",
        "evidence",
        "active_quest_cluster_id",
        "quest_cooldown_count",
        "no_progress_cooldown_count",
        "pet_db_row_present",
        "pet_store_active",
        "pet_guid",
        "pet_entry",
        "pet_alive",
        "last_pet_readiness_action",
        "paladin_righteous_fury_ready",
        "paladin_seal_ready",
        "paladin_aura_ready",
        "paladin_blessing_ready",
        "paladin_divine_plea_ready",
        "validation_route_manifest_index",
        "validation_route_manifest_count",
        "validation_route_advance_mode",
        "validation_route_advance_pending",
        "validation_route_advance_reason",
        "validation_route_manifest_load_error",
        "validation_route_progress_baseline_kills",
        "validation_route_pack_generation",
        "validation_route_pack_member_count",
        "validation_route_pack_engaged_count",
        "validation_route_pack_death_count",
        "validation_route_pack_transition_count",
        "validation_route_pack_members",
        "validation_route_combat_links",
        "validation_route_pack_observed_engagement",
        "validation_route_config_kind",
        "validation_route_config_node_kind",
        "validation_route_config_target_entry",
        "validation_route_config_activation_data_id",
        "validation_route_config_activation_spawn_group_id",
        "validation_route_config_activation_action_entry",
        "validation_route_config_activation_action_id",
        "validation_route_config_activation_summon_entry",
        "validation_route_config_opener_summon_entry",
        "validation_route_has_activation",
        "validation_route_manager_activation_applied",
        "validation_route_manager_activation_attempts",
        "validation_route_distance",
        "decision_fingerprint_hash",
        "decision_fingerprint_repeat_count",
        "decision_fingerprint_failure_count",
        "consecutive_same_decision_count",
        "idle_decision_repeat_count",
        "target_churn_count",
        "loop_guardrail_count",
        "last_loop_guardrail_action",
        "last_recovery_mode",
        "next_expected_action",
        "suggested_investigation",
    ]:
        assert field in diagnosis_json

    for field in [
        "guid",
        "entry",
        "observed",
        "alive",
        "attackable",
        "evade",
        "engaged",
        "death_recorded",
        "transition_recorded",
        "victim_guid",
        "attacker_guids",
    ]:
        assert field in diagnosis_json
    assert "bot && bot->IsInWorld() && bot->GetMap()" in diagnosis_json
    assert '<< ",\\\"entry\\\":" << (creature ? creature->GetEntry() : guid.GetEntry())' in diagnosis_json
    assert "std::sort(attackerGuids.begin(), attackerGuids.end());" in diagnosis_json
    for mapping in [
        '<< ",\\"pack_generation\\":" << Party().ValidationRoutePackGeneration',
        '<< ",\\"pack_member_count\\":" << Party().ValidationRoutePackMemberGuids.size()',
        '<< ",\\"pack_engaged_count\\":" << Party().ValidationRoutePackEngagedGuids.size()',
        '<< ",\\"pack_death_count\\":" << Party().ValidationRoutePackDeathGuids.size()',
        '<< ",\\"pack_transition_count\\":" << Party().ValidationRoutePackTransitionGuids.size()',
        '<< ",\\"pack_observed_engagement\\":" << (Party().ValidationRoutePackObservedEngagement ? "true" : "false")',
    ]:
        assert mapping in config_json

    for section in [
        "identity",
        "runtime",
        "movement",
        "quest",
        "target",
        "routing",
        "decision",
        "recent_failures",
        "fingerprint_hash",
        "fingerprint_repeat_count",
        "fingerprint_failure_count",
        "recovery",
        "loop_guardrail_count",
        "last_loop_guardrail_reason",
        "quest_cooldown_count",
        "no_progress_cooldown_count",
    ]:
        assert section in snapshot_json

    for field in [
        "timestamp_ms",
        "sequence",
        "situation",
        "action",
        "quest_id",
        "target_id",
        "destination",
        "result",
        "reason_code",
        "fingerprint_repeat_count",
        "consecutive_same_decision_count",
        "idle_decision_repeat_count",
        "target_churn_count",
        "loop_guardrail_action",
        "recovery_mode",
    ]:
        assert field in trace_entries

    assert "RecordDecisionTrace(state" in record_decision
    assert "loop_guardrail_triggered" in update_bot
    assert "context.State.LoopRecoveryCooldownUntilMs = nowMs + 15000;" in update_bot
    assert "RecordDecisionFingerprintMemory(state, bot, situation, action, chosenActivity, failure);" in record_decision
    assert_ordered(
        persist_fingerprint,
        "last_recovery_result",
        'JsonEscape(state.LastRecoveryResult) << "\\""',
        "fingerprint_source",
    )
    assert_ordered(
        record_decision,
        "RecordDecisionFingerprintMemory(state, bot, situation, action, chosenActivity, failure);",
        "RecordDecisionTrace(state, situation, action, target, state.LastDecisionQuestId",
    )
    assert "bool forceTeacherEvent = eventName == \"combat_started\"" in record_event
    assert "eventName == \"objective_target_lost\"" in record_event
    assert "if (!policy.writeEvent && !forceTeacherEvent)" in record_event
    assert "reward = clampMetric(reward, -25.0f, 25.0f);" in update_outcome_stats
    assert "powerDelta = clampMetric(powerDelta, -25.0f, 25.0f);" in update_outcome_stats
    assert "state.DecisionTrace.push_back(entry)" in record_trace
    assert "state.DecisionTrace.size() > 128" in record_trace
    assert "debug_schema_version" in debug
    assert "diagnosis" in debug


def test_botauto_runtime_profiles_surface():
    manifest_path = ROOT / "dataset/bot_runtime_profiles/profiles.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile_names = {profile["name"] for profile in manifest["profiles"]}
    assert manifest["schema"] == "bot_world_runtime_profiles_v1"
    assert {"free_roam_small", "stonecore_5n", "blackwing_descent_10n", "watch_near_player"} <= profile_names
    for profile in manifest["profiles"]:
        assert isinstance(profile["name"], str) and profile["name"]
        assert isinstance(profile["target_population"], int)
    assert next(profile for profile in manifest["profiles"] if profile["name"] == "stonecore_5n")["validation_route"] == {
        "enable": True,
        "manifest_path": "dataset/validation_scenarios/validation_routes.jsonl",
        "advance_mode": "terminal",
        "scenario_id": "stonecore_5n",
    }

    conf = read(WORLDSERVER_CONF)
    mgr = read(BOT_MGR)
    mgr_header = read(BOT_MGR_HEADER)
    commands = read(BOT_COMMANDS)

    assert 'BotWorld.ProfileManifest = "dataset/bot_runtime_profiles/profiles.json"' in conf
    assert re.search(r"^BotWorld\.AutoStart\s*=\s*0$", conf, re.MULTILINE)
    assert "BotWorldExperimentProfile" in mgr_header
    assert "SelectRuntimeProfile" in mgr_header
    assert "ReloadRuntimeProfiles" in mgr_header
    assert '{ "profiles", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert '{ "profile", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "HandleAutoProfilesCommand" in commands
    assert "HandleAutoProfileCommand" in commands
    assert "SelectRuntimeProfileForCohort(cohortId, profileName)" in commands
    assert "JsonFieldIsBool" in mgr
    assert "profile_missing_name" in mgr
    assert "profile_bad_type_" in mgr
    assert "ExtractJsonLineObjects(manifestJson)" in mgr
    assert "node.ScenarioId != Cohort().Config.ValidationRouteScenarioId" in mgr
    assert_ordered(
        function_body(mgr, "void BotWorldPopulationMgr::LoadConfig"),
        'sConfigMgr->GetStringDefault("BotWorld.ProfileManifest"',
        'sConfigMgr->GetIntDefault("BotWorld.TargetPopulation"',
        "ApplyRuntimeProfile(profileItr->second)",
        "LoadValidationRouteManifest();",
    )
    status = function_body(mgr, "std::string BotWorldPopulationMgr::GetStatusJson() const")
    assert '\\"active_profile\\"' in status
    assert '\\"loaded_profile_count\\"' in status
    assert '\\"validation_route\\"' in status


def test_validation_route_movement_check_requires_classified_ground_danger():
    route = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "profileAllowsCastMovement" not in route
    assert "if (!SpellLooksLikeGroundDanger(castSpell))" in route
    assert "if (!castSpell || !castSpell->CalcCastTime(candidate->getLevel()))" in route
    assert "WorldObject const* dodgeOrigin = movementOrigin && movementOrigin != bot ? movementOrigin : caster;" in route
    assert "bot->GetRelativeAngle(dodgeOrigin) + float(M_PI)" in route
    assert 'configuredHazard\n                ? (feralHazardHandoffBiased' in route
    assert ': "movement_check_jump")' in route
    assert 'configuredHazard ? "hazard_exit_failed" : "tactical_path_rejected"' in route
    assert 'configuredHazard ? "move_out_of_hazard" : "movement_check_jump"' in route
    assert 'configuredHazard ? "hold_hazard_exit_failed" : "hold_tactical_path_rejected"' in route


def test_validation_route_cleared_trash_regroups_to_terminal_endpoint():
    mgr = read(BOT_MGR)
    route = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    readiness_call = route.index("TryValidationRouteReadiness(state, bot, target, power, stage, activity, readinessResult)")
    endpoint_move = route.index('moved ? "move_to_terminal_route_endpoint" : "terminal_route_endpoint_path_rejected"')
    regroup_block = route[route.rfind('if (Cohort().Config.ValidationRouteKind != "boss"', 0, endpoint_move):readiness_call]

    assert endpoint_move < readiness_call
    assert 'std::string(GetDungeonRole(bot)) != "tank"' in regroup_block
    assert "routeDistance > routeArrivalRadius" in regroup_block
    assert "(Party().ValidationRoutePackObservedEngagement || Party().ValidationRouteCompletedPackCount > 0)" in regroup_block
    assert "!routeFocusMemoryFresh()" in regroup_block
    assert "routeTankFocusGuid().IsEmpty()" in regroup_block
    assert "!trashClusterHasLiveMobs()" in regroup_block
    assert "!validationPartyHasActiveCombat()" in regroup_block
    assert_ordered(
        regroup_block,
        "if (TryValidationRouteMovementCheck(state, bot, power, stage, activity,",
        "return true;",
        "MoveBotToPoint(state, bot,",
        "Cohort().Config.ValidationRouteX,",
        "BotMovementArbitration::Owner::Route,",
    )
    assert "move_to_terminal_route_endpoint" in regroup_block


def test_validation_route_status_persists_terminal_and_boss_death_evidence():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    notify_death = function_body(mgr, "void BotWorldPopulationMgr::NotifyCreatureDeath")
    advance = function_body(mgr, "bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest")
    status = function_body(mgr, "std::string BotWorldPopulationMgr::GetStatusJson() const")

    assert "std::vector<ValidationRouteEvidence> ValidationRouteTerminalEvidence;" in header
    assert "std::vector<ValidationRouteEvidence> ValidationRouteBossDeathEvidence;" in header
    assert "Party().ValidationRouteBossDeathEvidence.push_back" in notify_death
    assert "Party().ValidationRouteTerminalEvidence.push_back" in advance
    assert '\\"terminal_evidence\\"' in mgr
    assert '\\"boss_death_evidence\\"' in mgr


def test_validation_route_boss_terminal_requires_unit_kill_provenance():
    mgr = read(BOT_MGR)
    mgr_header = read(BOT_MGR_HEADER)
    unit = read(ROOT / "src/server/game/Entities/Unit/Unit.cpp")
    notify_death = function_body(mgr, "void BotWorldPopulationMgr::NotifyCreatureDeath")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    advance_manifest = function_body(mgr, "bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest")

    assert "void NotifyCreatureDeath(Creature* killed);" in mgr_header
    assert_ordered(
        unit,
        "victim->setDeathState(JUST_DIED);",
        "ai->JustDied(attacker);",
        "sBotWorldPopulationMgr->NotifyCreatureDeath(creature);",
    )
    assert "killed->GetEntry() != Cohort().Config.ValidationRouteTargetEntry" in notify_death
    assert "Party().ValidationRouteEngagedBossGuid != killed->GetGUID()" in notify_death
    assert "Party().ValidationRouteEngagedBossGeneration != Party().ValidationRouteGeneration" in notify_death
    assert "Party().ValidationRouteEngagedBossMapId != killed->GetMapId()" in notify_death
    assert "Party().ValidationRouteEngagedBossInstanceId != killed->GetInstanceId()" in notify_death
    assert "Party().ValidationRouteConfirmedBossDeathGuid = killed->GetGUID();" in notify_death
    assert 'RecordEvent(*reporterState, reporter, "boss_killed", killed, "confirmed_unit_death"' in notify_death
    assert 'Party().ValidationRouteManifestAdvanceReason = "boss_killed";' in notify_death
    assert "boss_death_unconfirmed" in route_objective
    assert "&& confirmedBossDeath" in advance_manifest


def test_validation_route_terminal_paths_consume_manifest_without_waiting_for_next_tick():
    mgr = read(BOT_MGR)
    mgr_header = read(BOT_MGR_HEADER)
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    group_recovery = read(GROUP_RECOVERY)
    route_pack = read(ROUTE_PACK)
    targeting = read(TARGETING)
    route_core = read(BOT_MGR_CORE)
    advance_manifest = function_body(mgr, "bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest")
    record_decision = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")

    assert 'std::string recoveryReason = "validation_route_stuck_no_fallback";' not in update_bot
    assert 'RecordDecision(state, bot, "validation_route_recovery", "validation_route_stuck"' not in update_bot
    assert 'State.ValidationRouteTerminalReason == "validation_trash_no_progress"' in route_objective
    assert "!persistedValidationRoutePackHasLiveMembers()" in route_objective
    assert "activeValidationRoutePackTarget()" in route_objective
    assert "failedTrashPackCanRetry" in route_objective
    assert "Callbacks.IsEligibleTrash(retryableFailedTrashTarget->ToCreature())" in read(TERMINAL_ARRIVAL)
    assert "!validationPartyHasActiveCombat()" in route_objective
    assert '"failed_terminal_reopened_after_pack_death"' in route_objective
    assert '"failed_terminal_reopened_for_live_pack_reapproach"' in route_objective
    assert 'cohortState.ValidationRouteAnchorOverrideReason = "validation_route_live_pack_reapproach";' in route_objective
    assert "cohortState.LoopRecoveryCooldownUntilMs = retryNowMs + 1000;" in route_objective
    assert 'bool routeTrashPackTarget = Cohort().Config.ValidationRouteKind != "boss"' in route_objective
    assert "creature && isEligibleTrashClusterMob(creature);" in route_objective
    assert "if (routeTrashPackTarget && !botIsTank" in route_objective
    finalization = read(BOT_DIR / "BotWorldPopulationMgrUpdateBotFinalization.cpp")
    assert_ordered(
        finalization,
        "RecordDecision(context.State, context.Bot, context.Situation.c_str(), context.Action.c_str()",
        'if (context.Action == "validation_route_complete")',
        "MaybeAdvanceValidationRouteManifest();",
    )
    assert_ordered(
        route_objective,
        'Party().ValidationRouteManifestAdvanceReason = "boss_killed";',
        "MaybeAdvanceValidationRouteManifest();",
        "return true;",
    )
    assert_ordered(
        route_objective,
        "auto isEligibleTrashClusterMob",
        "bool pullable = bot->IsWithinLOSInMap(creature)",
        "&& bot->GetExactDist(creature) <= routeEngageRange(bot, creature, 0);",
        "&& (hasStrictPathToValidationRouteTarget(creature) || pullable);",
        "auto isValidationRouteObjectiveTarget",
    )
    assert "&& bot->IsWithinLOSInMap(creature)\n            && hasStrictPathToValidationRouteTarget(creature);" not in route_objective
    assert_ordered(
        route_objective,
        "Unit* preAnchorTrashTarget = nullptr;",
        "preAnchorTrashTarget = findTrashClusterThreatTarget();",
        "if (routeDistance > routeArrivalRadius && !preAnchorTrashTarget)",
        "Unit* routeTarget = preAnchorTrashTarget;",
    )
    live_cluster_block = targeting.split("auto isEligibleTrashClusterMob", 1)[1].split(
        "auto forEachActiveValidationCohortCombatCreature", 1
    )[0]
    assert "if (!bot || !creature || !creature->IsAlive() || !creature->GetHealth() || !bot->IsValidAttackTarget(creature))" in live_cluster_block
    assert "Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID())" in live_cluster_block
    assert "isPendingScriptedEventEntry(creature)" in live_cluster_block
    assert "isValidationRoutePackEntry(creature->GetEntry())" in live_cluster_block
    assert "creature->IsInEvadeMode()" in live_cluster_block
    assert "IsValidAttackTarget" in live_cluster_block
    assert "hasStrictPathToValidationRouteTarget" in live_cluster_block
    assert "bot->IsWithinLOSInMap(creature)" in live_cluster_block
    assert "bot->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) + radius + 40.0f" in route_objective
    assert 'node.ExpectedAliveCount = uint32(std::max(0, readInt(routeJson, "expected_alive_count")));' in mgr
    assert "Cohort().Config.ValidationRouteExpectedAliveCount = node.ExpectedAliveCount;" in mgr
    trash_liveness_block = route_objective.split("auto trashClusterHasLiveMobs", 1)[1].split("auto markTrashClusterCleared", 1)[0]
    assert "Cohort().Config.ValidationRouteExpectedAliveCount && Cohort().Metrics.Kills - Party().ValidationRouteProgressBaselineKills < Cohort().Config.ValidationRouteExpectedAliveCount" not in trash_liveness_block
    assert "cohortState.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();" in route_objective
    assert "cohortState.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();" in route_objective
    assert 'std::string(GetDungeonRole(bot)) != "tank"' in route_objective
    assert 'cohortState.LastNoProgressReason = "unengaged_trash_target_repath";' in route_objective
    assert 'RecordEvent(state, bot, "validation_route_recovery", prerequisiteTarget, "unengaged_trash_target_repath"' in route_objective
    arrival = read(TERMINAL_ARRIVAL)
    assert_ordered(
        arrival,
        "bool routePartyCombatActive = Callbacks.PartyHasActiveCombat();",
        "bool arrivalCombatActive = ArrivalRoute && routePartyCombatActive;",
        "Regroup and descent nodes must not suppress a natural pull",
        "if (arrivalCombatActive)",
        "Callbacks.EnrollEngagedPackMembers();",
        "if (ArrivalRoute && !arrivalCombatActive)",
        'Manager.SubmitMeleeAutoAttackIntent(State,',
        'BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,',
        '"validation_route_arrival_hold");',
    )
    assert_ordered(
        group_recovery,
        "bool currentLivePackCanContinue =\n        Manager.CurrentLiveValidationRoutePackCanContinue(",
        "if (DiscoveryLeg)\n        Callbacks.EnrollEngagedPackMembers();",
        "If most of the party or a critical role is dead",
    )
    assert_ordered(
        read(VALIDATION_NO_PROGRESS),
        "A trash route can expose the next target",
        'if (Cohort().Config.ValidationRouteKind != "boss"\n        && !prerequisiteTarget->IsInCombat()',
        "&& !prerequisiteTarget->GetVictim())",
        'RecordEvent(state, bot, "validation_route_recovery", prerequisiteTarget, "unengaged_trash_target_repath"',
        'cohortState.LastNoProgressReason = "unengaged_trash_target_repath";',
    )
    assert 'markTrashClusterCleared("trash_cluster_expected_empty");' not in route_objective
    assert "&& !Cohort().Config.ValidationRouteExpectedAliveCount" not in route_objective
    assert_ordered(
        read(VALIDATION_OUTCOMES),
        "if (Party().ValidationRouteRecordedKillGuids.find(killedTarget->GetGUID()) != Party().ValidationRouteRecordedKillGuids.end())",
        "return false;",
        "Party().ValidationRouteRecordedKillGuids.insert(killedTarget->GetGUID());",
        "++Cohort().Metrics.Kills;",
        "state.LastKilledTargetGuid = killedTarget->GetGUID();",
        "if (isValidationRouteScriptTarget(creature)",
        "if (!trashClusterHasLiveMobs())",
        '"trash_cluster_empty_pending_anchor_verification"',
    )
    assert "GuidSet ValidationRouteRecordedKillGuids;" in mgr_header
    assert "Party().ValidationRouteRecordedKillGuids.clear();" in mgr
    for symbol in [
        "std::string ValidationRouteNodeKind;",
        "GuidSet ValidationRoutePackMemberGuids;",
        "GuidSet ValidationRoutePackEngagedGuids;",
        "GuidSet ValidationRoutePackDeathGuids;",
        "GuidSet ValidationRoutePackTransitionGuids;",
        "GuidSet ValidationRoutePendingFinalTransitionGuids;",
        "GuidSet ValidationRouteFinalTransitionGuids;",
        "uint64 ValidationRoutePackGeneration",
        "bool ValidationRoutePackObservedEngagement",
    ]:
        assert symbol in mgr_header
    assert 'node.NodeKind = ExtractJsonStringField(routeJson, "node_kind");' in mgr
    assert 'node.ScriptedEventEntries = ExtractJsonUIntArrayField(routeJson, "scripted_event_entries");' in mgr
    assert 'node.ScriptedEventTransitionAuraIds = ExtractJsonUIntArrayField(routeJson, "scripted_event_transition_aura_ids");' in mgr
    assert 'ExtractJsonBoolField(routeJson, "scripted_event_require_passive", node.ScriptedEventRequirePassive);' in mgr
    assert 'Cohort().Config.ValidationRouteNodeKind = node.NodeKind;' in mgr
    assert 'Cohort().Config.ValidationRouteScriptedEventEntries = node.ScriptedEventEntries;' in mgr
    assert 'Cohort().Config.ValidationRouteScriptedEventTransitionAuraIds = node.ScriptedEventTransitionAuraIds;' in mgr
    assert "protectedEncounterEntries.insert" in route_objective
    assert "Cohort().Config.ValidationRouteScriptedEventEntries.begin()" in route_objective
    route_progress_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildRouteProgressJson")
    record_route_progress = function_body(mgr, "void BotWorldPopulationMgr::RecordRouteProgress")
    assert '<< ",\\"generation\\":" << diagnostic.Generation' in route_progress_json
    assert "diagnostic.Generation = Party().ValidationRouteGeneration;" in record_route_progress
    assert 'Cohort().Config.ValidationRouteTargetEntry = node.NodeKind == "discovery_leg" ? 0 : node.TargetEntry;' in mgr
    assert 'bool discoveryLeg = Cohort().Config.ValidationRouteNodeKind == "discovery_leg";' in route_objective
    assert_ordered(
        route_objective,
        "auto isNaturalForwardHostile",
        "auto findForwardDiscoveryTarget",
        "PathGenerator path(bot);",
        "path.GetPath();",
        "creature->GetAttackDistance(bot)",
        "candidateAlongPath",
        "guid < bestGuid",
        "return best;",
    )
    discovery_block = route_objective.split("auto findForwardDiscoveryTarget", 1)[1].split("auto isValidationRouteObjectiveTarget", 1)[0]
    assert "enrollValidationRoutePackMember" not in discovery_block
    for rejected_path in [
        "PATHFIND_NOPATH",
        "PATHFIND_NOT_USING_PATH",
        "PATHFIND_INCOMPLETE",
        "PATHFIND_SHORTCUT",
        "PATHFIND_FARFROMPOLY",
    ]:
        assert rejected_path in route_objective
    assert "if (discoveryLeg)\n            return targeting.FindForwardDiscovery();" in route_pack
    assert "if (discoveryLeg)\n            return false;" in read(BOT_MGR_CORE)
    threat_target_block = route_pack.split("auto findTrashClusterThreatTarget", 1)[1].split("result.IsNaturalMember", 1)[0]
    assert_ordered(
        threat_target_block,
        "Creature* creature = object ? object->ToCreature() : nullptr;",
        "if (!targeting.IsEligibleTrash(creature))",
        "Unit* victim = creature->GetVictim();",
    )
    assert "Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())" not in threat_target_block
    assert_ordered(
        targeting + route_pack + route_core,
        "auto forEachActiveValidationCohortCombatCreature",
        "auto isValidationCohortCombatLinked",
        "auto isNaturalValidationRoutePackMember",
        "auto enrollValidationRoutePackMember",
        "!engaged",
        "Party().ValidationRoutePackMemberGuids.insert(creature->GetGUID()).second;",
        "Party().ValidationRoutePackEngagedGuids.insert(creature->GetGUID()).second;",
        'RecordEvent(state, bot, "validation_route_pack_enrolled"',
        "auto enrollEngagedValidationRoutePackMembers",
        "enrollValidationRoutePackMember(creature, true);",
        "auto persistedValidationRoutePackHasLiveMembers",
        "Party().ValidationRoutePackDeathGuids.find(guid) == Party().ValidationRoutePackDeathGuids.end()",
        "auto trashClusterHasLiveMobs",
        "enrollEngagedValidationRoutePackMembers();",
        "persistedValidationRoutePackHasLiveMembers()",
    )
    defeated_pack_block = function_body(
        read(VALIDATION_OUTCOMES),
        "bool BotWorldPopulationMgr::RecordDefeatedValidationRoutePackMembers",
    )
    assert "Party().ValidationRoutePackEngagedGuids.find(guid) == Party().ValidationRoutePackEngagedGuids.end()" in defeated_pack_block
    assert "Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end()" in defeated_pack_block
    assert "Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end()" in defeated_pack_block
    assert "std::vector<ObjectGuid> memberGuids(Party().ValidationRoutePackMemberGuids.begin(), Party().ValidationRoutePackMemberGuids.end());" in defeated_pack_block
    assert "for (ObjectGuid const& guid : memberGuids)" in defeated_pack_block
    assert "bot->GetMap()->GetCreature(guid); creature && !creature->IsAlive() && !creature->GetHealth()" in defeated_pack_block
    assert 'recordValidationRouteTrashKill(creature, "enrolled_member_seen_dead")' in defeated_pack_block
    assert "if (!creature)" not in defeated_pack_block
    usable_target_block = route_objective.split("auto routeUsableCombatTarget", 1)[1].split("auto maybeValidationPrerequisiteNoProgressAssist", 1)[0]
    assert "Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID())" in usable_target_block
    assert_ordered(
        route_objective,
        'targetSearchResult = "target_seen_dead";',
        "if (!isValidationRouteCombatTarget(creature))",
        'targetSearchResult = "target_seen_activation_target";',
    )
    transition_block = route_pack.split("auto recordValidationRouteScriptedTransition", 1)[1].split("auto retireStaleValidationRoutePackMembers", 1)[0]
    live_pack = read(VALIDATION_LIVE_PACK)
    for required in [
        "Party().ValidationRoutePackEngagedGuids.find(creature->GetGUID())",
        "uint32 auraId = targeting.ResolvedTransitionAura(creature);",
        "Party().ValidationRoutePackTransitionGuids.insert(creature->GetGUID())",
        "Party().ValidationRouteManifestIndex + 1",
        "ScriptedEventEntries.begin()",
        "if (!declaredByFutureNode)",
        "if (discoveryLeg)",
        "Party().ValidationRoutePendingFinalTransitionGuids.insert(transitionedGuid)",
        "else",
        "Party().ValidationRouteFinalTransitionGuids.insert(transitionedGuid)",
        "Party().ValidationRouteFocusGuid == transitionedGuid",
        "cohortState.TargetGuid == transitionedGuid",
        "cohortState.LastDecisionTargetGuid == transitionedGuid",
        "member->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE)",
        "cohortState.LastCombatAttempt.TargetGuid == transitionedGuid",
        "cohortState.LastRouteProgress.TargetGuid == transitionedGuid",
        "cohortState.ActivePathValid = false",
        '"validation_route_scripted_transition"',
    ]:
        assert required in transition_block
    assert "resolvedScriptedTransitionAuraId(creature)" in live_pack
    resolved_transition_block = targeting.split("auto resolvedScriptedTransitionAuraId", 1)[1].split("auto isEligibleTrashClusterMob", 1)[0]
    for required in [
        "Cohort().Config.ValidationRouteScriptedEventEntries.end()",
        "Cohort().Config.ValidationRouteScriptedEventTransitionAuraIds[index]",
        "creature->HasAura(auraId)",
        "creature->GetVictim()",
        "creature->HasReactState(REACT_PASSIVE)",
    ]:
        assert required in resolved_transition_block
    for generic_state in ["IsValidAttackTarget", "IsInEvadeMode", "UNIT_STATE_EVADE", "hasStrictPathToValidationRouteTarget", "IsWithinLOSInMap"]:
        assert generic_state not in transition_block
    natural_pack_member_block = route_pack.split("auto isNaturalValidationRoutePackMember", 1)[1].split(
        "auto enrollValidationRoutePackMember", 1
    )[0]
    # Current-node scripted actors (for example Stonecore Millhouse) are
    # intentionally enrolled so native damage can trigger their transition;
    # only future scripted actors are excluded from discovery/forward pulls.
    assert "targeting.IsFutureCanonicalSource(creature)" in natural_pack_member_block
    assert "nativeCombatObserved" in natural_pack_member_block
    assert "&& !nativeCombatObserved" in natural_pack_member_block
    assert "Party().ValidationRoutePendingFinalTransitionGuids.find(creature->GetGUID())" in natural_pack_member_block
    assert "Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID())" in natural_pack_member_block
    assert "Party().ValidationRoutePackTransitionGuids.find(guid) == Party().ValidationRoutePackTransitionGuids.end()" in route_objective
    assert_ordered(
        mgr,
        "void BotWorldPopulationMgr::LoadValidationRouteManifest()",
        "Party().ValidationRoutePendingFinalTransitionGuids.clear();",
        "Party().ValidationRouteFinalTransitionGuids.clear();",
    )
    apply_node = function_body(mgr, "bool BotWorldPopulationMgr::ApplyValidationRouteManifestNode")
    load_manifest = function_body(mgr, "void BotWorldPopulationMgr::LoadValidationRouteManifest")
    for required in [
        "node.NavigationAnchorX = node.X",
        "node.NavigationAnchorY = node.Y",
        "node.NavigationAnchorZ = node.Z",
        "node.NavigationAnchorO = node.O",
        'ExtractJsonNumberField(routeJson, "navigation_anchor_x", node.NavigationAnchorX)',
        'ExtractJsonNumberField(routeJson, "navigation_anchor_y", node.NavigationAnchorY)',
        'ExtractJsonNumberField(routeJson, "navigation_anchor_z", node.NavigationAnchorZ)',
        'ExtractJsonNumberField(routeJson, "navigation_anchor_o", node.NavigationAnchorO)',
    ]:
        assert required in load_manifest
    assert "Cohort().Config.ValidationRouteX = node.NavigationAnchorX;" in apply_node
    assert "Cohort().Config.ValidationRouteY = node.NavigationAnchorY;" in apply_node
    assert "Cohort().Config.ValidationRouteZ = node.NavigationAnchorZ;" in apply_node
    assert "Cohort().Config.ValidationRouteO = node.NavigationAnchorO;" in apply_node
    assert "Cohort().Config.ValidationRouteTargetEntry = node.NodeKind == \"discovery_leg\" ? 0 : node.TargetEntry;" in apply_node
    reset_route = function_body(mgr, "void BotWorldPopulationMgr::ResetValidationRouteRuntimeState")
    assert "state.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();" in reset_route
    assert "state.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();" in reset_route
    assert "Party().ValidationRoutePendingFinalTransitionGuids.clear();" in apply_node
    assert "Party().ValidationRouteFinalTransitionGuids.clear();" in mgr
    enrollment_scan = route_pack.split("auto enrollEngagedValidationRoutePackMembers", 1)[1].split("auto persistedValidationRoutePackHasLiveMembers", 1)[0]
    active_combat_scan = (targeting + route_pack).split("auto forEachActiveValidationCohortCombatCreature", 1)[1].split(
        "auto enrollValidationRoutePackMember", 1
    )[0]
    assert "GetCombatManager().GetPvECombatRefs()" in active_combat_scan
    assert "combatReference->IsSuppressedFor(member)" in active_combat_scan
    assert "combatReference->IsSuppressedFor(other)" in active_combat_scan
    assert "combatReference && !combatReference->IsSuppressedFor(member) && !combatReference->IsSuppressedFor(creature)" in active_combat_scan
    assert "member->GetMap() != bot->GetMap()" in active_combat_scan
    assert "creature->GetMap() != bot->GetMap()" in active_combat_scan
    assert "std::unordered_set<ObjectGuid> visited" in active_combat_scan
    assert "GetThreatManager().IsThreatenedBy" not in route_objective
    assert "combatReferences.find(creature->GetGUID())" in active_combat_scan
    assert "Party().ValidationRoutePendingFinalTransitionGuids.find(creature->GetGUID())" in active_combat_scan
    assert "Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID())" in active_combat_scan
    # Passive current-node scripted actors may only expose native damage
    # without a CombatManager reference; the discovery-only scan enrolls them
    # after observed combat/victim state or real health loss.
    assert "if (discoveryLeg && bot->GetMap())" in enrollment_scan
    assert "AllWorldObjectsInRange" in enrollment_scan
    assert "nearbyCheck(bot, 80.0f)" in enrollment_scan
    assert "nearbyObjects" in enrollment_scan
    assert "isCurrentNativeNaturalPackMember" in enrollment_scan
    assert "targeting.IsPendingScripted(creature)" in enrollment_scan
    assert "Cell::VisitAllObjects" in enrollment_scan
    assert "nativeCombatObserved" in enrollment_scan
    assert "targeting.ForEachActiveCombat" in enrollment_scan
    assert "isNaturalValidationRoutePackMember(creature)" in enrollment_scan
    assert "!discoveryLeg && !isLiveTrashClusterMob(creature)" not in enrollment_scan
    assert "enrollValidationRoutePackMember(creature, true);" in enrollment_scan
    assert '!engaged || !isNaturalValidationRoutePackMember(creature)' in route_objective
    assert "std::vector<ObjectGuid> memberGuids" in enrollment_scan
    assert "recordValidationRouteScriptedTransition(creature);" in enrollment_scan
    assert 'RecordEvent(state, bot, "validation_route_pack_enrolled", creature, "cohort_combat_reference"' in route_objective
    assert '"route_selection"' not in route_objective
    eligible_block = targeting.split("auto isEligibleTrashClusterMob", 1)[1].split("auto isLiveTrashClusterMob", 1)[0]
    assert "Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID())" in eligible_block
    assert "Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID())" in eligible_block
    assert "focusedDiscoveryCandidate" in eligible_block
    assert "Party().ValidationRouteFocusGuid == creature->GetGUID()" in eligible_block
    assert "AttackStop" not in transition_block
    assert "CombatStop" not in transition_block
    ineligible_target_block = route_objective.split("else if (ineligibleTrashTarget)", 1)[1].split(
        "if (bot->IsInCombat() && target", 1
    )[0]
    assert '"ineligible_trash_target"' in ineligible_target_block
    assert "SubmitMeleeAutoAttackIntent(state," in ineligible_target_block
    assert "BotMeleeAutoAttack::Kind::Suppress" in ineligible_target_block
    assert '"ineligible_trash_target");' in ineligible_target_block
    assert "state.TargetGuid.Clear();" in ineligible_target_block
    assert "target = nullptr;" in ineligible_target_block
    profile_action = function_body(mgr, "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction")
    for required in [
        "auto effectiveSpellMinRange",
        "bot->GetSpellMinRangeForTarget(target, spellInfo)",
        "spellInfo->RangeEntry->Flags & SPELL_RANGE_RANGED",
        "spellMinRange += bot->GetMeleeRange(target)",
        "action.MinRange = std::max(action.MinRange, minRange)",
        "action.MinRange = effectiveSpellMinRange(*best, action.MinRange)",
        'bool selfTarget = best->Profile.TargetSelector == "self";',
        "action.MinRange = selfTarget ? 0.0f",
        "ResolveSelfCenteredHostileMaxRange",
        "action.MaxRange = selfTarget",
        "? selfCenteredHostileMaxRange",
    ]:
        assert required in profile_action
    assert_ordered(
        route_objective,
        "Party().ValidationRoutePackMemberGuids.insert(killedTarget->GetGUID());",
        "Party().ValidationRoutePackDeathGuids.insert(killedTarget->GetGUID());",
        'RecordEvent(state, bot, "mob_killed"',
    )
    assert "!Party().ValidationRoutePackObservedEngagement" in route_objective
    assert "member->GetVictim() || !member->getAttackers().empty()" in route_objective
    assert "cohortObservation.PartyHasActiveCombat = partyHasActiveCombatUnit" in route_objective
    assert "&& cohortReadiness.TrashTerminalReady" in route_objective
    assert "nowMs - Party().ValidationRoutePackClearCandidateSinceMs < 2000" in route_objective
    assert "Party().ValidationRoutePackEngagedGuids.find(killedTarget->GetGUID())" in route_objective
    assert "bestAnchorTargetScore" not in route_objective
    assert '"dynamic_pack_members_live_or_unobserved"' in route_objective
    config_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildConfigJson")
    diagnosis_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")
    for field in [
        "pack_generation",
        "pack_sequence",
        "completed_pack_count",
        "pack_member_count",
        "pack_engaged_count",
        "pack_death_count",
        "pack_transition_count",
        "pack_observed_engagement",
    ]:
        assert f'\\"{field}\\"' in config_json
        assert f'\\"validation_route_{field}\\"' in diagnosis_json
    assert_ordered(
        route_objective,
        'recordValidationRouteTrashKill(seenRouteTarget, "target_seen_dead");',
        "clearValidationRouteKilledFocus(seenRouteTarget->GetGUID());",
        "seenRouteTarget = nullptr;",
        "if (!routeTarget && seenRouteTarget && seenRouteTargetDistance > 8.0f)",
    )
    assert_ordered(
        route_objective,
        "routeDistance <= routeArrivalRadius || Manager.HasCompletedValidationRouteDrudgeEntrancePull(bot)",
        "++state.ValidationRouteTargetSearchMissCount >= 2",
        "ValidationCohortReadinessObservation cohortObservation;",
        "ClassifyValidationCohortReadiness(cohortObservation);",
        "uint64& clearCandidateSinceMs = discoveryLeg ? Party().ValidationRouteNodeClearCandidateSinceMs : Party().ValidationRoutePackClearCandidateSinceMs;",
        "if (Cohort().Config.ValidationRouteAdvanceMode == \"terminal\"",
        "(discoveryLeg ? (Party().ValidationRouteCompletedPackCount > 0 || Party().ValidationRouteObservedDeadScriptTarget)",
        ": (Party().ValidationRoutePackObservedEngagement || Party().ValidationRouteObservedDeadScriptTarget))",
        "&& cohortReadiness.TrashTerminalReady",
        "&& nowMs - clearCandidateSinceMs >= 2000)",
        'markTrashClusterCleared("trash_cluster_cleared");',
    )
    complete_discovered_pack = function_body(
        read(VALIDATION_OUTCOMES),
        "bool BotWorldPopulationMgr::CompleteDiscoveredPackIfReady",
    )
    assert_ordered(
        complete_discovered_pack,
        "ledgerComplete = false;",
        "validationPartyHasActiveCombat()",
        'RecordEvent(state, bot, "validation_route_pack_terminal"',
        "++Party().ValidationRouteCompletedPackCount;",
        "++Party().ValidationRoutePackSequence;",
        "Party().ValidationRoutePackMemberGuids.clear();",
    )
    assert "if (completeDiscoveredPackIfReady())" in route_core
    discovered_pack_terminal = complete_discovered_pack
    assert "Party().ValidationRoutePendingFinalTransitionGuids.clear()" not in discovered_pack_terminal
    assert_ordered(
        route_objective,
        "if (discoveryLeg)",
        "Party().ValidationRouteFinalTransitionGuids.insert(Party().ValidationRoutePendingFinalTransitionGuids.begin(), Party().ValidationRoutePendingFinalTransitionGuids.end());",
        "Party().ValidationRoutePendingFinalTransitionGuids.clear();",
        'markTrashClusterCleared("trash_cluster_cleared");',
        "MaybeAdvanceValidationRouteManifest();",
    )
    assert 'uint32 routeTargetNoProgressThreshold = Cohort().Config.ValidationRouteKind == "boss" ? 5 : 20;' in route_objective
    assert "bool ValidationRouteManifestComplete = false;" in mgr_header
    assert_ordered(
        advance_manifest,
        "if (Party().ValidationRouteManifestComplete)",
        "Party().ValidationRouteManifestAdvancePending = false;",
        "return true;",
        'bool arrivalRoute = Cohort().Config.ValidationRouteKind == "travel" || Cohort().Config.ValidationRouteKind == "regroup" || Cohort().Config.ValidationRouteKind == "descent";',
        'bool confirmedBossDeath = Cohort().Config.ValidationRouteKind != "boss"',
        "bool terminal = !arrivalRoute",
        "&& confirmedBossDeath",
        "&& Party().ValidationRouteManifestAdvanceGeneration == Party().ValidationRouteGeneration;",
    )
    assert "uint32 loadedParticipants = 0;" in advance_manifest
    assert "if (!loadedBot)\n                continue;" in advance_manifest
    assert "++loadedParticipants;" in advance_manifest
    assert "!IsValidationCohortMemberInOriginalInstance(state, loadedBot)" in advance_manifest
    assert "Cohort().Config.TargetPopulation && loadedParticipants < Cohort().Config.TargetPopulation" in advance_manifest
    assert "if (loadedParticipants && allLoadedArrived)" in advance_manifest
    assert "ValidationCohortReadinessObservation" in advance_manifest
    assert "ClassifyValidationCohortReadiness(cohortObservation)" in advance_manifest
    assert "terminalCohortRadius" in advance_manifest
    assert "<= terminalCohortRadius" in advance_manifest
    assert "if (!cohortReadiness.FullRosterAtEndpoint)\n            return false;" in advance_manifest
    assert 'terminalReason = typedNativeDescent' in advance_manifest
    assert '? "native_descent_landed_path_proven" : "arrival";' in advance_manifest
    assert "bool successfulTerminal = state.ValidationRouteGeneration == Party().ValidationRouteGeneration" in advance_manifest
    assert "&& state.ValidationRouteTerminalGeneration == Party().ValidationRouteGeneration" in advance_manifest
    assert 'state.ValidationRouteTerminalReason == "all_routes_complete"' in advance_manifest
    assert 'Cohort().Config.ValidationRouteKind == "boss"' in advance_manifest
    assert 'state.ValidationRouteTerminalReason == "boss_killed"' in advance_manifest
    assert 'Cohort().Config.ValidationRouteKind != "boss"' in advance_manifest
    assert "state.LastDecisionAction" not in advance_manifest
    assert 'state.ValidationRouteTerminalReason == "trash_cluster_cleared"' in advance_manifest
    assert 'state.ValidationRouteTerminalReason == "trash_cluster_expected_empty"' not in advance_manifest
    assert "ValidationRouteTerminalState" not in record_decision
    assert_ordered(
        advance_manifest,
        "if (nextIndex >= Party().ValidationRouteManifest.size())",
        "Party().ValidationRouteManifestComplete = true;",
        'RecordEvent(*reporterState, reporter, "validation_route_manifest_complete"',
        "state.ValidationRouteTerminalState = true;",
        "return true;",
    )
    terminal_arrival = read(TERMINAL_ARRIVAL)
    assert_ordered(
        terminal_arrival,
        "if (State.ValidationRouteTerminalState",
        "&& State.ValidationRouteTerminalGeneration == Manager.Party().ValidationRouteGeneration)",
        "Callbacks.MoveToRouteAnchor()",
        "terminal_cohort_catchup",
        'Action = "move_to_validation_route_anchor";',
    )
    assert_ordered(
        route_objective,
        "if (Party().ValidationRouteManifestComplete)",
        'action = "validation_route_complete";',
        "return true;",
    )
    assert "Party().ValidationRouteManifestComplete" not in record_decision


def test_trash_terminal_uses_current_generation_truth_after_metric_restart():
    target_engagement = read(TARGET_ENGAGEMENT)
    route_objective = read(BOT_MGR_CORE) + target_engagement
    terminal_block = target_engagement.split(
        'if (!routeTarget && Cohort().Config.ValidationRouteKind != "boss" && std::string(GetDungeonRole(bot)) == "tank" && (routeDistance <= routeArrivalRadius', 1
    )[1].split('if (!routeTarget && Cohort().Config.ValidationRouteKind == "boss")', 1)[0]
    direct_scan = target_engagement.split("if (Cohort().Config.ValidationRouteTargetEntry && !routeTarget)", 1)[1].split(
        'if (!routeTarget\n        && seenRouteTarget', 1
    )[0]
    live_scan = read(BOT_MGR_CORE).split("auto trashClusterHasLiveMobs", 1)[1].split("auto markTrashClusterCleared", 1)[0]

    assert "ValidationRouteHasProgressSinceApply()" not in terminal_block
    assert "Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration" in terminal_block
    assert "Party().ValidationRoutePackObservedEngagement" in terminal_block
    assert "++state.ValidationRouteTargetSearchMissCount >= 2" in terminal_block
    assert "cohortObservation.PackHasLiveMobs = packHasLiveMobs" in terminal_block
    assert "cohortObservation.PartyHasActiveCombat = partyHasActiveCombatUnit" in terminal_block
    assert "cohortReadiness.TrashTerminalReady" in terminal_block
    assert "fullCohortAtEndpoint" in terminal_block
    assert "nowMs - clearCandidateSinceMs >= 2000" in terminal_block

    assert_ordered(
        direct_scan,
        "bool recordedCurrentDead = Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration",
        "Party().ValidationRoutePackDeathGuids.find(creature->GetGUID())",
        "Party().ValidationRouteRecordedKillGuids.find(creature->GetGUID())",
        "if (recordedCurrentDead)",
        "continue;",
        "float distance = bot->GetExactDist(creature);",
    )
    assert "recordValidationRouteTrashKill(seenRouteTarget, \"target_seen_dead\")" in read(TARGET_ENGAGEMENT)
    readiness_call = route_objective.index("TryValidationRouteReadiness(state, bot, target, power, stage, activity, readinessResult)")
    early_terminal_regroup = route_objective.index('moved ? "move_to_terminal_route_endpoint" : "terminal_route_endpoint_path_rejected"')
    assert early_terminal_regroup < readiness_call
    early_regroup_block = route_objective[route_objective.rfind('if (Cohort().Config.ValidationRouteKind != "boss"', 0, early_terminal_regroup):readiness_call]
    assert 'std::string(GetDungeonRole(bot)) != "tank"' in early_regroup_block
    assert "routeDistance > routeArrivalRadius" in early_regroup_block
    assert "!routeFocusMemoryFresh()" in early_regroup_block
    assert "routeTankFocusGuid().IsEmpty()" in early_regroup_block
    assert "!trashClusterHasLiveMobs()" in early_regroup_block
    assert "!validationPartyHasActiveCombat()" in early_regroup_block
    assert_ordered(
        early_regroup_block,
        "if (TryValidationRouteMovementCheck(state, bot, power, stage, activity,",
        "return true;",
        "MoveBotToPoint(state, bot,",
        "Cohort().Config.ValidationRouteX,",
        "BotMovementArbitration::Owner::Route,",
    )

    for forbidden_filter in [
        "if (!bot->IsValidAttackTarget(creature))",
        "if (creature->IsInEvadeMode()",
        "if (!hasStrictPathToValidationRouteTarget(creature))",
    ]:
        assert forbidden_filter not in live_scan
    for blocker_field in ["guid", "entry", "distance", "alive", "attackable", "evade", "path", "member"]:
        assert f'\\\"{blocker_field}\\\"' in terminal_block
    for hold_field in [
        "pack_has_live_mobs",
        "party_has_active_combat",
        "full_cohort_at_endpoint",
        "all_expected_members_accounted",
        "all_living_at_endpoint",
        "full_roster_at_endpoint",
        "trash_terminal_ready",
        "quiet_elapsed_ms",
        "quiet_remaining_ms",
    ]:
        assert f'\\\"{hold_field}\\\"' in terminal_block
    assert '\\"cohort_readiness\\":{\\"expected_members\\":' in terminal_block
    for hold_reason in [
        "dynamic_pack_members_live_or_unobserved",
        "trash_cluster_party_combat_active",
        "trash_cluster_cohort_not_accounted",
        "trash_cluster_living_cohort_not_at_endpoint",
        "trash_cluster_terminal_mode_required",
        "trash_cluster_clear_stability_pending",
    ]:
        assert f'"{hold_reason}"' in terminal_block
    assert_ordered(
        terminal_block,
        "if (packHasLiveMobs)",
        'raw << "{\\\"guid\\\":"',
        "else",
        'raw << "null";',
    )

    route_runtime = read(BOT_DIR / "BotWorldPopulationMgrValidationRouteRuntime.cpp")
    manifest_advance = function_body(
        route_runtime, "bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest"
    )
    assert "ClassifyValidationCohortReadiness(cohortObservation)" in manifest_advance
    assert "if (!cohortReadiness.FullRosterAtEndpoint)" in manifest_advance


def test_clip_capture_smoke_persists_clip_row_with_pre_and_post_frames():
    buffer = read(BOT_BUFFER)
    capture = function_body(buffer, "uint64 BotTelemetryBuffer::CaptureEvent")
    append_post = function_body(buffer, "void BotTelemetryBuffer::AppendPostFrame")

    assert "uint64 preWindowMs = uint64(_config.PreEventWindowSec) * 1000;" in capture
    assert "frame.timestamp_ms + preWindowMs >= nowMs" in capture
    assert "clip.pre_frames.push_back(frame);" in capture
    assert "clip.post_frames.push_back(trigger);" in capture
    assert "if (clip.pre_frames.empty())" in capture
    assert "clip.pre_frames.push_back(trigger);" in capture
    assert_ordered(
        capture,
        "clip.clip_id = InsertClipRow",
        "InsertFrameRows(clip.clip_id, clip.trigger_time_ms, clip.pre_frames, 0)",
        "InsertFrameRows(clip.clip_id, clip.trigger_time_ms, clip.post_frames, 0)",
        "buffer.OpenClips.push_back(clip)",
    )

    assert "frame.timestamp_ms <= clip.end_time_ms" in append_post
    assert "clip.post_frames.push_back(frame);" in append_post


def test_segment_trigger_smoke_opens_quest_execution_and_closes_success():
    segments = read(BOT_SEGMENTS)
    ctor = function_body(segments, "BotExperimentCoordinator::BotExperimentCoordinator")
    handle = function_body(segments, "void BotExperimentCoordinator::HandleTelemetryEvent")
    start = function_body(segments, "void BotExperimentCoordinator::StartSegment")
    finish = function_body(segments, "void BotExperimentCoordinator::FinishSegment")

    assert '{ "quest_execution_v1", { { "quest_accepted" } }, { "quest_completed" }, { "objective_failed", "timeout" } }' in ctor
    assert_ordered(handle, "Contains(definition->SuccessEvents, event)", "FinishSegment(itr->second, BotExperimentSegmentStatus::Success")
    assert_ordered(handle, "Contains(definition->FailureEvents, event)", "FinishSegment(itr->second, event == \"timeout\"")
    assert_ordered(handle, "for (BotExperimentDefinition const& definition", "if (trigger.EventType == event)", "StartSegment(bot, definition")

    assert "INSERT INTO experiment_bot_segments" in start
    assert "'running'" in start
    assert "UPDATE experiment_bot_segments SET status = '%s'" in finish
    assert "BotExperimentSegmentStatus::Success" in finish
    assert "++_counts.Success;" in finish


def test_recovery_smoke_records_death_recovery_without_center_fallback_unless_enabled():
    mgr = read(BOT_MGR)
    conf = read(WORLDSERVER_CONF)
    recover = function_body(mgr, "BotWorldPopulationMgr::DeathRecoveryResult BotWorldPopulationMgr::RecoverDeadBot")
    native = function_body(mgr, "bool BotWorldPopulationMgr::TryNativeCorpseRun")
    native_executor = function_body(mgr, "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent")
    update_bot = read(UPDATE_BOT_DEATH)
    build_policy = function_body(mgr, "BotWorldPopulationMgr::BotDeathRecoveryPolicy BotWorldPopulationMgr::BuildDeathRecoveryPolicy")

    assert re.search(r"^BotWorld\.TeleportToCenterOnDeath\s*=\s*0$", conf, re.MULTILINE)
    assert 'policy.Modes = { "native_corpse_run" };' in build_policy
    assert "policy.MaxDeathsBeforeFallback = Cohort().Config.MaxDeathsBeforeFallback;" in build_policy
    assert "recovery.RepeatedDeath = state.RecentDeathCount >= policy.MaxDeathsBeforeFallback;" in recover
    assert 'mode == "native_corpse_run"' in recover
    assert "TryNativeCorpseRun(state, bot, result)" in recover
    assert "BotNativeAction::ReleaseSpirit" in native
    assert "BotNativeAction::AreaTrigger" in native
    assert "BotNativeAction::ReclaimCorpse" in native
    assert "HandleRepopRequestOpcode(repop)" in native_executor
    assert "HandleAreaTriggerOpcode(areaTrigger)" in native_executor
    assert "HandleReclaimCorpseOpcode(reclaim)" in native_executor
    assert "ResurrectPlayer" not in native
    assert "TeleportTo(" not in native
    assert 'RecordEvent(state, bot, "death_recovery_started"' in update_bot
    assert 'RecordEvent(state, bot, "resurrected"' in update_bot
    assert 'RecordEvent(state, bot, "death_recovery_progress"' in update_bot
    assert 'RecordEvent(state, bot, "death_recovery_failed"' in update_bot
    mark_death = function_body(mgr, "void BotWorldPopulationMgr::MarkDeathDangerZone")
    assert 'sourceEntry, state.RecentDeathCount, 0u, metadataJson.c_str()' in mark_death
    assert "bool DeathEpisodeRecorded = false;" in read(BOT_MGR_HEADER)
    assert "if (!state.DeathEpisodeRecorded)" in update_bot
    assert "state.DeathEpisodeRecorded = true;" in update_bot
    assert "state.DeathEpisodeRecorded = false;" in update_bot
    recovery_success = update_bot.split("if (recovery.Recovered)", 1)[1].split("else", 1)[0]
    assert "state.DeathEpisodeRecorded = false;" in recovery_success
    assert "if (state.DeadTimer == diff)" not in update_bot


def test_validation_route_combat_resurrection_uses_typed_scheduler():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    native_intents = read(ROOT / "src/server/game/Bots/BotNativeActionIntent.h")
    builder = function_body(
        read(COMBAT_RES), "BotWorldPopulationMgr::BuildCombatResNativeActionCandidate"
    )
    executor = function_body(
        read(NATIVE_ACTION), "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent"
    )
    update_bot = read(BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp") + read(UPDATE_BOT_DEATH)

    assert "BuildCombatResNativeActionCandidate" in header
    for intent in ("CombatResApproach", "CombatResCast", "CombatResAccept"):
        assert f"struct {intent}" in native_intents
        assert f"BotNativeAction::{intent}" in executor
    approach_resources = native_intents.split(
        "if constexpr (std::is_same_v<T, CombatResApproach>)", 1
    )[1].split("if constexpr", 1)[0]
    assert "return Uses(Resource::Movement);" in approach_resources
    for forbidden_resource in (
        "Resource::GlobalCooldown",
        "Resource::Cast",
        "Resource::Target",
    ):
        assert forbidden_resource not in approach_resources
    assert native_intents.count("Resource::Movement, Resource::GlobalCooldown") >= 1
    assert "Resource::Interaction, Resource::Target" in native_intents

    assert "CurrentCombatResOwnerUsable" in builder
    assert 'candidate.Id.Strategy = "typed_combat_res"' in builder
    assert 'candidate.ActionPriority = BotActionArbitration::Priority::Mechanic' in builder
    assert "candidate.ExpiresAtMs = targetState->NativeBattleResDecisionUntilMs" in builder
    assert "BuildCombatResNativeActionCandidate(context.State, context.Bot," in update_bot
    assert "candidate.RequiredResources = combatRes->Resources();" in update_bot
    assert "context.State.DecisionKernel.Submit(std::move(candidate))" in update_bot

    for native_boundary in (
        "MoveBotToPoint(state, bot",
        "bot->CastSpell(target",
        "HandleResurrectResponseOpcode(response)",
        "HandleMoveTeleportAck(ack)",
    ):
        assert native_boundary in executor
    assert "NativeResurrectionPendingUntilMs" in executor
    assert '"reserved_cast_submitted"' in executor
    assert '"typed_approach_intent_submitted"' in executor
    assert '"typed_combat_res_waiting_for_active_cast"' in executor
    assert '"typed_combat_res_cast_resources_pending"' in executor
    assert '"typed_native_cast_submitted"' in executor
    assert '"typed_native_resurrection_completed"' in executor
    assert "CurrentCombatResOwnerUsable" in executor

    assert "TryNativePartyResurrection" not in mgr
    for forbidden in ("ResurrectPlayer", "NearTeleportTo", "TeleportTo("):
        assert forbidden not in builder


def test_certified_recovery_waits_for_group_combat_and_rebuffs_after_stability():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    update_bot = read(UPDATE_BOT_DEATH)
    readiness = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteReadiness")

    assert "uint64 GroupReadinessStableSinceMs = 0;" in header
    assert 'state.NativeBattleResDecision == "reserved_cast_submitted"' in update_bot
    assert 'state.NativeBattleResDecision == "reserved_approach"' in update_bot
    assert "acceptedCombatResIntentCurrent" in update_bot
    assert "NativeBattleResApproachIntentAcceptedUntilMs" in update_bot
    assert '"declined_typed_intent_not_current"' in update_bot
    assert "nativeDeathDecisionWindowComplete = state.DeadTimer >= 1500" in update_bot
    assert_ordered(update_bot, "if (battleResReserved)", "RecoverDeadBot(state, bot)")
    assert "certifiedGroupCombatActive" not in update_bot
    assert "member->IsInCombat()" in readiness
    assert "member->GetVictim()" in readiness
    assert "!member->getAttackers().empty()" in readiness
    assert "state.GroupReadinessStableSinceMs = 0;" in readiness
    assert "nowMs - state.GroupReadinessStableSinceMs < 10000" in readiness


def test_telemetry_frame_action_is_bounded_to_schema_width():
    mgr = read(BOT_MGR)
    frame_builder = function_body(mgr, "BotTelemetryFrame BotWorldPopulationMgr::BuildTelemetryFrame")

    assert "frame.action = BoundedResultLabel(action);" in frame_builder
    assert "frame.action = action ? action : \"\";" not in frame_builder


def test_export_smoke_lists_old_and_new_bot_experiment_tables():
    commands = read(BOT_COMMANDS)
    export_body = function_body(commands, "static bool HandleExportCommand")
    match = re.search(r'PSendSysMessage\("(?P<payload>\{.*?\})"\);', export_body, re.DOTALL)
    assert match
    payload = json.loads(match.group("payload").replace('\\"', '"'))

    assert payload["ok"] is True
    assert payload["action"] == "botexp_export"
    assert payload["storage"] == "character_database_tables"
    assert payload["embedding_feature_schema"] == "bot_semantic_phase6_v1"
    assert payload["policy_feature_schema"] == "bot_policy_features_v1"
    assert payload["failure_reason"] is None
    assert payload["tables"] == [
        "experiment_bot_runs",
        "experiment_bot_segments",
        "experiment_bot_events",
        "experiment_bot_decisions",
        "experiment_bot_activities",
        "experiment_bot_replay_records",
        "experiment_bot_clips",
        "experiment_bot_clip_frames",
        "bot_semantic_outcome_stats",
        "bot_memory_pois",
        "bot_memory_danger_zones",
        "bot_memory_failed_paths",
        "bot_memory_safe_positions",
        "bot_memory_objective_clusters",
        "bot_memory_recipe_sources",
        "bot_memory_material_sources",
        "bot_memory_daily_cooldowns",
        "bot_memory_transport_usage",
        "bot_memory_decision_fingerprints",
        "bot_policy_models",
        "bot_policy_evaluations",
    ]


def test_extended_bot_memory_schema_and_decision_fingerprint_surface():
    schema = read(ROOT / "sql/updates/characters/4.3.4/2026_06_16_00_characters_bot_extended_memory.sql")
    mgr_header = read(BOT_MGR_HEADER)
    mgr = read(BOT_MGR)
    record_decision = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")
    fingerprint = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionFingerprintMemory")
    fingerprint_persist = function_body(mgr, "void BotWorldPopulationMgr::PersistDecisionFingerprintDelta")
    record_quest = function_body(mgr, "void BotWorldPopulationMgr::RecordQuestEvent")
    objective_cluster = function_body(mgr, "void BotWorldPopulationMgr::RecordObjectiveClusterMemory")
    remember_poi = function_body(mgr, "void BotWorldPopulationMgr::RememberPoi")
    visible_source = function_body(mgr, "void BotWorldPopulationMgr::RememberVisibleSourceMemory")
    diagnosis_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")

    for table in [
        "bot_memory_objective_clusters",
        "bot_memory_recipe_sources",
        "bot_memory_material_sources",
        "bot_memory_daily_cooldowns",
        "bot_memory_transport_usage",
        "bot_memory_decision_fingerprints",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in schema

    for column in [
        "`cluster_id` int unsigned NOT NULL",
        "`recipe_spell_id` int unsigned NOT NULL",
        "`item_id` int unsigned NOT NULL",
        "`available_at` datetime NOT NULL",
        "`transport_type` varchar(64) NOT NULL",
        "`fingerprint_hash` int unsigned NOT NULL",
        "UNIQUE KEY `uniq_bot_fingerprint` (`bot_guid`, `fingerprint_hash`)",
    ]:
        assert column in schema

    assert "RecordDecisionFingerprintMemory" in mgr_header
    assert "RecordDecisionFingerprintMemory(state, bot, situation, action, chosenActivity, failure);" in record_decision
    assert "INSERT INTO bot_memory_decision_fingerprints" in fingerprint_persist
    assert "ON DUPLICATE KEY UPDATE repeat_count = repeat_count + VALUES(repeat_count)" in fingerprint_persist
    assert "FeatureSchemaHash(fingerprint.str())" in fingerprint
    assert "LastDecisionFingerprintRepeatCount" in mgr_header
    assert "LastDecisionFingerprintFailure = false" in mgr
    assert "state.LastDecisionFingerprintPersistedRepeatCount = 0" in mgr
    assert "FlushPendingDecisionFingerprintMemory();" in mgr
    assert "SELECT repeat_count, failure_count FROM bot_memory_decision_fingerprints" in fingerprint
    assert "fingerprint_source" in fingerprint_persist
    assert "RecordObjectiveClusterMemory(state, bot, eventType, questId, result, valueInt, contextJson);" in record_quest
    assert "INSERT INTO bot_memory_objective_clusters" in objective_cluster
    assert "DATE_ADD(NOW(), INTERVAL 2 MINUTE)" in objective_cluster
    assert "RememberVisibleSourceMemory(state, bot, object, poiType, entry, questId, metadataJson.c_str());" in remember_poi
    assert "INSERT INTO bot_memory_recipe_sources" in visible_source
    assert "INSERT INTO bot_memory_material_sources" in visible_source
    assert "decision_fingerprint_repeat_count" in diagnosis_json


def test_policy_model_shadow_assist_uses_registered_artifact_and_safe_gate():
    mgr_header = read(BOT_MGR_HEADER)
    mgr = read(BOT_MGR)
    conf = read(WORLDSERVER_CONF)
    schema = read(ROOT / "sql/updates/characters/4.3.4/2026_06_14_00_characters_bot_policy_models.sql")
    area_schema = read(ROOT / "sql/updates/characters/4.3.4/2026_06_14_01_characters_bot_decision_area_id.sql")
    validate = function_body(mgr, "void BotWorldPopulationMgr::ValidatePolicyModelDeployment")
    load_artifact = function_body(mgr, "bool BotWorldPopulationMgr::LoadPolicyModelArtifact")
    apply_scores = function_body(mgr, "void BotWorldPopulationMgr::ApplyPolicyModelScores")
    score = function_body(mgr, "float BotWorldPopulationMgr::ScorePolicyModelCandidate")
    trace = function_body(mgr, "BotWorldPopulationMgr::PolicyModelTrace BotWorldPopulationMgr::BuildPolicyModelTrace")
    record = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")

    for symbol in [
        "ArtifactPath",
        "ArtifactLoaded",
        "ModelMeans",
        "ModelWeights",
        "LoadPolicyModelArtifact",
        "PredictPolicyModelLabel",
        "BuildPolicyModelFeatureMap",
        "RecordDecisionReplay",
    ]:
        assert symbol in mgr_header

    assert "accepted, artifact_path, model_type" in validate
    assert "LoadPolicyModelArtifact(Cohort().PolicyModelConfig.ArtifactPath)" in validate
    assert "Cohort().PolicyModelConfig.Mode == \"shadow\"" in validate
    assert "Cohort().PolicyModelConfig.Mode == \"control\"" in validate
    assert "control_mode_disabled" in validate
    assert "Cohort().PolicyModelConfig.AssistAllowed = true;" in validate
    assert "artifact_load_failed" in validate

    assert "ReadSmallTextFile(artifactPath)" in load_artifact
    assert "ExtractJsonObjectField(json, \"means\")" in load_artifact
    assert "ExtractJsonObjectField(json, \"weights\")" in load_artifact
    assert "Cohort().PolicyModelConfig.ArtifactLoaded = true;" in load_artifact

    assert "MaxDecisionLatencyMs" in apply_scores
    assert "latencyMs > Cohort().PolicyModelConfig.MaxDecisionLatencyMs" in apply_scores
    assert "PredictPolicyModelLabel(\"expected_reward\", features)" in score
    assert "PredictPolicyModelLabel(\"death_risk\", features)" in score
    assert "artifact_loaded" in trace
    assert "model_type" in trace
    assert '\\"run_id\\"' in trace
    assert '\\"experiment_id\\"' in trace
    assert '\\"decision_id\\":null' in trace
    assert '\\"replay_id\\":' in trace
    assert '\\"feature_schema_version\\"' in trace

    for column in [
        "`model_version` varchar(128) NULL",
        "`feature_schema_version` varchar(64) NULL",
        "`model_score` float NULL",
        "`model_rank` int unsigned NULL",
        "`model_features_hash` int unsigned NULL",
    ]:
        assert column in schema
    assert "ADD COLUMN `area_id` int unsigned NULL" in area_schema
    assert "idx_experiment_bot_decisions_area" in area_schema

    assert "RecordDecisionReplay(state, bot, target" in record
    assert "replay_key" in record
    assert "zone_id, area_id, x, y, z" in record
    assert "bot->GetAreaId()" in record
    assert "model_version, feature_schema_version, model_score, model_rank, model_features_hash" in record
    for key in [
        "BotPolicyModel.MinEvalRows = 100",
        "BotPolicyModel.MaxDeathRate = 0.0",
        "BotPolicyModel.MaxStuckRate = 0.0",
        "BotPolicyModel.MaxFailureRate = 0.0",
    ]:
        assert key in conf
    assert "Mode may be shadow," in conf
    assert "assist, or control" in conf


def test_host_world_makefile_can_generate_always_on_recording_config():
    makefile = read(ROOT / "Makefile")

    assert "BOTWORLD_ENABLE ?= 1" in makefile
    assert "BOTWORLD_AUTOSTART ?= 0" in makefile
    assert "BOTWORLD_AUTOSTART_RECORDING ?= 1" in makefile
    assert "BOTWORLD_RECORDING_WINDOW_MINUTES ?= 15" in makefile
    assert "BOTWORLD_TARGET_POPULATION ?= 5" in makefile
    assert "BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK ?= 0" in makefile
    assert "BOTWORLD_USE_SAVED_POSITION ?= 1" in makefile
    assert "host-world-botexp-real" in makefile
    assert "host-world-botexp-watch" in makefile
    assert "bot-live-validate" in makefile
    assert "tools.bot_ml.run_live_bot_validation" in makefile
    assert "BotWorld.AutoStart = $(BOTWORLD_AUTOSTART)" in makefile
    assert "BotWorld.AutoStartRecording = $(BOTWORLD_AUTOSTART_RECORDING)" in makefile
    assert "BotWorld.AutoRecordingWindowMinutes = $(BOTWORLD_RECORDING_WINDOW_MINUTES)" in makefile
    assert "s|^BotWorld\\.SpawnMode\\s*=.*$$|BotWorld.SpawnMode = \"$(BOTWORLD_SPAWN_MODE)\"|gm" in makefile
    assert "BotWorld.UseSavedPosition = $(BOTWORLD_USE_SAVED_POSITION)" in makefile
    assert "BotWorld.RespawnMode = \"native_corpse_run\"" in makefile
    assert "BotWorld.AllowQuesting = 1" in makefile


def test_player_bot_chase_movement_inform_does_not_deref_non_creature_owner():
    chase = read(CHASE_MOVEMENT)
    inform = function_body(chase, "inline void DoMovementInform")

    assert "if (!owner->IsCreature())" in inform
    assert_ordered(inform, "if (!owner->IsCreature())", "return;", "owner->ToCreature()->AI()")


def test_profile_combat_resolver_prioritizes_density_actions_then_uses_rotation_fallbacks():
    mgr = read(BOT_MGR)
    resolver = function_body(
        mgr,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    executor = function_body(
        mgr,
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state, Player* bot, Unit* target",
    )

    assert "candidate.Category == BotCombatActionCategory::Aoe" in resolver
    assert "candidate.Category == BotCombatActionCategory::Cleave" in resolver
    assert "candidate.Category == BotCombatActionCategory::ResourceGenerator" in resolver
    assert "bestDensityFallback" in resolver
    assert "candidate.Profile.MinEnemies > hostileCount" in resolver
    assert "hostileCount > candidate.Profile.MaxEnemies" in resolver
    assert 'candidate.RejectReason = "enemy_count_too_low";' in resolver
    assert 'candidate.RejectReason = "enemy_count_too_high";' in resolver
    assert "auto engagedWithBotParty = [bot](Unit* unit) -> bool" in resolver
    assert "player->GetGroup() == bot->GetGroup()" in resolver
    assert "&& engagedWithBotParty(unit)" in resolver
    assert "best = bestDensityRecovery" in resolver
    assert "bestDensityResourceFallback" in resolver
    assert "bestDensityFallback ? bestDensityFallback : bestDensityGenerator" in resolver
    assert "ResolvedCombatAction action = ResolveProfileCombatAction(" in executor
    assert "bot, target, hostileCount, densityOnly" in executor


def test_hostile_profile_execution_rejects_buffs_and_defers_moving_cast_time_spells():
    mgr = read(BOT_MGR)
    resolver = function_body(
        mgr,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    executor = function_body(read(ROOT / "src/server/game/Bots/BotActionExecutor.cpp"), "BotActionResult BotActionExecutor::ExecuteCombat")

    assert "candidate.Category == BotCombatActionCategory::Buff" in resolver
    assert 'candidate.RejectReason = "requires_ally_target";' in resolver
    assert "spellInfo->CalcCastTime(bot->getLevel()) > 0" in executor
    assert "bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING)" in executor
    assert_ordered(
        executor,
        "bot->StopMoving();",
        "MoveIdle();",
        "return BotActionResult::Casting;",
        "bot->CastSpell(target, action.SpellId, castArgs)",
    )


def test_feral_stampeding_roar_records_every_existing_gate_and_cast_rejection():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "feral_stampeding_roar_gate_v1" in objective
    for gate in [
        "reserved_healer_threat_handoff",
        "native_charge_ready_for_healer_threat",
        "active_path_valid",
        "state_is_moving",
        "has_spell_77761",
        "has_aura_77761",
        "cast_attempted",
        "cast_submitted",
        "failure_reason",
    ]:
        assert gate in objective
    assert "bot, bot, 77761, &failureReason" in objective
    assert '"feral_stampeding_roar_not_submitted:" + failureReason' in objective
    assert "healerThreatAttacker, diagnosticResult.c_str()" in objective
    assert_ordered(
        objective,
        'failureReason = "reserved_healer_threat_handoff";',
        'failureReason = "native_charge_ready_for_healer_threat";',
        'failureReason = "inactive_path";',
        'failureReason = "state_not_moving";',
        'failureReason = "missing_spell";',
        'failureReason = "aura_active";',
        "TryCastFriendlySpell(",
        '"validation_route_threat_pickup_diagnostic"',
        "std::string diagnosticResult",
        "if (castSubmitted)",
    )


def test_rerun168_feral_healer_threat_restores_bear_form_before_recovery():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert_ordered(
        objective,
        "if (healerThreatAttacker)",
        "state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);",
        "if (!bot->HasAura(5487) && bot->HasSpell(5487)",
        "TryCastFriendlySpell(bot, bot, 5487)",
        '"feral_bear_form_healer_threat_before_recovery"',
        "healerThreatAttackerCount == 1",
        "TryCastCombatSpell(bot, healerThreatAttacker, 6795)",
    )


def test_rerun168_feral_reserved_handoff_preempts_stampeding_roar_gcd():
    objective = read(ROUTE_GATE) + read(FERAL_HANDOFF)

    assert_ordered(
        objective,
        "bool const reservedHealerThreatHandoff =",
        "state.FeralHealerThreatHandoffUntilMs > NowMs()",
        "!state.FeralHealerThreatHandoffTargetGuid.IsEmpty()",
        "!state.FeralHealerThreatHandoffAnchorGuid.IsEmpty()",
        "if (reservedHealerThreatHandoff)",
        'failureReason = "reserved_healer_threat_handoff";',
        "TryCastFriendlySpell(\n                    bot, bot, 77761, &failureReason)",
        "if (castSubmitted)",
        "if (state.FeralHealerThreatHandoffRemoteCluster",
        "TryCastCombatSpell(\n                        bot, feralTrashHandoffAnchor, 16979)",
    )


def test_feral_single_healer_threat_growl_preempts_stampeding_roar_gcd():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "healerThreatAttackerCount == 1" in objective
    assert '"feral_growl_single_healer_threat_before_roar"' in objective
    assert_ordered(
        objective,
        "healerThreatAttackerCount == 1",
        "TryCastCombatSpell(bot, healerThreatAttacker, 6795)",
        '"feral_growl_single_healer_threat_before_roar"',
        "bool const activePathValid = state.ActivePathValid;",
        "TryCastFriendlySpell(",
        '"feral_stampeding_roar_healer_threat_reposition"',
    )


def test_rerun198_multi_healer_wave_reserves_native_pickup_before_stampeding_roar():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    gate = objective.split(
        "bool const reservedHealerThreatHandoff =", 1
    )[1].split("std::ostringstream diagnosticRaw;", 1)[0]

    assert_ordered(
        gate,
        "if (reservedHealerThreatHandoff)",
        "else if (nativeChargeReadyForHealerThreat)",
        "else if (healerThreatAttackerCount >= 3)",
        'failureReason = "multi_healer_wave_native_pickup_reserved";',
        "else if (!activePathValid)",
        "TryCastFriendlySpell(",
    )
    assert "SetVictim" not in gate
    assert "AddThreat" not in gate
    assert "NearTeleportTo" not in gate


def test_feral_generic_healer_threat_fallback_preserves_densest_cluster_target():
    objective = read(FERAL_HANDOFF) + read(TRASH_THREAT_FAMILY) + read(TANK_TRASH_RECOVERY)
    fallback_source = read(TANK_TRASH_RECOVERY)
    fallback = fallback_source.split("Rerun140 proved the specialized Feral handoffs", 1)[1].split(
        "Unit* threatFocus = findTrashClusterThreatTarget();", 1
    )[0]

    assert "std::vector<Unit*> HealerOwnedTargets;" in objective
    assert "trashThreatControl.HealerOwnedTargets.push_back(creature);" in objective
    assert 'bot->getClass() == CLASS_DRUID && defenseTarget' in fallback
    assert 'std::string(GetDungeonRole(defenseTarget)) == "healer"' in fallback
    assert "candidate->GetVictim() != defenseTarget" in fallback
    assert "neighbor->GetVictim() == defenseTarget" in fallback
    assert "candidate->GetExactDist2d(neighbor) <= 10.0f" in fallback
    assert_ordered(
        fallback,
        "clusterCount > densestHealerClusterCount",
        "distance < densestHealerClusterDistance",
        "guid < densestHealerClusterGuid",
        "trashThreatControl.AreaTarget =",
        "densestHealerClusterTarget;",
        "ResolveProfileCombatAction(bot, target,",
    )
    assert_ordered(
        objective,
        '"feral_growl_lingering_healer_trash_attacker"',
        "Rerun140 proved the specialized Feral handoffs",
        'action = moved ? "move_to_trash_density"',
    )


def test_rerun160_feral_local_healer_swarm_prefers_native_swipe_with_roar_fallthrough():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    recovery = objective.split("Rerun160's maximum 6025-ms exposure", 1)[1].split(
        "if (feralTrashChargeArrived && defenseTarget", 1
    )[0]

    assert "nearbyHealerOwnedCount * 2" in recovery
    assert ">= currentHealerOwnedAttackers.size()" in recovery
    assert "trashThreatControl.EngagedCount >= 12" not in recovery
    assert "TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 779)" in recovery
    assert '"feral_swipe_healer_swarm_retention_before_roar"' in recovery
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "if (nearbyHealerOwnedCount >= 2 && missingOwnedRoar",
        "TryCastFriendlySpell(bot, bot, 99)",
        '"feral_demoralizing_roar_remote_healer_trash_cluster_handoff"',
    )


def test_rerun202_feral_ordinary_local_majority_prefers_thrash_before_swipe_and_roar():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    full_recovery = objective.split(
        "Rerun160's maximum 6025-ms exposure", 1
    )[1].split("if (feralTrashChargeArrived && defenseTarget", 1)[0]
    recovery = full_recovery.split(
        "Rerun202's generation-13 Flayer swarm", 1
    )[1]

    assert "nearbyHealerOwnedCount >= 2" in full_recovery
    assert "nearbyHealerOwnedCount * 2" in full_recovery
    assert ">= currentHealerOwnedAttackers.size()" in full_recovery
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "if (nearbyHealerOwnedCount >= 2 && missingOwnedRoar",
        "TryCastFriendlySpell(bot, bot, 99)",
        '"feral_demoralizing_roar_remote_healer_trash_cluster_handoff"',
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetThreat" not in recovery
    assert "AddThreat" not in recovery
    assert "SetVictim" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun171_feral_arrived_boss_handoff_prefers_native_swipe_before_roar():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun171 completed all fourteen route nodes", 1
    )[1].split("Rerun163 reached its identity-bound remote handoff", 1)[0]

    assert "localHealerOwnedSwipeWindow" in recovery
    assert "!feralHealerHandoffActive || feralHealerHandoffArrived" in recovery
    assert "candidate->GetVictim() == densityHealer" in recovery
    assert "bot->GetExactDist2d(candidate) <= 10.0f" in recovery
    assert "localHealerOwnedSwipeCount * 2" in recovery
    assert ">= healerOwnedBeforeHandoffSwipe" in recovery
    assert "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)" in recovery
    assert '"feral_swipe_healer_swarm_retention_before_roar"' in recovery
    assert "state.DecisionTimer, 250" in recovery
    assert_ordered(
        manager,
        "Rerun171 completed all fourteen route nodes",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "Rerun163 reached its identity-bound remote handoff",
        "tryFeralRoarPickup(true)",
    )


def test_rerun198_arrived_boss_handoff_prefers_thrash_with_swipe_fallback():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun198's second failing Azil subwave", 1
    )[1].split("Rerun163 reached its identity-bound remote handoff", 1)[0]

    assert "localHealerOwnedMajority" in recovery
    assert_ordered(
        recovery,
        "feralHealerHandoffActive",
        "feralHealerHandoffArrived",
        "healerOwnedBeforeHandoffSwipe >= 2",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "localHealerOwnedMajority",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun199_arrived_handoff_thrash_accepts_local_minority_before_second_roar():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun199 then reached the same arrived handoff", 1
    )[1].split("Rerun144 proved that a successful local Roar", 1)[0]
    thrash_gate = recovery.split(
        "if (localHealerOwnedSwipeTarget", 1
    )[1].split("TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)", 1)[0]

    assert "feralHealerHandoffArrived" in thrash_gate
    assert "|| localHealerOwnedMajority" in thrash_gate
    assert "healerOwnedBeforeHandoffSwipe >= 2" in thrash_gate
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "if (localHealerOwnedSwipeTarget && bot->HasSpell(779)",
        "localHealerOwnedMajority",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
    )
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun203_fresh_boss_local_majority_prefers_thrash_before_swipe():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun203 proved the ordinary-trash Thrash correction", 1
    )[1].split("Rerun144 proved that a successful local Roar", 1)[0]
    thrash_gate = recovery.split(
        "if (localHealerOwnedSwipeTarget", 1
    )[1].split("TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)", 1)[0]

    assert "feralHealerHandoffActive && feralHealerHandoffArrived" in thrash_gate
    assert "|| localHealerOwnedMajority" in thrash_gate
    assert "healerOwnedBeforeHandoffSwipe >= 2" in thrash_gate
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun204_fresh_large_local_minority_prefers_thrash_before_roar():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun204 proved that the fresh local-majority Thrash gate", 1
    )[1].split("Rerun144 proved that a successful local Roar", 1)[0]
    thrash_gate = recovery.split(
        "if (localHealerOwnedSwipeTarget", 1
    )[1].split("TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)", 1)[0]

    assert "freshLargeLocalHealerCluster = !feralHealerHandoffActive" in recovery
    assert "healerOwnedBeforeHandoffSwipe >= 12" in recovery
    assert "localHealerOwnedSwipeCount >= 2" in recovery
    assert "|| freshLargeLocalHealerCluster" in thrash_gate
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
    )
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun190_feral_local_majority_swipe_precedes_initial_roar():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun190 then proved the same damaging pickup"
    )
    recovery = objective[marker - 700 : marker + 10000]

    assert_ordered(
        recovery,
        'profile.SpecTag == "feral_druid_tank"',
        "!feralHealerHandoffActive || feralHealerHandoffArrived",
        "candidate->GetVictim() == densityHealer",
        "localHealerOwnedSwipeCount * 2",
        ">= healerOwnedBeforeHandoffSwipe",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun173_protection_healer_decay_and_hazard_pickup_use_native_responses():
    route = read(TRASH_THREAT_FAMILY) + read(MOVEMENT_CHECK_ACTIONS)

    fade_marker = route.index(
        "Rerun173's Protection/Holy composition fully owned the opening corridor"
    )
    fade_branch = route[fade_marker : fade_marker + 3300]
    assert "trashThreatControl.Tank->getClass() == CLASS_PALADIN" in fade_branch
    assert "trashThreatControl.HealerTargetCount >= 4" in fade_branch
    assert "trashThreatControl.HealerTargetCount >= 9" in fade_branch
    assert "protectionPaladinHealerThreat" in fade_branch
    assert "state.DecisionTimer, 250" in fade_branch
    assert "TryCastFriendlySpell(bot, bot, 586)" in fade_branch
    assert_ordered(
        fade_branch,
        "protectionPaladinHealerThreat =",
        "trashThreatControl.HealerTargetCount >= 9",
        "state.DecisionTimer, 250",
        "TryCastFriendlySpell(bot, bot, 586)",
        '"fade_early_trash_swarm_threat_drop"',
    )

    hazard_marker = route.index(
        "Rerun173's only over-ceiling dwell began when an Azil follower"
    )
    hazard_branch = route[hazard_marker - 900 : hazard_marker + 4500]
    assert 'hazardProfile.SpecTag == "protection"' in hazard_branch
    assert "bot->getClass() == CLASS_PALADIN" in hazard_branch
    assert "areaPriority == 3 && areaTarget" in hazard_branch
    assert "state.DecisionTimer, 250" in hazard_branch
    assert "TryCastCombatSpell(bot, areaTarget, 62124)" in hazard_branch
    assert '"hand_of_reckoning_hazard_healer_pickup"' in hazard_branch
    assert "Player* hazardHealer = areaTarget->GetVictim()" in hazard_branch
    assert 'GetDungeonRole(hazardHealer) == "healer"' in hazard_branch
    assert "TryCastFriendlySpell(bot, hazardHealer, 31789)" in hazard_branch
    assert '"righteous_defense_hazard_healer_pickup"' in hazard_branch
    assert_ordered(
        hazard_branch,
        "BotClassSpecActionProfile hazardProfile",
        'hazardProfile.SpecTag == "protection"',
        "TryCastCombatSpell(bot, areaTarget, 62124)",
        '"hand_of_reckoning_hazard_healer_pickup"',
        "TryCastFriendlySpell(bot, hazardHealer, 31789)",
        '"righteous_defense_hazard_healer_pickup"',
        "auto tryFeralHazardThrashRetention",
    )


def test_rerun174_large_passive_swarm_stages_party_before_native_activation():
    manager = read(BOT_MGR)
    route = read(AZIL_PASSIVE_SWARM)
    marker = route.index(
        "Rerun174 reached this passive 60-follower wave"
    )
    branch = route[marker - 800 : marker + 21000]

    assert "tankVisiblePassiveSwarmEngagedCount == 0" in branch
    assert "tankVisiblePassiveSwarmAddCount >= 24" in branch
    assert "isUsableListedAdd(densityTank, creature)" in branch
    assert "largePassiveSwarmEvidenceTarget" in branch
    assert_ordered(
        branch,
        "!manager.IsValidationCohortMemberInOriginalInstance(",
        "++largePassiveSwarmLoadedParticipants",
        "member->GetExactDist2d(densityTank) <= 18.0f",
    )
    assert "member->GetExactDist2d(densityTank) <= 18.0f" in branch
    assert "largePassiveSwarmStagedParticipants" in branch
    assert "Cohort().Config.TargetPopulation" in branch
    assert 'role != "tank"' in branch
    assert '"stage_for_large_passive_swarm_activation"' in branch
    assert '"hold_for_large_passive_swarm_activation"' in branch
    assert '"hold_large_passive_swarm_for_party_staging"' in branch
    assert "state.DecisionTimer, 250" in branch
    assert_ordered(
        branch,
        "tankVisiblePassiveSwarmAddCount",
        "bool largePassiveSwarm =",
        'role != "tank"',
        '"stage_for_large_passive_swarm_activation"',
        'role == "tank" && largePassiveSwarm',
        '"hold_large_passive_swarm_for_party_staging"',
        "BotMeleeAutoAttack::Kind::StartOrSwitch",
        '"tank_activate_passive_swarm"',
    )


def test_rerun176_remote_party_uses_tank_visible_passive_swarm_gate():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = route.index("Rerun176 proved the original staging decision")
    branch = route[marker : marker + 17000]

    assert_ordered(
        branch,
        "Trinity::AllWorldObjectsInRange tankVisibleCheck(",
        "densityTank, 45.0f",
        "isUsableListedAdd(densityTank, creature)",
        "++tankVisiblePassiveSwarmAddCount",
        "tankVisiblePassiveSwarmEngagedCount == 0",
        "tankVisiblePassiveSwarmAddCount >= 24",
        "largePassiveSwarmEvidenceTarget",
        'role != "tank"',
        "stagingReference",
        '"stage_for_large_passive_swarm_activation"',
        'role == "tank" && pendingSwarmActivation',
        "BotMeleeAutoAttack::Kind::StartOrSwitch",
    )


def test_rerun176_native_charge_preempts_stampeding_roar_and_small_pack_decay():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    charge = objective.split(
        "bool nativeChargeReadyForHealerThreat = false;", 1
    )[1].split("std::ostringstream diagnosticRaw;", 1)[0]
    secure = read(TRASH_INTERVENTION)

    assert "bot->GetSpellHistory()->HasGlobalCooldown(" in charge
    assert "bot->GetSpellHistory()->IsReady(chargeInfo)" in charge
    assert "HasPowerForSpell(bot, chargeInfo)" in charge
    assert_ordered(
        charge,
        "nativeChargeReadyForHealerThreat =",
        "if (reservedHealerThreatHandoff)",
        "else if (nativeChargeReadyForHealerThreat)",
        'failureReason = "native_charge_ready_for_healer_threat";',
        "TryCastFriendlySpell(",
    )
    assert "trashThreatControl.EngagedCount >= 3" in secure
    assert "trashThreatControl.TankOwnsTrashMajority" in secure
    assert "trashThreatControl.InsecureTrashSwarm" in secure
    assert "TryCastCombatSpell(bot, feralSecureMarginTarget, 779)" in secure


def test_rerun177_moderate_healer_subwave_ignores_tank_owned_cohort_size():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun177's only failing dwell was an eleven-healer-owned"
    )
    branch = objective[marker : marker + 1200]

    assert "healerOwnedCount >= 3 && healerOwnedCount < 12" in branch
    assert "nearbyHealerOwnedCount >= 1" in branch
    assert "engagedAddCount < 12" not in branch
    assert_ordered(
        branch,
        "bool immediateModerateWavePickup =",
        "healerOwnedCount >= 3 && healerOwnedCount < 12",
        "nearbyHealerOwnedCount >= 1",
        "bool usefulLocalPickup = immediateModerateWavePickup",
    )


def test_rerun178_tank_proof_drives_remote_passive_swarm_staging():
    manager = read(BOT_MGR)
    objective = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun178 proved that recomputing the tank-visible staging fact"
    )
    shared = objective[marker - 1300 : marker + 19000]
    pre_anchor = objective[objective.index("bool sharedLargePassiveSwarmStaging =") : marker]

    assert "ValidationRouteLargePassiveSwarmStagingGeneration" in pre_anchor
    assert "&& !sharedLargePassiveSwarmStaging" in pre_anchor
    assert_ordered(
        shared,
        "bool tankViewProvesLargePassiveSwarm =",
        "tankVisiblePassiveSwarmEngagedCount == 0",
        "tankVisiblePassiveSwarmAddCount >= 24",
        'if (role == "tank" && tankViewProvesLargePassiveSwarm)',
        "Party().ValidationRouteLargePassiveSwarmStaging = true",
        "bool largePassiveSwarm = densityTank",
        "&& sharedLargePassiveSwarmStaging",
        'role != "tank"',
        "float stagingAngle =",
        "FOLLOW_MOTION_TYPE",
        "MoveFollow(",
        '"stage_for_large_passive_swarm_activation"',
        'role == "tank" && pendingSwarmActivation',
        "BotMeleeAutoAttack::Kind::StartOrSwitch",
    )
    reset = function_body(
        manager,
        "void BotWorldPopulationMgr::ResetValidationRouteBossAddDensityState",
    )
    assert "ValidationRouteLargePassiveSwarmStaging = false" in reset
    assert "ValidationRouteLargePassiveSwarmStagingGeneration = 0" in reset


def test_rerun179_azil_seismic_shards_fail_closed_without_an_empty_seat():
    script = read(AZIL_SCRIPT)
    mount = script[script.index("case EVENT_SEISMIC_SHARD_MOUNT:") :]
    mount = mount[: mount.index("default:")]
    fill_path = function_body(script, "void FillPath")

    assert "SeatMap::const_iterator seat = vehicle->GetNextEmptySeat(0, false);" in mount
    assert "if (seat != vehicle->Seats.end())" in mount
    assert "me->EnterVehicle(highPriestAzil, seat->first);" in mount
    assert "me->DespawnOrUnsummon();" in mount
    assert "vehicle->GetNextEmptySeat(0, false)->first" not in mount
    assert fill_path.count("path.push_back(point);") == 3


def test_rerun180_large_feral_wave_retires_moderate_pickup_reservation():
    objective = read(BOT_DIR / "BotWorldPopulationMgrValidationFeralPickup.cpp")
    marker = objective.index(
        "Rerun180 captured a moderate reservation while eleven Azil"
    )
    promotion = objective[marker : marker + 2400]

    assert "healerOwnedCount >= 12 && nearbyHealerOwnedCount < 2" in promotion
    assert "state.FeralActiveSwarmPickupAnchorGuid.Clear();" in promotion
    assert "state.FeralActiveSwarmPickupUntilMs = 0;" in promotion
    assert "state.FeralActiveSwarmPickupAttempted = false;" in promotion
    assert "state.FeralActiveSwarmPickupArrived = false;" in promotion
    assert_ordered(
        promotion,
        "state.FeralActiveSwarmPickupAnchorGuid.Clear();",
        "state.FeralActiveSwarmPickupUntilMs = 0;",
        "MoveBotToPoint(state, bot,\n                    densityHealer->GetPositionX(),",
        '"feral_move_to_healer_for_split_swarm_pickup"',
    )
    assert "observedListedAttackerCount(densityHealer) < 3" in objective
    assert "healerOwnedCount >= 3 && healerOwnedCount < 12" in objective


def test_rerun175_feral_healer_target_preempts_tank_owned_density():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = route.index(
        "Rerun175's only 14 eligible healer-exposure samples"
    )
    branch_start = route.rindex(
        "bool feralCurrentHealerThreat =", 0, marker
    )
    branch = route[branch_start : marker + 12000]

    assert "feralCurrentHealerThreat" in branch
    assert_ordered(
        branch,
        "bool feralCurrentHealerThreat =",
        "bool feralTankOwnedDensitySelected = false;",
        "&& !feralCurrentHealerThreat",
        "if (!feralTankOwnedDensitySelected",
        "trashThreatControl.HealerOwnedTargets",
        "trashThreatControl.AreaTarget =",
        "ResolveProfileCombatAction(bot, target",
    )


def test_feral_large_tank_owned_trash_wave_prefers_density_before_freshness():
    objective = read(TRASH_THREAT_FAMILY) + read(TANK_TRASH_RECOVERY)
    selector = objective.split("Rerun142 proved continuous aura-fresh", 1)[1].split(
        "Rerun140 proved the specialized Feral handoffs", 1
    )[0]
    ordering = selector.split("if (!densestTankOwnedClusterTarget", 1)[1]

    assert "std::vector<Unit*> TankOwnedTargets;" in objective
    assert "trashThreatControl.TankOwnedTargets.push_back(creature);" in objective
    assert "trashThreatControl.EngagedCount >= 12" in selector
    assert "trashThreatControl.TankOwnsTrashMajority" in selector
    assert "candidate->GetVictim() != trashThreatControl.Tank" in selector
    assert "neighbor->GetVictim() == trashThreatControl.Tank" in selector
    assert "candidate->GetExactDist2d(neighbor) <= 10.0f" in selector
    assert "!candidate->HasAura(77758, bot->GetGUID())" in selector
    assert_ordered(
        ordering,
        "clusterCount > densestTankOwnedClusterCount",
        "missingThrash",
        "distance < densestTankOwnedClusterDistance",
        "guid < densestTankOwnedClusterGuid",
        "trashThreatControl.AreaTarget =",
        "densestTankOwnedClusterTarget;",
        "feralTankOwnedDensitySelected = true;",
    )
    assert_ordered(
        read(TANK_TRASH_RECOVERY),
        "Rerun142 proved continuous aura-fresh",
        "Rerun140 proved the specialized Feral handoffs",
        "ResolveProfileCombatAction(bot, target,",
    )


def test_feral_secure_margin_targets_remote_insecure_cluster_before_swipe():
    objective = read(TRASH_THREAT_FAMILY) + read(TRASH_INTERVENTION)
    selector = objective.split("Unit* feralSecureMarginTarget = nullptr;", 1)[1].split(
        "Rerun112 localized the all-hostile retention failure", 1
    )[0]

    assert "std::vector<Unit*> InsecureTankOwnedTargets;" in objective
    assert "trashThreatControl.InsecureTankOwnedTargets.push_back(creature);" in objective
    assert "tankThreat >= 2000.0f" in objective
    assert "tankThreat >= highestPartyThreat * 2.5f" in objective
    assert "candidate->GetVictim() != bot" in selector
    assert "neighbor->GetVictim() == bot" in selector
    assert "candidate->GetExactDist2d(neighbor) <= 10.0f" in selector
    assert "state.FeralHealerThreatHandoffUntilMs > NowMs()" in selector
    assert "!feralHealerHandoffPending" in selector
    assert_ordered(
        selector,
        "clusterCount > feralSecureMarginClusterCount",
        "distance < feralSecureMarginDistance",
        "guid < feralSecureMarginGuid",
        "MoveBotToProfileRange(",
        '"feral_approach_insecure_trash_threat_cluster"',
        "TryCastCombatSpell(bot, feralSecureMarginTarget, 779)",
        '"feral_swipe_secure_trash_threat_margin"',
    )


def test_trash_tactical_focus_and_next_encounter_terminal_ownership_stay_separate():
    active_owner = read(TARGETING)
    area_owner = read(TANK_TRASH_RECOVERY)
    terminal_owner = read(TARGET_ENGAGEMENT)
    active_combat = active_owner.split("auto validationPartyHasActiveCombat", 1)[1].split(
        "auto isBoundedTerminalPartyCombatTarget", 1
    )[0]
    bounded_terminal = active_owner.split("auto isBoundedTerminalPartyCombatTarget", 1)[1].split(
        "auto findBoundedTerminalPartyCombatTarget", 1
    )[0]
    area_focus = area_owner.split("target = trashThreatControl.AreaTarget;", 1)[1].split(
        "ResolvedCombatAction areaAction", 1
    )[0]
    terminal_start = terminal_owner.index("bool packHasLiveMobs = trashClusterHasLiveMobs();")
    terminal = terminal_owner[terminal_start : terminal_owner.index("if (terminalCombatTarget)", terminal_start)]

    assert "isImmediateNextValidationRouteEncounterMember" in active_combat
    assert "transferImmediateNextEncounter" in active_combat
    assert "isImmediateNextValidationRouteEncounterMember(creature)" in bounded_terminal
    assert "isImmediateNextValidationRouteBossTarget(creature)" not in bounded_terminal
    assert "!isImmediateNextValidationRouteEncounterMember(areaCreature)" in area_focus
    assert "isEligibleTrashClusterMob(areaCreature)" not in area_focus
    assert 'Cohort().Config.ValidationRouteKind == "boss"' not in area_focus
    assert "rememberValidationRouteFocus(target);" in area_focus
    assert_ordered(
        terminal,
        "bool packHasLiveMobs = trashClusterHasLiveMobs();",
        "validationPartyHasActiveCombat(!packHasLiveMobs)",
        "!packHasLiveMobs && partyHasActiveCombatUnit",
    )


def test_feral_boss_remote_handoff_uses_collision_safe_eight_yard_intercept():
    objective = read(AZIL_FERAL_LOCAL)
    handoff = objective.split("Rerun141 left one generation-14 boss-handoff attacker", 1)[1].split(
        'RecordEvent(state, bot, "boss_add_density", movementAnchor,', 1
    )[0]

    assert "state.FeralHealerThreatHandoffRemoteCluster" in handoff
    assert "movementAnchor->GetFirstCollisionPosition(" in handoff
    assert "8.0f" in handoff
    assert "movementAnchor->GetAngle(bot)" in handoff
    assert "- movementAnchor->GetOrientation()" in handoff
    assert_ordered(
        handoff,
        "Position remoteRoarIntercept;",
        "movementX =",
        "movementY =",
        "movementZ =",
        "continuingRemotePath",
        "manager.MoveBotToPoint(state,\n                bot, movementX, movementY, movementZ);",
        "movementX, movementY, movementZ",
    )


def test_feral_initial_boss_split_handoff_starts_at_same_roar_intercept():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    initial_handoff = objective.split(
        "Rerun150 proved the continuation's collision-safe Roar", 1
    )[1].split("if (remoteClusterRemains)", 1)[0]

    assert "remoteClusterAnchor->GetFirstCollisionPosition(" in initial_handoff
    assert "8.0f" in initial_handoff
    assert "remoteClusterAnchor->GetAngle(bot)" in initial_handoff
    assert "- remoteClusterAnchor->GetOrientation()" in initial_handoff
    assert "remoteClusterAnchor->GetPositionX()" not in initial_handoff
    assert "remoteClusterAnchor->GetPositionY()" not in initial_handoff
    assert "remoteClusterAnchor->GetPositionZ()" not in initial_handoff
    assert_ordered(
        initial_handoff,
        "Position remoteRoarIntercept;",
        "splitHandoffX =",
        "splitHandoffY =",
        "splitHandoffZ =",
        "bool splitClusterHandoff = remoteClusterRemains",
        "MoveBotToPoint(state, bot,",
        "splitHandoffX, splitHandoffY, splitHandoffZ",
    )


def test_feral_arrived_handoff_retries_roar_before_post_roar_area_threat():
    objective = read(AZIL_FERAL_LOCAL)
    post_roar = objective.split("Rerun144 proved that a successful local Roar", 1)[1].split(
        "Rerun106 isolated two Azil split waves", 1
    )[0]

    assert "candidate->GetVictim() == densityHealer" not in post_roar
    assert "bot->GetExactDist2d(candidate) <= 10.0f" in post_roar
    assert "candidate->HasAura(99, bot->GetGUID())" in post_roar
    assert (
        "postRoarAreaThreatReady = feralHealerHandoffActive\n"
        "        && feralHealerHandoffArrived"
    ) in post_roar
    assert "healerOwnedAfterRoar >= 2" in post_roar
    assert "localRoarCoveredCount >= 2" in post_roar
    assert "localRoarCoveredCount * 2 >= healerOwnedAfterRoar" in post_roar
    assert "ResolveProfileCombatAction(" in post_roar
    assert "addCount, true, 0, true" in post_roar
    assert "ExecuteProfileCombatAction(" in post_roar
    assert '"feral_post_roar_area_threat_retention"' in post_roar
    assert '"feral_hold_post_roar_area_threat_retention"' in post_roar
    assert_ordered(
        read(AZIL_FERAL_LOCAL) + read(AZIL_FERAL_REMOTE),
        "Rerun163 reached its identity-bound remote handoff",
        "feralHealerHandoffActive && feralHealerHandoffArrived",
        "tryFeralRoarPickup(true)",
        "Rerun144 proved that a successful local Roar",
        "feral_post_roar_area_threat_retention",
        "Rerun106 isolated two Azil split waves",
        "// A remote Charge must not abandon a useful local healer-owned cluster.",
    )

    retry = objective.split(
        "Rerun163 reached its identity-bound remote handoff", 1
    )[1].split("Rerun144 proved that a successful local Roar", 1)[0]
    assert "acceptance" not in retry
    assert "threshold" not in retry
    assert "tryFeralRoarPickup(true)" in retry
    assert "return true;" in retry


def test_rerun181_prearrival_handoff_does_not_spend_post_roar_swipe_gcd():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    post_roar = objective.split("Rerun144 proved that a successful local Roar", 1)[1].split(
        "Rerun106 isolated two Azil split waves", 1
    )[0]

    assert_ordered(
        post_roar,
        "Rerun181 showed this resolver could spend native Swipe",
        "postRoarAreaThreatReady = feralHealerHandoffActive",
        "&& feralHealerHandoffArrived",
        "if (postRoarAreaThreatReady)",
        '"feral_post_roar_area_threat_retention"',
    )


def test_rerun182_shared_passive_swarm_proof_keeps_native_tank_follow():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun182 proved the generation-scoped tank observation"
    )
    branch = objective[marker : marker + 17000]
    staging = branch[
        branch.index('if (largePassiveSwarm && role != "tank"') :
        branch.index('if (role == "tank" && pendingSwarmActivation')
    ]

    assert "cohortSwarmActive && densityTank" not in branch[:800]
    assert_ordered(
        branch,
        "bool largePassiveSwarm = densityTank",
        "&& sharedLargePassiveSwarmStaging",
        "member->GetExactDist2d(densityTank) <= 18.0f",
        'role != "tank"',
        "FOLLOW_MOTION_TYPE",
        "state.ActivePathToX = densityTank->GetPositionX()",
        "MoveFollow(",
        "densityTank, stagingRadius, stagingAngle",
        '"stage_for_large_passive_swarm_activation"',
    )
    assert "MoveBotToPoint" not in staging
    assert "largePassiveSwarmPartyStaged" in branch
    assert 'role == "tank" && pendingSwarmActivation' in branch
    assert "BotMeleeAutoAttack::Kind::StartOrSwitch" in branch


def test_rerun196_shared_passive_swarm_proof_resolves_remote_staging_tank():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun195 proved that the shared large-passive-swarm fact"
    )
    branch = objective[
        objective.index("bool sharedLargePassiveSwarmStaging =") :
        objective.index("bool passiveSwarmActivationNotActionable")
    ]

    assert marker > objective.index("bool sharedLargePassiveSwarmStaging =")
    assert_ordered(
        branch,
        "bool sharedLargePassiveSwarmStaging =",
        "bool swarmDefenseActive = highDensityPhase || cohortSwarmActive",
        "|| sharedLargePassiveSwarmStaging;",
        "if (swarmDefenseActive)",
        'if (!densityTank && memberRole == "tank")',
        "densityTank = member;",
        "bool largePassiveSwarm = densityTank",
        "&& sharedLargePassiveSwarmStaging",
        'if (largePassiveSwarm && role != "tank"',
        "MoveFollow(",
        "BotMeleeAutoAttack::Kind::StartOrSwitch",
    )
    assert "member->GetExactDist2d(densityTank) <= 18.0f" in branch
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun183_healer_owned_stable_swarm_path_revalidates_early():
    objective = read(SWARM_APPROACH)
    marker = objective.index(
        "Rerun183 exposed one identity-stable healer-owned follower"
    )
    branch = objective[marker - 500 : marker + 2300]

    assert_ordered(
        branch,
        "bool BotWorldPopulationMgr::ContinueStableTankSwarmApproach(",
        "bool selectedHealerOwned = densityHealer && selectedAdd",
        "selectedAdd->GetVictim() == densityHealer",
        'bool feralTank = profile.SpecTag == "feral_druid_tank"',
        'bool protectionPaladin = profile.SpecTag == "protection"',
        "protectionPaladin ? 1500 : 750",
        ": 2000",
        "pathAgeMs <= stableApproachLimitMs",
        "selectedAdd->GetExactDist2d(state.ActivePathToX, state.ActivePathToY)",
    )
    assert "cohortSwarmActive" in branch


def test_rerun184_feral_prepares_form_before_native_swarm_activation():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun184 activated all 59 staged followers onto the Feral"
    )
    branch = objective[marker - 700 : marker + 5200]

    assert_ordered(
        branch,
        "feralPassiveSwarmBearFormMissing",
        'profile.SpecTag == "feral_druid_tank"',
        "largePassiveSwarm && passiveSwarmClusterAnchor",
        "!bot->HasAura(5487)",
        "TryEnsurePersistentCombatSetup(",
        "feralPassiveSwarmBearFormGcdPending",
        "HasGlobalCooldown(",
        '"feral_prepare_bear_form_before_passive_swarm_activation"',
        '"feral_hold_bear_form_gcd_before_passive_swarm_activation"',
        'if (role == "tank" && largePassiveSwarm',
        "BotMeleeAutoAttack::Kind::StartOrSwitch",
    )
    assert "state.DecisionTimer, 250" in branch
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun185_protection_remote_boss_add_rescue_precedes_area_approach():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun185 completed Azil but localized 554 healer-target"
    )
    branch = objective[marker - 900 : marker + 6500]

    assert_ordered(
        branch,
        "if (approach)",
        'profile.SpecTag == "protection"',
        "densityDefenseTarget == densityHealer",
        "add->GetVictim() == densityHealer",
        "TryCastFriendlySpell(bot, densityHealer, 31789)",
        '"righteous_defense_healer_before_area_approach"',
        "TryCastCombatSpell(bot, add, 62124)",
        '"hand_of_reckoning_healer_before_area_approach"',
        "healerAttackerCount >= 2",
        "TryCastCombatSpell(bot, add, 31935)",
        '"avengers_shield_healer_before_area_approach"',
        "continueStableTankSwarmApproach(add)",
        "MoveBotToProfileRange(state, bot, add, &immediateAreaThreat)",
    )
    assert branch.count("state.DecisionTimer, 250);") >= 3
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun213_protection_keeps_bounded_stable_swarm_path():
    objective = read(SWARM_APPROACH)
    marker = objective.index(
        "Rerun213 found the equivalent topology gap for Protection"
    )
    branch = objective[objective.index(
        "bool BotWorldPopulationMgr::ContinueStableTankSwarmApproach("
    ) : marker + 1800]

    assert_ordered(
        branch,
        "bool BotWorldPopulationMgr::ContinueStableTankSwarmApproach(",
        "bool selectedHealerOwned = densityHealer && selectedAdd",
        'bool feralTank = profile.SpecTag == "feral_druid_tank"',
        'bool protectionPaladin = profile.SpecTag == "protection"',
        "protectionPaladin ? 1500 : 750",
        ": 2000",
        "role == \"tank\" && (feralTank || protectionPaladin)",
        "pathAgeMs <= stableApproachLimitMs",
        "selectedAdd->GetExactDist2d(state.ActivePathToX, state.ActivePathToY)",
    )
    assert "3000-ms dwell ceiling" in branch
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun186_boss_handoff_enrolls_remaining_healer_owned_newcomer():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    branch = objective.split(
        "Rerun156 proved the boss handoff discarded a still-valid Azil", 1
    )[1].split("bool feralHealerRemoteHandoffValid", 1)[0]
    fallback = branch.split(
        "Rerun186's first Roar started a bounded split-cluster handoff", 1
    )[1]

    assert_ordered(
        branch,
        "feralHealerHandoffAnchor->GetExactDist2d(candidate)",
        "<= 10.0f",
        "if (!reboundAnchor)",
        "float reboundDistance = std::numeric_limits<float>::max();",
        "bot->GetExactDist(candidate)",
        "state.FeralHealerThreatHandoffAnchorGuid =",
    )
    assert "candidate->GetVictim() == densityHealer" in fallback
    assert "bot->IsValidAttackTarget(candidate)" in fallback
    assert "distance < reboundDistance" in fallback
    assert "guid < reboundGuid" in fallback
    assert "FeralHealerThreatHandoffUntilMs =" not in fallback
    assert "SetThreat" not in fallback
    assert "SetVictim" not in fallback
    assert "NearTeleportTo" not in fallback


def test_rerun188_lingering_feral_healer_attacker_uses_native_swipe_after_growl():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun188 reduced Azil's final healer-owned wave to one follower"
    )
    branch = objective[marker - 1900 : marker + 3200]

    assert_ordered(
        branch,
        "observedListedAttackerCount(densityHealer) == 1",
        "TryCastCombatSpell(bot, healerOwnedAdd, 6795)",
        '"feral_growl_lingering_healer_swarm_attacker"',
        "TryCastCombatSpell(bot, healerOwnedAdd, 779)",
        '"feral_swipe_lingering_healer_swarm_attacker"',
        "add = healerOwnedAdd",
    )
    assert "state.DecisionTimer, 250" in branch
    assert "SetThreat" not in branch
    assert "SetVictim" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun189_protection_holy_wrath_uses_existing_self_centered_area_gate():
    migration = read(PROTECTION_HOLY_WRATH_SELF_SQL)
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    area_gate = objective.split(
        "On a multi-target wave, establish area threat before spending", 1
    )[1].split("if (role == \"tank\" && densityHealer", 1)[0]

    assert "SET a.`target_selector` = 'self'" in migration
    assert "p.`class_id` = 2" in migration
    assert "p.`spec_tag` = 'protection'" in migration
    assert "p.`role` = 'tank'" in migration
    assert "a.`spell_id` = 2812" in migration
    assert "min_enemies" not in migration
    assert "priority_bucket" not in migration
    assert_ordered(
        area_gate,
        "immediateAreaThreat.TargetGuid == bot->GetGUID()",
        "selfCenteredTargets >= 2",
        "bot->GetExactDist2d(add) <= 10.0f",
        "ExecuteProfileCombatAction(",
    )
    assert "SetThreat" not in area_gate
    assert "SetVictim" not in area_gate
    assert "NearTeleportTo" not in area_gate


def test_rerun192_protection_prefers_profile_self_centered_area_for_local_healer_wave():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    objective = function_body(
        mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    area_gate = objective.split(
        "Rerun191 captured fifteen Azil followers on the healer", 1
    )[1].split("if (role == \"tank\" && densityHealer", 1)[0]
    resolver = function_body(
        mgr,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )

    assert "bool selfCenteredOnly = false" in header
    assert_ordered(
        area_gate,
        "localProtectionHealerOwnedCount >= 2",
        "localProtectionHealerOwnedCount * 2",
        ">= protectionHealerAttackerCount",
        "ResolveProfileCombatAction(",
        "preferSelfCenteredProtectionArea",
        "!immediateAreaThreat.Valid && preferSelfCenteredProtectionArea",
    )
    assert 'candidate.Profile.TargetSelector != "self"' in resolver
    assert 'candidate.RejectReason = "self_centered_action_required"' in resolver
    assert "preferSelfCenteredProtectionArea);" in area_gate
    assert "SetThreat" not in area_gate
    assert "SetVictim" not in area_gate
    assert "NearTeleportTo" not in area_gate


def test_rerun193_protection_distributes_native_pickup_before_area_gcd():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    boss_marker = objective.index(
        "Rerun192 showed two distinct Protection starvation paths"
    )
    boss_branch = objective[boss_marker - 300 : boss_marker + 5600]
    trash_marker = objective.index(
        "Rerun170 retained 17 eligible healer-target samples"
    )
    trash_branch = objective[trash_marker : trash_marker + 4300]

    assert_ordered(
        boss_branch,
        'profile.SpecTag == "protection"',
        "protectionHealerAttackerCount >= 2",
        "TryCastFriendlySpell(bot, densityHealer, 31789)",
        '"righteous_defense_healer_before_area_gcd"',
        "Rerun191 captured fifteen Azil followers on the healer",
        "ResolveProfileCombatAction(",
    )
    assert "state.DecisionTimer, 250" in boss_branch
    assert_ordered(
        trash_branch,
        "bool healerTauntRepeatsCurrentTarget = true;",
        "attacker->GetGUID() == state.TargetGuid",
        "&& !repeatsCurrentTarget",
        "TryCastCombatSpell(bot, healerTauntTarget, 62124)",
    )
    assert "SetThreat" not in boss_branch + trash_branch
    assert "SetVictim" not in boss_branch + trash_branch
    assert "NearTeleportTo" not in boss_branch + trash_branch


def test_rerun198_protection_uses_native_healer_immunity_before_area_starvation():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun197 captured the complementary native-rescue"
    )
    rescue = objective[marker - 1300 : marker + 3800]

    assert_ordered(
        rescue,
        'TryCastFriendlySpell(bot, densityHealer, 31789)',
        '"righteous_defense_healer_before_area_gcd"',
        "protectionHealerAttackerCount >= 5",
        "!densityHealer->HasAura(1022)",
        "TryCastFriendlySpell(bot, densityHealer, 1022)",
        '"hand_of_protection_healer_before_area_gcd"',
        "Rerun191 captured fifteen Azil followers on the healer",
        "ResolveProfileCombatAction(",
    )
    assert "state.DecisionTimer, 250" in rescue
    lower_emergency = objective.index('"hand_of_protection_healer_emergency"')
    assert marker < lower_emergency
    assert "SetThreat" not in rescue
    assert "SetVictim" not in rescue
    assert "NearTeleportTo" not in rescue


def test_rerun200_protection_uses_avengers_shield_after_direct_taunt_rejection():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun200's only strict role failure was a remote two-follower Azil"
    )
    rescue = objective[marker - 1400 : marker + 3000]

    assert_ordered(
        rescue,
        "TryCastCombatSpell(bot, add, 62124)",
        '"hand_of_reckoning_add_pickup"',
        'profile.SpecTag == "protection"',
        "densityDefenseTarget == densityHealer",
        "addVictim == densityHealer",
        "observedListedAttackerCount(densityHealer) >= 2",
        "TryCastCombatSpell(bot, add, 31935)",
        '"avengers_shield_healer_add_pickup"',
        '"consecration_healer_pickup"',
    )
    assert "state.DecisionTimer, 250" in rescue
    assert "SetThreat" not in rescue
    assert "SetVictim" not in rescue
    assert "NearTeleportTo" not in rescue


def test_rerun200_protection_rescue_preserves_existing_area_approach_chain():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun200's only strict role failure was a remote two-follower Azil"
    )
    rescue = objective[marker - 1800 : marker + 4200]

    assert_ordered(
        rescue,
        '"righteous_defense_healer_pickup"',
        '"hand_of_reckoning_add_pickup"',
        '"avengers_shield_healer_add_pickup"',
        '"consecration_healer_pickup"',
    )
    area_marker = objective.index(
        "Rerun185 completed Azil but localized 554 healer-target"
    )
    area_rescue = objective[area_marker - 900 : area_marker + 6500]
    assert_ordered(
        area_rescue,
        '"righteous_defense_healer_before_area_approach"',
        '"hand_of_reckoning_healer_before_area_approach"',
        '"avengers_shield_healer_before_area_approach"',
        "MoveBotToProfileRange(state, bot, add, &immediateAreaThreat)",
    )


def test_rerun210_protection_warrior_charges_remote_healer_wave_before_area_movement():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun209's generation-14 maximum dwell began with fifteen Azil"
    )
    branch = objective[marker - 500 : marker + 10500]

    assert_ordered(
        branch,
        'profile.SpecTag == "protection_warrior"',
        "densityDefenseTarget == densityHealer",
        "add->GetVictim() == densityHealer",
        "warriorHealerAttackerCount >= 3",
        "bot->GetExactDist(add) > 8.0f",
        "bot->HasSpell(100)",
        "TryCastCombatSpell(bot, add, 100)",
        '"warrior_charge_healer_swarm_pickup"',
        "state.DecisionTimer, 250",
        "On a multi-target wave, establish area threat before spending",
        "ResolveProfileCombatAction(",
    )
    assert "state.DecisionTimer = std::min" in branch
    assert "SetThreat" not in branch
    assert "SetVictim" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun211_protection_warrior_closes_native_gap_and_peels_residual_healer_threat():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun210's maximum-dwell identity was the one survivor"
    )
    branch = objective[marker - 500 : marker + 14500]

    assert_ordered(
        branch,
        "warriorHealerAttackerCount > 0",
        "warriorHealerAttackerCount < 3",
        "guid < warriorResidualHealerGuid",
        "TryCastCombatSpell(bot, warriorResidualHealerAdd, 355)",
        '"warrior_taunt_residual_healer_threat"',
        "Rerun209's generation-14 maximum dwell began with fifteen Azil",
        "TryCastCombatSpell(bot, add, 100)",
        '"warrior_charge_healer_swarm_pickup"',
        "Rerun210 proved the complementary native dead zone",
        "bot->GetExactDist(add) > 5.0f",
        "bot->GetExactDist(add) <= 10.0f",
        "bot->HasSpell(46968)",
        "TryCastCombatSpell(bot, add, 46968)",
        '"warrior_shockwave_healer_swarm_gap"',
        "On a multi-target wave, establish area threat before spending",
        "ResolveProfileCombatAction(",
    )
    assert "state.DecisionTimer, 250" in branch
    assert "SetThreat" not in branch
    assert "SetVictim" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun212_density_recovery_admits_single_party_hostile_for_warrior_taunt():
    objective = read(AZIL_ADD_DISCOVERY) + read(AZIL_TANK_THREAT)
    marker = objective.index(
        "Rerun211's final generation retained one Stonecore Bruiser"
    )
    admission = objective[marker - 900 : marker + 5000]
    residual_marker = objective.index(
        "Rerun210's maximum-dwell identity was the one survivor"
    )
    residual = objective[residual_marker - 400 : residual_marker + 7000]

    assert_ordered(
        admission,
        "isUsableUnexpectedPartyHostile(bot, creature)",
        "unexpectedPartyHostiles.push_back(creature)",
        "bool sharedDensityRecoveryActive",
        "Party().ValidationRouteBossAddDensityGeneration",
        "== manager.Party().ValidationRouteGeneration",
        "unexpectedPartyHostiles.size() >= 3",
        "|| sharedDensityRecoveryActive",
        "considerLocalAdd(creature)",
    )
    assert_ordered(
        residual,
        "warriorHealerAttackerCount > 0",
        "warriorHealerAttackerCount < 3",
        "TryCastCombatSpell(bot, warriorResidualHealerAdd, 355)",
        '"warrior_taunt_residual_healer_threat"',
    )
    assert "densityDefenseTarget != densityHealer" not in residual
    correction = admission + residual
    assert "SetThreat" not in correction
    assert "SetVictim" not in correction
    assert "NearTeleportTo" not in correction


def test_rerun201_protection_honors_ready_local_majority_area_before_remote_approach():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun201 proved one exception already encoded by the resolver"
    )
    area = objective[marker - 3200 : marker + 10500]

    assert_ordered(
        area,
        "localProtectionHealerOwnedCount >= 2",
        "localProtectionHealerOwnedCount * 2",
        ">= protectionHealerAttackerCount",
        "preferSelfCenteredProtectionArea",
        "uint32 selfCenteredTargets = 0",
        "bool preferredLocalProtectionAreaReady",
        "preferSelfCenteredProtectionArea",
        "immediateAreaThreat.TargetGuid == bot->GetGUID()",
        "selfCenteredTargets >= 2",
        "bool selfCenteredAreaReady",
        "preferredLocalProtectionAreaReady",
        "|| bot->GetExactDist2d(add) <= 10.0f",
        "if (approach)",
        "MoveBotToProfileRange(state, bot, add, &immediateAreaThreat)",
        "ExecuteProfileCombatAction(",
    )
    assert "TryCastCombatSpell(bot, add, 31935)" in area
    assert "SetThreat" not in area
    assert "SetVictim" not in area
    assert "NearTeleportTo" not in area


def test_rerun201_local_majority_area_keeps_remote_and_non_protection_movement_contracts():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun201 proved one exception already encoded by the resolver"
    )
    area = objective[marker - 1200 : marker + 10500]

    assert "preferSelfCenteredProtectionArea" in area
    assert "preferredLocalProtectionAreaReady" in area
    assert "!densityDefenseTarget" in area
    assert "bot->GetExactDist2d(add) <= 10.0f" in area
    assert "MoveBotToProfileRange(state, bot, add, &immediateAreaThreat)" in area
    assert "preferSelfCenteredProtectionArea);" in area
    assert "SetThreat" not in area
    assert "SetVictim" not in area
    assert "NearTeleportTo" not in area


def test_rerun194_feral_remote_healer_wave_charges_before_local_minority_roar():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun193 completed every strict route objective"
    )
    recovery = objective[marker - 700 : marker + 5200]

    assert "healerOwnedBeforeCharge >= 1" in recovery
    assert "localHealerOwnedBeforeCharge * 2 < healerOwnedBeforeCharge" in recovery
    assert "candidate->GetVictim() != densityHealer" in recovery
    assert "bot->GetExactDist(candidate) <= 8.0f" in recovery
    assert "candidate->GetExactDist2d(neighbor) <= 10.0f" in recovery
    assert_ordered(
        recovery,
        "clusterCount > remoteHealerWaveClusterCount",
        "distance < remoteHealerWaveDistance",
        "guid < remoteHealerWaveGuid",
        "TryCastCombatSpell(bot, remoteHealerWaveChargeTarget, 16979)",
        '"feral_charge_remote_healer_wave_before_roar"',
        "state.FeralChargePickupUntilMs = NowMs() + 2500;",
        "if (localHealerOwnedBeforeCharge >= 2",
        "tryFeralRoarPickup(feralHealerHandoffArrived)",
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetThreat" not in recovery
    assert "SetVictim" not in recovery
    assert "NearTeleportTo" not in recovery


def test_profile_los_failure_is_recorded_before_existing_range_recovery():
    executor = function_body(
        read(BOT_MGR),
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state",
    )
    los = executor.split("SPELL_FAILED_LINE_OF_SIGHT", 1)[1].split(
        "if (state && result == BotActionResult::Ok)", 1
    )[0]

    assert "ProfileCastSuppressedSpellId = action.SpellId" in los
    assert "recoverLineOfSight = true;" in los
    assert_ordered(
        los,
        "RecordCombatAttempt(*state, bot, target",
        "if (recoverLineOfSight && target)",
        "MoveBotToProfileRange(*state, bot, target, &action);",
    )


def test_profile_combat_reconciles_native_position_feedback_before_retrying():
    manager = read(BOT_DIR / "BotWorldPopulationMgrCombatExecution.cpp")
    executor = read(ROOT / "src/server/game/Bots/BotActionExecutor.cpp")
    execute_combat = function_body(
        executor, "BotActionResult BotActionExecutor::ExecuteCombat"
    )
    execute_profile = function_body(
        manager,
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state",
    )
    boss = function_body(
        read(BOSS_MECHANICS),
        "BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics",
    )

    auto_attack = execute_combat.split('if (action.Type == "auto_attack")', 1)[1].split(
        'if (!action.SpellId)', 1
    )[0]
    submit_auto_attack = function_body(
        executor, "BotActionResult BotActionExecutor::SubmitMeleeAutoAttack"
    )
    move_to_range = function_body(
        read(BOT_DIR / "BotWorldPopulationMgrCombatMovement.cpp"),
        "bool BotWorldPopulationMgr::MoveBotToProfileRange",
    )
    assert "SubmitMeleeAutoAttack(bot, target)" in auto_attack
    assert "IsWithinLOSInMap(target)" in submit_auto_attack
    assert "IsWithinMeleeRange(target)" in submit_auto_attack
    assert_ordered(
        submit_auto_attack,
        "IsWithinLOSInMap(target)",
        "IsWithinMeleeRange(target)",
        "bot->Attack(target, true)",
        "if (!inLineOfSight)",
        "if (!inMeleeRange)",
    )
    assert "bot->GetVictim() == target" in submit_auto_attack
    assert "if (!attackBound)" in submit_auto_attack
    assert "return BotActionResult::NoLineOfSight" in submit_auto_attack
    assert "return BotActionResult::OutOfRange" in submit_auto_attack
    assert 'action->AutoAttackMode == "melee"' in move_to_range
    assert "SubmitMeleeAutoAttackIntent(state," in move_to_range
    assert "BotMeleeAutoAttack::Kind::StartOrSwitch" in move_to_range
    assert '"profile_move_to_melee_range"' in move_to_range
    assert "AttackStop" not in move_to_range

    assert "result == BotActionResult::OutOfRange" in execute_profile
    assert "result == BotActionResult::NoLineOfSight" in execute_profile
    assert "MoveBotToProfileRange(*state, bot, target, &action" in execute_profile
    assert '"native_position_reconciled"' in execute_profile
    assert '"position_reconcile"' in execute_profile
    assert '"native_out_of_range"' in execute_profile
    assert_ordered(
        execute_profile,
        "executor.ExecuteCombat(bot, bot, action)",
        "result == BotActionResult::OutOfRange",
        "MoveBotToProfileRange(*state, bot, target, &action",
        '"native_position_reconciled"',
    )

    assert 'result.Action = "move_to_boss_action_range"' in boss
    assert "nativeCombatObserved" in boss
    assert "if (!state.WasInCombat && nativeCombatObserved)" in boss
    assert "state.WasInCombat = nativeCombatObserved;" in boss

    fallback = read(BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp")
    assert_ordered(
        fallback,
        "if (routeAttempt->MovementSubmitted)",
        "routeAttempt->RouteOutcome =",
        "BotActionArbitration::Outcome::Started(",
        '"route_movement_submitted");',
    )
    assert '"route_native_combat_observed"' in fallback
    assert '"route_combat_submitted"' in fallback


def test_combat_keeps_high_priority_movement_and_selects_instant_dps():
    manager = read(BOT_MGR)
    resolver = function_body(
        manager, "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction"
    )
    execute_profile = function_body(
        manager,
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state",
    )

    assert "movementCompatibleOnly" in resolver
    assert "candidateSpellInfo->CalcCastTime(bot->getLevel()) > 0" in resolver
    assert "candidateSpellInfo->IsChanneled()" in resolver
    assert 'candidate.RejectReason = "movement_requires_instant_action";' in resolver
    assert "state->MovementLease.ExpiresAtMs > nowMs" in execute_profile
    assert "BotMovementArbitration::Priority::Combat" in execute_profile
    assert_ordered(
        execute_profile,
        "bool const movementCompatibleOnly",
        "ResolveProfileCombatAction(",
        "hostileTargetOnly, movementCompatibleOnly",
    )
    assert 'Outcome::Selected("profile_action_valid")' in execute_profile


def test_native_self_resurrection_uses_only_the_player_spell_cast_path():
    mgr = read(BOT_MGR)
    update = read(UPDATE_BOT_DEATH)
    self_res = function_body(read(BOT_DIR / "BotWorldPopulationMgrCombatSupport.cpp"), "bool BotWorldPopulationMgr::TryNativeSelfResurrection")

    assert "TryNativeSelfResurrection(state, bot)" in update
    assert "PLAYER_SELF_RES_SPELL" in self_res
    assert "SPELL_EFFECT_SELF_RESURRECT" in self_res
    assert "bot->CastSpell(bot, spellId, false)" in self_res
    assert "ResurrectPlayer" not in self_res
    assert "native_self_resurrection_submitted" in self_res


def test_validation_route_high_density_adds_pull_the_tank_into_the_swarm_and_fail_closed_to_density_contract():
    mgr = read(BOT_MGR)
    objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    adds = read(AZIL_ADD_WAVE_FAMILY)
    density_resolution = read(
        _AZIL_DIR / "HighPriestessAzilDensityCombatResolution.cpp"
    )
    reset = function_body(mgr, "void BotWorldPopulationMgr::ResetValidationRouteRuntimeState")
    density_reset = function_body(mgr, "void BotWorldPopulationMgr::ResetValidationRouteBossAddDensityState")

    assert "addX += creature->GetPositionX();" in adds
    assert "addY += creature->GetPositionY();" in adds
    assert 'bool observedBossEngagement = manager.Cohort().Config.ValidationRouteKind == "boss"' in adds
    assert "!manager.Party().ValidationRouteBossProgressTargetGuid.IsEmpty()" in adds
    assert "ObjectAccessor::GetUnit(*bot,\n            manager.Party().ValidationRouteBossProgressTargetGuid)" in adds
    assert "bool routeBossUnavailable = !routeBoss" in adds
    assert "manager.Party().ValidationRouteBossAddDensityGeneration =\n            manager.Party().ValidationRouteGeneration;" in adds
    assert "manager.Party().ValidationRouteBossAddDensityGeneration\n                != manager.Party().ValidationRouteGeneration" in adds
    assert "Party().ValidationRouteBossAddDensityPhase && routeBossAttackable" in adds
    assert "ResetValidationRouteBossAddDensityState();" in reset
    assert "Party().ValidationRouteBossAddDensityPhase = false;" in density_reset
    assert "Party().ValidationRouteBossAddDensityGeneration = 0;" in density_reset
    killed_focus = function_body(
        mgr, "void BotWorldPopulationMgr::ClearValidationRouteKilledFocus"
    )
    assert "if (Party().ValidationRouteBossProgressTargetGuid == killedGuid)" in killed_focus
    assert "ResetValidationRouteBossAddDensityState();" in killed_focus
    assert '\\"boss_add_density_phase\\"' in mgr
    assert '\\"boss_add_density_generation\\"' in mgr
    assert "profile.MovementDirective != \"melee\"" in adds
    assert "float centroidDistance = densityTank->GetExactDist2d(centroidX, centroidY);" in adds
    assert "MoveBotToPoint(state, densityTank, centroidX, centroidY, centroidZ)" in adds
    assert 'moved ? "tank_move_to_add_centroid" : "tank_add_centroid_path_rejected"' in adds
    assert 'escapeIssued ? "reissue_shared_escape_unreached" : "move_to_shared_escape"' in adds
    assert "densityAreaPhase ? addCount : 0, densityAreaPhase" in adds
    assert "ExecuteProfileCombatAction(&state, bot, add, &profileAction, addCount, true)" in adds
    assert "++densityTankOwnedAddCount;" in adds
    assert "densityTankOwnedAddCount * 10 >= addCount * 8" in adds
    assert "bool urgentSwarmDamageRelease = cohortSwarmActive && addCount >= 24" in adds
    assert "bool dpsSwarmDamageRelease = densityTankOwnsSecureMajority\n        || urgentSwarmDamageRelease;" in adds
    assert "!dpsSwarmDamageRelease && observedListedAttackerCount(bot)" in adds
    assert '"tank_swarm_defensive"' in adds
    assert "std::array<uint32, 3>{ 86150, 31850, 498 }" in adds
    assert 'RecordEvent(state, bot, "boss_add_density", add, "no_legal_density_action"' in adds
    assert_ordered(
        adds,
        "bool densitySingleTargetFallback = densityAreaPhase && !profileAction.Valid",
        "profileAction = manager.ResolveProfileCombatAction(bot, add);",
        '"single_target_fallback_selected"',
        '"focused_attack_boss_add_density"',
    )
    assert 'densityGenerator ? "resource_generator_selected" : "area_action_selected"' in adds
    assert 'densityGenerator ? "generate_resource_boss_add_density"' in adds
    assert 'action = "hold_boss_add_density";' in adds
    assert_ordered(adds, "request.TryRouteGroupHeal(bot, add)", "move_to_shared_escape", 'if (role == "healer")', "no_legal_density_action")
    assert "43438" not in adds
    assert "43917" not in adds

    density_branch = density_resolution[
        density_resolution.index("if (densityAreaPhase)") :
    ]
    assert "executor.Pull" not in density_branch


def test_validation_route_ground_danger_dodge_is_reserved_per_cast_window():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    movement = read(VALIDATION_ROUTE_MOVEMENT_FAMILY)

    assert "ValidationRouteDodgeCasterGuid" in header
    assert "ValidationRouteDodgeSpellId" in header
    assert "ValidationRouteDodgeUntilMs" in header
    assert "state.ValidationRouteDodgeCasterGuid == caster->GetGUID()" in movement
    assert "state.ValidationRouteDodgeSpellId == castSpell->Id" in movement
    assert "state.ValidationRouteDodgeUntilMs > nowMs" in movement
    assert "state.ValidationRouteDodgeUntilMs = nowMs + (moved ? 3000 : 500);" in movement
    assert 'configuredHazardShape == "frontal_cone"' in movement
    assert "dodgeOrigin->GetOrientation() + side * float(M_PI_2)" in movement
    assert_ordered(movement, "ValidationRouteDodgeUntilMs > nowMs", "MoveBotToPoint", "ValidationRouteDodgeUntilMs = nowMs")


def test_density_action_anchor_is_local_range_compatible_and_not_shared_cleanup_focus():
    adds = read(AZIL_ADD_WAVE_FAMILY)

    assert "std::vector<Creature*> const& localAdds = discovery.LocalAdds;" in adds
    assert "if (highDensityPhase && role != \"healer\")" in adds
    assert "for (Creature* candidate : localAdds)" in adds
    assert 'profile.MovementDirective == "melee"' in adds
    assert "distance < minRange" in adds
    assert "distance > maxRange" in adds
    assert "if (!densityAnchor || distance < bestDistance\n                || (distance == bestDistance && guid < bestAnchorGuid))" in adds
    assert "if (!densityApproachAnchor || distance < nearestDistance\n                || (distance == nearestDistance && guid < nearestAnchorGuid))" in adds
    assert "add = densityAnchor;" in adds
    assert "sharedFocusValid = false;" in adds
    assert "if (!highDensityPhase && !sharedFocusValid)" in adds
    assert '"no_compatible_density_anchor"' in adds
    assert "ResolvedCombatAction approachAction;" in adds
    assert "approachAction.MinRange = profile.MinRange;" in adds
    assert "approachAction.MaxRange = profile.MaxRange;" in adds
    assert "MoveBotToProfileRange(state, bot, densityApproachAnchor, &approachAction)" in adds
    assert '"approach_density_anchor"' in adds
    approach_block = adds[adds.index("if (highDensityPhase && !add && densityApproachAnchor)"):adds.index("if (!add)", adds.index("if (highDensityPhase && !add && densityApproachAnchor)"))]
    assert "executor.Pull" not in approach_block
    assert_ordered(adds, "add = densityAnchor;", "if (!highDensityPhase && !sharedFocusValid)")


def test_inactive_density_without_listed_add_does_not_consume_boss_activation_handler():
    adds = read(AZIL_ADD_WAVE_FAMILY)
    no_add = adds[adds.index("if (!add)", adds.index("approach_density_anchor")):adds.index("if (!highDensityPhase && !sharedFocusValid)")]

    assert_ordered(no_add, "if (!highDensityPhase)", "return false;", '"no_compatible_density_anchor"', "return true;")
    assert "if (highDensityPhase && !add && densityApproachAnchor)" in adds
    assert '"approach_density_anchor"' in adds
    assert '"no_compatible_density_anchor"' in no_add


def test_density_tank_centroid_control_prioritizes_loose_healer_targets():
    mgr = read(BOT_MGR)
    adds = read(AZIL_ADD_WAVE_FAMILY)
    assert "Player* densityTank = nullptr;" in adds
    assert "Player* densityHealer = nullptr;" in adds
    assert 'uint8 priority = victimRole == "healer" ? 3 : 2;' in adds
    assert "add = looseAdd ? looseAdd : densityAnchor;" in adds
    assert "highDensityPhase && bot == densityTank && addCount >= 3" in adds
    assert "&& !densityDefenseTarget" in adds
    assert "float centroidX = addX / float(addCount);" in adds
    assert "float centroidY = addY / float(addCount);" in adds
    assert "centroidDistance > 4.0f" in adds
    assert "MoveBotToPoint(state, densityTank, centroidX, centroidY, centroidZ)" in adds
    assert 'action = moved ? "tank_move_to_add_centroid" : "hold_tank_add_centroid";' in adds
    assert '"dps_stack_for_add_pickup"' in adds
    assert "densityDefenseTarget == bot && densityTank" not in adds
    assert 'role == "dps" && densityTank && !dpsSwarmDamageRelease && observedListedAttackerCount(bot)' in adds
    assert 'if (memberRole == "tank" || !attackerCount)' in adds
    assert "nearestAttacker->GetAngle(densityTank) - densityTank->GetOrientation()" in adds
    assert "densityTank->GetFirstCollisionPosition(4.0f" in adds
    assert "bool swarmDefenseActive = highDensityPhase || cohortSwarmActive\n        || sharedLargePassiveSwarmStaging;" in adds
    assert "if (swarmDefenseActive)" in adds
    assert "size_t defenseScore = attackerCount\n                + (memberRole == \"healer\" ? 3 : 0);" in adds
    assert '"dps_stack_for_swarm_pickup"' in adds
    assert '"dps_wait_for_swarm_tank_ownership"' in adds
    assert "uint32 densityTankSecureAddCount = 0;" in adds
    assert "densityTankSecureAddCount * 10 >= addCount * 9" in adds
    assert "if (tankThreat >= 2000.0f\n                    && tankThreat >= highestPartyThreat * 2.5f)" in adds
    assert '"swarm_pickup_emergency_defensive"' in adds
    assert 'bool tankSwarmAreaPhase = role == "tank" && cohortSwarmActive;' in adds
    assert 'bool secureSwarmAreaPhase = role == "dps" && cohortSwarmActive' in adds
    assert "dpsSwarmDamageRelease || hunterMisdirectionActive" in adds
    assert "bool densityAreaPhase = highDensityPhase || tankSwarmAreaPhase || secureSwarmAreaPhase;" in adds
    assert "bot->GetExactDist2d(densityTank) <= 8.0f" in adds
    assert "(observedListedAttackerCount(bot) && !botInsideTankPickup)" in adds
    assert "bot->GetExactDist2d(densityTank) > 8.0f" not in adds
    assert '"consecration_party_pickup"' in adds
    assert "if (highDensityPhase && role == \"healer\" && request.TryRouteGroupHeal(bot, add))" in adds
    assert_ordered(adds, "add = looseAdd ? looseAdd : densityAnchor;", "misdirection_to_tank", "tank_move_to_add_centroid")


def test_shared_density_latch_uses_cohort_observation_before_swarm_end_clear():
    adds = read(AZIL_ADD_WAVE_FAMILY)

    assert "GuidSet& cohortAddGuids = result.CohortAddGuids;" in adds
    assert "if (manager.Party().ValidationRouteBossAddDensityPhase && addCount < 3)" in adds
    assert "for (BotWorldPopulationMgrBotState::WorldBotState const& cohortState\n            : manager.Party().Bots)" in adds
    assert "Player* observer = manager.GetLoadedBot(cohortState);" in adds
    assert "cohortAddGuids.insert(creature->GetGUID());" in adds
    assert "result.CohortSwarmActive = cohortAddGuids.size() >= 3;" in adds
    assert "|| !cohortSwarmActive" in adds
    assert "|| addCount < 3" not in adds
    assert_ordered(
        adds,
        "if (manager.Party().ValidationRouteBossAddDensityPhase && addCount < 3)",
        "result.CohortSwarmActive = cohortAddGuids.size() >= 3;",
        "|| !cohortSwarmActive",
    )


def test_density_action_taxonomy_and_stonecore_roster_profile_paths_are_explicit():
    catalog_header = read(ROOT / "src/server/game/Bots/BotCombatActionCatalog.h")
    catalog = read(ROOT / "src/server/game/Bots/BotCombatActionCatalog.cpp")
    profiles = read(STONECORE_ROTATION_SQL)

    assert_ordered(catalog_header, "ProfessionAction,", "ResourceGenerator")
    assert 'case BotCombatActionCategory::ResourceGenerator: return "resource_generator";' in catalog
    assert 'MAP_CATEGORY("resource_generator", ResourceGenerator);' in catalog
    assert "hammer_of_the_righteous,aoe,holy_power,threat" in profiles
    assert "multi_shot,aoe" in profiles
    assert "flamestrike,aoe" in profiles
    assert "chain_lightning,maelstrom_5,aoe" in profiles
    assert "'resource_generator', 'steady_shot,focus_builder'" in profiles
    assert "'resource_generator', 'stormstrike,melee,maelstrom_generator'" in profiles


def test_healer_lifecycle_telemetry_is_cast_scoped_and_uses_actual_heal_info():
    root = Path(__file__).resolve().parents[1]
    header = read(BOT_MGR_HEADER)
    manager = read(BOT_MGR)
    unit = (root / "src/server/game/Entities/Unit/Unit.cpp").read_text()
    spell = (root / "src/server/game/Spells/Spell.cpp").read_text()
    controller = read(PLAYER_BOT_CONTROLLER)

    assert "struct PendingHealCast" in header
    assert "uint64 CastId" in header
    assert "std::set<uint64> AffectedAllyGuids" in header
    assert "uint64 pendingCastId = BeginPendingHealCast(bot, target, spellId);\n    SpellCastResult castResult" in manager
    assert 'bot_healing_lifecycle_v1' in manager
    for field in ("attempted_heal", "effective_heal", "overheal", "mana_delta",
                  "affected_ally_count", "attackers_before", "attackers_after",
                  "threat_before", "threat_after", "candidate_mask", "chosen_action"):
        assert field in manager
    assert "NotifyBotHeal(healer, victim, healInfo.GetSpellInfo()->Id," in unit
    assert "addhealth + healInfo.GetAbsorb(), effectiveHeal, healInfo.GetAbsorb())" in unit
    assert "NotifyBotSpellFinished(playerCaster, m_spellInfo->Id, ok)" in spell
    assert "NotifyBotSpellStarted(bot, lifecycleTarget, attempt.Spell->SpellId, candidateMaskJson, chosenActionJson)" in controller
    assert "CancelBotSpellStart(pendingCastId, bot, ToString(result))" in controller
    assert '"completed"' in manager and '"interrupted"' in manager and '"timeout"' in manager
    assert 'CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events' in manager
    assert 'ClearPendingHealCasts("run_stop")' in manager
    assert 'ClearPendingHealCasts("autonomy_stop")' in manager
    assert 'ClearPendingHealCasts("shutdown")' in manager
    assert "ManaAfterCast = caster->GetPower(POWER_MANA)" in manager
    assert "AttackersAfterCast" in manager and "ThreatAfterCast" in manager
    assert "absorbed_heal" in manager
    assert "no_matching_cast_window" in manager
    assert '_lastHealerCandidateMaskJson = "{}"' in controller
    assert '_lastHealerChosenActionJson = "{}"' in controller


def test_healer_candidate_mask_is_db_driven_and_records_rejections():
    root = Path(__file__).resolve().parents[1]
    profile = read_profile_sources()
    manager = read(BOT_MGR)

    assert '\\"valid\\":" << (candidate.RejectReason.empty() ? "true" : "false")' in profile
    assert 'candidate.RejectReason = allyTarget ? "missing_ally_target" : "missing_enemy_target"' in profile
    assert "BotClassSpecActionProfileStore::Build(bot, role.c_str())" in manager
    assert "candidate.Profile.InjuredHealthPct" in manager
    assert 'candidate.RejectReason = "not_healing_action"' in manager
    assert "return best ? best->SpellId : 0;" in manager


def test_rerun145_protection_pickup_and_passive_swarm_repairs_are_bounded():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)

    assert '"consecration_healer_multi_trash_pickup"' in manager
    multi_consecration = manager.index('"consecration_healer_multi_trash_pickup"')
    ordinary_righteous_defense = manager.index(
        '"righteous_defense_healer_pickup"', multi_consecration
    )
    assert multi_consecration < ordinary_righteous_defense
    assert "defenseAttackerCount >= 2" in manager[
        multi_consecration - 1200 : multi_consecration
    ]
    assert "bot->GetExactDist2d(defenseTarget) <= 8.0f" in manager[
        multi_consecration - 1200 : multi_consecration
    ]

    assert "engagedAddCount == 0 && passiveSwarmClusterAnchor" in manager
    assert "BotMeleeAutoAttack::Kind::StartOrSwitch" in manager
    assert "ResolveAndReconcileMeleeAutoAttack(state, bot);" in manager
    assert '"tank_activate_passive_swarm"' in manager


def test_rerun151_protection_remote_healer_cluster_uses_native_ranged_pickup():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)

    ranged_pickup = manager.index(
        '"avengers_shield_healer_multi_trash_pickup"'
    )
    ordinary_salvation = manager.index(
        '"hand_of_salvation_healer_trash_threat_drop"', ranged_pickup
    )
    ordinary_righteous_defense = manager.rindex(
        '"righteous_defense_healer_pickup"', 0, ranged_pickup
    )
    branch = manager[ranged_pickup - 2400 : ranged_pickup + 800]

    assert ordinary_righteous_defense < ranged_pickup < ordinary_salvation
    assert "defenseAttackerCount >= 2" in branch
    assert "bot->HasSpell(31935)" in branch
    assert "TryCastCombatSpell(bot, healerClusterTarget, 31935)" in branch
    assert "defenseTarget->getAttackers()" in branch
    assert "distance < healerClusterDistance" in branch
    assert "guid < healerClusterGuid" in branch


def test_rerun162_protection_retention_and_passive_swarm_fallback_are_bounded():
    root = Path(__file__).resolve().parents[1]
    boss_source = read(AZIL_TANK_PREPARATION)
    trash_source = read(TRASH_INTERVENTION)
    passive_source = read(AZIL_PASSIVE_SWARM)

    boss_marker = boss_source.index(
        "Rerun162 proved the same bounded Protection pickup cadence"
    )
    boss_branch = boss_source[boss_marker : boss_marker + 1800]
    assert 'role == "tank" && profile.SpecTag == "protection"' in boss_branch
    assert 'profile.SpecTag == "protection_paladin"' not in boss_branch
    assert "&& densityHealer" in boss_branch
    assert "cohortSwarmActive && densityHealer" not in boss_branch
    assert "engagedAddCount >= 12" in boss_branch
    assert "observedListedAttackerCount(densityHealer) >= 2" in boss_branch
    assert "state.DecisionTimer = std::min<uint32>(\n            state.DecisionTimer, 250);" in boss_branch

    trash_marker = trash_source.index(
        "Rerun153 proved the reactive cadence from rerun152"
    )
    trash_branch = trash_source[trash_marker : trash_marker + 1900]
    assert "protectionMultiHostileRetention" in trash_branch
    assert "trashThreatControl.EngagedCount >= 3" in trash_branch
    assert "trashThreatControl.TankOwnsTrashMajority" in trash_branch
    assert "protectionMultiHostileHealerPickup" in trash_branch
    assert "bot->getClass() == CLASS_PALADIN" in trash_branch
    assert 'std::string(GetDungeonRole(defenseTarget)) == "healer"' in trash_branch
    assert "defenseAttackerCount >= 2" in trash_branch
    assert "state.DecisionTimer = std::min<uint32>(\n                state.DecisionTimer, 250);" in trash_branch
    ordered_trash = trash_source + read(TANK_TRASH_RECOVERY)
    assert trash_marker < ordered_trash.index(
        '"consecration_healer_multi_trash_pickup"', trash_marker
    )

    passive_marker = passive_source.index(
        "Rerun153 reached the passive anchor but had no line of sight"
    )
    passive_branch = passive_source[passive_marker - 2600 : passive_marker + 1500]
    assert "bot->IsWithinLOSInMap(passiveSwarmClusterAnchor)" in passive_branch
    assert "passiveSwarmActivationNotActionable" in passive_branch
    assert "pendingSwarmActivation" in passive_branch
    assert "!passiveSwarmActivationNotActionable" in passive_branch


def test_rerun162_post_death_safe_anchor_uses_route_movement_z_contract():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)

    marker = manager.index(
        "Rerun162 selected a remembered post-death anchor"
    )
    branch = manager[marker : marker + 1600]
    assert "safeMap->GetHeight(bot->GetPhaseShift(), safe.X, safe.Y" in branch
    assert "safeFloorZ <= INVALID_HEIGHT" in branch
    assert "std::fabs(safeFloorZ - safe.Z) > 4.0f" in branch
    assert branch.index("std::fabs(safeFloorZ - safe.Z) > 4.0f") < branch.index(
        "float safeDanger = GetLocalDangerScore"
    )


def test_rerun154_feral_high_density_charge_reselects_remote_wave_target():
    root = Path(__file__).resolve().parents[1]
    manager = read(AZIL_FERAL_REMOTE)

    marker = manager.index(
        "Rerun154 exposed a declared 20-follower wave"
    )
    branch = manager[marker - 500 : marker + 4300]
    assert "feralChargeProtectsHighDensityParty = engagedAddCount >= 12" in branch
    assert "observedListedAttackerCount(densityHealer) == 0" in branch
    assert "Unit* feralChargeTarget = add;" in branch
    assert "bot->GetExactDist(feralChargeTarget) <= 8.0f" in branch
    assert "candidate->GetVictim() == bot" in branch
    assert 'GetDungeonRole(candidateVictim)) == "tank"' in branch
    assert "bot->GetExactDist(candidate) <= 8.0f" in branch
    assert "distance < remoteChargeDistance" in branch
    assert "guid < remoteChargeGuid" in branch
    assert "TryCastCombatSpell(bot, feralChargeTarget, 16979)" in branch
    assert "state.FeralChargePickupTargetGuid = feralChargeTarget->GetGUID();" in branch
    assert "state.FeralChargePickupUntilMs = NowMs() + 2500;" in branch
    assert "state.DecisionTimer = std::min<uint32>(\n            state.DecisionTimer, 250);" in branch
    assert_ordered(
        branch,
        "Unit* feralChargeTarget = add;",
        "for (Creature* candidate : localAdds)",
        "if (remoteChargeTarget)",
        "TryCastCombatSpell(bot, feralChargeTarget, 16979)",
        "state.FeralChargePickupTargetGuid = feralChargeTarget->GetGUID();",
    )


def test_rerun155_current_healer_threat_preempts_feral_secure_margin_approach():
    root = Path(__file__).resolve().parents[1]
    manager = read(TRASH_INTERVENTION)

    marker = manager.index(
        "Rerun155 recovered one of three healer-owned Flayers"
    )
    branch = manager[marker - 2100 : marker + 3000]
    assert "bool feralCurrentHealerThreat = defenseTarget" in branch
    assert 'std::string(GetDungeonRole(defenseTarget)) == "healer"' in branch
    assert "defenseAttackerCount >= 1" in branch
    assert "bool feralHealerHandoffPending = feralCurrentHealerThreat" in branch
    assert "trashThreatControl.TankOwnsTrashMajority" in branch
    assert "trashThreatControl.InsecureTrashSwarm" in branch
    assert "&& !feralHealerHandoffPending" in branch
    assert "&& !feralCurrentHealerThreat" in branch
    assert_ordered(
        branch,
        "bool feralCurrentHealerThreat = defenseTarget",
        "bool feralHealerHandoffPending = feralCurrentHealerThreat",
        "Rerun155 recovered one of three healer-owned Flayers",
        "&& !feralHealerHandoffPending",
        "&& !feralCurrentHealerThreat",
        '"feral_approach_insecure_trash_threat_cluster"',
    )


def test_rerun156_active_feral_wave_preempts_pending_swarm_preposition():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)

    marker = manager.index(
        "Rerun156 exposed a declared 60-follower Feral wave"
    )
    branch = manager[marker - 500 : marker + 1900]
    assert "feralActiveWavePreemptsPendingSwarmPickup" in branch
    assert 'profile.SpecTag == "feral_druid_tank"' in branch
    assert "engagedAddCount >= 12" in branch
    assert "densityHealer" in branch
    assert "observedListedAttackerCount(densityHealer) == 0" in branch
    assert "state.TankPendingSwarmPickupAnchorGuid.Clear();" in branch
    assert "state.TankPendingSwarmPickupUntilMs = 0;" in branch
    assert "state.TankPendingSwarmPickupEngagedHandoff = false;" in branch
    assert "tankPendingSwarmPickup = false;" in branch
    assert "pendingSwarmPickupAnchor = nullptr;" in branch
    assert_ordered(
        manager,
        "bool feralActiveWavePreemptsPendingSwarmPickup",
        "if (feralActiveWavePreemptsPendingSwarmPickup)",
        "if (tankPendingSwarmPickup && pendingSwarmPickupAnchor",
        "bool feralChargeProtectsHighDensityParty = engagedAddCount >= 12",
    )


def test_rerun156_boss_handoff_rebinds_within_original_healer_cluster():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)

    marker = manager.index(
        "Rerun156 proved the boss handoff discarded a still-valid Azil"
    )
    branch = manager[marker - 300 : marker + 4300]
    assert "state.FeralHealerThreatHandoffRemoteCluster" in branch
    assert "feralHealerHandoffAnchor->GetVictim() != densityHealer" in branch
    assert "for (Creature* candidate : localAdds)" in branch
    assert "candidate->GetVictim() == densityHealer" in branch
    assert "bot->IsValidAttackTarget(candidate)" in branch
    assert "feralHealerHandoffAnchor->GetExactDist2d(candidate)" in branch
    assert "<= 10.0f" in branch
    assert "candidate->GetGUID().GetCounter() < reboundGuid" in branch
    assert "state.FeralHealerThreatHandoffAnchorGuid =" in branch
    assert "feralHealerHandoffAnchor = reboundAnchor;" in branch
    assert "FeralHealerThreatHandoffUntilMs =" not in branch
    assert_ordered(
        branch,
        "if (state.FeralHealerThreatHandoffRemoteCluster",
        "for (Creature* candidate : localAdds)",
        "state.FeralHealerThreatHandoffAnchorGuid =",
        "bool feralHealerRemoteHandoffValid",
    )


def test_rerun164_failed_single_healer_growl_rebinds_generic_fallback():
    manager = read(BOT_MGR)
    marker = manager.index(
        "Rerun164 recovered the first of two Azil followers with Growl"
    )
    branch = manager[marker - 3400 : marker + 900]

    assert "observedListedAttackerCount(densityHealer) == 1" in branch
    assert "TryCastCombatSpell(bot, healerOwnedAdd, 6795)" in branch
    assert 'action = "feral_growl_lingering_healer_swarm_attacker";' in branch
    assert "if (healerOwnedAdd)" in branch
    assert "add = healerOwnedAdd;" in branch
    assert "sharedFocusValid = false;" in branch
    assert_ordered(
        branch,
        "TryCastCombatSpell(bot, healerOwnedAdd, 6795)",
        'action = "feral_growl_lingering_healer_swarm_attacker";',
        "return true;",
        "Rerun164 recovered the first of two Azil followers with Growl",
        "add = healerOwnedAdd;",
        "sharedFocusValid = false;",
    )


def test_rerun165_density_resolver_rejects_buff_without_removing_recovery_fallbacks():
    manager = read(BOT_MGR)
    resolver = function_body(
        manager,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    marker = resolver.index(
        "Rerun165 canary 3 captured a Protection tank owning all 49 Azil"
    )
    branch = resolver[marker - 650 : marker + 850]

    assert "densityOnly && candidate.Category == BotCombatActionCategory::Buff" in branch
    assert 'candidate.RejectReason = "density_buff_not_actionable";' in branch
    assert "BotCombatActionCategory::Defensive" not in branch
    assert "BotCombatActionCategory::ResourceGenerator" not in branch
    assert_ordered(
        branch,
        "if (densityOnly && candidate.Category == BotCombatActionCategory::Buff)",
        "SpellInfo const* candidateSpellInfo",
    )
    assert "bestDensityRecovery" in resolver
    assert "bestDensityResourceFallback" in resolver
    assert "bestDensityGenerator" in resolver


def test_rerun169_melee_fallback_exposes_native_range_to_movement_callers():
    manager = read(BOT_MGR)
    resolver = function_body(
        manager,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    marker = resolver.index(
        "Rerun169 canary 3 reached a remote healer-owned cluster"
    )
    branch = resolver[marker - 300 : marker + 1000]

    assert 'action.DebugName = "melee_auto_attack_fallback";' in branch
    assert "action.MinRange = 0.0f;" in branch
    assert "action.MaxRange = std::max(5.0f, bot->GetMeleeRange(target));" in branch
    assert_ordered(
        branch,
        'profile.AutoAttackMode == "melee"',
        'action.DebugName = "melee_auto_attack_fallback";',
        "action.MinRange = 0.0f;",
        "action.MaxRange = std::max(5.0f, bot->GetMeleeRange(target));",
    )


def test_rerun170_defers_passive_azil_followers_until_route_arrival():
    route = read(AZIL_ADD_DENSITY)
    marker = route.index(
        "Rerun170 reached Azil's route generation roughly 80-115 yards"
    )
    branch = route[marker - 500 : marker + 2300]

    assert "addCount > 0 && engagedAddCount == 0" in branch
    assert "Party().ValidationRouteBossProgressTargetGuid.IsEmpty()" in branch
    assert "request.CanonicalRouteDistance > request.RouteArrivalRadius" in branch
    assert_ordered(
        branch,
        "bool sharedLargePassiveSwarmStaging =",
        "addCount > 0 && engagedAddCount == 0",
        "request.CanonicalRouteDistance > request.RouteArrivalRadius",
        "result.BypassPreArrival = true;",
        "return result;",
        "manager.Party().ValidationRouteBossAddDensityPhase",
    )


def test_rerun197_passive_listed_adds_cannot_own_generic_boss_focus():
    objective = read(TARGETING)
    marker = objective.index("bool unengagedListedBossAdd =")
    branch = objective[marker - 300 : marker + 1900]

    assert_ordered(
        branch,
        "bool unengagedListedBossAdd =",
        "ValidationRouteAddTargetEntries.begin()",
        "!candidate->IsInCombat() && !candidate->GetVictim()",
        "if (unengagedListedBossAdd)",
        "return nullptr;",
        "if (isValidationRouteCombatTarget(creature))",
    )
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun197_feral_majority_healer_flip_uses_bounded_native_fade():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun196 then captured a distinct Feral"
    )
    branch = objective[marker - 900 : marker + 2600]

    assert_ordered(
        branch,
        "bool feralDruidMajorityHealerThreat =",
        "trashThreatControl.Tank->getClass() == CLASS_DRUID",
        "trashThreatControl.HealerTargetCount >= 4",
        "trashThreatControl.HealerTargetCount * 5",
        ">= trashThreatControl.EngagedCount * 4",
        "|| feralDruidMajorityHealerThreat",
        "state.DecisionTimer, 250",
        "TryCastFriendlySpell(bot, bot, 586)",
        '"fade_early_trash_swarm_threat_drop"',
    )
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun170_protection_healer_pickup_and_approach_use_urgent_cadence():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    taunt_marker = route.index(
        "Rerun170 retained 17 eligible healer-target samples"
    )
    taunt_branch = route[taunt_marker - 500 : taunt_marker + 3800]
    move_marker = route.index(
        "Rerun170's longest Protection exposure began with three"
    )
    move_branch = route[move_marker - 500 : move_marker + 1300]

    assert "isProtectionProfile()" in taunt_branch
    assert "defenseAttackerCount >= 1" in taunt_branch
    assert "bot->HasSpell(62124)" in taunt_branch
    assert "TryCastCombatSpell(bot, healerTauntTarget, 62124)" in taunt_branch
    assert '"hand_of_reckoning_healer_trash_pickup"' in taunt_branch
    assert "state.DecisionTimer, 250);" in taunt_branch
    assert_ordered(
        taunt_branch,
        "Righteous Defense was unavailable",
        "for (Unit* attacker : defenseTarget->getAttackers())",
        "TryCastCombatSpell(bot, healerTauntTarget, 62124)",
        "state.DecisionTimer, 250);",
        "Rerun151 localized Protection's remaining healer exposure",
    )

    assert "isProtectionProfile()" in move_branch
    assert "target->GetVictim()->ToPlayer()" in move_branch
    assert 'std::string(GetDungeonRole(areaVictim)) == "healer"' in move_branch
    assert "state.DecisionTimer = std::min<uint32>(" in move_branch
    assert "state.DecisionTimer, 250);" in move_branch
    assert_ordered(
        move_branch,
        "MoveBotToProfileRange(state, bot, target, &areaAction)",
        "isProtectionProfile()",
        'GetDungeonRole(areaVictim)) == "healer"',
        "state.DecisionTimer, 250);",
        'action = moved ? "move_to_trash_density"',
    )


def test_rerun157_preserves_global_cooldown_scheduling_identity():
    manager = read(BOT_MGR)
    resolver = function_body(
        manager,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    executor = function_body(
        manager,
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction",
    )

    assert 'candidate.RejectReason == "global_cooldown"' in resolver
    assert 'globalCooldownSchedulingWait ? "global_cooldown"' in resolver
    assert 'action.DebugName == "global_cooldown"' in executor
    assert "BotActionResult::GlobalCooldown : BotActionResult::NoAction" in executor
    assert "RecordCombatAttempt(*state, bot, target, \"profile_resolve\", &action," in executor
    assert "return invalidResult;" in executor


def test_rerun157_closes_control_race_and_retains_protection_threat_gates():
    manager = read(BOT_MGR)
    action_executor = read(ROOT / "src/server/game/Bots/BotActionExecutor.cpp")
    hostile_check = function_body(
        action_executor,
        "BotActionResult BotActionExecutor::CheckHostileSpell",
    )

    assert "bot->HasUnitState(UNIT_STATE_CONTROLLED)" in hostile_check
    assert "return BotActionResult::Throttled;" in hostile_check
    assert "bool urgentSwarmDamageRelease = cohortSwarmActive && addCount >= 24" in manager
    marker = manager.index("Rerun157 localized 28 of 37 Protection")
    branch = manager[marker : manager.index(
        "Rerun145 localized Protection's only healer exposure", marker
    )]
    assert 'std::string(GetDungeonRole(defenseTarget)) == "healer"' in branch
    assert "defenseAttackerCount >= 1" in branch
    assert "bot->HasSpell(1022)" in branch
    assert "!defenseTarget->HasAura(1022)" in branch
    assert "TryCastFriendlySpell(bot, defenseTarget, 1022)" in branch
    assert '"hand_of_protection_healer_trash_emergency"' in branch
    assert_ordered(
        manager,
        "Rerun157 localized 28 of 37 Protection",
        '"hand_of_protection_healer_trash_emergency"',
        "Rerun145 localized Protection's only healer exposure",
        '"consecration_healer_multi_trash_pickup"',
    )


def test_rerun158_passive_swarm_activation_uses_native_melee_reach():
    manager = read(BOT_MGR)
    activation = manager.index(
        "BotMeleeAutoAttack::Kind::StartOrSwitch",
        manager.index("bool pendingSwarmActivation"),
    )
    branch = manager[activation - 2600 : activation + 3600]

    assert "!bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)" in branch
    assert "bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)" in branch
    assert "bot->IsWithinLOSInMap(passiveSwarmClusterAnchor)" in branch
    assert "passiveSwarmActivationNotActionable" in branch
    assert "!passiveSwarmActivationNotActionable" in branch
    assert "passiveSwarmActivationLineOfSightBlocked" not in branch
    assert "bot->GetExactDist2d(passiveSwarmClusterAnchor) <= 6.0f" not in branch


def test_rerun159_feral_hazard_retention_prefers_native_thrash_with_fallthrough():
    manager = read(BOT_MGR)
    marker = manager.index("Rerun159 localized all Feral healer exposure")
    branch = manager[marker - 300 : marker + 5200]

    assert 'hazardProfile.SpecTag != "feral_druid_tank"' in branch
    assert "engagedCount < 12" in branch
    assert "!areaTarget" in branch
    assert "!bot->HasSpell(77758)" in branch
    assert "!TryCastCombatSpell(bot, areaTarget, 77758)" in branch
    assert '"feral_thrash_hazard_secure_threat_retention"' in branch
    assert "if (tryFeralHazardThrashRetention())" in branch
    assert_ordered(
        manager,
        "Rerun159 localized all Feral healer exposure",
        '"feral_thrash_hazard_secure_threat_retention"',
        '"feral_swipe_hazard_secure_threat_margin"',
        "if (tryFeralHazardThrashRetention())",
        '"tank_hazard_hold_aoe_threat"',
    )


def test_stonecore_quality_repairs_cover_hazards_pet_recovery_and_healer_protection():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    rotation_sql = (root / "sql/custom/world/2026_07_15_00_stonecore_complete_role_rotations.sql").read_text()
    emergency_threat_sql = read(EMERGENCY_ADD_THREAT_SQL)
    hunter_liveness_sql = (root / "sql/custom/world/2026_07_15_02_stonecore_hunter_rotation_liveness.sql").read_text()

    for field in (
        "ValidationRouteHazardSourceEntry",
        "ValidationRouteHazardDetectionSpellId",
        "ValidationRouteHazardDamageSpellId",
        "ValidationRouteHazardShape",
        "ValidationRouteHazardRadiusYards",
    ):
        assert field in header
        assert field in manager
    assert 'HasInArc(float(M_PI), bot)' in manager
    movement = function_body(
        read(MOVEMENT_CHECK),
        "bool BotWorldPopulationMgr::TryValidationRouteMovementCheck",
    )
    assert "BotWorldValidationHazards::BuildDefinitions(" in movement
    assert "Cohort().Config.ValidationRouteHazardSourceEntry" in movement
    assert "for (ValidationRouteManifestNode const& node : Party().ValidationRouteManifest)" not in movement
    assert "hazardDefinitionFor(creature->GetEntry(), 0)" in manager
    assert '"hazard_exit_started"' in manager
    assert '"hazard_exit_completed"' in manager
    assert '"hold_hazard_exit_failed"' in manager
    assert "HunterPetRevivePendingUntilMs" in header
    assert '"hunter_pet_revive_submitted"' in manager
    assert '"hunter_pet_revived"' in manager
    assert 'victimRole == "healer" ? 3 : 2' in manager
    assert 'if (botIsTank && victimRole == "healer")' in manager
    assert "score += 30000.0f;" in manager
    assert "bool loosePartyThreat = threatVictim && threatVictim->GetGroup() == bot->GetGroup()" in manager
    assert "victim->GetGroup() != bot->GetGroup()" in manager
    assert '"tank_move_to_add_centroid"' in manager
    assert '"misdirection_to_tank"' in manager
    assert "bool hunterAoeTransferReady = true;" in manager
    assert "bot->GetPower(POWER_FOCUS) >= 40" in manager
    assert "&& hunterTrashAoeTransferReady\n        && TryCastFriendlySpell(bot, trashThreatControl.Tank, 34477)" in manager
    assert "if (useAreaTransfer && bot->isMoving()" in manager
    assert "bot->StopMoving();" in manager
    assert "transferAction.SpellId = 2643;" in manager
    assert 'RecordCombatAttempt(state, bot, target, "misdirection_aoe_transfer"' in manager
    assert "bool hunterTrashAoeTransferReady = true;" in manager
    assert 'RecordCombatAttempt(state, bot, target, "misdirection_aoe_transfer"' in manager
    assert '"swarm_pickup_emergency_defensive"' in manager
    assert "bot->getClass() == CLASS_SHAMAN ? 3 : 5" in manager
    assert "persistedCurrentPackCombat" in manager
    assert "!hasStrictPathToValidationRouteTarget(creature)" in manager
    assert "isPendingScriptedEventEntry(creature) && !currentDiscoveryScriptedMember" in manager
    assert '"righteous_defense_healer_pickup"' in manager
    assert '"hand_of_reckoning_add_pickup"' in manager
    assert '"fade_threat_drop"' in manager
    assert '"fade_preemptive_add_wave_threat_drop"' in manager
    assert 'bool healerWaveFadeReady = role == "healer" && cohortSwarmActive' in manager
    assert '&& !densityTankOwnsSecureMajority' in manager
    assert '"healer_stack_for_add_pickup"' in manager
    assert '"guardian_spirit_self_emergency"' in manager
    assert '"desperate_prayer_self_emergency"' in manager
    assert "healer->getAttackers().empty() || UnitHealthPct(healer) > 0.60f" in manager
    assert "safeAngle - tankTarget->GetOrientation()" in manager
    assert "pickup = tankTarget->GetFirstCollisionPosition(4.0f" in manager
    assert "if (Pet* pet = bot->GetPet())\n                pet->AttackStop();" in manager
    assert '"tank_close_to_healer_adds"' not in manager
    assert '"consecration_healer_pickup"' in manager
    assert '"consecration_party_pickup"' in manager
    assert '"dps_stack_for_add_pickup"' in manager
    assert '"consecration_party_trash_pickup"' in manager
    assert '"dps_stack_for_trash_pickup"' in manager
    assert "bot->GetExactDist2d(densityTank) > 8.0f" not in manager
    assert "densityTankSecureAddCount * 10 >= addCount * 9" in manager
    assert "bool listedBossAdd = Cohort().Config.ValidationRouteKind == \"boss\"" in manager
    assert 'candidate.RejectReason = "major_tank_defensive_already_active";' in manager
    assert "bot->GetExactDist2d(densityTank) <= 8.0f" in manager
    assert "(observedListedAttackerCount(bot) && !botInsideTankPickup)" in manager
    assert "bot->GetExactDist2d(tank) > 8.0f" in manager
    assert "Unit* pickupFocus = tank->GetVictim() ? tank->GetVictim() : nearestAttacker;" in manager
    assert '"hand_of_salvation_healer_threat_drop"' in manager
    assert '"hand_of_protection_healer_emergency"' in manager
    assert "densityHealer && observedListedAttackerCount(densityHealer) >= 3" in manager
    assert "defenseScore += 1000;" in manager
    assert "olderHealerTarget" not in manager
    assert "Player* densityDefenseTarget = nullptr;" in manager
    assert '"dps_hold_for_nearby_add_pickup"' in manager
    assert '"tank_auto_attack_density_fallback"' in manager
    assert "urgentHunterPetRecovery" in manager
    assert "addCount >= 3 && !densityDefenseTarget" in manager
    assert "MoveBotToProfileRange(state, bot, target, &profileAction)" in manager
    assert "GetFirstCollisionPosition(profileAction.MinRange" not in manager
    assert "? std::max(12.0f, minRange + 4.0f)" in manager
    assert "auto moveOutOfProfileDeadZone" in manager
    assert "Player* partyRangedAnchor = nullptr;" in manager
    assert "for (float spread : { 3.0f, -3.0f, 0.0f })" in manager
    assert "endpointDistance >= rangeAction.MinRange + 1.0f" in manager
    assert "float absoluteBearing = movingOutward ? reference->GetAngle(bot) : bot->GetAngle(reference);" in manager
    assert "Position rangedPosition = bot->GetFirstCollisionPosition(travelDistance, relativeBearing + angleOffset);" in manager
    assert "for (uint8 ringIndex = 0; ringIndex < 16; ++ringIndex)" in manager
    assert "reference->GetPositionY() + std::sin(angle) * ringRange" in manager
    assert "tankAnchor->GetFirstCollisionPosition" not in manager
    assert "MoveChase(reference, desiredRange)" not in manager
    assert 'state.LastDecisionAction == "validation_route_complete"' in manager
    assert 'context.State.LastDecisionSituation == "validation_route_manifest"' in manager
    assert "bool ValidationRouteObservedDeadScriptTarget = false;" in header
    assert "Party().ValidationRouteObservedDeadScriptTarget = true;" in manager
    assert "Party().ValidationRouteCompletedPackCount > 0 || Party().ValidationRouteObservedDeadScriptTarget" in manager
    assert 'routeArrivalRadius = routeProfile.MovementDirective == "melee" ? 8.0f : 30.0f;' in manager
    assert "Party().ValidationRoutePackObservedEngagement || Party().ValidationRouteObservedDeadScriptTarget" in manager
    assert '\\"validation_route_observed_dead_script_target\\"' in manager
    assert "float minRange = selfTarget ? 0.0f" in manager
    assert 'candidate.RejectReason = "caster_controlled"' in manager
    assert 'candidate.RejectReason = "caster_prevented"' in manager
    assert "WHEN `action`.`spell_id` = 26573 THEN 0" in emergency_threat_sql
    assert "a.`priority_bucket` = 6" in hunter_liveness_sql
    assert "a.`spell_id` = 1130" in hunter_liveness_sql
    for spell_id in (2948, 92315, 11129, 403, 421, 53595, 26573):
        assert str(spell_id) in rotation_sql


def test_parallel_combat_calibration_is_isolated_and_uses_live_rotations():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    commands = (root / "src/server/scripts/Commands/cs_healerbot.cpp").read_text()
    unit = (root / "src/server/game/Entities/Unit/Unit.cpp").read_text()

    assert "std::vector<WorldBotState> CalibrationBots" in header
    assert "std::map<uint32, CalibrationMetrics> CalibrationMetricsByGuid" in header
    assert "std::map<uint32, CalibrationMetrics> CalibrationBestSingleMetrics" in header
    assert "std::map<uint32, CalibrationMetrics> CalibrationBestAoeMetrics" in header
    assert "std::map<uint32, std::string> LastCombatRejectsByBot" in header
    assert "combat_calibration" in manager
    assert "SelectCalibrationPoolCandidateGuid" in manager
    population = function_body(manager, "void BotWorldPopulationMgr::EnsureCalibrationPopulation")
    assert 'Cohort().CalibrationMode == "single_target_300"' in population
    assert "rangedSingleTargetMode" in population
    assert "UsesRangedAoeCalibrationLane(Cohort().CalibrationTargetSpec)" in population
    assert "demonologyAoeMode" in population
    assert "demonologyCloseRangeMode" not in population
    assert "IsolatedSingleTargetDummyEntry =" in manager
    assert "BotCalibrationFixtureContractGenerated::TargetEntry" in manager
    generated_fixture = (
        root / "src/server/game/Bots/BotCalibrationFixtureContractGenerated.h"
    ).read_text()
    assert "inline constexpr uint32_t TargetEntry = 44548;" in generated_fixture
    assert "IsolatedSingleTargetDummyX = -9140.0f" in population
    assert "CalibrationFixtureNativeDryLand" in population
    assert "IsolatedSingleTargetDummyY = 520.0f" in population
    assert "IsolatedSingleTargetRangedRadius = 15.0f" in population
    assert "sTerrainMgr.LoadTerrain(0)" in population
    assert "PhasingHandler::GetEmptyPhaseShift()" in population
    assert "terrain->GetGridHeight(" in population
    assert "fixtureGridZ + 4.0f" in population
    assert "calibrationFixtureGroundZ + 4.0f" in population
    assert "calibrationSpawnZ" in population
    assert "calibrationSpawnZ <= INVALID_HEIGHT" in population
    assert '"calibration_isolated_spawn_ground_unavailable"' in population
    assert "distanceContract->RuntimeMinimumDistanceYards" in population
    assert "distanceContract->RuntimeMaximumDistanceYards" in population
    assert "distanceMidpoint" in population
    assert "std::vector<float>{ 2.0f, 2.5f, 3.0f }" in population
    assert "RuntimeMinimumDistanceYards" in population
    assert "RuntimeMaximumDistanceYards" in population
    assert "approximateDistance" in population
    assert "selfCenteredHostileAction" in manager
    assert "!candidateSpellInfo->IsPositive()" in manager
    assert "bot->GetExactDist(target)" in manager
    assert '"calibration_isolated_ranged_ground_unavailable"' in population
    assert "heightDelta > 1.0f" in population
    assert '"calibration_isolated_melee_ground_unavailable"' in population
    assert "bot->IsWithinMeleeRange(" in population
    assert "bot->IsWithinLOSInMap(fixtureTarget)" in population
    assert "PATHFIND_NORMAL" in population
    assert "PATHFIND_INCOMPLETE" in population
    assert "path_calculated=%u path_type=%u" in population
    assert '"calibration_isolated_melee_fixture_unreachable"' in population
    for geometry_field in (
        "CalibrationFixtureBotSpawnX",
        "CalibrationFixtureBotSpawnY",
        "CalibrationFixtureBotSpawnZ",
        "CalibrationFixtureBotTargetDistance",
        "CalibrationFixtureNativeLineOfSight",
        "CalibrationFixtureNativePathReachable",
        "CalibrationFixtureNativeMeleeReachable",
        "CalibrationFixtureGeometryValidated",
        "CalibrationFixtureProfileLane",
    ):
        assert geometry_field in header
        assert geometry_field in population or geometry_field in manager
    assert "std::vector<CalibrationSpawnCandidate> calibrationSpawnCandidates" in population
    assert "std::stable_sort(calibrationSpawnCandidates.begin()" in population
    assert "maximumPopulationAttempts" in population
    assert "&calibrationSpawnCandidates[attempts - 1]" in population
    assert "std::to_string(candidateGuid), 0, x, y, z" in population
    assert "retryAlternateSpawn" in population
    assert "MinimumIsolatedDummyClearance = 45.0f" in population
    assert "map->SummonCreature(IsolatedSingleTargetDummyEntry" in population
    assert "fixtureArgs.SetSummonDuration(" in population
    assert "fixtureArgs.SummonHealth = IsolatedSingleTargetMaxHealth" in population
    assert "SetStatFlatModifier(UNIT_MOD_ARMOR, BASE_VALUE" in population
    assert "fixtureTarget->UpdateArmor()" in population
    assert "20 * 60 * IN_MILLISECONDS" in population
    assert "bot->IsValidAttackTarget(other)" in population
    assert "CalibrationFixtureTargetNearestHostileClearance" in population
    assert "CalibrationFailureReason" in header
    assert "calibration_isolated_target_provisioning_failed" in population
    assert "BotWorld calibration isolated target rejected" in population
    assert "BotWorld calibration target fidelity drift before scoring" in manager
    assert 'distance=%.3f range=[%.3f,%.3f]' in manager
    assert "!Cohort().CalibrationWindowComplete && populationReady" in manager
    for rejection in (
        "calibration_isolated_target_summon_failed",
        "calibration_isolated_target_not_attackable",
        "calibration_isolated_target_hostile_clearance_failed",
        "calibration_isolated_target_line_of_sight_failed",
        "calibration_isolated_target_distance_failed",
        "calibration_isolated_target_path_failed",
    ):
        assert rejection in population
    assert "Cohort().CalibrationWindowComplete = true" in population
    stop = manager.split(
        "std::string BotWorldPopulationMgr::StopCombatCalibration()", 1
    )[1].split("std::string BotWorldPopulationMgr::GetCombatCalibrationJson()", 1)[0]
    assert "sMapMgr->FindMap(" in stop
    assert "CalibrationFixtureTargetMapId, 0" in stop
    assert "fixture_cleanup_submitted_or_absent" in stop
    assert r'\"cohort_id\":\"' in stop
    assert r'\"server_epoch\":' in stop
    assert r'\"attempt_id\":' in stop
    assert "for (WorldBotState const& state : Party().CalibrationBots)" not in stop.split(
        "bool fixtureTargetFound", 1
    )[1].split("uint32 removed", 1)[0]
    classifier = function_body(manager, "bool UsesRangedAoeCalibrationLane")
    for ranged_spec in (
        "balance_druid",
        "beast_mastery_hunter",
        "marksmanship_hunter",
        "survival_hunter",
        "shadow_priest",
        "elemental_shaman",
        "arcane_mage",
        "fire_mage",
        "frost_mage",
        "affliction_warlock",
        "demonology_warlock",
        "destruction_warlock",
    ):
        assert f'"{ranged_spec}"' in classifier
    assert "shadowPriestSingleTargetMode" not in population
    update = function_body(manager, "void BotWorldPopulationMgr::UpdateCalibrationBot")
    assert 'Cohort().CalibrationMode == "single_target_300"' in update
    assert "CalibrationFixtureTargetGuid" in update
    assert "dummies.push_back(fixtureTarget)" in update
    assert "calibration_isolated_target_lost" in update
    assert "CompleteCalibrationScoredWindow()" in update
    assert "metrics.TargetCount = std::max(metrics.TargetCount, hostileCount)" not in update
    assert "uint32 hostileCount = Cohort().CalibrationAoePhase ? uint32(dummies.size()) : 1;" in update
    assert 'bool const strictSingleTarget = Cohort().CalibrationMode == "single_target_300";' in update
    assert "bool const forbidArea = false;" in update
    assert "bool const allowMultidot = !strictSingleTarget;" in update
    assert "false, forbidArea, allowMultidot" in update
    assert "forbidArea, allowMultidot);" in update

    resolver = function_body(
        manager, "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction"
    )
    assert "exactSingleTargetCalibration && candidate.SpellId == 42650" in resolver
    assert 'candidate.RejectReason = "reference_prepull_action_excluded"' in resolver

    notify_damage = function_body(manager, "void BotWorldPopulationMgr::NotifyCombatDamage")
    assert "calibration->second.LastDamageMsByTarget.size()" in notify_damage
    assert "calibration->second.OffTargetDamage += measuredDamage" in notify_damage
    assert "calibration->second.PrimaryTargetDamage += measuredDamage" in notify_damage

    damage = function_body(manager, "void BotWorldPopulationMgr::NotifyCombatDamage")
    assert damage.index("CalibrationMetricsByGuid.find") < damage.index("FindCombatLogCohortPlayer(attacker)")
    assert "uint32 measuredDamage = damage ? damage : unmitigatedDamage" in damage
    assert "calibration->second.SpellDamage[spellId] += measuredDamage" in damage
    assert "damageBeforeScriptAdjustment" in unit
    assert "isolated_from_route_telemetry" in manager
    assert "best_windows" in manager
    assert "external_bis_target_configured" in manager
    assert "EnsureCalibrationCohortGroup();" in manager
    assert "stonecore_party_owned_buffs" in manager
    assert "phase8_external_windows_observation_v1" in manager
    assert "temporal_external_auras_absent" in manager
    assert "ApplyCalibrationReferenceConditions(bot, target)" in update
    reference_conditions = function_body(manager, "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions")
    for spell_id in ["79102", "53646", "79058", "24932", "2895", "8515", "8076", "82930", "57669", "79470", "79471", "79472", "1490", "22959", "81326", "58567"]:
        assert spell_id in reference_conditions
    assert "2825" not in reference_conditions
    assert "bot->getClass() != CLASS_PALADIN" in reference_conditions
    assert "reference debuffs on that primary target" in reference_conditions
    assert "sunder->SetStackAmount(3)" in reference_conditions
    assert "target->GetAura(spellId, bot->GetGUID())" in reference_conditions
    assert "phase8_reference_condition_observation_v1" in manager
    assert "ObserveCalibrationReferenceConditions" in manager
    assert "ReferenceTargetAuraOwnerMismatchSamples" in manager
    assert "UnexpectedExternalBleedActiveSamples" in manager
    assert "ReferenceTargetDebuffsReady" in manager
    assert "ReferenceHeroismWindowObserved" in manager
    assert '\\"reference_setup\\"' in manager
    assert "EnsureCalibrationCohortGroup();" in manager
    assert "group->AddMember(bot)" in manager
    assert '\\"grouped\\"' in manager
    reference = json.loads((root / "dataset/combat_calibration/wowsims_cata_p4.json").read_text())
    assert reference["schema"] == "bot_combat_calibration_reference_v1"
    assert {profile["spec"] for profile in reference["profiles"]} == {
        "fire_mage", "survival_hunter", "enhancement_shaman"
    }
    assert "dummy->RemoveOwnedAuras([&ownedCasterGuids](Aura const* aura)" in manager
    assert "metrics.WindowEndedMs = endedMs;" in manager
    assert "last_action_rejections" in manager
    assert "last_chosen_action" in manager
    assert "Unit* target = dummies.front();" in update
    assert '{ "calibrate", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "StartCombatCalibration" in commands
    assert "StopCombatCalibration" in commands


def test_rerun148_feral_pre_victim_cadence_and_charge_identity_are_bounded():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)

    assert "engagedAddCount >= 12 && densityHealer" in manager
    assert "observedListedAttackerCount(densityHealer) == 0" in manager
    assert "state.DecisionTimer, 250" in manager
    assert "feralChargePickupTarget = ObjectAccessor::GetUnit(" in manager
    assert "state.FeralChargePickupTargetGuid" in manager
    assert "state.FeralChargePickupUntilMs > feralChargeNowMs" in manager


def test_rerun148_hunter_spell_los_failure_forces_one_alternate_lane_search():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)

    assert "MoveBotToProfileRange(*state, bot, target, &action, true);" in manager
    assert "if (!forceRangedReposition && distance >= desiredRange - 1.0f" in manager


def test_rerun206_feral_dps_provisions_and_maintains_cat_form():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)
    catalogs = (root / "tools/bot_ml/build_all_spec_phase1_catalogs.py").read_text()
    targets = json.loads((root / "experiments/configs/all_spec_targets_cata_p4_v1.json").read_text())
    feral = next(row for row in targets["targets"] if row["spec_target_id"] == "feral_druid_dps")

    assert '"feral_druid_dps": [768, 20484]' in catalogs
    assert '{ CLASS_DRUID, "dps", "feral_druid_dps", 768, 768, 0, "cat_form" }' in manager
    assert 768 in feral["action_profile_spell_ids"]


def test_rerun207_feral_dps_shred_repositions_behind_before_native_cast():
    root = Path(__file__).resolve().parents[1]
    manager = read(BOT_MGR)

    movement = function_body(manager, "bool BotWorldPopulationMgr::MoveBotToProfileRange")
    execution = function_body(manager, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction")
    assert 'action->SpellId == 5221 && directive == "melee_behind"' in movement
    assert "reference->HasInArc(nativeFrontArc, &rearPosition)" in movement
    assert "reference->GetFirstCollisionPosition(" in movement
    assert "moveToTerrainProjectedPoint(rearPosition.GetPositionX()" in movement
    assert "target->HasInArc(nativeFrontArc, bot)" in execution
    assert 'action.MovementDirective = "melee_behind";' in execution
    assert '"shred_behind_required"' in execution
    assert "state->ProfileCastSuppressedSpellId = action.SpellId;" in execution
    assert "state->ProfileCastSuppressedUntilMs = nowMs + 3000;" in execution
    assert_ordered(
        execution,
        "target->HasInArc(nativeFrontArc, bot)",
        "MoveBotToProfileRange(*state, bot, target, &action)",
        "BotActionExecutor executor",
    )
