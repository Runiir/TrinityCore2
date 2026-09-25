"""Magmaw duties by capability: the accepted roster is unchanged, the canonical composition is covered.

The accepted roster, its code-derived owners and its evidence-confirmed baiter
alternation come from tests/fixtures/magmaw_full_roster_duties_v1.json (kill
evidence b5-d1898555). The canonical rosters come from the raid-shard plan
(tools.raid_program.raid_shard_plan), so a composition change is seen here.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAGMAW = "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
FIXTURE = ROOT / "tests/fixtures/magmaw_full_roster_duties_v1.json"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
INCLUDES = ["src/server/game", "src/server/game/Entities/Object", "src/common", "src/common/Utilities",
            "src/common/Logging", "src/common/Debugging"]

HEADER = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBaiterRotation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDutyCapabilities.h"
#include <cstdio>
#include <string>

using namespace BotEncounter;

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

inline ActorSnapshot Player(uint32 guid, char const* role, char const* spec)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Kind = ActorKind::Player;
    player.Role = role;
    player.ClassSpec = spec;
    player.Position = { 30.0f, 0.0f, 210.0f };
    player.HealthPct = 100.0f;
    player.Alive = true;
    return player;
}

inline Blackboard Board(char const* cohort, std::vector<ActorSnapshot> players)
{
    Blackboard board;
    board.CurrentScope = Scope{ cohort, 7, 0, 4, "bwd.magmaw.encounter", 669, 1, "magmaw" };
    board.Revision = 21;
    board.ObservedAtMs = 1790220781549;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Players = std::move(players);
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::BossEntry, uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = boss.Attackable = boss.Selectable = boss.InCombat = true;
    board.Hostiles = { boss };
    return board;
}

inline int Fail(char const* what, std::string const& json)
{
    std::fprintf(stderr, "FAIL %s: %s\n", what, json.c_str());
    return 1;
}

// Drives the shared rotation through completed parasite waves: a live pillar
// is a wave, then QuietBoundaryMs without one ends it and picks the next baiter.
inline std::string Waves(Blackboard board, int waves)
{
    ActorSnapshot pillar;
    pillar.Guid = ObjectGuid(HighGuid::Unit, MagmawBaiterRotation::PillarEntry, uint32(77));
    pillar.Entry = MagmawBaiterRotation::PillarEntry;
    pillar.Alive = true;
    uint64 revision = 100;
    for (int wave = 0; wave < waves; ++wave)
    {
        board.Summons = { pillar };
        board.Revision = ++revision;
        board.ObservedAtMs += 1000;
        MagmawBaiterRotationRegistry::ObserveBaiters(board);
        board.Summons.clear();
        for (uint64 quietMs : { uint64(1000), uint64(MagmawBaiterRotation::QuietBoundaryMs) })
        {
            board.Revision = ++revision;
            board.ObservedAtMs += quietMs;
            MagmawBaiterRotationRegistry::ObserveBaiters(board);
        }
    }
    std::optional<MagmawBaiterRotation> const rotation =
        MagmawBaiterRotationRegistry::Find(board.CurrentScope.Key());
    std::string history;
    for (MagmawBaiterRotation::Assignment const& row : rotation->History)
        history += std::to_string(row.Wave) + ":" + std::to_string(row.Mage.GetCounter()) + ":"
            + MagmawBaiterRotation::ToString(row.Why) + ";";
    return history;
}
'''


def _run(tmp_path: Path, body: str) -> None:
    source, binary = tmp_path / "program.cpp", tmp_path / "program"
    source.write_text(HEADER + body)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), str(ROOT / MAGMAW / "BotMagmawDutyPlan.cpp"), "-o", str(binary)],
                   check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def _players(rows: list[tuple[int, str, str]]) -> str:
    return "{ " + ", ".join(f'Player({guid}, "{role}", "{spec}")' for guid, role, spec in rows) + " }"


def _plan_rows(shard: dict) -> list[tuple[int, str, str]]:
    return [(bot["character_guid"], bot["role"], bot["class_spec"]) for bot in shard["bots"]]


@pytest.fixture(scope="module")
def canonical() -> dict:
    from tools.raid_program.raid_shard_scenarios import build_plan
    plan = build_plan(COMPOSITION)
    return {shard["cohort_id"]: shard for shard in plan["shards"]}


def test_accepted_roster_duties_match_the_kill_evidence_fixture(tmp_path):
    fixture = json.loads(FIXTURE.read_text())
    roster = [(row["guid"], row["role"], row["class_spec"]) for row in fixture["roster_identity"]]
    confirmed = {key: value["value"] for key, value in fixture["evidence_confirmed"].items()}
    kills = [kill["baiter_rotation"]["history"] for kill in fixture["per_kill"].values()]
    three_waves = next(history for history in kills if len(history) == 3)
    expected_history = "".join(f"{row['wave']}:{row['mage_guid']}:{row['reason']};" for row in three_waves)
    # Evidence-confirmed owners plus the code-derived ones the fixture names (hook riders, pull tank,
    # Bloodlust owner), which tests/test_magmaw_duty_plan.py pins from the same selectors.
    assert fixture["code_derived_not_in_evidence"] == ["hook_riders", "pull_tank", "bloodlust_owner"]
    receipt = ('{\\"applies\\":true,\\"revision\\":21,\\"pull_tank\\":30002,'
               f'\\"bait_mage\\":{confirmed["baiter_primary_mage_guid"]},\\"bait_hunter\\":{confirmed["baiter_hunter_guid"]},'
               '\\"hook_riders\\":[30007,30008],'
               f'\\"mushroom_owners\\":[{",".join(map(str, confirmed["wild_mushroom_casters"]))}],'
               '\\"bloodlust_owner\\":30010}')
    _run(tmp_path, rf'''
int main()
{{
    Blackboard const board = Board("fixture", {_players(roster)});
    std::string const receipt = "{receipt}";
    std::string json = BuildMagmawDutyPlanStatusJson(&board);
    if (json != receipt)
        return Fail("accepted receipt changed", json);
    // Capability-only duties: one tank (no swap), Rebirth from both druids, Raise Ally from the DK.
    json = MagmawDutyPlanCapabilityJson(BuildMagmawDutyPlan(board));
    if (json != receipt.substr(0, receipt.size() - 1)
            + ",\"tank_swap_owner\":0,\"battle_res_casters\":[30001,30002,30003]}}")
        return Fail("capability receipt", json);
    // The accepted alternation: {expected_history}
    std::string const history = Waves(board, 2);  // two completed waves, three assignments
    if (history != "{expected_history}")
        return Fail("baiter alternation", history);
    std::optional<MagmawBaiterRotation> rotation = MagmawBaiterRotationRegistry::Find(board.CurrentScope.Key());
    if (rotation->PrimaryMage.GetCounter() != {confirmed["baiter_primary_mage_guid"]}
        || rotation->AlternateMage.GetCounter() != {confirmed["baiter_alternate_mage_guid"]}
        || rotation->Hunter.GetCounter() != {confirmed["baiter_hunter_guid"]})
        return Fail("rotation roster", history);
    // The old fixed-spec selectors and the capability selectors agree on every accepted member.
    for (ActorSnapshot const& member : board.Players)
    {{
        bool const mage = member.Role == "dps" && member.ClassSpec == "fire_mage";
        bool const hunter = member.Role == "dps"
            && (member.ClassSpec == "marksmanship_hunter" || member.ClassSpec == "survival_hunter");
        if (MagmawBaiterRotation::IsBaitMage(member) != mage || MagmawBaiterRotation::IsBaitHunter(member) != hunter
            || MagmawDutyCapabilities::IsMushroomCaster(member.ClassSpec) != (member.ClassSpec == "balance_druid"))
            return Fail("selector parity", member.ClassSpec);
    }}
    if (MagmawBloodlust::FindBloodlustOwner(board) != MagmawBloodlust::FindSingleElementalShaman(board))
        return Fail("bloodlust parity", "");
    return 0;
}}
''')


def test_canonical_magmaw_shard_has_an_owner_for_every_duty(tmp_path, canonical):
    shard = canonical["blackwing_descent_10n_magmaw_c0"]
    guid = {bot["character_key"]: bot["character_guid"] for bot in shard["bots"]}
    assert shard["role_counts"] == {"tank": 1, "healer": 2, "dps": 7}
    receipt = ('{\\"applies\\":true,\\"revision\\":21,'
               f'\\"pull_tank\\":{guid["death_knight"]},\\"bait_mage\\":{guid["mage"]},\\"bait_hunter\\":{guid["hunter"]},'
               f'\\"hook_riders\\":[{guid["paladin_ret"]},{guid["rogue"]}],\\"mushroom_owners\\":[{guid["druid"]}],'
               f'\\"bloodlust_owner\\":{guid["shaman"]},\\"tank_swap_owner\\":0,'
               f'\\"battle_res_casters\\":[{guid["death_knight"]},{guid["druid"]}]}}')
    _run(tmp_path, rf'''
int main()
{{
    Blackboard const board = Board("canonical-c0", {_players(_plan_rows(shard))});
    std::string const json = MagmawDutyPlanCapabilityJson(BuildMagmawDutyPlan(board));
    if (json != "{receipt}")
        return Fail("canonical plan", json);
    // IsPillarBaiter needs both lanes: the Beast Mastery Hunter now holds the Disengage lane.
    std::pair<ObjectGuid, ObjectGuid> const baiters = MagmawParasitePolicy::ResolveFixedBaiters(board);
    if (baiters.first.GetCounter() != {guid["mage"]} || baiters.second.GetCounter() != {guid["hunter"]})
        return Fail("fixed baiters", std::to_string(baiters.second.GetCounter()));
    // One Fire Mage keeps every wave.
    std::string const history = Waves(board, 2);
    if (history != "1:{guid["mage"]}:initial;2:{guid["mage"]}:single_mage;3:{guid["mage"]}:single_mage;")
        return Fail("single-mage rotation", history);
    if (MagmawDutyCapabilities::BaitMobilitySpell("beast_mastery_hunter") != 781
        || MagmawDutyCapabilities::BaitMobilitySpell("fire_mage") != 1953
        || MagmawDutyCapabilities::BaitMobilitySpell("arcane_mage") != 0
        || MagmawDutyCapabilities::BaitMobilitySpell("retribution_paladin") != 0)
        return Fail("mobility spells", "");
    return 0;
}}
''')


def test_three_healer_and_two_tank_variants_keep_owners(tmp_path, canonical):
    """Resto shaman (three healers) still owns Bloodlust; a Feral second tank owns the tank swap."""
    magmaw = canonical["blackwing_descent_10n_magmaw_c0"]
    resto = [(guid, "healer", "restoration_shaman") if spec == "elemental_shaman" else (guid, role, spec)
             for guid, role, spec in _plan_rows(magmaw)]
    guid = {bot["character_key"]: bot["character_guid"] for bot in magmaw["bots"]}
    full = canonical["blackwing_descent_10n_full_c0"]
    full_guid = {bot["character_key"]: bot["character_guid"] for bot in full["bots"]}
    assert {bot["class_spec"] for bot in full["bots"]} >= {"feral_druid_tank", "restoration_shaman"}
    _run(tmp_path, rf'''
int main()
{{
    MagmawDutyPlan const three = BuildMagmawDutyPlan(Board("three-healer", {_players(resto)}));
    if (three.BloodlustOwner.GetCounter() != {guid["shaman"]} || three.HookRiders.size() != 2
        || three.HookRiders[0].GetCounter() != {guid["paladin_ret"]} || three.HookRiders[1].GetCounter() != {guid["rogue"]})
        return Fail("three healers", MagmawDutyPlanCapabilityJson(three));
    MagmawDutyPlan const two = BuildMagmawDutyPlan(Board("two-tank", {_players(_plan_rows(full))}));
    if (two.PullTank.GetCounter() != {full_guid["death_knight"]}
        || two.TankSwapOwner.GetCounter() != {full_guid["druid"]}
        || !two.MushroomOwners.empty() || two.BloodlustOwner.GetCounter() != {full_guid["shaman"]})
        return Fail("two tanks", MagmawDutyPlanCapabilityJson(two));
    // Ambiguous or absent shamans leave Bloodlust unowned.
    using Candidate = MagmawBloodlust::BloodlustCandidate;
    ObjectGuid const a(HighGuid::Player, uint32(1)), b(HighGuid::Player, uint32(2));
    if (MagmawBloodlust::SelectBloodlustOwner({{ {{ a, "healer", "restoration_shaman" }}, {{ b, "healer", "restoration_shaman" }} }})
        || MagmawBloodlust::SelectBloodlustOwner({{ {{ a, "dps", "enhancement_shaman" }}, {{ b, "dps", "elemental_shaman" }} }}) != b
        || MagmawBloodlust::SelectBloodlustOwner({{ {{ a, "dps", "enhancement_shaman" }}, {{ b, "healer", "restoration_shaman" }} }}) != a
        || MagmawBloodlust::SelectBloodlustOwner(std::vector<Candidate>{{ {{ a, "dps", "fire_mage" }} }}))
        return Fail("bloodlust selection", "");
    return 0;
}}
''')


BLOODLUST_SCENARIOS = {
    "blackwing_descent_10n_magmaw_diagnostic": True,
    "blackwing_descent_10n_magmaw_c0_diagnostic": True,
    "blackwing_descent_10n_magmaw_c12_diagnostic": True,
    "blackwing_descent_10n_magmaw_c_diagnostic": False,
    "blackwing_descent_10n_magmaw_cx_diagnostic": False,
    "blackwing_descent_10n_maloriak_c0_diagnostic": False,
    "blackwing_descent_10n_magmaw_c0": False,
    "blackwing_descent_25n_magmaw_c0_diagnostic": False,
}


def test_bloodlust_scenario_gate_admits_every_canonical_magmaw_copy(tmp_path):
    checks = "\n".join(
        f'    if (MagmawBloodlust::IsMagmawBloodlustScenario("{scenario}") != {"true" if allowed else "false"})\n'
        f'        return Fail("scenario gate", "{scenario}");' for scenario, allowed in BLOODLUST_SCENARIOS.items())
    _run(tmp_path, "int main()\n{\n" + checks + "\n    return 0;\n}\n")


def test_duty_selectors_name_no_fixed_spec_outside_the_capability_header():
    """Admission to a duty reads BotMagmawDutyCapabilities.h, not spec strings scattered in selectors."""
    selectors = {
        "BotMagmawBaiterRotation.h": ('"fire_mage"', '"marksmanship_hunter"', '"survival_hunter"'),
        "BotAdaptiveMagmawStrategyHook.h": ('"balance_druid"',),
        "BotMagmawDutyPlan.cpp": ('"balance_druid"', "FindSingleElementalShaman"),
        "BotMagmawCoordinatorAssignments.cpp": ('"fire_mage"', '"marksmanship_hunter"', '"survival_hunter"',
                                                '"elemental_shaman"'),
        "BotMagmawDirectionalMobilityPolicy.h": ('"fire_mage"', '"marksmanship_hunter"', '"survival_hunter"'),
        "BotMagmawBalanceMushroomDuty.h": ('"balance_druid"',),
    }
    for name, literals in selectors.items():
        text = (ROOT / MAGMAW / name).read_text(encoding="utf-8")
        for literal in literals:
            assert literal not in text, (name, literal)
    for name in ("BotMagmawDutyCapabilities.h", "BotMagmawBloodlust.h", "BotMagmawDutyPlan.cpp",
                 "BotMagmawCoordinatorAssignments.cpp", "BotMagmawBaiterRotation.h"):
        assert len((ROOT / MAGMAW / name).read_text(encoding="utf-8").splitlines()) < 1000
