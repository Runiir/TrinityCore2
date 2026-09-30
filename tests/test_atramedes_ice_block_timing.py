"""BWD 10N round 3 fix (Atramedes): the chased mage relies on its Ice Block only when it beats the breath.

Reviewer finding (BotAtramedesAirGong.h, DecideAirGong): `bound.empty() && contact && IceBlockUsable(...)`
withheld the gong rescue whenever at most a global cooldown was left on the mage's Ice Block, whatever the
time to contact. Reproduction: canonical positions, six Building Speed stacks, Sound 0, Ice Block unused, no
Blink ready, 1,200 ms left on the Ice Block timer, contact in 0.911 s. The result was Required=false,
Withheld=kiter_ice_block: no block cast (it is not castable for another 1.2 s) and no gong, while the breath
ticks hit for 15.6-16.4k every 500 ms. With 1,600 ms left (more than a global cooldown) the rescue worked.

The fix (BotAtramedesIceBlock.h IceBlockInTime, used by DecideAirGong): rely on the block only when it is
castable now, or ready at or before the predicted contact less one decision step (IceBlockLatencySeconds,
0.25 s). Otherwise the rescue (or the mage's mobility) goes ahead.

The program drives the production headers with the strategy test's snapshot helpers:
- the reviewer's case at 1,200 ms: the rescue is required (it fails before the fix);
- the boundary: 650 ms (ready 0.25 s before contact) still waits for the block, 700 ms strikes;
- controls: the block castable now is cast (no shield), a pending block that is in time keeps kiting and starts
  no cast, 1,600 ms (more than a global cooldown) strikes as before, an Ice Block the fight already used strikes;
- inside the breath (contact now) only a castable block is relied on;
- the predicate itself: castable now, in time, late, spent, cooling down.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.test_atramedes_strategy import INCLUDES, PROGRAM, ROOT

HARNESS = PROGRAM[:PROGRAM.index("// ---- end of the air-phase replay harness ----")]
ATRAMEDES = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes"

RULES = r'''
// The Mage is chased at Sound 0 by a flame `gap` yd north of it with `stacks` Building Speed stacks, everyone
// else at the arena centre, Ice Block unused with `iceBlockMs` left on its published timer, no Blink ready.
static Blackboard ChasedMage(uint8 stacks, float gap, uint32 iceBlockMs)
{
    Blackboard board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    AddTimer(Member(board, Mage), M::IceBlockSpell, iceBlockMs);
    AddFlame(board, Member(board, Mage), { 110.0f, -271.0f + gap, 75.0f }, stacks);
    return board;
}

static float ContactOf(Blackboard const& board)
{
    A::Facts const facts = A::BuildFacts(board);
    ActorSnapshot const* kiter = A::FindLivingPlayer(board, facts.AirKiter);
    assert(kiter && A::KiterFlame(facts, *kiter));
    return A::FlameTimeToContact(*A::KiterFlame(facts, *kiter), *kiter);
}

static A::GongDecision DecisionOf(Blackboard const& board)
{
    return A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board));
}

static bool CastsIceBlock(AdaptiveAtramedesPlan const& plan)
{
    BotNativeAction::CastSpell const* cast = CastOf(plan);
    return cast && cast->SpellId == M::IceBlockSpell;
}

// The reviewer's geometry: six stacks, 9.06 yd apart, contact in 0.911 s.
static constexpr float ReviewerGap = 9.06f;

static void TestReviewerCaseStrikesWhenTheBlockIsLate()
{
    Blackboard board = ChasedMage(6, ReviewerGap, 1200);
    // The premise: the flame is 0.911 s from the mage, inside the rescue lead, and its Sound is 0.
    float const contact = ContactOf(board);
    assert(contact > 0.90f && contact < 0.92f && contact <= A::RescueLeadSeconds);
    assert(Member(board, Mage).AlternatePower == 0 && !M::Ready(Member(board, Mage), M::BlinkSpell));
    A::Facts const facts = A::BuildFacts(board);
    assert(A::IceBlockUsable(facts, Member(board, Mage)) && !A::IceBlockReady(Member(board, Mage)));
    // The block comes after the flame: the rescue goes ahead (it was withheld as "kiter_ice_block").
    A::GongDecision const late = DecisionOf(board);
    assert(late.Required && late.Urgent && late.Reason == "air_breath_rescue" && late.Withheld.empty());
    assert(!late.Clicker.IsEmpty());
    // The mage does not wait on a block it cannot cast, nor hold its cast back for it.
    AdaptiveAtramedesPlan const plan = Plan(board, Mage);
    assert(!CastsIceBlock(plan));
    assert(plan.Interaction || plan.Movement);
    // A ready Blink (the mage's mobility) comes before the strike, not the late block.
    Blackboard blink = ChasedMage(6, ReviewerGap, 1200);
    AddTimer(Member(blink, Mage), M::BlinkSpell, 0);
    assert(!DecisionOf(blink).Required && DecisionOf(blink).Withheld == "kiter_mobility_extension");
    // With more than a global cooldown left the rescue already worked.
    Blackboard cooling = ChasedMage(6, ReviewerGap, 1600);
    assert(DecisionOf(cooling).Required && DecisionOf(cooling).Reason == "air_breath_rescue");
}

static void TestBoundaryAndControls()
{
    // The boundary: ready 0.25 s before contact still waits for the block, a little later does not.
    float const contact = ContactOf(ChasedMage(6, ReviewerGap, 0));
    assert(contact > 0.90f && contact < 0.92f);
    uint32 const edge = uint32((contact - A::IceBlockLatencySeconds) * 1000.0f);
    assert(edge > 600 && edge < 700);
    for (uint32 ms : { 0u, 300u, 600u, edge - 1 })
    {
        Blackboard board = ChasedMage(6, ReviewerGap, ms);
        A::GongDecision const wait = DecisionOf(board);
        assert(!wait.Required && wait.Withheld == "kiter_ice_block");
        assert(CountClicks(board) == 0);
        AdaptiveAtramedesPlan const plan = Plan(board, Mage);
        if (ms == 0)
        {
            // Control: castable now, it is cast (no shield, no movement).
            assert(CastsIceBlock(plan) && !plan.Movement);
        }
        else
        {
            // Pending but in time: it kites on and starts no new cast, so the block goes out when castable.
            assert(!CastsIceBlock(plan) && !plan.Interaction && plan.Movement && plan.SuppressOffense);
        }
    }
    for (uint32 ms : { edge + 25u, 900u, 1200u, 1500u, 1600u, 5000u })
    {
        A::GongDecision const strike = DecisionOf(ChasedMage(6, ReviewerGap, ms));
        assert(strike.Required && strike.Reason == "air_breath_rescue" && strike.Withheld.empty());
    }
    // Negative control: the same timers with the flame still far away (contact not yet due) change nothing.
    for (uint32 ms : { 0u, 1200u })
    {
        Blackboard far = ChasedMage(6, 40.0f, ms);
        assert(ContactOf(far) > A::RescueLeadSeconds && !DecisionOf(far).Required);
    }
    // Ice Block the fight already used is never relied on, whatever the timer says.
    Blackboard spent = ChasedMage(6, ReviewerGap, 0);
    A::Facts facts = A::BuildFacts(spent);
    facts.IceBlockSpent = true;
    A::GongDecision const used = A::DecideGong(spent, facts, A::BuildDutyPlan(spent));
    assert(used.Required && used.Withheld.empty());
    // Hypothermia: no play either.
    Blackboard cold = ChasedMage(6, ReviewerGap, 0);
    AddAura(Member(cold, Mage), A::HypothermiaAura, PlayerGuid(Mage));
    assert(DecisionOf(cold).Required);
}

static void TestInsideTheBreath()
{
    // The flame is on the mage (contact now, 0 stacks): only a block that is castable now is relied on; a block
    // a global cooldown away takes two breath ticks first, so the rescue strikes.
    Blackboard ready = ChasedMage(0, 3.0f, 0);
    assert(ContactOf(ready) == 0.0f);
    assert(DecisionOf(ready).Withheld == "kiter_ice_block" && !DecisionOf(ready).Required);
    assert(CastsIceBlock(Plan(ready, Mage)));
    for (uint32 ms : { 1u, 250u, 1000u })
    {
        Blackboard pending = ChasedMage(0, 3.0f, ms);
        A::GongDecision const strike = DecisionOf(pending);
        assert(strike.Required && strike.Reason == "air_breath_rescue");
        assert(!CastsIceBlock(Plan(pending, Mage)));
    }
}

static void TestPredicate()
{
    Blackboard board = ChasedMage(6, ReviewerGap, 0);
    A::Facts const facts = A::BuildFacts(board);
    ActorSnapshot& mage = Member(board, Mage);
    float const inf = std::numeric_limits<float>::infinity();
    // Castable now: in time whatever the contact.
    assert(A::IceBlockReadySeconds(facts, mage) == 0.0f);
    assert(A::IceBlockInTime(facts, mage, 0.0f) && A::IceBlockInTime(facts, mage, 5.0f));
    // Pending: ready + one decision step must not pass the contact.
    TimerOf(mage, M::IceBlockSpell)->RemainingMs = 400;
    assert(std::fabs(A::IceBlockReadySeconds(facts, mage) - 0.4f) < 0.0001f);
    assert(A::IceBlockInTime(facts, mage, 0.65f) && !A::IceBlockInTime(facts, mage, 0.64f));
    assert(!A::IceBlockInTime(facts, mage, 0.0f));
    // More than a global cooldown, a used block, Hypothermia, a block already up, a dead or unknown mage: no play.
    TimerOf(mage, M::IceBlockSpell)->RemainingMs = 1501;
    assert(A::IceBlockReadySeconds(facts, mage) == inf && !A::IceBlockInTime(facts, mage, 100.0f));
    TimerOf(mage, M::IceBlockSpell)->RemainingMs = 0;
    A::Facts spent = facts;
    spent.IceBlockSpent = true;
    assert(A::IceBlockReadySeconds(spent, mage) == inf && !A::IceBlockInTime(spent, mage, 100.0f));
    Blackboard iced = board;
    Member(iced, Mage).Auras.push_back({ A::IceBlockAura, PlayerGuid(Mage), 0, iced.ObservedAtMs + 10000 });
    assert(!A::IceBlockInTime(facts, Member(iced, Mage), 100.0f));
    Blackboard unknown = AirBoard();
    assert(A::IceBlockReadySeconds(A::BuildFacts(unknown), Member(unknown, Mage)) == inf);
}

static void RunRules()
{
    TestReviewerCaseStrikesWhenTheBlockIsLate();
    TestBoundaryAndControls();
    TestInsideTheBreath();
    TestPredicate();
    std::puts("ice block timing rules ok");
}

int main()
{
    RunRules();
    return 0;
}
'''


def compile_and_run(tmp_path: Path, include_first: list[str] | None = None) -> subprocess.CompletedProcess:
    source = tmp_path / "ice_block_timing.cpp"
    binary = tmp_path / "ice_block_timing"
    source.write_text(HARNESS + RULES, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-O1",
                    *(include_first or []), *INCLUDES, str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)


def test_chased_mage_relies_on_ice_block_only_when_it_beats_the_breath(tmp_path: Path) -> None:
    result = compile_and_run(tmp_path)
    print(result.stdout)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert "ice block timing rules ok" in result.stdout


def test_the_gong_decision_compares_readiness_with_contact() -> None:
    gong = (ATRAMEDES / "BotAtramedesAirGong.h").read_text(encoding="utf-8")
    assert "bound.empty() && contact && IceBlockInTime(facts, *kiter, timeToContact)" in gong
    assert "bound.empty() && contact && IceBlockUsable(" not in gong
    ice = (ATRAMEDES / "BotAtramedesIceBlock.h").read_text(encoding="utf-8")
    body = ice[ice.index("inline bool IceBlockInTime("):]
    body = body[:body.index("\n}\n")]
    assert "ready <= 0.0f || ready + IceBlockLatencySeconds <= secondsToContact" in body
    assert "IceBlockLatencySeconds = 0.25f" in ice
    for path in (ATRAMEDES / "BotAtramedesAirGong.h", ATRAMEDES / "BotAtramedesIceBlock.h"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path.name
