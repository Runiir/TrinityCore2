from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


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


def fixture_source(observation_body: str, helper_body: str) -> str:
    return r'''#include <cassert>
#include <cstdint>
#include <string>
#include <vector>

using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

namespace BotActionArbitration
{
struct Outcome
{
    std::string Reason;

    static Outcome NotApplicable(char const* reason)
    {
        return { reason };
    }
};
}

namespace BotEncounter
{
struct AdaptiveMagmawStrategy
{
    static constexpr uint32 BossEntry = 41570;
    static constexpr uint32 HeadEntry = 42347;
    static constexpr uint32 ParasiteEntry = 41806;
    static constexpr uint32 ParasiteAltEntry = 42321;
};
}

struct Creature;

struct Unit
{
    Creature* creature = nullptr;
    uint64 guid = 0;
    bool alive = true;

    Creature* ToCreature() const
    {
        return creature;
    }

    bool IsAlive() const
    {
        return alive;
    }

    uint64 GetGUID() const
    {
        return guid;
    }
};

struct Creature : Unit
{
    explicit Creature(uint32 creatureEntry, uint64 creatureGuid)
        : entry(creatureEntry)
    {
        guid = creatureGuid;
        creature = this;
    }

    uint32 entry;
    bool dungeonBoss = false;
    bool worldBoss = false;
    uint32 mapId = 0;
    uint32 instanceId = 0;

    uint32 GetEntry() const
    {
        return entry;
    }

    bool IsDungeonBoss() const
    {
        return dungeonBoss;
    }

    bool isWorldBoss() const
    {
        return worldBoss;
    }

    uint32 GetMapId() const
    {
        return mapId;
    }

    uint32 GetInstanceId() const
    {
        return instanceId;
    }
};

struct StubBot
{
    bool nativeCombatObserved = true;

    bool IsValidAttackTarget(Unit* target) const
    {
        return target && target->IsAlive();
    }

    float GetExactDist(Unit*) const
    {
        return 1.0f;
    }
};

struct StubConfig
{
    std::string ValidationRouteKind = "boss";
    std::string ValidationRouteNodeId = "bwd.magmaw.encounter";
    uint32 ValidationRouteTargetEntry =
        BotEncounter::AdaptiveMagmawStrategy::BossEntry;
};

struct StubCohort
{
    StubConfig Config;
};

struct StubParty
{
    bool ValidationRouteObservedEngagement = false;
    uint64 ValidationRouteEngagedBossGuid = 0;
    uint64 ValidationRouteEngagedBossGeneration = 0;
    uint32 ValidationRouteEngagedBossMapId = 0;
    uint32 ValidationRouteEngagedBossInstanceId = 0;
    uint64 ValidationRouteGeneration = 7;
    uint64 ValidationRouteFocusGuid = 0xF0C05EED;
};

struct StubState
{
    uint64 LastDecisionTargetGuid = 0;
    bool WasInCombat = false;
    uint64 TargetGuid = 0x7A7A7A7A;
};

struct StubPower { };

struct StubActivity
{
    int Activity = 0;
};

struct StubContext
{
    bool AdaptiveMagmawOwnsNode = true;
    Unit* Target = nullptr;
    StubBot* Bot = nullptr;
    StubState State;
    StubPower Power;
    int Stage = 0;
    StubActivity ChosenActivity;
};

struct EngagementFixture
{
    StubCohort cohort;
    StubParty party;
    std::vector<std::string> events;

    StubCohort& Cohort()
    {
        return cohort;
    }

    StubParty& Party()
    {
        return party;
    }

    bool IsNativeCombatObserved(StubBot* bot, Unit* target) const
    {
        return bot && target && bot->nativeCombatObserved;
    }

    std::string BuildRawJson(StubBot*, Unit*) const
    {
        return "{}";
    }

    std::string BuildSemanticJson(StubBot*, Unit*, char const*, StubPower*,
        int, int) const
    {
        return "{}";
    }

    void RecordEvent(StubState&, StubBot*, char const* event, Unit*, char const*,
        char const*, char const*, float, uint32, uint32)
    {
        events.emplace_back(event);
    }

    void RememberValidationRouteBossEngagement(Creature const* boss)
    {
''' + helper_body + r'''
    }

    BotActionArbitration::Outcome Observe(StubContext& context)
    {
''' + observation_body + r'''
    }
};

static void AssertEngagement(StubParty const& party, uint64 guid,
    uint64 generation, uint32 mapId, uint32 instanceId)
{
    assert(party.ValidationRouteEngagedBossGuid == guid);
    assert(party.ValidationRouteEngagedBossGeneration == generation);
    assert(party.ValidationRouteEngagedBossMapId == mapId);
    assert(party.ValidationRouteEngagedBossInstanceId == instanceId);
}

static void AssertUnchanged(StubParty const& party, uint64 guid,
    uint64 generation, uint32 mapId, uint32 instanceId)
{
    AssertEngagement(party, guid, generation, mapId, instanceId);
}

int main()
{
    constexpr uint64 SENTINEL_GUID = 0x11111111;
    constexpr uint64 SENTINEL_GENERATION = 99;
    constexpr uint32 SENTINEL_MAP = 998;
    constexpr uint32 SENTINEL_INSTANCE = 997;
    constexpr uint64 TARGET_SENTINEL = 0x7A7A7A7A;
    constexpr uint64 FOCUS_SENTINEL = 0xF0C05EED;

    Creature boss(BotEncounter::AdaptiveMagmawStrategy::BossEntry, 41570);
    boss.dungeonBoss = true;
    boss.mapId = 669;
    boss.instanceId = 2;
    StubBot bot;
    EngagementFixture fixture;
    fixture.party.ValidationRouteEngagedBossGuid = SENTINEL_GUID;
    fixture.party.ValidationRouteEngagedBossGeneration = SENTINEL_GENERATION;
    fixture.party.ValidationRouteEngagedBossMapId = SENTINEL_MAP;
    fixture.party.ValidationRouteEngagedBossInstanceId = SENTINEL_INSTANCE;

    // Native combat on the declared live boss registers identity even when
    // the event stream already deduplicated this target.
    StubContext deduplicated;
    deduplicated.Target = &boss;
    deduplicated.Bot = &bot;
    deduplicated.State.LastDecisionTargetGuid = boss.GetGUID();
    deduplicated.State.WasInCombat = true;
    fixture.Observe(deduplicated);
    AssertEngagement(fixture.party, boss.GetGUID(),
        fixture.party.ValidationRouteGeneration, boss.mapId, boss.instanceId);
    assert(!fixture.party.ValidationRouteObservedEngagement);
    assert(deduplicated.State.TargetGuid == TARGET_SENTINEL);
    assert(fixture.party.ValidationRouteFocusGuid == FOCUS_SENTINEL);

    StubContext first;
    first.Target = &boss;
    first.Bot = &bot;
    fixture.Observe(first);
    assert(fixture.party.ValidationRouteObservedEngagement);
    assert(first.State.WasInCombat);
    assert((fixture.events == std::vector<std::string>{
        "validation_target_priority", "boss_action", "boss_started" }));
    assert(first.State.TargetGuid == TARGET_SENTINEL);
    assert(fixture.party.ValidationRouteFocusGuid == FOCUS_SENTINEL);

    // Adaptive head and parasite observations remain declared targets but
    // cannot overwrite the exact boss engagement identity.
    for (uint32 entry : { BotEncounter::AdaptiveMagmawStrategy::HeadEntry,
            BotEncounter::AdaptiveMagmawStrategy::ParasiteEntry,
            BotEncounter::AdaptiveMagmawStrategy::ParasiteAltEntry })
    {
        Creature add(entry, uint64(entry));
        StubContext addContext;
        addContext.Target = &add;
        addContext.Bot = &bot;
        fixture.party.ValidationRouteEngagedBossGuid = SENTINEL_GUID;
        fixture.party.ValidationRouteEngagedBossGeneration = SENTINEL_GENERATION;
        fixture.party.ValidationRouteEngagedBossMapId = SENTINEL_MAP;
        fixture.party.ValidationRouteEngagedBossInstanceId = SENTINEL_INSTANCE;
        fixture.party.ValidationRouteObservedEngagement = false;
        fixture.Observe(addContext);
        AssertUnchanged(fixture.party, SENTINEL_GUID, SENTINEL_GENERATION,
            SENTINEL_MAP, SENTINEL_INSTANCE);
    }

    // The adaptive observation gate does not register non-native, dead, or
    // wrong-node candidates, and ordinary target/focus sentinels survive.
    StubContext rejected;
    rejected.Target = &boss;
    rejected.Bot = &bot;
    fixture.party.ValidationRouteEngagedBossGuid = SENTINEL_GUID;
    fixture.party.ValidationRouteEngagedBossGeneration = SENTINEL_GENERATION;
    fixture.party.ValidationRouteEngagedBossMapId = SENTINEL_MAP;
    fixture.party.ValidationRouteEngagedBossInstanceId = SENTINEL_INSTANCE;
    boss.dungeonBoss = false;
    fixture.Observe(rejected);
    AssertUnchanged(fixture.party, SENTINEL_GUID, SENTINEL_GENERATION,
        SENTINEL_MAP, SENTINEL_INSTANCE);
    boss.dungeonBoss = true;
    bot.nativeCombatObserved = false;
    fixture.Observe(rejected);
    AssertUnchanged(fixture.party, SENTINEL_GUID, SENTINEL_GENERATION,
        SENTINEL_MAP, SENTINEL_INSTANCE);

    bot.nativeCombatObserved = true;
    boss.alive = false;
    fixture.Observe(rejected);
    AssertUnchanged(fixture.party, SENTINEL_GUID, SENTINEL_GENERATION,
        SENTINEL_MAP, SENTINEL_INSTANCE);

    boss.alive = true;
    fixture.cohort.Config.ValidationRouteNodeId = "other.node";
    fixture.Observe(rejected);
    AssertUnchanged(fixture.party, SENTINEL_GUID, SENTINEL_GENERATION,
        SENTINEL_MAP, SENTINEL_INSTANCE);
    assert(rejected.State.TargetGuid == TARGET_SENTINEL);
    assert(fixture.party.ValidationRouteFocusGuid == FOCUS_SENTINEL);
}
'''


def compile_fixture(
    tmp_path: Path, observation_body: str, helper_body: str
) -> Path:
    source = tmp_path / "validation_route_boss_engagement.cpp"
    binary = tmp_path / "validation_route_boss_engagement"
    source.write_text(
        fixture_source(observation_body, helper_body), encoding="utf-8"
    )
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


def test_validation_route_boss_engagement_behavior(tmp_path: Path) -> None:
    fallback = (BOTS / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text(
        encoding="utf-8"
    )
    focus = (BOTS / "BotWorldPopulationMgrValidationFocus.cpp").read_text(
        encoding="utf-8"
    )
    observation_body = function_body(
        fallback, "auto observeAdaptiveMagmawRoute = [this, &context]()"
    )
    helper_body = function_body(
        focus, "void BotWorldPopulationMgr::RememberValidationRouteBossEngagement("
    )
    binary = compile_fixture(tmp_path, observation_body, helper_body)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
