"""Phase 2 survival of the healerless pillar (2 tanks, 2 healers, 6 DPS).

Two healers cover two of the three pillars; the pillar tops are 62.5-70 yards
apart (beyond every 40-yard heal), so the third team lives on its own. This
module is a resource-limited Monte Carlo model of that team through phase 2,
recorded in experiments/configs/cata_raid_encounters/blackwing_descent/
nefarian_phase_two_survival_v1.json and re-run here with the same seeds. The
test checks the recorded numbers are what the model gives (a regression shows
as a changed risk), not that the risk is small: the risk is the finding.

Model (every number sourced or stated as an assumption):
- Shadowflame Barrage (78621): cast every 2.5 s from 2.5 s after the lift-off
  (EVENT_SHADOWFLAME_BARRAGE, boss_nefarians_end.cpp), a 2 s cast, then 4
  random living players of the 10 (SpellMgr target cap 4 in 10N) are hit when
  the missile arrives at 30 yd/s, 16,199-19,800 shadow each (4.4.2 client
  row, 10N). In phase 2 Nefarian holds NefarianElevatorLiftOffPosition
  (boss_nefarians_end.cpp: the arena centre, z 35.63), 40.5 yards across and
  32.6 above a pillar top (the lowered top, z about 3.06): 52 yards, 1.73 s of
  flight.
- Magma: the team floats from 5.5 s after the platform starts down and hops at
  about 13.9 s: 8 ticks of 5000 + 250 k (81114/81118).
- Prototypes: 1,627,290 health each (10N). Ranged damage starts when they are
  ready, 6.7 s after the platform starts down (from the magma), melee after
  the hop (15 s). Phase 2 ends when the last one dies; the Barrage stops then.
  Per-member single-target DPS (assumed, T11 10N, conservative): Survival
  hunter 20k, Fire mage 22k, Assassination rogue 22k, Retribution 18k,
  Demonology 20k, Elemental 20k (only while not healing), Blood DK tank 10k,
  Feral tank 8k, healers 0.
- The off-healer (DecideOffHeal): Healing Surge on the lowest reachable
  teammate under the strategy's threshold (read from BotNefarianTactics.h),
  1.5 s cast (SpellCastTimes 16) landing at completion, one cast per 1.5 s
  (GCD), 27% of the 23,430 level-85 base mana per cast (SpellPower 317) from an
  80,000 pool with 100 mana/s regeneration (assumed), heal 4,803 +-6.65%
  (SpellScaling, level 85) plus 0.483 of 4,500 spell power (assumed), 15% crits
  at 200%. It cannot cast while walking to the foot, swimming to its station
  or hopping (before 4 s, 6.4-8.4 s, 13.3-15 s): a cast starts only when it
  completes before the next of those moves (it is delayed, never cut short).
  Blast Nova interrupts are not modelled: the strategy interrupts before it
  heals, so the healing here is an upper bound on that account.
- Preparation, realised with 80% probability each: a pre-ascent Power Word:
  Shield (12,000 absorb, conservative) and a Flash of Light top-up (+12,000).
- Starting health 80-100% of maximum (after the phase 1 burn, assumed).
  Maximum health (assumed, T11 10N raid-buffed): Blood DK 220k, Feral 230k,
  DPS 135-150k. The Blood DK heals itself for a conservative 3,000 per second
  (Death Strike). The healed pillars are not tracked.
This is not a native estimate: the reviewer's sensitivity table (recorded in
the data file) spans roughly an order of magnitude. The live run decides the
healerless pillar's viability.
Outcome: the probability that a member of the healerless team dies before
phase 2 ends, the mean phase length, and the median first death.
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_phase_two_survival_v1.json"
TACTICS = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianTactics.h"
CONTRACT = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_v1.json"

PROTOTYPE = 1_627_290
BARRAGE = (16_199.0, 19_800.0)
BARRAGE_CAST = 2.0
MISSILE_SPEED = 30.0
LIFT_OFF_HEIGHT = 35.63 - 3.06
PILLAR_RADIUS = 40.5
HEAL_BASE = 4_803.0
HEAL_VARIANCE = 0.0665
HEAL_CRIT = 2.0
SURGE_COST = 0.27 * 23_430
MANA_POOL = 80_000.0
MANA_REGEN = 100.0
DK_SELF_HEAL = 3_000.0
SEEDS = 600


def threshold() -> float:
    text = TACTICS.read_text(encoding="utf-8")
    return float(re.search(r"constexpr float OffHealThresholdPct = ([0-9.]+)f;", text).group(1)) / 100.0


# name, maximum health, DPS, melee, role
DK = ("dk", 220_000, 10_000, True, "tank")
FERAL = ("feral", 230_000, 8_000, True, "tank")
HUNTER = ("hunter", 140_000, 20_000, False, "dps")
SHAMAN_HEALS = ("shaman", 140_000, 20_000, False, "offheal")
SHAMAN = ("shaman", 140_000, 20_000, False, "dps")
MAGE = ("mage", 135_000, 22_000, False, "dps")
ROGUE = ("rogue", 140_000, 22_000, True, "dps")
RET = ("ret", 150_000, 18_000, True, "dps")
WARLOCK = ("warlock", 140_000, 20_000, False, "dps")
HOLY = ("holy", 140_000, 0, False, "healer")
DISC = ("disc", 135_000, 0, False, "healer")

LAYOUTS = {
    # The current default: the canonical duty plan, the shaman off-heals.
    "default": {0: [HOLY, ROGUE, MAGE], 1: [DISC, RET, FERAL, WARLOCK], 2: [DK, SHAMAN_HEALS, HUNTER]},
    # Option A, a pure burn team: the warlock joins pillar 2, the shaman damages.
    "option_a_burn": {0: [HOLY, ROGUE, MAGE], 1: [DISC, RET, FERAL], 2: [DK, SHAMAN, HUNTER, WARLOCK]},
    # Option A with the off-healer kept.
    "option_a_burn_offheal": {0: [HOLY, ROGUE, MAGE], 1: [DISC, RET, FERAL], 2: [DK, SHAMAN_HEALS, HUNTER, WARLOCK]},
    # Both tanks (the sturdiest, one self-healing) and a ranged DPS unhealed.
    "tank_pillar": {0: [HOLY, ROGUE, HUNTER, SHAMAN], 1: [DISC, RET, WARLOCK], 2: [DK, FERAL, MAGE]},
}


STILL = ((4.0, 6.4), (8.4, 13.3), (15.0, 1e9))


def cast_fits(start: float, length: float) -> bool:
    """A cast completes inside one of the healer's still windows."""
    return any(low <= start and start + length <= high for low, high in STILL)


def missile_seconds() -> float:
    """Flight from NefarianElevatorLiftOffPosition to a pillar top."""
    return math.hypot(PILLAR_RADIUS, LIFT_OFF_HEIGHT) / MISSILE_SPEED


def run(seed: int, layout: dict, heal_below: float, dps_scale: float = 1.0,
        tweak: dict | None = None) -> tuple[float | None, float]:
    tweak = tweak or {}
    mitigation = tweak.get("mitigation", 0.0)
    mana_pool = tweak.get("mana_pool", MANA_POOL)
    mana_regen = tweak.get("mana_regen", MANA_REGEN)
    dk_self_heal = tweak.get("dk_self_heal", DK_SELF_HEAL)
    prep = tweak.get("preparation", 0.8)
    rnd = random.Random(seed)
    members = {}
    for pillar, team in layout.items():
        for name, health, dps, melee, role in team:
            members[name] = {"pillar": pillar, "max": float(health), "hp": rnd.uniform(0.8, 1.0) * health,
                             "dps": dps * dps_scale, "melee": melee, "role": role, "absorb": 0.0,
                             "dead": False}
    for member in members.values():
        if member["pillar"] == 2:
            if rnd.random() < prep:
                member["absorb"] = 12_000.0
            if rnd.random() < prep:
                member["hp"] = min(member["max"], member["hp"] + 12_000.0)
    prototypes = {pillar: float(PROTOTYPE) for pillar in layout}
    healer = next((n for n, m in members.items() if m["role"] == "offheal"), None)
    mana = mana_pool
    cast_target = None
    cast_done = gcd_done = -1.0
    first_death = None
    pending: list[tuple[int, str, float]] = []  # (arrival step, target, damage)

    def hit(member: dict, damage: float) -> None:
        damage *= 1.0 - mitigation
        soaked = min(member["absorb"], damage)
        member["absorb"] -= soaked
        member["hp"] -= damage - soaked

    step = -8  # 0.1 s steps; the lift-off is 0.8 s before the platform starts down
    while step < 1800:
        step += 1
        t = step / 10.0
        busy_healing = healer is not None and cast_target is not None
        for name, member in members.items():
            if member["dead"] or t < (15.0 if member["melee"] else 6.7):
                continue
            if name == healer and busy_healing:
                continue
            prototypes[member["pillar"]] = max(0.0, prototypes[member["pillar"]] - member["dps"] / 10.0)
        if all(value <= 0.0 for value in prototypes.values()):
            return first_death, t
        if 65 <= step <= 135 and (step - 65) % 10 == 0:
            tick = (step - 65) // 10
            for member in members.values():
                if member["pillar"] == 2 and not member["dead"]:
                    hit(member, 5000.0 + 250.0 * tick)
        # A Barrage cast starts every 2.5 s from 2.5 s after the lift-off; its
        # targets are chosen when the 2 s cast completes, and each missile
        # lands after its flight.
        if step >= 37 and (step - 37) % 25 == 0:
            alive = [name for name, member in members.items() if not member["dead"]]
            for name in rnd.sample(alive, min(4, len(alive))):
                arrival = step + round(missile_seconds() * 10.0)
                pending.append((arrival, name, rnd.uniform(*BARRAGE)))
        landed = [entry for entry in pending if entry[0] <= step]
        pending = [entry for entry in pending if entry[0] > step]
        for _, name, damage in landed:
            if not members[name]["dead"]:
                hit(members[name], damage)
        for name, member in members.items():
            if member["pillar"] != 2:
                member["hp"] = member["max"]
            elif name == "dk" and not member["dead"]:
                member["hp"] = min(member["max"], member["hp"] + dk_self_heal / 10.0)
            if member["hp"] <= 0.0 and not member["dead"]:
                member["dead"] = True
                if member["pillar"] == 2 and first_death is None:
                    first_death = t
        mana = min(mana_pool, mana + mana_regen / 10.0)
        if healer is None or members[healer]["dead"]:
            continue
        if cast_target is not None and t >= cast_done:
            target = members[cast_target]
            if not target["dead"]:
                amount = HEAL_BASE * rnd.uniform(1.0 - HEAL_VARIANCE, 1.0 + HEAL_VARIANCE) + 0.483 * 4500.0
                if rnd.random() < 0.15:
                    amount *= HEAL_CRIT
                target["hp"] = min(target["max"], target["hp"] + amount)
            cast_target = None
        if cast_target is None and cast_fits(t, 1.5) and t >= gcd_done and mana >= SURGE_COST:
            team = [n for n, m in members.items() if m["pillar"] == 2 and not m["dead"]]
            lowest = min(team, key=lambda n: members[n]["hp"] / members[n]["max"])
            if members[lowest]["hp"] / members[lowest]["max"] < heal_below:
                cast_target = lowest
                cast_done = gcd_done = t + 1.5
                mana -= SURGE_COST
    return first_death, 180.0


def summarize(layout: dict, heal_below: float, dps_scale: float = 1.0, seeds: int = SEEDS,
              tweak: dict | None = None) -> dict:
    deaths = []
    phases = []
    for seed in range(seeds):
        death, phase = run(seed, layout, heal_below, dps_scale, tweak)
        phases.append(phase)
        if death is not None and death <= phase:
            deaths.append(death)
    return {
        "death_probability": round(len(deaths) / seeds, 3),
        "mean_phase_seconds": round(statistics.mean(phases), 1),
        "median_first_death_seconds": round(statistics.median(deaths), 1) if deaths else None,
    }


# The reviewer's sensitivity variants (GPT-6 Astra, second re-review), on the
# default layout.
SENSITIVITY = {
    "barrage_and_magma_10pct_mitigation": {"mitigation": 0.10},
    "barrage_and_magma_20pct_mitigation": {"mitigation": 0.20},
    "mana_40000": {"mana_pool": 40_000.0},
    "mana_120000": {"mana_pool": 120_000.0},
    "regen_0": {"mana_regen": 0.0},
    "regen_300": {"mana_regen": 300.0},
    "no_dk_self_heal": {"dk_self_heal": 0.0},
    "no_preparation": {"preparation": 0.0},
}


def model_results() -> dict:
    heal_below = threshold()
    results = {name: summarize(layout, heal_below) for name, layout in LAYOUTS.items()}
    for scale in (1.25, 1.5):
        results[f"default_dps_x{scale}"] = summarize(LAYOUTS["default"], heal_below, scale)
    return results


def sensitivity_results() -> dict:
    heal_below = threshold()
    return {name: summarize(LAYOUTS["default"], heal_below, tweak=tweak)["death_probability"]
            for name, tweak in SENSITIVITY.items()}


def test_recorded_survival_is_the_models() -> None:
    recorded = json.loads(DATA.read_text(encoding="utf-8"))
    assert recorded["seeds"] == SEEDS
    assert recorded["off_heal_threshold"] == threshold()
    assert recorded["results"] == model_results()
    assert recorded["sensitivity_death_probability"] == sensitivity_results()


def test_mechanics() -> None:
    # A heal is never cast across a swim or hop, and the Barrage lands late.
    assert not cast_fits(5.5, 1.5) and cast_fits(4.0, 1.5) and not cast_fits(12.0, 1.5)
    assert 1.7 < missile_seconds() < 1.76


def test_the_risk_is_reported_not_hidden() -> None:
    recorded = json.loads(DATA.read_text(encoding="utf-8"))
    default = recorded["results"]["default"]["death_probability"]
    healerless = json.loads(CONTRACT.read_text(encoding="utf-8"))["strategy"]["healerless_pillar"]
    assert f"{default:.0%}" in healerless
    assert "not a native estimate" in healerless and "not a native estimate" in recorded["note"]
    assert recorded["pillar_top_separation_yards"]["minimum"] > 40.0
