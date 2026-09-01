// Included inside AdaptiveMagmawStrategy private scope.
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
        bool* crashSideHold)
    {
        MagmawHazardObservation const observed = ObserveHazards(board, bot);
        bool const pillarBaiter = IsPillarBaiter(board, bot.Guid);
        bool const parasiteWave = HasLivingParasite(board);
        bool retainedCrashMayYieldToRoute = false;
        if (eventMovement)
            if (auto const* lethal = eventMovement->ActiveLethal())
            {
                bool const newerPillar = observed.Pillar
                    && observed.Pillar->Guid != lethal->SourceGuid
                    && Distance2d(bot.Position, observed.Pillar->Position) <= 12.0f;
                bool const newerCrash = observed.Crash
                    && observed.Crash->Guid != lethal->SourceGuid;
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
        if (observed.Crash)
            if (std::optional<MagmawRangedAnchors> const anchors =
                    ResolveRangedAnchors(board, boss))
            {
                crashSide = ProposeMagmawCrashSideMovement(board, bot,
                    *observed.Crash, anchors->Support, anchors->Left,
                    anchors->Right, pillarBaiter, SupportStackDistance,
                    eventMovement, 450.0f);
                if (crashSide.Movement
                    && (!pillarBaiter || !parasiteWave))
                {
                    if (laneTransition && pillarBaiter)
                        laneTransition->MarkPreempted();
                    return crashSide.Movement;
                }
            }
        if (observed.Pillar
            && !(observed.Crash && pillarBaiter && parasiteWave))
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
            && !(observed.Crash && pillarBaiter && parasiteWave))
            return std::nullopt;

        // A native rejection keeps the same actor-owned movement lifecycle
        // and endpoint. Do not replace it with a freshly sampled lane merely
        // because the observation revision or parasite GUID changed.
        if (pillarBaiter && hazardState && !observed.Crash)
            if (std::optional<BotNativeAction::Candidate> const retained =
                    MagmawParasitePolicy::RetainedHazardMovement(board,
                        *hazardState))
                return retained;

        if (pillarBaiter && laneTransition && HasLivingParasite(board))
            if (std::optional<MagmawRangedAnchors> const anchors =
                    ResolveRangedAnchors(board, boss))
            {
                std::optional<MagmawParasiteCrashObstacle> crashObstacle;
                if (observed.Crash)
                {
                    MagmawCrashSideMovement const geometry =
                        ResolveMagmawCrashSideMovement(bot.Position,
                            observed.Crash->Position, anchors->Support,
                            anchors->Left, anchors->Right, true,
                            SupportStackDistance);
                    if (geometry.Resolved)
                        crashObstacle = MagmawParasiteCrashObstacle{
                            true, observed.Crash->Position,
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
                bool const baiterCrashSide = pillarBaiter && observed.Crash;
                ActorSnapshot const* mangleOwner = FindMangleOwner(board);
                std::optional<Vector3> destination;
                if (baiterCrashSide)
                    destination = Distance2d(anchors->Left,
                        observed.Crash->Position) >= Distance2d(anchors->Right,
                            observed.Crash->Position)
                        ? anchors->Left : anchors->Right;
                else if (pillarBaiter)
                    destination = FormationAnchor(board, *anchors, bot.Guid);
                else if (mangleOwner)
                    destination = MagmawMangleSupportGeometry::Resolve(
                        anchors->Support, mangleOwner->Position,
                        MangleSupportMaxDistance);
                else
                    destination = anchors->Support;
                if (!destination)
                    return std::nullopt;
                bool const ownerRangeSafe = !mangleOwner
                    || MagmawMangleSupportGeometry::WithinDistance(
                        bot.Position, mangleOwner->Position,
                        MangleSupportMaxDistance);
                if (!ownerRangeSafe || Distance2d(bot.Position, *destination)
                        > RangedStackTolerance)
                    return BuildPointMovement(board, *destination,
                        baiterCrashSide
                            ? "mangle_safe_side" : "mangle_midpoint_stage",
                        BotActionArbitration::Priority::Survival, 490.0f);
            }
        return std::nullopt;
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
        Vector3 const& destination = FormationAnchor(board, *anchors,
            bot.Guid);
        if (Distance2d(bot.Position, destination) <= RangedStackTolerance)
            return std::nullopt;
        return BuildPointMovement(board, destination,
            "ranged_formation_restore",
            BotActionArbitration::Priority::Mechanic, 275.0f);
    }
