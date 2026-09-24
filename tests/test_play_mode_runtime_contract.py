from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_play_mode_is_default_off() -> None:
    # worldserver.conf.dist is hash-pinned by tracked_runtime_config_derivation
    # (TEMPLATE_SHA256), so the key stays out of it: absent means off, and
    # only the play launcher sets it.
    dist = _read(ROOT / "src/server/worldserver/worldserver.conf.dist")
    assert "BotWorld.PlayMode.Enable" not in dist
    config = _read(BOTS / "BotWorldPopulationMgrConfig.cpp")
    assert 'GetBoolDefault("BotWorld.PlayMode.Enable", false)' in config
    assert "bool PlayModeEnable = false;" in _read(BOTS / "BotWorldPopulationMgrConfig.h")


def test_cohorts_default_to_validation_and_only_fill_starts_play() -> None:
    contracts = _read(BOTS / "BotWorldPopulationMgrRuntimeContracts.h")
    assert "CohortPurpose Purpose = CohortPurpose::Validation;" in contracts
    # The only runtime path that selects Play is `.botauto play fill`, and it
    # checks the default-off config key before touching any cohort.
    writers = [
        path.relative_to(ROOT).as_posix()
        for path in BOTS.rglob("*")
        if path.suffix in {".h", ".cpp"}
        and path.name != "BotCohortPurpose.h"
        and re.search(r"Purpose\s*=\s*CohortPurpose::Play", _read(path))
    ]
    assert writers == ["src/server/game/Bots/BotWorldPopulationMgrPlay.cpp"]
    play = _read(BOTS / "BotWorldPopulationMgrPlay.cpp")
    fill = play[play.index("std::string Context::Fill("):]
    assert fill.index('"BotWorld.PlayMode.Enable"') < fill.index("cohort->Purpose = CohortPurpose::Play")


# Shared-lifecycle files may reach play code only behind the Play purpose or
# through Context helpers that return validation-neutral values.
NEUTRAL_HELPERS = (
    "IsExternalSlot", "ExternalSlotCount", "ExpectedBotCount", "StatusFieldsJson", "FrozenLeaderHolds",
)


def test_shared_lifecycle_hooks_are_gated_or_neutral() -> None:
    hooks = []
    for path in sorted(BOTS.glob("BotWorldPopulationMgr*.cpp")):
        if path.name == "BotWorldPopulationMgrPlay.cpp":
            continue
        lines = _read(path).splitlines()
        for index, line in enumerate(lines):
            match = re.search(r"BotWorldPopulationMgrPlay::Context::(\w+)", line)
            if not match:
                continue
            window = "\n".join(lines[max(0, index - 8) : index + 1])
            gated = "CohortPurpose::Play" in window or re.search(r"\bplay\b", window)
            hooks.append((path.name, match.group(1)))
            assert match.group(1) in NEUTRAL_HELPERS or gated, (path.name, index + 1, line)
    names = {name for _, name in hooks}
    assert {"PermitRouteAdvance", "NativeGroupAdmits", "AdmissionAnchor", "ResetBotPool",
            "PublishExternalPlayers"} <= names


def test_neutral_helpers_are_identity_for_validation() -> None:
    play = _read(BOTS / "BotWorldPopulationMgrPlay.cpp")
    assert "return mgr.Cohort().Purpose == CohortPurpose::Play\n        && mgr.Cohort().Play.ExternalSlotIds.count(slotId) != 0;" in play
    assert "return mgr.Cohort().Purpose == CohortPurpose::Play\n        ? uint32(mgr.Cohort().Play.ExternalSlotIds.size()) : 0;" in play
    status = play[play.index("std::string Context::StatusFieldsJson("):]
    assert 'return "";' in status.split("BotPlaySession const& session")[0]


def test_status_and_diagnose_publish_purpose_and_duty_plan() -> None:
    status = _read(BOTS / "BotWorldPopulationMgrStatus.cpp")
    assert '\\"cohort_purpose\\":\\"" << CohortPurposeName(Cohort().Purpose)' in status
    assert '\\"play_mode_enabled\\":' in status
    assert "BuildMagmawDutyPlanStatusJson(" in status
    diagnosis = _read(BOTS / "BotWorldPopulationMgrDiagnosis.cpp")
    assert '\\"cohort_purpose\\":\\"" << CohortPurposeName(Cohort().Purpose)' in diagnosis


def test_external_members_stay_out_of_duty_selectors() -> None:
    blackboard = _read(BOTS / "BotEncounterBlackboard.h")
    assert "std::vector<ActorSnapshot> ExternalPlayers;" in blackboard
    # FindActor searches external members last, so bot, hostile, summon and
    # interactable lookups keep their precedence.
    assert blackboard.index("findIn(Interactables)") < blackboard.index(
        "findIn(ExternalPlayers)"
    )
    # Duty selectors never read external members; only the play publisher
    # fills them and only heal targeting reads them.
    magmaw = BOTS / "Content/Raids/BlackwingDescent/Encounters/Magmaw"
    readers = [
        path.name
        for path in magmaw.rglob("*")
        if path.suffix in {".h", ".cpp"} and "ExternalPlayers" in _read(path)
    ]
    assert readers == []
    users = sorted(
        path.name
        for path in BOTS.glob("*.cpp")
        if "ExternalPlayers" in _read(path)
    )
    assert users == [
        "BotWorldPopulationMgrEncounterBlackboard.cpp",  # PublishExternalPlayers call
        "BotWorldPopulationMgrPlay.cpp",
        "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
    ]


def test_no_ungated_frozen_leader_comparison_remains() -> None:
    # A human leads a play raid, so every comparison of the live group leader
    # with a bot's frozen leader must be play-gated or use FrozenLeaderHolds
    # (review of 1f5a8178ab: an ungated one made every fill roll back).
    offenders = []
    for path in sorted(BOTS.rglob("*")):
        if path.suffix not in {".cpp", ".h", ".inl"}:
            continue
        lines = _read(path).splitlines()
        for index, line in enumerate(lines):
            if "GetLeaderGUID()" not in line:
                continue
            window = "\n".join(lines[max(0, index - 2) : index + 3])
            if ("ValidationCohortLeaderGuid" in window and "!play" not in window
                    and "FrozenLeaderHolds" not in window):
                offenders.append(f"{path.relative_to(BOTS)}:{index + 1}")
    assert offenders == []
    play = _read(BOTS / "BotWorldPopulationMgrPlay.cpp")
    helper = play[play.index("bool Context::FrozenLeaderHolds("):]
    helper = helper[: helper.index("}") + 1]
    assert "mgr.Cohort().Purpose == CohortPurpose::Play" in helper
    assert "group->GetLeaderGUID() == frozenLeader" in helper


def test_human_ready_check_hook_is_a_no_op_outside_play() -> None:
    handler = _read(ROOT / "src/server/game/Handlers/GroupHandler.cpp")
    request = handler[handler.index("group->OfflineReadyCheck();"):]
    assert request.index("BotWorldPopulationMgrPlay::OnRaidReadyCheckStarted(group, GetPlayer());") < 200
    play = _read(BOTS / "BotWorldPopulationMgrPlay.cpp")
    hook = play[play.index("void Context::OnRaidReadyCheckStarted("):]
    guard = hook[: hook.index("return;")]
    for condition in ("cohort->Purpose != CohortPurpose::Play", "!cohort->Play.Active",
                      "group->GetGUID() != cohort->Play.GroupGuid", "!IsHuman(initiator)"):
        assert condition in guard


def test_fill_success_never_reads_the_renamable_config_name() -> None:
    # An auto recording window renames Config.Name (review of 778df0d620).
    play = _read(BOTS / "BotWorldPopulationMgrPlay.cpp")
    assert "Config.Name" not in play.replace("// Config.Name is renamed", "")
    assert "SelectedProfileName == Scenario" in play


def test_pull_timer_hooks_are_no_ops_outside_a_play_raid() -> None:
    chat = _read(ROOT / "src/server/game/Handlers/ChatHandler.cpp")
    assert "BotWorldPopulationMgrPlay::OnAddonMessage(sender, type, prefix, message);" in chat
    play = _read(BOTS / "BotWorldPopulationMgrPlay.cpp")
    leadership = play[play.index("bool Context::FromPlayLeadership("):]
    leadership = leadership[: leadership.index("\n}\n")]
    for condition in ("cohort->Active", "cohort->Purpose == CohortPurpose::Play",
                      "cohort->Play.Active", "IsHuman(sender)",
                      "group->GetGUID() == cohort->Play.GroupGuid"):
        assert condition in leadership
    for hook in ("void OnAddonMessage(", "void OnGroupChat("):
        body = play[play.index(hook):]
        body = body[: body.index("\n}\n")]
        assert "FromPlayLeadership(" in body
        assert body.index("FromPlayLeadership(") < body.index("Context::Pull(")


def test_play_reset_restores_the_provisioned_hunter_pet_growl_state() -> None:
    # The Chainwielder patrol pull waits for Growl autocast off, which
    # provisioning sets (active 129) and validation re-applies every run; a
    # play session found it enabled after earlier runs (2026-09-24).
    play = _read(BOTS / "BotWorldPopulationMgrPlay.cpp")
    reset = play[play.index("bool Context::ResetBotPool("):]
    reset = reset[: reset.index("\n}\n")]
    assert "HunterPetGrowlSpellId" in reset and "PetGrowlAutocastDisabled" in reset
    assert "constexpr uint32 HunterPetGrowlSpellId = 2649;" in play
    assert "constexpr uint32 PetGrowlAutocastDisabled = 0x81;" in play
    provisioning = _read(ROOT / "experiments/configs/validation_provisioning_cata_001.json")
    assert '{ "id": 2649, "active": 129 }' in provisioning
