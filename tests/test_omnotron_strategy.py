from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OMNOTRON = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron"
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
    return result.stdout


PRELUDE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotAdaptiveOmnotronStrategy.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <variant>

using namespace BotEncounter;
namespace O = BotEncounter::Omnotron;

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #cond); ++failures; } } while (0)

static constexpr float CX = -324.78f;
static constexpr float CY = -399.078f;
static constexpr float CZ = 213.825f;

inline ActorSnapshot Player(uint32 guid, char const* role, char const* spec, float x, float y)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Kind = ActorKind::Player;
    player.Role = role;
    player.ClassSpec = spec;
    player.Position = { CX + x, CY + y, CZ };
    player.HealthPct = 100.0f;
    player.Alive = true;
    return player;
}

inline ActorSnapshot Unit(uint32 entry, uint32 counter, float x, float y)
{
    ActorSnapshot unit;
    unit.Guid = ObjectGuid(HighGuid::Unit, entry, counter);
    unit.Entry = entry;
    unit.Kind = ActorKind::Summon;
    unit.Position = { CX + x, CY + y, CZ };
    unit.Alive = true;
    unit.HealthPct = 100.0f;
    return unit;
}

inline ActorSnapshot Construct(uint32 entry, uint32 counter, float x, float y,
    ObjectGuid victim, uint64 activatedExpiresAt)
{
    ActorSnapshot unit = Unit(entry, counter, x, y);
    unit.Attackable = unit.Selectable = unit.InCombat = true;
    unit.ReactAggressive = true;
    unit.VictimGuid = victim;
    unit.Auras.push_back({ 78740, unit.Guid, 1, activatedExpiresAt });
    return unit;
}

inline ActorSnapshot Inactive(uint32 entry, uint32 counter, float x, float y)
{
    ActorSnapshot unit = Unit(entry, counter, x, y);
    unit.InCombat = true;
    unit.Auras.push_back({ 78726, unit.Guid, 1, 0 });
    unit.Auras.push_back({ 82265, unit.Guid, 1, 0 });
    return unit;
}

// Canonical BWD 10N composition, Omnotron selection (Feral tank, Elemental).
inline Blackboard Board(char const* cohort, uint64 revision, uint64 now)
{
    Blackboard board;
    board.CurrentScope = Scope{ cohort, 3, 0, 2, "bwd.omnotron.encounter", 669, 7,
        "omnotron_defense_system" };
    board.Revision = revision;
    board.ObservedAtMs = now;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.omnotron.encounter";
    board.Players = {
        Player(40001, "tank", "blood_death_knight", -2.0f, -4.0f),
        Player(40002, "tank", "feral_druid_tank", 6.0f, -4.0f),
        Player(40003, "dps", "beast_mastery_hunter", 0.0f, 12.0f),
        Player(40004, "dps", "fire_mage", 4.0f, 12.0f),
        Player(40005, "healer", "holy_paladin", -4.0f, 12.0f),
        Player(40006, "dps", "retribution_paladin", -1.0f, -1.0f),
        Player(40007, "healer", "discipline_priest", 8.0f, 12.0f),
        Player(40008, "dps", "assassination_rogue", 1.0f, -1.0f),
        Player(40009, "dps", "elemental_shaman", -8.0f, 12.0f),
        Player(40010, "dps", "demonology_warlock", 12.0f, 12.0f),
    };
    return board;
}

inline ObjectGuid G(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }

inline BotNativeAction::Move const* MoveOf(AdaptiveOmnotronPlan const& plan)
{
    return plan.Movement ? std::get_if<BotNativeAction::Move>(&plan.Movement->Action) : nullptr;
}

inline float Dist(float x, float y, Vector3 const& p) { return std::hypot(x - p.X, y - p.Y); }
'''


def test_omnotron_strategy_targets_tanks_and_shields(tmp_path: Path) -> None:
    program = PRELUDE + r'''
int main()
{
    AdaptiveOmnotronStrategy strategy;
    uint64 const now = 1000000;

    // Pre-pull: the patrolling construct is not engaged, so the route owns
    // approach and pull.
    Blackboard prepull = Board("prepull", 1, now);
    ActorSnapshot patrol = Unit(O::ElectronEntry, 1, 0.0f, 0.0f);
    patrol.Attackable = patrol.Selectable = true;
    prepull.Summons = { patrol, Inactive(O::MagmatronEntry, 2, 16.0f, -6.0f) };
    CHECK(!strategy.Propose(prepull, G(40004), "dps").OwnsNode);

    // Engaged: Electron (older) on the DK, Magmatron (newer) on the druid.
    Blackboard board = Board("pair", 2, now);
    ActorSnapshot electron = Construct(O::ElectronEntry, 1, 0.0f, 0.0f, G(40001), now + 30000);
    ActorSnapshot magmatron = Construct(O::MagmatronEntry, 2, 8.0f, 0.0f, G(40002), now + 75000);
    board.Summons = { electron, magmatron, Inactive(O::ToxitronEntry, 3, -9.0f, -12.0f),
        Inactive(O::ArcanotronEntry, 4, 9.0f, -12.0f) };
    AdaptiveOmnotronPlan dk = strategy.Propose(board, G(40001), "tank");
    AdaptiveOmnotronPlan druid = strategy.Propose(board, G(40002), "tank");
    AdaptiveOmnotronPlan mage = strategy.Propose(board, G(40004), "dps");
    CHECK(dk.OwnsNode && dk.TankTarget == electron.Guid && dk.DamageTarget == electron.Guid);
    CHECK(druid.TankTarget == magmatron.Guid && druid.DamageTarget == magmatron.Guid);
    CHECK(mage.DamageTarget == magmatron.Guid);  // newest construct shields last
    CHECK(!mage.SuppressOffense && !mage.Movement);

    // Magmatron raises Barrier: damage moves to Electron, the druid holds
    // Magmatron without attacking and drags it away from Electron.
    Blackboard barrier = board;
    barrier.Revision = 3;
    barrier.Summons[1].Auras.push_back({ 79582, magmatron.Guid, 1, now + 10000 });
    AdaptiveOmnotronPlan druidShield = strategy.Propose(barrier, G(40002), "tank");
    AdaptiveOmnotronPlan rogue = strategy.Propose(barrier, G(40008), "dps");
    CHECK(druidShield.TankTarget == magmatron.Guid && druidShield.DamageTarget.IsEmpty());
    CHECK(druidShield.SuppressOffense
        && druidShield.SuppressReason == "tank_holds_shielded_construct");
    CHECK(druidShield.Movement
        && druidShield.Movement->Id.Mechanic == "tank_shield_separation");
    CHECK(rogue.DamageTarget == electron.Guid && !rogue.SuppressOffense);
    // Only unshielded active constructs may be damaged; the runtime restricts
    // the rest (direct casts and nearby area spells).
    CHECK(rogue.OffenseAllowed.size() == 1 && rogue.OffenseAllowed[0] == electron.Guid);
    CHECK(mage.OffenseAllowed.size() == 2);

    // A shield cast in progress already counts.
    Blackboard casting = board;
    casting.Revision = 4;
    casting.Summons[1].Cast = CastSnapshot{ 79582, ObjectGuid{}, now, false, false };
    CHECK(strategy.Propose(casting, G(40004), "dps").DamageTarget == electron.Guid);

    // Every active construct shielded: offense is suppressed.
    Blackboard allShielded = barrier;
    allShielded.Revision = 5;
    allShielded.Summons[0].Auras.push_back({ 79900, electron.Guid, 1, now + 10000 });
    AdaptiveOmnotronPlan idle = strategy.Propose(allShielded, G(40004), "dps");
    CHECK(idle.SuppressOffense && idle.SuppressReason == "all_constructs_shielded");

    // The shield ledger saw Magmatron's Barrier above; start the next
    // scenarios from a fresh ledger.
    O::ShieldLedger::ResetForTests();

    // Handover: Electron shuts down, a new Toxitron attacks a healer. The DK
    // (free) owns Toxitron and must take it; the druid keeps Magmatron.
    Blackboard handover = board;
    handover.Revision = 6;
    handover.Summons[0].Cast = CastSnapshot{ 78746, ObjectGuid{}, now, false, false };
    handover.Summons[2] = Construct(O::ToxitronEntry, 3, -9.0f, -12.0f, G(40005), now + 90000);
    AdaptiveOmnotronPlan dkHandover = strategy.Propose(handover, G(40001), "tank");
    CHECK(dkHandover.TankTarget == handover.Summons[2].Guid);
    CHECK(strategy.Propose(handover, G(40002), "tank").TankTarget == magmatron.Guid);
    CHECK(strategy.Propose(handover, G(40004), "dps").DamageTarget == handover.Summons[2].Guid);

    // Opening: one construct on the DK, the druid waits next to the construct
    // whose Recharging aura ends within the standby lead.
    Blackboard opening = Board("opening", 7, now);
    opening.Summons = { Construct(O::ElectronEntry, 1, 0.0f, 0.0f, G(40001), now + 80000),
        Inactive(O::ArcanotronEntry, 4, 12.0f, -14.0f) };
    opening.Summons[1].Auras.push_back({ 78699, ObjectGuid{}, 1, now + 8000 });
    AdaptiveOmnotronPlan standby = strategy.Propose(opening, G(40002), "tank");
    CHECK(standby.TankTarget.IsEmpty() && standby.DamageTarget.IsEmpty());
    CHECK(standby.SuppressOffense && standby.SuppressReason == "tank_standby_next_construct");
    CHECK(standby.Movement && standby.Movement->Id.Mechanic == "tank_standby_next_construct");
    // Before the standby lead the free tank assists on the focus.
    Blackboard early = opening;
    early.Revision = 71;
    early.Summons[1].Auras.back().ExpiresAtMs = now + 30000;
    AdaptiveOmnotronPlan assist = strategy.Propose(early, G(40002), "tank");
    CHECK(!assist.SuppressOffense && assist.DamageTarget == early.Summons[0].Guid);

    // A shielded construct that turned on someone else stays the owner's
    // TankTarget; the runtime taunts it under a single-cast allowance, so it
    // never enters any bot's OffenseAllowed (area spells stay refused).
    Blackboard stray = barrier;
    stray.Revision = 72;
    stray.Summons[1].VictimGuid = G(40007);
    AdaptiveOmnotronPlan owner = strategy.Propose(stray, G(40001), "tank");
    AdaptiveOmnotronPlan other = strategy.Propose(stray, G(40008), "dps");
    O::DutyPlan const strayDuty = O::BuildDutyPlan(stray, O::Observe(stray), O::LedgerMode::Peek);
    O::TankDuty const* druidDuty = strayDuty.TankDutyFor(G(40002));
    CHECK(druidDuty && druidDuty->Construct == magmatron.Guid);
    AdaptiveOmnotronPlan druidStray = strategy.Propose(stray, G(40002), "tank");
    CHECK(druidStray.TankTarget == magmatron.Guid && druidStray.SuppressOffense);
    CHECK(std::find(druidStray.OffenseAllowed.begin(), druidStray.OffenseAllowed.end(),
        magmatron.Guid) == druidStray.OffenseAllowed.end());
    CHECK(std::find(other.OffenseAllowed.begin(), other.OffenseAllowed.end(),
        magmatron.Guid) == other.OffenseAllowed.end());
    CHECK(owner.TankTarget == electron.Guid);

    O::ShieldLedger::ResetForTests();
    // Power Generator under the DK's construct: the DK walks it out; ranged
    // damage dealers stack in the field.
    Blackboard field = board;
    field.Revision = 8;
    field.Summons.push_back(Unit(O::PowerGeneratorEntry, 20, 1.0f, 0.0f));
    AdaptiveOmnotronPlan dkField = strategy.Propose(field, G(40001), "tank");
    AdaptiveOmnotronPlan lock = strategy.Propose(field, G(40010), "dps");
    AdaptiveOmnotronPlan rogueField = strategy.Propose(field, G(40008), "dps");
    CHECK(dkField.Movement && dkField.Movement->Id.Mechanic == "tank_generator_exit");
    if (BotNativeAction::Move const* move = MoveOf(dkField))
        CHECK(Dist(move->X, move->Y, field.Summons.back().Position) >= 14.0f);
    CHECK(lock.Movement && lock.Movement->Id.Mechanic == "power_generator_stack");
    if (BotNativeAction::Move const* move = MoveOf(lock))
        CHECK(Dist(move->X, move->Y, field.Summons.back().Position) <= 2.5f);
    CHECK(!rogueField.Movement);

    std::printf("ok\n");
    return failures ? 1 : 0;
}
'''
    assert _compile_and_run(tmp_path, program).strip() == "ok"


def test_omnotron_interrupt_rotation_and_dispels(tmp_path: Path) -> None:
    program = PRELUDE + r'''
static Blackboard ArcanotronBoard(uint64 revision, uint64 now, bool casting)
{
    Blackboard board = Board("interrupts", revision, now);
    ActorSnapshot arcanotron = Construct(O::ArcanotronEntry, 4, 0.0f, 0.0f, G(40001), now + 60000);
    if (casting)
        arcanotron.Cast = CastSnapshot{ 79710, G(40004), now, false, true };
    board.Summons = { arcanotron };
    return board;
}

int main()
{
    O::InterruptLedger::ResetForTests();
    AdaptiveOmnotronStrategy strategy;
    uint64 now = 2000000;

    // Pool by capability and reach: melee 10 s interrupts in range (Ret,
    // Rogue), ranged (Shaman 15 s, Mage 24 s), then the DK tank. Healers,
    // the hunter (BM) and the warlock have no executor interrupt; the Feral
    // tank's Skull Bash (60 s) comes last.
    Blackboard board = ArcanotronBoard(1, now, true);
    O::EncounterFacts facts = O::Observe(board);
    O::DutyPlan plan = O::BuildDutyPlan(board, facts, O::LedgerMode::Peek);
    CHECK(plan.Interrupt.Pool.size() == 6);
    if (plan.Interrupt.Pool.size() == 6)
    {
        CHECK(plan.Interrupt.Pool[0] == G(40006));
        CHECK(plan.Interrupt.Pool[1] == G(40008));
        CHECK(plan.Interrupt.Pool[2] == G(40009));
        CHECK(plan.Interrupt.Pool[3] == G(40001));
        CHECK(plan.Interrupt.Pool[4] == G(40004));
        CHECK(plan.Interrupt.Pool[5] == G(40002));
    }
    // A status peek never advances the rotation.
    CHECK(O::BuildDutyPlan(board, facts, O::LedgerMode::Peek).Interrupt.Ordinal == 1);

    // Cast 1: primary Ret interrupts at once; the Rogue backs up after 450 ms.
    CHECK(strategy.Propose(board, G(40006), "dps").InterruptTarget == board.Summons[0].Guid);
    CHECK(strategy.Propose(board, G(40008), "dps").InterruptTarget.IsEmpty());
    CHECK(strategy.Propose(board, G(40004), "dps").InterruptTarget.IsEmpty());
    Blackboard later = ArcanotronBoard(2, now + 500, true);
    CHECK(strategy.Propose(later, G(40008), "dps").InterruptTarget == later.Summons[0].Guid);
    CHECK(strategy.Propose(later, G(40006), "dps").InterruptTarget == later.Summons[0].Guid);

    // Cast ends, next cast: the rotation advances to the Rogue.
    strategy.Propose(ArcanotronBoard(3, now + 2000, false), G(40006), "dps");
    Blackboard second = ArcanotronBoard(4, now + 6500, true);
    CHECK(strategy.Propose(second, G(40008), "dps").InterruptTarget == second.Summons[0].Guid);
    CHECK(strategy.Propose(second, G(40006), "dps").InterruptTarget.IsEmpty());
    // An older snapshot never rewinds the ledger.
    strategy.Propose(ArcanotronBoard(2, now + 500, true), G(40006), "dps");
    CHECK(strategy.Propose(second, G(40008), "dps").InterruptTarget == second.Summons[0].Guid);

    // A player with a personal movement duty moves to the end of the pool.
    Blackboard conductor = ArcanotronBoard(5, now + 7000, true);
    conductor.Players[5].Auras.push_back({ 79888, ObjectGuid{}, 1, now + 17000 });
    O::DutyPlan duty = O::BuildDutyPlan(conductor, O::Observe(conductor), O::LedgerMode::Peek);
    CHECK(!duty.Interrupt.Pool.empty() && duty.Interrupt.Pool.back() == G(40006));

    // Under Power Conversion the rotation still interrupts Arcanotron, but
    // Arcanotron never enters OffenseAllowed: the interrupt alone is widened
    // at submission (see the restriction replay test).
    Blackboard converted = ArcanotronBoard(9, now + 7500, true);
    converted.Summons[0].Auras.push_back({ 79729, converted.Summons[0].Guid, 1, now + 17500 });
    AdaptiveOmnotronPlan convertedPlan = strategy.Propose(converted, G(40009), "dps");
    AdaptiveOmnotronPlan convertedIdle = strategy.Propose(converted, G(40010), "dps");
    CHECK(convertedIdle.OffenseAllowed.empty() && convertedIdle.SuppressOffense);
    CHECK(convertedPlan.InterruptTarget == converted.Summons[0].Guid);
    CHECK(convertedPlan.OffenseAllowed.empty() && convertedPlan.SuppressOffense);
    CHECK(convertedPlan.InterruptCastOrdinal >= 2);
    // Every landed interrupt procs Converted Power alike (spell_proc 79729
    // SpellTypeMask 0), so no interrupt is excluded under the shield.
    Blackboard marks = converted;
    marks.Revision = 10;
    marks.Players[2].ClassSpec = "marksmanship_hunter";
    O::DutyPlan const marksDuty = O::BuildDutyPlan(marks, O::Observe(marks), O::LedgerMode::Peek);
    CHECK(std::find(marksDuty.Interrupt.Pool.begin(), marksDuty.Interrupt.Pool.end(), G(40003))
        != marksDuty.Interrupt.Pool.end());

    // Not interruptible: no duty.
    Blackboard locked = ArcanotronBoard(6, now + 8000, true);
    locked.Summons[0].Cast->Interruptible = false;
    CHECK(strategy.Propose(locked, G(40008), "dps").InterruptTarget.IsEmpty());

    // Soaked In Poison: the Holy Paladin dispels 3 stacks first, the Ret
    // backs up a second carrier; the Feral tank never dispels.
    Blackboard poison = ArcanotronBoard(7, now + 9000, false);
    poison.Players[3].Auras.push_back({ 80011, ObjectGuid{}, 4, now + 30000 });
    poison.Players[8].Auras.push_back({ 80011, ObjectGuid{}, 3, now + 30000 });
    poison.Players[2].Auras.push_back({ 80011, ObjectGuid{}, 1, now + 30000 });
    CHECK(strategy.Propose(poison, G(40005), "healer").DispelTarget == G(40004));
    CHECK(strategy.Propose(poison, G(40006), "dps").DispelTarget == G(40009));
    CHECK(strategy.Propose(poison, G(40002), "tank").DispelTarget.IsEmpty());
    poison.Players[2].HealthPct = 40.0f;
    O::DutyPlan low = O::BuildDutyPlan(poison, O::Observe(poison), O::LedgerMode::Peek);
    CHECK(low.Dispels.size() == 2);

    std::printf("%s\n", O::BuildOmnotronDutyPlanStatusJson(&board).c_str());
    std::printf("ok\n");
    return failures ? 1 : 0;
}
'''
    output = _compile_and_run(tmp_path, program).strip().splitlines()
    assert output[-1] == "ok"
    assert output[0].startswith('{"applies":true,')
    assert '"pool":[40006,40008,40009,40001,40004,40002]' in output[0]


def test_omnotron_movement_mechanics(tmp_path: Path) -> None:
    program = PRELUDE + r'''
int main()
{
    AdaptiveOmnotronStrategy strategy;
    uint64 const now = 3000000;
    Blackboard board = Board("movement", 1, now);
    ActorSnapshot electron = Construct(O::ElectronEntry, 1, 0.0f, 0.0f, G(40001), now + 60000);
    ActorSnapshot magmatron = Construct(O::MagmatronEntry, 2, 8.0f, -2.0f, G(40002), now + 80000);
    board.Summons = { electron, magmatron };

    // Lightning Conductor: the carrier ends up farther than 8 yd from everyone.
    Blackboard conductor = board;
    conductor.Players[3].Auras.push_back({ 79888, electron.Guid, 1, now + 10000 });
    AdaptiveOmnotronPlan carrier = strategy.Propose(conductor, G(40004), "dps");
    CHECK(carrier.Movement && carrier.Movement->Id.Mechanic == "lightning_conductor_isolate");
    CHECK(carrier.Movement->ActionPriority == BotActionArbitration::Priority::Survival);
    if (BotNativeAction::Move const* move = MoveOf(carrier))
    {
        float nearest = 100.0f;
        for (ActorSnapshot const& other : conductor.Players)
            if (other.Guid != G(40004))
                nearest = std::min(nearest, Dist(move->X, move->Y, other.Position));
        CHECK(nearest > 8.0f);
        CHECK(std::hypot(move->X - CX, move->Y - CY) <= O::ArenaRadius + 0.01f);
    }
    // A neighbour inside 10 yd of the carrier steps away.
    AdaptiveOmnotronPlan neighbour = strategy.Propose(conductor, G(40003), "dps");
    CHECK(neighbour.Movement && neighbour.Movement->Id.Mechanic == "lightning_conductor_clear");

    // Acquiring Target on the hunter: others in the Magmatron->hunter line
    // step out; the hunter turns the line away from everyone.
    Blackboard acquire = board;
    acquire.Players[2].Position = { CX + 8.0f, CY + 16.0f, CZ };
    acquire.Players[2].Auras.push_back({ 79501, magmatron.Guid, 1, now + 4000 });
    acquire.Players[4].Position = { CX + 8.0f, CY + 8.0f, CZ };
    AdaptiveOmnotronPlan inLine = strategy.Propose(acquire, G(40005), "healer");
    CHECK(inLine.Movement && inLine.Movement->Id.Mechanic == "flamethrower_line_dodge");
    AdaptiveOmnotronPlan hunter = strategy.Propose(acquire, G(40003), "dps");
    CHECK(hunter.Movement && hunter.Movement->Id.Mechanic == "acquiring_target_line_clear");
    if (BotNativeAction::Move const* move = MoveOf(hunter))
    {
        O::FlamethrowerCone cone;
        cone.Origin = magmatron.Position;
        cone.Bearing = std::atan2(move->Y - magmatron.Position.Y, move->X - magmatron.Position.X);
        int exposed = 0;
        for (ActorSnapshot const& other : acquire.Players)
            if (other.Guid != G(40003) && O::InsideCone(cone, other.Position, 0.0f))
                ++exposed;
        CHECK(exposed == 0);
    }

    // Poison Bomb fixated on the mage: the mage kites away, a nearby player
    // leaves the blast radius, and ranged damage kills only a safe bomb.
    Blackboard bombs = board;
    ActorSnapshot bomb = Unit(O::PoisonBombEntry, 30, 4.0f, 8.0f);
    bomb.Attackable = bomb.Selectable = true;
    bomb.VictimGuid = G(40004);
    bombs.Summons.push_back(bomb);
    bombs.Players[3].Auras.push_back({ 80094, bomb.Guid, 1, now + 20000 });
    AdaptiveOmnotronPlan kiter = strategy.Propose(bombs, G(40004), "dps");
    CHECK(kiter.Movement && kiter.Movement->Id.Mechanic == "poison_bomb_kite");
    if (BotNativeAction::Move const* move = MoveOf(kiter))
        CHECK(Dist(move->X, move->Y, bomb.Position) > Dist(bombs.Players[3].Position.X,
            bombs.Players[3].Position.Y, bomb.Position));
    AdaptiveOmnotronPlan warlock = strategy.Propose(bombs, G(40010), "dps");
    CHECK(warlock.DamageTarget == magmatron.Guid);  // mage within 6 yd: not safe yet
    Blackboard safe = bombs;
    safe.Players[3].Position = { CX + 4.0f, CY + 20.0f, CZ };
    safe.Players[2].Position = { CX - 6.0f, CY + 14.0f, CZ };
    safe.Players[4].Position = { CX - 10.0f, CY + 12.0f, CZ };
    safe.Players[6].Position = { CX + 14.0f, CY + 4.0f, CZ };
    CHECK(strategy.Propose(safe, G(40010), "dps").DamageTarget == bomb.Guid);
    CHECK(strategy.Propose(safe, G(40008), "dps").DamageTarget == magmatron.Guid);

    // Chemical Cloud: a player inside 12 yd walks out past the edge.
    Blackboard cloud = board;
    cloud.Summons.push_back(Unit(O::ChemicalCloudEntry, 31, 8.0f, 14.0f));
    AdaptiveOmnotronPlan inCloud = strategy.Propose(cloud, G(40007), "healer");
    CHECK(inCloud.Movement && inCloud.Movement->Id.Mechanic == "omnotron_hazard_exit");
    if (BotNativeAction::Move const* move = MoveOf(inCloud))
        CHECK(Dist(move->X, move->Y, cloud.Summons.back().Position) > 12.0f);

    // A cloud near the arena edge: the exit is outside the cloud, not the rim.
    Blackboard edge = board;
    edge.Summons.push_back(Unit(O::ChemicalCloudEntry, 32, 12.0f, 0.0f));
    edge.Players[6].Position = { CX + 18.0f, CY, CZ };
    AdaptiveOmnotronPlan edgePlan = strategy.Propose(edge, G(40007), "healer");
    CHECK(edgePlan.Movement && edgePlan.Movement->Id.Mechanic == "omnotron_hazard_exit");
    if (BotNativeAction::Move const* move = MoveOf(edgePlan))
    {
        CHECK(Dist(move->X, move->Y, edge.Summons.back().Position) > 12.0f);
        CHECK(std::hypot(move->X - CX, move->Y - CY) <= O::ArenaRadius + 0.01f);
    }
    // Two clouds with a puddle between them: a clear point, not a loop.
    Blackboard maze = board;
    maze.Summons.push_back(Unit(O::ChemicalCloudEntry, 33, -8.0f, 8.0f));
    maze.Summons.push_back(Unit(O::ChemicalCloudEntry, 34, 12.0f, 8.0f));
    maze.Summons.push_back(Unit(O::PoisonPuddleEntry, 35, 2.0f, 8.0f));
    maze.Players[3].Position = { CX + 2.0f, CY + 8.0f, CZ };
    AdaptiveOmnotronPlan mazePlan = strategy.Propose(maze, G(40004), "dps");
    CHECK(mazePlan.Movement && mazePlan.Movement->Id.Mechanic == "omnotron_hazard_exit");
    if (BotNativeAction::Move const* move = MoveOf(mazePlan))
        CHECK(O::HazardDepth(O::Observe(maze), { move->X, move->Y, CZ }) <= 0.0f);

    // Encasing Shadows (heroic root): no movement proposal at all.
    Blackboard rooted = conductor;
    rooted.Players[3].Auras.push_back({ 92023, ObjectGuid{}, 1, now + 5000 });
    CHECK(!strategy.Propose(rooted, G(40004), "dps").Movement);

    // Off node: the strategy stays silent.
    Blackboard other = board;
    other.Route.NodeId = "bwd.maloriak.encounter";
    CHECK(!strategy.Propose(other, G(40004), "dps").OwnsNode);

    std::printf("ok\n");
    return failures ? 1 : 0;
}
'''
    assert _compile_and_run(tmp_path, program).strip() == "ok"


def test_omnotron_focus_prefers_a_spent_shield_and_tank_separation_slides(tmp_path: Path) -> None:
    program = PRELUDE + r"""
int main()
{
    O::ShieldLedger::ResetForTests();
    AdaptiveOmnotronStrategy strategy;
    uint64 const now = 4000000;
    auto pair = [&](uint64 revision)
    {
        Blackboard board = Board("spent", revision, now + revision * 100);
        board.Summons = {
            Construct(O::ElectronEntry, 1, 0.0f, 0.0f, G(40001), now + 30000),
            Construct(O::MagmatronEntry, 2, 8.0f, 0.0f, G(40002), now + 75000) };
        return board;
    };
    ObjectGuid const electron = pair(1).Summons[0].Guid;
    ObjectGuid const magmatron = pair(1).Summons[1].Guid;

    // Neither construct has shielded yet: the newest one is the focus.
    CHECK(strategy.Propose(pair(1), G(40004), "dps").DamageTarget == magmatron);
    // Electron shields: focus stays on Magmatron.
    Blackboard shielded = pair(2);
    shielded.Summons[0].Auras.push_back({ 79900, electron, 1, now + 12000 });
    CHECK(strategy.Propose(shielded, G(40004), "dps").DamageTarget == magmatron);
    // Electron's shield is gone: it cannot shield again this activation, so
    // it becomes the focus and Magmatron is left alone before its own shield.
    Blackboard spent = pair(3);
    AdaptiveOmnotronPlan mage = strategy.Propose(spent, G(40004), "dps");
    CHECK(mage.DamageTarget == electron);
    O::DutyPlan const duty = O::BuildDutyPlan(spent, O::Observe(spent), O::LedgerMode::Peek);
    CHECK(duty.ShieldSpent.size() == 1 && duty.ShieldSpent[0] == electron);
    CHECK(O::BuildOmnotronDutyPlanStatusJson(&spent).find("\"shield_spent\":[" + std::to_string(electron.GetCounter()) + "]") != std::string::npos);
    // Shutting down: focus returns to the newest construct.
    Blackboard shutting = pair(4);
    shutting.Summons[0].Cast = CastSnapshot{ 78746, ObjectGuid{}, now, false, false };
    CHECK(strategy.Propose(shutting, G(40004), "dps").DamageTarget == magmatron);
    // Inactive, then activated again 90 s later: the spent mark is gone.
    Blackboard inactive = pair(5);
    inactive.Summons[0] = Inactive(O::ElectronEntry, 1, 0.0f, 0.0f);
    strategy.Propose(inactive, G(40004), "dps");
    Blackboard again = pair(6);
    again.Summons[0].Auras.back().ExpiresAtMs = now + 120000;
    CHECK(strategy.Propose(again, G(40004), "dps").DamageTarget == electron);  // now the newest
    O::DutyPlan const fresh = O::BuildDutyPlan(again, O::Observe(again), O::LedgerMode::Peek);
    CHECK(fresh.ShieldSpent.empty());
    // A status Peek never marks anything.
    Blackboard peekOnly = pair(7);
    peekOnly.CurrentScope.CohortId = "peek-only";
    peekOnly.Summons[1].Auras.push_back({ 79582, magmatron, 1, now + 10000 });
    O::BuildOmnotronDutyPlanStatusJson(&peekOnly);
    peekOnly.Summons[1].Auras.pop_back();
    peekOnly.Revision = 8;
    CHECK(O::BuildDutyPlan(peekOnly, O::Observe(peekOnly), O::LedgerMode::Peek).ShieldSpent.empty());

    // Shield separation on the arena rim: the old straight push clamped to a
    // point beside the tank; the new one slides for a real gain or holds.
    Blackboard rim = pair(9);
    rim.CurrentScope.CohortId = "rim";
    rim.Players[1].Position = { CX + 19.5f, CY, CZ };
    rim.Summons[1].Position = { CX + 17.0f, CY, CZ };
    rim.Summons[0].Position = { CX + 9.0f, CY, CZ };
    rim.Summons[1].Auras.push_back({ 79582, magmatron, 1, now + 10000 });
    AdaptiveOmnotronPlan druid = strategy.Propose(rim, G(40002), "tank");
    CHECK(druid.Movement && druid.Movement->Id.Mechanic == "tank_shield_separation");
    if (BotNativeAction::Move const* move = MoveOf(druid))
    {
        float const before = std::hypot(rim.Summons[1].Position.X - rim.Summons[0].Position.X,
            rim.Summons[1].Position.Y - rim.Summons[0].Position.Y);
        CHECK(Dist(move->X, move->Y, rim.Summons[0].Position) >= before + O::ShieldSeparationMinimumGain);
        CHECK(std::hypot(move->X - CX, move->Y - CY) <= O::ArenaRadius + 0.01f);
        CHECK(Dist(move->X, move->Y, rim.Players[1].Position) >= 3.0f);
    }
    // Already far apart: no proposal at all.
    Blackboard apart = rim;
    apart.Revision = 10;
    apart.Summons[0].Position = { CX - 10.0f, CY, CZ };
    CHECK(!strategy.Propose(apart, G(40002), "tank").Movement);

    std::printf("ok\n");
    return failures ? 1 : 0;
}
"""
    assert _compile_and_run(tmp_path, program).strip() == "ok"


def test_omnotron_interrupt_ledger_is_scoped_per_cohort_and_wipe(tmp_path: Path) -> None:
    program = PRELUDE + r"""
int main()
{
    O::InterruptLedger::ResetForTests();
    ObjectGuid const caster = ObjectGuid(HighGuid::Unit, O::ArcanotronEntry, uint32(4));
    auto board = [](char const* cohort, uint32 wipe, uint64 revision, uint64 now)
    {
        Blackboard b = Board(cohort, revision, now);
        b.CurrentScope.WipeGeneration = wipe;
        return b;
    };
    uint64 const now = 5000000;
    // Shard A sees three casts, shard B one, on the same caster GUID.
    uint64 revision = 1;
    for (int cast = 0; cast < 3; ++cast)
    {
        O::InterruptLedger::Observe(board("shard-a", 0, revision, now + revision), caster, true);
        ++revision;
        O::InterruptLedger::Observe(board("shard-a", 0, revision, now + revision), caster, false);
        ++revision;
    }
    O::InterruptCastObservation const b1 =
        O::InterruptLedger::Observe(board("shard-b", 0, 1, now), caster, true);
    CHECK(b1.Ordinal == 1);
    O::InterruptCastObservation const a4 =
        O::InterruptLedger::Observe(board("shard-a", 0, revision, now + revision), caster, true);
    CHECK(a4.Ordinal == 4);
    // Same cast observed again (same or later revision): no new ordinal.
    CHECK(O::InterruptLedger::Observe(board("shard-a", 0, revision + 1, now + revision + 1), caster, true).Ordinal == 4);
    // An older revision never rewinds or advances.
    CHECK(O::InterruptLedger::Observe(board("shard-a", 0, 1, now + 1), caster, false).Ordinal == 4);
    // A wipe starts a new generation: the rotation restarts at 1.
    CHECK(O::InterruptLedger::Observe(board("shard-a", 1, revision + 2, now + revision + 2), caster, true).Ordinal == 1);
    // Peek never changes a count.
    CHECK(O::InterruptLedger::Peek(board("shard-b", 0, 9, now + 9), caster, true).Ordinal == 1);
    CHECK(O::InterruptLedger::Peek(board("shard-b", 0, 9, now + 9), caster, false).Ordinal == 1);
    CHECK(O::InterruptLedger::Observe(board("shard-b", 0, 10, now + 10), caster, true).Ordinal == 1);
    // Idle entries age out.
    uint64 const later = now + O::InterruptLedger::IdleExpiryMs + 100000;
    CHECK(O::InterruptLedger::Observe(board("shard-c", 0, 1, later), caster, true).Ordinal == 1);
    CHECK(O::InterruptLedger::Peek(board("shard-b", 0, 11, later), caster, false).Ordinal == 0);

    std::printf("ok\n");
    return failures ? 1 : 0;
}
"""
    assert _compile_and_run(tmp_path, program).strip() == "ok"


def test_omnotron_restriction_replay_scopes_the_single_cast_allowance(tmp_path: Path) -> None:
    program = PRELUDE.replace(
        '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotAdaptiveOmnotronStrategy.h"',
        '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotAdaptiveOmnotronStrategy.h"\n'
        '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronOffenseAuthority.h"') + r"""
static bool Protected(uint64 owner, ActorSnapshot const& unit)
{
    return BotRaidAreaAuthority::IsProtectedEncounterTarget(owner, unit.Entry, 0,
        unit.Guid.GetRawValue());
}

int main()
{
    O::InterruptLedger::ResetForTests();
    O::ShieldLedger::ResetForTests();
    AdaptiveOmnotronStrategy strategy;
    uint64 const now = 6000000;
    // Arcanotron under Power Conversion casts Annihilator; Toxitron is the
    // other active construct. The Ret paladin is the primary interrupter.
    Blackboard board = Board("replay", 1, now);
    ActorSnapshot arcanotron = Construct(O::ArcanotronEntry, 4, 0.0f, 0.0f, G(40001), now + 30000);
    arcanotron.Auras.push_back({ 79729, arcanotron.Guid, 1, now + 9000 });
    arcanotron.Cast = CastSnapshot{ 79710, G(40004), now, false, true };
    ActorSnapshot toxitron = Construct(O::ToxitronEntry, 3, 10.0f, 0.0f, G(40002), now + 75000);
    ActorSnapshot bomb = Unit(O::PoisonBombEntry, 30, 16.0f, 10.0f);
    board.Summons = { arcanotron, toxitron, bomb };
    AdaptiveOmnotronPlan ret = strategy.Propose(board, G(40006), "dps");
    CHECK(ret.InterruptTarget == arcanotron.Guid);
    CHECK(ret.OffenseAllowed.size() == 1 && ret.OffenseAllowed[0] == toxitron.Guid);

    // Tick restriction built from the plan, as SubmitAdaptiveOmnotronRouteAuthority applies it.
    uint64 const owner = G(40006).GetRawValue();
    uint64 const bystander = G(40008).GetRawValue();
    O::OffenseRestriction const restriction = O::BuildOffenseRestriction(ret.OffenseAllowed);
    CHECK(restriction.Entries.size() == 4 && restriction.AllowedGuids.size() == 1);
    O::ApplyOffenseRestriction(owner, restriction);
    O::ApplyOffenseRestriction(bystander, O::BuildOffenseRestriction(
        strategy.Propose(board, G(40008), "dps").OffenseAllowed));
    CHECK(Protected(owner, arcanotron));       // shielded: every offense path refused
    CHECK(!Protected(owner, toxitron));        // unshielded focus allowed
    CHECK(!Protected(owner, bomb));            // bombs are never restricted
    CHECK(BotRaidAreaAuthority::HasProtectedEncounterEntries(owner));

    {
        // The interrupt Attempt: exactly one cast under the allowance.
        O::SingleCastAllowance allowance(owner, restriction, arcanotron.Guid);
        CHECK(allowance.Widened());
        CHECK(!Protected(owner, arcanotron));
        CHECK(Protected(bystander, arcanotron));  // other bots keep the restriction
        // An allowance for an already allowed target changes nothing.
        O::SingleCastAllowance noop(owner, restriction, toxitron.Guid);
        CHECK(!noop.Widened());
    }
    CHECK(Protected(owner, arcanotron));       // restored right after the cast
    CHECK(!Protected(owner, toxitron));

    // Once the shield ends, Arcanotron is allowed by the plan itself.
    Blackboard after = board;
    after.Revision = 2;
    after.Summons[0].Auras.pop_back();
    AdaptiveOmnotronPlan retAfter = strategy.Propose(after, G(40006), "dps");
    O::ApplyOffenseRestriction(owner, O::BuildOffenseRestriction(retAfter.OffenseAllowed));
    CHECK(!Protected(owner, after.Summons[0]));

    // Leaving the node (no restriction set) keeps nothing restricted.
    BotRaidAreaAuthority::SetCurrentEncounterRestrictions(owner, {}, {});
    CHECK(!Protected(owner, arcanotron));
    BotRaidAreaAuthority::SetCurrentEncounterRestrictions(bystander, {}, {});

    std::printf("ok\n");
    return failures ? 1 : 0;
}
"""
    assert _compile_and_run(tmp_path, program).strip() == "ok"


def test_omnotron_strategy_headers_stay_small() -> None:
    for path in sorted(OMNOTRON.glob("*")):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path
