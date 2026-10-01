"""Omnotron tank survival (BWD 10N round 4, BotOmnotronTankSurvival.h).

In round 3 at tier-11 gear, 3 of 4 attempts wiped after a tank fell first.
Tanks held constructs with no Survival Instincts, Frenzied Regeneration,
Demoralizing Roar or healer external. These tests pin the decisions the
runtime now submits as ordinary native casts, and the source contract that
the Omnotron submitter reaches them.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_omnotron_strategy import OMNOTRON, PRELUDE, _compile_and_run

HEADER = OMNOTRON / "BotOmnotronTankSurvival.h"
PET_GUARD = OMNOTRON / "BotOmnotronPetShieldGuard.h"
CANDIDATES = OMNOTRON / "BotWorldPopulationMgrOmnotronCandidates.cpp"

SURVIVAL_PRELUDE = PRELUDE + r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronTankSurvival.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronPetShieldGuard.h"

// Electron on the Blood DK (40001), Magmatron on the Feral (40002), 4.5 yd
// from the druid, Electron 7.2 yd from it.
inline Blackboard Engaged(char const* cohort, uint64 now)
{
    Blackboard board = Board(cohort, 10, now);
    board.Summons = { Construct(O::ElectronEntry, 1, 0.0f, 0.0f, G(40001), now + 30000),
        Construct(O::MagmatronEntry, 2, 8.0f, 0.0f, G(40002), now + 75000),
        Inactive(O::ToxitronEntry, 3, -9.0f, -12.0f),
        Inactive(O::ArcanotronEntry, 4, 9.0f, -12.0f) };
    return board;
}

inline ActorSnapshot& PlayerOf(Blackboard& board, uint32 counter)
{
    for (ActorSnapshot& player : board.Players)
        if (player.Guid == G(counter))
            return player;
    return board.Players.front();
}

inline std::vector<O::SurvivalDecision> Decide(Blackboard const& board, uint32 counter,
    bool moving = false)
{
    O::EncounterFacts const facts = O::Observe(board);
    ActorSnapshot const* bot = board.FindActor(G(counter));
    return bot ? O::DecideSurvivalActions(board, facts, *bot, moving)
               : std::vector<O::SurvivalDecision>{};
}

inline bool Has(std::vector<O::SurvivalDecision> const& list, uint32 spell)
{
    for (O::SurvivalDecision const& decision : list)
        if (decision.SpellId == spell)
            return true;
    return false;
}
'''


def test_omnotron_feral_tank_defensives_and_demoralizing_roar(tmp_path: Path) -> None:
    program = SURVIVAL_PRELUDE + r'''
int main()
{
    uint64 const now = 2000000;
    ObjectGuid const magmatron = ObjectGuid(HighGuid::Unit, O::MagmatronEntry, 2u);

    // Healthy Feral holding Magmatron: no defensive, only the roar (neither
    // construct carries a -10% debuff).
    Blackboard healthy = Engaged("feral-healthy", now);
    std::vector<O::SurvivalDecision> fine = Decide(healthy, 40002);
    CHECK(fine.size() == 1 && fine[0].SpellId == 99 && !fine[0].Urgent);
    CHECK(fine[0].Target == G(40002));

    // Scarlet Fever on Electron and a fresh roar on Magmatron: nothing to do.
    Blackboard debuffed = Engaged("feral-debuffed", now);
    debuffed.Summons[0].Auras.push_back({ 81130, G(40001), 1, now + 20000 });
    debuffed.Summons[1].Auras.push_back({ 99, G(40002), 1, now + 20000 });
    CHECK(Decide(debuffed, 40002).empty());
    // A roar about to fall off is refreshed.
    debuffed.Summons[1].Auras.back().ExpiresAtMs = now + 2000;
    CHECK(Has(Decide(debuffed, 40002), 99));
    // A shielded construct never asks for the roar (the offense restriction
    // keeps area spells off it as well).
    Blackboard shielded = Engaged("feral-shielded", now);
    shielded.Summons[0].Auras.push_back({ 81130, G(40001), 1, now + 20000 });
    shielded.Summons[1].Auras.push_back({ 79582, magmatron, 1, now + 10000 });
    CHECK(!Has(Decide(shielded, 40002), 99));
    // A construct out of reach (10 yd plus its bounding radius) does not count.
    Blackboard far = Engaged("feral-far", now);
    far.Summons[1].Auras.push_back({ 99, G(40002), 1, now + 20000 });
    far.Summons[0].Position.X = CX - 12.0f;
    CHECK(!Has(Decide(far, 40002), 99));
    // Only a Feral tank that holds a construct roars.
    CHECK(!Has(Decide(healthy, 40001), 99));
    Blackboard loose = Engaged("feral-loose", now);
    loose.Summons[1].VictimGuid = G(40001);
    CHECK(!Has(Decide(loose, 40002), 99));

    // Round 3 cd3009: the Feral at 30% on Arcanotron. Survival Instincts
    // first, then Barkskin and Frenzied Regeneration, all urgent.
    Blackboard low = debuffed;
    low.Summons[1].Auras.back().ExpiresAtMs = now + 20000;
    PlayerOf(low, 40002).HealthPct = 30.0f;
    std::vector<O::SurvivalDecision> dying = Decide(low, 40002);
    CHECK(dying.size() == 3);
    CHECK(dying.size() == 3 && dying[0].SpellId == 61336 && dying[0].Urgent);
    CHECK(dying.size() == 3 && dying[1].SpellId == 22812 && dying[1].Urgent);
    CHECK(dying.size() == 3 && dying[2].SpellId == 22842 && dying[2].Urgent);
    // 60%: Barkskin only, not urgent.
    PlayerOf(low, 40002).HealthPct = 60.0f;
    std::vector<O::SurvivalDecision> mid = Decide(low, 40002);
    CHECK(mid.size() == 1 && mid[0].SpellId == 22812 && !mid[0].Urgent);
    // An active defensive is not recast. Pain Suppression holds the major
    // cooldown back.
    PlayerOf(low, 40002).HealthPct = 30.0f;
    PlayerOf(low, 40002).Auras.push_back({ 22812, G(40002), 1, now + 8000 });
    PlayerOf(low, 40002).Auras.push_back({ 33206, G(40007), 1, now + 6000 });
    std::vector<O::SurvivalDecision> covered = Decide(low, 40002);
    CHECK(covered.size() == 1 && covered[0].SpellId == 22842);

    // Two constructs on the Feral (the DK died): the major defensive starts at 55%.
    Blackboard doubled = debuffed;
    doubled.Summons[1].Auras.back().ExpiresAtMs = now + 20000;
    doubled.Summons[0].VictimGuid = G(40002);
    PlayerOf(doubled, 40002).HealthPct = 52.0f;
    std::vector<O::SurvivalDecision> both = Decide(doubled, 40002);
    CHECK(both.size() >= 2 && both[0].SpellId == 61336 && both[1].SpellId == 22812);
    PlayerOf(doubled, 40002).HealthPct = 90.0f;
    std::vector<O::SurvivalDecision> early = Decide(doubled, 40002);
    CHECK(early.size() == 1 && early[0].SpellId == 22812);

    // A tank without a construct on it keeps its cooldowns.
    Blackboard idle = Engaged("feral-idle", now);
    idle.Summons[1].VictimGuid = G(40001);
    PlayerOf(idle, 40002).HealthPct = 20.0f;
    CHECK(Decide(idle, 40002).empty());
    // Outside the encounter node nothing applies.
    Blackboard elsewhere = low;
    elsewhere.Route.NodeId = "bwd.omnotron.sentries";
    CHECK(Decide(elsewhere, 40002).empty());
    return failures;
}
'''
    _compile_and_run(tmp_path, program)


def test_omnotron_blood_tank_defensives(tmp_path: Path) -> None:
    program = SURVIVAL_PRELUDE + r'''
int main()
{
    uint64 const now = 3000000;
    Blackboard board = Engaged("blood", now);
    CHECK(Decide(board, 40001).empty());
    PlayerOf(board, 40001).HealthPct = 55.0f;
    std::vector<O::SurvivalDecision> tap = Decide(board, 40001);
    CHECK(tap.size() == 1 && tap[0].SpellId == 48982 && !tap[0].Urgent);
    PlayerOf(board, 40001).HealthPct = 30.0f;
    std::vector<O::SurvivalDecision> low = Decide(board, 40001);
    CHECK(low.size() == 3 && low[0].SpellId == 48792 && low[1].SpellId == 55233
        && low[2].SpellId == 48982 && low[0].Urgent && low[1].Urgent);
    // Icebound Fortitude running: Vampiric Blood and Rune Tap still help.
    PlayerOf(board, 40001).Auras.push_back({ 48792, G(40001), 1, now + 10000 });
    std::vector<O::SurvivalDecision> covered = Decide(board, 40001);
    CHECK(covered.size() == 2 && covered[0].SpellId == 55233);
    return failures;
}
'''
    _compile_and_run(tmp_path, program)


def test_omnotron_healers_hold_the_construct_victim(tmp_path: Path) -> None:
    program = SURVIVAL_PRELUDE + r'''
int main()
{
    uint64 const now = 4000000;
    // Everyone healthy: no tank heal (generic healing keeps the raid).
    Blackboard board = Engaged("heal", now);
    CHECK(Decide(board, 40005).empty());
    CHECK(Decide(board, 40007).empty());

    // The Feral at 80%: the paladin Holy Shocks and Holy Lights him; the
    // priest only shields him.
    PlayerOf(board, 40002).HealthPct = 80.0f;
    std::vector<O::SurvivalDecision> paladin = Decide(board, 40005);
    CHECK(paladin.size() == 2 && paladin[0].SpellId == 20473 && paladin[1].SpellId == 635);
    CHECK(paladin.size() == 2 && paladin[0].Target == G(40002) && !paladin[0].Urgent);
    std::vector<O::SurvivalDecision> priest = Decide(board, 40007);
    CHECK(priest.size() == 1 && priest[0].SpellId == 17 && priest[0].Target == G(40002));
    // Weakened Soul: no shield.
    PlayerOf(board, 40002).Auras.push_back({ 6788, G(40007), 1, now + 12000 });
    CHECK(Decide(board, 40007).empty());

    // The lowest construct victim is chosen: the DK at 40%, the Feral at 80%.
    PlayerOf(board, 40001).HealthPct = 40.0f;
    std::vector<O::SurvivalDecision> urgent = Decide(board, 40005);
    CHECK(!urgent.empty() && urgent[0].Target == G(40001) && urgent[0].Urgent);
    CHECK(urgent.size() == 4 && urgent[0].SpellId == 20473 && urgent[1].SpellId == 19750
        && urgent[2].SpellId == 82326 && urgent[3].SpellId == 635);
    // Moving: instant spells only.
    std::vector<O::SurvivalDecision> walking = Decide(board, 40005, true);
    CHECK(walking.size() == 1 && walking[0].SpellId == 20473);
    // Pain Suppression at 30% unless a major reduction already runs.
    PlayerOf(board, 40001).HealthPct = 30.0f;
    std::vector<O::SurvivalDecision> suppress = Decide(board, 40007);
    CHECK(!suppress.empty() && suppress[0].SpellId == 33206 && suppress[0].Urgent
        && suppress[0].Target == G(40001));
    CHECK(Has(suppress, 17) && Has(suppress, 47540) && Has(suppress, 2061));
    PlayerOf(board, 40001).Auras.push_back({ 48792, G(40001), 1, now + 10000 });
    CHECK(!Has(Decide(board, 40007), 33206));
    // Lay on Hands at 10% without Forbearance.
    PlayerOf(board, 40001).HealthPct = 10.0f;
    CHECK(Decide(board, 40005)[0].SpellId == 633);
    PlayerOf(board, 40001).Auras.push_back({ 25771, G(40005), 1, now + 60000 });
    CHECK(Decide(board, 40005)[0].SpellId == 20473);
    // A victim beyond heal range is not chosen.
    Blackboard far = Engaged("heal-far", now);
    PlayerOf(far, 40002).HealthPct = 30.0f;
    PlayerOf(far, 40005).Position.Y = CY + 60.0f;
    CHECK(Decide(far, 40005).empty());
    // Damage dealers never get these decisions.
    CHECK(Decide(board, 40004).empty());
    return failures;
}
'''
    _compile_and_run(tmp_path, program)


def test_omnotron_submitter_casts_the_first_castable_survival_decision() -> None:
    source = CANDIDATES.read_text(encoding="utf-8")
    assert '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronTankSurvival.h"' in source
    block = source[source.index("O::DecideSurvivalActions(board, facts, *self, moving)"):]
    block = block[: block.index("DecisionKernel.Submit(std::move(survival))")]
    # Spell book, native cooldown, power and movement are checked before a
    # candidate is submitted; the cast is the ordinary native cast intent.
    for guard in ("HasActiveSpell(decision.SpellId)", "GetSpellHistory()->IsReady(info)",
                  "CalcCastTime() > 0", "BotNativeAction::CastSpell{",
                  "ExecuteNativeActionIntent("):
        assert guard in block, guard
    # Only while the adaptive plan owns the encounter node.
    head = source[: source.index("O::DecideSurvivalActions(board, facts, *self, moving)")]
    assert "if (context.AdaptiveOmnotronOwnsNode && Cohort().EncounterSnapshot)" in head
    assert "if (!ownedFacts)\n        return;" in head
    # No invented aura, damage or teleport: the header only names spells.
    header = HEADER.read_text(encoding="utf-8")
    for forbidden in ("AddAura", "CastSpell(", "NearTeleportTo", "DealDamage", "SetHealth"):
        assert forbidden not in header, forbidden
    assert len(header.splitlines()) < 1000 and len(source.splitlines()) < 1000


def test_omnotron_running_felstorm_beside_a_shield_is_cancelled(tmp_path: Path) -> None:
    program = SURVIVAL_PRELUDE + r'''
int main()
{
    uint64 const now = 5000000;
    ObjectGuid const electron = ObjectGuid(HighGuid::Unit, O::ElectronEntry, 1u);
    Blackboard board = Engaged("felstorm", now);
    // Pet 6 yd from Electron (centre), Magmatron 8 yd away.
    Vector3 const pet{ CX + 3.0f, CY + 5.2f, CZ };
    CHECK(!O::FelstormReachesShieldedConstruct(O::Observe(board), pet));
    // Round 3 acb506: Unstable Shield up on Electron.
    board.Summons[0].Auras.push_back({ 79900, electron, 1, now + 10000 });
    CHECK(O::FelstormReachesShieldedConstruct(O::Observe(board), pet));
    // A shield still being cast counts.
    Blackboard casting = Engaged("felstorm-cast", now);
    casting.Summons[0].Cast = CastSnapshot{ 79900, ObjectGuid{}, now, false, false };
    CHECK(O::FelstormReachesShieldedConstruct(O::Observe(casting), pet));
    // Reach: 8 yd whirl plus the construct's bounding radius and 1 yd of travel.
    Vector3 const edge{ CX - 12.4f, CY, CZ };
    Vector3 const beyond{ CX - 12.7f, CY, CZ };
    CHECK(O::FelstormReachesShieldedConstruct(O::Observe(board), edge));
    CHECK(!O::FelstormReachesShieldedConstruct(O::Observe(board), beyond));
    // An inactive construct is not a shield.
    Blackboard inactive = Engaged("felstorm-inactive", now);
    inactive.Summons[2].Auras.push_back({ 80053, ObjectGuid{}, 1, now + 10000 });
    CHECK(!O::FelstormReachesShieldedConstruct(O::Observe(inactive),
        Vector3{ CX - 9.0f, CY - 12.0f, CZ }));
    return failures;
}
'''
    _compile_and_run(tmp_path, program)


def test_omnotron_felstorm_cancel_uses_the_client_pet_cancel_aura_request() -> None:
    source = CANDIDATES.read_text(encoding="utf-8")
    block = source[source.index("A running Felstorm beside a shielded construct"):]
    block = block[: block.index("DecisionKernel.Submit(std::move(cancel))")]
    assert "BotActionArbitration::Resource::Pet" in block
    finder = source[source.index("ObjectGuid OmnotronFelstormBesideShield("):]
    finder = finder[: finder.index("\n}\n")]
    for guard in ("GetEntry() != O::FelguardEntry", "HasAura(O::FelstormAura)",
                  "FelstormReachesShieldedConstruct"):
        assert guard in finder, guard
    helper = source[source.index("bool CancelOmnotronPetFelstorm("):]
    for guard in ("CMSG_PET_CANCEL_AURA", "HandlePetCancelAuraOpcode(request)"):
        assert guard in helper, guard
    assert "RemoveAura" not in block and "RemoveOwnedAura" not in block
    header = PET_GUARD.read_text(encoding="utf-8")
    assert "FelstormAura = 89751" in header and "FelstormRadius = 8.0f" in header


def test_omnotron_survival_submission_skips_unaffordable_and_yields_to_interrupt(
        tmp_path: Path) -> None:
    """Review r4 findings 7 and 8 (FirstSubmittableSurvival)."""
    program = SURVIVAL_PRELUDE + r'''
#include <set>

// A native admission stand-in: spells on cooldown and spells the bot cannot
// pay for are not castable.
struct Admission
{
    std::set<uint32> Cooling;
    std::set<uint32> Unaffordable;
    bool operator()(O::SurvivalDecision const& decision) const
    {
        return !Cooling.count(decision.SpellId) && !Unaffordable.count(decision.SpellId);
    }
};

int main()
{
    uint64 const now = 6000000;
    // The DK at 40% under Electron: the paladin's list is Holy Shock, Flash of
    // Light, Divine Light, Holy Light.
    Blackboard board = Engaged("submit", now);
    PlayerOf(board, 40001).HealthPct = 40.0f;
    std::vector<O::SurvivalDecision> const paladin = Decide(board, 40005);
    CHECK(paladin.size() == 4 && paladin[1].SpellId == 19750);
    // Holy Shock cooling, mana for Holy Light only: Holy Light, not a Flash of
    // Light the native cast would reject.
    Admission poor{ { 20473 }, { 19750, 82326 } };
    O::SurvivalDecision const* chosen = O::FirstSubmittableSurvival(paladin, false, poor);
    CHECK(chosen && chosen->SpellId == 635 && chosen->Target == G(40001));
    // Nothing castable: nothing submitted.
    Admission broke{ { 20473 }, { 19750, 82326, 635 } };
    CHECK(!O::FirstSubmittableSurvival(paladin, false, broke));
    // With mana the first castable one wins.
    CHECK(O::FirstSubmittableSurvival(paladin, false, Admission{ { 20473 }, {} })->SpellId
        == 19750);

    // The Feral at 60% holding Magmatron, assigned to interrupt Arcane
    // Annihilator: nonurgent Barkskin and Demoralizing Roar wait.
    Blackboard feral = Engaged("submit-feral", now);
    PlayerOf(feral, 40002).HealthPct = 60.0f;
    std::vector<O::SurvivalDecision> const upkeep = Decide(feral, 40002);
    CHECK(upkeep.size() == 2 && !upkeep[0].Urgent && !upkeep[1].Urgent);
    CHECK(O::FirstSubmittableSurvival(upkeep, false, Admission{})
        && O::FirstSubmittableSurvival(upkeep, false, Admission{})->SpellId == 22812);
    CHECK(!O::FirstSubmittableSurvival(upkeep, true, Admission{}));
    // At 30% urgent survival still goes first, interrupt or not.
    PlayerOf(feral, 40002).HealthPct = 30.0f;
    std::vector<O::SurvivalDecision> const dying = Decide(feral, 40002);
    O::SurvivalDecision const* urgent = O::FirstSubmittableSurvival(dying, true, Admission{});
    CHECK(urgent && urgent->SpellId == 61336 && urgent->Urgent);
    // Survival Instincts cooling: the next urgent defensive, never the roar.
    urgent = O::FirstSubmittableSurvival(dying, true, Admission{ { 61336 }, {} });
    CHECK(urgent && urgent->Urgent && urgent->SpellId != 99);

    // Blood DK at 55%: Rune Tap is nonurgent and waits for the interrupt.
    PlayerOf(board, 40001).HealthPct = 55.0f;
    std::vector<O::SurvivalDecision> const tap = Decide(board, 40001);
    CHECK(tap.size() == 1 && tap[0].SpellId == 48982);
    CHECK(!O::FirstSubmittableSurvival(tap, true, Admission{}));
    CHECK(O::FirstSubmittableSurvival(tap, false, Admission{}) == &tap[0]);
    return failures;
}
'''
    _compile_and_run(tmp_path, program)


def test_omnotron_submitter_admits_power_and_honours_the_assigned_interrupt() -> None:
    """Review r4 findings 7 and 8: the runtime admission checks power, and the
    assigned interrupter submits only urgent survival."""
    source = CANDIDATES.read_text(encoding="utf-8")
    block = source[source.index("O::DecideSurvivalActions(board, facts, *self, moving)"):]
    block = block[: block.index("DecisionKernel.Submit(std::move(survival))")]
    for guard in ("O::FirstSubmittableSurvival(decisions,",
                  "assignedInterrupt", "HasPowerForSpell(context.Bot, info)",
                  "HasActiveSpell(decision.SpellId)", "GetSpellHistory()->IsReady(info)"):
        assert guard in block, guard
    head = source[: source.index("O::DecideSurvivalActions(board, facts, *self, moving)")]
    assert ("bool const assignedInterrupt = !context.AdaptiveOmnotronInterruptTargetGuid.IsEmpty();"
            in head)
    # Exactly one survival candidate per decision tick.
    assert source.count("DecisionKernel.Submit(std::move(survival))") == 1


def test_omnotron_shield_suppression_cancels_a_running_felstorm() -> None:
    """Review r4 finding 6: suppression (utility 100) owns the Pet lane ahead
    of the standalone cancel (95), so it must end the whirl itself."""
    source = CANDIDATES.read_text(encoding="utf-8")
    helper = source[source.index("bool CancelOmnotronPetFelstorm("):]
    helper = helper[: helper.index("\n}\n")]
    for guard in ("CMSG_PET_CANCEL_AURA", "HandlePetCancelAuraOpcode(request)",
                  "BotEncounter::Omnotron::FelstormAura"):
        assert guard in helper, guard
    suppress = source[source.index("if (context.AdaptiveOmnotronSuppressOffense)"):]
    suppress = suppress[: suppress.index("DecisionKernel.Submit(std::move(suppress))")]
    assert "suppress.Attempt = [this, &context, felstormPet]()" in suppress
    assert "CancelOmnotronPetFelstorm(context.Bot, felstormPet)" in suppress
    # The pet beside a shield is found before suppression is submitted.
    before = source[: source.index("if (context.AdaptiveOmnotronSuppressOffense)")]
    assert "OmnotronFelstormBesideShield(context.Bot, *ownedFacts)" in before
    cancel = source[source.index("A running Felstorm beside a shielded construct"):]
    cancel = cancel[: cancel.index("DecisionKernel.Submit(std::move(cancel))")]
    assert "CancelOmnotronPetFelstorm(context.Bot, petGuid)" in cancel
    assert "RemoveAura" not in source and "RemoveOwnedAura" not in source
