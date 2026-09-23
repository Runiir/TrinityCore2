"""Magmaw Mangle fidelity: threat wipe on seize, Sweltering Armor on release.

Evidence for the production change in boss_magmaw.cpp PassengerBoarded:
- Hotfix (2010-12-22), quoted by Warcraft Wiki "Magmaw": "Sweltering Armor is
  now properly applied to Magmaw's Mangle target once the debuff has faded,
  regardless of whether Magmaw was successfully impaled or not."
- WCL 10N MxFq7TRbvnjGY1hJ fight 22 and 25H FhcbnAmN9v7kr1VP fight 3 apply
  78199 at Mangle removal (ledger longer_wcl_followup.armor_application).
- Warcraft Wiki / Wowpedia ability text: Mangle "Completely wipes the tank's
  aggro"; 2011 guides (Jinxed Thoughts heroic guide, MMO-Champion thread
  848005) agree the wipe hits only the mangled tank.
The production member body is compiled against minimal stubs.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
BOSS = SCRIPTS / "boss_magmaw.cpp"
SHARED = SCRIPTS / "boss_magmaw_shared.h"
DBC = ROOT / "data/dbc/enUS"


def body(source: str, signature: str) -> str:
    start = source.index("{", source.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_seize_wipes_threat_and_release_applies_sweltering(tmp_path: Path) -> None:
    source = BOSS.read_text(encoding="utf-8")
    boarded = body(source, "void PassengerBoarded(Unit* passenger, int8 seatId, bool apply) override")
    unit = r'''
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
using uint32 = std::uint32_t;
using int8 = std::int8_t;
enum : uint32 { SPELL_MANGLE_2 = 78412, SPELL_SWELTERING_ARMOR = 78199,
    SPELL_MANGLE_DAMAGE = 89773, BROADCAST_TEXT_WHISPER_MANGLE = 48488 };
enum VehicleSeats { SEAT_MAGMAWS_PINCER_1 = 0, SEAT_MAGMAWS_PINCER_2 = 1, SEAT_MANGLE = 2 };
struct Player;
struct Unit {
    bool alive = true, combat = true, player = true;
    std::vector<std::string> log;
    bool IsAlive() const { return alive; }
    bool IsInCombat() const { return combat; }
    void CastSpell(Unit*, uint32 id, bool) { log.push_back("cast:" + std::to_string(id)); }
    void RemoveAurasDueToSpell(uint32 id) { log.push_back("remove:" + std::to_string(id)); }
    Player* ToPlayer();
};
struct Player : Unit {
    void Whisper(uint32, Player*, bool) { log.push_back("whisper"); }
};
Player* Unit::ToPlayer() { return player ? static_cast<Player*>(this) : nullptr; }
struct ThreatManager {
    std::vector<Unit*> reset;
    void ResetThreat(Unit* target) { reset.push_back(target); }
};
struct Magmaw : Unit {
    ThreatManager threat;
    ThreatManager& GetThreatManager() { return threat; }
};
struct Boss {
    Magmaw actor;
    Magmaw* me = &actor;
    void PassengerBoarded(Unit* passenger, int8 seatId, bool apply)
''' + boarded + r'''
};
using Log = std::vector<std::string>;
int main() {
    // Seize: Mangle seat aura and whisper, threat wiped, no armor yet.
    Boss seize; Player tank;
    seize.PassengerBoarded(&tank, SEAT_MANGLE, true);
    assert((tank.log == Log{ "cast:78412", "whisper" }));
    assert(seize.me->threat.reset.size() == 1 && seize.me->threat.reset[0] == &tank);

    // Impale or the 30 s timeout: Mangle fades on a living target in combat,
    // then Sweltering Armor is applied (WCL: within 1 ms of the removal).
    Boss release; Player released;
    release.PassengerBoarded(&released, SEAT_MANGLE, false);
    assert((released.log == Log{ "remove:89773", "remove:78412", "cast:78199" }));
    assert(release.me->threat.reset.empty());

    // Death in the seat (Mangled Lifeless or ticks): no armor on a corpse.
    Boss death; Player dead; dead.alive = false;
    death.PassengerBoarded(&dead, SEAT_MANGLE, false);
    assert((dead.log == Log{ "remove:89773", "remove:78412" }));

    // Evade/wipe: _EnterEvadeMode has already stopped combat.
    Boss evade; Player wiped; evade.me->combat = false;
    evade.PassengerBoarded(&wiped, SEAT_MANGLE, false);
    assert((wiped.log == Log{ "remove:89773", "remove:78412" }));

    // Magmaw dead: no armor.
    Boss killed; Player freed; killed.me->alive = false;
    killed.PassengerBoarded(&freed, SEAT_MANGLE, false);
    assert((freed.log == Log{ "remove:89773", "remove:78412" }));

    // Pincer seats are untouched: no Mangle, armor or threat change.
    Boss pincer; Player rider;
    pincer.PassengerBoarded(&rider, SEAT_MAGMAWS_PINCER_1, true);
    pincer.PassengerBoarded(&rider, SEAT_MAGMAWS_PINCER_2, false);
    assert(rider.log.empty() && pincer.me->threat.reset.empty());
    return 0;
}
'''
    cpp = tmp_path / "mangle_release.cpp"
    exe = tmp_path / "mangle_release"
    cpp.write_text(unit, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_release_paths_reach_the_release_branch_in_the_right_state() -> None:
    source = BOSS.read_text(encoding="utf-8")
    # Sweltering Armor is cast only in the release branch and cleared from
    # players on evade/wipe, like the parasite auras.
    assert source.count("SPELL_SWELTERING_ARMOR") == 2
    assert source.count("CastSpell(passenger, SPELL_SWELTERING_ARMOR, true)") == 1
    boarded = body(source, "void PassengerBoarded(Unit* passenger, int8 seatId, bool apply) override")
    release = boarded[boarded.index("else"):]
    assert "passenger->CastSpell(passenger, SPELL_SWELTERING_ARMOR, true);" in release
    assert release.index("RemoveAurasDueToSpell(SPELL_MANGLE_2)") < release.index("SPELL_SWELTERING_ARMOR")

    # Impale ejects the seat-2 passenger (Eject Passenger 3 -> seat 2) while
    # Magmaw is alive and engaged, so a successful hook releases with armor.
    expose = source[source.index("case ACTION_EXPOSE_HEAD:"):source.index("case ACTION_COVER_HEAD:")]
    assert "DoCastSelf(SPELL_EJECT_PASSENGER_3, true);" in expose
    # Evade clears combat before it ejects the Mangle seat, so a wipe does not.
    evade = body(source, "void EnterEvadeMode(EvadeReason /*why*/) override")
    parasite = evade.index("DoRemoveAurasDueToSpellOnPlayers(SPELL_PARASITIC_INFECTION_PERIODIC_DAMAGE);")
    armor = evade.index("instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_SWELTERING_ARMOR);")
    # After the eject (which applies nothing once combat has stopped).
    assert evade.index("DoCastSelf(SPELL_EJECT_PASSENGER_3, true);") < parasite < armor
    assert evade.index("_EnterEvadeMode();") < evade.index("DoCastSelf(SPELL_EJECT_PASSENGER_3, true);")
    creature_ai = (ROOT / "src/server/game/AI/CreatureAI.cpp").read_text(encoding="utf-8")
    assert "me->CombatStop(true);" in body(creature_ai, "bool CreatureAI::_EnterEvadeMode(EvadeReason /*why*/)")
    generic = (ROOT / "src/server/scripts/Spells/spell_generic_vehicles_tournament.cpp").read_text(encoding="utf-8")
    assert "case SPELL_GEN_EJECT_PASSENGER_3:\n                    seatId = 2;" in generic
    assert "SPELL_EJECT_PASSENGER_3                     = 95204," in SHARED.read_text(encoding="utf-8")


@pytest.mark.skipif(not (DBC / "Spell.dbc").exists(), reason="pinned DBC not extracted")
def test_client_data_behind_the_release_timing() -> None:
    sys.path.insert(0, str(ROOT))
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    spells = {r[0]: r for r in load_wdbc_values(
        DBC / "Spell.dbc", "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii")}
    durations = {r[0]: r[1] for r in load_wdbc_values(DBC / "SpellDuration.dbc", "niii")}
    effects: dict[int, list[list[int]]] = {}
    for row in load_wdbc_values(DBC / "SpellEffect.dbc", "nifiiiffiiiiiifiifiiiiiiiix"):
        effects.setdefault(row[24], []).append(row)

    # Sweltering Armor: armor (resistance school 1) -50% for 90 s.
    armor = effects[78199][0]
    assert (armor[3], armor[5], armor[12]) == (101, -50, 1)
    assert durations[spells[78199][13]] == 90000
    # Mangle 89773: 30 s periodic physical aura, 2 s period, 10N roll
    # 110,464-128,377; it seats the target through Ride Vehicle 78360 (seat 3-1).
    tick = next(e for e in effects[89773] if e[25] == 0)
    assert (tick[3], tick[4], tick[5] + 1, tick[5] + tick[9]) == (3, 2000, 110464, 128377)
    assert durations[spells[89773][13]] == 30000
    assert any(e[1] == 140 and e[21] == 78360 for e in effects[89773])
    ride = next(e for e in effects[78360] if e[3] == 236)
    assert ride[5] == 3

    # Magmaw's vehicle 834 seat 2 carries CAN_ATTACK (0x4000): the seized tank
    # may cast, so its own defensives are lawful while mangled.
    vehicles = {r[0]: r for r in load_wdbc_values(
        DBC / "Vehicle.dbc", "niffffiiiiiiiifffffffffffffffssssfifiiii")}
    seats = {r[0]: r for r in load_wdbc_values(
        DBC / "VehicleSeat.dbc",
        "niiffffffffffiiiiiifffffffiiifffiiiiiiiffiiiiiffffffffffffiiiiiiii")}
    seat = seats[vehicles[834][6 + 2]]
    assert seat[1] & 0x4000
    assert not seat[1] & 0x100000  # passenger stays selectable/attackable
