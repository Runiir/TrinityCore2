#ifndef TRINITY_BOT_FALL_ADMISSION_H
#define TRINITY_BOT_FALL_ADMISSION_H

// A native fall is admitted transactionally.
//
// MotionMaster::MoveFall (and LaunchFallOnto, which repeats its body) sets the
// unit's MOVEMENTFLAG_FALLING and resets its fall time BEFORE the falling
// spline is launched, and MoveSplineInit::Launch may then refuse the launch: a
// passenger's fall whose body meets its transport's model emits nothing
// (ProvePassengerEffectSpline), as does an invalid spline. StopMoving clears
// neither the flag nor the fall time, and the GenericMovementGenerator the
// refused launch left in the controlled slot only expires at the next update,
// with no cleanup (BWD 10N round 3 review): the bot stood motionless with
// FALLING set, so the swim and walk code saw it as airborne and its landing
// was owed for a fall that never started.
//
// Capture() records the two things a fall launch sets before it can be
// refused; after a launch that started no fall spline RollBack() puts them
// back exactly as they were (a fall continued after a landing without floor
// already had FALLING set: it stays set, with its fall time) and removes the
// launch's stale effect generator, but only one whose spline is finished, so a
// running spline's generator is never touched. After a launch that started the
// spline nothing is rolled back.
// Pure: Traits names the real enumerators (Falling, Controlled, Effect), the
// bot is a Player (or a stand-in with the same members).

#include <cstdint>

namespace BotFallAdmission
{
struct Saved
{
    bool Falling = false;
    std::uint32_t FallTime = 0;
};

template <class Traits, class Bot>
Saved Capture(Bot const& bot)
{
    Saved saved;
    saved.Falling = bot.HasUnitMovementFlag(Traits::Falling);
    saved.FallTime = bot.m_movementInfo.GetFallTime();
    return saved;
}

template <class Traits, class Bot>
void RollBack(Bot& bot, Saved const& saved)
{
    if (!saved.Falling)
        bot.RemoveUnitMovementFlag(Traits::Falling);
    bot.m_movementInfo.SetFallTime(saved.FallTime);
    // The refused launch's generator: an effect generator in the controlled
    // slot with no spline running (a live spline's generator stays).
    if (bot.movespline->Finalized()
        && bot.GetMotionMaster()->GetMotionSlotType(Traits::Controlled) == Traits::Effect)
        bot.GetMotionMaster()->Clear(Traits::Controlled);
}
}

#endif
