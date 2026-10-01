"""Round 4 (BWD 10N): phase-two healer reach and the melee Biting Chill ring.

Reuses the canonical replay helpers of test_maloriak_strategy.py (its program
up to main) and checks two r03 findings:

- kill 35b93d: the Feral held both Prime Subjects at the west add spot while
  both healers stood 43-61 yards away on the back fan; it took one heal in
  14 s and died to Prime Subject melee (cd3009 fell to 12.7k the same way);
- kill 35b93d: the chilled rogue walked 8 yards off its nearest ally, 11-15
  yards from Maloriak, and landed no melee on him for 12 s.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _strategy_module():
    spec = importlib.util.spec_from_file_location(
        "maloriak_strategy_replay", ROOT / "tests/test_maloriak_strategy.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CASES = r'''
int main()
{
    // Phase two, the Feral holding both Prime Subjects at the west add spot
    // (r03 35b93d: Feral at -130, -434), both healers on the far back fan.
    {
        Blackboard board = Canonical();
        Boss(board).HealthPct = 20.0f;
        Boss(board).Auras.push_back({ 95663, Boss(board).Guid, 1, 0 });
        for (uint32 index = 0; index < 2; ++index)
        {
            ActorSnapshot subject = Add(41841, 700 + index, -131.0f + 2.0f * float(index), -436.0f, true, 100.0f);
            subject.VictimGuid = G(FERAL);
            board.Summons.push_back(subject);
        }
        Vector3 const feral = board.Players[FERAL].Position;
        board.Players[HOLY].Position = { -95.0f, -470.0f, 73.6f };
        board.Players[DISC].Position = { -88.0f, -462.0f, 73.6f };
        CHECK(Dist(board.Players[HOLY].Position, feral) > 45.0f);
        std::vector<Vector3> spots;
        for (Slot slot : { HOLY, DISC })
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            CHECK(plan.Movement.has_value());
            if (!plan.Movement)
                continue;
            CHECK(plan.Movement->Id.Mechanic == "phase_two_spread");
            Vector3 const spot = Destination(plan);
            CHECK(Dist(spot, feral) <= M::OffTankHealReach);
            CHECK(Dist(spot, board.Players[DK].Position) <= 30.0f);
            CHECK(AngleFromFront(board, spot) >= 70.0f);
            spots.push_back(spot);
        }
        if (spots.size() == 2)
            CHECK(Dist(spots[0], spots[1]) >= 4.99f);
        // Standing on its slot, a healer holds (no oscillation).
        AdaptiveMaloriakPlan const first = Plan(board, HOLY);
        board.Players[HOLY].Position = Destination(first);
        CHECK(!Plan(board, HOLY).Movement);
        // The ranged damage dealers keep the ordinary back fan.
        AdaptiveMaloriakPlan const mage = Plan(board, MAGE);
        CHECK(mage.Movement && mage.Movement->Id.Mechanic == "phase_two_spread");
        CHECK(AngleFromFront(board, Destination(mage)) > 75.0f);
        // With the off-tank dead there is nobody to keep in reach.
        board.Players[FERAL].Alive = false;
        board.Players[HOLY].Position = { -95.0f, -470.0f, 73.6f };
        AdaptiveMaloriakPlan const alone = Plan(board, HOLY);
        CHECK(!alone.Movement || Dist(Destination(alone), feral) > M::OffTankHealReach);
    }

    // Phase one is unchanged: no Prime Subjects, no off-tank hold.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        board.Players[HOLY].Position = { -95.0f, -470.0f, 73.6f };
        AdaptiveMaloriakPlan const plan = Plan(board, HOLY);
        CHECK(!plan.Movement || Dist(Destination(plan), board.Players[FERAL].Position) > M::OffTankHealReach);
    }

    // Biting Chill on a melee damage dealer at the boss: a clear point of the
    // back melee rings, never 8 yards out of reach.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        board.Players[ROGUE].Auras.push_back({ M::BitingChillSpell, Boss(board).Guid, 1, board.ObservedAtMs + 9000 });
        board.Players[RET].Position = { -107.0f, -457.0f, 73.6f };
        AdaptiveMaloriakPlan const chill = Plan(board, ROGUE);
        CHECK(chill.Movement && chill.Movement->Id.Mechanic == "biting_chill_ring_isolation");
        Vector3 const ring = Destination(chill);
        CHECK(Dist(ring, BossAt) <= M::MeleeOuterRingRadius + 0.01f);
        CHECK(AngleFromFront(board, ring) >= 70.0f);
        for (ActorSnapshot const& player : board.Players)
            if (player.Guid != G(ROGUE))
                CHECK(Dist(ring, player.Position) >= 5.49f);
        // Standing there, apart from everyone: no further move.
        board.Players[ROGUE].Position = ring;
        CHECK(!Plan(board, ROGUE).Movement);
        // A sphere on every ring point: the old step away from the ally.
        board.Players[ROGUE].Position = { -108.5f, -457.5f, 73.6f };
        for (uint32 index = 0; index < 8; ++index)
        {
            float const angle = float(index) * 3.14159265f / 4.0f;
            board.Summons.push_back(Add(41961, 800 + index, BossAt.X + 4.0f * std::cos(angle),
                BossAt.Y + 4.0f * std::sin(angle), false, 100.0f));
        }
        AdaptiveMaloriakPlan const blocked = Plan(board, ROGUE);
        CHECK(blocked.Movement.has_value());
        if (blocked.Movement)
            CHECK(blocked.Movement->Id.Mechanic != "biting_chill_ring_isolation");
    }

    // A chilled melee player away from the boss (on an Aberration) and a
    // chilled ranged player keep the step away from the nearest ally.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        board.Players[ROGUE].Auras.push_back({ M::BitingChillSpell, Boss(board).Guid, 1, board.ObservedAtMs + 9000 });
        board.Players[ROGUE].Position = { -125.0f, -440.0f, 73.6f };
        board.Players[SHAMAN].Position = { -123.0f, -441.0f, 73.6f };
        AdaptiveMaloriakPlan const away = Plan(board, ROGUE);
        CHECK(away.Movement && away.Movement->Id.Mechanic == "biting_chill_isolation");
        Blackboard ranged = Canonical();
        Boss(ranged).Auras.push_back({ 78895, Boss(ranged).Guid, 1, 0 });
        ranged.Players[MAGE].Auras.push_back({ M::BitingChillSpell, Boss(ranged).Guid, 1, ranged.ObservedAtMs + 9000 });
        ranged.Players[MAGE].Position = { -103.0f, -457.5f, 73.6f };
        AdaptiveMaloriakPlan const mage = Plan(ranged, MAGE);
        CHECK(mage.Movement && mage.Movement->Id.Mechanic == "biting_chill_isolation");
    }

    return failures == 0 ? 0 : 1;
}
'''


def test_maloriak_round4_healer_reach_and_chill_ring(tmp_path: Path) -> None:
    module = _strategy_module()
    prefix = module.PROGRAM[: module.PROGRAM.index("int main()")]
    source = tmp_path / "maloriak_round4.cpp"
    binary = tmp_path / "maloriak_round4"
    source.write_text(prefix + CASES, encoding="utf-8")
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function"]
    for include in module.INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
