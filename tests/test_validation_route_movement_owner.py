from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
CONTRACT = BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.h"
PRODUCER = BOT_DIR / "BotWorldPopulationMgrValidationRouteMovementCheck.cpp"


def test_configured_hazard_owner_crosses_production_classifier(
    tmp_path: Path,
) -> None:
    producer = PRODUCER.read_text(encoding="utf-8")
    assert "SelectValidationRouteMovementOwner(" in producer
    assert "configuredHazard, bot->IsInCombat()" in producer
    assert "movementLease.Owner, movementLease.Priority" in producer

    source = tmp_path / "validation_route_movement_owner.cpp"
    binary = tmp_path / "validation_route_movement_owner"
    source.write_text(
        r'''
#include "Bots/BotWorldPopulationMgrValidationRouteMovementCheck.h"

#include <cassert>

int main()
{
    using namespace BotMovementArbitration;
    using namespace BotWorldPopulationMgrValidationRoute;

    // V97 receipt 2: a configured hazard while the actor is in combat is
    // lethal-safety movement, not ordinary combat-range or route traversal.
    MovementLease const configuredInCombat =
        SelectValidationRouteMovementOwner(true, true);
    assert(configuredInCombat.Owner == Owner::Hazard);
    assert(configuredInCombat.Priority == Priority::Hazard);

    // Adjacent ordinary in-combat movement retains the compatibility
    // adapter's existing CombatRange/Combat classification.
    MovementLease const ordinaryInCombat =
        SelectValidationRouteMovementOwner(false, true);
    assert(ordinaryInCombat.Owner == Owner::CombatRange);
    assert(ordinaryInCombat.Priority == Priority::Combat);

    // An absent configured-hazard identity does not manufacture an explicit
    // owner outside combat; the established adapter remains authoritative.
    MovementLease const ordinaryOutOfCombat =
        SelectValidationRouteMovementOwner(false, false);
    assert(ordinaryOutOfCombat.Owner == Owner::None);
    assert(ordinaryOutOfCombat.Priority == Priority::Idle);

    Lease activeCombat;
    activeCombat.MovementOwner = Owner::CombatRange;
    activeCombat.MovementPriority = Priority::Combat;
    activeCombat.ExpiresAtMs = 200;
    activeCombat.MovementScope = { 1, 0, 1, 669, 8 };

    Request hazard;
    hazard.MovementOwner = configuredInCombat.Owner;
    hazard.MovementPriority = configuredInCombat.Priority;
    hazard.ExpiresAtMs = 200;
    hazard.MovementScope = activeCombat.MovementScope;
    hazard.X = 5.0f;
    assert(Evaluate(activeCombat, hazard, 100) == Decision::Preempt);

    Request mislabeledRoute = hazard;
    mislabeledRoute.MovementOwner = Owner::Route;
    mislabeledRoute.MovementPriority = Priority::Route;
    assert(Evaluate(activeCombat, mislabeledRoute, 100)
        == Decision::PreserveExisting);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/server/game"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)

