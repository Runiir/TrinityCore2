from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
HELPER = (
    BOTS
    / "Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"
)
MODULE = BOTS / "BotWorldPopulationMgrMagmawBloodlust.cpp"
MANAGER = BOTS / "BotWorldPopulationMgr.h"
RUNTIME = BOTS / "BotWorldPopulationMgrRuntimeContracts.h"
CANDIDATES = BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
EVENTS = BOTS / "BotWorldPopulationMgrEventRecording.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
SCENARIOS = ROOT / "dataset/validation_scenarios/validation_scenarios.jsonl"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def test_exact_magmaw_10n_roster_is_the_admitted_diagnostic_roster() -> None:
    scenario = next(
        json.loads(line)
        for line in SCENARIOS.read_text(encoding="utf-8").splitlines()
        if line.strip()
        and json.loads(line)["scenario_id"]
        == "blackwing_descent_10n_magmaw_diagnostic"
    )
    roster = [
        (member["roster_slot_id"], member["role"], member["class_spec"])
        for member in scenario["roster_identity"]
    ]
    assert len(roster) == 10
    assert roster.count(("raid_dps_5", "dps", "elemental_shaman")) == 1

    source = text(MODULE)
    for slot, role, class_spec in roster:
        assert f'{{ "{slot}", "{role}", "{class_spec}" }}' in source
    assert 'DiagnosticScenario =\n    "blackwing_descent_10n_magmaw_diagnostic"' in text(HELPER)
    assert 'ValidationRouteScenarioId != DiagnosticScenario' in source
    assert 'AdmissionScenarioId != DiagnosticScenario' in source


def test_first_exposed_head_and_all_raid_lockouts_are_pure_observations() -> None:
    helper = text(HELPER)
    window = function_body(helper, "ObserveFirstHeadWindow(")
    assert 'board.Route.NodeId != EncounterNode' in window
    assert 'board.NativeBossState != "in_progress"' in window
    assert "FindBoss(board)" in window
    assert "FindExposedHead(board)" in window

    head = function_body(helper, "FindExposedHead(")
    assert "actor.Entry == ExposedHeadEntry" in head
    assert "actor.Selectable" in head
    assert "actor.Attackable" in head
    assert "std::sort" in head
    assert "GetRawValue()" in head

    for spell_id in (2825, 32182, 80353, 90355, 57723, 57724, 80354, 95809):
        assert str(spell_id) in helper
    assert "FindRaidLockout(board)" in text(MODULE)
    assert "ObservedBloodlustAura(board" in text(MODULE)
    assert "TimingEvidence" in helper
    assert "no_wcl_verification" in helper


def test_bloodlust_is_one_native_cast_with_normal_readiness_and_telemetry() -> None:
    module = text(MODULE)
    body = function_body(module, "SubmitMagmawBloodlustCandidate(")
    runtime = text(RUNTIME)

    assert "MagmawBloodlustSubmitted" in runtime
    assert "MagmawBloodlustAuraObserved" in runtime
    assert "MagmawBloodlustAttemptId" in runtime
    assert "MagmawBloodlustWipeGeneration" in runtime
    assert "MagmawBloodlustRouteGeneration" in runtime
    assert "MagmawBloodlustOwnerGuid" in runtime
    assert "MagmawBloodlustHeadGuid" in runtime

    assert "TryCastFriendlySpell(context.Bot, context.Bot, BloodlustSpell" in body
    assert '"submitted_native_spell_2825"' in body
    assert '"observed_aura_2825"' in body
    assert '"blocked_" + reason' in body
    assert "MagmawBloodlustSubmitted = true" in body
    assert "MagmawBloodlustHeadGuid != window->HeadGuid" in body
    assert body.index("TryCastFriendlySpell(") < body.index(
        "MagmawBloodlustSubmitted = true"
    )
    assert body.index('"submitted_native_spell_2825"') > body.index(
        "MagmawBloodlustSubmitted = true"
    )
    assert "Resource::GlobalCooldown" in body
    assert "Resource::Cast" in body
    assert "Resource::Target" in body
    assert "HasSpell(BloodlustSpell)" in body
    assert "TryCastFriendlySpell" in text(BOTS / "BotWorldPopulationMgrCombatSupport.cpp")

    forbidden = (
        "AddAura(",
        "RemoveSpellCooldown",
        "ResetSpellCooldown",
        "SetCooldown",
        "CastSpell(context.Bot, BloodlustSpell, true)",
        "BotAdaptiveMagmawStrategy.h",
        "BotEncounterBlackboard.cpp",
    )
    assert not any(token in body for token in forbidden)
    assert "SubmitMagmawBloodlustCandidate(context);" in text(CANDIDATES)
    assert "BotWorldPopulationMgrMagmawBloodlust.cpp" in text(CMAKE)
    assert 'observedEvent == "magmaw_bloodlust"' in text(EVENTS)

    for path in (HELPER, MODULE, MANAGER, RUNTIME, CANDIDATES, EVENTS):
        assert len(text(path).splitlines()) < 1000, path
