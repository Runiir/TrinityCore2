"""Tier-11 Bloodlust timing for the canonical Magmaw c0 shard (BWD 10N round 4).

The matched T11 kills hold raid lust for the first exposed head; the legacy accepted shard keeps its
WCL-timed pre-Mangle lead so the b5-d1898555 verdict stays reproducible.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAGMAW = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
TIMING = MAGMAW / "BotMagmawBloodlustTiming.h"
T11 = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_wcl_cast_timelines_t11_v1.json"
T11_REFS = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_wcl_dps_reference_t11_v1.json"
LUST = {"Bloodlust", "Heroism", "Time Warp", "Ancient Hysteria"}


def _constant(name: str) -> int:
    match = re.search(rf"constexpr uint32 {name} = (\d+);", TIMING.read_text(encoding="utf-8"))
    assert match, name
    return int(match.group(1))


def _to_ms(clock: str) -> int:
    minutes, seconds = clock.split(":")
    return round((int(minutes) * 60 + float(seconds)) * 1000)


def test_t11_reference_lust_lands_on_the_first_exposed_head() -> None:
    timelines = json.loads(T11.read_text(encoding="utf-8"))
    refs = [(timelines["reference_id"], timelines["actors"])] + [
        (extra["reference_id"], extra["actors"]) for extra in timelines["additional_references"]
    ]
    lusts = [
        (ref, cast["ability"], cast["t"])
        for ref, actors in refs
        for actor in actors
        for cast in actor["casts"]
        if cast["ability"] in LUST
    ]
    assert lusts == [("RtPXnbZxFkpacw1h-fight6", "Heroism", 116.069)]
    assert _constant("T11ReferenceHeroismAfterPullMs") == 116069

    manifest = json.loads(T11_REFS.read_text(encoding="utf-8"))
    rtpx = next(ref for ref in manifest["references"] if ref["id"] == "RtPXnbZxFkpacw1h-fight6")
    mangle_end = _to_ms(rtpx["phase_coverage"]["mangle_removal_times"][0])
    assert mangle_end == _constant("T11ReferenceMangleEndAfterPullMs") == 112904
    # Every T11 kill outlasts its Mangle release by far more than the 30 s head
    # window, so a head-anchored 40 s lust is always spent inside the kill.
    for ref in manifest["references"]:
        release = _to_ms(ref["phase_coverage"]["mangle_removal_times"][0])
        assert ref["duration_sec"] * 1000 - release >= 16000, ref["id"]

    # The matched actors' major cooldowns also target the exposed head.
    on_head = {
        cast["ability"]
        for _, actors in refs
        for actor in actors
        for cast in actor["casts"]
        if cast.get("target") == "Exposed Head of Magmaw"
    }
    assert {"Combustion", "Vendetta", "Dancing Rune Weapon"} <= on_head


def test_canonical_cohorts_wait_for_the_head_and_legacy_keeps_its_lead(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_t11_lust.cpp"
    binary = tmp_path / "magmaw_t11_lust"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlustTiming.h"

#include <cassert>
#include <string>

using namespace BotEncounter;
using namespace BotEncounter::MagmawBloodlust;

static ObjectGuid const BossGuid(HighGuid::Unit, BossEntry, uint32(41));
static ObjectGuid const HeadGuid(HighGuid::Unit, ExposedHeadEntry, uint32(76));

static Blackboard Encounter(uint32 remainingMs, bool withHead)
{
    ActorSnapshot boss;
    boss.Guid = BossGuid;
    boss.Entry = BossEntry;
    boss.Kind = ActorKind::Hostile;
    boss.Alive = boss.Attackable = boss.Selectable = boss.InCombat = true;
    boss.MechanicTimers.push_back({ MassiveCrashSpell, remainingMs, false,
        FactSource::NativeInstanceState });
    Blackboard board;
    board.Route.NodeId = std::string(EncounterNode);
    board.NativeBossState = "in_progress";
    board.Hostiles = { boss };
    if (withHead)
    {
        ActorSnapshot head;
        head.Guid = HeadGuid;
        head.Entry = ExposedHeadEntry;
        head.Kind = ActorKind::Summon;
        head.Alive = head.Attackable = head.Selectable = head.InCombat = true;
        board.Summons = { head };
    }
    return board;
}

int main()
{
    std::string_view const legacy = "blackwing_descent_10n_magmaw_diagnostic";
    std::string_view const c0 = "blackwing_descent_10n_magmaw_c0_diagnostic";
    std::string_view const c1 = "blackwing_descent_10n_magmaw_c1_diagnostic";
    assert(LustTimingPolicyForScenario(legacy) == LustTimingPolicy::PreMangleLeadOrFirstHead);
    assert(LustTimingPolicyForScenario(c0) == LustTimingPolicy::FirstExposedHeadOnly);
    assert(LustTimingPolicyForScenario(c1) == LustTimingPolicy::FirstExposedHeadOnly);
    assert(LustTimingPolicyForScenario("blackwing_descent_10n_magmaw_cx_diagnostic")
        == LustTimingPolicy::PreMangleLeadOrFirstHead);
    assert(LustTimingPolicyForScenario("") == LustTimingPolicy::PreMangleLeadOrFirstHead);

    // Inside the pre-Mangle lead with no head: legacy lusts, c0 waits.
    Blackboard const lead = Encounter(PreMangleLustLeadMs, false);
    auto const legacyLead = SelectLustWindow(lead, std::nullopt, legacy);
    assert(legacyLead && legacyLead->Trigger == LustTrigger::PreMangleLead);
    auto const twoArg = SelectLustWindow(lead, std::nullopt);
    assert(twoArg && twoArg->Trigger == legacyLead->Trigger
        && twoArg->TargetGuid == legacyLead->TargetGuid);
    assert(!SelectLustWindow(lead, std::nullopt, c0));
    // During the Mangle -> Massive Crash sequence c0 still waits.
    assert(!SelectLustWindow(Encounter(0, false), std::nullopt, c0));

    // The first exposed head opens the lust for both, bound to the head.
    Blackboard const head = Encounter(60000, true);
    std::optional<HeadWindow> const window = ObserveFirstHeadWindow(head);
    assert(window);
    for (std::string_view scenario : { legacy, c0 })
    {
        auto const choice = SelectLustWindow(head, window, scenario);
        assert(choice && choice->Trigger == LustTrigger::FirstExposedHead);
        assert(choice->TargetGuid == HeadGuid && choice->BossGuid == BossGuid);
    }
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "src/server/game"),
         "-I", str(ROOT / "src/server/game/Entities/Object"),
         "-I", str(ROOT / "src/server/shared"),
         "-I", str(ROOT / "src/common"),
         str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
