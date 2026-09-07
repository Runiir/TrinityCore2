from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BOSS = ROOT / (
    "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/"
    "boss_magmaw.cpp"
)


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
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def fixture_source(reset_body: str, engaged_body: str) -> str:
    return r'''#include <cassert>
#include <chrono>
#include <cstdint>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using namespace std::chrono_literals;

#define TC_LOG_ERROR(...) do { } while (false)

struct Unit { };

struct StubCreature
{
    static constexpr uint32 UNKILLABLE = 8u;

    uint32 staticFlags = 0;
    int reactState = -1;

    void SetUnkillable(bool enabled)
    {
        if (enabled)
            staticFlags |= UNKILLABLE;
        else
            staticFlags &= ~UNKILLABLE;
    }

    bool IsUnkillable() const
    {
        return (staticFlags & UNKILLABLE) != 0;
    }

    void SetReactState(int state)
    {
        reactState = state;
    }
};

struct StubInstance
{
    uint32 encounterEngages = 0;
    uint32 worldStateUpdates = 0;

    void SendEncounterUnit(uint32, StubCreature*, uint32)
    {
        ++encounterEngages;
    }

    void DoUpdateWorldState(uint32, uint32)
    {
        ++worldStateUpdates;
    }
};

struct StubEvents
{
    uint32 phase = 0;
    uint32 schedules = 0;

    void SetPhase(uint32 value)
    {
        phase = value;
    }

    template <typename Rep, typename Period>
    void ScheduleEvent(uint32, std::chrono::duration<Rep, Period>, uint32,
        uint32)
    {
        ++schedules;
    }
};

struct BossAI
{
    explicit BossAI(StubCreature* creature) : me(creature) { }

    StubCreature* me;
    bool bossEngaged = false;
    uint32 resetCalls = 0;

    void _Reset()
    {
        ++resetCalls;
        bossEngaged = false;
    }

    void JustEngagedWith(Unit*)
    {
        bossEngaged = true;
    }
};

struct Position
{
    float X;
    float Y;
    float Z;
};

constexpr Position NefarianIntroSummonPos{ 0.0f, 0.0f, 0.0f };

enum : uint32
{
    EVENT_MAGMA_PROJECTILE = 1,
    EVENT_LAVA_SPEW,
    EVENT_MANGLE,
    PHASE_OUT_OF_COMBAT = 10,
    PHASE_COMBAT,
    ENCOUNTER_FRAME_ENGAGE = 20,
    FRAME_PRIORITY_MAGMAW,
    WORLD_STATE_ID_PARASITE_EVENING = 30,
    NPC_NEFARIAN_MAGMAW = 40,
    TEMPSUMMON_MANUAL_DESPAWN = 50
};

constexpr int REACT_PASSIVE = 60;
constexpr int REACT_AGGRESSIVE = 61;
constexpr int EVADE_REASON_OTHER = 70;

struct boss_magmaw_fixture : public BossAI
{
    boss_magmaw_fixture(StubCreature* creature, StubInstance* scriptInstance,
        bool heroicMode) : BossAI(creature), instance(scriptInstance),
        heroic(heroicMode) { }

    void Reset()
    {
''' + reset_body + r'''
    }

    void JustEngagedWith(Unit* who)
    {
''' + engaged_body + r'''
    }

    uint8 GetMissingBodyMask() const
    {
        return bodyComplete ? 0 : missingBodyMask;
    }

    void DespawnBody()
    {
        ++despawnCalls;
    }

    void EnterEvadeMode(int)
    {
        ++evadeCalls;
    }

    bool IsHeroic() const
    {
        return heroic;
    }

    void DoSummon(uint32, Position const&, uint32, uint32)
    {
        ++summons;
    }

    StubInstance* instance;
    StubEvents events;
    bool heroic;
    bool bodyComplete = true;
    uint8 missingBodyMask = 1;
    uint32 despawnCalls = 0;
    uint32 evadeCalls = 0;
    uint32 summons = 0;
    uint8 _magmaProjectileCount = 0;
    bool _headEngaged = false;
    bool _heroicPhaseTwoActive = false;
};

int main()
{
    constexpr uint32 OTHER_FLAGS = 0x00000040u | 0x00000200u;
    Unit pullTarget;

    // 10N: Reset explicitly rearms the template protection and preserves
    // unrelated static flags; a complete pull releases only UNKILLABLE.
    StubCreature normalCreature;
    StubInstance normalInstance;
    boss_magmaw_fixture normal(&normalCreature, &normalInstance, false);
    normalCreature.staticFlags = OTHER_FLAGS;
    normal.Reset();
    assert(normalCreature.staticFlags
        == (OTHER_FLAGS | StubCreature::UNKILLABLE));
    normal.JustEngagedWith(&pullTarget);
    assert(normalCreature.staticFlags == OTHER_FLAGS);
    assert(!normalCreature.IsUnkillable());
    assert(normal.bossEngaged);
    assert(normalInstance.encounterEngages == 1);
    assert(normalInstance.worldStateUpdates == 1);
    assert(normal.events.schedules == 3);
    assert(normal.summons == 0);

    // A reset followed by an incomplete body stays protected at the early
    // return, then a later complete repull clears it again.
    normal.bodyComplete = false;
    normal.Reset();
    assert(normalCreature.staticFlags
        == (OTHER_FLAGS | StubCreature::UNKILLABLE));
    normal.JustEngagedWith(&pullTarget);
    assert(normalCreature.staticFlags
        == (OTHER_FLAGS | StubCreature::UNKILLABLE));
    assert(normalCreature.IsUnkillable());
    assert(!normal.bossEngaged);
    assert(normal.evadeCalls == 1);
    assert(normalInstance.encounterEngages == 1);

    normal.bodyComplete = true;
    normal.Reset();
    assert(normalCreature.staticFlags
        == (OTHER_FLAGS | StubCreature::UNKILLABLE));
    normal.JustEngagedWith(&pullTarget);
    assert(normalCreature.staticFlags == OTHER_FLAGS);
    assert(normalInstance.encounterEngages == 2);
    assert(normal.events.schedules == 6);

    // Heroic uses the same death-boundary transition and keeps its summon
    // branch exercised without modeling native damage or cleanup.
    StubCreature heroicCreature;
    StubInstance heroicInstance;
    boss_magmaw_fixture heroic(&heroicCreature, &heroicInstance, true);
    heroicCreature.staticFlags = OTHER_FLAGS;
    heroic.Reset();
    assert(heroicCreature.staticFlags
        == (OTHER_FLAGS | StubCreature::UNKILLABLE));
    heroic.JustEngagedWith(&pullTarget);
    assert(heroicCreature.staticFlags == OTHER_FLAGS);
    assert(!heroicCreature.IsUnkillable());
    assert(heroic.summons == 1);
}
'''


def compile_fixture(
    tmp_path: Path, reset_body: str, engaged_body: str
) -> Path:
    source = tmp_path / "magmaw_native_death_boundary.cpp"
    binary = tmp_path / "magmaw_native_death_boundary"
    source.write_text(fixture_source(reset_body, engaged_body), encoding="utf-8")
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    return binary


def test_magmaw_native_death_boundary(tmp_path: Path) -> None:
    source = BOSS.read_text(encoding="utf-8")
    reset_body = function_body(source, "void Reset() override")
    engaged_body = function_body(
        source, "void JustEngagedWith(Unit* who) override"
    )
    binary = compile_fixture(tmp_path, reset_body, engaged_body)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
