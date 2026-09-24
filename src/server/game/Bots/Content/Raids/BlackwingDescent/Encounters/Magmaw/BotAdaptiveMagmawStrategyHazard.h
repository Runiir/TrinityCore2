// Included inside AdaptiveMagmawStrategy private scope.
    static_assert(MagmawPlatformNavigation::SupportStackDistance
        == SupportStackDistance, "platform return anchor must match support");
    static std::optional<BotNativeAction::Candidate> BuildPillarEvade(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& pillar,
        MagmawEventMovementTransitionState* eventMovement)
    {
        float dx = bot.Position.X - pillar.Position.X;
        float dy = bot.Position.Y - pillar.Position.Y;
        float distance = std::sqrt(dx * dx + dy * dy);
        if (distance <= 12.0f)
        {
            if (distance < 0.01f)
            {
                dx = std::cos(bot.Facing);
                dy = std::sin(bot.Facing);
                distance = 1.0f;
            }
            Vector3 const destination{
                pillar.Position.X + dx / distance * 15.0f,
                pillar.Position.Y + dy / distance * 15.0f,
                bot.Position.Z };
            if (eventMovement)
            {
                if (auto const* episode = eventMovement->RetainLethal(
                        pillar.Guid, bot.Guid, "pillar_evade", destination,
                        pillar.Position, 12.0f))
                    return BuildMagmawEventMovement(board, *episode,
                        BotActionArbitration::Priority::Survival,
                        500.0f - distance);
                return std::nullopt;
            }
            BotNativeAction::Candidate candidate;
            candidate.Id.ScopeKey = board.CurrentScope.CohortId + ":"
                + std::to_string(board.CurrentScope.AttemptId) + ":"
                + std::to_string(board.CurrentScope.WipeGeneration) + ":"
                + std::to_string(board.CurrentScope.RouteGeneration) + ":"
                + board.CurrentScope.NodeId;
            candidate.Id.Strategy = "adaptive_magmaw";
            candidate.Id.Mechanic = "pillar_evade";
            candidate.Id.Actor = pillar.Guid;
            candidate.Id.EventGeneration = board.Revision;
            candidate.ActionPriority = BotActionArbitration::Priority::Survival;
            candidate.Utility = 500.0f - distance;
            candidate.ExpiresAtMs = board.ObservedAtMs + 750;
            candidate.Action = BotNativeAction::Move{ destination.X,
                destination.Y, destination.Z };
            return candidate;
        }
        return std::nullopt;
    }
    static std::optional<BotNativeAction::Candidate> BuildPillarBaitMove(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ActorSnapshot const& pillar,
        BotMovementArbitration::Lease const* /*movementLease*/,
        MagmawLaneTransitionState* laneTransition,
        MagmawEventMovementTransitionState* eventMovement)
    {
        if (!IsPillarBaiter(board, bot.Guid) || !laneTransition)
            return std::nullopt;
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return std::nullopt;
        std::optional<Vector3> const destination =
            MagmawParasitePolicy::EnsureLaneDestination(board, bot, *anchors,
                *laneTransition, pillar.Guid.GetRawValue(), 1);
        if (destination
            && Distance2d(*destination, pillar.Position)
                < MagmawParasitePolicy::SafeClearance)
            laneTransition->MarkPreempted();
        if (laneTransition->Preempted
            && (!destination
                || Distance2d(*destination, pillar.Position)
                    < MagmawParasitePolicy::SafeClearance))
            return BuildPillarEvade(board, bot, pillar, eventMovement);
        laneTransition->Resume();
        if (!destination
            || Distance2d(bot.Position, *destination)
                <= RangedStackTolerance)
            return std::nullopt;
        BotNativeAction::Candidate candidate = BuildPointMovement(
            board, *destination, "pillar_bait_switch",
            BotActionArbitration::Priority::Survival, 500.0f);
        candidate.Id.Actor = bot.Guid;
        candidate.Id.EventGeneration = laneTransition->TransitionId;
        if (BotNativeAction::Move* move =
                std::get_if<BotNativeAction::Move>(&candidate.Action))
        {
            move->Z = destination->Z;
            move->IntentReason = "pillar_bait_switch";
        }
        return candidate;
    }

    static bool HasActivePillar(Blackboard const& board)
    {
        return std::any_of(board.Summons.begin(), board.Summons.end(),
            [](ActorSnapshot const& actor)
            {
                return actor.Alive && actor.Entry == PillarEntry;
            });
    }

    static bool HasLivingParasite(Blackboard const& board)
    {
        return MagmawParasitePolicy::HasLivingParasite(board);
    }

    static bool HasActiveHazardPath(Blackboard const& board,
        BotMovementArbitration::Lease const* movementLease,
        bool activePathValid, bool moving)
    {
        return MagmawParasitePolicy::HasActiveHazardPath(board,
            movementLease, activePathValid, moving);
    }

    static bool IsCrashHazard(ActorSnapshot const& actor)
    {
        return actor.Entry == RoomStalkerEntry && HasAura(actor, 87949);
    }

    // Native lighting selects exactly the Room Stalkers inside the chosen
    // dummy's HasInArc(pi/4) arc, i.e. within pi/8 of its facing
    // (instance_blackwing_descent.cpp).  When a crash dummy is observed, the
    // one whose arc holds the whole lit set is the tip of the damage cone.
    static std::optional<Vector3> ObserveActiveCrashDummy(
        Blackboard const& board, std::vector<ActorSnapshot const*> const& lit)
    {
        if (lit.empty())
            return std::nullopt;
        constexpr float HalfArc = 3.14159265f / 8.0f + 0.02f;
        for (std::vector<ActorSnapshot> const* actors : {
                 &board.Hostiles, &board.Summons, &board.Interactables })
            for (ActorSnapshot const& dummy : *actors)
            {
                if (!dummy.Alive || dummy.Entry != PersistentCrashDummyEntry
                    || !std::isfinite(dummy.Position.X)
                    || !std::isfinite(dummy.Position.Y)
                    || !std::isfinite(dummy.Facing))
                    continue;
                bool const holdsLitSet = std::all_of(lit.begin(), lit.end(),
                    [&dummy](ActorSnapshot const* stalker)
                    {
                        float const angle = std::remainder(std::atan2(
                            stalker->Position.Y - dummy.Position.Y,
                            stalker->Position.X - dummy.Position.X)
                                - dummy.Facing, 2.0f * 3.14159265f);
                        return std::fabs(angle) <= HalfArc;
                    });
                if (holdsLitSet)
                    return dummy.Position;
            }
        return std::nullopt;
    }

    // One footprint per native Massive Crash, shared by every bot: all alive
    // lit Room Stalkers, never only the one nearest this bot, so the chosen
    // side and the episode identity cannot flip while the bot moves.  The
    // covered hull also holds native points inside the same cone: Magmaw,
    // who faces the chosen dummy from inside its arc (units at his position
    // were hit by both crash sides in the retained kills), and the observed
    // dummy at the cone tip.  Without them the tip between the dummy and the
    // first lit stalkers would read as clear.
    static MagmawCrashFootprint ObserveCrashFootprint(Blackboard const& board,
        ActorSnapshot const& boss)
    {
        std::vector<ActorSnapshot const*> lit;
        for (std::vector<ActorSnapshot> const* actors : {
                 &board.Hostiles, &board.Summons })
            for (ActorSnapshot const& actor : *actors)
                if (actor.Alive && IsCrashHazard(actor))
                    lit.push_back(&actor);
        std::vector<Vector3> knownInside;
        if (boss.Alive)
            knownInside.push_back(boss.Position);
        if (std::optional<Vector3> const dummy =
                ObserveActiveCrashDummy(board, lit))
            knownInside.push_back(*dummy);
        return BuildMagmawCrashFootprint(lit, knownInside);
    }

    static bool HasMangleAura(ActorSnapshot const& actor)
    {
        return HasAura(actor, 89773) || HasAura(actor, 78412);
    }

    static ActorSnapshot const* FindMangleOwner(Blackboard const& board)
    {
        ActorSnapshot const* owner = nullptr;
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && HasMangleAura(member)
                && (!owner || member.Guid.GetRawValue()
                    < owner->Guid.GetRawValue()))
                owner = &member;
        return owner;
    }
    static bool IsPincerWarningActor(ActorSnapshot const& actor)
    {
        // Persistent Massive Crash dummies are not a transient telegraph;
        // only the lit Room Stalker carries that native warning state.
        return actor.Alive && actor.Entry == RoomStalkerEntry
            && HasAura(actor, 87949);
    }

    static bool PincerWarningObserved(Blackboard const& board)
    {
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && HasMangleAura(member))
                return true;
        for (std::vector<ActorSnapshot> const* actors : {
                 &board.Hostiles, &board.Summons })
            for (ActorSnapshot const& actor : *actors)
                if (IsPincerWarningActor(actor))
                    return true;
        return false;
    }

    static bool PincerCommitmentActive(
        MagmawHookAssignment const& assignment, ActorSnapshot const& boss,
        bool warningObserved)
    {
        return assignment.Assigned && (boss.Interactable || warningObserved);
    }
    static std::optional<BotNativeAction::Candidate> ProposeHazardMovement(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, bool pincerWindow, bool pincerWarning,
        BotMovementArbitration::Lease const* movementLease,
        MagmawLaneTransitionState* laneTransition,
        MagmawParasiteHazardState* hazardState,
        MagmawEventMovementTransitionState* eventMovement,
        std::optional<MagmawDirectionalMobilityInput> const& mobility,
        std::optional<BotNativeAction::Candidate>* directionalMobility,
        bool* crashSideHold,
        MagmawNativeMovementProbe const* nativeProbe = nullptr)
    {
        MagmawHazardObservation const observed = ObserveHazards(board, bot);
        MagmawCrashFootprint const crash = ObserveCrashFootprint(board, boss);
        bool const pillarBaiter = IsPillarBaiter(board, bot.Guid);
        bool const parasiteWave = HasLivingParasite(board);
        bool retainedCrashMayYieldToRoute = false;
        if (eventMovement)
            if (auto const* lethal = eventMovement->ActiveLethal())
            {
                bool const newerPillar = observed.Pillar
                    && observed.Pillar->Guid != lethal->SourceGuid
                    && Distance2d(bot.Position, observed.Pillar->Position) <= 12.0f;
                bool const newerCrash = crash.Valid
                    && crash.Identity != lethal->SourceGuid;
                retainedCrashMayYieldToRoute = pillarBaiter && parasiteWave
                    && lethal->Mechanic == "massive_crash_evade";
                if (newerPillar || newerCrash)
                    eventMovement->RetireActiveLethal();
                if (!newerPillar && !newerCrash
                    && !retainedCrashMayYieldToRoute)
                    return BuildMagmawEventMovement(board, *lethal,
                        BotActionArbitration::Priority::Survival, 450.0f);
            }
        MagmawCrashSideProposal crashSide;
        if (crash.Valid)
        {
            if (std::optional<MagmawRangedAnchors> const anchors =
                    ResolveRangedAnchors(board, boss))
                crashSide = ProposeMagmawCrashSideMovement(board, bot,
                    crash, anchors->Support, anchors->Left,
                    anchors->Right, pillarBaiter, SupportStackDistance,
                    eventMovement, 450.0f);
            else
                crashSide = ProposeMagmawCrashSideMovementWithoutAnchors(
                    board, bot, crash, eventMovement, 450.0f);
            if (crashSide.Movement
                && (!pillarBaiter || !parasiteWave))
            {
                if (laneTransition && pillarBaiter)
                    laneTransition->MarkPreempted();
                return crashSide.Movement;
            }
        }
        if (observed.Pillar
            && !(crash.Valid && pillarBaiter && parasiteWave))
        {
            if (pincerWindow)
            {
                if (laneTransition && laneTransition->IsBaiter(bot.Guid))
                    laneTransition->MarkPreempted();
                if (std::optional<BotNativeAction::Candidate> const pillar =
                        BuildPillarEvade(board, bot, *observed.Pillar,
                            eventMovement))
                    return pillar;
            }
            else
            {
                if (std::optional<BotNativeAction::Candidate> const bait =
                        BuildPillarBaitMove(board, bot, boss, *observed.Pillar,
                            movementLease, laneTransition, eventMovement))
                    return bait;
                if (std::optional<BotNativeAction::Candidate> const pillar =
                        BuildPillarEvade(board, bot, *observed.Pillar,
                            eventMovement))
                    return pillar;
            }
        }
        if (crashSide.Hold && !pillarBaiter)
        {
            if (crashSideHold)
                *crashSideHold = true;
            return std::nullopt;
        }
        if (pincerWindow
            && !(crash.Valid && pillarBaiter && parasiteWave))
            return std::nullopt;

        // Lease expiry and observation churn keep the actor-owned lifecycle.
        // The native adapter separately retires a permanently rejected exact
        // endpoint before a fresh route may be sampled.
        if (pillarBaiter && hazardState && !crash.Valid)
            if (std::optional<BotNativeAction::Candidate> const retained =
                    MagmawParasitePolicy::RetainedHazardMovement(board,
                        *hazardState))
                return retained;

        if (pillarBaiter && laneTransition && HasLivingParasite(board))
            if (std::optional<MagmawRangedAnchors> const anchors =
                    ResolveRangedAnchors(board, boss))
            {
                std::optional<MagmawParasiteCrashObstacle> crashObstacle;
                if (crash.Valid)
                {
                    // The side comes from the whole lit set; the local
                    // obstacle keeps the lit stalker nearest this baiter.
                    MagmawCrashSideMovement const geometry =
                        ResolveMagmawCrashSideMovement(bot.Position,
                            crash.Centroid, anchors->Support,
                            anchors->Left, anchors->Right, true,
                            SupportStackDistance);
                    if (geometry.Resolved)
                        crashObstacle = MagmawParasiteCrashObstacle{
                            true, observed.Crash ? observed.Crash->Position
                                : crash.Centroid,
                            geometry.UnsafeSideAnchor,
                            geometry.SafeSideAnchor, 12.0f };
                }
                if (std::optional<BotNativeAction::Candidate> route =
                        MagmawParasitePolicy::ProposeSafeParasiteRoute(board,
                            bot, *anchors, *laneTransition, crashObstacle))
                {
                    // Keep the retained Crash episode stable until a complete
                    // parasite route has actually been admitted.  If route
                    // construction fails, the fallback below must retain the
                    // same episode and candidate identity on the next tick.
                    if (retainedCrashMayYieldToRoute && eventMovement)
                        eventMovement->RetireActiveLethal();
                    if (mobility && directionalMobility)
                        *directionalMobility = ProposeMagmawDirectionalMobility(
                            board, bot, boss, *route, *mobility,
                            MagmawParasitePolicy::ObserveRouteFacts(board,
                                bot));
                    return route;
                }
                // If current contact makes a fully admitted arc impossible,
                // the lethal Crash side still wins over a radial parasite
                // escape. This is the bounded fallback, not the normal path.
                if (crashSide.Movement)
                {
                    laneTransition->MarkPreempted();
                    return crashSide.Movement;
                }
                MagmawParasiteRouteFacts const facts =
                    MagmawParasitePolicy::ObserveRouteFacts(board, bot);
                if (facts.EmergencyClearance
                    && observed.NearestImmediateHazard)
                    if (std::optional<BotNativeAction::Candidate> emergency =
                            MagmawParasitePolicy::Propose(board, bot,
                                *observed.NearestImmediateHazard, true,
                                anchors, movementLease, laneTransition,
                                hazardState))
                    {
                        if (mobility && directionalMobility)
                            *directionalMobility =
                                ProposeMagmawDirectionalMobility(board, bot,
                                    boss, *emergency, *mobility, facts);
                        return emergency;
                    }
            }
        if (pillarBaiter && HasLivingParasite(board))
            return std::nullopt;
        if (crashSide.Hold)
        {
            if (crashSideHold)
                *crashSideHold = true;
            return std::nullopt;
        }

        if (pincerWarning && !HasMangleAura(bot))
            if (std::optional<MagmawRangedAnchors> const anchors =
                    ResolveRangedAnchors(board, boss))
            {
                bool const baiterCrashSide = pillarBaiter && crash.Valid;
                ActorSnapshot const* mangleOwner = FindMangleOwner(board);
                std::optional<Vector3> destination;
                if (baiterCrashSide)
                    destination = Distance2d(anchors->Left,
                        crash.Centroid) >= Distance2d(anchors->Right,
                            crash.Centroid)
                        ? anchors->Left : anchors->Right;
                else if (pillarBaiter)
                    destination = FormationAnchor(board, *anchors, bot.Guid);
                else if (mangleOwner)
                {
                    // HEAL-002: a healer already in heal range and line of
                    // sight of the Mangled tank stays and heals; the stage
                    // move is only for a healer that would otherwise be out
                    // of range or sight. Crash, pillar and lava moves above
                    // are unaffected.
                    if (HealerSupportsMangleInPlace(bot, *mangleOwner,
                            nativeProbe))
                        return std::nullopt;
                    destination = MagmawMangleSupportGeometry::Resolve(
                        anchors->Support, mangleOwner->Position,
                        MangleSupportMaxDistance);
                }
                else
                    destination = anchors->Support;
                if (!destination)
                    return std::nullopt;
                bool const ownerRangeSafe = !mangleOwner
                    || MagmawMangleSupportGeometry::WithinDistance(
                        bot.Position, mangleOwner->Position,
                        MangleSupportMaxDistance);
                if (ownerRangeSafe && Distance2d(bot.Position, *destination)
                        <= RangedStackTolerance)
                    return std::nullopt;
                if (!baiterCrashSide && nativeProbe)
                {
                    // HEAL-003: the stage point must be on the platform with a
                    // native way back; otherwise try the support anchor, else
                    // hold position.
                    destination = AdmitMangleStagePoint(*destination,
                        *anchors, mangleOwner, *nativeProbe);
                    if (!destination)
                        return std::nullopt;
                }
                return BuildPointMovement(board, *destination,
                    baiterCrashSide
                        ? "mangle_safe_side" : "mangle_midpoint_stage",
                    BotActionArbitration::Priority::Survival, 490.0f);
            }
        return std::nullopt;
    }

    static bool HealerSupportsMangleInPlace(ActorSnapshot const& bot,
        ActorSnapshot const& mangleOwner,
        MagmawNativeMovementProbe const* nativeProbe)
    {
        return bot.Role == "healer" && nativeProbe
            && nativeProbe->LineOfSightTo
            && MagmawMangleSupportGeometry::WithinDistance(bot.Position,
                mangleOwner.Position, MangleSupportMaxDistance)
            && nativeProbe->LineOfSightTo(mangleOwner.Guid);
    }

    static std::optional<Vector3> AdmitMangleStagePoint(
        Vector3 const& stage, MagmawRangedAnchors const& anchors,
        ActorSnapshot const* mangleOwner,
        MagmawNativeMovementProbe const& nativeProbe)
    {
        if (!nativeProbe.ObserveDestination)
            return stage;
        std::vector<Vector3> candidates{ stage };
        if (Distance2d(stage, anchors.Support)
                > MagmawPlatformNavigation::SamePointTolerance
            && (!mangleOwner || MagmawMangleSupportGeometry::WithinDistance(
                anchors.Support, mangleOwner->Position,
                MangleSupportMaxDistance)))
            candidates.push_back(anchors.Support);
        return SelectMagmawPlatformDestination(nativeProbe, candidates,
            anchors.Support, anchors.Support.Z).Destination;
    }

    // HEAL-003: the ordinary formation return, unless this non-baiter's
    // return destination is stranded (consecutive native path rejections).
    static std::optional<BotNativeAction::Candidate>
    ProposeRangedFormationReturn(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const& boss,
        std::string_view role, MagmawPersonalParasiteEscapeTask* returnTask)
    {
        std::optional<BotNativeAction::Candidate> restore =
            ProposeRangedFormationRestore(board, bot, boss, role);
        if (!restore || !returnTask || IsPillarBaiter(board, bot.Guid))
            return restore;
        BotNativeAction::Move const* move =
            std::get_if<BotNativeAction::Move>(&restore->Action);
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!move || !anchors)
            return restore;
        Vector3 const original{ move->X, move->Y, move->Z };
        if (!returnTask->ReturnRecovery.Stranded(original, board.ObservedAtMs))
            return restore;
        return ProposeStrandFallback(board, bot, *anchors, original,
            *returnTask);
    }

    static std::optional<BotNativeAction::Candidate>
    ProposeRangedFormationRestore(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const& boss,
        std::string_view role)
    {
        if (role == "tank")
            return std::nullopt;
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return std::nullopt;
        bool const baiter = IsPillarBaiter(board, bot.Guid);
        std::optional<Vector3> const destination = baiter
            ? std::optional<Vector3>(FormationAnchor(board, *anchors, bot.Guid))
            : OrdinarySupportDestination(board, bot, boss, *anchors);
        if (!destination)
            return std::nullopt;
        bool rangeSettled = true;
        if (!baiter && bot.PreferredCombatRange
            && bot.PreferredCombatRange->MinRange > 0.0f)
        {
            ConfiguredCombatRange const& range = *bot.PreferredCombatRange;
            float const dx = bot.Position.X - boss.Position.X;
            float const dy = bot.Position.Y - boss.Position.Y;
            float const dz = bot.Position.Z - boss.Position.Z;
            float const distance = std::sqrt(dx * dx + dy * dy + dz * dz);
            rangeSettled = distance >= range.MinRange && distance <= range.MaxRange;
        }
        if (rangeSettled && Distance2d(bot.Position, *destination) <= RangedStackTolerance)
            return std::nullopt;
        return BuildPointMovement(board, *destination,
            "ranged_formation_restore",
            BotActionArbitration::Priority::Mechanic, 275.0f);
    }

    // HEAL-003: after ReturnFailureThreshold consecutive native rejections of
    // the same return destination, stop retrying it and walk to the nearest
    // native-reachable ranged support anchor or ranged group position (each
    // proven on the platform with a way back to the support anchor). With no
    // reachable option the actor holds position; the original destination is
    // retried once the strand hold expires.
    static std::optional<BotNativeAction::Candidate> ProposeStrandFallback(
        Blackboard const& board, ActorSnapshot const& bot,
        MagmawRangedAnchors const& anchors, Vector3 const& original,
        MagmawPersonalParasiteEscapeTask& task)
    {
        MagmawStrandRecoveryState& strand = task.ReturnRecovery;
        if (!strand.FallbackActive)
        {
            if (!task.NativeProbe || !task.NativeProbe->ObserveDestination
                || board.ObservedAtMs < strand.NextProbeAtMs)
            {
                ++strand.HoldCount;
                return std::nullopt;
            }
            std::vector<Vector3> candidates{ anchors.Support };
            for (ActorSnapshot const& member : board.Players)
                if (member.Alive && member.Guid != bot.Guid
                    && member.Role != "tank"
                    && !IsPillarBaiter(board, member.Guid)
                    && Distance2d(member.Position, anchors.Support)
                        <= MagmawPlatformNavigation::GroupPositionRadius)
                    candidates.push_back(member.Position);
            std::stable_sort(candidates.begin(), candidates.end(),
                [&bot](Vector3 const& left, Vector3 const& right)
                {
                    return Distance2d(bot.Position, left)
                        < Distance2d(bot.Position, right);
                });
            std::vector<Vector3> excluded = strand.Excluded;
            excluded.push_back(original);
            MagmawPlatformSelection const selection =
                SelectMagmawPlatformDestination(*task.NativeProbe,
                    candidates, anchors.Support, anchors.Support.Z,
                    excluded);
            if (!selection.Destination)
            {
                ++strand.HoldCount;
                strand.NextProbeAtMs = board.ObservedAtMs
                    + MagmawPlatformNavigation::HoldRetryMs;
                return std::nullopt;
            }
            strand.FallbackActive = true;
            strand.Fallback = *selection.Destination;
            strand.FallbackFailures = 0;
            strand.FallbackSelectedAtMs = board.ObservedAtMs;
            ++strand.FallbackCount;
        }
        if (Distance2d(bot.Position, strand.Fallback) <= RangedStackTolerance)
            return std::nullopt;
        return BuildPointMovement(board, strand.Fallback,
            "ranged_formation_restore",
            BotActionArbitration::Priority::Mechanic, 275.0f);
    }

    static bool InConfiguredHeadRange(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const* head, std::string_view role)
    {
        if (role != "dps" || !head || !head->Alive || !head->Selectable
            || !head->Attackable || !bot.PreferredCombatRange)
            return false;
        ConfiguredCombatRange const& range = *bot.PreferredCombatRange;
        if (range.TargetGuid != head->Guid || range.TargetEntry != HeadEntry
            || !range.SourceSpellId || !range.ProfileGeneration
            || range.ProfileGeneration != board.ProfileGeneration
            || range.ProfileContentHash.empty()
            || range.ProfileContentHash != board.ProfileContentHash
            || !std::isfinite(range.MinRange) || !std::isfinite(range.MaxRange)
            || range.MinRange < 0.0f || range.MaxRange <= range.MinRange)
            return false;
        float const dx = bot.Position.X - head->Position.X;
        float const dy = bot.Position.Y - head->Position.Y;
        float const dz = bot.Position.Z - head->Position.Z;
        float const distance = std::sqrt(dx * dx + dy * dy + dz * dz);
        return std::isfinite(distance) && distance >= range.MinRange
            && distance <= range.MaxRange;
    }
