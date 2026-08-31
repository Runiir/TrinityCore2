from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "-I", str(ROOT / "src/server/game"),
    "-I", str(ROOT / "src/server/game/Entities/Object"),
    "-I", str(ROOT / "src/common"),
    "-I", str(ROOT / "src/common/Utilities"),
    "-I", str(ROOT / "src/common/Logging"),
    "-I", str(ROOT / "src/common/Debugging"),
]


def test_task_relative_movement_observation_fixture(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_task_movement_observation.cpp"
    binary = tmp_path / "magmaw_task_movement_observation"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneMovementObservation.h"

#include <cassert>

using namespace BotEncounter;
using Disposition = MagmawTransferLaneMovementDisposition;

static BotMovementArbitration::Lease Lease(
    BotMovementArbitration::Owner owner,
    BotMovementArbitration::Scope const& scope,
    Vector3 const& destination, uint64 expiry)
{
    BotMovementArbitration::Lease lease;
    lease.MovementOwner = owner;
    lease.MovementPriority = owner == BotMovementArbitration::Owner::Recovery
        ? BotMovementArbitration::Priority::Recovery
        : owner == BotMovementArbitration::Owner::Hazard
        ? BotMovementArbitration::Priority::Hazard
        : BotMovementArbitration::Priority::Mechanic;
    lease.MovementScope = scope;
    lease.ExpiresAtMs = expiry;
    lease.X = destination.X;
    lease.Y = destination.Y;
    lease.Z = destination.Z;
    return lease;
}

int main()
{
    Scope lifecycle{ "cohort", 7, 2, 5, "magmaw", 669, 23,
        "blackwing_descent.magmaw", 91, 4 };
    auto const scope = MagmawTransferLaneMovementScope(lifecycle);
    Vector3 const destination{ 11.0f, -22.0f, 210.0f };
    MagmawTransferLaneMovementObservation observation;
    auto classify = [&](uint64 now)
    {
        return ClassifyMagmawTransferLaneMovementObservation(now, scope,
            destination, observation);
    };

    assert(classify(1000) == Disposition::NoLease);
    observation.CurrentLease = Lease(BotMovementArbitration::Owner::Hazard,
        scope, destination, 1000);
    assert(classify(1000) == Disposition::ExpiredLease);
    assert(classify(1001) == Disposition::ExpiredLease);

    observation.CurrentLease->ExpiresAtMs = 1001;
    assert(classify(1000) == Disposition::OwnHazardTransfer);
    observation.CurrentLease->X +=
        MagmawTransferLaneLeaseDestinationTolerance2d + 0.01f;
    assert(classify(1000) == Disposition::HazardSafetyPreemption);
    assert(IsMagmawTransferLaneSafetyPreemption(classify(1000)));

    observation.CurrentLease = Lease(BotMovementArbitration::Owner::Recovery,
        scope, destination, 1001);
    assert(classify(1000) == Disposition::RecoverySafetyPreemption);
    observation.CurrentLease->X += 50.0f;
    assert(classify(1000) == Disposition::RecoverySafetyPreemption);

    observation.CurrentLease = Lease(BotMovementArbitration::Owner::Mechanic,
        scope, destination, 1001);
    assert(classify(1000) == Disposition::OwnMechanicTransfer);
    observation.CurrentLease->Z +=
        MagmawTransferLaneLeaseDestinationToleranceZ + 0.01f;
    assert(classify(1000) == Disposition::OtherCurrentLease);
    assert(!IsMagmawTransferLaneSafetyPreemption(classify(1000)));

    observation.CurrentLease = Lease(BotMovementArbitration::Owner::Hazard,
        scope, destination, 1001);
    ++observation.CurrentLease->MovementScope.RouteGeneration;
    assert(classify(1000) == Disposition::DifferentScope);
    assert(!IsMagmawTransferLaneSafetyPreemption(classify(1000)));

    observation.CurrentLease = Lease(BotMovementArbitration::Owner::Recovery,
        scope, destination, 1001);
    ++observation.CurrentLease->MovementScope.InstanceId;
    assert(classify(1000) == Disposition::DifferentScope);
    assert(!IsMagmawTransferLaneSafetyPreemption(classify(1000)));

    observation.CurrentLease = Lease(BotMovementArbitration::Owner::Hazard,
        scope, destination, 1001);
    observation.CurrentLease->DynamicTargetGuid = 99;
    assert(classify(1000) == Disposition::HazardSafetyPreemption);
}
''', encoding="utf-8")
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
        str(source),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawTransferLaneMovementObservation.cpp"),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
