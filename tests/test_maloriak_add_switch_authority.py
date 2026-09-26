"""Maloriak's 30% add switch at the native edge (user tactic 2026-09-26).

From 30% every damage dealer leaves Maloriak for the Aberrations until the
chambers are empty; the Blood DK main tank alone stays on him. In the r05
holds, with only the target cleared, Maloriak still took 62-73k DPS: casts in
flight, the Greater Fire Elemental, a Doomguard, the Felguard, a Tentacle of
the Old Ones and DoT ticks. A route-authority hook applies the restriction
after the adaptive reset every tick (as Omnotron's), holds offensive
cooldowns and guardian summons for phase two, stops a cast already running
on the boss and sends the pet back. One Arcane Storm interrupt or taunt on
the boss stays allowed through the SingleCastAllowance shared with Omnotron.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
MALORIAK = BOTS / "Content/Raids/BlackwingDescent/Encounters/Maloriak"
OMNOTRON = BOTS / "Content/Raids/BlackwingDescent/Encounters/Omnotron"
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]

PROGRAM = r'''
#include "Bots/BotEncounterCooldownHold.h"
#include "Bots/BotEncounterOffenseRestriction.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakAddSwitch.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronOffenseAuthority.h"

#include <chrono>
#include <cstdio>
#include <optional>
#include <thread>
#include <type_traits>

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

namespace M = BotEncounter::Maloriak;
namespace O = BotEncounter::Omnotron;
namespace R = BotEncounterOffense;
namespace H = BotEncounterCooldownHold;
using BotRaidCooldownReservation::CandidateContext;

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); ++failures; } } while (0)

static bool Protected(uint64 owner, uint32 entry, ObjectGuid guid)
{
    return BotRaidAreaAuthority::IsProtectedEncounterTarget(owner, entry, 0, guid.GetRawValue());
}

int main()
{
    // Omnotron's restriction types are the shared ones: one implementation.
    static_assert(std::is_same_v<O::SingleCastAllowance, R::SingleCastAllowance>);
    static_assert(std::is_same_v<O::OffenseRestriction, R::OffenseRestriction>);

    ObjectGuid const boss(HighGuid::Unit, M::BossEntry, uint32(69));
    ObjectGuid const aberration(HighGuid::Unit, M::AberrationEntry, uint32(70));
    uint64 const holder = ObjectGuid(HighGuid::Player, uint32(30404)).GetRawValue();
    uint64 const bystander = ObjectGuid(HighGuid::Player, uint32(30408)).GetRawValue();

    // One tick: the adaptive route authority clears the restriction, then the
    // hook re-applies it, whatever the kernel resolves afterwards.
    BotRaidAreaAuthority::SetCurrentEncounterRestrictions(holder, {}, {});
    CHECK(!Protected(holder, M::BossEntry, boss));
    R::ApplyOffenseRestriction(holder, M::AddSwitchRestriction());
    R::ApplyOffenseRestriction(bystander, M::AddSwitchRestriction());
    CHECK(Protected(holder, M::BossEntry, boss));
    CHECK(!Protected(holder, M::AberrationEntry, aberration));  // adds stay open
    CHECK(BotRaidAreaAuthority::HasProtectedEncounterEntries(holder));  // area spells beside him refused

    // The one interrupt, purge or taunt on the boss.
    CHECK(M::AddSwitchAllowanceApplies(true, M::BossEntry));
    CHECK(!M::AddSwitchAllowanceApplies(false, M::BossEntry));
    CHECK(!M::AddSwitchAllowanceApplies(true, M::AberrationEntry));
    {
        std::optional<R::SingleCastAllowance> allowance;
        allowance.emplace(holder, M::AddSwitchRestriction(), boss);
        CHECK(allowance->Widened());
        CHECK(!Protected(holder, M::BossEntry, boss));
        CHECK(Protected(bystander, M::BossEntry, boss));  // other bots keep it
        R::SingleCastAllowance empty(holder, M::AddSwitchRestriction(), ObjectGuid());
        CHECK(!empty.Widened());
    }
    // Restored right after the cast (review M6: a destructor that does not
    // restore leaves the boss open to every offense path of the bot).
    CHECK(Protected(holder, M::BossEntry, boss));
    CHECK(Protected(bystander, M::BossEntry, boss));

    // Re-review item 1: a running cast is stopped when hostile and reaching
    // the boss, whatever its explicit target: a self-cast Hellfire beside him
    // (explicit target the caster, area over him), a ground Blizzard, a
    // Fireball at him; never a heal, never a cast that does not reach him.
    CHECK(M::AddSwitchStopsCast(false, false, true));   // Hellfire / Blizzard over him
    CHECK(M::AddSwitchStopsCast(false, true, false));   // aimed at him (auto-repeat too)
    CHECK(!M::AddSwitchStopsCast(true, false, true));   // a heal beside him
    CHECK(!M::AddSwitchStopsCast(true, true, false));
    CHECK(!M::AddSwitchStopsCast(false, false, false)); // an Aberration away from him

    // Guardian area sparing (review item 4): a leased flag the switch hook
    // renews; the shaman elemental script skips Fire Nova / Fire Shield while
    // a unit restricted for its shaman is in their radius.
    {
        CHECK(!R::IsGuardianAreaSparing(holder));
        R::SetGuardianAreaSparing(holder, true, 60000);
        CHECK(R::IsGuardianAreaSparing(holder) && !R::IsGuardianAreaSparing(bystander));
        R::SetGuardianAreaSparing(holder, false);
        CHECK(!R::IsGuardianAreaSparing(holder));
        R::SetGuardianAreaSparing(holder, true, 1);
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        CHECK(!R::IsGuardianAreaSparing(holder) && R::GuardianAreaSparingLeases.empty());
        R::SetGuardianAreaSparing(0, true);
        CHECK(R::GuardianAreaSparingLeases.empty());
    }

    // The Greater Fire Elemental attacking an allowed Aberration beside the
    // boss: Fire Nova (10 yd around the elemental) or Fire Shield would reach
    // him, so it is skipped; on an Aberration kited 25 yd away it is cast.
    {
        R::AreaPoint const bossAt{ -105.8f, -455.0f, 3.5f };
        R::AreaPoint const elementalBeside{ -112.0f, -455.0f, 0.0f };
        R::AreaPoint const addBeside{ -110.0f, -455.0f, 0.0f };
        CHECK(R::AreaReachesRestricted({ elementalBeside, addBeside }, 10.0f, { bossAt }));
        R::AreaPoint const elementalKite{ -131.0f, -455.0f, 0.0f };
        R::AreaPoint const addKite{ -133.0f, -453.0f, 0.0f };
        CHECK(!R::AreaReachesRestricted({ elementalKite, addKite }, 10.0f, { bossAt }));
        CHECK(!R::AreaReachesRestricted({ elementalBeside }, 0.0f, { bossAt }));
        CHECK(!R::AreaReachesRestricted({ elementalBeside }, 10.0f, {}));
        // The boss's combat reach counts: 13 yd away with 3.5 yd reach.
        CHECK(R::AreaReachesRestricted({ { -118.8f, -455.0f, 0.0f } }, 10.0f, { bossAt }));
    }

    // Offensive cooldowns wait for phase two: the rows the r05 roster casts.
    {
        CandidateContext const fireElemental{ BotCombatActionCategory::OffensiveCooldown,
            "fire_elemental_totem,opener,long_cooldown,wowsims_66843" };
        CandidateContext const doomguard{ BotCombatActionCategory::OffensiveCooldown,
            "summon_doomguard,guardian,pinned_apl" };
        CandidateContext const mirrorImage{ BotCombatActionCategory::OffensiveCooldown,
            "mirror_image,opener,threat_reduction" };
        CandidateContext const avengingWrath{ BotCombatActionCategory::OffensiveCooldown, "burst" };
        CandidateContext const potion{ BotCombatActionCategory::UseItem, "combat_potion,volcanic_potion" };
        CandidateContext const heroism{ BotCombatActionCategory::OffensiveCooldown, "heroism,raid_lust" };
        CandidateContext const inquisition{ BotCombatActionCategory::OffensiveCooldown,
            "inquisition,raid_reservation_exempt" };
        CandidateContext const iceboundFortitude{ BotCombatActionCategory::Defensive, "major_defensive" };
        CandidateContext const deathStrike{ BotCombatActionCategory::Builder, "self_heal" };
        CandidateContext const healthstone{ BotCombatActionCategory::UseItem, "health_potion,survival" };
        CHECK(std::string(H::HoldReason(fireElemental)) == "encounter_hold_offensive_guardian_reserved");
        CHECK(std::string(H::HoldReason(doomguard)) == "encounter_hold_offensive_guardian_reserved");
        CHECK(std::string(H::HoldReason(mirrorImage)) == "encounter_hold_offensive_cooldown_reserved");
        CHECK(std::string(H::HoldReason(avengingWrath)) == "encounter_hold_offensive_cooldown_reserved");
        CHECK(std::string(H::HoldReason(potion)) == "encounter_hold_combat_potion_reserved");
        CHECK(std::string(H::HoldReason(heroism)) == "encounter_hold_bloodlust_reserved");
        CHECK(!H::HoldReason(inquisition));
        CHECK(!H::HoldReason(iceboundFortitude));
        CHECK(!H::HoldReason(deathStrike));
        CHECK(!H::HoldReason(healthstone));

        // Only a bot whose hold is live, only while its lease runs.
        CHECK(!H::ReservationReason(holder, fireElemental));
        H::Set(holder, true, 60000);
        CHECK(H::ReservationReason(holder, fireElemental));
        CHECK(!H::ReservationReason(holder, iceboundFortitude));
        CHECK(!H::ReservationReason(bystander, fireElemental));
        H::Set(holder, false);
        CHECK(!H::ReservationReason(holder, fireElemental) && H::Leases.empty());
        H::Set(holder, true, 1);
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        CHECK(!H::IsHeld(holder) && H::Leases.empty());
        H::Set(0, true);
        CHECK(H::Leases.empty());
    }

    BotRaidAreaAuthority::SetCurrentEncounterRestrictions(holder, {}, {});
    BotRaidAreaAuthority::SetCurrentEncounterRestrictions(bystander, {}, {});
    CHECK(!Protected(holder, M::BossEntry, boss));
    std::printf("ok\n");
    return failures ? 1 : 0;
}
'''


def test_add_switch_authority_replay(tmp_path: Path) -> None:
    source = tmp_path / "add_switch_authority.cpp"
    binary = tmp_path / "add_switch_authority"
    source.write_text(PROGRAM, encoding="utf-8")
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
    assert result.stdout.strip() == "ok"


def test_route_authority_hook_runs_after_the_reset_before_resolution() -> None:
    header = (BOTS / "BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    assert "    void SubmitMaloriakRouteAuthority(BotUpdateContext& context);\n" in header
    fallback = (BOTS / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text(encoding="utf-8")
    reset = fallback.index("ConfigureValidationRouteCombatAuthority(context.Bot);")
    hook = fallback.index("SubmitMaloriakRouteAuthority(context);")
    assert reset < hook < fallback.index("auto runRoute = [this, &context, routeAttempt, routeOwnerReason,")
    # With the route observers and Omnotron's route authority, after the
    # Magmaw parasite contract.
    assert fallback.index("{contract.ParasiteEntry, contract.ParasiteAltEntry}, allowedGuids);") < hook
    assert hook < fallback.index("SubmitAdaptiveOmnotronRouteAuthority(context);")
    assert fallback.count("SubmitMaloriakRouteAuthority(") == 1
    # The kernel resolves only after every submission, the hook included.
    decision = (BOTS / "BotWorldPopulationMgrUpdateBotDecision.cpp").read_text(encoding="utf-8")
    assert decision.index("SubmitValidationKernelFallbackCandidates(context);") < decision.index(
        "context.State.DecisionKernel.Resolve();")


def test_switch_latch_is_published_and_read_by_every_bot() -> None:
    """Review P1/P2: one effective, latched and capped switch state."""
    blackboard = (BOTS / "BotWorldPopulationMgrEncounterBlackboard.cpp").read_text(encoding="utf-8")
    assert '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakLatches.h"' in blackboard
    chimaeron = blackboard.index("BotEncounter::Chimaeron::UpdateEncounterLatches(*snapshot,")
    maloriak = blackboard.index("BotEncounter::Maloriak::UpdateEncounterLatches(*snapshot,")
    assert chimaeron < maloriak < blackboard.index("Cohort().EncounterSnapshot = std::move(snapshot);")
    preparation = (BOTS / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text(encoding="utf-8")
    call = preparation[preparation.index("maloriakStrategy.Propose(*Cohort().EncounterSnapshot,"):]
    assert "Cohort().EncounterLatches ? &Cohort().EncounterLatches->View()" in call[:300]


def test_elemental_area_spells_spare_the_switch_boss() -> None:
    """Review item 4: the Greater Fire Elemental belongs to the totem, so the
    controlled-unit gates never see the shaman; its script checks its area
    spells while the switch spares guardian areas (Maloriak only)."""
    shaman = (ROOT / "src/server/scripts/Pet/pet_shaman.cpp").read_text(encoding="utf-8")
    gate = shaman[shaman.index("bool ShamanAreaCastBlocked(Creature* elemental, uint32 spellId)"):]
    gate = gate[:gate.index("\n}\n")]
    for token in ("BotEncounterOffense::IsGuardianAreaSparing(ownerGuid)",
                  "IsCurrentEncounterRestrictedEntry(ownerGuid,", "IsProtectedEncounterTarget(ownerGuid,",
                  "elemental->GetVictim()", "effect.CalcRadius(elemental, index)",
                  "BotEncounterOffense::AreaReachesRestricted(centers, radius, restricted)"):
        assert token in gate, token
    assert "if (!ShamanAreaCastBlocked(me, SPELL_SHAMAN_FIRENOVA))\n                                DoCastVictim(SPELL_SHAMAN_FIRENOVA);" in shaman
    assert "if (!ShamanAreaCastBlocked(me, SPELL_SHAMAN_FIRESHIELD))\n                                DoCastVictim(SPELL_SHAMAN_FIRESHIELD);" in shaman
    shared = (BOTS / "BotEncounterOffenseRestriction.h").read_text(encoding="utf-8")
    assert "inline void SetGuardianAreaSparing(uint64 ownerGuid, bool sparing," in shared
    setters = [path for path in (ROOT / "src").rglob("*.cpp")
               if "SetGuardianAreaSparing(" in path.read_text(errors="replace")]
    assert [path.name for path in setters] == ["BotWorldPopulationMgrMaloriakCandidates.cpp"]


def test_omnotron_uses_the_shared_single_cast_allowance() -> None:
    shared = (BOTS / "BotEncounterOffenseRestriction.h").read_text(encoding="utf-8")
    assert "class SingleCastAllowance" in shared
    assert "BotRaidAreaAuthority::SetCurrentEncounterRestrictions(ownerGuid," in shared
    omnotron = (OMNOTRON / "BotOmnotronOffenseAuthority.h").read_text(encoding="utf-8")
    assert '#include "Bots/BotEncounterOffenseRestriction.h"' in omnotron
    assert "class SingleCastAllowance" not in omnotron
    assert "using BotEncounterOffense::SingleCastAllowance;" in omnotron
    module = (MALORIAK / "BotWorldPopulationMgrMaloriakCandidates.cpp").read_text(encoding="utf-8")
    assert "BotEncounterOffense::SingleCastAllowance" in module
    assert "class PushHoldAllowance" not in module


def test_cooldown_hold_gates_both_profile_resolvers() -> None:
    for name in ("BotWorldPopulationMgrCombatResolverAdmission.cpp", "BotWorldPopulationMgrCombatSpell.cpp"):
        source = (BOTS / name).read_text(encoding="utf-8")
        assert '#include "Bots/BotEncounterCooldownHold.h"' in source, name
        reservation = source.index("BotRaidCooldownReservation::ReservationReason(")
        hold = source.index("BotEncounterCooldownHold::ReservationReason(\n", reservation)
        assert "bot->GetGUID().GetRawValue()," in source[hold:hold + 200], name
        assert "candidate.RejectReason = holdReason;\n" in source[hold:hold + 400], name
        assert len(source.splitlines()) < 1000, name


def test_restricted_boss_stops_pets_guardians_and_controlled_melee() -> None:
    """The hook relies on the native authority for everything the bot
    controls; pin the checks it relies on."""
    server = ROOT / "src/server"
    pet_ai = (server / "game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
    assert "return ProtectedEncounterTarget(me->GetCharmerOrOwner(), me->GetVictim());" in pet_ai
    assert "if (!ProtectedEncounterTarget(owner, ownerVictim))" in pet_ai
    unit_ai = (server / "game/AI/CoreAI/UnitAI.cpp").read_text(encoding="utf-8")
    assert unit_ai.count("RaidControlledOffenseRejected(me,") >= 5
    unit = (server / "game/Entities/Unit/Unit.cpp").read_text(encoding="utf-8")
    assert unit.count("if (RaidControlledUnitOffenseRejected(this, victim))") == 2
    assert "InterruptSpell(CURRENT_AUTOREPEAT_SPELL, true, true);" in unit
    shaman = (server / "scripts/Pet/pet_shaman.cpp").read_text(encoding="utf-8")
    assert "!ShamanAuthorityAllows(owner, elemental->GetVictim())" in shaman
    warlock = (server / "scripts/Pet/pet_warlock.cpp").read_text(encoding="utf-8")
    assert "return !creature || !BotRaidAreaAuthority::IsProtectedEncounterTarget(ownerGuid," in warlock


def test_add_switch_sources_stay_small() -> None:
    for path in (MALORIAK / "BotWorldPopulationMgrMaloriakCandidates.cpp",
                 MALORIAK / "BotAdaptiveMaloriakStrategy.h",
                 MALORIAK / "BotMaloriakAddSwitch.h",
                 MALORIAK / "BotMaloriakAddControl.h",
                 MALORIAK / "BotMaloriakLatches.h",
                 BOTS / "BotEncounterOffenseRestriction.h",
                 BOTS / "BotEncounterCooldownHold.h",
                 OMNOTRON / "BotOmnotronOffenseAuthority.h"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path.name
