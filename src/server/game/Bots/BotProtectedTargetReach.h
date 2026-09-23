#ifndef TRINITY_BOT_PROTECTED_TARGET_REACH_H
#define TRINITY_BOT_PROTECTED_TARGET_REACH_H

#include "Define.h"

#include <algorithm>

// Geometry used by the protected-encounter splash guard. Area spells, and
// callers that do not name a spell, keep the fixed target-centred radius.
// Hostile melee chain spells (Heart Strike, Avenger's Shield, Cleave) can only
// reach the units that Spell::SearchChainTargets would select, so the guard
// only looks inside that native envelope. Pure logic: the caller derives the
// shape from SpellInfo and the owner's spell modifiers.
namespace BotProtectedTargetReach
{
constexpr float AreaGuardRadius = 45.0f;
// Spell::SearchChainTargets: jump radius for SPELL_DAMAGE_CLASS_MELEE.
constexpr float MeleeChainJumpRadius = 5.0f;
// Unit::GetMeleeRange: combat reaches + 4/3, never below NOMINAL_MELEE_RANGE.
constexpr float MeleeRangeReachSlack = 1.3333334f;
constexpr float NominalMeleeRange = 5.0f;

enum class Anchor : uint8
{
    AreaGuard, // fixed radius around the selected target
    Target,    // chain search from the primary target
    Caster     // SPELL_ATTR2_CHAIN_FROM_CASTER: every jump starts at the caster
};

struct MeleeChainShape
{
    // Melee damage class whose only hostile multi-target effects are chains:
    // no area targets, persistent/area auras or multi-target trigger spells.
    bool PureMeleeChain = false;
    uint32 ChainTargets = 0;       // largest hostile ChainTarget after spell mods
    bool ChainFromCaster = false;  // SPELL_ATTR2_CHAIN_FROM_CASTER
    bool TreatAsAreaEffect = false; // SPELL_ATTR5_TREAT_AS_AREA_EFFECT, non-generic family
};

struct Reach
{
    Anchor From = Anchor::AreaGuard;
    float Radius = AreaGuardRadius;
    // SPELL_ATTR5_TREAT_AS_AREA_EFFECT widens the chain search by each
    // candidate's melee range to the caster.
    bool AddCandidateMeleeRange = false;
};

inline Reach Resolve(MeleeChainShape const& shape)
{
    if (!shape.PureMeleeChain || shape.ChainTargets <= 1)
        return {};
    // Chain-from-caster keeps the caster as every jump source, and each jump
    // requires IsWithinDist(candidate, jumpRadius), which includes both
    // combat reaches. The combat-reach-inclusive searcher matches that test.
    if (shape.ChainFromCaster)
        return { Anchor::Caster, MeleeChainJumpRadius, false };
    // Otherwise every chained unit must lie inside the area search of
    // jumpRadius * extra targets around the primary target's position.
    return { Anchor::Target,
        MeleeChainJumpRadius * float(shape.ChainTargets - 1),
        shape.TreatAsAreaEffect };
}

// Radius for a combat-reach-inclusive (AllWorldObjectsInRange) search around
// the anchor that collects a superset of the natively reachable units.
inline float CollectRadius(Reach const& reach, float ownerCombatReach)
{
    if (!reach.AddCandidateMeleeRange)
        return reach.Radius;
    return reach.Radius
        + std::max(ownerCombatReach + MeleeRangeReachSlack, NominalMeleeRange);
}

// Exact native test for a target-anchored chain: the area search measures
// the candidate's centre against the primary target's position in 2D, so a
// huge primary target's combat reach does not extend the chain. The height
// bound is ignored, which only admits more candidates.
inline bool TargetAnchoredCandidateInReach(Reach const& reach,
    float exactDist2dToTarget, float candidateMeleeRangeToOwner)
{
    float const hitbox = reach.AddCandidateMeleeRange ? candidateMeleeRangeToOwner : 0.0f;
    return exactDist2dToTarget <= reach.Radius + hitbox;
}
}

#endif
