#ifndef TRINITY_BOT_MAGMAW_DAMAGE_TARGET_BINDING_H
#define TRINITY_BOT_MAGMAW_DAMAGE_TARGET_BINDING_H

#include "ObjectGuid.h"

namespace BotEncounter
{
enum class MagmawDamageTargetBindResult : uint8
{
    NotRequested,
    Cleared,
    NativeMissing,
    NativeDead,
    NativeInvalid,
    Bound
};

template<class Context, class Target>
MagmawDamageTargetBindResult BindMagmawDamageTarget(Context& context,
    ObjectGuid proposedTarget, bool clearOptionalTarget, Target* nativeTarget)
{
    if (clearOptionalTarget)
    {
        if (!proposedTarget.IsEmpty())
            return MagmawDamageTargetBindResult::NativeInvalid;
        context.Target = nullptr;
        context.State.TargetGuid.Clear();
        return MagmawDamageTargetBindResult::Cleared;
    }
    if (proposedTarget.IsEmpty())
        return MagmawDamageTargetBindResult::NotRequested;
    if (!nativeTarget || nativeTarget->GetGUID() != proposedTarget)
        return MagmawDamageTargetBindResult::NativeMissing;
    if (!nativeTarget->IsAlive())
        return MagmawDamageTargetBindResult::NativeDead;
    if (!context.Bot || !context.Bot->IsValidAttackTarget(nativeTarget))
        return MagmawDamageTargetBindResult::NativeInvalid;

    context.Target = nativeTarget;
    context.State.TargetGuid = proposedTarget;
    return MagmawDamageTargetBindResult::Bound;
}
}

#endif
