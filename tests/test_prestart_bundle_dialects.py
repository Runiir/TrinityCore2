from tools.raid_program.prestart_bundle_dialects import (
    CHAINWIELDER,
    config_values,
    identity,
)


def test_chainwielder_composite_replay_binds_magmaw_task_authority() -> None:
    values = config_values(CHAINWIELDER)

    assert values["BotWorld.Magmaw.TransferLaneTaskAuthority"] == "1"
    assert identity(
        CHAINWIELDER,
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
    )["task_authority_enabled"] is True
