"""Header-only replay of the adaptive Chimaeron strategy on the canonical 10N composition.

The C++ program builds blackboards the way the runtime publishes them and checks
every decision the strategy owns: capability duties, prewake staging, mixture
spread, outage stack, the Break/Double Attack taunt exchange, healer floor
assignments, the burn window, raid cooldowns and Mortality absorbs.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHIMAERON = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron"
SCRIPT = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_chimaeron.cpp"
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]

PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotAdaptiveChimaeronStrategy.h"
#include <cmath>
#include <cstdio>
#include <map>
#include <string>
#include <vector>

using namespace BotEncounter;
namespace C = BotEncounter::Chimaeron;

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { ++failures; \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); } } while (0)

constexpr float HomeX = -104.738f, HomeY = 20.592f, HomeZ = 72.14094f;
constexpr uint32 DK = 11002001, DRUID = 11002002, HUNTER = 11002003, MAGE = 11002004,
    HOLY = 11002005, RET = 11002006, DISC = 11002007, ROGUE = 11002008,
    SHAMAN = 11002009, LOCK = 11002010;

static ObjectGuid G(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }

static ActorSnapshot Member(uint32 guid, char const* role, char const* spec)
{
    ActorSnapshot player;
    player.Guid = G(guid);
    player.Kind = ActorKind::Player;
    player.Role = role;
    player.ClassSpec = spec;
    player.Position = { -114.389f, 43.1875f, 73.9f };
    player.Health = player.MaxHealth = 150000;
    player.HealthPct = 100.0f;
    player.Alive = true;
    return player;
}

static Blackboard Board(char const* node, bool engaged)
{
    Blackboard board;
    board.CurrentScope = Scope{ "blackwing_descent_10n_chimaeron_c0", 3, 0, 2, node, 669, 1,
        "chimaeron" };
    board.Revision = 40;
    board.ObservedAtMs = 1000000;
    board.NativeBossState = engaged ? "in_progress" : "not_started";
    board.Route.NodeId = node;
    board.Route.NavigationHints.push_back({ HomeX, HomeY, HomeZ });
    board.Players = {
        Member(DK, "tank", "blood_death_knight"),
        Member(DRUID, "tank", "feral_druid_tank"),
        Member(HUNTER, "dps", "beast_mastery_hunter"),
        Member(MAGE, "dps", "fire_mage"),
        Member(HOLY, "healer", "holy_paladin"),
        Member(RET, "dps", "retribution_paladin"),
        Member(DISC, "healer", "discipline_priest"),
        Member(ROGUE, "dps", "assassination_rogue"),
        Member(SHAMAN, "healer", "restoration_shaman"),
        Member(LOCK, "dps", "demonology_warlock"),
    };
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, uint32(C::BossEntry), uint32(250113));
    boss.Entry = C::BossEntry;
    boss.Position = { HomeX, HomeY, HomeZ };
    boss.Alive = boss.Attackable = boss.Selectable = true;
    boss.Health = boss.MaxHealth = 25900000;
    boss.HealthPct = 100.0f;
    if (engaged)
    {
        boss.InCombat = true;
        boss.ReactAggressive = true;
        boss.VictimGuid = G(DK);
        for (ActorSnapshot& player : board.Players)
            player.Auras.push_back({ C::FinklesMixtureSpell, ObjectGuid(), 1, 0 });
    }
    board.Hostiles = { boss };
    return board;
}

static ActorSnapshot& P(Blackboard& board, uint32 guid)
{
    for (ActorSnapshot& player : board.Players)
        if (player.Guid == G(guid))
            return player;
    std::fprintf(stderr, "missing player %u\n", guid);
    std::abort();
}

static ActorSnapshot& Boss(Blackboard& board) { return board.Hostiles.front(); }

static char const* RoleOf(Blackboard const& board, uint32 guid)
{
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid == G(guid))
            return player.Role.c_str();
    return "dps";
}

static AdaptiveChimaeronPlan Plan(Blackboard const& board, uint32 guid,
    ChimaeronEncounterMemory* memory = nullptr)
{
    return AdaptiveChimaeronStrategy().Propose(board, G(guid), RoleOf(board, guid), memory);
}

static bool MoveOf(AdaptiveChimaeronPlan const& plan, C::Point& out)
{
    if (!plan.Movement)
        return false;
    auto const* move = std::get_if<BotNativeAction::Move>(&plan.Movement->Action);
    if (!move)
        return false;
    out = { move->X, move->Y };
    return true;
}

static uint32 CastOf(AdaptiveChimaeronPlan const& plan, ObjectGuid* target = nullptr)
{
    if (!plan.Action)
        return 0;
    auto const* cast = std::get_if<BotNativeAction::CastSpell>(&plan.Action->Action);
    if (!cast)
        return 0;
    if (target)
        *target = cast->Target;
    return cast->SpellId;
}

static std::vector<uint32> Everyone()
{
    return { DK, DRUID, HUNTER, MAGE, HOLY, RET, DISC, ROGUE, SHAMAN, LOCK };
}

static float MinimumGap(std::map<uint32, C::Point> const& points)
{
    float gap = 1000.0f;
    for (auto const& [left, a] : points)
        for (auto const& [right, b] : points)
            if (left < right)
                gap = std::min(gap, C::Distance(a, b));
    return gap;
}

static std::map<uint32, C::Point> SpreadSlots(Blackboard const& board)
{
    C::Duties const duties = C::BuildDuties(board);
    C::Point const centre = C::FormationCentre(board, Boss(const_cast<Blackboard&>(board)));
    std::map<uint32, C::Point> slots;
    for (ActorSnapshot const& player : board.Players)
        if (std::optional<C::Point> slot = C::SpreadSlot(duties, centre, player.Guid))
            slots[player.Guid.GetCounter()] = *slot;
    return slots;
}

static std::map<uint32, C::Point> Destinations(Blackboard const& board)
{
    std::map<uint32, C::Point> result;
    for (uint32 guid : Everyone())
    {
        C::Point point;
        if (MoveOf(Plan(board, guid), point))
            result[guid] = point;
    }
    return result;
}

static void TestDuties()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    C::Duties const duties = C::BuildDuties(board);
    CHECK(duties.BreakTank == G(DK));
    CHECK(duties.DoubleAttackTank == G(DRUID));
    CHECK((duties.Healers == std::vector<ObjectGuid>{ G(HOLY), G(DISC), G(SHAMAN) }));
    CHECK((duties.Melee == std::vector<ObjectGuid>{ G(RET), G(ROGUE) }));
    CHECK((duties.Ranged == std::vector<ObjectGuid>{ G(HUNTER), G(MAGE), G(HOLY), G(DISC),
        G(SHAMAN), G(LOCK) }));
    CHECK((duties.RangedHealers == std::vector<ObjectGuid>{ G(HOLY), G(DISC), G(SHAMAN) }));
    CHECK(duties.LustOwner == G(MAGE) && duties.LustSpell == 80353);
    CHECK(duties.BarrierOwner == G(DISC));
    CHECK(duties.SpiritLinkOwner == G(SHAMAN));
    CHECK(C::DutiesJson(duties) == "{\"break_tank\":11002001,\"double_attack_tank\":11002002,"
        "\"healers\":[11002005,11002007,11002009],\"melee\":[11002006,11002008],"
        "\"ranged\":[11002003,11002004,11002005,11002007,11002009,11002010],"
        "\"lust_owner\":11002004,\"barrier_owner\":11002007,\"spirit_link_owner\":11002009}");

    // A configured main-tank lease wins over the capability ranking.
    AssignmentLease lease;
    lease.Kind = AssignmentKind::Tank;
    lease.Slot = "main_tank";
    lease.AssigneeGuid = G(DRUID);
    board.Assignments.push_back(lease);
    C::Duties const leased = C::BuildDuties(board);
    CHECK(leased.BreakTank == G(DRUID) && leased.DoubleAttackTank == G(DK));

    // A dead Break tank hands the boss to the surviving tank.
    Blackboard deadTank = Board("bwd.chimaeron.encounter", true);
    P(deadTank, DK).Alive = false;
    C::Duties const survivor = C::BuildDuties(deadTank);
    CHECK(survivor.BreakTank == G(DRUID) && survivor.DoubleAttackTank.IsEmpty());

    // Without a mage the shaman lusts (Bloodlust; the runtime casts Heroism
    // when that is the variant the bot knows). Mages always rank first.
    Blackboard noMage = Board("bwd.chimaeron.encounter", true);
    P(noMage, MAGE).ClassSpec = "affliction_warlock";
    C::Duties const shamanLust = C::BuildDuties(noMage);
    CHECK(shamanLust.LustOwner == G(SHAMAN) && shamanLust.LustSpell == 2825);
    P(noMage, SHAMAN).Alive = false;
    CHECK(C::BuildDuties(noMage).LustOwner.IsEmpty());
    Blackboard twoMages = Board("bwd.chimaeron.encounter", true);
    P(twoMages, LOCK).ClassSpec = "frost_mage";
    CHECK(C::BuildDuties(twoMages).LustOwner == G(MAGE));
}

static void TestPrewake()
{
    Blackboard board = Board("bwd.chimaeron.wake_wait", false);
    std::map<uint32, C::Point> const moves = Destinations(board);
    CHECK(moves.size() == 10);
    C::Point const boss{ HomeX, HomeY };
    float const tankDistance = C::Distance(moves.at(DK), boss);
    CHECK(std::fabs(tankDistance - 9.0f) < 0.01f);
    for (auto const& [guid, point] : moves)
        if (guid != DK)
            CHECK(C::Distance(point, boss) >= 16.0f - 0.01f);
    AdaptiveChimaeronPlan const plan = Plan(board, HUNTER);
    CHECK(!plan.OwnsNode);
    CHECK(plan.SuppressOffense && plan.SuppressReason == "prewake_boss_asleep");
    CHECK(plan.DamageTarget.IsEmpty());
    CHECK(!plan.Action);
    CHECK(plan.EncounterPhase == C::Phase::Prewake);

    // A patrol fighting the raid lifts the prewake suppression; the sleeping
    // boss stays off limits (no damage target is published).
    Blackboard patrol = Board("bwd.chimaeron.regroup", false);
    ActorSnapshot trash;
    trash.Guid = ObjectGuid(HighGuid::Unit, uint32(42800), uint32(700));
    trash.Entry = 42800;
    trash.Alive = trash.Attackable = trash.Selectable = trash.InCombat = true;
    trash.VictimGuid = G(DK);
    patrol.Hostiles.push_back(trash);
    AdaptiveChimaeronPlan const fighting = Plan(patrol, ROGUE);
    CHECK(fighting.EncounterPhase == C::Phase::Prewake);
    CHECK(!fighting.SuppressOffense && fighting.DamageTarget.IsEmpty());
    patrol.Hostiles.back().VictimGuid.Clear();
    CHECK(Plan(patrol, ROGUE).SuppressOffense);

    // Once the boss wakes the wait node no longer stages anyone.
    Boss(board).InCombat = true;
    Boss(board).VictimGuid = G(DK);
    CHECK(Plan(board, HUNTER).EncounterPhase == C::Phase::None);
    CHECK(!Plan(board, HUNTER).Movement);
}

static void TestMixtureSpread()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    std::map<uint32, C::Point> const moves = Destinations(board);
    CHECK(moves.size() == 10);
    C::Point const boss{ HomeX, HomeY };
    std::vector<uint32> const guids = Everyone();
    for (std::size_t i = 0; i < guids.size(); ++i)
        for (std::size_t j = i + 1; j < guids.size(); ++j)
        {
            float const gap = C::Distance(moves.at(guids[i]), moves.at(guids[j]));
            if (gap < C::MinimumSpreadSlotGap - 0.01f)
                std::fprintf(stderr, "spread gap %u-%u %.2f\n", guids[i], guids[j], gap);
            CHECK(gap >= C::MinimumSpreadSlotGap - 0.01f);
        }
    for (auto const& [guid, point] : moves)
    {
        CHECK(point.X >= C::ChamberMinX && point.X <= C::ChamberMaxX);
        CHECK(point.Y >= C::ChamberMinY && point.Y <= C::ChamberMaxY);
        CHECK(C::Distance(point, boss) <= 22.5f);
    }
    for (uint32 melee : { RET, ROGUE })
        CHECK(C::Distance(moves.at(melee), boss) <= 12.0f);
    for (uint32 healer : { HOLY, DISC, SHAMAN })
        for (uint32 tank : { DK, DRUID })
            CHECK(C::Distance(moves.at(healer), moves.at(tank)) <= 38.0f);

    // Members standing in their slots are left alone.
    for (auto const& [guid, point] : moves)
        P(board, guid).Position = { point.X, point.Y, HomeZ };
    CHECK(Destinations(board).empty());

    // Every member at the edge of its arrival tolerance, pushed toward its
    // nearest neighbour's slot: nobody moves, and nobody shares a Caustic
    // Slime split (6 yd) with anybody else.
    Blackboard edge = board;
    std::map<uint32, C::Point> placed;
    for (auto const& [guid, point] : moves)
    {
        C::Point nearest = point;
        float best = 1000.0f;
        for (auto const& [other, otherPoint] : moves)
            if (other != guid && C::Distance(point, otherPoint) < best)
            {
                best = C::Distance(point, otherPoint);
                nearest = otherPoint;
            }
        float const shift = C::SpreadTolerance - 0.01f;
        C::Point const shifted{ point.X + (nearest.X - point.X) / best * shift,
            point.Y + (nearest.Y - point.Y) / best * shift };
        P(edge, guid).Position = { shifted.X, shifted.Y, HomeZ };
        placed[guid] = shifted;
    }
    CHECK(Destinations(edge).empty());
    CHECK(MinimumGap(placed) > 6.0f);
    AdaptiveChimaeronPlan const plan = Plan(board, MAGE);
    CHECK(plan.OwnsNode && plan.DamageTarget == Boss(board).Guid);
    CHECK(!plan.SuppressOffense && !plan.HealingDisabled);
    CHECK(plan.Duty == "ranged");
    CHECK(Plan(board, DK).Duty == "break_tank");
    CHECK(Plan(board, DRUID).Duty == "double_attack_tank");
    CHECK(Plan(board, HOLY).Duty == "tank_healer");
    CHECK(Plan(board, SHAMAN).Duty == "raid_healer");
    CHECK(Plan(board, ROGUE).Duty == "melee");
}

// Non-canonical rosters keep the same guarantee: up to three melee on the
// inner arc, six on the 22 yd arc, overflow on the 33 yd arc.
static void TestAlternativeRosterSpacing()
{
    Blackboard fourMelee = Board("bwd.chimaeron.encounter", true);
    P(fourMelee, HUNTER).ClassSpec = "combat_rogue";
    P(fourMelee, LOCK).ClassSpec = "fury_warrior";
    std::map<uint32, C::Point> const melee = SpreadSlots(fourMelee);
    CHECK(melee.size() == 10);
    CHECK(MinimumGap(melee) >= C::MinimumSpreadSlotGap - 0.01f);

    Blackboard oneMelee = Board("bwd.chimaeron.encounter", true);
    P(oneMelee, RET).ClassSpec = "shadow_priest";
    std::map<uint32, C::Point> const ranged = SpreadSlots(oneMelee);
    CHECK(ranged.size() == 10);
    CHECK(MinimumGap(ranged) >= C::MinimumSpreadSlotGap - 0.01f);
    // Healers stay on the 22 yd arc, inside heal range of both tanks.
    C::Point const boss{ HomeX, HomeY };
    for (uint32 healer : { HOLY, DISC, SHAMAN })
    {
        CHECK(std::fabs(C::Distance(ranged.at(healer), boss) - C::RangedRadius) < 0.01f);
        for (uint32 tank : { DK, DRUID })
            CHECK(C::Distance(ranged.at(healer), ranged.at(tank)) <= 38.0f);
    }
}

static void TestOutageStack()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    for (ActorSnapshot& player : board.Players)
        player.Auras.clear();
    Boss(board).Auras.push_back({ C::FeudSpell, ObjectGuid(), 1, board.ObservedAtMs + 20000 });
    std::map<uint32, C::Point> const moves = Destinations(board);
    CHECK(moves.size() == 10);
    CHECK(Plan(board, HUNTER).EncounterPhase == C::Phase::Outage);
    C::Point const stack{ HomeX, HomeY - 8.0f };
    for (auto const& [guid, point] : moves)
    {
        CHECK(C::Distance(point, stack) <= 1.51f);
        for (auto const& [other, otherPoint] : moves)
            CHECK(C::Distance(point, otherPoint) <= 3.01f);
    }
    // One stragger returning from far away is pulled into the stack; a member
    // inside the arrival tolerance is left alone.
    for (auto const& [guid, point] : moves)
        P(board, guid).Position = { point.X + 0.5f, point.Y, HomeZ };
    CHECK(Destinations(board).empty());
}

static void TestTauntExchange()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    ObjectGuid const boss = Boss(board).Guid;
    ObjectGuid target;
    // Plain phase one: the Break tank holds, nobody taunts.
    CHECK(!Plan(board, DK).Action && !Plan(board, DRUID).Action);

    // Double Attack on the boss while the Break tank holds: the Feral taunts.
    Boss(board).Auras.push_back({ C::DoubleAttackSpell, boss, 1, 0 });
    CHECK(CastOf(Plan(board, DRUID), &target) == 6795 && target == boss);
    CHECK(Plan(board, DRUID).Action->Id.Mechanic == "taunt_double_attack_soak");
    CHECK(!Plan(board, DK).Action);

    // While the charge is up the Break tank does not take the boss back.
    Boss(board).VictimGuid = G(DRUID);
    CHECK(!Plan(board, DK).Action && !Plan(board, DRUID).Action);

    // The doubled swing consumed the charge: the Break tank taunts back.
    Boss(board).Auras.clear();
    CHECK(CastOf(Plan(board, DK), &target) == 56222 && target == boss);
    CHECK(Plan(board, DK).Action->Id.Mechanic == "taunt_back_break_holder");

    // Feud pacifies the boss: no exchange until its last 2.5 seconds.
    Boss(board).VictimGuid = G(DK);
    Boss(board).Auras = { { C::DoubleAttackSpell, boss, 1, 0 },
        { C::FeudSpell, boss, 1, board.ObservedAtMs + 10000 } };
    CHECK(!Plan(board, DRUID).Action);
    Boss(board).Auras[1].ExpiresAtMs = board.ObservedAtMs + 2000;
    CHECK(CastOf(Plan(board, DRUID)) == 6795);

    // A non-tank victim (wake-up pick) is taken by the Break tank.
    Boss(board).Auras.clear();
    Boss(board).VictimGuid = G(DISC);
    CHECK(CastOf(Plan(board, DK)) == 56222);
    CHECK(Plan(board, DK).Action->Id.Mechanic == "taunt_recover_non_tank_victim");
    CHECK(!Plan(board, DRUID).Action);

    // Held at 21% (Massacre casting, damage over time drifted the boss into
    // the handoff range): no handoff; the ordinary exchange continues.
    Boss(board).VictimGuid = G(DK);
    Boss(board).HealthPct = 21.0f;
    P(board, DK).HealthPct = P(board, DRUID).HealthPct = 100.0f;
    Boss(board).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), board.ObservedAtMs, false, false };
    ChimaeronEncounterMemory druidMemory;
    ChimaeronEncounterMemory dkMemory;
    CHECK(Plan(board, ROGUE).SuppressOffense);
    CHECK(!Plan(board, DRUID, &druidMemory).Action);
    Boss(board).Auras = { { C::DoubleAttackSpell, boss, 1, 0 } };
    CHECK(Plan(board, DRUID, &druidMemory).Action
        && Plan(board, DRUID, &druidMemory).Action->Id.Mechanic == "taunt_double_attack_soak");
    Boss(board).VictimGuid = G(DRUID);
    Boss(board).Auras.clear();
    CHECK(Plan(board, DK, &dkMemory).Action
        && Plan(board, DK, &dkMemory).Action->Id.Mechanic == "taunt_back_break_holder");
    CHECK(!druidMemory.BurnReleased && !dkMemory.BurnReleased);

    // The raid is ready: the burn releases and the fresh Feral takes the boss
    // into Mortality; the Break tank does not take it back.
    Boss(board).VictimGuid = G(DK);
    Boss(board).Cast.reset();
    CHECK(Plan(board, DRUID, &druidMemory).Action && Plan(board, DRUID, &druidMemory).Action->Id.Mechanic
        == "taunt_mortality_handoff");
    CHECK(druidMemory.BurnReleased);
    // Latched: a Massacre cast after the release does not cancel the handoff.
    Boss(board).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), board.ObservedAtMs, false, false };
    CHECK(Plan(board, DRUID, &druidMemory).Action && Plan(board, DRUID, &druidMemory).Action->Id.Mechanic
        == "taunt_mortality_handoff");
    Boss(board).Cast.reset();
    Boss(board).VictimGuid = G(DRUID);
    CHECK(!Plan(board, DK).Action);

    // Mortality: immune to taunt, no exchange at all.
    Boss(board).HealthPct = 19.0f;
    Boss(board).VictimGuid = G(DK);
    Boss(board).Auras = { { C::MortalityBossSpell, boss, 1, 0 }, { C::DoubleAttackSpell, boss, 1, 0 } };
    CHECK(!Plan(board, DRUID).Action && !Plan(board, DK).Action);
}

static void TestHealingFloor()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    // Right after Massacre every protected member sits at 1 health.
    for (ActorSnapshot& player : board.Players)
    {
        player.Health = 1;
        player.HealthPct = 100.0f / 150000.0f;
    }
    CHECK(Plan(board, HOLY).PriorityHealTarget == G(DK));    // victim, next swing
    CHECK(Plan(board, DISC).PriorityHealTarget == G(DK));    // second healer on the victim
    CHECK(Plan(board, SHAMAN).PriorityHealTarget == G(HUNTER));
    CHECK(Plan(board, MAGE).PriorityHealTarget.IsEmpty());   // not a healer

    // The victim is safe; the floor list splits across the healers.
    P(board, DK).Health = 150000;
    P(board, DK).HealthPct = 100.0f;
    CHECK(Plan(board, HOLY).PriorityHealTarget == G(DRUID)); // first tank on the floor
    CHECK(Plan(board, DISC).PriorityHealTarget == G(HUNTER));
    CHECK(Plan(board, SHAMAN).PriorityHealTarget == G(MAGE));

    // Double Attack pending: the soaker is healed toward full first.
    Blackboard pending = Board("bwd.chimaeron.encounter", true);
    Boss(pending).Auras.push_back({ C::DoubleAttackSpell, Boss(pending).Guid, 1, 0 });
    P(pending, DRUID).Health = 105000;
    P(pending, DRUID).HealthPct = 70.0f;
    P(pending, LOCK).Health = 8000;
    P(pending, LOCK).HealthPct = 5.3f;
    CHECK(Plan(pending, HOLY).PriorityHealTarget == G(DRUID));
    CHECK(Plan(pending, DISC).PriorityHealTarget == G(LOCK));
    CHECK(Plan(pending, SHAMAN).PriorityHealTarget == G(LOCK));

    // Nobody near the floor and tanks healthy: no published target, the
    // default lowest-health selection stays in charge.
    Blackboard healthy = Board("bwd.chimaeron.encounter", true);
    CHECK(Plan(healthy, HOLY).PriorityHealTarget.IsEmpty());

    // Outage: no floor, health percentage order, split across healers.
    Blackboard outage = Board("bwd.chimaeron.encounter", true);
    for (ActorSnapshot& player : outage.Players)
        player.Auras.clear();
    P(outage, ROGUE).HealthPct = 40.0f;
    P(outage, MAGE).HealthPct = 55.0f;
    P(outage, HUNTER).HealthPct = 70.0f;
    CHECK(Plan(outage, HOLY).PriorityHealTarget == G(ROGUE));
    CHECK(Plan(outage, DISC).PriorityHealTarget == G(MAGE));
    CHECK(Plan(outage, SHAMAN).PriorityHealTarget == G(HUNTER));

    // In the burn window the Break tank is topped to the 80% readiness bar.
    Blackboard window = Board("bwd.chimaeron.encounter", true);
    Boss(window).HealthPct = 22.0f;
    P(window, DK).HealthPct = 70.0f;
    CHECK(Plan(window, HOLY).PriorityHealTarget == G(DK));
    Boss(window).HealthPct = 50.0f;
    CHECK(Plan(window, HOLY).PriorityHealTarget.IsEmpty());

    // Mortality: healing is 99% reduced, nothing is published.
    Blackboard mortality = Board("bwd.chimaeron.encounter", true);
    Boss(mortality).Auras.push_back({ C::MortalityBossSpell, Boss(mortality).Guid, 1, 0 });
    P(mortality, DRUID).Health = 5000;
    AdaptiveChimaeronPlan const plan = Plan(mortality, HOLY);
    CHECK(plan.HealingDisabled && plan.PriorityHealTarget.IsEmpty());
    CHECK(plan.EncounterPhase == C::Phase::Mortality);
    CHECK(plan.DamageTarget == Boss(mortality).Guid);
    CHECK(!plan.Movement);
}

static void TestBurnWindow()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    Boss(board).HealthPct = 22.0f;
    Boss(board).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), board.ObservedAtMs, false, false };
    AdaptiveChimaeronPlan const hold = Plan(board, ROGUE);
    CHECK(hold.SuppressOffense && hold.SuppressReason == "burn_hold_before_mortality");
    CHECK(!Plan(board, MAGE).Action);   // no lust into a Massacre

    // Tanks keep attacking in the hold (threat, Death Strike).
    CHECK(!Plan(board, DK).SuppressOffense && !Plan(board, DRUID).SuppressOffense);

    Boss(board).Cast.reset();
    CHECK(!Plan(board, ROGUE).SuppressOffense);
    ObjectGuid target;
    CHECK(CastOf(Plan(board, MAGE), &target) == 80353 && target == G(MAGE));

    // Before any release a tank still low from the last Massacre keeps the
    // hold on (no memory: this revision decides).
    P(board, DRUID).HealthPct = 60.0f;
    CHECK(Plan(board, ROGUE).SuppressOffense);
    P(board, DRUID).HealthPct = 100.0f;

    // With memory the release is latched for the scope: a swing on a tank
    // mid-burn does not re-suppress damage while the lust runs.
    ChimaeronEncounterMemory rogueMemory;
    CHECK(!Plan(board, ROGUE, &rogueMemory).SuppressOffense && rogueMemory.BurnReleased);
    P(board, DRUID).HealthPct = 60.0f;
    Boss(board).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), board.ObservedAtMs, false, false };
    CHECK(!Plan(board, ROGUE, &rogueMemory).SuppressOffense);
    // A new scope (wipe, new attempt) starts unlatched.
    board.CurrentScope.WipeGeneration += 1;
    CHECK(Plan(board, ROGUE, &rogueMemory).SuppressOffense && !rogueMemory.BurnReleased);
    Boss(board).Cast.reset();
    P(board, DRUID).HealthPct = 100.0f;

    // A native Massacre timer inside the lead keeps the hold; a distant one does not.
    Boss(board).MechanicTimers.push_back({ C::MassacreSpell, 5000, false,
        FactSource::NativeInstanceState });
    CHECK(Plan(board, ROGUE).SuppressOffense);
    Boss(board).MechanicTimers.back().RemainingMs = 20000;
    CHECK(!Plan(board, ROGUE).SuppressOffense);

    // Sated/Temporal Displacement anywhere: no second lust.
    P(board, HUNTER).Auras.push_back({ 57724, ObjectGuid(), 1, 0 });
    CHECK(!Plan(board, MAGE).Action);

    // Outage inside the window holds; DoT creep past 20.3% no longer holds.
    Blackboard outage = Board("bwd.chimaeron.encounter", true);
    for (ActorSnapshot& player : outage.Players)
        player.Auras.clear();
    Boss(outage).HealthPct = 22.0f;
    CHECK(Plan(outage, ROGUE).SuppressOffense);
    Boss(outage).HealthPct = 20.2f;
    CHECK(!Plan(outage, ROGUE).SuppressOffense);

    // Mortality: lust if it was not used at the window.
    Blackboard mortality = Board("bwd.chimaeron.encounter", true);
    Boss(mortality).HealthPct = 19.0f;
    Boss(mortality).Auras.push_back({ C::MortalityBossSpell, Boss(mortality).Guid, 1, 0 });
    CHECK(CastOf(Plan(mortality, MAGE)) == 80353);
    CHECK(!Plan(mortality, ROGUE).SuppressOffense);
}

static void TestOutageCooldownsAndMortalityAbsorbs()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    for (ActorSnapshot& player : board.Players)
    {
        player.Auras.clear();
        player.Position = { HomeX, HomeY - 8.0f, HomeZ };
    }
    ActorSnapshot& boss = Boss(board);
    boss.Auras.push_back({ C::FeudSpell, boss.Guid, 1, board.ObservedAtMs + 15000 });
    CHECK(CastOf(Plan(board, DISC)) == 62618);
    CHECK(Plan(board, DISC).Action->Id.Mechanic == "outage_power_word_barrier");
    CHECK(!Plan(board, SHAMAN).Action);
    // Barrier already up: not recast.
    P(board, ROGUE).Auras.push_back({ 81782, G(DISC), 1, 0 });
    CHECK(!Plan(board, DISC).Action);
    boss.Auras[0].ExpiresAtMs = board.ObservedAtMs + 9000;
    CHECK(CastOf(Plan(board, SHAMAN)) == 98008);
    CHECK(!Plan(board, DISC).Action);
    // Away from the stack nobody drops a stack cooldown.
    P(board, SHAMAN).Position = { HomeX + 20.0f, HomeY - 8.0f, HomeZ };
    CHECK(!Plan(board, SHAMAN).Action);

    Blackboard mortality = Board("bwd.chimaeron.encounter", true);
    ActorSnapshot& enraged = Boss(mortality);
    enraged.HealthPct = 15.0f;
    enraged.VictimGuid = G(DRUID);
    enraged.Auras.push_back({ C::MortalityBossSpell, enraged.Guid, 1, 0 });
    P(mortality, DRUID).HealthPct = 50.0f;
    ChimaeronEncounterMemory discMemory;
    ObjectGuid target;
    // Shield first whenever Weakened Soul allows.
    CHECK(CastOf(Plan(mortality, DISC, &discMemory), &target) == 17 && target == G(DRUID));
    // Shield up: Pain Suppression on the failing tank.
    P(mortality, DRUID).Auras.push_back({ 17, G(DISC), 1, 0 });
    P(mortality, DRUID).Auras.push_back({ 6788, G(DISC), 1, 0 });
    CHECK(CastOf(Plan(mortality, DISC, &discMemory), &target) == 33206 && target == G(DRUID));
    // Pain Suppression observed once: never proposed again in this scope,
    // even after it expires (its cooldown is not on the blackboard).
    P(mortality, DRUID).Auras.push_back({ 33206, G(DISC), 1, 0 });
    CHECK(!Plan(mortality, DISC, &discMemory).Action && discMemory.PainSuppressionObserved);
    P(mortality, DRUID).Auras = { { 6788, G(DISC), 1, 0 } };
    CHECK(!Plan(mortality, DISC, &discMemory).Action);
    // Weakened Soul gone: the next shield.
    P(mortality, DRUID).Auras.clear();
    CHECK(CastOf(Plan(mortality, DISC, &discMemory)) == 17);
}

// The shape the arbitration replay (tests/test_bot_action_arbitration.py)
// exercises: a Feud outage with one protected tank under the floor, and the
// runtime role saying healer for a roster dps.
static void TestArbitrationReplayShape()
{
    Blackboard board;
    board.CurrentScope = Scope{ "arbiter", 1, 0, 1, "bwd.chimaeron.encounter", 669, 1, "x" };
    board.Revision = 7;
    board.ObservedAtMs = 9100;
    board.Route.NodeId = "bwd.chimaeron.encounter";
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, uint32(43296), uint32(92));
    boss.Entry = 43296;
    boss.Alive = true;
    boss.HealthPct = 70.0f;
    boss.Auras.push_back({ C::FeudSpell, ObjectGuid(), 1, 0 });
    board.Hostiles = { boss };
    ActorSnapshot floorTarget = Member(101, "tank", "fire_mage");
    floorTarget.Position = { -4.0f, 0.0f, 0.0f };
    floorTarget.Health = 9000;
    floorTarget.Auras.push_back({ C::FinklesMixtureSpell, ObjectGuid(), 1, 0 });
    ActorSnapshot tankB = Member(102, "tank", "fire_mage");
    tankB.Position = { 14.0f, 0.0f, 0.0f };
    ActorSnapshot conductor = Member(103, "dps", "fire_mage");
    conductor.Position = { 1.0f, 0.0f, 0.0f };
    board.Players = { floorTarget, tankB, conductor };
    AdaptiveChimaeronPlan const plan = AdaptiveChimaeronStrategy().Propose(board,
        conductor.Guid, "healer");
    CHECK(plan.OwnsNode);
    CHECK(plan.PriorityHealTarget == floorTarget.Guid);
    CHECK(plan.Movement.has_value());
}

static void TestOtherNodes()
{
    // Before the wake wait the route owns movement; the strategy only keeps
    // everyone off the sleeping boss.
    for (char const* node : { "bwd.chimaeron.regroup", "bwd.chimaeron.finkle" })
    {
        Blackboard asleep = Board(node, false);
        AdaptiveChimaeronPlan const plan = Plan(asleep, ROGUE);
        CHECK(plan.EncounterPhase == C::Phase::Prewake);
        CHECK(plan.SuppressOffense && !plan.Movement && !plan.OwnsNode && !plan.Action);
    }
    for (char const* node : { "bwd.chimaeron.regroup", "bwd.chimaeron.finkle", "bwd.magmaw.encounter" })
    {
        Blackboard board = Board(node, true);
        AdaptiveChimaeronPlan const plan = Plan(board, DK);
        CHECK(!plan.OwnsNode && !plan.Movement && !plan.Action && !plan.SuppressOffense);
        CHECK(plan.DamageTarget.IsEmpty());
    }
    Blackboard noBoss = Board("bwd.chimaeron.encounter", true);
    noBoss.Hostiles.clear();
    CHECK(!Plan(noBoss, DK).OwnsNode);
}

int main()
{
    TestDuties();
    TestPrewake();
    TestMixtureSpread();
    TestAlternativeRosterSpacing();
    TestOutageStack();
    TestTauntExchange();
    TestHealingFloor();
    TestBurnWindow();
    TestOutageCooldownsAndMortalityAbsorbs();
    TestArbitrationReplayShape();
    TestOtherNodes();
    if (failures)
        std::fprintf(stderr, "%d checks failed\n", failures);
    return failures ? 1 : 0;
}
'''


def _compile_and_run(tmp_path: Path, program: str) -> subprocess.CompletedProcess:
    source = tmp_path / "chimaeron_strategy.cpp"
    binary = tmp_path / "chimaeron_strategy"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)


def test_chimaeron_strategy_decisions_replay(tmp_path: Path) -> None:
    result = _compile_and_run(tmp_path, PROGRAM)
    assert result.returncode == 0, result.stderr


def test_strategy_headers_stay_small_and_self_contained() -> None:
    headers = sorted(CHIMAERON.glob("*.h"))
    assert {path.name for path in headers} >= {
        "BotAdaptiveChimaeronStrategy.h", "BotChimaeronFacts.h", "BotChimaeronDutyPlan.h",
        "BotChimaeronFormation.h", "BotChimaeronHealingPlan.h", "BotChimaeronTankSwap.h",
        "BotChimaeronSupportActions.h",
    }
    for path in headers:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) < 1000, path
        # Header-only replays cannot link ObjectGuid::Empty.
        assert "ObjectGuid::Empty" not in text, path
        # The strategy reads the blackboard only; it never reaches into the core.
        for forbidden in ('#include "Player.h"', '#include "Creature.h"', "ObjectAccessor"):
            assert forbidden not in text, (path, forbidden)


def _script_constant(name: str) -> int:
    match = re.search(rf"\b{name}\s*=\s*(\d+)", SCRIPT.read_text(encoding="utf-8"))
    assert match, name
    return int(match.group(1))


def _facts_constant(name: str) -> int:
    text = (CHIMAERON / "BotChimaeronFacts.h").read_text(encoding="utf-8")
    match = re.search(rf"constexpr uint(?:32|64) {name} = (\d+);", text)
    assert match, name
    return int(match.group(1))


def test_strategy_spell_identities_match_the_native_script() -> None:
    pairs = {
        "SPELL_MASSACRE": "MassacreSpell",
        "SPELL_BREAK": "BreakSpell",
        "SPELL_DOUBLE_ATTACK": "DoubleAttackSpell",
        "SPELL_FEUD": "FeudSpell",
        "SPELL_MORTALITY_1": "MortalityRaidSpell",
        "SPELL_MORTALITY_2": "MortalityBossSpell",
        "SPELL_FINKLES_MIXTURE": "FinklesMixtureSpell",
    }
    for script_name, facts_name in pairs.items():
        assert _script_constant(script_name) == _facts_constant(facts_name), script_name
    header = (ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/"
              "blackwing_descent.h").read_text(encoding="utf-8")
    assert re.search(r"NPC_BILE_O_TRON_800\s*=\s*44418", header)
    assert re.search(r"NPC_FINKLE_EINHORN\s*=\s*44202", header)
    assert _facts_constant("BossEntry") == 43296
    assert _facts_constant("BileOTronEntry") == 44418
    assert _facts_constant("FinkleEntry") == 44202
