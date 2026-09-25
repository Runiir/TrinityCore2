"""Burn window before Mortality and the cohort encounter latches (Chimaeron 10N).

Covers the one-step release and handoff, the last-chance handoff, the bounded
hold, a failed handoff, the generic latch store, and replays that start from a
Massacre at 21% with the raid at 1 health. Shares PRELUDE (blackboard builders,
the cohort publisher) with tests/test_chimaeron_strategy.py.
"""
from __future__ import annotations

from pathlib import Path

from tests.test_chimaeron_strategy import PRELUDE, compile_and_run

BURN_TESTS = r'''
static void ReadyBoard(Blackboard& board, float healthPct)
{
    Boss(board).HealthPct = healthPct;
    Boss(board).VictimGuid = G(DK);
    Boss(board).Cast.reset();
    for (ActorSnapshot& player : board.Players)
        player.HealthPct = 100.0f;
}

static void CastMassacre(Blackboard& board)
{
    Boss(board).Cast = CastSnapshot{ C::MassacreSpell, ObjectGuid(), board.ObservedAtMs, false, false };
}

// Before the handoff arms (above the 21% last-chance line) the ordinary
// exchange continues;
// the release makes the Feral's handoff the first action.
static void TestBurnTauntExchange()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    ObjectGuid const boss = Boss(board).Guid;
    EncounterLatchStore store;
    ReadyBoard(board, 21.2f);
    CastMassacre(board);
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
    CHECK(!Latched(store, C::BurnReleasedLatch));

    Boss(board).VictimGuid = G(DK);
    Boss(board).Cast.reset();
    Publish(board, store);
    CHECK(Latched(store, C::BurnReleasedLatch) && !Latched(store, C::HandoffDoneLatch));
    CHECK(Latched(store, C::BurnReleasedLatch)->Value == uint64(C::BurnReleaseReason::Ready));
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff");
    CHECK(!Plan(board, DK, &store.View()).Action);
    // Latched: a Massacre cast after the release does not cancel the handoff.
    CastMassacre(board);
    Publish(board, store);
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff");
    Boss(board).Cast.reset();
    Boss(board).VictimGuid = G(DRUID);
    Publish(board, store);
    CHECK(Latched(store, C::HandoffDoneLatch));
    CHECK(!Plan(board, DK, &store.View()).Action && !Plan(board, DRUID, &store.View()).Action);
    // The Feral retakes the boss from anyone until Mortality.
    Boss(board).VictimGuid = G(DK);
    Publish(board, store);
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff");
    CHECK(!Plan(board, DK, &store.View()).Action);
}

static void TestBurnWindow()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    Boss(board).HealthPct = 22.0f;
    CastMassacre(board);
    AdaptiveChimaeronPlan const hold = Plan(board, ROGUE);
    CHECK(hold.SuppressOffense && hold.SuppressReason == "burn_hold_before_mortality");
    CHECK(!Plan(board, MAGE).Action);   // no lust into a Massacre
    // Above the handoff line tanks keep attacking in the hold (threat, Death Strike).
    CHECK(!Plan(board, DK).SuppressOffense && !Plan(board, DRUID).SuppressOffense);

    // Ready (no view: this revision decides): released, handoff pending.
    Boss(board).Cast.reset();
    CHECK(Plan(board, ROGUE).SuppressReason == "burn_wait_for_mortality_handoff");
    CHECK(MechanicOf(Plan(board, DRUID)) == "taunt_mortality_handoff");
    CHECK(Plan(board, DK).SuppressReason == "burn_break_tank_stand_down");
    CHECK(!Plan(board, MAGE).Action);
    // The Feral holds the boss: the push starts and the lust owner lusts.
    Boss(board).VictimGuid = G(DRUID);
    CHECK(!Plan(board, ROGUE).SuppressOffense && !Plan(board, DRUID).SuppressOffense);
    ObjectGuid target;
    CHECK(CastOf(Plan(board, MAGE), &target) == 80353 && target == G(MAGE));
    CHECK(Plan(board, DK).SuppressOffense);

    // Cohort latches hold for the scope: a swing on a tank or a Massacre
    // mid-burn does not re-suppress the push.
    EncounterLatchStore store;
    Boss(board).VictimGuid = G(DK);
    Publish(board, store);
    Boss(board).VictimGuid = G(DRUID);
    Publish(board, store);
    CHECK(Latched(store, C::HandoffDoneLatch));
    P(board, DRUID).HealthPct = 60.0f;
    CastMassacre(board);
    Publish(board, store);
    CHECK(!Plan(board, ROGUE, &store.View()).SuppressOffense);
    // Every bot reads the same view: a stale revision is ignored.
    EncounterLatchView stale = store.View();
    stale.Revision -= 1;
    CHECK(Plan(board, ROGUE, &stale).SuppressOffense);
    // A new scope key (next attempt, wipe generation, route node) starts over.
    // The native encounter epoch is part of the key but authoritative only
    // for Magmaw today; Chimaeron relies on the disengage reset below.
    board.CurrentScope.WipeGeneration += 1;
    Publish(board, store);
    CHECK(!Latched(store, C::BurnReleasedLatch) && Plan(board, ROGUE, &store.View()).SuppressOffense);
    // A disengaged boss (evade with survivors keeps the GUID) clears the module.
    ReadyBoard(board, 22.0f);
    Publish(board, store);
    CHECK(Latched(store, C::BurnReleasedLatch));
    Boss(board).InCombat = false;
    Boss(board).VictimGuid.Clear();
    Publish(board, store);
    EncounterLatchModuleView const* module = store.View().Module(C::LatchModule);
    CHECK(module && module->Latches.empty() && module->Subject.IsEmpty());
    Boss(board).InCombat = true;

    // Held below the handoff line, the tanks are held too.
    Blackboard low = Board("bwd.chimaeron.encounter", true);
    Boss(low).HealthPct = 21.2f;
    CastMassacre(low);
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

    // An outage in the window holds; damage over time alone never releases.
    Blackboard outage = Board("bwd.chimaeron.encounter", true);
    for (ActorSnapshot& player : outage.Players)
        player.Auras.clear();
    Boss(outage).HealthPct = 22.0f;
    CHECK(Plan(outage, ROGUE).SuppressOffense);
    Boss(outage).HealthPct = 20.6f;
    CHECK(Plan(outage, ROGUE).SuppressOffense && Plan(outage, DK).SuppressOffense);

    // Mortality: lust if unused; the Break tank stands down behind a living
    // Double Attack tank.
    Blackboard mortality = Board("bwd.chimaeron.encounter", true);
    Boss(mortality).HealthPct = 19.0f;
    Boss(mortality).Auras.push_back({ C::MortalityBossSpell, Boss(mortality).Guid, 1, 0 });
    CHECK(CastOf(Plan(mortality, MAGE)) == 80353);
    CHECK(!Plan(mortality, ROGUE).SuppressOffense && !Plan(mortality, DRUID).SuppressOffense);
    CHECK(Plan(mortality, DK).SuppressOffense);
    P(mortality, DRUID).Alive = false;
    CHECK(!Plan(mortality, DK).SuppressOffense);
}

// Damage the hold cannot stop carries the boss to 21% unreleased: the
// handoff arms anyway, the Break tank stops taunting and stands down, and the
// non-tanks wait for readiness.
static void TestLastChanceHandoff()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    EncounterLatchStore store;
    ReadyBoard(board, 21.1f);
    P(board, DK).HealthPct = 30.0f;     // readiness out of reach for now
    Publish(board, store);
    CHECK(!Latched(store, C::LastChanceLatch) && !Plan(board, DRUID, &store.View()).Action);
    Boss(board).HealthPct = 21.0f;
    Publish(board, store);
    CHECK(Latched(store, C::LastChanceLatch) && !Latched(store, C::BurnReleasedLatch));
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff");
    CHECK(Plan(board, DK, &store.View()).SuppressReason == "burn_break_tank_stand_down");
    CHECK(Plan(board, ROGUE, &store.View()).SuppressReason == "burn_hold_before_mortality");
    // The Break tank never takes the boss back, even from a Double Attack.
    Boss(board).VictimGuid = G(DRUID);
    Publish(board, store);
    CHECK(Latched(store, C::HandoffDoneLatch));
    CHECK(!Plan(board, DK, &store.View()).Action);
    CHECK(Plan(board, ROGUE, &store.View()).SuppressOffense);   // still waiting for readiness
    CHECK(!Plan(board, MAGE, &store.View()).Action);
    // Readiness releases; the handoff already landed, so the push starts.
    P(board, DK).HealthPct = 100.0f;
    Publish(board, store);
    CHECK(Latched(store, C::BurnReleasedLatch));
    CHECK(!Plan(board, ROGUE, &store.View()).SuppressOffense);
    CHECK(CastOf(Plan(board, MAGE, &store.View())) == 80353);

    // Without a view the same line arms from this revision alone.
    Blackboard stateless = Board("bwd.chimaeron.encounter", true);
    ReadyBoard(stateless, 20.4f);
    P(stateless, DK).HealthPct = 30.0f;
    CHECK(MechanicOf(Plan(stateless, DRUID)) == "taunt_mortality_handoff");
    CHECK(!Plan(stateless, DK).Action);
}

// A hold that cannot reach readiness is bounded: two Massacre cycles, or fewer
// than two living healers. The release goes through the same handoff.
static void TestHoldCap()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    EncounterLatchStore store;
    ReadyBoard(board, 22.0f);
    P(board, DK).HealthPct = 30.0f;
    Publish(board, store);
    uint64 const started = Latched(store, C::HoldStartedLatch)->SetAtMs;
    Publish(board, store, 59000);
    CHECK(!Latched(store, C::BurnReleasedLatch) && Plan(board, ROGUE, &store.View()).SuppressOffense);
    Publish(board, store, 1000);
    CHECK(board.ObservedAtMs == started + 60000);
    EncounterLatch const* released = Latched(store, C::BurnReleasedLatch);
    CHECK(released && released->Value == uint64(C::BurnReleaseReason::HoldCap));
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff");
    CHECK(Plan(board, ROGUE, &store.View()).SuppressReason == "burn_wait_for_mortality_handoff");

    Blackboard healers = Board("bwd.chimaeron.encounter", true);
    EncounterLatchStore healerStore;
    ReadyBoard(healers, 22.0f);
    P(healers, DK).HealthPct = 30.0f;
    P(healers, HOLY).Alive = false;
    Publish(healers, healerStore);
    CHECK(!Latched(healerStore, C::BurnReleasedLatch));
    P(healers, DISC).Alive = false;
    Publish(healers, healerStore);
    CHECK(Latched(healerStore, C::BurnReleasedLatch)
        && Latched(healerStore, C::BurnReleasedLatch)->Value == uint64(C::BurnReleaseReason::HealersDown));
}

// The handoff never lands (out of range, line of sight, crowd control, a
// rejected cast): after one taunt cooldown the non-tanks are released, the
// Break tank attacks again to keep his threat, and the Feral keeps retrying.
static void TestFailedHandoff()
{
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    EncounterLatchStore store;
    ReadyBoard(board, 22.0f);
    Publish(board, store);
    uint64 const releasedAt = Latched(store, C::BurnReleasedLatch)->SetAtMs;
    Publish(board, store, 7900);
    CHECK(!Latched(store, C::HandoffTimedOutLatch));
    CHECK(Plan(board, ROGUE, &store.View()).SuppressOffense);
    CHECK(Plan(board, DK, &store.View()).SuppressReason == "burn_break_tank_stand_down");
    Publish(board, store, 100);
    CHECK(board.ObservedAtMs == releasedAt + 8000);
    CHECK(Latched(store, C::HandoffTimedOutLatch) && !Latched(store, C::HandoffDoneLatch));
    CHECK(!Plan(board, ROGUE, &store.View()).SuppressOffense);
    CHECK(!Plan(board, DK, &store.View()).SuppressOffense);
    CHECK(MechanicOf(Plan(board, DRUID, &store.View())) == "taunt_mortality_handoff_retry");
    CHECK(CastOf(Plan(board, MAGE, &store.View())) == 80353);
    // The Break tank recovers a non-tank victim but never takes the boss
    // from the Feral.
    Boss(board).VictimGuid = G(ROGUE);
    Publish(board, store);
    CHECK(MechanicOf(Plan(board, DK, &store.View())) == "taunt_recover_non_tank_victim");
    Boss(board).VictimGuid = G(DRUID);
    Publish(board, store);
    CHECK(Latched(store, C::HandoffDoneLatch) && !Plan(board, DK, &store.View()).Action);
    // The late handoff landed: the Break tank stands down again.
    CHECK(Plan(board, DK, &store.View()).SuppressReason == "burn_break_tank_stand_down");
}

// The generic cohort store: modules are independent, first set wins, scope
// and subject changes clear only what they own.
static void TestEncounterLatchStore()
{
    EncounterLatchStore store;
    store.BeginPublication("scope-a", 5, 1000);
    EncounterLatchModule council = store.Module("council");
    council.BindSubject(G(1));
    CHECK(council.Latch("x", 7).SetAtMs == 1000);
    EncounterLatchModule onyxia = store.Module("onyxia");
    onyxia.BindSubject(G(2));
    onyxia.Latch("y");
    store.BeginPublication("scope-a", 6, 2000);
    council = store.Module("council");
    CHECK(council.Latch("x", 9).SetAtMs == 1000 && council.Find("x")->Value == 7);
    CHECK(store.View().Revision == 6 && store.View().ObservedAtMs == 2000);
    // Another module's subject change leaves this module alone.
    store.Module("onyxia").BindSubject(G(3));
    CHECK(store.Module("council").Find("x") && !store.Module("onyxia").Find("y"));
    store.Module("council").Clear("x");
    CHECK(!store.Module("council").Find("x"));
    store.Module("council").Latch("z");
    store.Module("council").Reset();
    CHECK(!store.Module("council").Find("z") && store.Module("council").Subject().IsEmpty());
    store.Module("council").Latch("z");
    store.BeginPublication("scope-b", 7, 3000);
    CHECK(store.View().Modules.empty());
    CHECK(EncounterLatchScopeKey("k", 3, 4) == "k:3:4");
}

// Replay from a Massacre with the raid at 1 health. Every 250 ms the cohort
// publishes one latch update, all ten bots decide, living healers heal their
// assignment (HealPct each), the Feral's Growl lands once off cooldown, the
// boss swings every 4 s unless Feud pacifies him, and the boss loses 0.12% per
// step when anybody attacks, else 0.02% (damage over time). The adversarial
// walk drops 0.1% every step regardless. Outage clears the mixture; Feud sets
// the boss's Feud aura with the given time left. With a Break cycle, Break
// lands on the victim and Double Attack is applied every cycle (their shared
// native timer); a doubled swing consumes it. Damage over time stops once the
// boss is at or below DotStopPct (0 = never).
struct ReplayConfig
{
    uint64 GrowlReadyAfterMs = 0;
    bool Adversarial = false;
    float HealPct = 20.0f;
    float StartPct = 21.0f;
    bool Outage = false;
    uint64 FeudLeftMs = 0;
    bool HealersDown = false;
    uint64 BreakCycleMs = 0;
    float DotStopPct = 0.0f;
};

struct ReplayResult
{
    bool MortalityReached = false;
    ObjectGuid VictimAtMortality;
    uint64 MortalityAtMs = 0;
    int Violations = 0;
    int FeralBreakStacks = 0;
    int BreakTankBreakStacks = 0;
};

static void Heal(ActorSnapshot& member, float pct)
{
    member.HealthPct = std::min(100.0f, member.HealthPct + pct);
    member.Health = uint64(member.HealthPct * float(member.MaxHealth) / 100.0f);
}

static ReplayResult RunBurnReplay(ReplayConfig const& config)
{
    ReplayResult result;
    Blackboard board = Board("bwd.chimaeron.encounter", true);
    Boss(board).HealthPct = config.StartPct;
    for (ActorSnapshot& player : board.Players)
    {
        player.Health = 1;
        player.HealthPct = 100.0f / 150000.0f;
        if (config.Outage)
            player.Auras.clear();
    }
    if (config.HealersDown)
        P(board, HOLY).Alive = P(board, DISC).Alive = false;
    uint64 const start = board.ObservedAtMs;
    if (config.FeudLeftMs)
        Boss(board).Auras.push_back({ C::FeudSpell, Boss(board).Guid, 1,
            start + config.FeudLeftMs });
    EncounterLatchStore store;
    uint64 growlReadyAt = start + config.GrowlReadyAfterMs;
    uint64 nextSwingAt = start + 4000;
    uint64 nextBreakAt = start + config.BreakCycleMs;
    std::map<uint32, int> breakStacks;
    auto violation = [&](char const* what, uint32 guid)
    {
        ++result.Violations;
        std::fprintf(stderr, "replay violation %s bot %u t=%llu hp=%.2f\n", what, guid,
            static_cast<unsigned long long>(board.ObservedAtMs - start), Boss(board).HealthPct);
    };
    for (int step = 0; step < 400; ++step)
    {
        Publish(board, store, 250);
        auto& bossAuras = Boss(board).Auras;
        bossAuras.erase(std::remove_if(bossAuras.begin(), bossAuras.end(),
            [&board](AuraSnapshot const& aura)
            {
                return aura.SpellId == C::FeudSpell && aura.ExpiresAtMs <= board.ObservedAtMs;
            }), bossAuras.end());
        bool const feud = std::any_of(bossAuras.begin(), bossAuras.end(),
            [](AuraSnapshot const& aura) { return aura.SpellId == C::FeudSpell; });
        bool const released = Latched(store, C::BurnReleasedLatch) != nullptr;
        bool const armed = released || Latched(store, C::LastChanceLatch);
        bool const settled = Latched(store, C::HandoffDoneLatch)
            || Latched(store, C::HandoffTimedOutLatch);
        bool const failed = Latched(store, C::HandoffTimedOutLatch)
            && !Latched(store, C::HandoffDoneLatch);
        std::map<uint32, AdaptiveChimaeronPlan> plans;
        for (uint32 guid : Everyone())
            if (P(board, guid).Alive)
                plans[guid] = Plan(board, guid, &store.View());

        bool const nonTankHeld = plans[ROGUE].SuppressOffense;
        bool const pushing = released && settled;
        for (auto const& [guid, plan] : plans)
        {
            bool const tank = guid == DK || guid == DRUID;
            std::string const mechanic = MechanicOf(plan);
            if (mechanic.rfind("taunt_mortality_handoff", 0) == 0 && !armed)
                violation("handoff_before_armed", guid);
            if (guid == DK && armed && mechanic.rfind("taunt_", 0) == 0
                && !(failed && mechanic == "taunt_recover_non_tank_victim"))
                violation("break_tank_taunt_after_armed", guid);
            if (!tank && !plan.SuppressOffense && !pushing)
                violation("non_tank_released_before_push", guid);
            if (!tank && plan.SuppressOffense != nonTankHeld)
                violation("non_tanks_disagree", guid);
            if (tank && !pushing && Boss(board).HealthPct <= C::MortalityHandoffPct
                && !plan.SuppressOffense)
                violation("tank_attacks_below_handoff_line_while_held", guid);
        }

        for (uint32 healer : { HOLY, DISC, SHAMAN })
        {
            if (!P(board, healer).Alive)
                continue;
            ObjectGuid heal = plans[healer].PriorityHealTarget;
            if (heal.IsEmpty())
                for (uint32 tank : { DK, DRUID })
                    if (P(board, tank).HealthPct < 90.0f
                        && (heal.IsEmpty() || P(board, tank).HealthPct
                            < P(board, heal.GetCounter()).HealthPct))
                        heal = G(tank);
            if (!heal.IsEmpty())
                Heal(P(board, heal.GetCounter()), config.HealPct);
        }
        if (CastOf(plans[DRUID]) == 6795 && board.ObservedAtMs >= growlReadyAt)
        {
            Boss(board).VictimGuid = G(DRUID);
            growlReadyAt = board.ObservedAtMs + 8000;
        }
        if (CastOf(plans[DK]) == 56222)
            Boss(board).VictimGuid = G(DK);
        auto doubleAttack = [&board]()
        {
            auto& auras = Boss(board).Auras;
            return std::find_if(auras.begin(), auras.end(), [](AuraSnapshot const& aura)
                { return aura.SpellId == C::DoubleAttackSpell; });
        };
        if (config.BreakCycleMs && board.ObservedAtMs >= nextBreakAt)
        {
            int& stacks = breakStacks[Boss(board).VictimGuid.GetCounter()];
            stacks = std::min(4, stacks + 1);
            if (doubleAttack() == Boss(board).Auras.end())
                Boss(board).Auras.push_back({ C::DoubleAttackSpell, Boss(board).Guid, 1, 0 });
            nextBreakAt += config.BreakCycleMs;
        }
        if (!feud && board.ObservedAtMs >= nextSwingAt)
        {
            float damage = 25.0f;
            if (auto itr = doubleAttack(); itr != Boss(board).Auras.end())
            {
                Boss(board).Auras.erase(itr);
                damage = 50.0f;
            }
            ActorSnapshot& victim = P(board, Boss(board).VictimGuid.GetCounter());
            victim.HealthPct = std::max(1.0f, victim.HealthPct - damage);
            victim.Health = uint64(victim.HealthPct * float(victim.MaxHealth) / 100.0f);
            nextSwingAt += 4000;
        }
        bool attacking = false;
        for (uint32 guid : { DK, DRUID, HUNTER, MAGE, RET, ROGUE, LOCK })
            attacking = attacking || !plans[guid].SuppressOffense;
        float const dot = Boss(board).HealthPct > config.DotStopPct ? 0.02f : 0.0f;
        float const drop = config.Adversarial ? 0.1f : (attacking ? 0.12f : dot);
        Boss(board).HealthPct -= drop;
        if (Boss(board).HealthPct <= C::MortalityHealthPct)
        {
            result.MortalityReached = true;
            result.VictimAtMortality = Boss(board).VictimGuid;
            result.MortalityAtMs = board.ObservedAtMs - start;
            result.FeralBreakStacks = breakStacks[DRUID];
            result.BreakTankBreakStacks = breakStacks[DK];
            break;
        }
    }
    return result;
}

static ReplayResult Replay(uint64 growlReadyAfterMs, bool adversarial, float healPct)
{
    ReplayConfig config;
    config.GrowlReadyAfterMs = growlReadyAfterMs;
    config.Adversarial = adversarial;
    config.HealPct = healPct;
    return RunBurnReplay(config);
}

static void CheckFeral(ReplayResult const& result, char const* label)
{
    if (result.Violations || !result.MortalityReached || result.VictimAtMortality != G(DRUID))
        std::fprintf(stderr, "replay %s: violations=%d mortality=%d victim=%u\n", label,
            result.Violations, int(result.MortalityReached), result.VictimAtMortality.GetCounter());
    CHECK(result.Violations == 0);
    CHECK(result.MortalityReached && result.VictimAtMortality == G(DRUID));
}

static void TestBurnReplayFromPostMassacre()
{
    // Fast healing: readiness releases, the Feral takes the boss into Mortality.
    for (uint64 growlReady : { 0ull, 3000ull, 6000ull })
        CheckFeral(Replay(growlReady, false, 20.0f), "fast healing");
    // Damage over time only and healers needing far longer than 12 s to bring
    // both tanks to 80%: the last-chance line hands the boss to the Feral.
    for (uint64 growlReady : { 0ull, 3000ull, 6000ull, 8000ull })
        CheckFeral(Replay(growlReady, false, 1.0f), "slow healing");
    // Adversarial walk (0.1% per step whatever the hold does): the Feral is
    // the Mortality victim whenever his taunt is available before 20%.
    for (uint64 growlReady : { 0ull, 1000ull, 2000ull, 2500ull })
        CheckFeral(Replay(growlReady, true, 1.0f), "adversarial walk");
    // Taunt unavailable until after 20%: only the sequence rules can hold.
    ReplayResult const late = Replay(6000, true, 1.0f);
    CHECK(late.Violations == 0 && late.MortalityReached);

    // Outage with Feud still running: the armed handoff is not held back by
    // Feud, by last chance (15 s and 25 s left) or by healers down.
    for (uint64 feudLeft : { 15000ull, 25000ull })
    {
        ReplayConfig lastChance;
        lastChance.HealPct = 1.0f;
        lastChance.Outage = true;
        lastChance.FeudLeftMs = feudLeft;
        CheckFeral(RunBurnReplay(lastChance), "outage feud last chance");
        ReplayConfig healersDown = lastChance;
        healersDown.HealersDown = true;
        CheckFeral(RunBurnReplay(healersDown), "outage feud healers down");
    }

    // The last-chance margin covers a Growl just spent on a Double Attack
    // soak: the line arms at 21.0% (2.5 s from 21.2%) and Growl returns 7.9 s
    // later, still before the damage over time reaches 20%.
    ReplayConfig spent;
    spent.HealPct = 1.0f;
    spent.StartPct = 21.2f;
    spent.GrowlReadyAfterMs = 2500 + 7900;
    ReplayResult const margin = RunBurnReplay(spent);
    CheckFeral(margin, "spent growl at the line");
    CHECK(margin.MortalityAtMs > spent.GrowlReadyAfterMs);

    // A long hold whose damage over time crosses the line and then stops
    // (21.4% down to 20.9%, Break and Double Attack every 15 s, slow healing):
    // once the drift stops the last-chance arm is dropped and the Break tank
    // holds Break again, so the Feral enters Mortality with at most one more
    // Break stack than in the control whose drift stops above the line.
    ReplayConfig armed;
    armed.HealPct = 1.0f;
    armed.StartPct = 21.4f;
    armed.DotStopPct = 20.9f;
    armed.BreakCycleMs = 15000;
    ReplayConfig control = armed;
    control.DotStopPct = 21.1f;
    ReplayResult const longHold = RunBurnReplay(armed);
    ReplayResult const noArm = RunBurnReplay(control);
    CheckFeral(longHold, "long armed hold");
    CheckFeral(noArm, "long hold control");
    if (longHold.FeralBreakStacks > noArm.FeralBreakStacks + 1)
        std::fprintf(stderr, "long hold: feral stacks %d vs control %d\n",
            longHold.FeralBreakStacks, noArm.FeralBreakStacks);
    CHECK(longHold.FeralBreakStacks <= noArm.FeralBreakStacks + 1);
    CHECK(longHold.MortalityAtMs > 30000);
}

int main()
{
    TestBurnTauntExchange();
    TestBurnWindow();
    TestLastChanceHandoff();
    TestHoldCap();
    TestFailedHandoff();
    TestEncounterLatchStore();
    TestBurnReplayFromPostMassacre();
    if (failures)
        std::fprintf(stderr, "%d checks failed\n", failures);
    return failures ? 1 : 0;
}
'''

PROGRAM = PRELUDE + BURN_TESTS


def test_chimaeron_burn_window_and_latches_replay(tmp_path: Path) -> None:
    result = compile_and_run(tmp_path, PROGRAM, "chimaeron_burn")
    assert result.returncode == 0, result.stderr
