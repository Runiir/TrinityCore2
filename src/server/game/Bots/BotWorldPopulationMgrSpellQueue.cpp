#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotSpellQueue.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Player.h"

namespace
{
constexpr char const* ProfileCombatKey = "world.profile_combat";
constexpr char const* NativeLockKey = "native.lock_release";
}

BotActionArbitration::Outcome BotWorldPopulationMgr::ScheduleProfileCombatWait(
    WorldBotState& state, Player* bot, ResolvedCombatAction const& action,
    BotActionResult result, BotActionArbitration::Outcome outcome)
{
    BotSpellQueue::Queue& queue = state.SpellQueue;
    uint64 const nowMs = BotWorldPopulationMgrSpellSemantics::NowMs();
    if ((result == BotActionResult::Ok || result == BotActionResult::Casting)
        && BotSpellQueue::IsGlobalCooldownProbe(action.SpellId))
        queue.GcdProbeSpellId = action.SpellId;

    // Queue the rotation for the exact GCD release instead of treating the
    // lock as a failed attempt.
    if (result == BotActionResult::GlobalCooldown)
        return ScheduleNativeLockWait(state, bot, ProfileCombatKey,
            BotActionArbitration::Priority::TrainedDamage, "global_cooldown",
            std::move(outcome));

    // Every legal action is waiting for a resource or cooldown that
    // regenerates on its own.  Poll at the combat cadence; exponential
    // backoff let a returning rune or energy tick sit unused for seconds.
    if (result == BotActionResult::NoAction
        && outcome.Result == BotActionArbitration::Disposition::Retryable
        && BotSpellQueue::IsRegenerationWaitReason(action.ResolutionReason))
    {
        uint64 const readyAtMs = nowMs + BotSpellQueue::RegenerationPollMs;
        queue.Schedule(ProfileCombatKey, action.ResolutionReason,
            uint8(BotActionArbitration::Priority::TrainedDamage), readyAtMs,
            nowMs);
        return BotActionArbitration::Outcome::WaitUntil(outcome.Reason,
            readyAtMs);
    }
    return outcome;
}

BotActionArbitration::Outcome BotWorldPopulationMgr::ScheduleNativeLockWait(
    WorldBotState& state, Player* bot, std::string const& key,
    BotActionArbitration::Priority priority, std::string const& reason,
    BotActionArbitration::Outcome outcome)
{
    if (reason != "global_cooldown" && reason != "already_casting")
        return outcome;

    BotSpellQueue::Queue& queue = state.SpellQueue;
    uint64 const nowMs = BotWorldPopulationMgrSpellSemantics::NowMs();
    BotSpellQueue::NativeLock const lock = BotSpellQueue::ObserveNativeLock(
        bot, queue.GcdProbeSpellId, nowMs);
    uint64 const readyAtMs = lock.Locked(nowMs) ? lock.ReleaseAtMs()
        : nowMs + BotSpellQueue::RegenerationPollMs;
    queue.Schedule(key, reason, uint8(priority), readyAtMs, nowMs);
    return BotActionArbitration::Outcome::WaitUntil(reason, readyAtMs);
}

void BotWorldPopulationMgr::AlignDecisionTimerToSpellQueue(
    BotUpdateContext& context)
{
    BotSpellQueue::Queue& queue = context.State.SpellQueue;
    if (!context.Bot->IsInCombat())
    {
        queue.Clear();
        return;
    }

    // The probe only supplies the GCD start recovery category, so any spell
    // the bot attempted (heals, totems, encounter actions) can seed it.
    if (!queue.GcdProbeSpellId && BotSpellQueue::IsGlobalCooldownProbe(
            context.State.LastCombatAttempt.SpellId))
        queue.GcdProbeSpellId = context.State.LastCombatAttempt.SpellId;

    // Whatever this decision submitted, the next useful action becomes legal
    // when the native lock clears.  Wake exactly then instead of on the next
    // fixed tick; the ordinary cadence still bounds the wait so movement and
    // mechanic reactions keep running during long casts.
    uint64 const nowMs = BotWorldPopulationMgrSpellSemantics::NowMs();
    BotSpellQueue::NativeLock const lock = BotSpellQueue::ObserveNativeLock(
        context.Bot, queue.GcdProbeSpellId, nowMs);
    if (lock.Locked(nowMs))
        queue.Schedule(NativeLockKey,
            lock.ChannelEndsAtMs == lock.ReleaseAtMs() ? "channel"
                : (lock.CastEndsAtMs == lock.ReleaseAtMs() ? "cast"
                    : "global_cooldown"),
            uint8(BotActionArbitration::Priority::TrainedDamage),
            lock.ReleaseAtMs(), nowMs);
    context.State.DecisionTimer = queue.WakeDelayMs(nowMs,
        context.State.DecisionTimer);
}
