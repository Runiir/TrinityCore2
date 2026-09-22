from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def compile_and_run(tmp_path: Path, name: str, body: str) -> None:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(body, encoding="utf-8")
    subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "src/common/Logging"),
            "-I", str(ROOT / "src/common/Debugging"),
            str(source), str(BOTS / "BotSpellQueue.cpp"),
            "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_wait_until_is_scheduled_not_a_failure(tmp_path: Path) -> None:
    compile_and_run(tmp_path, "wait_until", r'''
#include "Bots/BotActionArbiter.h"
#include <cassert>

using namespace BotActionArbitration;

Candidate Make(Outcome (*attempt)(), int* calls)
{
    Candidate candidate;
    candidate.Key = "world.profile_combat";
    candidate.ActionPriority = Priority::TrainedDamage;
    candidate.RequiredResources = Uses(Resource::GlobalCooldown);
    candidate.Attempt = [attempt, calls]() { ++*calls; return attempt(); };
    return candidate;
}

Outcome GcdWait() { return Outcome::WaitUntil("global_cooldown", 1700); }

int main()
{
    Kernel kernel;
    int calls = 0;
    // A timed wait keeps the candidate out of the next resolutions until the
    // exact release time and never accumulates failures, however long the
    // bot keeps waiting.
    for (uint64 now = 1000; now < 20000; now += 100)
    {
        kernel.Begin(now);
        kernel.Submit(Make(GcdWait, &calls));
        kernel.Resolve();
        Lifecycle const* lifecycle = kernel.FindLifecycle("world.profile_combat");
        assert(lifecycle);
        assert(lifecycle->ConsecutiveFailures == 0);
        assert(lifecycle->FirstFailureAtMs == 0);
        assert(!kernel.ShouldEscalate("world.profile_combat", now, 5000));
        if (now >= 1700)
            break;
    }
    kernel.ResetLifecycleHistory(0);
    calls = 0;
    kernel.Begin(1000);
    kernel.Submit(Make(GcdWait, &calls));
    kernel.Resolve();
    assert(calls == 1);
    assert(kernel.FindLifecycle("world.profile_combat")->RetryAfterMs == 1700);
    assert(kernel.FindLifecycle("world.profile_combat")->LastReason == "global_cooldown");
    assert(kernel.FindLifecycle("world.profile_combat")->CurrentPhase == Phase::Deferred);
    kernel.Begin(1699);
    kernel.Submit(Make(GcdWait, &calls));
    kernel.Resolve();
    assert(calls == 1);
    assert(kernel.LastResolution().Trace.front().Status == "backoff");
    kernel.Begin(1700);
    kernel.Submit(Make(GcdWait, &calls));
    kernel.Resolve();
    assert(calls == 2);

    // A release beyond the candidate's maximum is clamped, and a release in
    // the past makes the candidate eligible again immediately.
    kernel.Observe("far", Outcome::WaitUntil("channel", 900000), 1000, 100, 3000, 5);
    assert(kernel.FindLifecycle("far")->RetryAfterMs == 4000);
    kernel.Observe("past", Outcome::WaitUntil("global_cooldown", 10), 1000, 100, 3000, 5);
    assert(kernel.FindLifecycle("past")->RetryAfterMs == 1000);

    // Ordinary retryable failures keep their exponential backoff and escalate.
    kernel.ResetLifecycleHistory(0);
    uint64 now = 1000;
    uint64 lastDelayMs = 0;
    for (int attempt = 0; attempt < 6; ++attempt)
    {
        kernel.Observe("fail", Outcome::Retryable("cast_failed"), now, 100, 3000, 5);
        lastDelayMs = kernel.FindLifecycle("fail")->RetryAfterMs - now;
        now = kernel.FindLifecycle("fail")->RetryAfterMs;
    }
    assert(kernel.FindLifecycle("fail")->ConsecutiveFailures == 6);
    assert(lastDelayMs == 3000);
    assert(kernel.ShouldEscalate("fail", 6000, 5000));
    // The unchanged native mapping still reports a GCD as not submitted.
    assert(FromBotActionResult(BotActionResult::GlobalCooldown).Result
        == Disposition::Retryable);
    assert(FromBotActionResult(BotActionResult::GlobalCooldown).RetryAtMs == 0);
}
''')


def test_priority_queue_orders_by_release_then_priority(tmp_path: Path) -> None:
    compile_and_run(tmp_path, "queue_order", r'''
#include "Bots/BotSpellQueue.h"
#include <cassert>
#include <string>

using namespace BotSpellQueue;

bool Contains(std::string const& json, std::string const& field)
{
    return json.find(field) != std::string::npos;
}

int main()
{
    NativeLock lock;
    lock.GlobalCooldownEndsAtMs = 1200;
    lock.CastEndsAtMs = 2500;
    assert(lock.ReleaseAtMs() == 2500);
    assert(lock.Locked(2499));
    assert(!lock.Locked(2500));
    assert(!NativeLock{}.Locked(0));

    Queue queue;
    assert(queue.Empty());
    assert(queue.WakeDelayMs(100, 100) == 100);

    queue.Schedule("late", "cast", 60, 500, 100);
    queue.Schedule("damage", "global_cooldown", 60, 300, 100);
    queue.Schedule("mechanic", "global_cooldown", 140, 300, 100);
    // Wake for the earliest release, never later than the ordinary cadence
    // and never with a zero delay.
    assert(queue.WakeDelayMs(100, 1000) == 200);
    assert(queue.WakeDelayMs(100, 50) == 50);
    assert(queue.WakeDelayMs(300, 1000) == 1);

    // Both intents released at 300 surface in priority order; the lower
    // priority one is released last.
    assert(queue.ReleaseDue(299) == 0);
    assert(queue.ReleaseDue(304) == 2);
    std::string json = queue.ToJson(304);
    assert(Contains(json, "\"last_released_key\":\"damage\""));
    assert(Contains(json, "\"released\":2"));
    assert(Contains(json, "\"max_release_latency_ms\":4"));
    assert(Contains(json, "\"next_key\":\"late\""));
    assert(Contains(json, "\"next_ready_in_ms\":196"));

    // A newer wait on the same key supersedes the older release time.
    queue.Clear();
    queue.Schedule("world.profile_combat", "global_cooldown", 60, 400, 100);
    queue.Schedule("world.profile_combat", "global_cooldown", 60, 900, 100);
    assert(queue.WakeDelayMs(100, 5000) == 800);
    assert(queue.ReleaseDue(500) == 0);
    assert(queue.ReleaseDue(910) == 1);
    assert(queue.Empty());

    // Requested releases are bounded to the maximum wait.
    queue.Schedule("long_channel", "channel", 60, 100000, 1000);
    assert(queue.WakeDelayMs(1000, 100000) == MaxWaitMs);

    // Repeated waits on one key stay compact.
    queue.Clear();
    for (uint64 now = 0; now < 100000; now += 10)
        queue.Schedule("world.profile_combat", "global_cooldown", 60, now + 700, now);
    assert(Contains(queue.ToJson(0), "\"pending\":1"));

    assert(IsRegenerationWaitReason("insufficient_resource"));
    assert(IsRegenerationWaitReason("cooldown_not_ready"));
    assert(!IsRegenerationWaitReason("out_of_range"));
    assert(!IsRegenerationWaitReason("no_valid_profile_action"));
}
''')


def test_spell_queue_recovers_gcd_time_lost_to_backoff(tmp_path: Path) -> None:
    # Replays the live decision loop with the real kernel and queue: a world
    # tick advances the decision timer, the rotation candidate either casts
    # an instant or observes the GCD, and the queue aligns the next decision
    # with the native release exactly as AlignDecisionTimerToSpellQueue does.
    compile_and_run(tmp_path, "gcd_replay", r'''
#include "Bots/BotActionArbiter.h"
#include "Bots/BotSpellQueue.h"
#include <cassert>
#include <cstdio>

using namespace BotActionArbitration;

int Replay(bool spellQueue, uint32 gcdMs, uint32 cadenceMs, uint32 worldTickMs)
{
    Kernel kernel;
    BotSpellQueue::Queue queue;
    uint64 gcdEndsAtMs = 0;
    uint32 timer = 0;
    int casts = 0;
    for (uint64 now = 0; now < 60000; now += worldTickMs)
    {
        if (timer > worldTickMs)
        {
            timer -= worldTickMs;
            continue;
        }
        timer = cadenceMs;
        queue.ReleaseDue(now);
        kernel.Begin(now);
        Candidate combat;
        combat.Key = "world.profile_combat";
        combat.ActionPriority = Priority::TrainedDamage;
        combat.RequiredResources = Uses(Resource::GlobalCooldown, Resource::Cast);
        combat.Attempt = [&]()
        {
            if (gcdEndsAtMs > now)
            {
                if (!spellQueue)
                    return Outcome::Retryable("global_cooldown");
                uint64 const readyAtMs = gcdEndsAtMs + 1;
                queue.Schedule("world.profile_combat", "global_cooldown",
                    uint8(Priority::TrainedDamage), readyAtMs, now);
                return Outcome::WaitUntil("global_cooldown", readyAtMs);
            }
            gcdEndsAtMs = now + gcdMs;
            ++casts;
            return Outcome::Submitted("native_action_submitted");
        };
        kernel.Submit(std::move(combat));
        kernel.Resolve();
        if (spellQueue)
        {
            if (gcdEndsAtMs > now)
                queue.Schedule("native.lock_release", "global_cooldown",
                    uint8(Priority::TrainedDamage), gcdEndsAtMs + 1, now);
            timer = queue.WakeDelayMs(now, timer);
        }
    }
    return casts;
}

int main()
{
    // 60 s of a hasted 1.2 s GCD allows 50 instants.
    int const oldDps = Replay(false, 1200, 100, 10);
    int const queuedDps = Replay(true, 1200, 100, 10);
    // The old one-second cadence of tanks and healers, with and without the
    // queue aligning the decision to the release.
    int const oldTank = Replay(false, 1500, 1000, 10);
    int const queuedTank = Replay(true, 1500, 1000, 10);
    std::printf("dps old=%d queued=%d tank old=%d queued=%d\n",
        oldDps, queuedDps, oldTank, queuedTank);
    assert(oldDps <= 40);
    assert(queuedDps >= 49);
    assert(oldTank <= 30);
    assert(queuedTank >= 39);
}
''')


def test_live_wiring_uses_the_spell_queue() -> None:
    decision = (BOTS / "BotWorldPopulationMgrUpdateBotDecision.cpp").read_text()
    release = decision.index("SpellQueue.ReleaseDue(")
    assert release < decision.index("PrepareValidationKernel(context);")
    align = decision.index("AlignDecisionTimerToSpellQueue(context);")
    assert decision.index("DecisionKernel.Resolve();") < align
    assert '\\"spell_queue\\":' in decision

    fallback = (BOTS / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text()
    assert "return ScheduleProfileCombatWait(context.State, context.Bot," in fallback

    candidates = (BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp").read_text()
    assert "return ScheduleNativeLockWait(context.State," in candidates

    module = (BOTS / "BotWorldPopulationMgrSpellQueue.cpp").read_text()
    assert "Outcome::WaitUntil(" in module
    assert "queue.WakeDelayMs(nowMs," in module

    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text()
    for name in ("BotSpellQueue.cpp", "BotSpellQueueNativeLock.cpp",
                 "BotWorldPopulationMgrSpellQueue.cpp"):
        assert f"Bots/{name}" in cmake
