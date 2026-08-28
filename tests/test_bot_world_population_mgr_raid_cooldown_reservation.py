from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_raid_route_reserves_trash_cooldowns_and_releases_on_boss_combat(
    tmp_path: Path,
) -> None:
    source = tmp_path / "raid_cooldown_reservation.cpp"
    binary = tmp_path / "raid_cooldown_reservation"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"

#include <cassert>
#include <string>

using namespace BotRaidCooldownReservation;

RouteContext Trash()
{
    RouteContext route;
    route.ValidationRouteEnabled = true;
    route.RaidInstance = true;
    route.RouteKind = "trash";
    route.NodeKind = "trash_cluster";
    route.EncounterPhase = "formation";
    return route;
}

int main()
{
    RouteContext trash = Trash();
    CandidateContext fireElemental{
        BotCombatActionCategory::OffensiveCooldown,
        "fire_elemental_totem,opener,long_cooldown,wowsims_66843"};
    CandidateContext combustion{
        BotCombatActionCategory::OffensiveCooldown,
        "combustion,burn"};
    CandidateContext combatPotion{
        BotCombatActionCategory::UseItem,
        "volcanic_potion,consumable,burst"};
    CandidateContext bloodlust{
        BotCombatActionCategory::Buff,
        "bloodlust,raid_lust"};

    assert(std::string(ReservationReason(trash, fireElemental))
        == "raid_offensive_guardian_reserved");
    assert(std::string(ReservationReason(trash, combustion))
        == "raid_offensive_cooldown_reserved");
    assert(std::string(ReservationReason(trash, combatPotion))
        == "raid_combat_potion_reserved");
    assert(std::string(ReservationReason(trash, bloodlust))
        == "raid_bloodlust_reserved");

    CandidateContext tankEmergency{
        BotCombatActionCategory::Defensive,
        "guardian_of_ancient_kings,major_defensive,tank"};
    CandidateContext healerEmergency{
        BotCombatActionCategory::OffensiveCooldown,
        "spirit_link_totem,healing_cooldown"};
    assert(ReservationReason(trash, tankEmergency) == nullptr);
    assert(ReservationReason(trash, healerEmergency) == nullptr);

    RouteContext boss = trash;
    boss.RouteKind = "boss";
    boss.NodeKind = "boss";
    boss.EncounterInProgress = true;
    boss.EncounterPhase = "combat";
    assert(ReservationReason(boss, fireElemental) == nullptr);
    assert(ReservationReason(boss, combustion) == nullptr);

    RouteContext bossPrepull = boss;
    bossPrepull.EncounterInProgress = false;
    bossPrepull.EncounterPhase = "formation";
    assert(std::string(ReservationReason(bossPrepull, fireElemental))
        == "raid_offensive_guardian_reserved");

    bossPrepull.ContractAllowsReservedCooldowns = true;
    assert(ReservationReason(bossPrepull, fireElemental) == nullptr);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/shared"),
            "-I",
            str(ROOT / "src/common"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
