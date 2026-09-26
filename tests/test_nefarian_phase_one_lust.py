"""Phase 1 Bloodlust on the Onyxia pull (user raid experience 2026-09-26).

The user's tactic: Bloodlust and burn Onyxia before Nefarian lands. The
Nefarian strategy declares no lust timing of its own, so the canonical boss
lust fallback (BotRaidBossLust.h) owns it: the lust owner casts once a boss is
engaged and the main tank has held it for TankHoldMs. Onyxia (41270) is a
boss mob (creature_template type_flags 0x4, Creature::isWorldBoss), so the
hold starts when the Feral tank picks her up, not when Nefarian lands about
30 s later.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run


ROOT = Path(__file__).resolve().parents[1]
TDB = ROOT / "data/TDB_full_434.22011_2022_01_09/TDB_full_world_434.22011_2022_01_09.sql"

PROGRAM = PRELUDE.replace(
    '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"',
    '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"\n'
    '#include "Bots/BotRaidBossLust.h"') + r'''
int main()
{
    Blackboard board = CanonicalBoard();
    AddDragons(board, false); // Onyxia engaged by the Feral, Nefarian airborne
    ObjectGuid const onyxia = board.Summons[0].Guid;
    auto isBoss = [&board](ObjectGuid guid)
    {
        ActorSnapshot const* actor = board.FindActor(guid);
        // isWorldBoss: Onyxia and Nefarian both carry CREATURE_TYPE_FLAG_BOSS_MOB.
        return actor && (actor->Entry == OnyxiaEntry || actor->Entry == NefarianEntry);
    };
    BotRaidBossLust::TankHold const hold = BotRaidBossLust::FindTankHold(board, isBoss);
    CHECK(hold.Boss == onyxia && hold.Tank == Bot(2), "the Feral holding Onyxia starts the lust hold");
    CHECK(!BotRaidBossLust::StrategyOwnsLust("bwd.nefarian.encounter",
        "blackwing_descent_10n_nefarian_c0_diagnostic"),
        "the Nefarian strategy leaves the lust to the canonical fallback");
    std::optional<BotRaidBossLust::Owner> const owner = BotRaidBossLust::SelectOwner(board);
    CHECK(owner && owner->Guid == Bot(4) && owner->ProposedSpell == 80353,
        "the fire mage owns the lust (Time Warp)");
    AdaptiveNefarianStrategy strategy;
    CHECK(ObserveEncounter(board).CurrentPhase == Phase::OnyxiaOnly
        && strategy.Propose(board, Bot(4), "dps").DamageTarget == onyxia,
        "and the raid burns Onyxia meanwhile");
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_lust_lands_on_the_onyxia_pull(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM)


def test_onyxia_is_a_boss_mob() -> None:
    if not TDB.is_file():
        pytest.skip("the TDB dump is local-only")
    text = TDB.read_text(encoding="utf-8", errors="replace")
    for entry, name in ((41270, "Onyxia"), (41376, "Nefarian")):
        match = re.search(r"\(" + str(entry) + r",(?:\d+,){9}'" + name + r"'([^)]*)\)", text)
        assert match, entry
        # After name, femaleName, subname, IconName: gossip_menu_id, minlevel,
        # maxlevel, exp, exp_unk, faction, npcflag, speed_walk, speed_run,
        # scale, rank, dmgschool, BaseAttackTime, RangeAttackTime,
        # BaseVariance, RangeVariance, unit_class, unit_flags, unit_flags2,
        # dynamicflags, family, trainer_type, trainer_class, trainer_race,
        # type, type_flags.
        fields = match.group(1).split(",")[4:]
        type_flags = int(fields[25])
        assert type_flags & 0x4, (entry, type_flags)
