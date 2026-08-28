#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "ChaseMovementGenerator.h"
#include "Creature.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <optional>
#include <string>
#include <utility>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

void BotWorldPopulationMgr::BeginMeleeAutoAttackDecision(
    WorldBotState& state, Player* bot)
{
    state.MeleeAutoAttackLane.Begin(NowMs());
    state.LastMeleeAutoAttackCandidateCount = 0;

    // Availability is an observation that produces a typed safety candidate;
    // it is not a second native stop owner. The scope-exit reconciler handles
    // early returns through the same deterministic lane.
    if (!bot || !bot->IsInWorld() || !bot->IsAlive())
        SubmitMeleeAutoAttackIntent(state, BotMeleeAutoAttack::Kind::Suppress,
            ObjectGuid::Empty, BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal, "player_unavailable");
}

bool BotWorldPopulationMgr::SubmitMeleeAutoAttackIntent(
    WorldBotState& state, BotMeleeAutoAttack::Kind kind, ObjectGuid target,
    BotMeleeAutoAttack::Owner owner,
    BotActionArbitration::Priority priority, char const* reason)
{
    BotMeleeAutoAttack::Intent intent;
    intent.Toggle = kind;
    intent.IntentOwner = owner;
    intent.ActionPriority = priority;
    intent.Target = target;
    intent.Reason = reason ? reason : "unspecified";
    bool const submitted = state.MeleeAutoAttackLane.Submit(std::move(intent));
    state.LastMeleeAutoAttackCandidateCount = uint32(
        state.MeleeAutoAttackLane.CandidateCount());
    return submitted;
}

void BotWorldPopulationMgr::ResolveAndReconcileMeleeAutoAttack(
    WorldBotState& state, Player* bot)
{
    state.LastMeleeAutoAttackReconcileMs = NowMs();

    // Re-observe hard masks after all producers have run. A route may close
    // offense authority in the same tick in which a lower-priority profile
    // proposed a start/switch. Selecting here prevents even one unwanted
    // white swing while retaining ordinary movement-time autoattack uptime.
    if (!bot || !bot->IsInWorld() || !bot->IsAlive())
        SubmitMeleeAutoAttackIntent(state, BotMeleeAutoAttack::Kind::Suppress,
            ObjectGuid::Empty, BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal, "player_unavailable");
    else if (BotRaidAreaAuthority::IsAllOffenseSuppressed(
        bot->GetGUID().GetRawValue()))
        SubmitMeleeAutoAttackIntent(state, BotMeleeAutoAttack::Kind::Suppress,
            ObjectGuid::Empty, BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "all_offense_suppressed");
    else if (!state.TargetGuid.IsEmpty()
        && !state.DesiredMeleeAttackTargetGuid.IsEmpty()
        && state.TargetGuid != state.DesiredMeleeAttackTargetGuid)
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::StartOrSwitch, state.TargetGuid,
            BotMeleeAutoAttack::Owner::TargetSelection,
            BotActionArbitration::Priority::TrainedDamage,
            "observed_target_switch");

    state.LastMeleeAutoAttackCandidateCount = uint32(
        state.MeleeAutoAttackLane.CandidateCount());
    std::optional<BotMeleeAutoAttack::Intent> selected =
        state.MeleeAutoAttackLane.Resolve();
    if (selected)
    {
        state.LastMeleeAutoAttackIntentOwner =
            BotMeleeAutoAttack::ToString(selected->IntentOwner);
        state.LastMeleeAutoAttackIntentKind =
            BotMeleeAutoAttack::ToString(selected->Toggle);
        state.LastMeleeAutoAttackIntentReason = selected->Reason;
        state.LastMeleeAutoAttackIntentPriority =
            uint8(selected->ActionPriority);
    }

    auto stopNativeToggle = [&](char const* outcome)
    {
        // This is the sole player AttackStop owner. Pet and controlled-unit
        // attack state remains independently reconciled through pet commands.
        if (bot && bot->GetVictim())
            bot->AttackStop();
        state.DesiredMeleeAttackTargetGuid.Clear();
        state.LastMeleeAutoAttackOutcome = outcome;
    };

    if (selected && selected->Toggle != BotMeleeAutoAttack::Kind::StartOrSwitch)
    {
        bool const suppressed = selected->Toggle
            == BotMeleeAutoAttack::Kind::Suppress;
        stopNativeToggle(suppressed
            ? "native_toggle_suppressed" : "native_toggle_stopped");
        state.MeleeAutoAttackState = suppressed ? "suppressed" : "inactive";
        state.MeleeAutoAttackSuppressionReason = selected->Reason;
        return;
    }

    if (selected)
        state.DesiredMeleeAttackTargetGuid = selected->Target;
    if (state.DesiredMeleeAttackTargetGuid.IsEmpty())
    {
        state.MeleeAutoAttackState = "inactive";
        state.MeleeAutoAttackSuppressionReason.clear();
        state.LastMeleeAutoAttackOutcome = "no_desired_toggle";
        return;
    }

    Unit* target = bot ? ObjectAccessor::GetUnit(*bot,
        state.DesiredMeleeAttackTargetGuid) : nullptr;
    bool protectedTarget = false;
    if (bot)
        if (Creature const* creature = target ? target->ToCreature() : nullptr)
            protectedTarget = BotRaidAreaAuthority::IsProtectedEncounterTarget(
                bot->GetGUID().GetRawValue(), creature->GetEntry(),
                creature->GetSpawnId(), creature->GetGUID().GetRawValue());
    if (!bot || !bot->IsInWorld() || !bot->IsAlive() || !target
        || !target->IsInWorld() || !target->IsAlive()
        || !bot->IsValidAttackTarget(target) || protectedTarget)
    {
        char const* reason = protectedTarget
            ? "protected_encounter_target" : "target_invalid";
        stopNativeToggle("native_toggle_rejected");
        state.MeleeAutoAttackState = "suppressed";
        state.MeleeAutoAttackSuppressionReason = reason;
        state.LastMeleeAutoAttackIntentOwner = "safety";
        state.LastMeleeAutoAttackIntentKind = "suppress";
        state.LastMeleeAutoAttackIntentReason = reason;
        state.LastMeleeAutoAttackIntentPriority = uint8(
            BotActionArbitration::Priority::Terminal);
        return;
    }

    if (bot->GetVictim() && bot->GetVictim() != target)
        bot->AttackStop();
    // This is the sole player Attack owner. Binding does not require current
    // reach: native swing legality resumes automatically after movement.
    bool const attackBound = bot->Attack(target, true)
        || bot->GetVictim() == target;
    state.MeleeAutoAttackState = attackBound
        ? (bot->IsWithinMeleeRange(target) && bot->IsWithinLOSInMap(target)
            ? "swing_ready" : "toggle_bound_moving_to_range")
        : "toggle_retryable";
    state.MeleeAutoAttackSuppressionReason = attackBound
        ? std::string() : "native_attack_rejected";
    state.LastMeleeAutoAttackOutcome = attackBound
        ? (bot->IsWithinMeleeRange(target) && bot->IsWithinLOSInMap(target)
            ? "native_swing_ready" : "native_toggle_bound_awaiting_range")
        : "native_toggle_retryable";
}

bool BotWorldPopulationMgr::MoveBotToProfileRange(WorldBotState& state, Player* bot, Unit* reference,
    ResolvedCombatAction const* action, bool forceRangedReposition)
{
    if (!bot || !reference)
        return false;

    auto moveToTerrainProjectedPoint = [&](float x, float y, float z)
    {
        Map* map = bot->GetMap();
        if (!map)
            return false;

        float floorZ = map->GetHeight(bot->GetPhaseShift(), x, y, z + 2.0f, true, 64.0f);
        if (floorZ == INVALID_HEIGHT)
            return false;

        return MoveBotToPoint(state, bot, x, y, floorZ, false,
            BotMovementArbitration::Owner::CombatRange,
            BotMovementArbitration::Priority::Combat);
    };

    std::string role = GetDungeonRole(bot);
    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role.c_str());
    std::string directive = action && !action->MovementDirective.empty() ? action->MovementDirective : profile.MovementDirective;
    float minRange = action && action->MinRange > 0.0f ? action->MinRange : profile.MinRange;
    float maxRange = action && action->MaxRange > 0.0f ? action->MaxRange : profile.MaxRange;

    if (profile.MissingProfile || directive.empty())
        return false;

    // Auto-attack is a persistent native toggle, not a rotation candidate.
    // Bind it before movement so a melee player chases the same victim and
    // white swings resume immediately whenever native melee reach is legal.
    if (action && action->AutoAttackMode == "melee")
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::StartOrSwitch,
            reference->GetGUID(), BotMeleeAutoAttack::Owner::Profile,
            BotActionArbitration::Priority::TrainedDamage,
            "profile_move_to_melee_range");

    if (action && action->SpellId == 5221 && directive == "melee_behind")
    {
        // Rerun207 canary 4 proved that Cat Form and the rest of the Feral DPS
        // rotation were live, but all 32 failures were native Shred result 59:
        // the resolver selected a legal resource/range candidate while the bot
        // was still in the target's forbidden front arc.  Keep native spell
        // legality authoritative and use the existing path validator to reach
        // a collision-safe point inside melee range behind this exact target.
        float const rearRange = std::max(2.0f,
            std::min(bot->GetMeleeRange(reference) - 0.5f,
                bot->GetCombatReach() + reference->GetCombatReach() + 0.5f));
        float nativeFrontArc = float(M_PI);
        if (Creature const* creature = reference->ToCreature();
            creature && creature->HasStaticFlag(CREATURE_STATIC_FLAG_5_240_DEGREE_BACK_ARC))
            nativeFrontArc -= float(M_PI) / 3.0f;

        for (float rearOffset : { 0.0f, float(M_PI) / 12.0f,
            -float(M_PI) / 12.0f, float(M_PI) / 6.0f,
            -float(M_PI) / 6.0f })
        {
            Position rearPosition = reference->GetFirstCollisionPosition(
                rearRange, float(M_PI) + rearOffset);
            if (reference->HasInArc(nativeFrontArc, &rearPosition))
                continue;
            if (moveToTerrainProjectedPoint(rearPosition.GetPositionX(),
                rearPosition.GetPositionY(), rearPosition.GetPositionZ()))
                return true;
        }
        return false;
    }

    if (directive == "melee" || (minRange <= 0.0f && maxRange <= 5.0f))
    {
        // A live melee target owns the native chase destination.  Do not
        // project its actor elevation through the static floor gate first: large
        // bosses and vehicle-like actors can report a model origin outside
        // the walkable floor even while their same-map collision body is
        // attackable.  The dynamic-target planner deliberately bypasses
        // static floor admission and MotionMaster performs the ordinary
        // player chase without inventing a point or teleporting.
        float const targetX = reference->GetPositionX();
        float const targetY = reference->GetPositionY();
        return MoveBotToPoint(state, bot, targetX, targetY,
            bot->GetPositionZ(), false,
            BotMovementArbitration::Owner::CombatRange,
            BotMovementArbitration::Priority::Combat, reference);
    }

    // A small center-to-center offset is not enough around bosses with a large
    // combat reach: the movement can finish while the ranged weapon is still
    // inside its hostile minimum range.  Use a stable ranged band for every
    // real dead-zone escape, while retaining the profile maximum as the cap.
    // When the selected action is shorter-ranged than the profile's ordinary
    // lane, preserve its declared priority with the smallest useful inward
    // correction.  The general ranged mover deliberately uses broad four-yard
    // steps, but that overshoots a legal edge-range action such as Shadowflame
    // and can also fail to find a same-floor path for a sub-yard correction.
    // Stay just inside the native envelope; the core still revalidates range
    // before accepting the later cast.
    bool const preciseMaximumRangeApproach = action && minRange <= 0.0f
        && maxRange > 5.0f && profile.MaxRange > maxRange;
    float const maximumRangeSafetyMargin = preciseMaximumRangeApproach
        ? 0.40f : 1.0f;
    float desiredRange = preciseMaximumRangeApproach
        ? std::max(5.0f, maxRange - maximumRangeSafetyMargin)
        : (minRange > 0.0f
            ? std::max(12.0f, minRange + 4.0f)
            : std::max(12.0f, std::min(maxRange - 2.0f, 25.0f)));
    if (maxRange > 0.0f)
        desiredRange = std::min(desiredRange, std::max(5.0f,
            maxRange - (preciseMaximumRangeApproach
                ? maximumRangeSafetyMargin : 2.0f)));
    desiredRange = std::max(5.0f, desiredRange);

    float distance = bot->GetExactDist(reference);
    if (!forceRangedReposition && distance >= desiredRange - 1.0f
        && (maxRange <= 0.0f || distance <= maxRange - maximumRangeSafetyMargin)
        && bot->IsWithinLOSInMap(reference))
        return false;

    if (preciseMaximumRangeApproach && distance > desiredRange)
    {
        // Follow the already-proven complete mmap route toward the target and
        // stop at its first sampled point inside the legal spell envelope.
        // A chase generator aims at the target's collision body, which can be
        // across a courtyard ledge even when an earlier point on the same
        // native path is a legal player casting position.
        PathGenerator approachPath(bot);
        if (approachPath.CalculatePath(reference->GetPositionX(),
                reference->GetPositionY(), reference->GetPositionZ(), false))
        {
            PathType const approachType = approachPath.GetPathType();
            bool const completeNativeApproach =
                !(approachType & (PATHFIND_NOPATH | PATHFIND_NOT_USING_PATH
                    | PATHFIND_INCOMPLETE | PATHFIND_SHORTCUT
                    | PATHFIND_FARFROMPOLY));
            Movement::PointsArray const& points = approachPath.GetPath();
            if (completeNativeApproach && points.size() >= 2)
                for (std::size_t index = 1; index < points.size(); ++index)
                {
                    G3D::Vector3 const& from = points[index - 1];
                    G3D::Vector3 const& to = points[index];
                    float const segmentX = to.x - from.x;
                    float const segmentY = to.y - from.y;
                    float const segmentZ = to.z - from.z;
                    float const segmentLength = std::sqrt(segmentX * segmentX
                        + segmentY * segmentY + segmentZ * segmentZ);
                    uint32 const sampleCount = std::max<uint32>(1,
                        uint32(std::ceil(segmentLength / 0.5f)));
                    for (uint32 sample = 1; sample <= sampleCount; ++sample)
                    {
                        float const t = float(sample) / float(sampleCount);
                        float const x = from.x + segmentX * t;
                        float const y = from.y + segmentY * t;
                        float const z = from.z + segmentZ * t;
                        float const candidateRange = reference->GetExactDist(x, y, z);
                        if (candidateRange > desiredRange || candidateRange < 5.0f)
                            continue;
                        // Preserve its native path height: a terrain ray at
                        // the same X/Y can select the other side of the ledge.
                        if (MoveBotToPoint(state, bot, x, y, z, false,
                                BotMovementArbitration::Owner::CombatRange,
                                BotMovementArbitration::Priority::Combat))
                            return true;
                    }
                }
        }

        // The full path to the hostile can be valid even when its final point
        // is on the other side of a terrain shelf.  Resolve deterministic
        // target-centered ring points against the target's observed floor,
        // then let the ordinary point mover require a complete mmap path from
        // the player.  Projecting these X/Y points from the ranged bot's Z can
        // select the upper shelf (or no floor) and made a legal short-range
        // self-centered action permanently unreachable.
        if (Map* map = bot->GetMap())
        {
            float const baseAngle = reference->GetAngle(bot);
            for (float const ringRange : { desiredRange,
                std::max(5.25f, desiredRange - 0.75f) })
                for (uint8 ringIndex = 0; ringIndex < 16; ++ringIndex)
                {
                    int8 const signedStep = ringIndex == 0 ? 0
                        : (ringIndex % 2 ? int8((ringIndex + 1) / 2)
                                         : -int8(ringIndex / 2));
                    float const angle = baseAngle
                        + float(signedStep) * float(M_PI) / 8.0f;
                    float const x = reference->GetPositionX()
                        + std::cos(angle) * ringRange;
                    float const y = reference->GetPositionY()
                        + std::sin(angle) * ringRange;
                    float const z = map->GetHeight(bot->GetPhaseShift(), x, y,
                        reference->GetPositionZ() + 4.0f, true, 64.0f);
                    if (!std::isfinite(z) || z <= INVALID_HEIGHT)
                        continue;
                    float const candidateRange = reference->GetExactDist(x, y, z);
                    if (candidateRange < 5.0f
                        || candidateRange > maxRange - maximumRangeSafetyMargin)
                        continue;
                    if (MoveBotToPoint(state, bot, x, y, z, false,
                            BotMovementArbitration::Owner::CombatRange,
                            BotMovementArbitration::Priority::Combat))
                        return true;
                }
        }

        // GetFirstCollisionPosition is intentionally optimized for ordinary
        // multi-yard movement and can collapse a sub-yard ray back to the
        // current point. Keep the exact desired range, but add a small lateral
        // component so the complete native mmap path has a real segment to
        // validate. Both deterministic sides retain normal terrain, lease, and
        // native motion authority.
        float const deltaX = reference->GetPositionX() - bot->GetPositionX();
        float const deltaY = reference->GetPositionY() - bot->GetPositionY();
        float const planarDistance = std::sqrt(deltaX * deltaX + deltaY * deltaY);
        float const verticalDelta = reference->GetPositionZ() - bot->GetPositionZ();
        float const desiredPlanarDistance = std::sqrt(std::max(0.0f,
            desiredRange * desiredRange - verticalDelta * verticalDelta));
        if (planarDistance > 0.001f && desiredPlanarDistance > 0.001f)
        {
            float const radialAngle = reference->GetAngle(bot);
            // The closest point can sit across a ledge or a missing polygon.
            // Widen the deterministic same-ring arc until mmap finds a
            // complete player-walkable route; every candidate still ends at
            // the exact legal spell radius and passes MoveBotToPoint.
            for (float const nativePathSegment : { 1.5f, 3.0f, 5.0f, 7.0f })
            {
                float const cosine = std::clamp(
                    (planarDistance * planarDistance
                        + desiredPlanarDistance * desiredPlanarDistance
                        - nativePathSegment * nativePathSegment)
                        / (2.0f * planarDistance * desiredPlanarDistance),
                    -1.0f, 1.0f);
                float const lateralAngle = std::acos(cosine);
                for (float const side : { 1.0f, -1.0f })
                {
                    float const angle = radialAngle + side * lateralAngle;
                    float const x = reference->GetPositionX()
                        + std::cos(angle) * desiredPlanarDistance;
                    float const y = reference->GetPositionY()
                        + std::sin(angle) * desiredPlanarDistance;
                    if (moveToTerrainProjectedPoint(x, y, bot->GetPositionZ()))
                        return true;
                }
            }
        }

    }

    // A party member already casting from a legal ranged lane is stronger
    // navigation evidence than a ray projected out of a large boss model.
    // Try small perpendicular spread offsets first and the member's exact
    // point last. The normal path validator and hazard controller remain
    // authoritative, so this cannot force an off-mesh or unsafe destination.
    Player* partyRangedAnchor = nullptr;
    if (Group* group = bot->GetGroup())
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            if (Player* member = itr->GetSource(); member && member != bot && member->IsAlive()
                && member->GetMap() == bot->GetMap() && std::string(GetDungeonRole(member)) == "healer")
            {
                float memberRange = member->GetExactDist(reference);
                if (memberRange >= (minRange > 0.0f ? minRange + 1.0f : 5.0f)
                    && (maxRange <= 0.0f
                        || memberRange <= maxRange - maximumRangeSafetyMargin))
                {
                    partyRangedAnchor = member;
                    break;
                }
            }

    if (partyRangedAnchor)
    {
        float tangentAngle = reference->GetAngle(partyRangedAnchor) + float(M_PI_2);
        for (float spread : { 3.0f, -3.0f, 0.0f })
        {
            float x = partyRangedAnchor->GetPositionX() + std::cos(tangentAngle) * spread;
            float y = partyRangedAnchor->GetPositionY() + std::sin(tangentAngle) * spread;
            Position rangedPosition;
            rangedPosition.Relocate(x, y, partyRangedAnchor->GetPositionZ(), tangentAngle);
            float candidateRange = reference->GetExactDist(rangedPosition);
            if (candidateRange < (minRange > 0.0f ? minRange + 1.0f : 5.0f)
                || (maxRange > 0.0f
                    && candidateRange > maxRange - maximumRangeSafetyMargin))
                continue;
            if (moveToTerrainProjectedPoint(x, y, rangedPosition.GetPositionZ()))
                return true;
        }
    }

    // Boss origins are often outside or on the edge of the navigable polygon.
    // Project from the bot's known-good polygon instead: move radially away
    // when inside the ranged band and toward the target when outside it. This
    // avoids collision rays being truncated at the boss model before the
    // hunter has cleared the hostile minimum range.
    bool movingOutward = distance < desiredRange - 1.0f;
    float absoluteBearing = movingOutward ? reference->GetAngle(bot) : bot->GetAngle(reference);
    float relativeBearing = absoluteBearing - bot->GetOrientation();
    float const minimumTravelDistance = preciseMaximumRangeApproach
        ? 0.10f : 4.0f;
    float const minimumMovementDistance = preciseMaximumRangeApproach
        ? 0.05f : 1.0f;
    float travelDistance = std::max(minimumTravelDistance,
        std::fabs(desiredRange - distance) + (movingOutward ? 2.0f : 0.0f));
    float minimumCandidateRange = movingOutward
        ? std::max(minRange > 0.0f ? minRange + 1.0f : 5.0f, desiredRange - 1.0f)
        : (minRange > 0.0f ? minRange + 1.0f : 5.0f);
    for (float angleOffset : { 0.0f, float(M_PI_4) / 2.0f, -float(M_PI_4) / 2.0f, float(M_PI_4), -float(M_PI_4) })
    {
        Position rangedPosition = bot->GetFirstCollisionPosition(travelDistance, relativeBearing + angleOffset);
        float candidateRange = reference->GetExactDist(rangedPosition);
        if (candidateRange < minimumCandidateRange
            || (maxRange > 0.0f
                && candidateRange > maxRange - maximumRangeSafetyMargin)
            || bot->GetExactDist(rangedPosition) < minimumMovementDistance)
            continue;
        if (moveToTerrainProjectedPoint(rangedPosition.GetPositionX(), rangedPosition.GetPositionY(), rangedPosition.GetPositionZ()))
            return true;
    }

    // If the ranged bot is pinned at an arena wall, require a tank to have a
    // legal melee anchor and search geometric firing rings around the target.
    // Do not use a collision ray whose origin is the boss or whose radius is
    // measured from the tank: large boss models truncate the former, while
    // the latter can still place the hunter inside the hostile minimum range.
    // Every candidate is terrain-projected and must pass the normal complete
    // mmap path validation before it can become a one-shot point movement.
    Player* tankAnchor = nullptr;
    if (Group* group = bot->GetGroup())
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            if (Player* member = itr->GetSource(); member && member->IsAlive()
                && member->GetMap() == bot->GetMap() && std::string(GetDungeonRole(member)) == "tank"
                && member->GetExactDist(reference) <= 12.0f)
            {
                tankAnchor = member;
                break;
            }

    if (tankAnchor)
    {
        float minimumRingRange = minRange > 0.0f ? minRange + 1.0f : 5.0f;
        float ringRanges[] = { desiredRange, std::max(minimumRingRange, desiredRange - 2.0f) };
        float baseAngle = reference->GetAngle(bot);
        for (float ringRange : ringRanges)
        {
            for (uint8 ringIndex = 0; ringIndex < 16; ++ringIndex)
            {
                float angle = baseAngle + float(ringIndex) * float(M_PI) / 8.0f;
                Position rangedPosition;
                rangedPosition.Relocate(
                    reference->GetPositionX() + std::cos(angle) * ringRange,
                    reference->GetPositionY() + std::sin(angle) * ringRange,
                    reference->GetPositionZ(), angle);
                float candidateRange = reference->GetExactDist(rangedPosition);
                if (candidateRange < minimumRingRange
                    || (maxRange > 0.0f
                        && candidateRange > maxRange - maximumRangeSafetyMargin)
                    || bot->GetExactDist(rangedPosition) < minimumMovementDistance)
                    continue;
                if (moveToTerrainProjectedPoint(rangedPosition.GetPositionX(), rangedPosition.GetPositionY(), rangedPosition.GetPositionZ()))
                    return true;
            }
        }
    }
    return false;
}
