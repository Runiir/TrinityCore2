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


def test_release_latency_excludes_paused_decision_loops(tmp_path: Path) -> None:
    # Live Magmaw runs reported 115-224 ms mean release latency and a 3-9 s
    # maximum per bot: each maximum matched the longest heartbeat world stall
    # of that run, and a bot that died and was revived reported 42 s.  The
    # queue must describe its own lateness, not how long the loop was paused.
    compile_and_run(tmp_path, "paused_latency", r'''
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
    static_assert(PausedReleaseGapMs > CombatDecisionIntervalMs,
        "an ordinary combat decision must never count as a pause");

    Queue queue;
    // Continuous 100 ms decisions: a release 30 ms late is scheduler latency.
    queue.ReleaseDue(1000);
    queue.Schedule("world.profile_combat", "global_cooldown", 60, 1070, 1000);
    assert(queue.ReleaseDue(1100) == 1);

    // A heartbeat stalls the world thread for 3.6 s while an intent is due.
    queue.Schedule("world.profile_combat", "global_cooldown", 60, 1150, 1100);
    assert(queue.ReleaseDue(4700) == 1);
    std::string json = queue.ToJson(4700);
    assert(Contains(json, "\"released\":2"));
    assert(Contains(json, "\"released_after_pause\":1"));
    assert(Contains(json, "\"mean_release_latency_ms\":30"));
    assert(Contains(json, "\"max_release_latency_ms\":30"));

    // The next ordinary decision counts again.
    queue.Schedule("native.lock_release", "cast", 60, 4750, 4700);
    assert(queue.ReleaseDue(4800) == 1);
    json = queue.ToJson(4800);
    assert(Contains(json, "\"released\":3"));
    assert(Contains(json, "\"released_after_pause\":1"));
    assert(Contains(json, "\"mean_release_latency_ms\":40"));
    assert(Contains(json, "\"max_release_latency_ms\":50"));

    // A bot that dies keeps its pending intent until the kernel runs again
    // after the revive; that release is not a 42 s scheduler delay.
    queue.Schedule("raid.support.heal.30005", "already_casting", 100, 4900, 4800);
    assert(queue.ReleaseDue(47000) == 1);
    json = queue.ToJson(47000);
    assert(Contains(json, "\"released_after_pause\":2"));
    assert(Contains(json, "\"max_release_latency_ms\":50"));

    // A gap at the pause bound still counts as an ordinary decision.
    queue.Schedule("world.profile_combat", "global_cooldown", 60, 47100, 47000);
    assert(queue.ReleaseDue(47000 + PausedReleaseGapMs) == 1);
    json = queue.ToJson(47000 + PausedReleaseGapMs);
    assert(Contains(json, "\"released_after_pause\":2"));
    assert(Contains(json, "\"max_release_latency_ms\":400"));
}
''')


def test_only_the_gcd_is_waited_for_exactly(tmp_path: Path) -> None:
    # Review of 585abda09c: a healer that failed with already_casting waited
    # for the full cast end (up to 3 s) on its per-target heal key.  A hazard
    # move interrupts that cast, and the emergency heal then sat blocked.
    compile_and_run(tmp_path, "lock_retry", r'''
#include "Bots/BotActionArbiter.h"
#include "Bots/BotSpellQueue.h"
#include <cassert>

using namespace BotActionArbitration;
using namespace BotSpellQueue;

int main()
{
    uint64 const now = 10000;
    NativeLock gcd;
    gcd.GlobalCooldownEndsAtMs = now + 1200;
    assert(LockRetryAtMs(gcd, now) == now + 1200);

    NativeLock cast;
    cast.GlobalCooldownEndsAtMs = now + 900;
    cast.CastEndsAtMs = now + 2500;
    assert(LockRetryAtMs(cast, now) == now + CombatDecisionIntervalMs);

    NativeLock channel;
    channel.ChannelEndsAtMs = now + 3000;
    assert(LockRetryAtMs(channel, now) == now + CombatDecisionIntervalMs);
    assert(cast.Casting(now) && channel.Casting(now) && !gcd.Casting(now));

    // A cast about to finish is still re-checked at its own end.
    NativeLock finishing;
    finishing.CastEndsAtMs = now + 40;
    assert(LockRetryAtMs(finishing, now) == now + 40);

    // An expired cast leaves only the GCD, which is exact again.
    NativeLock expired;
    expired.GlobalCooldownEndsAtMs = now + 700;
    expired.CastEndsAtMs = now - 1;
    assert(LockRetryAtMs(expired, now) == now + 700);

    // No observable lock: poll at the regeneration cadence.
    assert(LockRetryAtMs(NativeLock{}, now) == now + RegenerationPollMs);

    // Kernel replay: the heal key that met already_casting is eligible again
    // one combat decision later, long before the interrupted cast would have
    // ended, and the retry never counts as a failure.
    Kernel kernel;
    std::string const key = "raid.support.heal.30007";
    kernel.Observe(key, Outcome::WaitUntil("already_casting",
        LockRetryAtMs(cast, now)), now, 100, 3000, 5);
    Lifecycle const* heal = kernel.FindLifecycle(key);
    assert(heal->RetryAfterMs == now + CombatDecisionIntervalMs);
    assert(heal->ConsecutiveFailures == 0);
}
''')


def test_timed_wait_preserves_the_failure_streak(tmp_path: Path) -> None:
    # Review of 585abda09c: every timed wait zeroed ConsecutiveFailures and
    # FirstFailureAtMs, so a candidate that alternated a real failure with a
    # GCD wait could never escalate.
    compile_and_run(tmp_path, "wait_streak", r'''
#include "Bots/BotActionArbiter.h"
#include <cassert>

using namespace BotActionArbitration;

int main()
{
    Kernel kernel;
    std::string const key = "world.profile_combat";
    uint64 now = 1000;
    for (int attempt = 0; attempt < 4; ++attempt, now += 1000)
    {
        kernel.Observe(key, Outcome::Retryable("cast_failed"), now, 100, 3000, 5);
        kernel.Observe(key, Outcome::WaitUntil("global_cooldown", now + 500),
            now + 1, 100, 3000, 5);
        Lifecycle const* lifecycle = kernel.FindLifecycle(key);
        assert(lifecycle->ConsecutiveFailures == uint32(attempt + 1));
        assert(lifecycle->FirstFailureAtMs == 1000);
        assert(lifecycle->RetryAfterMs == now + 500);
    }
    kernel.Observe(key, Outcome::Retryable("cast_failed"), now, 100, 3000, 5);
    assert(kernel.FindLifecycle(key)->ConsecutiveFailures == 5);
    assert(kernel.ShouldEscalate(key, now, 3000));

    // A timed wait on a fresh key still starts no streak, and a commit
    // still clears one.
    kernel.Observe("fresh", Outcome::WaitUntil("global_cooldown", 1500), 1000, 100, 3000, 5);
    assert(kernel.FindLifecycle("fresh")->ConsecutiveFailures == 0);
    assert(kernel.FindLifecycle("fresh")->FirstFailureAtMs == 0);
    kernel.Observe(key, Outcome::Submitted("native_action_submitted"), now, 100, 3000, 5);
    assert(kernel.FindLifecycle(key)->ConsecutiveFailures == 0);
    assert(kernel.FindLifecycle(key)->FirstFailureAtMs == 0);
}
''')


def test_clear_is_cheap_and_complete(tmp_path: Path) -> None:
    compile_and_run(tmp_path, "queue_clear", r'''
#include "Bots/BotSpellQueue.h"
#include <cassert>

using namespace BotSpellQueue;

int main()
{
    Queue queue;
    queue.Clear();
    assert(queue.Empty());
    queue.Schedule("raid.support.heal.30005", "already_casting", 100, 2000, 1000);
    queue.Schedule("world.profile_combat", "global_cooldown", 60, 1500, 1000);
    queue.Clear();
    assert(queue.Empty());
    assert(queue.WakeDelayMs(1000, 100) == 100);
    assert(queue.ReleaseDue(5000) == 0);
}
''')


def test_queue_is_cleared_on_death_and_combat_end_before_any_gate() -> None:
    preparation = (BOTS / "BotWorldPopulationMgrUpdateBotPreparation.cpp").read_text()
    body = preparation[preparation.index("bool BotWorldPopulationMgr::PrepareBotUpdate("):]
    clear = body.index("context.State.SpellQueue.Clear();")
    assert "!context.Bot->IsAlive() || !context.Bot->IsInCombat()" in body[:clear]
    assert "return false;" not in body[:clear]
    assert clear < body.index("HandleBotDeath(context.State, context.Bot, context.Diff);")

    module = (BOTS / "BotWorldPopulationMgrSpellQueue.cpp").read_text()
    wait = module[module.index("::ScheduleNativeLockWait("):]
    assert "BotSpellQueue::LockRetryAtMs(lock, nowMs)" in wait
    assert "lock.ReleaseAtMs()" not in wait[:wait.index("void BotWorldPopulationMgr::")]


def test_heal_attempt_skips_selection_while_casting() -> None:
    # Review of this batch: a 100 ms re-check during a cast re-ran heal
    # selection, the protected-target grid search and a LOS raycast before
    # TryCastFriendlySpell reported already_casting.
    candidates = (BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp").read_text()
    attempt = candidates[candidates.index('"heal_target_stale");'):]
    precheck = attempt.index(".Casting(lockNowMs))")
    assert "BotSpellQueue::ObserveNativeLock(context.Bot," in attempt[:precheck]
    assert precheck < attempt.index("SelectHealSpell(context.Bot,")
    assert precheck < attempt.index("TryCastFriendlySpell(")
    wait = attempt[precheck:attempt.index("bool const instantHealRequired")]
    assert "return ScheduleNativeLockWait(context.State," in wait
    assert '"already_casting"' in wait


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
