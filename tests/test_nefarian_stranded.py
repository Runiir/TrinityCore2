"""Round 2 (r01 live evidence): members stranded off Nefarian's End.

Kill 6bf52232 (label blackwing_descent_10n-r01-553da85c98):
- the Elemental shaman's pillar prototype died at 100 s; the plan retargeted
  a prototype on another pillar about 70 yards away and native range recovery
  walked her into the air, where she hovered at local Z 10.3 for the rest of
  the fight (Shadow of Cowardice every 4-6 s in phase 3);
- the rogue ended phase 2 at local Z 3.1, 8 yards from a pillar centre and
  1.7 yards above the ring, and the platform hold kept him there, 26 yards
  from Nefarian, for 15 minutes.

Phase 2 now follows the user's tactic (2026-09-26, authoritative): only the
crossing pair (one healer and one damage dealer of the first healer pillar to
finish) leaves, by the swim path; everyone else holds on its pillar. The
stranded-fall positions below are the ones the combat log recorded.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run


PROGRAM = PRELUDE + r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianStranded.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianPlatformBody.h"

static TransportPlacement PlacementAt(Blackboard const& board, uint32 slot, float localZ)
{
    ActorSnapshot const* bot = board.FindActor(Bot(slot));
    LocalPoint const local = WorldToLocal(bot->Position);
    TransportPlacement placement;
    placement.Actor = Bot(slot);
    placement.Transport = board.Interactables[0].Guid;
    placement.TransportEntry = ElevatorEntry;
    placement.Offset = { local.X, local.Y, localZ };
    return placement;
}

static ActorSnapshot const* ProtoOn(Blackboard const& board, int pillar)
{
    return PillarPrototype(ObserveEncounter(board), pillar);
}

static void RemovePrototypeOf(Blackboard& board, int pillar)
{
    ActorSnapshot const* prototype = ProtoOn(board, pillar);
    ObjectGuid const guid = prototype ? prototype->Guid : ObjectGuid();
    board.Summons.erase(std::remove_if(board.Summons.begin(), board.Summons.end(),
        [guid](ActorSnapshot const& s) { return s.Guid == guid; }), board.Summons.end());
}

// PlatformBoard with every healer-pillar member on its own pillar top.
static Blackboard CrossingBoard()
{
    Blackboard board = PlatformBoard(PlatformFrame::LoweredOriginZ);
    DutyPlan const duty = BuildNefarianDutyPlan(board);
    for (int pillar : { 0, 1 })
    {
        uint8 slot = 0;
        for (ObjectGuid member : duty.Pillars[pillar].Members)
            FindPlayer(board, member.GetCounter() - 30500).Position = LocalToWorld(
                PillarSlot(uint8(pillar), slot++), PlatformFrame::PillarTopLocalZ,
                PlatformFrame::LoweredOriginZ);
    }
    return board;
}

static NativeFacts TopFacts(Blackboard const& board)
{
    NativeFacts facts;
    for (ActorSnapshot const& player : board.Players)
        facts.Placements.push_back(PlacementAt(board, player.Guid.GetCounter() - 30500,
            PlatformFrame::PillarTopLocalZ));
    facts.PillarAscentSupported = true;
    facts.PillarKillMs = { 0, 5000, 0 };
    return facts;
}

// User raid experience 2026-09-26 (authoritative): when a healer pillar kills
// its prototype, exactly one healer and one damage dealer of it swim to the
// tank pillar; everyone else holds on its pillar; nobody targets another
// pillar's prototype from afar or walks off a pillar into the air.
static void TestPhaseTwoCrossingOnly()
{
    CHECK(CrossingSupported, "the executor carries the liquid ledge drop (patch R8)");
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CrossingBoard();
    DutyPlan const duty = BuildNefarianDutyPlan(board);
    CHECK(duty.TankPillar == 2 && duty.Pillars[1].Healer == Bot(7), "canonical teams");
    Blackboard killed = board;
    RemovePrototypeOf(killed, 1);
    EncounterView const view = ObserveEncounter(killed);
    ArenaLayout const layout = BuildArenaLayout(duty);
    NativeFacts const facts = TopFacts(killed);
    CHECK(SendingPillar(killed, view, duty, &facts) == 1, "pillar 1 finished first");

    // Exactly the pair leaves: the healer and one damage dealer of pillar 1.
    int leaving = 0;
    for (int pillar : { 0, 1 })
        for (ObjectGuid member : duty.Pillars[pillar].Members)
        {
            ActorSnapshot const& actor = FindPlayer(killed, member.GetCounter() - 30500);
            CrossingAssignment const crossing = CrossingFor(
                MovementContext{ killed, view, duty, layout, actor, &facts });
            if (crossing.Pillar >= 0)
            {
                ++leaving;
                CHECK(pillar == 1 && crossing.Pillar == 2 && crossing.Departing,
                    "only pillar 1 members depart, for the tank pillar");
            }
        }
    CHECK(leaving == 2, "exactly one healer and one damage dealer cross");
    ObjectGuid const helper = PillarDamageHelper(killed, duty, 1, &facts);
    CHECK(!helper.IsEmpty() && IsPillarHelper(killed, duty, 1, Bot(7), &facts), "the healer is in the pair");
    uint32 const helperSlot = helper.GetCounter() - 30500;

    // The departing damage dealer does not target the tank pillar's prototype
    // from its own pillar (range recovery would walk it into the air); its
    // movement is the crossing's own rim / step-off, the swim path.
    AdaptiveNefarianPlan const departing = strategy.Propose(killed, helper, "dps", &facts);
    CHECK(departing.DamageTarget.IsEmpty() && departing.SuppressOffense
        && departing.SuppressReason == "nefarian_crossing_under_way",
        "no damage target while the crossing is under way");
    bool const crossingMove = departing.Movement
        && departing.Movement->Id.Mechanic.rfind("pillar_crossing", 0) == 0;
    CHECK(crossingMove || departing.MovementHold == "nefarian_crossing_defensive_first",
        "the helper leaves only by the crossing stages");

    // At the rim with no defensive ready: the step off lands in the lava
    // (LandInLiquid), never a dry walk.
    Blackboard atRim = killed;
    float const toward = AngleOf({ PillarCenters[2].X - PillarCenters[1].X,
        PillarCenters[2].Y - PillarCenters[1].Y });
    uint8 slot = 0;
    for (uint8 candidate = 1; candidate < 6; ++candidate)
        if (AngularGap(PillarSlotHeading(1, candidate), toward)
            < AngularGap(PillarSlotHeading(1, slot), toward))
            slot = candidate;
    LocalPoint const rim = Offset(PillarCenters[1], PillarSlotHeading(1, slot), DescentRimRadius + 0.2f);
    FindPlayer(atRim, helperSlot).Position = LocalToWorld(rim, PlatformFrame::PillarTopLocalZ - 0.5f,
        PlatformFrame::LoweredOriginZ);
    NativeFacts rimFacts = TopFacts(atRim);
    rimFacts.Readiness.push_back({ helper, SpellDivineShield, true, false });
    rimFacts.Readiness.push_back({ helper, 33206, true, false });
    AdaptiveNefarianPlan const step = strategy.Propose(atRim, helper, "dps", &rimFacts);
    auto const* stepMove = step.Movement
        ? std::get_if<BotNativeAction::TransportSurfaceMove>(&step.Movement->Action) : nullptr;
    CHECK(stepMove && LandsInLiquid(*stepMove)
        && (stepMove->Kind == BotNativeAction::TransportSurfaceMove::Stage::StepOff
            || stepMove->Kind == BotNativeAction::TransportSurfaceMove::Stage::Fall),
        "the step off the rim goes into the lava");
    CHECK(step.DamageTarget.IsEmpty(), "still no damage target at the rim");

    // On the tank pillar, in reach: the helper damages its prototype.
    Blackboard arrived = killed;
    FindPlayer(arrived, helperSlot).Position = LocalToWorld(PillarSlot(2, 3),
        PlatformFrame::PillarTopLocalZ, PlatformFrame::LoweredOriginZ);
    NativeFacts arrivedFacts = TopFacts(arrived);
    CHECK(strategy.Propose(arrived, helper, "dps", &arrivedFacts).DamageTarget
        == ProtoOn(arrived, 2)->Guid, "on the tank pillar the helper damages its prototype");

    // Everyone else on pillar 1 holds: no target on another pillar, no move off.
    for (ObjectGuid member : duty.Pillars[1].Members)
    {
        if (member == helper || member == Bot(7))
            continue;
        AdaptiveNefarianPlan const plan = strategy.Propose(killed, member, "dps", &facts);
        CHECK(plan.DamageTarget.IsEmpty() && plan.SuppressOffense
            && plan.SuppressReason == "nefarian_platform_prototype_out_of_reach",
            "a non-helper whose prototype died holds fire");
        CHECK(!plan.Movement || plan.Movement->Id.Mechanic.rfind("pillar_crossing", 0) != 0,
            "and does not leave its pillar");
    }
    // Pillar 0, still fighting: its own prototype.
    for (ObjectGuid member : duty.Pillars[0].Members)
        if (member != duty.Pillars[0].Healer)
            CHECK(strategy.Propose(killed, member, "dps", &facts).DamageTarget
                == ProtoOn(killed, 0)->Guid, "pillar 0 keeps its own prototype");

    // Not the sending pillar (pillar 0 killed second): nobody of it leaves,
    // even a member standing next to another pillar's prototype.
    Blackboard both = killed;
    RemovePrototypeOf(both, 0);
    NativeFacts bothFacts = TopFacts(both);
    bothFacts.PillarKillMs = { 9000, 5000, 0 };
    EncounterView const bothView = ObserveEncounter(both);
    for (ObjectGuid member : duty.Pillars[0].Members)
    {
        ActorSnapshot const& actor = FindPlayer(both, member.GetCounter() - 30500);
        CHECK(CrossingFor(MovementContext{ both, bothView, duty, layout, actor, &bothFacts }).Pillar < 0,
            "the later finisher sends nobody");
        if (member != duty.Pillars[0].Healer)
            CHECK(strategy.Propose(both, member, "dps", &bothFacts).DamageTarget.IsEmpty(),
                "and its members hold fire");
    }

    // No prototype left: unchanged (Electrocute at every 10%).
    Blackboard allDead = board;
    allDead.Summons.resize(1);
    CHECK(strategy.Propose(allDead, Bot(9), "dps").SuppressReason == "nefarian_platform_no_prototype",
        "no prototype at all keeps the old hold reason");
}

static Blackboard GroundBoard()
{
    Blackboard board = CanonicalBoard();
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { -16.8f, 0.44f }, 0.0f);
    nefarian.InCombat = true;
    nefarian.VictimGuid = Bot(1);
    board.Summons.push_back(nefarian);
    FindPlayer(board, 1).Position = LocalToWorld({ -10.0f, 0.4f }, PlatformFrame::FloorLocalZ,
        PlatformFrame::RaisedOriginZ);
    return board;
}

static void TestStrandedFall()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = GroundBoard();
    CHECK(ObserveEncounter(board).CurrentPhase == Phase::NefarianGround, "phase 3");

    // The shaman, hovering over the centre floor at pillar-top height.
    LocalPoint const shaman{ 5.90216f, 19.71925f };
    FindPlayer(board, 9).Position = LocalToWorld(shaman, 10.3224f, PlatformFrame::RaisedOriginZ);
    // The rogue, 8 yards from pillar 2's centre, 1.7 yards above the ring.
    LocalPoint const rogue{ -18.6f, 26.6f };
    FindPlayer(board, 8).Position = LocalToWorld(rogue, 3.1f, PlatformFrame::RaisedOriginZ);
    NativeFacts facts;
    facts.Placements.push_back(PlacementAt(board, 9, 10.3224f));
    facts.Placements.push_back(PlacementAt(board, 8, 3.1f));
    for (uint32 slot : { 1u, 4u })
        facts.Placements.push_back(PlacementAt(board, slot, PlatformFrame::FloorLocalZ));

    for (uint32 slot : { 9u, 8u })
    {
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(slot), "dps", &facts);
        auto const* move = plan.Movement
            ? std::get_if<BotNativeAction::TransportSurfaceMove>(&plan.Movement->Action) : nullptr;
        LocalPoint const at = slot == 9 ? shaman : rogue;
        CHECK(move && move->Kind == BotNativeAction::TransportSurfaceMove::Stage::Fall
            && plan.Movement->Id.Mechanic == "platform_stranded_fall"
            && plan.Movement->ActionPriority == BotActionArbitration::Priority::Survival,
            "a stranded passenger falls where it stands");
        CHECK(move && Near(move->LandingZ, PlatformFrame::RaisedOriginZ + FloorLocalZAt(at), 0.01f)
            && move->LandOnTransport && move->Transport == board.Interactables[0].Guid,
            "onto the model floor under it");
        CHECK(plan.DamageTarget == board.Summons[0].Guid, "and keeps Nefarian as its target");
    }
    CHECK(Near(FloorLocalZAt(shaman), PlatformFrame::FloorLocalZ, 0.001f)
        && Near(FloorLocalZAt(rogue), RingLocalZ, 0.001f), "centre floor and ring");

    // The fall under way lands through the descent's Land stage onto the
    // same floor.
    NativeFacts falling = facts;
    falling.Falls.push_back({ Bot(9), true, false });
    AdaptiveNefarianPlan const landing = strategy.Propose(board, Bot(9), "dps", &falling);
    auto const* land = landing.Movement
        ? std::get_if<BotNativeAction::TransportSurfaceMove>(&landing.Movement->Action) : nullptr;
    CHECK(land && land->Kind == BotNativeAction::TransportSurfaceMove::Stage::Land
        && Near(land->LandingZ, PlatformFrame::RaisedOriginZ + FloorLocalZAt(shaman), 0.01f),
        "the landing is declared on the centre floor");

    // Not stranded: on the floor, moving, on a pillar top, the floor not at rest.
    AdaptiveNefarianPlan const tank = strategy.Propose(board, Bot(1), "tank", &facts);
    CHECK(!tank.Movement || tank.Movement->Id.Mechanic != "platform_stranded_fall",
        "a member on the floor does not fall");
    NativeFacts moving = facts;
    moving.Motion.push_back({ Bot(8), true, LocalToWorld({ -16.8f, 14.3f }, RingLocalZ,
        PlatformFrame::RaisedOriginZ) });
    AdaptiveNefarianPlan const walking = strategy.Propose(board, Bot(8), "dps", &moving);
    CHECK(!walking.Movement || walking.Movement->Id.Mechanic != "platform_stranded_fall",
        "a member under way is not judged stranded");
    Blackboard onPillar = board;
    FindPlayer(onPillar, 8).Position = LocalToWorld(PillarSlot(2, 1),
        PlatformFrame::PillarTopLocalZ, PlatformFrame::RaisedOriginZ);
    NativeFacts pillarFacts;
    pillarFacts.Placements.push_back(PlacementAt(onPillar, 8, PlatformFrame::PillarTopLocalZ));
    AdaptiveNefarianPlan const descent = strategy.Propose(onPillar, Bot(8), "dps", &pillarFacts);
    CHECK(descent.Movement && descent.Movement->Id.Mechanic.rfind("pillar_descent", 0) == 0,
        "a member on a pillar top keeps the pillar descent");
    Blackboard rising = board;
    rising.Interactables = { MakeElevator(0.0f) };
    NativeFacts risingFacts;
    risingFacts.Placements.push_back(PlacementAt(rising, 9, 10.3224f));
    EncounterView const risingView = ObserveEncounter(rising);
    DutyPlan const risingDuty = BuildNefarianDutyPlan(rising);
    ArenaLayout const risingLayout = BuildArenaLayout(risingDuty);
    MovementContext const context{ rising, risingView, risingDuty, risingLayout,
        FindPlayer(rising, 9), &risingFacts };
    CHECK(!StrandedAbovePlatform(context), "never while the floor moves");
}

// Round 3 (E1, round-2 live evidence): the mage, the warlock and the Disc
// priest stayed on the pillar-1 rim at local (-15.8, -32.4), offset z 9.37,
// in all three runs; no step-off was ever committed. The plan proposes the
// step-off there (the refusal is the executor's native landing query under
// the platform's north half, tests/test_nefarian_ledge_drop_floor_query.py,
// shared-runtime patch request), onto the ring under the rim.
static void TestRound3PillarOneRimStepOff()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = GroundBoard();
    LocalPoint const rim{ -15.8f, -32.4f };
    float distance = 0.0f;
    CHECK(NearestPillar(rim, distance) == 1 && distance > DescentRimRadius - 0.3f
        && distance < DescentOverVoidRadius(1, 0) - 0.15f, "the rim point is pillar 1's rim");
    for (uint32 slot : { 4u, 7u, 10u })
    {
        FindPlayer(board, slot).Position = LocalToWorld(rim, 9.37f, PlatformFrame::RaisedOriginZ);
        NativeFacts facts;
        facts.PillarAscentSupported = true;
        facts.Placements.push_back(PlacementAt(board, slot, 9.37f));
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(slot),
            slot == 7 ? "healer" : "dps", &facts);
        auto const* move = plan.Movement
            ? std::get_if<BotNativeAction::TransportSurfaceMove>(&plan.Movement->Action) : nullptr;
        CHECK(plan.Phase == Phase::NefarianGround && move
            && move->Kind == BotNativeAction::TransportSurfaceMove::Stage::StepOff
            && plan.Movement->Id.Mechanic == "pillar_descent_step_off"
            && plan.Movement->ActionPriority == BotActionArbitration::Priority::Survival,
            "E1: the pillar-1 rim yields the step-off");
        CHECK(move && Near(move->LandingZ, PlatformFrame::RaisedOriginZ + RingLocalZ, 0.001f)
            && move->LandOnTransport && Near(move->LandingToleranceYards, 1.0f),
            "declared onto the ring under the rim");
        if (move)
        {
            LocalPoint const off = WorldToLocal({ move->X, move->Y, move->Z });
            float offDistance = 0.0f;
            NearestPillar(off, offDistance);
            CHECK(Near(offDistance, DescentStepOffRadius, 0.01f)
                && Distance(off, rim) <= DescentStepOffRadius - DescentRimRadius + 0.3f,
                "the declared step-off is past the wall on the member's own heading");
        }
        FindPlayer(board, slot).Position = LocalToWorld({ 9.0f, 0.0f }, PlatformFrame::FloorLocalZ,
            PlatformFrame::RaisedOriginZ);
    }
}

// Round 3 (E2): the rogue (3 of 3 runs) and both tanks (2 of 3) sat inside a
// pillar's hollow shaft, within 1.5 yd of its centre at local z 3-4. No
// executor-proven step leaves it (BotNefarianPlatformBody.h): the plan names
// the state under the pillar hold instead of a float, swim or walk.
static void TestRound3InsidePillarShaft()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CrossingBoard();
    DutyPlan const duty = BuildNefarianDutyPlan(board);
    struct Case { uint32 Slot; int Pillar; LocalPoint Offset; float LocalZ; bool Passenger; };
    Case const cases[] = {
        { 8, 0, { 0.9f, 0.6f }, 3.4f, false }, // the rogue, swimming in the shaft
        { 8, 0, { -1.2f, 0.4f }, 3.9f, true },  // the rogue, a passenger in it
        { 1, 2, { 1.0f, -0.8f }, 3.1f, false }, // the Blood DK
        { 2, 2, { -0.5f, 1.3f }, 4.0f, true },  // the Feral
    };
    for (Case const& c : cases)
    {
        CHECK(duty.PillarOf(Bot(c.Slot)) == c.Pillar, "the member's own pillar");
        Blackboard inside = board;
        LocalPoint const at{ PillarCenters[c.Pillar].X + c.Offset.X,
            PillarCenters[c.Pillar].Y + c.Offset.Y };
        FindPlayer(inside, c.Slot).Position = LocalToWorld(at, c.LocalZ,
            PlatformFrame::LoweredOriginZ);
        CHECK(FindPlayer(inside, c.Slot).Position.Z < MagmaSurfaceZ - 5.0f,
            "six yards under the magma, as recorded");
        CHECK(InsidePillarShaft(at, c.LocalZ), "inside the hollow shaft");
        NativeFacts facts = TopFacts(inside);
        facts.Placements.erase(std::remove_if(facts.Placements.begin(), facts.Placements.end(),
            [&c](TransportPlacement const& p) { return p.Actor == Bot(c.Slot); }),
            facts.Placements.end());
        if (c.Passenger)
            facts.Placements.push_back(PlacementAt(inside, c.Slot, c.LocalZ));
        EncounterView const view = ObserveEncounter(inside);
        ArenaLayout const layout = BuildArenaLayout(duty);
        CHECK(!OnPillarStructure(MovementContext{ inside, view, duty, layout,
            FindPlayer(inside, c.Slot), &facts }), "inside the shaft is not on the pillar");
        AdaptiveNefarianPlan const plan = strategy.Propose(inside, Bot(c.Slot),
            FindPlayer(inside, c.Slot).Role, &facts);
        CHECK(plan.Phase == Phase::PlatformHold && !plan.Ascent && !plan.Movement,
            "no float, swim, hop or walk out of the shaft is proposed");
        CHECK(IsPillarHold(plan.MovementHold)
            && HoldReason(plan.MovementHold) == "nefarian_inside_pillar_column",
            "the typed state, under the pillar hold (no native chase deeper in)");
    }
    // Negative controls: on the top and on the rim a member is on the pillar,
    // and a swimmer at its station is not inside anything.
    CHECK(!InsidePillarShaft(PillarSlot(0, 1), PlatformFrame::PillarTopLocalZ)
        && !InsidePillarShaft(PillarRadial(0, 1, HopLandingRadius(0, 1)), HopLandingLocalZ)
        && !InsidePillarShaft(PillarRadial(0, 1, SwimStationRadius), LoweredMagmaLocalZ - FloatDepthYards),
        "top, rim and swim station are outside the shaft");
    CHECK(InsidePillarShaft(PillarSlot(0, 1), PlatformFrame::PillarTopLocalZ - 0.7f)
        && !InsidePillarShaft(PillarSlot(0, 1), PlatformFrame::PillarTopLocalZ - 0.5f),
        "the shaft starts past the floor tolerance under the top");
}

// Round 3 (E2): the Ret paladin stood on the pillar-1 top without being a
// passenger, and the rising platform left him behind. A member on a top who
// is not on the transport boards before the rise: at the lowered stop, and
// while the rising top is still within the emerge band under its feet;
// past that it is a typed miss.
static void TestRound3TopBoardsBeforeRise()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CrossingBoard();
    NativeFacts facts = TopFacts(board);
    facts.Placements.erase(std::remove_if(facts.Placements.begin(), facts.Placements.end(),
        [](TransportPlacement const& p) { return p.Actor == Bot(6); }), facts.Placements.end());
    AdaptiveNefarianPlan const lowered = strategy.Propose(board, Bot(6), "dps", &facts);
    CHECK(lowered.Phase == Phase::PlatformHold && lowered.Ascent
        && lowered.Ascent->Stage == AscentStage::Board,
        "on the top, not a passenger, at the lowered stop: board");

    // The rise (every prototype dead): the top comes up under his feet from
    // where he stood (feet - top: 0 at the lowered stop, then negative).
    Blackboard rise = board;
    rise.Summons.resize(1);
    Vector3 const feet = FindPlayer(board, 6).Position;
    float const lowest = PillarSurfaceLowest(1, Distance(WorldToLocal(feet), PillarCenters[1]));
    for (float gap : { 0.1f, -0.2f, -0.45f })
    {
        rise.Interactables = { MakeElevator(feet.Z - lowest - gap) };
        FindPlayer(rise, 6).Position = feet;
        AdaptiveNefarianPlan const plan = strategy.Propose(rise, Bot(6), "dps", &facts);
        CHECK(plan.Phase == Phase::PlatformReturn && plan.Ascent
            && plan.Ascent->Stage == AscentStage::Board
            && Near(plan.Ascent->FloorToleranceYards, RisingFloorEmergeToleranceYards),
            "the rising top within the band: board where he stands");
    }
    rise.Interactables = { MakeElevator(feet.Z - lowest + 0.55f) };
    AdaptiveNefarianPlan const missed = strategy.Propose(rise, Bot(6), "dps", &facts);
    CHECK(!missed.Ascent && HoldReason(missed.MovementHold) == "nefarian_rising_top_missed"
        && IsPillarHold(missed.MovementHold), "past the band: the typed miss, held");
    rise.Interactables = { MakeElevator(feet.Z - lowest + 2.0f) };
    AdaptiveNefarianPlan const buried = strategy.Propose(rise, Bot(6), "dps", &facts);
    CHECK(!buried.Ascent && HoldReason(buried.MovementHold) == "nefarian_inside_pillar_column",
        "left behind inside the rising pillar: the shaft state");
    // A passenger on its top in phase 2 with nothing to do is held, so native
    // combat movement cannot walk it anywhere.
    NativeFacts const topFacts = TopFacts(board);
    AdaptiveNefarianPlan const aboard = strategy.Propose(board, Bot(4), "dps", &topFacts);
    CHECK(!aboard.Movement && IsPillarHold(aboard.MovementHold), "an idle passenger on its top is held");
}

int main()
{
    TestPhaseTwoCrossingOnly();
    TestStrandedFall();
    TestRound3PillarOneRimStepOff();
    TestRound3InsidePillarShaft();
    TestRound3TopBoardsBeforeRise();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_nefarian_stranded_members(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM)


def test_nefarian_stranded_members_under_sanitizers(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM, sanitize=True)
