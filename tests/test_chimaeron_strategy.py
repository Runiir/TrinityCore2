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
#include <algorithm>
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
    EncounterLatchView const* latches = nullptr)
{
    return AdaptiveChimaeronStrategy().Propose(board, G(guid), RoleOf(board, guid), latches);
}

// The cohort publisher: a new revision, then one latch update from it.
static void Publish(Blackboard& board, EncounterLatchStore& store, uint64 stepMs = 0)
{
    board.Revision += 1;
    board.ObservedAtMs += stepMs;
    store.BeginPublication(EncounterLatchScopeKey(board.CurrentScope.Key(),
        board.CurrentScope.ServerEpoch, board.CurrentScope.EncounterEpoch),
        board.Revision, board.ObservedAtMs);
    C::UpdateEncounterLatches(board, store);
}

static std::string MechanicOf(AdaptiveChimaeronPlan const& plan)
{
    return plan.Action ? plan.Action->Id.Mechanic : std::string();
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
    // Every melee count 0-5 (the rest ranged) keeps the spread guarantee.
    for (std::size_t meleeCount = 0; meleeCount <= 5; ++meleeCount)
    {
        Blackboard sweep = Board("bwd.chimaeron.encounter", true);
        std::size_t index = 0;
        for (uint32 guid : { HUNTER, MAGE, RET, ROGUE, LOCK })
            P(sweep, guid).ClassSpec = index++ < meleeCount ? "combat_rogue" : "fire_mage";
        std::map<uint32, C::Point> const slots = SpreadSlots(sweep);
        CHECK(slots.size() == 10);
        if (MinimumGap(slots) < C::MinimumSpreadSlotGap - 0.01f)
            std::fprintf(stderr, "melee %zu gap %.2f\n", meleeCount, MinimumGap(slots));
        CHECK(MinimumGap(slots) >= C::MinimumSpreadSlotGap - 0.01f);
    }

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
    EncounterLatchStore store;
    Boss(board).VictimGuid = G(DK);
    Boss(board).HealthPct = 21.0f;
    P(board, DK).HealthPct = P(board, DRUID).HealthPct = 100.0f;
    Boss(board).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), board.ObservedAtMs, false, false };
    Publish(board, store);
    CHECK(Plan(board, ROGUE, &store.View()).SuppressOffense);
    CHECK(!Plan(board, DRUID, &store.View()).Action);
    Boss(board).Auras = { { C::DoubleAttackSpell, boss, 1, 0 } };
    Publish(board, store);
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_double_attack_soak");
    Boss(board).VictimGuid = G(DRUID);
    Boss(board).Auras.clear();
    Publish(board, store);
    CHECK(MechanicOf(Plan(board, DK, &store.View())) == "taunt_back_break_holder");
    CHECK(!store.Find(C::BurnReleasedLatch));

    // The raid is ready: the release makes the Feral's handoff the first
    // action; the Break tank never takes the boss back.
    Boss(board).VictimGuid = G(DK);
    Boss(board).Cast.reset();
    Publish(board, store);
    CHECK(store.Find(C::BurnReleasedLatch) && !store.Find(C::HandoffDoneLatch));
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff");
    CHECK(!Plan(board, DK, &store.View()).Action);
    // Latched: a Massacre cast after the release does not cancel the handoff.
    Boss(board).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), board.ObservedAtMs, false, false };
    Publish(board, store);
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff");
    Boss(board).Cast.reset();
    Boss(board).VictimGuid = G(DRUID);
    Publish(board, store);
    CHECK(store.Find(C::HandoffDoneLatch));
    CHECK(!Plan(board, DK, &store.View()).Action && !Plan(board, DRUID, &store.View()).Action);
    // The Feral retakes the boss from anyone until Mortality.
    Boss(board).VictimGuid = G(DK);
    Publish(board, store);
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff");
    CHECK(!Plan(board, DK, &store.View()).Action);

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
    // Above the handoff line tanks keep attacking in the hold (threat, Death Strike).
    CHECK(!Plan(board, DK).SuppressOffense && !Plan(board, DRUID).SuppressOffense);

    // Ready (no view: this revision decides): released, handoff pending.
    // Non-tanks wait for the Feral's taunt; the Break tank stands down.
    Boss(board).Cast.reset();
    CHECK(Plan(board, ROGUE).SuppressOffense
        && Plan(board, ROGUE).SuppressReason == "burn_wait_for_mortality_handoff");
    CHECK(MechanicOf(Plan(board, DRUID)) == "taunt_mortality_handoff");
    CHECK(Plan(board, DK).SuppressOffense
        && Plan(board, DK).SuppressReason == "burn_break_tank_stand_down");
    CHECK(!Plan(board, MAGE).Action);
    // The Feral holds the boss: the push starts and the lust owner lusts.
    Boss(board).VictimGuid = G(DRUID);
    CHECK(!Plan(board, ROGUE).SuppressOffense && !Plan(board, DRUID).SuppressOffense);
    ObjectGuid target;
    CHECK(CastOf(Plan(board, MAGE), &target) == 80353 && target == G(MAGE));
    CHECK(Plan(board, DK).SuppressOffense);

    // Cohort latches: the release and handoff hold for the scope, so a swing
    // on a tank or a Massacre mid-burn does not re-suppress the push.
    EncounterLatchStore store;
    Boss(board).VictimGuid = G(DK);
    Publish(board, store);
    Boss(board).VictimGuid = G(DRUID);
    Publish(board, store);
    CHECK(store.Find(C::HandoffDoneLatch));
    P(board, DRUID).HealthPct = 60.0f;
    Boss(board).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), board.ObservedAtMs, false, false };
    Publish(board, store);
    CHECK(!Plan(board, ROGUE, &store.View()).SuppressOffense);
    // Every bot reads the same view: a stale revision is ignored.
    EncounterLatchView stale = store.View();
    stale.Revision -= 1;
    CHECK(Plan(board, ROGUE, &stale).SuppressOffense);
    // A new scope (wipe, new attempt, new native encounter epoch) starts over.
    board.CurrentScope.EncounterEpoch += 1;
    Publish(board, store);
    CHECK(!store.Find(C::BurnReleasedLatch) && Plan(board, ROGUE, &store.View()).SuppressOffense);
    // A disengaged boss (evade with survivors keeps the GUID) clears everything.
    Boss(board).Cast.reset();
    P(board, DRUID).HealthPct = 100.0f;
    Boss(board).VictimGuid = G(DK);
    Publish(board, store);
    CHECK(store.Find(C::BurnReleasedLatch));
    Boss(board).InCombat = false;
    Boss(board).VictimGuid.Clear();
    Publish(board, store);
    CHECK(store.View().Latches.empty() && store.View().Subject.IsEmpty());
    Boss(board).InCombat = true;
    Boss(board).VictimGuid = G(DK);

    // The handoff is bounded by one taunt cooldown: with the Feral's taunt
    // unavailable the non-tanks are released 8 s after the release.
    EncounterLatchStore timeout;
    Publish(board, timeout);
    uint64 const releasedAt = timeout.Find(C::BurnReleasedLatch)->SetAtMs;
    Publish(board, timeout, 7900);
    CHECK(!timeout.Find(C::HandoffDoneLatch) && Plan(board, ROGUE, &timeout.View()).SuppressOffense);
    Publish(board, timeout, 100);
    CHECK(board.ObservedAtMs == releasedAt + 8000);
    CHECK(timeout.Find(C::HandoffDoneLatch) && !Plan(board, ROGUE, &timeout.View()).SuppressOffense);

    // Held below the handoff line, the tanks are held too.
    Blackboard low = Board("bwd.chimaeron.encounter", true);
    Boss(low).HealthPct = 21.0f;
    Boss(low).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), low.ObservedAtMs, false, false };
    CHECK(Plan(low, DK).SuppressReason == "burn_hold_tanks_below_handoff");
    CHECK(Plan(low, DRUID).SuppressReason == "burn_hold_tanks_below_handoff");

    // A native Massacre timer inside the lead keeps the hold; a distant one does not.
    Blackboard timer = Board("bwd.chimaeron.encounter", true);
    Boss(timer).HealthPct = 22.0f;
    Boss(timer).VictimGuid = G(DRUID);
    Boss(timer).MechanicTimers.push_back({ C::MassacreSpell, 5000, false,
        FactSource::NativeInstanceState });
    CHECK(Plan(timer, ROGUE).SuppressReason == "burn_hold_before_mortality");
    Boss(timer).MechanicTimers.back().RemainingMs = 20000;
    CHECK(!Plan(timer, ROGUE).SuppressOffense);
    // Sated/Temporal Displacement anywhere: no second lust.
    P(timer, HUNTER).Auras.push_back({ 57724, ObjectGuid(), 1, 0 });
    CHECK(!Plan(timer, MAGE).Action);

    // An outage in the window holds, and damage over time past the old floor
    // no longer releases anything: only readiness and the handoff do.
    Blackboard outage = Board("bwd.chimaeron.encounter", true);
    for (ActorSnapshot& player : outage.Players)
        player.Auras.clear();
    Boss(outage).HealthPct = 22.0f;
    CHECK(Plan(outage, ROGUE).SuppressOffense);
    Boss(outage).HealthPct = 20.2f;
    CHECK(Plan(outage, ROGUE).SuppressOffense && Plan(outage, DK).SuppressOffense);

    // Mortality: lust if unused, nobody held but the Break tank standing
    // down behind a living Double Attack tank.
    Blackboard mortality = Board("bwd.chimaeron.encounter", true);
    Boss(mortality).HealthPct = 19.0f;
    Boss(mortality).Auras.push_back({ C::MortalityBossSpell, Boss(mortality).Guid, 1, 0 });
    CHECK(CastOf(Plan(mortality, MAGE)) == 80353);
    CHECK(!Plan(mortality, ROGUE).SuppressOffense && !Plan(mortality, DRUID).SuppressOffense);
    CHECK(Plan(mortality, DK).SuppressOffense);
    P(mortality, DRUID).Alive = false;
    CHECK(!Plan(mortality, DK).SuppressOffense);
}

// The generic cohort store: first set wins, scope and subject changes clear.
static void TestEncounterLatchStore()
{
    EncounterLatchStore store;
    store.BeginPublication("scope-a", 5, 1000);
    store.BindSubject(G(1));
    CHECK(store.Latch("boss.x", 7).SetAtMs == 1000);
    store.BeginPublication("scope-a", 6, 2000);
    CHECK(store.Latch("boss.x", 9).SetAtMs == 1000 && store.Find("boss.x")->Value == 7);
    CHECK(store.View().Revision == 6 && store.View().ObservedAtMs == 2000);
    store.Clear("boss.x");
    CHECK(!store.Find("boss.x"));
    store.Latch("boss.y");
    store.BindSubject(G(1));
    CHECK(store.Find("boss.y"));
    store.BindSubject(G(2));
    CHECK(!store.Find("boss.y") && store.View().Subject == G(2));
    store.Latch("boss.y");
    store.BeginPublication("scope-b", 7, 3000);
    CHECK(!store.Find("boss.y") && store.View().Subject.IsEmpty());
    CHECK(EncounterLatchScopeKey("k", 3, 4) == "k:3:4");
}

// Replay from the reviewer's case: a Massacre lands at 21.0% with the raid at
// 1 health. Every 250 ms the cohort publishes one latch update, all ten bots
// decide, healers heal their assignment, taunts land when the Feral's Growl is
// off cooldown, the boss swings every 4 s, and the boss loses 0.1% per step
// whenever anybody attacks (plus 0.02% damage over time). The adversarial walk
// drops 0.1% every step regardless.
struct ReplayResult
{
    bool MortalityReached = false;
    ObjectGuid VictimAtMortality;
    int Violations = 0;
};

static void Heal(ActorSnapshot& member, float pct)
{
    member.HealthPct = std::min(100.0f, member.HealthPct + pct);
    member.Health = uint64(member.HealthPct * float(member.MaxHealth) / 100.0f);
}

static ReplayResult RunBurnReplay(uint64 growlReadyAfterMs, bool adversarialWalk)
{
    ReplayResult result;
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    Boss(board).HealthPct = 21.0f;
    for (ActorSnapshot& player : board.Players)
    {
        player.Health = 1;
        player.HealthPct = 100.0f / 150000.0f;
    }
    EncounterLatchStore store;
    uint64 const start = board.ObservedAtMs;
    uint64 growlReadyAt = start + growlReadyAfterMs;
    uint64 nextSwingAt = start + 4000;
    auto violation = [&](char const* what, uint32 guid)
    {
        ++result.Violations;
        std::fprintf(stderr, "replay violation %s bot %u t=%llu hp=%.2f\n", what, guid,
            static_cast<unsigned long long>(board.ObservedAtMs - start), Boss(board).HealthPct);
    };
    for (int step = 0; step < 400; ++step)
    {
        Publish(board, store, 250);
        EncounterLatchView const& view = store.View();
        bool const released = view.Find(C::BurnReleasedLatch) != nullptr;
        bool const handedOff = view.Find(C::HandoffDoneLatch) != nullptr;
        std::map<uint32, AdaptiveChimaeronPlan> plans;
        for (uint32 guid : Everyone())
            plans[guid] = Plan(board, guid, &view);

        bool nonTankHeld = plans[ROGUE].SuppressOffense;
        for (auto const& [guid, plan] : plans)
        {
            bool const tank = guid == DK || guid == DRUID;
            std::string const mechanic = MechanicOf(plan);
            if (mechanic == "taunt_mortality_handoff" && !released)
                violation("handoff_before_release", guid);
            if (guid == DK && released && mechanic.rfind("taunt_", 0) == 0)
                violation("break_tank_taunt_after_release", guid);
            if (!tank && !plan.SuppressOffense && !handedOff)
                violation("non_tank_released_before_handoff", guid);
            if (!tank && plan.SuppressOffense != nonTankHeld)
                violation("non_tanks_disagree", guid);
            if (tank && !handedOff && Boss(board).HealthPct <= C::MortalityHandoffPct
                && !plan.SuppressOffense)
                violation("tank_attacks_below_handoff_line_while_held", guid);
        }

        // Healers heal their assignment, or the lowest tank below 90%.
        for (uint32 healer : { HOLY, DISC, SHAMAN })
        {
            ObjectGuid heal = plans[healer].PriorityHealTarget;
            if (heal.IsEmpty())
                for (uint32 tank : { DK, DRUID })
                    if (P(board, tank).HealthPct < 90.0f
                        && (heal.IsEmpty() || P(board, tank).HealthPct
                            < P(board, heal.GetCounter()).HealthPct))
                        heal = G(tank);
            if (!heal.IsEmpty())
                Heal(P(board, heal.GetCounter()), 20.0f);
        }
        if (CastOf(plans[DRUID]) == 6795 && board.ObservedAtMs >= growlReadyAt)
        {
            Boss(board).VictimGuid = G(DRUID);
            growlReadyAt = board.ObservedAtMs + 8000;
        }
        if (CastOf(plans[DK]) == 56222)
            Boss(board).VictimGuid = G(DK);
        if (board.ObservedAtMs >= nextSwingAt)
        {
            ActorSnapshot& victim = P(board, Boss(board).VictimGuid.GetCounter());
            victim.HealthPct = std::max(1.0f, victim.HealthPct - 25.0f);
            victim.Health = uint64(victim.HealthPct * float(victim.MaxHealth) / 100.0f);
            nextSwingAt += 4000;
        }
        bool attacking = false;
        for (uint32 guid : { DK, DRUID, HUNTER, MAGE, RET, ROGUE, LOCK })
            attacking = attacking || !plans[guid].SuppressOffense;
        float const drop = adversarialWalk ? 0.1f : (attacking ? 0.12f : 0.02f);
        Boss(board).HealthPct -= drop;
        if (Boss(board).HealthPct <= C::MortalityHealthPct)
        {
            result.MortalityReached = true;
            result.VictimAtMortality = Boss(board).VictimGuid;
            break;
        }
    }
    return result;
}

static void TestBurnReplayFromPostMassacre()
{
    for (uint64 growlReady : { 0ull, 3000ull, 6000ull })
    {
        ReplayResult const walk = RunBurnReplay(growlReady, false);
        CHECK(walk.Violations == 0);
        CHECK(walk.MortalityReached && walk.VictimAtMortality == G(DRUID));
    }
    // The adversarial walk (damage the hold cannot stop) may reach Mortality
    // first, but never breaks the sequence rules.
    for (uint64 growlReady : { 0ull, 6000ull })
    {
        ReplayResult const adversarial = RunBurnReplay(growlReady, true);
        CHECK(adversarial.Violations == 0 && adversarial.MortalityReached);
    }
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
    EncounterLatchStore latches;
    Publish(mortality, latches);
    ObjectGuid target;
    // Shield first whenever Weakened Soul allows.
    CHECK(CastOf(Plan(mortality, DISC, &latches.View()), &target) == 17 && target == G(DRUID));
    // Shield up: Pain Suppression on the failing tank.
    P(mortality, DRUID).Auras.push_back({ 17, G(DISC), 1, 0 });
    P(mortality, DRUID).Auras.push_back({ 6788, G(DISC), 1, 0 });
    Publish(mortality, latches);
    CHECK(CastOf(Plan(mortality, DISC, &latches.View()), &target) == 33206 && target == G(DRUID));
    // Pain Suppression observed: the cohort latch keeps it off for its 3 minute
    // cooldown even after the aura expires (the cooldown is not observable).
    P(mortality, DRUID).Auras.push_back({ 33206, G(DISC), 1, 0 });
    Publish(mortality, latches);
    CHECK(!Plan(mortality, DISC, &latches.View()).Action);
    P(mortality, DRUID).Auras = { { 6788, G(DISC), 1, 0 } };
    Publish(mortality, latches, 60000);
    CHECK(!Plan(mortality, DISC, &latches.View()).Action);
    // Weakened Soul gone: the next shield.
    P(mortality, DRUID).Auras.clear();
    Publish(mortality, latches);
    CHECK(CastOf(Plan(mortality, DISC, &latches.View())) == 17);
    // A cast older than its cooldown (for example in phase one) does not block
    // the Mortality one.
    P(mortality, DRUID).Auras = { { 17, G(DISC), 1, 0 }, { 6788, G(DISC), 1, 0 } };
    Publish(mortality, latches, 120000);
    CHECK(CastOf(Plan(mortality, DISC, &latches.View())) == 33206);
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
    TestEncounterLatchStore();
    TestBurnReplayFromPostMassacre();
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
