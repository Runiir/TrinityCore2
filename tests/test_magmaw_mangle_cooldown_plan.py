"""Blood tank cooldowns planned around Magmaw's next Mangle (TANK-003).

Kill b3-0dbce440-k1 (Magmaw 10N, actor 30002): the 70% Vampiric Blood row fired
at 50.2 s with Mangle 39.8 s away, and the 35% emergency release spent
Icebound Fortitude at 60.3 s, 29.7 s before Mangle. Bone Shield ran out at
86.2 s, and in the last 6 s Heart Strike x2 and Rune Strike took the runes and
GCDs while Death Strike was rune-gated. The tank met Mangle at 46% health with
nothing up and died at 89.2 s.

These cases replay the resolver's decision for those ticks. They use the
Blood tank rows (live world DB profile 267 v31, read 2026-09-24) plus the
Rune Tap row from 2026_09_24_10, and the native cooldowns from the pinned 4.3.4
DBC. The production comparator (candidatePreferred) and the balance-mode
scoring switch are compiled out of BotWorldPopulationMgrCombatResolver.cpp.
Each case runs with and without the plan.
"""
from __future__ import annotations

import re
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
MAGMAW = BOTS / "Content/Raids/BlackwingDescent/Encounters/Magmaw"
PLAN = MAGMAW / "BotMagmawMangleCooldownPlan.h"
DEFENSIVE = MAGMAW / "BotMagmawMangleDefensive.h"
MODULE = MAGMAW / "BotWorldPopulationMgrMagmawMangleDefensive.cpp"
RESOLVER = BOTS / "BotWorldPopulationMgrCombatResolver.cpp"
RESERVATION = BOTS / "BotWorldPopulationMgrRaidCooldownReservation.h"
RUNE_TAP_SQL = ROOT / "sql/custom/world/2026_09_24_10_blood_rune_tap.sql"
SEAT_HEART_STRIKE_SQL = ROOT / "sql/custom/world/2026_09_23_40_blood_mangle_death_strike_runes.sql"
SEAT_DISEASE_SQL = ROOT / "sql/custom/world/2026_09_23_41_blood_mangle_disease_runes.sql"
SEIZED_HEART_STRIKE_SQL = ROOT / "sql/custom/world/2026_09_24_20_blood_seized_heart_strike.sql"
MANGLE_SEAT = 78412
ICY_TOUCH, PLAGUE_STRIKE = 45477, 45462

BONE_SHIELD, ICEBOUND, VAMPIRIC_BLOOD, RUNE_TAP = 49222, 48792, 55233, 48982
DEATH_STRIKE, HEART_STRIKE, RUNE_STRIKE, BLOOD_TAP, ERW = 49998, 55050, 56815, 45529, 47568

# Live profile 267 v31: spell -> (category, D, H, T, M, S, bucket, sort, max_self_hp).
LIVE_ROWS = {
    BONE_SHIELD: ("Defensive", 0, 0, 0.2, 0.85, 0.85, 1, 20, 0.9),
    ICEBOUND: ("Defensive", 0, 0, 0.1, 1, 1, 1, 25, 0.65),
    VAMPIRIC_BLOOD: ("Defensive", 0, 0.3, 0.1, 0.85, 1, 1, 28, 0.7),
    ERW: ("OffensiveCooldown", 1.1, 0, 2.2, 0, 0, 1, 36, 1.0),
    BLOOD_TAP: ("ResourceGenerator", 1.2, 0, 1.9, 0, 0, 1, 37, 1.0),
    DEATH_STRIKE: ("Mitigation", 0.76, 0.8, 0.75, 0.65, 0.85, 1, 40, 1.0),
    HEART_STRIKE: ("Builder", 1.5, 0, 1.5, 0, 0, 1, 42, 1.0),
    RUNE_STRIKE: ("Spender", 1.45, 0, 1.55, 0, 0, 1, 44, 1.0),
}
# Pinned 4.3.4 DBC cooldowns (asserted in test_magmaw_mangle_defensive.py,
# test_magmaw_mangle_icebound_reservation.py and test_blood_rune_tap.py).
COOLDOWNS = {ICEBOUND: 180000, VAMPIRIC_BLOOD: 60000, BONE_SHIELD: 60000, RUNE_TAP: 30000}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    raise AssertionError(signature)


def _rune_tap_row() -> tuple:
    """The Rune Tap row exactly as the migration inserts it."""
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE bot_rotation_profile (id INTEGER PRIMARY KEY, class_id INTEGER,
            spec_tag TEXT, role TEXT, version INTEGER, source_note TEXT, scope_note TEXT);
        CREATE TABLE bot_rotation_action (id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER, sort_order INTEGER, spell_id INTEGER, category TEXT,
            mechanic_tags TEXT, damage_weight REAL, healing_weight REAL, threat_weight REAL,
            mitigation_weight REAL, survival_weight REAL, priority_bucket INTEGER,
            min_enemies INTEGER, max_enemies INTEGER, max_self_health_pct REAL,
            requires_melee_range INTEGER, target_selector TEXT, movement_directive TEXT,
            auto_attack_mode TEXT, min_range REAL, max_range REAL, maintain_aura_id INTEGER,
            refresh_aura_below_ms INTEGER, min_ready_runes INTEGER, max_ready_runes INTEGER,
            enabled INTEGER);
        INSERT INTO bot_rotation_profile VALUES (267, 6, 'blood_death_knight', 'tank', 31, 'n', 's');
    """)
    db.executescript(text(RUNE_TAP_SQL))
    return db.execute(
        "SELECT category, damage_weight, healing_weight, threat_weight, mitigation_weight, "
        "survival_weight, priority_bucket, sort_order, max_self_health_pct "
        "FROM bot_rotation_action WHERE spell_id = ?", (RUNE_TAP,)).fetchone()


def _candidate_preferred() -> str:
    source = text(RESOLVER)
    start = source.index("    auto candidatePreferred =")
    end = source.index("\n    };", start) + len("\n    };")
    return source[start:end]


def _role_score_switch() -> str:
    source = text(RESOLVER)
    start = source.index("        float roleScore = candidate.Score;")
    end = source.index("        candidate.Score = roleScore;", start)
    return source[start:end]


def _rows_cpp() -> str:
    rows = dict(LIVE_ROWS)
    category, d, h, t, m, s, bucket, sort, max_hp = _rune_tap_row()
    assert category == "defensive"
    rows[RUNE_TAP] = ("Defensive", d, h, t, m, s, bucket, sort, max_hp)
    lines = []
    for spell, (cat, d, h, t, m, s, bucket, sort, max_hp) in sorted(rows.items(), key=lambda r: r[1][7]):
        weights = ", ".join(f"{float(w)!r}f" for w in (d, h, t, m, s))
        lines.append(
            f"    Row({spell}u, BotCombatActionCategory::{cat}, {weights}, "
            f"{bucket}u, {sort}u, {float(max_hp)!r}f),")
    return "\n".join(lines)


PROGRAM = r"""
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMangleCooldownPlan.h"

#include <cassert>
#include <cstring>
#include <set>
#include <string>
#include <vector>

using namespace BotEncounter;
using namespace BotEncounter::MagmawMangleCooldownPlan;
using MagmawMangleDefensive::DefensiveReadiness;
using MagmawMangleDefensive::DefensiveStates;
using MagmawMangleDefensive::SelectDefensive;

enum class BotRoleBalanceMode { PureSurvival, Recovery, BalancedRoleDps, DpsPush, RoleFirst };

struct ActionProfile
{
    unsigned PriorityBucket = 1;
    unsigned SortOrder = 0;
    float DamageWeight = 0, HealingWeight = 0, ThreatWeight = 0, MitigationWeight = 0;
    float SurvivalWeight = 0, ProgressionWeight = 0;
    float MaxSelfHealthPct = 1.0f;
};

// Completes the header's forward declaration with the fields the extracted
// production comparator and scorer read.
struct BotActionCandidate
{
    ActionProfile Profile;
    float Score = 0.0f;
    unsigned ActionId = 0;
    uint32 SpellId = 0;
    BotCombatActionCategory Category = BotCombatActionCategory::Wait;
    std::string RejectReason;
};

static BotActionCandidate Row(uint32 spell, BotCombatActionCategory category, float d, float h,
    float t, float m, float s, unsigned bucket, unsigned sort, float maxHp)
{
    BotActionCandidate row;
    row.SpellId = spell;
    row.ActionId = spell;
    row.Category = category;
    row.Profile.PriorityBucket = bucket;
    row.Profile.SortOrder = sort;
    row.Profile.DamageWeight = d;
    row.Profile.HealingWeight = h;
    row.Profile.ThreatWeight = t;
    row.Profile.MitigationWeight = m;
    row.Profile.SurvivalWeight = s;
    row.Profile.MaxSelfHealthPct = maxHp;
    return row;
}

static std::vector<BotActionCandidate> Rows()
{
    return {
%ROWS%
    };
}

static uint32 CooldownMs(uint32 spell)
{
    switch (spell)
    {
        case %ICEBOUND%: return %ICEBOUND_CD%;
        case %VB%: return %VB_CD%;
        case %BONE%: return %BONE_CD%;
        case %RUNE_TAP%: return %RUNE_TAP_CD%;
        default: return 0;
    }
}

struct Tick
{
    float Health = 1.0f;
    uint32 DueMs = 90000;
    bool InProgress = false;
    // Spells the native preflight accepts this tick (cooldown, runes, GCD).
    std::set<uint32> Valid;
    BotRoleBalanceMode Mode = BotRoleBalanceMode::BalancedRoleDps;
    // Pre-Mangle lead inputs.
    bool Victim = true;
    bool Seized = false;
    uint32 BloodShieldMs = 0;
    bool BonePending = false;
    // Ready runes whose current type is Blood (not Death).
    uint8 BloodRunes = 0;
};

// What Observe computes natively, from the same inputs.
static Plan MakePlan(Tick const& tick, std::vector<BotActionCandidate> const& candidates)
{
    Plan plan;
    plan.Active = true;
    plan.Timer.DueInMs = tick.DueMs;
    plan.Timer.HitInProgress = tick.InProgress || !tick.DueMs || tick.Seized;
    plan.HealthPct = tick.Health;
    plan.IceboundCooldownMs = CooldownMs(IceboundFortitudeSpell);
    plan.VampiricBloodCooldownMs = CooldownMs(VampiricBloodSpell);
    plan.BoneShieldCooldownMs = CooldownMs(BoneShieldSpell);
    for (BotActionCandidate const& candidate : candidates)
        if ((candidate.SpellId == VampiricBloodSpell || candidate.SpellId == RuneTapSpell)
            && candidate.RejectReason.empty())
            plan.ShorterSurvivalCastable = true;
    auto castable = [&candidates](uint32 spell)
    {
        for (BotActionCandidate const& candidate : candidates)
            if (candidate.SpellId == spell && candidate.RejectReason.empty())
                return true;
        return false;
    };
    plan.SeizedHeartStrikeHold = HoldSeizedHeartStrike(tick.Seized,
        castable(DeathStrikeSpell), tick.BloodRunes, castable(RuneTapSpell));
    std::optional<DefensiveWindow> window;
    if (tick.Seized)
        window = DefensiveWindow{ {}, {}, DefensiveTrigger::Mangled, 0 };
    else if (tick.Victim && tick.DueMs <= MagmawMangleDefensive::PreMangleBoneShieldLeadMs)
        window = DefensiveWindow{ {}, {}, DefensiveTrigger::PreMangleLead, tick.DueMs };
    if (!tick.Seized)
        plan.RuneHold = HoldRuneSpenders(window, tick.BloodShieldMs, tick.BonePending);
    return plan;
}

// The resolver loop order for these rows: native preflight, the boss-node
// big-hit reservation (Defensive rows), the Mangle plan, the self-health gate,
// then the production balance-mode score and comparator.
static uint32 Resolve(Tick const& tick, bool withPlan)
{
    std::string role = "tank";
    struct { BotRoleBalanceMode RecommendedBalanceMode; } saturation{ tick.Mode };
%CANDIDATE_PREFERRED%
    std::vector<BotActionCandidate> candidates = Rows();
    for (BotActionCandidate& candidate : candidates)
        if (!tick.Valid.count(candidate.SpellId))
            candidate.RejectReason = "native_preflight";
    Plan const manglePlan = withPlan ? MakePlan(tick, candidates) : Plan{};
    BotRaidCooldownReservation::RouteContext const route{
        true, true, true, false, "boss", "boss", "combat" };
    BotRaidCooldownReservation::BossHitTimer const timer{ true,
        tick.InProgress || !tick.DueMs || tick.Seized };
    BotActionCandidate* best = nullptr;
    for (BotActionCandidate& candidate : candidates)
    {
        if (!candidate.RejectReason.empty())
            continue;
        if (candidate.Category == BotCombatActionCategory::Defensive
            && BotRaidCooldownReservation::BossHitDefensiveReservationReason(route, 90000,
                timer, tick.Health, candidate.Category, CooldownMs(candidate.SpellId)))
            continue;
        if (manglePlan.RejectReason(candidate.SpellId))
            continue;
        if (tick.Health > candidate.Profile.MaxSelfHealthPct)
            continue;
        candidate.Score = candidate.Profile.DamageWeight + candidate.Profile.HealingWeight
            + candidate.Profile.ThreatWeight + candidate.Profile.MitigationWeight
            + candidate.Profile.SurvivalWeight + candidate.Profile.ProgressionWeight
            - float(candidate.Profile.PriorityBucket) * 0.03f;
%ROLE_SCORE%
        candidate.Score = roleScore;
        if (candidatePreferred(candidate, best))
            best = &candidate;
    }
    return best ? best->SpellId : 0;
}

static std::set<uint32> const OffGcd = { IceboundFortitudeSpell, VampiricBloodSpell, RuneTapSpell };

static bool Is(char const* reason, char const* expected)
{
    return reason && std::strcmp(reason, expected) == 0;
}

int main()
{
    constexpr char const* Kept = "raid_boss_big_hit_defensive_kept_for_hit";
    constexpr char const* VbReserved = "magmaw_mangle_vampiric_blood_reserved";
    constexpr char const* LeadHold = "magmaw_mangle_lead_death_strike_hold";
    constexpr char const* SeizedHold = "magmaw_mangle_seized_heart_strike_hold";
    constexpr char const* BoneReserved = "magmaw_mangle_bone_shield_reserved";

    // --- k1 50.2 s: 63% health, Mangle due in 39.8 s, inside a GCD. ----------
    Tick vbTrigger;
    vbTrigger.Health = 0.63f;
    vbTrigger.DueMs = 39800;
    vbTrigger.Valid = OffGcd;
    vbTrigger.Valid.erase(RuneTapSpell);  // no Rune Tap row in the k1 build
    // Unplanned, this is the k1 cast: the 70% row spends Vampiric Blood.
    assert(Resolve(vbTrigger, false) == VampiricBloodSpell);
    // Planned: Vampiric Blood would not be back for the Mangle -> held;
    // Icebound stays reserved by the existing big-hit rule -> wait.
    assert(Resolve(vbTrigger, true) == 0);
    assert(Is(MakePlan(vbTrigger, {}).RejectReason(VampiricBloodSpell), VbReserved));
    // Outside a GCD the rotation is unchanged (no lead, no hold).
    Tick rotation = vbTrigger;
    rotation.Valid = { HeartStrikeSpell, RuneStrikeSpell, IceboundFortitudeSpell, VampiricBloodSpell };
    assert(Resolve(rotation, false) == HeartStrikeSpell);
    assert(Resolve(rotation, true) == HeartStrikeSpell);
    // Mangle more than 61.5 s away: Vampiric Blood is back in time -> allowed.
    Tick early = vbTrigger;
    early.DueMs = 61500;
    assert(Resolve(early, true) == VampiricBloodSpell);
    early.DueMs = 61499;
    assert(Resolve(early, true) == 0);

    // --- k1 60.3 s: 34% health, Mangle due in 29.7 s, IBF ready. ------------
    Tick emergency;
    emergency.Health = 0.34f;
    emergency.DueMs = 29700;
    emergency.Valid = { IceboundFortitudeSpell };  // k1: Vampiric Blood spent at 50.2 s
    // The k1 death: with nothing else, the existing release spends Icebound
    // (genuinely lethal; still the behavior with the plan).
    assert(Resolve(emergency, false) == IceboundFortitudeSpell);
    assert(Resolve(emergency, true) == IceboundFortitudeSpell);
    // With the plan Vampiric Blood survived 50.2 s: it is spent, Icebound kept.
    emergency.Valid = { IceboundFortitudeSpell, VampiricBloodSpell };
    assert(Resolve(emergency, true) == VampiricBloodSpell);
    // No castable option in the candidate list: nothing is kept.
    assert(!MakePlan(emergency, {}).RejectReason(IceboundFortitudeSpell));
    {
        std::vector<BotActionCandidate> candidates = Rows();
        for (BotActionCandidate& candidate : candidates)
            if (!emergency.Valid.count(candidate.SpellId))
                candidate.RejectReason = "native_preflight";
        Plan const plan = MakePlan(emergency, candidates);
        assert(Is(plan.RejectReason(IceboundFortitudeSpell), Kept));
        assert(!plan.RejectReason(VampiricBloodSpell));
    }
    // role_first scores Icebound and Vampiric Blood alike (3.62 before float
    // rounding), so the unplanned pick is a coin toss; the plan keeps Icebound.
    emergency.Mode = BotRoleBalanceMode::RoleFirst;
    assert(Resolve(emergency, true) == VampiricBloodSpell);
    emergency.Mode = BotRoleBalanceMode::PureSurvival;
    assert(Resolve(emergency, true) == VampiricBloodSpell);
    emergency.Mode = BotRoleBalanceMode::BalancedRoleDps;

    // Requested case: exactly 35%, Mangle due in 40 s, Icebound ready.
    Tick at35 = emergency;
    at35.Health = 0.35f;
    at35.DueMs = 40000;
    assert(Resolve(at35, true) == VampiricBloodSpell);
    // Vampiric Blood on cooldown, Rune Tap castable: Rune Tap, Icebound kept.
    at35.Valid = { IceboundFortitudeSpell, RuneTapSpell };
    assert(Resolve(at35, true) == RuneTapSpell);
    // Death Strike castable: it outranks all three.
    at35.Valid = { IceboundFortitudeSpell, VampiricBloodSpell, RuneTapSpell, DeathStrikeSpell };
    assert(Resolve(at35, true) == DeathStrikeSpell);
    // Neither Vampiric Blood nor Rune Tap: Icebound is released.
    at35.Valid = { IceboundFortitudeSpell };
    assert(Resolve(at35, true) == IceboundFortitudeSpell);
    // Just above the release: Icebound is reserved by the existing rule and
    // Vampiric Blood by the plan.
    Tick above = at35;
    above.Health = 0.36f;
    above.Valid = { IceboundFortitudeSpell, VampiricBloodSpell };
    assert(Resolve(above, true) == 0);
    assert(Resolve(above, false) == VampiricBloodSpell);

    // Requested case: Mangle further away than Icebound's cooldown -> allowed.
    // (The native 180 s cooldown exceeds the 95 s Mangle repeat, so a live
    // timer never gets here; the rule is the cooldown, not a constant.)
    Tick far = emergency;
    far.Valid = { IceboundFortitudeSpell, VampiricBloodSpell };
    {
        Plan plan = MakePlan(far, {});
        plan.ShorterSurvivalCastable = true;
        plan.Timer.DueInMs = 181500;
        assert(!plan.RejectReason(IceboundFortitudeSpell));
        plan.Timer.DueInMs = 181499;
        assert(Is(plan.RejectReason(IceboundFortitudeSpell), Kept));
        plan.IceboundCooldownMs = 20000;  // a hypothetical short cooldown
        plan.Timer.DueInMs = 29700;
        assert(!plan.RejectReason(IceboundFortitudeSpell));
    }

    // During the Mangle (sequence, overdue 0 or seized) nothing is held.
    Tick seizedLow = emergency;
    seizedLow.Seized = true;
    assert(Resolve(seizedLow, true) == VampiricBloodSpell);
    seizedLow.Valid = { IceboundFortitudeSpell };
    assert(Resolve(seizedLow, true) == IceboundFortitudeSpell);
    Tick overdue = vbTrigger;
    overdue.DueMs = 0;
    assert(Resolve(overdue, true) == VampiricBloodSpell);

    // --- Pre-cast point (1.5 s): the helper, not the profile, casts. ----------
    {
        auto states = [](bool ibfReady, bool ibfActive, bool vbReady, bool boneCovers)
        {
            return DefensiveStates{ DefensiveReadiness{ IceboundFortitudeSpell, true, ibfReady, ibfActive },
                DefensiveReadiness{ VampiricBloodSpell, true, vbReady, false },
                DefensiveReadiness{ BoneShieldSpell, true, true, boneCovers } };
        };
        DefensiveWindow const precast{ {}, {}, DefensiveTrigger::PreMangleLead, 1500 };
        // Mangle 1: Icebound ready -> Icebound (the surviving b2-fd4ba456-k4).
        assert(SelectDefensive(precast, states(true, false, true, true)) == IceboundFortitudeSpell);
        // Icebound on cooldown (Mangle 2, or spent early) -> Vampiric Blood.
        assert(SelectDefensive(precast, states(false, false, true, true)) == VampiricBloodSpell);
        // Both down -> Bone Shield if it no longer covers.
        assert(SelectDefensive(precast, states(false, false, false, false)) == BoneShieldSpell);
        // The profile row stays held above 35% here, so it cannot double-cast.
        Tick precastTick = vbTrigger;
        precastTick.DueMs = 1500;
        assert(Is(MakePlan(precastTick, {}).RejectReason(VampiricBloodSpell), VbReserved));
    }

    // --- Pre-Mangle lead rune hold (k1 84-90 s): 46% health. ---------------
    Tick lead;
    lead.Health = 0.46f;
    lead.DueMs = 5800;
    lead.Valid = { HeartStrikeSpell, RuneStrikeSpell };  // Death Strike rune-gated
    // Unplanned: Heart Strike takes the Blood/Death rune and the GCD (k1).
    assert(Resolve(lead, false) == HeartStrikeSpell);
    // Planned: Heart Strike and Rune Strike wait for Death Strike.
    assert(Resolve(lead, true) == 0);
    assert(Is(MakePlan(lead, {}).RejectReason(HeartStrikeSpell), LeadHold));
    assert(Is(MakePlan(lead, {}).RejectReason(RuneStrikeSpell), LeadHold));
    assert(!MakePlan(lead, {}).RejectReason(DeathStrikeSpell));
    assert(!MakePlan(lead, {}).RejectReason(45477) && !MakePlan(lead, {}).RejectReason(45462));
    // Runes back: Death Strike lands.
    lead.Valid.insert(DeathStrikeSpell);
    assert(Resolve(lead, true) == DeathStrikeSpell);
    // Its Blood Shield (10 s) lasts to the seize: the hold ends.
    lead.Valid.erase(DeathStrikeSpell);
    lead.DueMs = 4300;
    lead.BloodShieldMs = 10000;
    assert(Resolve(lead, true) == HeartStrikeSpell);
    // An older Blood Shield that expires before the seize does not end it.
    lead.BloodShieldMs = 3000;
    assert(Resolve(lead, true) == 0);
    lead.BloodShieldMs = 4300;
    assert(Resolve(lead, true) == HeartStrikeSpell);
    // Bone Shield below 3 charges with its cooldown ready keeps the hold.
    lead.BonePending = true;
    assert(Resolve(lead, true) == 0);
    lead.BonePending = false;
    // Below 60% Rune Tap still fires in the hold (off the GCD).
    lead.BloodShieldMs = 0;
    lead.Valid = { HeartStrikeSpell, RuneStrikeSpell, RuneTapSpell };
    assert(Resolve(lead, true) == RuneTapSpell);
    // The lead hold ends at the seize, never opens outside the 6 s lead, and
    // only for Magmaw's victim.  Seized, only a spare Blood rune may pay
    // Heart Strike (the seized cases below).
    Tick seized = lead;
    seized.Valid = { HeartStrikeSpell, RuneStrikeSpell };
    seized.Seized = true;
    seized.BloodRunes = 1;
    assert(Resolve(seized, true) == HeartStrikeSpell);
    assert(!MakePlan(seized, {}).RuneHold);
    Tick before = seized;
    before.Seized = false;
    before.DueMs = 6001;
    assert(Resolve(before, true) == HeartStrikeSpell);
    before.DueMs = 6000;
    assert(Resolve(before, true) == 0);
    before.Victim = false;
    assert(Resolve(before, true) == HeartStrikeSpell);

    // --- Seized by Mangle (2c0ed2d8-k1 89.8-100.8 s): Heart Strike. ---------
    // Death Strike rune-gated (fewer than 2 ready runes), a ready Blood rune,
    // Rune Tap on cooldown (cast at 91.8 s): Heart Strike takes the Blood
    // rune, which Death Strike (Frost + Unholy) could never use.
    Tick grip;
    grip.Health = 0.70f;
    grip.DueMs = 0;
    grip.Seized = true;
    grip.BloodRunes = 1;
    grip.Valid = { HeartStrikeSpell, RuneStrikeSpell };
    assert(Resolve(grip, true) == HeartStrikeSpell);
    assert(!MakePlan(grip, {}).RejectReason(HeartStrikeSpell));
    // Rune Strike alone still goes out.
    grip.Valid = { RuneStrikeSpell };
    assert(Resolve(grip, true) == RuneStrikeSpell);
    grip.Valid = { HeartStrikeSpell };
    assert(Resolve(grip, true) == HeartStrikeSpell);
    // Death Strike castable: Heart Strike stays held; Death Strike is cast.
    grip.Valid = { HeartStrikeSpell, RuneStrikeSpell, DeathStrikeSpell };
    assert(Resolve(grip, true) == DeathStrikeSpell);
    {
        std::vector<BotActionCandidate> candidates = Rows();
        for (BotActionCandidate& candidate : candidates)
            if (!grip.Valid.count(candidate.SpellId))
                candidate.RejectReason = "native_preflight";
        assert(Is(MakePlan(grip, candidates).RejectReason(HeartStrikeSpell), SeizedHold));
        assert(!MakePlan(grip, candidates).RejectReason(RuneStrikeSpell));
        assert(!MakePlan(grip, candidates).RejectReason(DeathStrikeSpell));
    }
    grip.Valid = { HeartStrikeSpell, DeathStrikeSpell };
    assert(Resolve(grip, true) == DeathStrikeSpell);
    // Only a Death rune ready (bundle1-b8a539b): Heart Strike's native
    // preflight passes on it, but the rune is Death Strike's -> held.
    grip.BloodRunes = 0;
    grip.Valid = { HeartStrikeSpell, RuneStrikeSpell };
    assert(Resolve(grip, true) == RuneStrikeSpell);
    assert(Is(MakePlan(grip, {}).RejectReason(HeartStrikeSpell), SeizedHold));
    grip.Valid = { HeartStrikeSpell };
    assert(Resolve(grip, true) == 0);
    // Rune Tap castable (off cooldown, a rune ready): the one Blood rune is
    // kept for it (91.8 s: 55% health -> Rune Tap, as the kill cast it).
    grip.BloodRunes = 1;
    grip.Health = 0.55f;
    grip.Valid = { HeartStrikeSpell, RuneStrikeSpell, RuneTapSpell };
    assert(Resolve(grip, true) == RuneTapSpell);
    // Above Rune Tap's 60%: the Blood rune still waits for it.
    grip.Health = 0.70f;
    assert(Resolve(grip, true) == RuneStrikeSpell);
    grip.Valid = { HeartStrikeSpell, RuneTapSpell };
    assert(Resolve(grip, true) == 0);
    // Two ready Blood runes: one for Rune Tap, one for Heart Strike.
    grip.BloodRunes = 2;
    assert(Resolve(grip, true) == HeartStrikeSpell);
    grip.Health = 0.55f;
    grip.Valid = { HeartStrikeSpell, RuneStrikeSpell, RuneTapSpell };
    assert(Resolve(grip, true) == RuneTapSpell);  // outranks at 60% or less
    // The rule itself.
    assert(!HoldSeizedHeartStrike(false, true, 0, true));
    assert(!HoldSeizedHeartStrike(true, false, 1, false));
    assert(HoldSeizedHeartStrike(true, true, 2, false));
    assert(HoldSeizedHeartStrike(true, false, 0, false));
    assert(HoldSeizedHeartStrike(true, false, 1, true));
    assert(!HoldSeizedHeartStrike(true, false, 2, true));
    // The seized hold needs no Mangle timer: the seizure aura proves it.
    {
        Plan untimed;
        untimed.SeizedHeartStrikeHold = true;
        assert(!untimed.Active);
        assert(Is(untimed.RejectReason(HeartStrikeSpell), SeizedHold));
        assert(!untimed.RejectReason(RuneStrikeSpell));
    }
    // Not seized: Heart Strike is only the lead's business.
    Tick unseized = grip;
    unseized.Seized = false;
    unseized.DueMs = 30000;
    unseized.BloodRunes = 0;
    unseized.Valid = { HeartStrikeSpell, RuneStrikeSpell };
    assert(Resolve(unseized, true) == HeartStrikeSpell);

    // --- Bone Shield reserved for the helper's pre-cast (2c0ed2d8-k1). -------
    // 54.3 s: no Bone Shield (the row only fires once the aura is gone), 64%
    // health, Mangle 35.5 s away.  Unplanned, the ordinary row casts it and
    // it is on cooldown at the 89.8 s seize.  Planned, it waits.
    Tick bone;
    bone.Health = 0.64f;
    bone.DueMs = 35500;
    bone.Valid = { BoneShieldSpell };
    assert(Resolve(bone, false) == BoneShieldSpell);
    assert(Resolve(bone, true) == 0);
    assert(Is(MakePlan(bone, {}).RejectReason(BoneShieldSpell), BoneReserved));
    // The GCD and the Unholy rune go to the rotation instead.
    bone.Valid = { BoneShieldSpell, HeartStrikeSpell, RuneStrikeSpell };
    assert(Resolve(bone, true) == HeartStrikeSpell);
    bone.Valid = { BoneShieldSpell };
    // Requested: held at Mangle - 60 s.  1 min cooldown + the 6 s lead: back
    // for the pre-cast from 66 s out.
    bone.DueMs = 60000;
    assert(Resolve(bone, true) == 0);
    bone.DueMs = 65999;
    assert(Resolve(bone, true) == 0);
    bone.DueMs = 66000;
    assert(Resolve(bone, true) == BoneShieldSpell);
    bone.DueMs = 90000;  // the pull: the first Mangle is 90 s out
    assert(Resolve(bone, true) == BoneShieldSpell);
    // Emergency release at 35%, as for Vampiric Blood.
    bone.DueMs = 35500;
    bone.Health = 0.35f;
    assert(Resolve(bone, true) == BoneShieldSpell);
    bone.Health = 0.36f;
    assert(Resolve(bone, true) == 0);
    // During the Mangle (seized, sequence or overdue) nothing is held.
    Tick boneSeized = bone;
    boneSeized.Seized = true;
    assert(Resolve(boneSeized, true) == BoneShieldSpell);
    Tick boneOverdue = bone;
    boneOverdue.DueMs = 0;
    assert(Resolve(boneOverdue, true) == BoneShieldSpell);
    // Inside the lead the profile row stays held; the helper casts it.
    bone.DueMs = 6000;
    assert(Is(MakePlan(bone, {}).RejectReason(BoneShieldSpell), BoneReserved));
    {
        auto states = [](bool ibfReady, bool boneReady, bool boneCovers)
        {
            return DefensiveStates{ DefensiveReadiness{ IceboundFortitudeSpell, true, ibfReady, false },
                DefensiveReadiness{ VampiricBloodSpell, true, true, false },
                DefensiveReadiness{ BoneShieldSpell, true, boneReady, boneCovers } };
        };
        DefensiveWindow const boneLead{ {}, {}, DefensiveTrigger::PreMangleLead, 6000 };
        // Pre-cast allowed: at 6 s Bone Shield is the only defensive in its
        // lead (Icebound and Vampiric Blood wait for 1.5 s).
        assert(SelectDefensive(boneLead, states(true, true, false)) == BoneShieldSpell);
        // The kill as played: recast at 54.3 s, cooldown at the seize.
        assert(!SelectDefensive(boneLead, states(true, false, false)));
        // Refreshed (6 charges) -> nothing more; Icebound at 1.5 s.
        assert(!SelectDefensive(boneLead, states(true, true, true)));
        DefensiveWindow const precast{ {}, {}, DefensiveTrigger::PreMangleLead, 1500 };
        assert(SelectDefensive(precast, states(true, true, true)) == IceboundFortitudeSpell);
        // Pending Bone Shield keeps Heart Strike and Rune Strike off its
        // Unholy rune and the GCD in the lead.
        assert(HoldRuneSpenders(boneLead, 10000, true));
        assert(!HoldRuneSpenders(boneLead, 10000, false));
    }
    // An inactive plan (no timer) never holds Bone Shield.
    {
        Plan untimed;
        untimed.BoneShieldCooldownMs = 60000;
        untimed.HealthPct = 0.64f;
        assert(!untimed.RejectReason(BoneShieldSpell));
    }

    // --- Rune Tap below 60% ------------------------------------------------
    Tick tap;
    tap.Health = 0.59f;
    tap.DueMs = 80000;
    tap.Valid = { HeartStrikeSpell, RuneStrikeSpell, RuneTapSpell, BloodTapSpellForTest };
    assert(Resolve(tap, true) == RuneTapSpell);
    tap.Valid.insert(DeathStrikeSpell);
    assert(Resolve(tap, true) == DeathStrikeSpell);
    tap.Valid.erase(DeathStrikeSpell);
    tap.Health = 0.61f;
    assert(Resolve(tap, true) == BloodTapSpellForTest);
    tap.Valid.erase(BloodTapSpellForTest);
    assert(Resolve(tap, true) == HeartStrikeSpell);

    // --- An inactive plan (not the tank, no board, not Magmaw) rejects nothing.
    Plan idle;
    assert(!idle.SeizedHeartStrikeHold && !idle.RuneHold);
    for (uint32 spell : { IceboundFortitudeSpell, VampiricBloodSpell, HeartStrikeSpell,
            RuneStrikeSpell, RuneTapSpell, DeathStrikeSpell, BoneShieldSpell })
        assert(!idle.RejectReason(spell));
    return 0;
}
"""


def test_replayed_resolver_decisions(tmp_path: Path) -> None:
    program = (PROGRAM
               .replace("%ROWS%", _rows_cpp())
               .replace("%CANDIDATE_PREFERRED%", _candidate_preferred())
               .replace("%ROLE_SCORE%", _role_score_switch())
               .replace("%ICEBOUND%", str(ICEBOUND)).replace("%ICEBOUND_CD%", str(COOLDOWNS[ICEBOUND]))
               .replace("%VB%", str(VAMPIRIC_BLOOD)).replace("%VB_CD%", str(COOLDOWNS[VAMPIRIC_BLOOD]))
               .replace("%BONE%", str(BONE_SHIELD)).replace("%BONE_CD%", str(COOLDOWNS[BONE_SHIELD]))
               .replace("%RUNE_TAP%", str(RUNE_TAP)).replace("%RUNE_TAP_CD%", str(COOLDOWNS[RUNE_TAP]))
               .replace("BloodTapSpellForTest", f"{BLOOD_TAP}u"))
    assert not re.search(r"%[A-Z_]+%", program)
    source = tmp_path / "mangle_cooldown_plan.cpp"
    binary = tmp_path / "mangle_cooldown_plan"
    source.write_text(program, encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-variable",
         "-I", str(ROOT / "src/server/game"),
         "-I", str(ROOT / "src/server/game/Entities/Object"),
         "-I", str(ROOT / "src/server/shared"),
         "-I", str(ROOT / "src/common"),
         str(source), "-o", str(binary)],
        check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_extracted_resolver_blocks_are_the_production_ones() -> None:
    switch = _role_score_switch()
    assert "case BotRoleBalanceMode::BalancedRoleDps:" in switch
    assert ("roleScore += candidate.Profile.DamageWeight * 0.55f + candidate.Profile.HealingWeight * 0.25f"
            " + candidate.Profile.ThreatWeight * 0.25f;") in switch
    assert "if (role == \"tank\")" in switch
    assert "return !current || candidate.Profile.PriorityBucket < current->Profile.PriorityBucket" in _candidate_preferred()
    candidates = text(BOTS / "BotClassSpecActionProfileCandidates.cpp")
    assert ("candidate.Score = spell.DamageWeight + spell.HealingWeight + spell.ThreatWeight\n"
            "            + spell.MitigationWeight + spell.SurvivalWeight + spell.ProgressionWeight\n"
            "            - float(spell.PriorityBucket) * 0.03f;") in candidates


def test_resolver_applies_the_plan_after_the_boss_reservation() -> None:
    resolver = text(RESOLVER)
    assert ('#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/'
            'BotMagmawMangleCooldownPlan.h"') in resolver
    observe = ("    BotEncounter::MagmawMangleCooldownPlan::Plan const manglePlan =\n"
               "        BotEncounter::MagmawMangleCooldownPlan::Observe(bot, role,\n"
               "            Cohort().EncounterSnapshot.get(), candidates, excludedSpellId,\n"
               "            policyExcludedSpellId);\n"
               "    for (BotActionCandidate& candidate : candidates)\n")
    assert observe in resolver
    loop = resolver[resolver.index(observe):]
    reserve = loop.index("BossDefensiveReservationReason(bot, candidate.ResolvedSpellId)")
    hold = loop.index("manglePlan.RejectReason(candidate.SpellId)")
    health = loop.index('candidate.RejectReason = "self_health_gate";')
    score = loop.index("float roleScore = candidate.Score;")
    assert reserve < hold < health < score
    assert re.search(r"if \(candidate\.RejectReason\.empty\(\)\)\s*"
                     r"if \(char const\* mangleHold = manglePlan\.RejectReason\(candidate\.SpellId\)\)\s*"
                     r"\{\s*candidate\.RejectReason = mangleHold;\s*continue;\s*\}", loop)
    for path in (RESOLVER, MODULE, PLAN, DEFENSIVE, RESERVATION):
        assert len(text(path).splitlines()) < 1000, path


def test_native_observation_matches_the_replayed_plan() -> None:
    module = text(MODULE)
    observe = function_body(module, "Plan Observe(Player const* bot, std::string_view role, Blackboard const* board,")
    assert 'if (!bot || role != "tank")\n        return plan;' in observe
    # The seized Heart Strike hold is set from the tank's own Mangle aura and
    # native runes before the board or the Mangle timer is consulted.
    seized_hold = observe.index("plan.SeizedHeartStrikeHold = HoldSeizedHeartStrike(seized,")
    assert observe.index("bool const seized = NativelyMangled(bot);") < seized_hold
    assert seized_hold < observe.index("if (!board)\n        return plan;")
    assert seized_hold < observe.index("MagmawMangleDefensive::ObserveMangleTimer(*board, botGuid)")
    assert "castable(DeathStrikeSpell)" in observe
    assert "BotBloodDecisionObservation::ObserveReadyRunes(bot).Blood" in observe
    assert "castable(RuneTapSpell)" in observe
    assert "plan.BoneShieldCooldownMs = NativeCooldownMs(BoneShieldSpell);" in observe
    assert "plan.ShorterSurvivalCastable = castable(VampiricBloodSpell)\n        || castable(RuneTapSpell);" in observe
    assert '#include "Bots/BotBloodDecisionObservation.h"' in module
    assert "plan.Timer.HitInProgress = plan.Timer.HitInProgress || seized;" in observe
    assert "BotWorldPopulationMgrNativeHelpers::UnitHealthPct(bot)" in observe
    assert "NativeCooldownMs(IceboundFortitudeSpell)" in observe
    assert "NativeCooldownMs(VampiricBloodSpell)" in observe
    # Castable = the profile candidate passed the native preflight and is not
    # suppressed for this resolution.
    castable = function_body(module, "bool CandidateCastable(")
    assert "candidate.RejectReason.empty()" in castable
    assert "spellId == excludedSpellId || spellId == policyExcludedSpellId" in castable
    assert "CandidateCastable(candidates, spellId, excludedSpellId,\n            policyExcludedSpellId)" in observe
    # The rune hold reads Blood Shield and Bone Shield natively, never once seized.
    assert "if (seized)\n        return plan;" in observe
    assert "MagmawMangleDefensive::ObserveMangleDefensiveWindow(*board, botGuid)" in observe
    assert "NativelyKnownAndReady(bot, BoneShieldSpell)" in observe
    assert "!NativeBoneShieldCovers(bot)" in observe
    assert "NativeBloodShieldRemainingMs(bot)" in observe
    cooldown = function_body(module, "uint32 NativeCooldownMs(uint32 spellId)")
    assert "std::max(spellInfo->RecoveryTime, spellInfo->CategoryRecoveryTime)" in cooldown
    shield = function_body(module, "uint32 NativeBloodShieldRemainingMs(Player const* bot)")
    assert "bot->GetAura(BloodShieldAbsorbSpell)" in shield and "GetDuration()" in shield
    # Blood Shield is the Death Strike heal's native absorb.
    dk = text(ROOT / "src/server/scripts/Spells/spell_dk.cpp")
    assert "SPELL_DK_BLOOD_SHIELD_ABSORB                = 77535," in dk
    heal = dk[dk.index("class spell_dk_death_strike_heal"):]
    heal = heal[:heal.index("RegisterSpellScript") if "RegisterSpellScript" in heal[:3000] else 3000]
    assert "target->CastSpell(target, SPELL_DK_BLOOD_SHIELD_ABSORB" in heal
    plan = text(PLAN)
    assert "constexpr uint32 BloodShieldAbsorbSpell = 77535;" in plan
    assert "constexpr uint32 RuneTapSpell = 48982;" in plan
    assert "constexpr uint32 HeartStrikeSpell = 55050;" in plan
    assert "constexpr uint32 DeathStrikeSpell = 49998;" in plan
    assert "constexpr uint32 RuneStrikeSpell = 56815;" in plan
    # Lawful: the plan only rejects rows.
    for forbidden in ("CastSpell", "ResetCooldown", "SetHealth", "ModifyHealth", "AddAura"):
        assert forbidden not in plan
        assert forbidden not in observe


def test_ready_blood_rune_never_pays_death_strike_natively() -> None:
    """A spare Blood rune is Heart Strike's without costing Death Strike."""
    spell = text(ROOT / "src/server/game/Spells/Spell.cpp")
    take = function_body(spell, "void Spell::TakeRunePower(SpellMissInfo hitInfo)")
    exact = take.index("runeCost[AsUnderlyingType(rune)] > 0")
    death = take.index("rune == RuneType::Death")
    # Exact rune type first, Death runes only for what is left.
    assert exact < death
    assert "runeCost[AsUnderlyingType(RuneType::Death)] = runeCost[AsUnderlyingType(RuneType::Blood)]" in take
    # The candidate preflight: a Blood rune only reduces the Blood cost.
    candidates = text(BOTS / "BotClassSpecActionProfileCandidates.cpp")
    power = candidates[candidates.index("bool HasEnoughPowerForProfileSpell"):]
    power = power[:power.index("\n}\n")]
    assert re.search(r"case RuneType::Blood:\s*if \(required\[0\] > 0\)\s*--required\[0\];", power)
    # Ready Blood runes = ready runes whose current type is Blood.
    observation = text(BOTS / "BotBloodDecisionObservation.h")
    ready = observation[observation.index("inline ReadyRunes ObserveReadyRunes"):]
    ready = ready[:ready.index("inline char const* RuneTypeName")]
    assert "IsRuneReady(actor->GetRuneCooldown(rune))" in ready
    assert "case RuneType::Blood: ++observation.Blood; break;" in ready
    # The seizure auras the hold reads (seat 78412 among them).
    assert "89773, 91912, 94616, 94617, 78412," in text(DEFENSIVE)


def _seat_database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, spec_tag TEXT NOT NULL,
            role TEXT NOT NULL, version INTEGER NOT NULL, source_note TEXT NOT NULL,
            scope_note TEXT NOT NULL);
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL, spell_id INTEGER NOT NULL,
            required_self_aura INTEGER NOT NULL DEFAULT 0,
            forbidden_self_aura INTEGER NOT NULL DEFAULT 0);
    """)
    db.executemany("INSERT INTO bot_rotation_profile VALUES (?,?,?,?,?,?,?)", [
        (267, 6, "blood_death_knight", "tank", 25, "n", "s"),
        (283, 6, "frost_death_knight", "dps", 11, "n", "s"),
    ])
    db.executemany("INSERT INTO bot_rotation_action VALUES (?,?,?,?,?)", [
        (2049, 267, DEATH_STRIKE, 0, 0),
        (2874, 267, HEART_STRIKE, 0, 0),
        (2050, 267, ICY_TOUCH, 0, 0),
        (2051, 267, PLAGUE_STRIKE, 0, 0),
        (9001, 283, HEART_STRIKE, 0, 0),
    ])
    db.executescript(_forward(SEAT_HEART_STRIKE_SQL))
    db.executescript(_forward(SEAT_DISEASE_SQL))
    return db


def _forward(path: Path) -> str:
    return text(path).split("-- BEGIN REVERSE MIGRATION")[0]


def _reverse(path: Path) -> str:
    block = text(path).split("-- BEGIN REVERSE MIGRATION")[1].split("-- END REVERSE MIGRATION")[0]
    return "\n".join(line[3:] for line in block.splitlines() if line.startswith("-- "))


def _seat_rows(db: sqlite3.Connection) -> list:
    return db.execute("SELECT id, required_self_aura, forbidden_self_aura "
                      "FROM bot_rotation_action ORDER BY id").fetchall()


def test_seized_heart_strike_migration_replays_scoped_idempotent_and_reversible() -> None:
    db = _seat_database()
    applied = _seat_rows(db)
    assert applied == [(2049, 0, 0), (2050, 0, MANGLE_SEAT), (2051, 0, MANGLE_SEAT),
                       (2874, 0, MANGLE_SEAT), (9001, 0, 0)]
    assert db.execute("SELECT version FROM bot_rotation_profile WHERE id=267").fetchone() == (28,)

    db.executescript(_forward(SEIZED_HEART_STRIKE_SQL))
    after = _seat_rows(db)
    # Only Blood tank Heart Strike loses the seat aura; Icy Touch and Plague
    # Strike keep it (Death Strike's Frost and Unholy runes).
    assert after == [(2049, 0, 0), (2050, 0, MANGLE_SEAT), (2051, 0, MANGLE_SEAT),
                     (2874, 0, 0), (9001, 0, 0)]
    blood = db.execute("SELECT version, source_note FROM bot_rotation_profile WHERE id=267").fetchone()
    assert blood == (33, "phase9_blood_seized_heart_strike_2026_09_24")
    assert db.execute("SELECT version FROM bot_rotation_profile WHERE id=283").fetchone() == (11,)

    db.executescript(_forward(SEIZED_HEART_STRIKE_SQL))
    assert _seat_rows(db) == after
    db.execute("UPDATE bot_rotation_profile SET version = 40 WHERE id = 267")
    db.executescript(_forward(SEIZED_HEART_STRIKE_SQL))
    assert db.execute("SELECT version FROM bot_rotation_profile WHERE id=267").fetchone() == (40,)

    db.executescript(_reverse(SEIZED_HEART_STRIKE_SQL))
    assert _seat_rows(db) == applied
    # The applied migrations are untouched and still sort before this one.
    names = sorted(path.name for path in SEIZED_HEART_STRIKE_SQL.parent.glob("2026_09_2*.sql"))
    assert names.index(SEAT_HEART_STRIKE_SQL.name) < names.index(SEIZED_HEART_STRIKE_SQL.name)
    assert names.index(SEAT_DISEASE_SQL.name) < names.index(SEIZED_HEART_STRIKE_SQL.name)
    assert "SET `forbidden_self_aura` = 78412" in text(SEAT_HEART_STRIKE_SQL)
    assert "AND `spell_id` = 55050" in text(SEIZED_HEART_STRIKE_SQL)
