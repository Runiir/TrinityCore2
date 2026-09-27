"""Omnotron raid geometry: centre tank slots and healer coverage of every tank.

Round 1 (blackwing_descent_10n-r01-553da85c98): the Blood DK held Electron
about 30 yd north of the arena centre, the Feral tank activated Magmatron at
its southern spawn and both healers stayed north; the Feral tank died to
Magmatron melee 50-57 yd from both healers. These fixtures replay that
geometry and the slot/coverage rules that replace it.
"""
from __future__ import annotations

from pathlib import Path

from tests.test_omnotron_strategy import PRELUDE, _compile_and_run


def test_omnotron_tanks_hold_constructs_on_centre_slots(tmp_path: Path) -> None:
    program = PRELUDE + r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronPositioning.h"

int main()
{
    AdaptiveOmnotronStrategy strategy;
    uint64 const now = 6000000;
    // Round 1 at 60 s: Electron pulled north, Magmatron at its spawn south.
    Blackboard board = Board("slots", 1, now);
    board.Players[0].Position = { -343.0f, -369.0f, CZ };
    board.Players[1].Position = { -315.0f, -410.0f, CZ };
    ActorSnapshot electron = Construct(O::ElectronEntry, 1, 0.0f, 0.0f, G(40001), now + 40000);
    electron.Position = { -339.0f, -372.0f, CZ };
    ActorSnapshot magmatron = Construct(O::MagmatronEntry, 2, 0.0f, 0.0f, G(40002), now + 80000);
    magmatron.Position = { -315.0f, -410.0f, CZ };
    board.Summons = { electron, magmatron };

    AdaptiveOmnotronPlan dk = strategy.Propose(board, G(40001), "tank");
    AdaptiveOmnotronPlan druid = strategy.Propose(board, G(40002), "tank");
    CHECK(dk.Movement && dk.Movement->Id.Mechanic == "tank_center_slot");
    CHECK(druid.Movement && druid.Movement->Id.Mechanic == "tank_center_slot");
    BotNativeAction::Move const* dkMove = MoveOf(dk);
    BotNativeAction::Move const* druidMove = MoveOf(druid);
    CHECK(dkMove && druidMove);
    if (dkMove && druidMove)
    {
        // West slot for the northern Electron, east slot for Magmatron; each
        // tank walks the trail distance past its slot, away from its construct.
        Vector3 const dkDest{ dkMove->X, dkMove->Y, CZ };
        Vector3 const druidDest{ druidMove->X, druidMove->Y, CZ };
        CHECK(std::fabs(Dist(CX - O::TankSlotOffset, CY, dkDest) - O::ConstructTrail) < 0.01f);
        CHECK(std::fabs(Dist(CX + O::TankSlotOffset, CY, druidDest) - O::ConstructTrail) < 0.01f);
        CHECK(Dist(electron.Position.X, electron.Position.Y, dkDest)
            > Dist(CX - O::TankSlotOffset, CY, electron.Position));
        // Both tanks end in heal range of one point at the centre.
        CHECK(Dist(CX, CY, dkDest) <= O::HealerTankReach);
        CHECK(Dist(CX, CY, druidDest) <= O::HealerTankReach);
    }
    // Both tanks derive the same pairing from one snapshot: two slots 10 yd
    // apart, within cleave reach (Blood Boil 10 yd plus the construct's size).
    O::EncounterFacts const facts = O::Observe(board);
    O::DutyPlan const duty = O::BuildDutyPlan(board, facts, O::LedgerMode::Peek);
    std::optional<Vector3> const west = O::TankSlotFor(facts, duty, G(40001));
    std::optional<Vector3> const east = O::TankSlotFor(facts, duty, G(40002));
    CHECK(west && Dist(CX - O::TankSlotOffset, CY, *west) < 0.01f);
    CHECK(east && Dist(CX + O::TankSlotOffset, CY, *east) < 0.01f);
    CHECK(west && east && std::fabs(std::hypot(west->X - east->X, west->Y - east->Y)
        - 2.0f * O::TankSlotOffset) < 0.01f);
    CHECK(2.0f * O::TankSlotOffset <= 10.0f + O::ConstructBoundingRadius);

    // A construct already within the tolerance of its slot: no move.
    Blackboard settled = board;
    settled.Revision = 2;
    settled.Summons[0].Position = { CX - 4.0f, CY + 3.0f, CZ };
    settled.Summons[1].Position = { CX + 9.0f, CY - 2.0f, CZ };
    settled.Players[0].Position = { CX - 6.0f, CY + 1.0f, CZ };
    settled.Players[1].Position = { CX + 10.0f, CY, CZ };
    CHECK(!strategy.Propose(settled, G(40001), "tank").Movement);
    CHECK(!strategy.Propose(settled, G(40002), "tank").Movement);

    // A shielded construct is not walked to its slot.
    Blackboard shielded = board;
    shielded.Revision = 3;
    shielded.Summons[0].Auras.push_back({ 79900, electron.Guid, 1, now + 10000 });
    AdaptiveOmnotronPlan holding = strategy.Propose(shielded, G(40001), "tank");
    CHECK(!holding.Movement || holding.Movement->Id.Mechanic != "tank_center_slot");

    // A single tanked construct takes the nearer slot.
    Blackboard alone = board;
    alone.Revision = 4;
    alone.Summons = { electron };
    AdaptiveOmnotronPlan opening = strategy.Propose(alone, G(40001), "tank");
    if (BotNativeAction::Move const* move = MoveOf(opening))
        CHECK(std::fabs(Dist(CX - O::TankSlotOffset, CY, { move->X, move->Y, CZ })
            - O::ConstructTrail) < 0.01f);
    else
        CHECK(false);

    // A shielded construct beside the other one is dragged apart first; once
    // its shield is gone it is walked back to its slot.
    Blackboard close = settled;
    close.Revision = 8;
    close.Summons[0].Position = { CX - 3.0f, CY, CZ };
    close.Summons[1].Position = { CX + 4.0f, CY, CZ };
    close.Summons[0].Auras.push_back({ 79900, electron.Guid, 1, now + 10000 });
    AdaptiveOmnotronPlan apart = strategy.Propose(close, G(40001), "tank");
    CHECK(apart.Movement && apart.Movement->Id.Mechanic == "tank_shield_separation");
    Blackboard after = settled;
    after.Revision = 9;
    after.Summons[0].Position = { CX - 17.0f, CY + 3.0f, CZ };
    after.Players[0].Position = { CX - 18.0f, CY + 3.0f, CZ };
    AdaptiveOmnotronPlan back = strategy.Propose(after, G(40001), "tank");
    CHECK(back.Movement && back.Movement->Id.Mechanic == "tank_center_slot");

    // A Power Generator on a slot moves that slot out of the field.
    Blackboard field = board;
    field.Revision = 5;
    field.Summons.push_back(Unit(O::PowerGeneratorEntry, 40, O::TankSlotOffset, 0.0f));
    O::EncounterFacts const fieldFacts = O::Observe(field);
    O::DutyPlan const fieldDuty = O::BuildDutyPlan(field, fieldFacts, O::LedgerMode::Peek);
    std::optional<Vector3> const moved = O::TankSlotFor(fieldFacts, fieldDuty, G(40002));
    CHECK(moved && Dist(CX + O::TankSlotOffset, CY, *moved) >= O::SlotGeneratorClearance);
    CHECK(moved && Dist(CX, CY, *moved) <= O::ArenaRadius + 0.01f);

    // A slot inside a Chemical Cloud is not taken.
    Blackboard cloud = board;
    cloud.Revision = 6;
    cloud.Summons.push_back(Unit(O::ChemicalCloudEntry, 41, -O::TankSlotOffset, 0.0f));
    AdaptiveOmnotronPlan clouded = strategy.Propose(cloud, G(40001), "tank");
    CHECK(!clouded.Movement || clouded.Movement->Id.Mechanic != "tank_center_slot");

    // A Chemical Cloud 14 yd beyond a clear slot, on the trail side: the
    // trail point (10.5 yd from the cloud) is inside its 12 yd radius, so the
    // tank walks to the slot itself instead; never into the cloud.
    Blackboard beyond = board;
    beyond.Revision = 10;
    beyond.Summons = { electron };
    beyond.Summons[0].Position = { CX - O::TankSlotOffset, CY + 20.0f, CZ };
    beyond.Players[0].Position = { CX - O::TankSlotOffset, CY + 22.0f, CZ };
    beyond.Summons.push_back(Unit(O::ChemicalCloudEntry, 43, -O::TankSlotOffset, -14.0f));
    O::EncounterFacts const beyondFacts = O::Observe(beyond);
    CHECK(O::HazardDepth(beyondFacts, { CX - O::TankSlotOffset, CY, CZ }) <= 0.0f);
    CHECK(O::HazardDepth(beyondFacts,
        { CX - O::TankSlotOffset, CY - O::ConstructTrail, CZ }) > 0.0f);
    AdaptiveOmnotronPlan trail = strategy.Propose(beyond, G(40001), "tank");
    CHECK(trail.Movement && trail.Movement->Id.Mechanic == "tank_center_slot");
    if (BotNativeAction::Move const* move = MoveOf(trail))
    {
        CHECK(O::HazardDepth(beyondFacts, { move->X, move->Y, CZ }) <= 0.0f);
        CHECK(Dist(CX - O::TankSlotOffset, CY, { move->X, move->Y, CZ }) < 0.01f);
    }
    // A second cloud reaching the slot as well: no clear point, hold.
    Blackboard boxed = beyond;
    boxed.Revision = 11;
    boxed.Summons.push_back(Unit(O::ChemicalCloudEntry, 44, -O::TankSlotOffset - 13.0f, 0.0f));
    AdaptiveOmnotronPlan hold = strategy.Propose(boxed, G(40001), "tank");
    CHECK(!hold.Movement || hold.Movement->Id.Mechanic != "tank_center_slot");

    // A tank waiting for the next construct has no slot.
    Blackboard standby = board;
    standby.Revision = 7;
    standby.Summons = { electron };
    O::EncounterFacts const standbyFacts = O::Observe(standby);
    CHECK(!O::TankSlotFor(standbyFacts,
        O::BuildDutyPlan(standby, standbyFacts, O::LedgerMode::Peek), G(40002)));

    std::printf("ok\n");
    return failures ? 1 : 0;
}
'''
    assert _compile_and_run(tmp_path, program).strip() == "ok"


def test_omnotron_healers_cover_every_tank(tmp_path: Path) -> None:
    program = PRELUDE + r'''
int main()
{
    AdaptiveOmnotronStrategy strategy;
    uint64 const now = 7000000;
    // Round 1 at 60 s: both healers north with the DK, the Feral tank south.
    Blackboard board = Board("coverage", 1, now);
    board.Players[0].Position = { -343.0f, -369.0f, CZ };
    board.Players[1].Position = { -315.0f, -410.0f, CZ };
    board.Players[4].Position = { -322.0f, -354.0f, CZ };
    board.Players[6].Position = { -346.0f, -367.0f, CZ };
    ActorSnapshot electron = Construct(O::ElectronEntry, 1, 0.0f, 0.0f, G(40001), now + 40000);
    electron.Position = { -339.0f, -372.0f, CZ };
    ActorSnapshot magmatron = Construct(O::MagmatronEntry, 2, 0.0f, 0.0f, G(40002), now + 80000);
    magmatron.Position = { -315.0f, -410.0f, CZ };
    board.Summons = { electron, magmatron };

    for (uint32 healer : { 40005u, 40007u })
    {
        AdaptiveOmnotronPlan plan = strategy.Propose(board, G(healer), "healer");
        CHECK(plan.Movement && plan.Movement->Id.Mechanic == "healer_tank_coverage");
        if (BotNativeAction::Move const* move = MoveOf(plan))
            for (int tank = 0; tank < 2; ++tank)
                CHECK(Dist(move->X, move->Y, board.Players[tank].Position) <= O::HealerTankReach);
    }

    // In range of both tanks: no coverage move.
    Blackboard covered = Board("coverage", 2, now);
    covered.Summons = { Construct(O::ElectronEntry, 1, -7.0f, 0.0f, G(40001), now + 40000),
        Construct(O::MagmatronEntry, 2, 7.0f, 0.0f, G(40002), now + 80000) };
    AdaptiveOmnotronPlan still = strategy.Propose(covered, G(40005), "healer");
    CHECK(!still.Movement || still.Movement->Id.Mechanic != "healer_tank_coverage");

    // The coverage point avoids a Chemical Cloud on the tanks' centroid.
    Blackboard cloud = board;
    cloud.Revision = 3;
    cloud.Summons.push_back(Unit(O::ChemicalCloudEntry, 42, 0.0f, 0.0f));
    cloud.Summons.back().Position = { -329.0f, -389.5f, CZ };
    AdaptiveOmnotronPlan avoid = strategy.Propose(cloud, G(40005), "healer");
    CHECK(avoid.Movement && avoid.Movement->Id.Mechanic == "healer_tank_coverage");
    if (BotNativeAction::Move const* move = MoveOf(avoid))
        CHECK(O::HazardDepth(O::Observe(cloud), { move->X, move->Y, CZ }) <= 0.0f);

    // A healer carrying Lightning Conductor isolates instead.
    Blackboard conductor = board;
    conductor.Revision = 4;
    conductor.Players[6].Auras.push_back({ 79888, electron.Guid, 1, now + 10000 });
    conductor.Players[6].Position = conductor.Players[0].Position;
    conductor.Players[6].Position.X += 2.0f;
    AdaptiveOmnotronPlan carrier = strategy.Propose(conductor, G(40007), "healer");
    CHECK(carrier.Movement && carrier.Movement->Id.Mechanic == "lightning_conductor_isolate");

    // Damage dealers never get a coverage move.
    Blackboard ranged = board;
    ranged.Revision = 5;
    ranged.Players[3].Position = board.Players[4].Position;
    AdaptiveOmnotronPlan mage = strategy.Propose(ranged, G(40004), "dps");
    CHECK(!mage.Movement || mage.Movement->Id.Mechanic != "healer_tank_coverage");

    std::printf("ok\n");
    return failures ? 1 : 0;
}
'''
    assert _compile_and_run(tmp_path, program).strip() == "ok"


def test_omnotron_healer_generator_must_reach_every_tank(tmp_path: Path) -> None:
    program = PRELUDE + r'''
int main()
{
    AdaptiveOmnotronStrategy strategy;
    uint64 const now = 8000000;
    Blackboard board = Board("generator", 1, now);
    board.Players[0].Position = { CX - 7.0f, CY, CZ };
    board.Players[1].Position = { CX + 7.0f, CY, CZ };
    board.Players[4].Position = { CX - 10.0f, CY + 14.0f, CZ };
    board.Summons = { Construct(O::ElectronEntry, 1, -7.0f, 2.0f, G(40001), now + 40000),
        Construct(O::MagmatronEntry, 2, 7.0f, 2.0f, G(40002), now + 80000) };

    // A generator 20 yd north-west: in range of the DK, 34 yd from the druid.
    Blackboard far = board;
    far.Summons.push_back(Unit(O::PowerGeneratorEntry, 50, -20.0f, 18.0f));
    AdaptiveOmnotronPlan skip = strategy.Propose(far, G(40005), "healer");
    CHECK(!skip.Movement || skip.Movement->Id.Mechanic != "power_generator_stack");
    // A generator between the tanks: the healer stands in it.
    Blackboard near = board;
    near.Revision = 2;
    near.Summons.push_back(Unit(O::PowerGeneratorEntry, 51, 0.0f, 12.0f));
    AdaptiveOmnotronPlan stack = strategy.Propose(near, G(40005), "healer");
    CHECK(stack.Movement && stack.Movement->Id.Mechanic == "power_generator_stack");

    std::printf("ok\n");
    return failures ? 1 : 0;
}
'''
    assert _compile_and_run(tmp_path, program).strip() == "ok"
