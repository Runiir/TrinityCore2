"""Icebound Fortitude is kept on the last trash node for Magmaw's first Mangle.

Evidence: in all six base-0891a99 / bundle1-b8a539b kills the Blood tank's
Icebound Fortitude was "cooldown_not_ready" for the whole Magmaw encounter.
In bundle1 kill 1 the tank fell to 27.6% on the Drudge pack 41 s before the
pull, where the trash recovery lane casts Icebound at 55%; 180 s later it is
still down at the 90 s Mangle. The generic rule: on the trash node right
before a boss with a declared opening hit, a Defensive whose own cooldown
exceeds that hit's time after pull is reserved. On the boss node, a Defensive
whose cooldown exceeds the big-hit spacing is kept between big hits while the
boss's native timer runs (the Mangle helper casts it), released while the hit
is in progress (timer at 0 or the tank held in the boss's seat) and at 35%
health or less.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
RESERVATION = BOTS / "BotWorldPopulationMgrRaidCooldownReservation.h"
GATE = BOTS / "BotWorldPopulationMgrValidationRecoveryGate.cpp"
RESOLVER = BOTS / "BotWorldPopulationMgrCombatResolver.cpp"
SPELL = BOTS / "BotWorldPopulationMgrCombatSpell.cpp"
TRASH = BOTS / "BotWorldPopulationMgrValidationRouteTankTrashRecovery.cpp"
MANAGER = BOTS / "BotWorldPopulationMgr.h"
TIMING = BOTS / "Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlustTiming.h"
BOSS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp"
SCENARIOS = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
DBC = ROOT / "data/dbc/enUS"


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
                return source[brace + 1:index]
    raise AssertionError(signature)


def test_reservation_rule(tmp_path: Path) -> None:
    source = tmp_path / "boss_defensive_reservation.cpp"
    binary = tmp_path / "boss_defensive_reservation"
    source.write_text(r'''
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include <cassert>
#include <cstring>
using namespace BotRaidCooldownReservation;
int main()
{
    assert(BossOpeningHitAfterPullMs("boss", "bwd.magmaw.encounter") == 90000);
    assert(BossOpeningHitAfterPullMs("trash", "bwd.magmaw.encounter") == 0);
    assert(BossOpeningHitAfterPullMs("boss", "bwd.chimaeron.encounter") == 0);

    RouteContext trash{true, true, false, false, "trash", "trash", ""};
    char const* reserved = BossDefensiveReservationReason(trash, 90000,
        BotCombatActionCategory::Defensive, 180000);
    assert(reserved && std::strcmp(reserved, "raid_boss_defensive_reserved") == 0);
    // Back in time (Vampiric Blood, Bone Shield: 60 s): trash keeps it.
    assert(!BossDefensiveReservationReason(trash, 90000, BotCombatActionCategory::Defensive, 60000));
    assert(!BossDefensiveReservationReason(trash, 90000, BotCombatActionCategory::Defensive, 90000));
    // Only Defensive rows; Death Strike (Mitigation) and heals are untouched.
    assert(!BossDefensiveReservationReason(trash, 90000, BotCombatActionCategory::Mitigation, 180000));
    // No declared next boss hit, a boss node, outside the validation route
    // or outside a raid: nothing is reserved.
    assert(!BossDefensiveReservationReason(trash, 0, BotCombatActionCategory::Defensive, 180000));
    RouteContext boss{true, true, true, false, "boss", "boss", "combat"};
    assert(!BossDefensiveReservationReason(boss, 90000, BotCombatActionCategory::Defensive, 180000));
    RouteContext free{false, true, false, false, "trash", "trash", ""};
    assert(!BossDefensiveReservationReason(free, 90000, BotCombatActionCategory::Defensive, 180000));
    RouteContext dungeon{true, false, false, false, "trash", "trash", ""};
    assert(!BossDefensiveReservationReason(dungeon, 90000, BotCombatActionCategory::Defensive, 180000));
    // The existing emergency exemption still leaves defensives alone.
    assert(!ReservationReason(trash, { BotCombatActionCategory::Defensive, "icebound_fortitude" }));

    // Boss node: Icebound (3 min) cannot cover two Mangles 90-95 s apart.
    BossOpeningHit const* magmaw = FindBossOpeningHit("bwd.magmaw.encounter");
    assert(magmaw && magmaw->AfterPullMs == 90000 && magmaw->TimerSpellId == 88253);
    assert(!FindBossOpeningHit("bwd.magmaw.drudges"));
    BossHitTimer running{true, false};
    char const* held = BossHitDefensiveReservationReason(boss, 90000, running, 0.60f,
        BotCombatActionCategory::Defensive, 180000);
    assert(held && std::strcmp(held, "raid_boss_big_hit_defensive_reserved") == 0);
    // Vampiric Blood / Bone Shield come back between Mangles: never held.
    assert(!BossHitDefensiveReservationReason(boss, 90000, running, 0.60f,
        BotCombatActionCategory::Defensive, 60000));
    // Released during the hit, in an emergency, without a native timer, and
    // before the encounter is engaged.
    assert(!BossHitDefensiveReservationReason(boss, 90000, BossHitTimer{true, true}, 0.60f,
        BotCombatActionCategory::Defensive, 180000));
    assert(!BossHitDefensiveReservationReason(boss, 90000, running, 0.35f,
        BotCombatActionCategory::Defensive, 180000));
    assert(!BossHitDefensiveReservationReason(boss, 90000, BossHitTimer{false, false}, 0.60f,
        BotCombatActionCategory::Defensive, 180000));
    RouteContext staging{true, true, false, false, "boss", "boss", ""};
    assert(!BossHitDefensiveReservationReason(staging, 90000, running, 0.60f,
        BotCombatActionCategory::Defensive, 180000));
    assert(!BossHitDefensiveReservationReason(trash, 90000, running, 0.60f,
        BotCombatActionCategory::Defensive, 180000));
    assert(!BossHitDefensiveReservationReason(boss, 90000, running, 0.60f,
        BotCombatActionCategory::Mitigation, 180000));
    return 0;
}
''', encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_opening_hit_is_the_native_first_mangle() -> None:
    header = text(RESERVATION)
    assert '{ "bwd.magmaw.encounter", 90000, 88253 },' in header
    assert "constexpr uint32 MassiveCrashSpell = 88253;" in text(TIMING)
    engage = function_body(text(BOSS), "void JustEngagedWith(Unit* who)")
    assert "events.ScheduleEvent(EVENT_MANGLE, 1min + 30s, 0, PHASE_COMBAT);" in engage
    assert "constexpr uint32 NativeFirstMangleAfterPullMs = 90000;" in text(TIMING)
    # The route puts trash directly before the encounter in both scenarios.
    scenarios = json.loads(text(SCENARIOS))
    for scenario in scenarios["scenarios"] + scenarios["diagnostic_scenarios"]:
        nodes = [(node.get("node_id"), node.get("kind")) for node in scenario.get("route", [])]
        if ("bwd.magmaw.encounter", "boss") in nodes:
            index = nodes.index(("bwd.magmaw.encounter", "boss"))
            assert nodes[index - 1] == ("bwd.magmaw.drudges", "trash")


def test_route_helper_and_every_trash_defensive_path_use_the_rule() -> None:
    gate = text(GATE)
    next_hit = function_body(gate, "uint32 BotWorldPopulationMgr::NextValidationRouteBossOpeningHitMs() const")
    assert 'Cohort().Config.ValidationRouteKind != "trash"' in next_hit
    assert "Party().ValidationRouteManifestIndex + 1" in next_hit
    assert "BossOpeningHitAfterPullMs(\n        next.Kind, next.NodeId)" in next_hit
    reserve = function_body(gate, "char const* BotWorldPopulationMgr::BossDefensiveReservationReason(")
    assert "std::max(spellInfo->RecoveryTime, spellInfo->CategoryRecoveryTime)" in reserve
    assert "NextValidationRouteBossOpeningHitMs()" in reserve
    # Boss node: the boss's own native timer, seat hold and current health.
    assert "actor.FindMechanicTimer(hit->TimerSpellId)" in reserve
    assert "native->Source == BotEncounter::FactSource::NativeInstanceState" in reserve
    assert "native->SequenceActive || !native->RemainingMs" in reserve
    assert "bot->GetVehicleBase()->GetGUID() == actor.Guid" in reserve
    assert "BotWorldPopulationMgrNativeHelpers::UnitHealthPct(bot)" in reserve
    manager = text(MANAGER)
    assert "uint32 NextValidationRouteBossOpeningHitMs() const;" in manager
    assert "char const* BossDefensiveReservationReason(Player const* bot, uint32 defensiveSpellId) const;" in manager

    # Profile rows (Icebound's 65% row) in both candidate paths.
    resolver = text(RESOLVER)
    assert re.search(r"candidate\.Category == BotCombatActionCategory::Defensive\)\s*"
                     r"if \(char const\* bossReserve = BossDefensiveReservationReason\("
                     r"bot, candidate\.ResolvedSpellId\)\)", resolver)
    spell = text(SPELL)
    assert re.search(r"candidate\.Category == BotCombatActionCategory::Defensive\)\s*"
                     r"if \(char const\* bossReserve = BossDefensiveReservationReason\("
                     r"bot, candidate\.SpellId\)\)", spell)
    # The trash recovery lane's direct 55% Icebound cast.
    trash = text(TRASH)
    ibf = trash[trash.index("if (UnitHealthPct(bot) <= 0.55f && bot->HasSpell(48792)"):]
    ibf = ibf[:ibf.index("TryCastFriendlySpell(bot, bot, 48792)")]
    assert "!Manager.BossDefensiveReservationReason(bot, 48792)" in ibf
    for path in (RESERVATION, GATE, RESOLVER, SPELL, TRASH, MANAGER):
        assert len(text(path).splitlines()) < 1000, path


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_only_icebound_is_long_enough_to_be_reserved_for_magmaw() -> None:
    sys.path.insert(0, str(ROOT))
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    spells = {r[0]: r for r in load_wdbc_values(
        DBC / "Spell.dbc", "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii")}
    cooldowns = {r[0]: r for r in load_wdbc_values(DBC / "SpellCooldowns.dbc", "diii")}

    def cooldown(spell_id: int) -> int:
        row = cooldowns[spells[spell_id][37]]
        return max(row[1], row[2])

    # Icebound Fortitude 3 min > 90 s: reserved.  Vampiric Blood and Bone
    # Shield (1 min) return before the first Mangle: trash keeps them.
    assert cooldown(48792) == 180000 > 90000
    assert cooldown(55233) == 60000 <= 90000
    assert cooldown(49222) == 60000 <= 90000
