"""Round 10: per-boss talent group switching in the canonical full raid (BotRaidSpecSwitch.h).

The full raid mirrors the boss shards (tools/raid_program/raid_full_route_mirror.py) and carries a spec_contract
on a regroup node before every node set whose shard runs other talent groups. Each member casts its own Activate
Primary/Secondary Spec spell, equips the group's native equipment set through CMSG_EQUIPMENT_SET_USE, and its
admission receipt is re-frozen; every identity reader follows the ACTIVE talent group (BotActiveSpecIdentity.h).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from tools.bot_ml import build_validation_scenario_manifests as builder

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
DBC = ROOT / "data/dbc/enUS"
FULL = "blackwing_descent_10n_full_c0"


def _scenarios() -> dict:
    config = json.loads(CONFIG.read_text())
    return {row["id"]: row for row in config["scenarios"] + config["diagnostic_scenarios"]}


def _run(tmp_path: Path, program: str) -> str:
    source, binary = tmp_path / "spec_switch.cpp", tmp_path / "spec_switch"
    source.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src/server/game"),
                    "-I", str(ROOT / "src/common"), str(source), "-o", str(binary)], check=True)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def _cpp_string(text: str) -> str:
    return "R\"JSON(" + text + ")JSON\""


def test_the_full_raid_contracts_parse_and_bad_contracts_are_refused(tmp_path):
    full = _scenarios()[FULL]
    contracts = [builder.spec_contract(_scenarios()[FULL], step) for step in full["route"] if step.get("spec_contract")]
    assert len(contracts) == 5
    good = ", ".join(_cpp_string(json.dumps(contract)) for contract in contracts)
    row = {"roster_slot": 1, "talent_group": 0, "class_spec": "balance_druid", "role": "dps",
           "talent_groups": [{"talent_group": 0, "class_spec": "balance_druid", "role": "dps"},
                             {"talent_group": 1, "class_spec": "feral_druid_tank", "role": "tank"}]}
    bad = {
        "spec_contract_shape": [],
        "spec_contract_unknown_field:gear": [{**row, "gear": 1}],
        "spec_contract_wanted_group_undeclared": [{**row, "talent_groups": row["talent_groups"][1:]}],
        "spec_contract_wanted_identity_mismatch": [{**row, "role": "tank"}],
        "spec_contract_slot_duplicate": [row, row],
        "spec_contract_row_invalid": [{**row, "roster_slot": 0}],
        "spec_contract_talent_group_duplicate": [{**row, "talent_groups": row["talent_groups"][:1] * 2}],
        # Review P2: a missing wanted group must not default to group 0.
        "spec_contract_row_field_missing": [{key: value for key, value in row.items() if key != "talent_group"}],
        "spec_contract_talent_group_invalid": [{**row, "talent_groups": [
            {"talent_group": 0, "class_spec": "balance_druid"}, row["talent_groups"][1]]}],
    }
    checks = "\n".join(
        f'    expect_error({_cpp_string(json.dumps(value))}, "{name}");' for name, value in bad.items())
    out = _run(tmp_path, r'''
#include "Bots/BotRaidSpecSwitch.h"
#include <cassert>
#include <cstdio>
namespace S = BotRaidSpecSwitch;
static std::vector<S::ContractRow> parse(char const* text, std::string& error)
{
    BotValidationRouteNativeJson::Value value;
    std::vector<S::ContractRow> rows;
    std::string parseError;
    assert(BotValidationRouteNativeJson::Parse(text, value, parseError));
    error.clear();
    S::ParseContract(value, rows, error);
    return rows;
}
static void expect_error(char const* text, char const* name)
{
    std::string error;
    parse(text, error);
    if (error != name) { std::printf("wrong:%s:%s\n", name, error.c_str()); assert(false); }
}
int main()
{
    char const* good[] = { ''' + good + r''' };
    for (char const* text : good)
    {
        std::string error;
        std::vector<S::ContractRow> rows = parse(text, error);
        assert(error.empty() && rows.size() == 10);
        for (S::ContractRow const& row : rows)
            std::printf("%u:%s:%u:%s:%s\n", row.RosterSlot, row.CharacterKey.c_str(), unsigned(row.TalentGroup),
                row.ClassSpec.c_str(), row.Role.c_str());
    }
''' + checks + r'''
    return 0;
}
''')
    lines = out.split()
    assert len(lines) == 50
    druid = [line for line in lines if ":druid:" in line]
    assert [line.split(":", 2)[2] for line in druid] == [
        "0:balance_druid:dps", "1:feral_druid_tank:tank", "0:balance_druid:dps", "1:feral_druid_tank:tank",
        "1:feral_druid_tank:tank"]


def test_the_switch_steps_and_the_activate_spells(tmp_path):
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    effects = {int(row[24]): int(row[5]) for row in load_wdbc_values(
        DBC / "SpellEffect.dbc", "nifiiiffiiiiiifiifiiiiiiiix") if int(row[1]) == 162}  # TALENT_SPEC_SELECT
    # Spell::EffectActivateSpec calls ActivateSpec(damage - 1): basepoints 1 -> group 0, 2 -> group 1.
    assert effects[63645] == 1 and effects[63644] == 2
    out = _run(tmp_path, r'''
#include "Bots/BotRaidSpecSwitch.h"
#include "Bots/BotActiveSpecIdentity.h"
#include <cassert>
#include <cstdio>
namespace S = BotRaidSpecSwitch;
int main()
{
    assert(S::ActivateSpellFor(0) == 63645 && S::ActivateSpellFor(1) == 63644);
    S::Observation in;
    in.ActiveGroup = 1; in.WantedGroup = 0; in.NowMs = 1000;
    assert(S::Decide(in) == S::Step::CastActivate);
    in.Casting = true;
    assert(S::Decide(in) == S::Step::AwaitCast);
    in.Casting = false; in.RetryDue = false;
    assert(S::Decide(in) == S::Step::AwaitCast);
    in.WaitingSinceMs = 1000; in.NowMs = 1000 + S::SwitchTimeoutMs;
    assert(S::Decide(in) == S::Step::Timeout);
    in = S::Observation(); in.ActiveGroup = in.WantedGroup = 0;
    assert(S::Decide(in) == S::Step::EquipSet);
    in.SetEquipped = true;
    assert(S::Decide(in) == S::Step::Refreeze);
    in.ReceiptCurrent = true;
    assert(S::Decide(in) == S::Step::Done);

    namespace I = BotActiveSpecIdentity;
    I::Identity identity;
    assert(!I::Resolve(42, 0, identity));
    I::Register(42, { { 0, { "balance_druid", "dps" } }, { 1, { "feral_druid_tank", "tank" } } });
    assert(I::Resolve(42, 0, identity) && identity.ClassSpec == "balance_druid" && identity.Role == "dps");
    assert(I::Resolve(42, 1, identity) && identity.ClassSpec == "feral_druid_tank" && identity.Role == "tank");
    assert(I::DeclaresClassSpec(42, "feral_druid_tank") && !I::DeclaresClassSpec(42, "restoration_druid"));
    I::Forget(42);
    assert(!I::IsRegistered(42));
    std::printf("ok\n");
    return 0;
}
''')
    assert out.strip() == "ok"


def test_the_native_loader_reads_the_exact_spec_contract_value(tmp_path):
    """Re-review P2: the manifest loader locates `spec_contract` structurally. Null, a string, an object (even one
    wrapping a valid array) and an empty array are refused; only an absent property skips validation."""
    scenario = _scenarios()[FULL]
    step = next(step for step in scenario["route"] if step.get("spec_contract"))
    valid = builder.spec_contract(scenario, step)
    base = {"completion_contract": {"kind": "arrival", "items": [1, 2]}, "kind": "regroup", "route_node_id": "n"}
    cases = {
        "absent": (base, "ok:0"),
        "valid": ({**base, "spec_contract": valid}, "ok:10"),
        "null": ({**base, "spec_contract": None}, "bad:spec_contract_shape"),
        "string": ({**base, "spec_contract": "[1]"}, "bad:spec_contract_shape"),
        "object": ({**base, "spec_contract": {}}, "bad:spec_contract_shape"),
        "wrapped": ({**base, "spec_contract": {"rows": valid}}, "bad:spec_contract_shape"),
        "empty": ({**base, "spec_contract": []}, "bad:spec_contract_shape"),
        "row_missing_group": ({**base, "spec_contract": [{key: value for key, value in valid[0].items()
                                                          if key != "talent_group"}]},
                              "bad:spec_contract_row_field_missing"),
    }
    calls = "\n".join(f'    report("{name}", {_cpp_string(json.dumps(row))});' for name, (row, _) in cases.items())
    out = _run(tmp_path, r'''
#include "Bots/BotRaidSpecSwitch.h"
#include <cstdio>
static void report(char const* name, char const* text)
{
    std::vector<BotRaidSpecSwitch::ContractRow> rows;
    bool present = false;
    std::string error;
    bool const ok = BotRaidSpecSwitch::ParseRouteRowContract(text, rows, present, error);
    if (ok)
        std::printf("%s ok:%zu\n", name, rows.size());
    else
        std::printf("%s bad:%s\n", name, error.c_str());
    if (!present && !ok)
        std::printf("%s absent_but_invalid\n", name);
}
int main()
{
''' + calls + r'''
    report("unparsable_with_contract", "{\"spec_contract\": [");
    return 0;
}
''')
    got = dict(line.split(" ", 1) for line in out.splitlines())
    assert got == {**{name: expected for name, (_, expected) in cases.items()},
                   "unparsable_with_contract": "bad:spec_contract_route_row_unparsable"}
    manifest = _text("BotWorldPopulationMgrValidationRouteManifest.cpp")
    assert "BotRaidSpecSwitch::ParseRouteRowContract(" in manifest
    assert 'ExtractJsonArrayField(routeJson, "spec_contract")' not in manifest


def test_a_declared_but_null_empty_or_malformed_contract_is_refused():
    """Review P2: the builder never drops a declared contract silently."""
    scenario = _scenarios()[FULL]
    step = next(step for step in scenario["route"] if step.get("spec_contract"))
    row = step["spec_contract"][0]
    for broken in (None, [], "druid", {"roster_slot": 1}, [row, row], [{**row, "talent_group": "0"}],
                   [{**row, "role": "melee"}], [{**row, "talent_groups": None}], [{**row, "talent_group": 1,
                    "talent_groups": [group for group in row["talent_groups"] if group["talent_group"] != 1]}],
                   [{key: value for key, value in row.items() if key != "talent_group"}]):
        with pytest.raises(ValueError, match="spec_contract_(shape|row_invalid)"):
            builder.spec_contract(scenario, {**step, "spec_contract": broken})
    assert builder.spec_contract(scenario, {key: value for key, value in step.items() if key != "spec_contract"}) == []


def test_only_composition_regroup_rows_carry_a_contract():
    scenarios = _scenarios()
    for scenario_id, scenario in scenarios.items():
        for step in scenario.get("route") or []:
            contract = builder.spec_contract(scenario, step)
            assert bool(contract) == (scenario_id == FULL and step["node_id"].startswith("bwd.spec_switch.")), (
                scenario_id, step["node_id"])
    step = next(step for step in scenarios[FULL]["route"] if step.get("spec_contract"))
    with pytest.raises(ValueError, match="spec_contract_outside_composition_regroup"):
        builder.spec_contract(scenarios["blackwing_descent_10n"], step)
    with pytest.raises(ValueError, match="spec_contract_outside_composition_regroup"):
        builder.spec_contract(scenarios[FULL], {**step, "kind": "trash"})


def _text(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


def test_every_identity_reader_follows_the_active_talent_group():
    role = _text("BotWorldPopulationMgrCombatSupport.cpp")
    body = role[role.index("char const* BotWorldPopulationMgr::GetDungeonRole(Player* bot) const"):]
    assert body.index("BotActiveSpecIdentity::Resolve(") < body.index("GetLfgRoles")
    roster = _text("BotWorldPopulationMgrRoster.cpp")
    body = roster[roster.index("std::string BotWorldPopulationMgr::GetBotClassSpec(Player const* bot) const"):]
    assert body.index("BotActiveSpecIdentity::Resolve(") < body.index("character_bot_pool")
    profile = _text("BotClassSpecActionProfile.cpp")
    body = profile[profile.index("std::string InferSpecTag("):]
    assert body.index("BotActiveSpecIdentity::Resolve(") < body.index("PoolClassSpec(")
    runtime = _text("BotWorldPopulationMgrValidationCohortRuntime.cpp")
    assert "slot.Role = specSwitchIdentity ? activeIdentity.Role" in runtime
    assert "slot.ClassSpec = specSwitchIdentity ? activeIdentity.ClassSpec" in runtime
    assert "ActiveSpecContractRoleCounts(contractTanks, contractHealers, contractDps, specSwitchInProgress)" in runtime


def test_the_switch_is_wired_into_the_route_and_the_admission_receipt():
    arrival = _text("BotWorldPopulationMgrValidationRouteTerminalArrival.cpp")
    assert "if (HoldForSpecSwitch() || HoldForPrepullSetup())" in arrival
    manifest = _text("BotWorldPopulationMgrValidationRouteManifest.cpp")
    assert "BotRaidSpecSwitch::ParseRouteRowContract(" in manifest
    group = _text("BotWorldPopulationMgrValidationCohortGroup.cpp")
    drift = group[group.index("Admission gear is immutable for the whole attempt"):]
    assert drift.index("if (state.SpecSwitchPending)") < drift.index("EquippedGearManifestsEqual(")
    assert "bool BotWorldPopulationMgr::RefreezeAdmissionReceiptForSpecSwitch(" in group
    switch = _text("BotWorldPopulationMgrRaidSpecSwitch.cpp")
    assert "TryCastFriendlySpell(bot, bot, spellId, &failure)" in switch  # the member's own cast
    assert "bot->GetSession()->HandleEquipmentSetUse(packet);" in switch  # its own opcode handler
    assert "${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRaidSpecSwitch.cpp" in (
        ROOT / "src/server/game/CMakeLists.txt").read_text()


def test_the_runtime_marks_its_roster_scope_and_forgets_on_cleanup():
    runtime = _text("BotWorldPopulationMgrRaidRuntime.cpp")
    marker = '(HasValidationRouteSpecContracts() ? ",\\"spec_contract_scope\\":true" : "")'
    assert runtime.count(marker) == 4  # both runtime objects and both roster row emitters
    switch = _text("BotWorldPopulationMgrRaidSpecSwitch.cpp")
    assert "bool BotWorldPopulationMgr::HasValidationRouteSpecContracts() const" in switch
    cleanup = _text("BotMgrCleanup.cpp")
    body = cleanup[cleanup.index("void BotMgr::CleanupBot("):]
    assert body.index("BotActiveSpecIdentity::Forget(botGuid.GetCounter());") < body.index("_removingBots.insert")


def test_touched_sources_stay_below_the_module_limit():
    for name in ("BotRaidSpecSwitch.h", "BotActiveSpecIdentity.h", "BotWorldPopulationMgrRaidSpecSwitch.cpp",
                 "BotWorldPopulationMgrValidationCohortRuntime.cpp", "BotWorldPopulationMgrValidationCohortGroup.cpp",
                 "BotWorldPopulationMgrValidationRouteTerminalArrival.cpp", "BotWorldPopulationMgrBotState.h",
                 "BotWorldPopulationMgr.h", "BotWorldPopulationMgrValidationRouteManifest.cpp",
                 "BotWorldPopulationMgrRouteState.h", "BotWorldPopulationMgrRaidRuntime.cpp", "BotMgrCleanup.cpp"):
        assert len(_text(name).splitlines()) < 1000, name
