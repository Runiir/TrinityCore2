"""BWD 10N round 3 (Atramedes): the strategy keeps the user's kiter Sound bound.

User decision 2026-09-30 ("Bound kiter Sound"): in every air-phase Roaring Flame chase the tracked kiter
stays at 10 Sound or less (BotAtramedesSoundBound.h). The program reuses the strategy test's snapshot
helpers and native air-phase replay (tests/test_atramedes_strategy.py, cut at its harness sentinel) and
checks each rule with negative controls:
- the pre-liftoff reset (a ground strike in the last 4 s before the published liftoff while anyone is
  above 7 Sound), the chase Sound reset (the kiter above 7) and the Sound-bound contact (the next breath
  or fire patch tick would pass 10);
- the explicit shield budget (every Searing Flame interrupt still expected is kept; a forbidden strike
  logs a `*_at_reserve` reason);
- the mage's Ice Block gong strictly once per fight: readiness comes from its 300 s cooldown, and an
  attempt-scoped guard (BotAtramedesIceBlockGuard.h) keeps a fight that outlasts the cooldown from playing it
  a second time;
- the hazard-aware kite path and relay hold points (Sonar Bomb zones, fire patches).
The replay metric is the production chase counter (samples above 10) over every replayed air phase.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.test_atramedes_strategy import INCLUDES, PROGRAM, ROOT

HARNESS = PROGRAM[:PROGRAM.index("// ---- end of the air-phase replay harness ----")]

RULES = r'''
static std::string ReasonOf(Blackboard const& board)
{
    return std::string(A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board)).Reason);
}
static std::string WithheldOf(Blackboard const& board)
{
    return std::string(A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board)).Withheld);
}

// A chase: the mage kites at (110, -271) with the flame 30 yd behind (no
// contact soon), everyone else at the arena centre.
static Blackboard QuietChase(uint32 sound)
{
    Blackboard board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    AddFlame(board, Member(board, Mage), { 110.0f, -241.0f, 75.0f }, 0);
    Member(board, Mage).AlternatePower = sound;
    return board;
}

static void TestChaseSoundReset()
{
    assert(A::KiterSoundNoMargin == 7 && A::KiterSoundBound == 10);
    // Negative control: a kiter at low Sound far from the flame: no gong.
    for (uint32 sound : { 0u, 3u, 7u })
    {
        Blackboard board = QuietChase(sound);
        assert(A::FlameTimeToContact(board.Summons.back(), Member(board, Mage)) > 2.0f);
        assert(!A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board)).Required);
        assert(CountClicks(board) == 0);
    }
    // At 8 one breath tick would pass 10: strike at once, contact or not.
    Blackboard board = QuietChase(8);
    A::GongDecision const gong = A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board));
    assert(gong.Required && gong.Reason == "air_kiter_sound_reset");
    assert(CountClicks(board) == 1);
    // The kiter's own mobility lowers no Sound: the reset is not held back
    // for it, and the kiter named to strike strikes rather than casting.
    AddTimer(Member(board, Mage), M::BlinkSpell, 0);
    AddTimer(Member(board, Mage), M::IceBlockSpell, 0);
    assert(ReasonOf(board) == "air_kiter_sound_reset" && CountClicks(board) == 1);
    // An iced kiter is immune: nothing to reset.
    Member(board, Mage).Auras.push_back({ A::IceBlockAura, PlayerGuid(Mage), 0, board.ObservedAtMs + 10000 });
    assert(!A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board)).Required);
}

static void TestSoundBoundContact()
{
    // A fire patch under the kiter: 6 + 5 would pass 10.
    Blackboard board = QuietChase(6);
    Vector3 const at = Member(board, Mage).Position;
    board.Summons.push_back(MakeUnit(A::RoaringFlamePatchEntry, 700, at.X + 1.0f, at.Y, ActorKind::Summon));
    assert(A::NextSound(A::BuildFacts(board), Member(board, Mage), false) == 11);
    assert(ReasonOf(board) == "air_kiter_sound_bound");
    // Negative control: 5 + 5 is still 10.
    Member(board, Mage).AlternatePower = 5;
    assert(!A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board)).Required);
    // The next breath tick counts while the kiter is still inside the
    // breath, although the model expects it to escape (5 + 3 + 5 = 13).
    Blackboard inside = QuietChase(5);
    inside.Summons.pop_back();
    AddFlame(inside, Member(inside, Mage), { 110.0f, -266.5f, 75.0f }, 0);
    Vector3 const self = Member(inside, Mage).Position;
    inside.Summons.push_back(MakeUnit(A::RoaringFlamePatchEntry, 701, self.X, self.Y + 1.0f, ActorKind::Summon));
    assert(ReasonOf(inside) == "air_kiter_sound_bound");
}

static void TestShieldBudget()
{
    // Air at full health: the next ground phase's Searing Flame is kept.
    Blackboard board = QuietChase(8);
    KeepShields(board, 1);
    A::ShieldBudget const budget = A::BuildShieldBudget(A::BuildFacts(board));
    assert(budget.Available == 1 && budget.Reserve.Total() == 1 && !budget.AllowsAirStrike()
        && budget.AirStrikesLeft() == 0 && budget.AllowsEmergency() && budget.AllowsSearingFlame());
    assert(WithheldOf(board) == "air_kiter_sound_reset_at_reserve");
    assert(Plan(board, Hunter).GongReason == "air_kiter_sound_reset_at_reserve");
    assert(CountClicks(board) == 0);
    // The contact rule logs its own reason.
    Member(board, Mage).AlternatePower = 6;
    Vector3 const at = Member(board, Mage).Position;
    board.Summons.push_back(MakeUnit(A::RoaringFlamePatchEntry, 702, at.X, at.Y, ActorKind::Summon));
    assert(WithheldOf(board) == "air_kiter_sound_bound_at_reserve");
    // A boss that dies before the next Searing Flame needs no reserve.
    Boss(board).HealthPct = 25.0f;
    assert(A::BuildShieldBudget(A::BuildFacts(board)).AirStrikesLeft() == 1);
    // Nobody stands at the one shield left: the kiter runs for it.
    assert(ReasonOf(board) == "air_kiter_sound_bound" && Mechanic(Plan(board, Mage)) == "gong_approach");
}

static void TestIceBlockGongOncePerFight()
{
    // The Warlock is chased at 8 Sound; the mage (Ice Block ready) waits at
    // its relay station: the Sound reset is the mage's Ice Block play.
    Blackboard board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    AddTimer(Member(board, Mage), M::IceBlockSpell, 0);
    A::DutyPlan const duties = A::BuildDutyPlan(board);
    std::optional<A::ShieldFact> const station = A::AirRelayShieldFor(board, A::BuildFacts(board), duties,
        PlayerGuid(Mage));
    assert(station);
    Member(board, Mage).Position = A::AirStationPoint(*station);
    Member(board, Warlock).Position = { 110.0f, -271.0f, 75.0f };
    AddFlame(board, Member(board, Warlock), { 110.0f, -241.0f, 75.0f }, 0);
    Member(board, Warlock).AlternatePower = 8;
    A::GongDecision const ice = A::DecideGong(board, A::BuildFacts(board), duties);
    assert(ice.Required && ice.Reason == "air_ice_block_rescue" && ice.Clicker == PlayerGuid(Mage));
    // Once used (300 s cooldown, Hypothermia), a later Sound reset is an
    // ordinary strike: the play stays once per fight.
    Blackboard used = board;
    TimerOf(Member(used, Mage), M::IceBlockSpell)->RemainingMs = 290000;
    assert(ReasonOf(used) == "air_kiter_sound_reset");
    Blackboard cold = board;
    AddAura(Member(cold, Mage), A::HypothermiaAura, PlayerGuid(Mage));
    assert(ReasonOf(cold) == "air_kiter_sound_reset");
    // The pre-liftoff reset is a ground strike: never the Ice Block play.
    Blackboard ground = Board();
    AddTimer(Member(ground, Mage), M::IceBlockSpell, 0);
    AddTimer(Boss(ground), A::TakeOffSpell, 3000);
    Member(ground, Warlock).AlternatePower = 8;
    assert(ReasonOf(ground) == "pre_liftoff_sound_reset");
}

static void TestIceBlockStaysSpentPastTheCooldown()
{
    // Ice Block is strictly once per fight. Readiness alone (the published 300 s cooldown) would make a
    // mage ready again in a fight that outlasts it; the attempt-scoped guard records the block the fight
    // saw (BotAtramedesIceBlockGuard.h) and every play treats Ice Block as spent from then on.
    std::string const cohort = "blackwing_descent_10n_atramedes_c0";
    A::ObservationAttempt const attempt{ 1, 3 };  // the boards' scope: attempt 3
    A::IceBlockGuard guard;
    auto factsOf = [&guard](Blackboard const& board)
    {
        A::Facts facts = A::BuildFacts(board);
        facts.IceBlockSpent = guard.Spent(board.CurrentScope.CohortId, board.CurrentScope.AttemptId);
        return facts;
    };
    auto planOf = [&guard](Blackboard const& board, uint32 slot)
    {
        return AdaptiveAtramedesStrategy().Propose(board, PlayerGuid(slot), "dps", &guard);
    };
    auto iced = [](Blackboard board)
    {
        Member(board, Mage).Auras.push_back({ A::IceBlockAura, PlayerGuid(Mage), 0, board.ObservedAtMs + 10000 });
        return board;
    };

    // The rescue strike: the Warlock is chased at 8 Sound, the mage (Ice Block ready) waits at its relay.
    Blackboard board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    AddTimer(Member(board, Mage), M::IceBlockSpell, 0);
    A::DutyPlan const duties = A::BuildDutyPlan(board);
    std::optional<A::ShieldFact> const station = A::AirRelayShieldFor(board, A::BuildFacts(board), duties,
        PlayerGuid(Mage));
    assert(station);
    Member(board, Mage).Position = A::AirStationPoint(*station);
    Member(board, Warlock).Position = { 110.0f, -271.0f, 75.0f };
    AddFlame(board, Member(board, Warlock), { 110.0f, -241.0f, 75.0f }, 0);
    Member(board, Warlock).AlternatePower = 8;
    assert(!guard.Spent(cohort, 3));
    A::GongDecision const first = A::DecideGong(board, factsOf(board), duties);
    assert(first.Required && first.Reason == "air_ice_block_rescue" && first.Clicker == PlayerGuid(Mage));
    AdaptiveAtramedesPlan const firstPlan = planOf(board, Mage);
    BotNativeAction::SpellClick const* strike = ClickOf(firstPlan);
    assert(strike && strike->Target == first.Shield->Guid);

    // The fight plays the block: the mage is seen under Ice Block while Atramedes is engaged.
    guard.Observe(cohort, attempt, iced(board));
    assert(guard.Spent(cohort, 3));
    // The fight outlasts the cooldown (300 s later): Ice Block is ready again, no Hypothermia, no aura. The
    // readiness alone still says ready (the bug), and the guard keeps the play from starting a second time.
    Blackboard later = board;
    TimerOf(Member(later, Mage), M::IceBlockSpell)->RemainingMs = 0;
    assert(A::IceBlockAvailable(Member(later, Mage)) && A::IceBlockReady(Member(later, Mage)));
    assert(!A::IceBlockUsable(factsOf(later), Member(later, Mage)) && !A::IceBlockCastable(factsOf(later), Member(later, Mage)));
    A::GongDecision const second = A::DecideGong(later, factsOf(later), duties);
    assert(second.Required && second.Reason == "air_kiter_sound_reset" && second.Reason != "air_ice_block_rescue");
    assert(!A::IceMage(later, factsOf(later), duties) && A::IceMage(later, A::BuildFacts(later), duties));
    // Negative controls: no guard (nullptr) plays it, as does a fresh guard.
    AdaptiveAtramedesPlan const unguardedPlan = AdaptiveAtramedesStrategy().Propose(later,
        PlayerGuid(Mage), "dps", nullptr);
    BotNativeAction::SpellClick const* unguarded = ClickOf(unguardedPlan);
    assert(unguarded && unguarded->Target == first.Shield->Guid);
    A::IceBlockGuard fresh;
    A::Facts freshFacts = A::BuildFacts(later);
    freshFacts.IceBlockSpent = fresh.Spent(cohort, 3);
    assert(A::DecideGong(later, freshFacts, duties).Reason == "air_ice_block_rescue");

    // The baiting mage (newest striker, flame on its way) stops baiting; the bait's block is not cast.
    Blackboard bait = AirBoard();
    AddTimer(Member(bait, Mage), M::IceBlockSpell, 0);
    bait.Summons.push_back(MakeUnit(A::ReverberatingFlameEntry, 81, 120.0f, -240.0f, ActorKind::Summon));
    Member(bait, Mage).Auras.push_back({ A::AirClashAura, station->Guid, 0, bait.ObservedAtMs + 15000 });
    assert(A::IceBaiting(bait, A::BuildFacts(bait), Member(bait, Mage)));
    assert(!A::IceBaiting(bait, factsOf(bait), Member(bait, Mage)));

    // The chased mage itself: blocks in the first play, takes no second block.
    Blackboard chased = AirBoard();
    for (ActorSnapshot& player : chased.Players)
        player.Position = A::ArenaCenter;
    Member(chased, Mage).Position = { 110.0f, -271.0f, 75.0f };
    AddTimer(Member(chased, Mage), M::IceBlockSpell, 0);
    AddTimer(Member(chased, Mage), M::BlinkSpell, 0);
    AddFlame(chased, Member(chased, Mage), { 107.0f, -271.0f, 75.0f }, 0);
    A::Facts const freshChase = A::BuildFacts(chased);
    assert(A::DecideGong(chased, freshChase, A::BuildDutyPlan(chased)).Withheld == "kiter_ice_block");
    AdaptiveAtramedesPlan const freshBlock = AdaptiveAtramedesStrategy().Propose(chased, PlayerGuid(Mage), "dps", &fresh);
    assert(CastOf(freshBlock) && CastOf(freshBlock)->SpellId == M::IceBlockSpell);
    assert(A::DecideGong(chased, factsOf(chased), A::BuildDutyPlan(chased)).Withheld != "kiter_ice_block");
    AdaptiveAtramedesPlan const secondBlock = planOf(chased, Mage);
    assert(!CastOf(secondBlock) || CastOf(secondBlock)->SpellId != M::IceBlockSpell);

    // Scope. Another attempt and another cohort start unspent.
    assert(!guard.Spent(cohort, 4) && !guard.Spent("other_cohort", 3) && !guard.Spent(cohort, 0));
    Blackboard nextAttempt = iced(board);
    nextAttempt.CurrentScope.AttemptId = 4;
    guard.Observe(cohort, A::ObservationAttempt{ 1, 4 }, nextAttempt);
    assert(guard.Spent(cohort, 4) && !guard.Spent(cohort, 3));  // attempt 4's own record replaced attempt 3's
    // A restart that keeps the attempt id (a new start lifecycle, `.botexp start` on an active cohort) is the
    // same fight: Atramedes stays engaged, the memory stays (v4 review;
    // tests/test_atramedes_ice_block_guard_lifecycle.py replays the rest). Only the fight ending clears it.
    A::IceBlockGuard lifecycle;
    lifecycle.Observe(cohort, attempt, iced(board));
    assert(lifecycle.Spent(cohort, 3));
    lifecycle.Observe(cohort, A::ObservationAttempt{ 2, 3 }, board);
    assert(lifecycle.Spent(cohort, 3));
    Blackboard restartedWipe = board;
    Boss(restartedWipe).InCombat = false;
    lifecycle.Observe(cohort, A::ObservationAttempt{ 2, 3 }, restartedWipe);
    assert(!lifecycle.Spent(cohort, 3));
    // A snapshot of another cohort or attempt, or off the encounter node, is never observed.
    A::IceBlockGuard strict;
    Blackboard foreign = iced(board);
    foreign.CurrentScope.CohortId = "foreign";
    strict.Observe(cohort, attempt, foreign);
    Blackboard stale = iced(board);
    stale.CurrentScope.AttemptId = 2;
    strict.Observe(cohort, attempt, stale);
    Blackboard elsewhere = iced(board);
    elsewhere.Route.NodeId = "bwd.nefarian.encounter";
    strict.Observe(cohort, attempt, elsewhere);
    strict.Observe(cohort, A::ObservationAttempt{ 1, 0 }, iced(board));
    assert(!strict.Spent(cohort, 3) && !strict.Spent("foreign", 3) && !strict.Spent(cohort, 2));
    // Evidence only while Atramedes is engaged: a block on trash before the pull is another fight's; a dead
    // or missing Atramedes neither spends nor clears; the respawned boss out of combat (a wipe) clears.
    Blackboard prePull = iced(board);
    Boss(prePull).InCombat = false;
    strict.Observe(cohort, attempt, prePull);
    assert(!strict.Spent(cohort, 3));
    strict.Observe(cohort, attempt, iced(board));
    assert(strict.Spent(cohort, 3));
    Blackboard gone = iced(board);
    gone.Summons.clear();
    strict.Observe(cohort, attempt, gone);
    assert(strict.Spent(cohort, 3));
    strict.Observe(cohort, attempt, prePull);
    assert(!strict.Spent(cohort, 3));
    // A dead mage under no aura, and Hypothermia alone (a block before the pull), are no evidence.
    Blackboard dead = iced(board);
    Member(dead, Mage).Alive = false;
    strict.Observe(cohort, attempt, dead);
    Blackboard cold = board;
    AddAura(Member(cold, Mage), A::HypothermiaAura, PlayerGuid(Mage));
    strict.Observe(cohort, attempt, cold);
    assert(!strict.Spent(cohort, 3));
}

static void TestDuePreLiftoffResetOutranksARefusedElectiveGong()
{
    // One second before liftoff, a player at 85 Sound, this phase's Searing Flame spent and two shields
    // left; the next phase's interrupt is kept (full health). The elective budget (one spare on top of
    // every interrupt) refuses the 80-Sound gong, but the air strike budget allows the pre-liftoff reset:
    // the chase would start above the Sound bound with a spendable shield in hand.
    Blackboard board = Board();
    AddTimer(Boss(board), A::TakeOffSpell, 1000);
    Member(board, Warlock).AlternatePower = 85;
    KeepShields(board, 2);
    A::Facts const facts = A::BuildFacts(board);
    A::ShieldBudget const budget = A::BuildShieldBudget(facts);
    assert(budget.Available == 2 && budget.Reserve.CurrentPhase == 0 && budget.Reserve.NextPhase == 1);
    assert(!budget.AllowsElective() && budget.AllowsAirStrike());
    assert(A::PreLiftoffSoundResetDue(facts) && facts.MaxSound >= A::SoundHigh);
    A::GongDecision const gong = A::DecideGong(board, facts, A::BuildDutyPlan(board));
    assert(gong.Required && gong.Urgent && gong.Reason == "pre_liftoff_sound_reset");
    assert(gong.Withheld.empty() && !gong.Clicker.IsEmpty() && gong.Shield);
    assert(CountClicks(board) == 1);
    assert(Plan(board, Hunter).GongReason == "pre_liftoff_sound_reset");
    // Negative controls. The liftoff 6 s away: the reset is not due, the elective refusal stands.
    Blackboard early = board;
    Boss(early).MechanicTimers.back().RemainingMs = 6000;
    assert(!A::DecideGong(early, A::BuildFacts(early), A::BuildDutyPlan(early)).Required);
    assert(WithheldOf(early) == "sound_high_at_reserve" && CountClicks(early) == 0);
    // One shield less: the air strike budget refuses too, and the high-Sound refusal is what is logged.
    Blackboard last = board;
    KeepShields(last, 1);
    assert(!A::BuildShieldBudget(A::BuildFacts(last)).AllowsAirStrike());
    assert(WithheldOf(last) == "sound_high_at_reserve" && CountClicks(last) == 0);
    // A spare shield: the elective gong is allowed as before (it is the ordinary high-Sound gong).
    Blackboard spare = Board();
    AddTimer(Boss(spare), A::TakeOffSpell, 1000);
    Member(spare, Warlock).AlternatePower = 85;
    KeepShields(spare, 3);
    assert(A::BuildShieldBudget(A::BuildFacts(spare)).AllowsElective());
    assert(ReasonOf(spare) == "sound_high");
}

static void TestPreLiftoffReset()
{
    // Published schedule, this phase's Searing Flame spent, 3 s to liftoff.
    Blackboard board = Board();
    AddTimer(Boss(board), A::TakeOffSpell, 3000);
    Member(board, Warlock).AlternatePower = 8;
    assert(A::BuildFacts(board).LiftoffInMs == 3000u);
    A::GongDecision const reset = A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board));
    assert(reset.Required && reset.Reason == "pre_liftoff_sound_reset");
    // Whoever stands nearest a shield strikes the nearest one: the owner at
    // its duty shield here.
    assert(reset.Clicker == PlayerGuid(Hunter) && reset.Shield);
    assert(G::Distance3d(Member(board, Hunter).Position, reset.Shield->Position) <= A::ShieldClickDistance);
    assert(CountClicks(board) == 1);
    // The tank counts too: the air flame may take it.
    Member(board, Warlock).AlternatePower = 0;
    Member(board, Tank).AlternatePower = 9;
    assert(ReasonOf(board) == "pre_liftoff_sound_reset");
    // Negative controls: everyone at 7 or less; the liftoff 6 s away; no
    // published schedule.
    Member(board, Tank).AlternatePower = 7;
    assert(!A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board)).Required && CountClicks(board) == 0);
    Member(board, Tank).AlternatePower = 9;
    Boss(board).MechanicTimers.back().RemainingMs = 6000;
    assert(CountClicks(board) == 0);
    Blackboard unpublished = Board();
    Member(unpublished, Tank).AlternatePower = 9;
    assert(CountClicks(unpublished) == 0);
    // The reserve: the last shield is the next ground phase's Searing Flame.
    Boss(board).MechanicTimers.back().RemainingMs = 3000;
    KeepShields(board, 1);
    assert(WithheldOf(board) == "pre_liftoff_sound_reset_at_reserve" && CountClicks(board) == 0);
    KeepShields(board, 0);
    board = Board();
    AddTimer(Boss(board), A::TakeOffSpell, 3000);
    Member(board, Tank).AlternatePower = 9;
    KeepShields(board, 2);
    assert(ReasonOf(board) == "pre_liftoff_sound_reset");
}

static void TestKitePathAvoidsHazards()
{
    Blackboard board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    ActorSnapshot& kiter = Member(board, Mage);
    kiter.Position = { 110.0f, -250.0f, 75.0f };
    AddFlame(board, kiter, { 95.0f, -225.0f, 75.0f }, 0);
    A::Facts facts = A::BuildFacts(board);
    int const direction = A::AirKiteDirection(facts, Member(board, Mage));
    std::optional<Vector3> const next = A::NextRingWaypoint(Member(board, Mage).Position, direction);
    assert(next);
    // Negative control: no hazard, the kite is the ring waypoint.
    std::optional<Vector3> const plain = A::KitePath::ChooseWaypoint(facts, Member(board, Mage),
        A::KiterFlame(facts, Member(board, Mage)), direction);
    assert(plain && G::Distance2d(*plain, *next) < 0.01f);
    // A Sonar Bomb marker on that run: another ring waypoint, clear of it,
    // and the kite still moves away from the flame.
    Vector3 const self = Member(board, Mage).Position;
    board.Summons.push_back(MakeUnit(A::SonarBombMarkerEntry, 710, (self.X + next->X) / 2.0f,
        (self.Y + next->Y) / 2.0f, ActorKind::Summon));
    facts = A::BuildFacts(board);
    ActorSnapshot const* flame = A::KiterFlame(facts, Member(board, Mage));
    std::optional<Vector3> const around = A::KitePath::ChooseWaypoint(facts, Member(board, Mage), flame, direction);
    assert(around && G::Distance2d(*around, *next) > 1.0f);
    assert(A::KitePath::HazardSound(facts, Member(board, Mage), *around)
        < A::KitePath::HazardSound(facts, Member(board, Mage), *next));
    assert(A::KitePath::BreathSound(Member(board, Mage), flame, *around) == 0.0f);
    AdaptiveAtramedesPlan const plan = Plan(board, Mage);
    assert(Mechanic(plan) == "roaring_flame_breath_kite");
    assert(G::Distance2d({ MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f }, *around) < 0.01f);
    // A run that only a waypoint into the flame could avoid keeps the breath
    // term: bomb avoidance never hands the kiter to the flame.
    ActorSnapshot close = Member(board, Mage);
    ActorSnapshot fast = *flame;
    fast.Position = { self.X - 1.0f, self.Y + 5.0f, 75.0f };
    assert(A::KitePath::BreathSound(close, &fast, { self.X - 20.0f, self.Y + 20.0f, 75.0f }) > 0.0f);
}

static void TestRelayHoldsInReachOffHazards()
{
    Blackboard board = AirBoard();
    A::Facts facts = A::BuildFacts(board);
    std::vector<A::ShieldFact> const relays = A::RelayShields(facts);
    A::ShieldFact const shield = relays.front();
    Vector3 const station = A::AirStationPoint(shield);
    // Negative control: a clear station is the station.
    assert(G::Distance2d(A::AirStationFor(facts, shield), station) < 0.01f);
    // The redirected flame's trail across it: a clear point in reach.
    board.Summons.push_back(MakeUnit(A::RoaringFlamePatchEntry, 720, station.X, station.Y, ActorKind::Summon));
    facts = A::BuildFacts(board);
    Vector3 const moved = A::AirStationFor(facts, shield);
    assert(G::Distance2d(moved, station) > 1.0f && A::StationHazardFree(facts, moved)
        && A::StationInReach(moved, shield));
    // The owner standing in the fire takes the shortest safe step that keeps
    // its shield in click reach (BotAtramedesDodge.h), not a step away from
    // its shield: no longer than the walk to the moved station.
    Member(board, Hunter).Position = station;
    AdaptiveAtramedesPlan const plan = Plan(board, Hunter);
    assert(Mechanic(plan) == "air_relay_hazard_step");
    Vector3 const to{ MoveOf(plan)->X, MoveOf(plan)->Y, MoveOf(plan)->Z };
    assert(A::StationHazardFree(facts, to) && G::Distance3d(to, shield.Position) <= A::ShieldClickDistance);
    assert(G::Distance2d(to, station) <= G::Distance2d(moved, station) + 0.01f);
    // The Ice Block bait steps out of a bomb zone instead of holding in it.
    Blackboard bait = AirBoard();
    AddTimer(Member(bait, Mage), M::IceBlockSpell, 0);
    bait.Summons.push_back(MakeUnit(A::ReverberatingFlameEntry, 81, 120.0f, -240.0f, ActorKind::Summon));
    Member(bait, Mage).Auras.push_back({ A::AirClashAura, shield.Guid, 0, bait.ObservedAtMs + 15000 });
    Vector3 const mage = Member(bait, Mage).Position;
    assert(!Plan(bait, Mage).Movement);
    bait.Summons.push_back(MakeUnit(A::SonarBombMarkerEntry, 721, mage.X + 1.0f, mage.Y, ActorKind::Summon));
    AdaptiveAtramedesPlan const step = Plan(bait, Mage);
    assert(Mechanic(step) == "sonar_bomb_exit" && !step.Interaction);
}
'''

REPLAY = r'''
static std::vector<std::pair<uint32, uint32>> GroundCarry(uint32 target)
{
    // The second Sonic Breath's kiter kept one tick (+20), two others two
    // Sonar Pulse disk ticks (+6); the air flame's random first target is the
    // loud one.
    uint32 const a = Tank + (target - Tank + 3) % 10;
    uint32 const b = Tank + (target - Tank + 6) % 10;
    return { { target, 20 }, { a, 6 }, { b, 6 } };
}

struct Tally { int Runs = 0; int Over = 0; uint32 Worst = 0; int Ground = 0; };
static std::map<std::string, Tally> tallies;
static void Note(std::string const& kind, AirReplay const& run)
{
    Tally& tally = tallies[kind];
    ++tally.Runs;
    tally.Over += run.MaxKiterSound > A::KiterSoundBound;
    tally.Worst = std::max(tally.Worst, run.MaxKiterSound);
    tally.Ground += run.GroundStrikes;
    assert(run.Chases >= 1 && !run.DoubleClick);
}

int main()
{
    TestChaseSoundReset();
    TestSoundBoundContact();
    TestShieldBudget();
    TestIceBlockGongOncePerFight();
    TestIceBlockStaysSpentPastTheCooldown();
    TestDuePreLiftoffResetOutranksARefusedElectiveGong();
    TestPreLiftoffReset();
    TestKitePathAvoidsHazards();
    TestRelayHoldsInReachOffHazards();
    std::puts("kiter sound rules ok");

    std::vector<uint32> const beforePhase1 = AfterGroundSearing(AllShieldIds(), 100.0f);
    std::vector<uint32> const farthest{ 250123, 250127, 250131 };
    for (float cap : { float(A::BuildingSpeedMaxStacks), 99.0f })
        for (float delay : { 7.0f, 3.0f })
            for (uint32 slot = Tank; slot <= Warlock; ++slot)
            {
                AirReplay const first = ReplayAirPhase(slot, cap, delay, false, beforePhase1);
                Note("canonical phase1", first);
                Note("canonical phase2", ReplayAirPhase(slot, cap, delay, false,
                    AfterGroundSearing(first.ShieldsLeft, 60.0f), 60.0f));
                Note("canonical phase3", ReplayAirPhase(slot, cap, delay, false, farthest, 25.0f));
            }
    int iceUses = 0;
    for (int scenario = 0; scenario < 3; ++scenario)
        for (uint32 seed : { 1u, 2u, 3u })
        {
            if (scenario < 2 && seed > 1)
                continue;
            for (int variant = 0; variant < 3; ++variant)
                for (float delay : { 7.0f, 3.0f })
                    for (uint32 slot = Tank; slot <= Warlock; ++slot)
                    {
                        ReplayOptions options;
                        options.Mobility = true;
                        options.IceBlockReady = variant == 0;
                        options.NoMage = variant == 2;
                        options.DashRemainingMs = variant == 1 ? 56000 : 0;
                        options.Bombs = options.FirePatches = scenario == 2;
                        options.Seed = seed;
                        if (options.NoMage && slot == Mage)
                            continue;
                        if (scenario == 1)
                            options.GroundSound = GroundCarry(slot);
                        AirReplay const one = ReplayAirPhase(slot, float(A::BuildingSpeedMaxStacks), delay,
                            false, beforePhase1, 100.0f, 31.0f, options);
                        ReplayOptions later = options;
                        later.IceBlockReady = false;
                        later.DashRemainingMs = 56000;
                        later.Seed = seed + 17;
                        AirReplay const two = ReplayAirPhase(slot, float(A::BuildingSpeedMaxStacks), delay,
                            false, AfterGroundSearing(one.ShieldsLeft, 60.0f), 60.0f, 31.0f, later);
                        // The mage's Ice Block play: at most once over both phases.
                        assert(one.IceStrikes + one.IceBlocks <= 2 && two.IceStrikes == 0 && two.IceBlocks == 0);
                        assert(one.IceStrikes <= 1 && one.IceBlocks <= 1);
                        iceUses += one.IceBlocks;
                        char const* name = scenario == 0 ? "mobility" : scenario == 1 ? "ground" : "hazards";
                        char key[48];
                        std::snprintf(key, sizeof(key), "%s spawn%.0f first", name, delay);
                        Note(key, one);
                        std::snprintf(key, sizeof(key), "%s spawn%.0f next", name, delay);
                        Note(key, two);
                        if (scenario == 1)
                        {
                            // The loud player is reset before the flame spawns.
                            assert(one.GroundStrikes == 1 && one.GroundReasons.front() == "pre_liftoff_sound_reset");
                            assert(one.FirstChaseSound >= 0 && one.FirstChaseSound <= int(A::KiterSoundNoMargin));
                        }
                    }
        }
    assert(iceUses >= 15);
    // A reserve that forbids the pre-liftoff reset logs why: two shields at
    // full health keep this phase's and the next phase's Searing Flame.
    {
        ReplayOptions options;
        options.GroundSound = { { Balance, 20 } };
        AirReplay const held = ReplayAirPhase(Balance, float(A::BuildingSpeedMaxStacks), 7.0f, false,
            { 250131 }, 100.0f, 31.0f, options);
        assert(held.GroundStrikes == 0);
        assert(std::find(held.Withheld.begin(), held.Withheld.end(), "pre_liftoff_sound_reset_at_reserve")
            != held.Withheld.end());
        assert(held.MaxKiterSound > A::KiterSoundBound);  // the bound fails only with the reason logged
        std::printf("withheld reserve run: max_kiter_sound=%u withheld=%s\n", held.MaxKiterSound,
            held.Withheld.front().c_str());
    }
    for (auto const& [kind, tally] : tallies)
        std::printf("kiter sound %-22s runs=%3d over10=%3d worst=%3u pre_liftoff_resets=%d\n", kind.c_str(),
            tally.Runs, tally.Over, tally.Worst, tally.Ground);
    // Shields available and the native spawn (the flame about 4 s after the
    // liftoff; the replay's 7 s): no phase above the bound.
    for (char const* kind : { "canonical phase1", "canonical phase2", "canonical phase3", "mobility spawn7 first",
             "mobility spawn7 next", "ground spawn7 first", "ground spawn7 next", "mobility spawn3 first",
             "ground spawn3 first", "mobility spawn3 next" })
        assert(tallies[kind].Over == 0);
    // Ratchets for the stress cases (3 s spawn, bombs and fire). Before the
    // bound strategy: 1/29, 16/29 and 55-57 of 87. With it (round 3
    // atramedes_strategy): 1, 16, 14 and 16, 6 and 19. With every bot dodging
    // every hazard (round 3 atramedes_dodge, BotAtramedesDodge.h): 0, 13,
    // 10 and 3, 5 and 16 (over twelve seeds 38/48/44/18 of 348 against
    // 41/59/60/53 before). Round 4 (every bot leaves a Sonar Bomb zone by
    // the fastest escape, BotAtramedesDodge.h BombEscape): 9 and 5, 3 and
    // 15, 32 against 34 in all; over twelve seeds 35/51/45/22 (153 of 1392)
    // against 148, inside the replay's noise (the same headers with one
    // constant nudged by 0.01 give 150): each kind keeps two phases of
    // slack, the total stays at or below round 3's.
    assert(tallies["ground spawn3 next"].Over <= 13);
    assert(tallies["hazards spawn7 first"].Over <= 10 && tallies["hazards spawn7 next"].Over <= 5);
    assert(tallies["hazards spawn3 first"].Over <= 5 && tallies["hazards spawn3 next"].Over <= 16);
    assert(tallies["hazards spawn7 first"].Over + tallies["hazards spawn7 next"].Over
        + tallies["hazards spawn3 first"].Over + tallies["hazards spawn3 next"].Over <= 34);
    std::puts("kiter sound replay ok");
    return 0;
}
'''


def test_atramedes_kiter_sound_bound_rules_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "kiter_sound.cpp"
    binary = tmp_path / "kiter_sound"
    source.write_text(HARNESS + "#include <cstring>\n" + RULES + REPLAY, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-O1",
                    *INCLUDES, str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    print(result.stdout)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert "kiter sound rules ok" in result.stdout and "kiter sound replay ok" in result.stdout


def test_sound_bound_rules_are_wired_and_bounded() -> None:
    folder = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes"
    bound = (folder / "BotAtramedesSoundBound.h").read_text(encoding="utf-8")
    assert "KiterSoundNoMargin = KiterSoundBound - BreathTickSound" in bound
    gong = (folder / "BotAtramedesGongPolicy.h").read_text(encoding="utf-8")
    assert "struct ShieldBudget" in gong and "pre_liftoff_sound_reset_at_reserve" in gong
    air = (folder / "BotAtramedesAirGong.h").read_text(encoding="utf-8")
    assert "SoundBoundGong(facts, *kiter" in air and "SoundBoundWithheld(bound)" in air
    movement = (folder / "BotAtramedesMovementPolicy.h").read_text(encoding="utf-8")
    assert movement.count("KitePath::ChooseWaypoint") == 2
    for name in ("BotAtramedesSoundBound.h", "BotAtramedesKitePath.h", "BotAtramedesIceBlockGuard.h"):
        assert len((folder / name).read_text(encoding="utf-8").splitlines()) < 1000


def test_ice_block_once_per_fight_guard_is_wired() -> None:
    """The plays read the guard-aware readiness; the adapter feeds the guard and the strategy reads it."""
    folder = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes"
    for name in ("BotAtramedesAirGong.h", "BotAtramedesAirActions.h"):
        text = (folder / name).read_text(encoding="utf-8")
        assert "IceBlockAvailable(" not in text and "IceBlockReady(" not in text, name
    ice = (folder / "BotAtramedesIceBlock.h").read_text(encoding="utf-8")
    assert "return !facts.IceBlockSpent && IceBlockAvailable(actor);" in ice
    assert "return !facts.IceBlockSpent && IceBlockReady(actor);" in ice
    strategy = (folder / "BotAdaptiveAtramedesStrategy.h").read_text(encoding="utf-8")
    assert "facts.IceBlockSpent = iceBlockGuard" in strategy
    adapter = (folder / "BotWorldPopulationMgrAtramedesCandidates.cpp").read_text(encoding="utf-8")
    assert "ProcessIceBlockGuard().Observe(Cohort().Id," in adapter
    guard = (folder / "BotAtramedesIceBlockGuard.h").read_text(encoding="utf-8")
    assert "ObservationAttempt" in guard and "board.Route.NodeId != EncounterNode" in guard
