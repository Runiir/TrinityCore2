"""Round 4 (BWD 10N, tier-11 gear): healer mana and the late outage.

Round 3 wiped 4/4 at the first Bile-O-Tron outage, which the 10N knockout
rule moves to the second or third Massacre. The healers spent 1.2 M healing
topping the raid between the first two Massacres (every Massacre sets the raid
back to 1 health), reached the outage about 70% dry and healed 0.77-0.81 M
there against 1.70 M in round 2; the slime volleys killed 7-8 members at
1-25k. These replays pin the repairs:

- while the mixture is up a healer with no floor, soak or tank entry holds
  instead of the runtime's lowest-health top-up;
- the outage raises everyone above the slime line (lowest absolute health
  first), with tanks as ordinary members while Feud pacifies the boss;
- Power Word: Barrier covers both volleys of the outage;
- Divine Plea and Mana Tide Totem are cast in quiet mixture windows, gated on
  the caster's own mana by the runtime.
"""
from __future__ import annotations

from pathlib import Path

from tests.test_chimaeron_strategy import CHIMAERON, PRELUDE, compile_and_run

PROGRAM = PRELUDE + r'''
static void AtOneHealth(Blackboard& board)
{
    for (ActorSnapshot& player : board.Players)
    {
        player.Health = 1;
        player.HealthPct = 100.0f / float(player.MaxHealth);
    }
}

static void SetHealth(Blackboard& board, uint32 guid, uint64 health, uint64 maxHealth = 150000)
{
    ActorSnapshot& player = P(board, guid);
    player.MaxHealth = maxHealth;
    player.Health = health;
    player.HealthPct = 100.0f * float(health) / float(maxHealth);
}

static Blackboard Outage(bool feud = true)
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    for (ActorSnapshot& player : board.Players)
        player.Auras.clear();
    if (feud)
        Boss(board).Auras.push_back({ C::FeudSpell, Boss(board).Guid, 1,
            board.ObservedAtMs + 20000 });
    return board;
}

static void TestMixtureHoldsTopUp()
{
    // Mixture up, a DPS at 60%: above the floor, protected. Topping him up is
    // lost to the next Massacre, so no healer heals (the runtime would pick
    // the lowest member below 94% without a published target).
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    SetHealth(board, ROGUE, 90000);
    for (uint32 healer : { HOLY, DISC, SHAMAN })
    {
        AdaptiveChimaeronPlan const plan = Plan(board, healer);
        CHECK(plan.PriorityHealTarget.IsEmpty());
        CHECK(plan.HealingDisabled);
        CHECK(plan.HealingHoldReason == "mixture_floor_only_conserve_mana");
    }
    // Not a healer: nothing to hold.
    CHECK(!Plan(board, MAGE).HealingDisabled);

    // At the floor he is published and healing runs.
    SetHealth(board, ROGUE, 15000);
    AdaptiveChimaeronPlan const floor = Plan(board, HOLY);
    CHECK(floor.PriorityHealTarget == G(ROGUE) && !floor.HealingDisabled);
    CHECK(floor.HealingHoldReason.empty());

    // Tank top-ups still run (the Double Attack tank below 90%).
    SetHealth(board, ROGUE, 90000);
    SetHealth(board, DRUID, 100000);
    AdaptiveChimaeronPlan const tank = Plan(board, HOLY);
    CHECK(tank.PriorityHealTarget == G(DRUID) && !tank.HealingDisabled);

    // Another hostile fighting the raid lifts the hold.
    SetHealth(board, DRUID, 150000);
    ActorSnapshot add;
    add.Guid = ObjectGuid(HighGuid::Unit, uint32(46083), uint32(777));
    add.Entry = 46083;
    add.Alive = add.Attackable = add.InCombat = true;
    add.VictimGuid = G(MAGE);
    board.Hostiles.push_back(add);
    CHECK(!Plan(board, HOLY).HealingDisabled);

    // Outage: no hold even with nothing listed.
    Blackboard outage = Outage();
    CHECK(!Plan(outage, HOLY).HealingDisabled);
}

static void TestOutageSlimeLine()
{
    // 10 alive in one stack: 2 x 235,200 / 10 + 10,000.
    Blackboard outage = Outage();
    CHECK(C::OutageSlimeSafeHealth(outage, P(outage, ROGUE)) == 57040u);

    // Right after the knockout Massacre everyone sits at 1 health. Feud
    // pacifies the boss, so the tank healer takes the lowest member of the
    // stack, not the tank.
    AtOneHealth(outage);
    SetHealth(outage, DK, 2000, 250000);
    SetHealth(outage, MAGE, 5000);
    ObjectGuid const holy = Plan(outage, HOLY).PriorityHealTarget;
    CHECK(holy != G(DK));
    CHECK(P(outage, uint32(holy.GetCounter())).Health == 1);
    // The three healers take three different members.
    ObjectGuid const disc = Plan(outage, DISC).PriorityHealTarget;
    ObjectGuid const shaman = Plan(outage, SHAMAN).PriorityHealTarget;
    CHECK(holy != disc && disc != shaman && holy != shaman);

    // Below the line the order is absolute health: the tank at 50,000 of
    // 250,000 (20%) waits behind the hunter at 40,000 of 150,000 (26.7%).
    Blackboard line = Outage();
    SetHealth(line, DK, 50000, 250000);
    SetHealth(line, HUNTER, 40000);
    CHECK(Plan(line, HOLY).PriorityHealTarget == G(HUNTER));
    CHECK(Plan(line, DISC).PriorityHealTarget == G(DK));

    // Above the line: top-up by health percentage.
    Blackboard topUp = Outage();
    SetHealth(topUp, DK, 175000, 250000);   // 70%
    SetHealth(topUp, MAGE, 60000);          // 40%
    CHECK(Plan(topUp, HOLY).PriorityHealTarget == G(MAGE));
    CHECK(Plan(topUp, DISC).PriorityHealTarget == G(DK));

    // A slime line member outranks any top-up.
    SetHealth(topUp, ROGUE, 56000);
    CHECK(Plan(topUp, HOLY).PriorityHealTarget == G(ROGUE));

    // Fewer members share the slime: the line rises (6 alive: 88,400).
    Blackboard fewer = Outage();
    for (uint32 dead : { HUNTER, MAGE, RET, LOCK })
        P(fewer, dead).Alive = false;
    CHECK(C::OutageSlimeSafeHealth(fewer, P(fewer, ROGUE)) == 88400u);
    SetHealth(fewer, ROGUE, 80000);
    CHECK(Plan(fewer, HOLY).PriorityHealTarget == G(ROGUE));

    // The victim at the floor during Feud is not a tier-0 double cover.
    Blackboard victim = Outage();
    AtOneHealth(victim);
    SetHealth(victim, DK, 5000, 250000);
    CHECK(Plan(victim, HOLY).PriorityHealTarget != G(DK)
        || Plan(victim, DISC).PriorityHealTarget != G(DK));

    // An outage without Feud (not observed on a knockout) keeps the tank
    // healer on the tanks.
    Blackboard noFeud = Outage(false);
    AtOneHealth(noFeud);
    SetHealth(noFeud, DK, 2000, 250000);
    CHECK(Plan(noFeud, HOLY).PriorityHealTarget == G(DK) || Plan(noFeud, HOLY).PriorityHealTarget == G(DRUID));
}

// Review r4 finding 9: the line is read from the splash geometry, not from
// every living member. Ten alive, but only six share each splash (the stack
// is still forming): 2 x 235,200 / 6 = 78,400 per recipient, so a member at
// 58,000 is below the line (88,400), not a percentage top-up.
static void TestOutageSlimeLineFollowsTheSplash()
{
    Blackboard split = Outage();
    // Four members 12 yd away: outside every splash of the six.
    for (uint32 away : { HUNTER, MAGE, RET, LOCK })
        P(split, away).Position.X += 12.0f;
    CHECK(C::OutageSlimeSafeHealth(split, P(split, ROGUE)) == 88400u);
    // The four share with one another only: 2 x 235,200 / 4 + 10,000.
    CHECK(C::OutageSlimeSafeHealth(split, P(split, MAGE)) == 127600u);
    SetHealth(split, ROGUE, 58000);
    SetHealth(split, DK, 95000, 250000);    // 38%, above his line: a top-up
    CHECK(Plan(split, HOLY).PriorityHealTarget == G(ROGUE));
    CHECK(!C::NoUrgentHealing(split, C::Observe(split, G(HOLY)),
        C::BuildDuties(split, G(HOLY))));

    // A member 6.5 yd from the stack is reached by its slimes, but shares
    // none of them: the stack's full share lands on him as well.
    Blackboard edge = Outage();
    P(edge, LOCK).Position.X += 6.5f;
    // Slimes on the nine (each shared by nine) or on him alone.
    CHECK(C::OutageSlimeSafeHealth(edge, P(edge, LOCK)) == 235200u + 26133u + 10000u);

    // The full stack keeps the shared line.
    Blackboard stacked = Outage();
    SetHealth(stacked, ROGUE, 58000);
    CHECK(C::OutageSlimeSafeHealth(stacked, P(stacked, ROGUE)) == 57040u);
}

static void TestBarrierCoversBothVolleys()
{
    Blackboard board = Outage();
    for (ActorSnapshot& player : board.Players)
        player.Position = { HomeX, HomeY - C::ColumnMiddleDistance, HomeZ };
    ActorSnapshot& boss = Boss(board);
    // 16 s left: a Barrier now (10 s) would expire before the second volley
    // (6.2-7.0 s left, WCL).
    boss.Auras[0].ExpiresAtMs = board.ObservedAtMs + 16000;
    CHECK(CastOf(Plan(board, DISC)) != 62618);
    boss.Auras[0].ExpiresAtMs = board.ObservedAtMs + 15000;
    CHECK(CastOf(Plan(board, DISC)) == 62618);
    boss.Auras[0].ExpiresAtMs = board.ObservedAtMs + 13000;
    CHECK(CastOf(Plan(board, DISC)) == 62618);
    // The first volley lands at 12.3-12.8 s left: too late to start.
    boss.Auras[0].ExpiresAtMs = board.ObservedAtMs + 12000;
    CHECK(CastOf(Plan(board, DISC)) != 62618);
}

static void TestManaCooldowns()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    Boss(board).MechanicTimers.push_back({ C::MassacreSpell, 20000, false,
        FactSource::NativeInstanceState });
    ObjectGuid target;
    CHECK(CastOf(Plan(board, HOLY), &target) == 54428 && target == G(HOLY));
    CHECK(MechanicOf(Plan(board, HOLY)) == "mixture_divine_plea");
    CHECK(CastOf(Plan(board, SHAMAN), &target) == 16190 && target == G(SHAMAN));
    CHECK(MechanicOf(Plan(board, SHAMAN)) == "mixture_mana_tide_totem");
    CHECK(!Plan(board, DISC).Action);
    CHECK(!Plan(board, MAGE).Action && !Plan(board, RET).Action);

    // A member at the floor: heal first.
    SetHealth(board, LOCK, 5000);
    CHECK(!Plan(board, HOLY).Action && !Plan(board, SHAMAN).Action);
    SetHealth(board, LOCK, 150000);

    // Divine Plea (9 s, -50% healing) must end before the Massacre lands.
    Boss(board).MechanicTimers.back().RemainingMs = 9000;
    CHECK(!Plan(board, HOLY).Action);
    Boss(board).MechanicTimers.back().RemainingMs = 0;
    CHECK(!Plan(board, HOLY).Action);
    Boss(board).MechanicTimers.clear();
    CHECK(!Plan(board, HOLY).Action);

    // Not in the burn window, not in an outage.
    Blackboard burn = Board("bwd.chimaeron.encounter", true);
    Boss(burn).MechanicTimers.push_back({ C::MassacreSpell, 20000, false,
        FactSource::NativeInstanceState });
    Boss(burn).HealthPct = 22.0f;
    CHECK(CastOf(Plan(burn, HOLY)) != 54428);
    Blackboard outage = Outage();
    Boss(outage).MechanicTimers.push_back({ C::MassacreSpell, 20000, false,
        FactSource::NativeInstanceState });
    CHECK(CastOf(Plan(outage, HOLY)) != 54428 && CastOf(Plan(outage, SHAMAN)) != 16190);

    // The runtime's own mana line.
    CHECK(C::IsManaCooldownSpell(54428) && C::IsManaCooldownSpell(16190));
    CHECK(!C::IsManaCooldownSpell(62618) && !C::IsManaCooldownSpell(80353));
    CHECK(C::ManaCooldownWanted(54428, 80.0f) && !C::ManaCooldownWanted(54428, 90.0f));
    CHECK(C::ManaCooldownWanted(16190, 70.0f) && !C::ManaCooldownWanted(16190, 80.0f));
    CHECK(!C::ManaCooldownWanted(62618, 0.0f));
}

int main()
{
    TestMixtureHoldsTopUp();
    TestOutageSlimeLine();
    TestOutageSlimeLineFollowsTheSplash();
    TestBarrierCoversBothVolleys();
    TestManaCooldowns();
    if (failures)
        std::fprintf(stderr, "%d checks failed\n", failures);
    return failures ? 1 : 0;
}
'''


def test_chimaeron_mana_and_outage_replay(tmp_path: Path) -> None:
    result = compile_and_run(tmp_path, PROGRAM, "chimaeron_mana_and_outage")
    assert result.returncode == 0, result.stderr


def test_runtime_gates_mana_cooldowns_on_its_own_mana() -> None:
    """The snapshot carries no mana: the runtime checks the caster's own mana
    line, spell book and cooldown before submitting, and skips with a typed,
    resource-free candidate otherwise."""
    source = (CHIMAERON / "BotWorldPopulationMgrChimaeronCandidates.cpp").read_text(encoding="utf-8")
    for marker in (
        "BotEncounter::Chimaeron::IsManaCooldownSpell(cast->SpellId)",
        "context.Bot->GetPower(POWER_MANA)",
        "BotEncounter::Chimaeron::ManaCooldownWanted(",
        "context.Bot->HasSpell(cast->SpellId)",
        "context.Bot->GetSpellHistory()->IsReady(spellInfo)",
        "BotEncounter::Chimaeron::ManaCooldownNotNeededReason",
    ):
        assert marker in source, marker
    assert source.index("ManaCooldownWanted(") < source.index("ExecuteNativeActionIntent(")
