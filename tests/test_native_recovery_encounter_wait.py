"""A released ghost waits at the raid portal while the encounter is in progress.

Round 5 (r04 Maloriak): the rogue died at 63 s, released, and reached the BWD
portal at 105 s while Maloriak was in progress. Map::CannotEnter refused the
entry (CANNOT_ENTER_ZONE_IN_COMBAT) and WorldSession::HandleAreaTriggerOpcode
resurrected the ghost outside the raid (reviveAtTrigger), which failed the
attempt as validation_active_instance_drift. The wait is scoped to canonical
raid shards (accepted dungeon and legacy scenarios keep their recovery) and
bounded so it cannot hold a ghost forever.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
RECOVERY = BOTS / "BotWorldPopulationMgrRecovery.cpp"
STATE = BOTS / "BotWorldPopulationMgrBotState.h"
PREPARATION = BOTS / "BotWorldPopulationMgrUpdateBotPreparation.cpp"
HANDLER = ROOT / "src/server/game/Handlers/MiscHandler.cpp"
MAP = ROOT / "src/server/game/Maps/Map.cpp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_native_entry_refusal_resurrects_outside_the_raid() -> None:
    handler = read(HANDLER)
    refusal = handler.index("case Map::CANNOT_ENTER_ZONE_IN_COMBAT:")
    assert "reviveAtTrigger = true;" in handler[refusal:refusal + 200]
    assert "player->ResurrectPlayer(0.5f);" in handler
    source = read(MAP)
    combat = source.index("return CANNOT_ENTER_ZONE_IN_COMBAT;")
    # Dungeons as well as raids: the wait must scope itself to raids.
    assert "(IsDungeon() || IsRaid())" in source[combat - 250:combat]


def wait_block() -> tuple[str, str]:
    source = read(RECOVERY)
    wait = source.index('transition("entrance_encounter_wait");')
    submit = source.index("BotNativeAction::AreaTrigger{ entranceEntry->ID }")
    assert wait < submit
    start = source.rindex("bool const canonicalRaid = Cohort().Raid.RaidInstance", 0, wait)
    return source, source[start:submit]


def test_wait_is_scoped_to_canonical_raid_shards() -> None:
    source, block = wait_block()
    assert '#include "Bots/BotCanonicalRaidScope.h"' in source
    assert "BotCanonicalRaidScope::IsCanonicalCompositionScenario(" in block
    assert "Cohort().Config.ValidationRouteScenarioId" in block
    assert "originalMap && originalMap->IsRaid()" in block
    assert "state.ValidationCohortInstanceId" in block
    assert "originalScript && originalScript->IsEncounterInProgress()" in block


def test_wait_never_submits_the_trigger_and_is_bounded() -> None:
    source, block = wait_block()
    assert "constexpr uint64 NativeEntranceEncounterWaitMaxMs = 15 * 60 * 1000;" in source
    wait = block.index('transition("entrance_encounter_wait");')
    before, after = block[:wait], block[wait:]
    assert "state.NativeRecoveryEntranceWaitStartedMs = nowMs;" in before
    assert 'return terminal("native_entrance_encounter_wait_exhausted");' in before
    assert "state.NativeRecoveryEpisodeLastProgressMs = nowMs;" in after
    assert '"native_instance_entrance_encounter_in_progress_wait"' in after
    assert "state.LastNoProgressReason = result;" in after
    assert "return true;" in after
    # The wait clears as soon as the entrance may be submitted.
    reset = after.index("state.NativeRecoveryEntranceWaitStartedMs = 0;")
    assert after.index("return true;") < reset < after.index('transition("entrance_submitted");')
    # The corpse run never names or calls the native handlers themselves
    # (test_bot_no_cheat_contract).
    assert "HandleAreaTriggerOpcode" not in block
    assert "ResurrectPlayer" not in block
    assert len(source.splitlines()) < 1000


def test_wait_start_is_episode_state() -> None:
    assert "uint64 NativeRecoveryEntranceWaitStartedMs = 0;" in read(STATE)
    assert "state.NativeRecoveryEntranceWaitStartedMs = 0;" in read(RECOVERY)
    assert "context.State.NativeRecoveryEntranceWaitStartedMs = 0;" in read(PREPARATION)
