"""Round 4: the dragons' victims live on the floor (BotNefarianDragonTankCare.h).

BWD 10N round 3 (tier-11 phase gear, label blackwing_descent_10n-r03-a3864fcf6d)
wiped in phase 1 in all four attempts: the Feral Onyxia tank died first
(Onyxia melee at +32-38 s, once her Shadowflame Breath at +12 s), then the
untanked dragons killed the raid. The Disc priest cast almost only instants
(1.9-4.2k HPS): nothing in the plan healed the dragon tanks, the tanks' own
defensives ran only on the pillars, and the formation walk (Mechanic 200,
claiming the cast lanes) re-planned with every step of a tank.

The compiled program drives the real strategy on the canonical 10N board:
- the Feral and the Blood DK use their defensives when a dragon attacks them
  (on a breath at them, or hurt), in phase 1 and phase 3;
- each healer heals the dragons' victims first, instant while walking, with a
  cast-time heal while standing, above the formation walk;
- a caster or healer that already stands on a safe spot serving its targets
  near its wanted spot keeps it (no walk).
"""

from __future__ import annotations

from pathlib import Path

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run

ROOT = Path(__file__).resolve().parents[1]
CARE = ROOT / ("src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
               "Nefarian/BotNefarianDragonTankCare.h")

PROGRAM = PRELUDE + r'''
using BotActionArbitration::Priority;

static BotNativeAction::Candidate const* Find(AdaptiveNefarianPlan const& plan, uint32 spellId)
{
    for (BotNativeAction::Candidate const& action : plan.Actions)
        if (auto const* cast = std::get_if<BotNativeAction::CastSpell>(&action.Action);
            cast && cast->SpellId == spellId)
            return &action;
    return nullptr;
}

static ObjectGuid TargetOf(BotNativeAction::Candidate const* action)
{
    auto const* cast = action ? std::get_if<BotNativeAction::CastSpell>(&action->Action) : nullptr;
    return cast ? cast->Target : ObjectGuid();
}

static ActorSnapshot& OnyxiaOf(Blackboard& board) { return board.Summons[0]; }
static ActorSnapshot& NefarianOf(Blackboard& board) { return board.Summons[1]; }

static void Breathe(ActorSnapshot& dragon, ObjectGuid at)
{
    CastSnapshot cast;
    cast.SpellId = 77826;
    cast.TargetGuid = at;
    dragon.Cast = cast;
}

static NativeFacts NotReady(ObjectGuid actor, std::initializer_list<uint32> spells)
{
    NativeFacts facts;
    for (uint32 spell : spells)
        facts.Readiness.push_back({ actor, spell, false, true });
    return facts;
}

// Known and ready, but the bot cannot pay the mana now; `cooling` spells are
// on cooldown.
static NativeFacts Unaffordable(ObjectGuid actor, std::initializer_list<uint32> spells,
    std::initializer_list<uint32> cooling = {})
{
    NativeFacts facts;
    for (uint32 spell : spells)
        facts.Readiness.push_back({ actor, spell, true, true, false });
    for (uint32 spell : cooling)
        facts.Readiness.push_back({ actor, spell, false, true });
    return facts;
}

static void TestFeralOnOnyxia()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, false);
    CHECK(ObserveEncounter(board).CurrentPhase == Phase::OnyxiaOnly, "phase 1, Onyxia on the Feral");
    AdaptiveNefarianPlan plan = strategy.Propose(board, Bot(2), "tank");
    CHECK(!Find(plan, SpellBarkskin) && !Find(plan, SpellSurvivalInstincts),
        "a healthy Feral spends nothing");

    Breathe(OnyxiaOf(board), Bot(2));
    plan = strategy.Propose(board, Bot(2), "tank");
    BotNativeAction::Candidate const* bark = Find(plan, SpellBarkskin);
    CHECK(bark && TargetOf(bark) == Bot(2) && bark->ActionPriority == Priority::Survival,
        "Barkskin on Onyxia's breath at the Feral");
    OnyxiaOf(board).Cast.reset();

    FindPlayer(board, 2).HealthPct = 30.0f;
    plan = strategy.Propose(board, Bot(2), "tank");
    CHECK(Find(plan, SpellSurvivalInstincts) && Find(plan, SpellBarkskin)
        && Find(plan, SpellFrenziedRegeneration), "a Feral at 30% uses all three");
    AddAura(FindPlayer(board, 2), SpellBarkskin);
    NativeFacts const facts = NotReady(Bot(2), { SpellSurvivalInstincts });
    plan = strategy.Propose(board, Bot(2), "tank", &facts);
    CHECK(!Find(plan, SpellBarkskin) && !Find(plan, SpellSurvivalInstincts)
        && Find(plan, SpellFrenziedRegeneration),
        "never a defensive already up or on cooldown");

    // Not attacked: no defensive (the Blood DK waits for Nefarian).
    FindPlayer(board, 1).HealthPct = 30.0f;
    plan = strategy.Propose(board, Bot(1), "tank");
    CHECK(!Find(plan, SpellIceboundFortitude) && !Find(plan, SpellVampiricBlood),
        "a tank no dragon attacks spends nothing");
}

static void TestBloodOnNefarian()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, true);
    CHECK(ObserveEncounter(board).CurrentPhase == Phase::BothDragons, "both dragons");
    Breathe(NefarianOf(board), Bot(1));
    AdaptiveNefarianPlan plan = strategy.Propose(board, Bot(1), "tank");
    CHECK(Find(plan, SpellAntiMagicShell), "Anti-Magic Shell on Nefarian's breath at the DK");
    NefarianOf(board).Cast.reset();
    FindPlayer(board, 1).HealthPct = 45.0f;
    plan = strategy.Propose(board, Bot(1), "tank");
    CHECK(Find(plan, SpellVampiricBlood) && Find(plan, SpellRuneTap)
        && !Find(plan, SpellIceboundFortitude), "Vampiric Blood and Rune Tap at 45%");
    BotNativeAction::Candidate const* strike = Find(plan, SpellDeathStrike);
    CHECK(strike && TargetOf(strike) == NefarianOf(board).Guid,
        "Death Strike on the dragon it holds");
    FindPlayer(board, 1).HealthPct = 30.0f;
    plan = strategy.Propose(board, Bot(1), "tank");
    CHECK(Find(plan, SpellIceboundFortitude), "Icebound Fortitude at 30%");
}

static void TestDisciplineOnTheTank()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, false);
    AdaptiveNefarianPlan plan = strategy.Propose(board, Bot(7), "healer");
    BotNativeAction::Candidate const* shield = Find(plan, SpellPowerWordShield);
    CHECK(shield && TargetOf(shield) == Bot(2) && shield->ActionPriority == Priority::Mechanic
        && shield->Utility > 200.0f, "the Disc shields Onyxia's tank above the formation walk");

    AddAura(FindPlayer(board, 2), SpellWeakenedSoul);
    FindPlayer(board, 2).HealthPct = 60.0f;
    plan = strategy.Propose(board, Bot(7), "healer");
    CHECK(Find(plan, SpellPenance) && TargetOf(Find(plan, SpellPenance)) == Bot(2),
        "Penance on the hurt tank");
    NativeFacts moving;
    moving.Motion.push_back({ Bot(7), true, FindPlayer(board, 7).Position });
    plan = strategy.Propose(board, Bot(7), "healer", &moving);
    CHECK(!Find(plan, SpellPenance) && !Find(plan, SpellFlashHeal) && !Find(plan, SpellGreaterHeal),
        "no cast-time heal while it walks");

    FindPlayer(board, 2).HealthPct = 25.0f;
    plan = strategy.Propose(board, Bot(7), "healer");
    BotNativeAction::Candidate const* suppression = Find(plan, SpellPainSuppression);
    CHECK(suppression && suppression->ActionPriority == Priority::Survival,
        "Pain Suppression at 25%");
    NativeFacts used = NotReady(Bot(7), { SpellPainSuppression });
    plan = strategy.Propose(board, Bot(7), "healer", &used);
    CHECK(Find(plan, SpellFlashHeal) && Find(plan, SpellFlashHeal)->ActionPriority == Priority::Survival,
        "then Flash Heal, urgent under 50%");

    // Review r4 finding 8: the victim is under Weakened Soul and the priest
    // cannot afford Flash Heal, but Penance is ready and affordable: Penance,
    // not a Flash Heal the native cast would reject.
    FindPlayer(board, 2).HealthPct = 45.0f;
    NativeFacts poor = Unaffordable(Bot(7), { SpellFlashHeal }, { SpellPainSuppression });
    plan = strategy.Propose(board, Bot(7), "healer", &poor);
    CHECK(!Find(plan, SpellFlashHeal), "no unaffordable Flash Heal");
    CHECK(Find(plan, SpellPenance) && TargetOf(Find(plan, SpellPenance)) == Bot(2)
        && Find(plan, SpellPenance)->ActionPriority == Priority::Survival,
        "affordable Penance on the shielded-out tank instead");
    // Shielded (Power Word: Shield up, no Weakened Soul) is the same.
    Blackboard shielded = board;
    FindPlayer(shielded, 2).Auras.clear();
    AddAura(FindPlayer(shielded, 2), SpellPowerWordShield);
    plan = strategy.Propose(shielded, Bot(7), "healer", &poor);
    CHECK(!Find(plan, SpellFlashHeal) && Find(plan, SpellPenance),
        "Penance on the shielded tank when Flash Heal is unaffordable");
    FindPlayer(board, 2).HealthPct = 25.0f;

    // Out of reach or sight: the shared triage keeps it.
    NativeFacts hidden;
    hidden.OutOfSight.push_back(Bot(2));
    plan = strategy.Propose(board, Bot(7), "healer", &hidden);
    CHECK(!Find(plan, SpellFlashHeal) && !Find(plan, SpellPainSuppression), "no heal out of sight");
    FindPlayer(board, 2).Position = LocalToWorld({ -45.0f, 0.0f }, PlatformFrame::FloorLocalZ,
        PlatformFrame::RaisedOriginZ);
    plan = strategy.Propose(board, Bot(7), "healer");
    CHECK(!Find(plan, SpellPainSuppression), "no heal out of range");
}

static void TestHolyPaladinOnTheTank()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, true);
    // Nefarian on the DK at 80%, Onyxia on the Feral at 95%: the lowest first.
    FindPlayer(board, 1).HealthPct = 80.0f;
    FindPlayer(board, 1).Position = LocalToWorld({ -10.0f, 0.0f }, PlatformFrame::FloorLocalZ,
        PlatformFrame::RaisedOriginZ);
    FindPlayer(board, 2).HealthPct = 95.0f;
    AdaptiveNefarianPlan plan = strategy.Propose(board, Bot(5), "healer");
    CHECK(TargetOf(Find(plan, SpellHolyShock)) == Bot(1), "Holy Shock on the lower dragon tank");
    NativeFacts shock = NotReady(Bot(5), { SpellHolyShock });
    plan = strategy.Propose(board, Bot(5), "healer", &shock);
    CHECK(Find(plan, SpellHolyLight), "Holy Light while Holy Shock recovers");
    FindPlayer(board, 1).HealthPct = 35.0f;
    plan = strategy.Propose(board, Bot(5), "healer", &shock);
    CHECK(Find(plan, SpellFlashOfLight), "Flash of Light under 40%");
    // Review r4 finding 8: Holy Shock cooling, mana for Holy Light but not
    // for Flash of Light or Divine Light: Holy Light.
    NativeFacts poor = Unaffordable(Bot(5), { SpellFlashOfLight, SpellDivineLight },
        { SpellHolyShock });
    plan = strategy.Propose(board, Bot(5), "healer", &poor);
    CHECK(!Find(plan, SpellFlashOfLight) && !Find(plan, SpellDivineLight),
        "no unaffordable Flash of Light or Divine Light");
    CHECK(Find(plan, SpellHolyLight) && TargetOf(Find(plan, SpellHolyLight)) == Bot(1),
        "affordable Holy Light on the dragon tank");
    FindPlayer(board, 1).HealthPct = 10.0f;
    plan = strategy.Propose(board, Bot(5), "healer");
    CHECK(Find(plan, SpellLayOnHands), "Lay on Hands under 15%");
    AddAura(FindPlayer(board, 1), SpellForbearance);
    plan = strategy.Propose(board, Bot(5), "healer");
    CHECK(!Find(plan, SpellLayOnHands), "never under Forbearance");
}

static void TestPhaseThreeAndPlatform()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = PlatformBoard(PlatformFrame::LoweredOriginZ);
    FindPlayer(board, 1).HealthPct = 30.0f;
    AdaptiveNefarianPlan plan = strategy.Propose(board, Bot(1), "tank");
    CHECK(!Find(plan, SpellIceboundFortitude), "no floor care on the pillars");
}

static void TestFormationKeepsItsSpot()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, false);
    AdaptiveNefarianPlan first = strategy.Propose(board, Bot(7), "healer");
    CHECK(first.MovementSurface && first.MovementSurface->Purpose == MovePurpose::Formation,
        "the healer has a formation spot");
    if (!first.MovementSurface)
        return;
    LocalPoint const spot = first.MovementSurface->Local;
    std::vector<LocalPoint> const sight = first.MovementSurface->Sight;
    // A nearby spot that is safe and serves the same targets.
    bool placed = false;
    for (float bearing = 0.0f; bearing < 360.0f && !placed; bearing += 30.0f)
    {
        LocalPoint const near = Offset(spot, DegToRad(bearing), 5.0f);
        FindPlayer(board, 7).Position = LocalToWorld(near, FloorLocalZAt(near),
            PlatformFrame::RaisedOriginZ);
        MovementContext const context{ board, ObserveEncounter(board),
            BuildNefarianDutyPlan(board), BuildArenaLayout(BuildNefarianDutyPlan(board)),
            FindPlayer(board, 7), nullptr };
        if (OnPlatformFloor(context) && FloorPointSafe(context, near, false)
            && SpotServes(near, sight))
        {
            placed = true;
            AdaptiveNefarianPlan const again = strategy.Propose(board, Bot(7), "healer");
            CHECK(!again.Movement, "a healer that serves from 5 yd away does not walk");
            CHECK(again.MovementSurface && Distance(again.MovementSurface->Local, near) < 0.1f,
                "its goal is where it stands");
        }
    }
    CHECK(placed, "a serving spot 5 yd from the formation spot exists");
    // Far from the wanted spot it still walks back.
    LocalPoint const far = Offset(spot, AngleOf(spot) + Pi, 16.0f);
    FindPlayer(board, 7).Position = LocalToWorld(far, FloorLocalZAt(far),
        PlatformFrame::RaisedOriginZ);
    AdaptiveNefarianPlan const back = strategy.Propose(board, Bot(7), "healer");
    CHECK(back.MovementSurface && Distance(back.MovementSurface->Local, far) > 5.0f,
        "16 yd away it walks back toward its spot");
}

int main()
{
    TestFeralOnOnyxia();
    TestBloodOnNefarian();
    TestDisciplineOnTheTank();
    TestHolyPaladinOnTheTank();
    TestPhaseThreeAndPlatform();
    TestFormationKeepsItsSpot();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_dragon_tank_care(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM)


def test_dragon_tank_care_under_sanitizers(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM, sanitize=True)


def test_care_spells_are_observed() -> None:
    observer = (CARE.parent / "BotNefarianNativeObserver.h").read_text(encoding="utf-8")
    assert "DragonTankCareSpellsFor(player.ClassSpec)" in observer
    assert CARE.read_text(encoding="utf-8").count("\n") < 1000
