// Included inside AdaptiveMagmawStrategy private scope.
    enum class PrepullDisposition : uint8
    {
        NotApplicable,
        HoldOffense
    };

    struct PrepullDecision
    {
        PrepullDisposition Disposition = PrepullDisposition::NotApplicable;
    };
    using MagmawRangedAnchors = MagmawParasitePolicy::FormationAnchors;

    static bool IsParasiteEntry(uint32 entry)
    {
        return entry == ParasiteEntry || entry == ParasiteAltEntry;
    }

    static bool IsRangedParasiteSupportSpec(std::string_view classSpec)
    {
        // Keep this admission list aligned with the native ranged calibration
        // lane. It is intentionally a closed list so melee, healers, and
        // future unclassified profiles cannot acquire parasite targets.
        return classSpec == "balance_druid"
            || classSpec == "beast_mastery_hunter"
            || classSpec == "marksmanship_hunter"
            || classSpec == "survival_hunter"
            || classSpec == "shadow_priest"
            || classSpec == "elemental_shaman"
            || classSpec == "arcane_mage"
            || classSpec == "fire_mage"
            || classSpec == "frost_mage"
            || classSpec == "affliction_warlock"
            || classSpec == "demonology_warlock"
            || classSpec == "destruction_warlock";
    }
    static MagmawActorObservation ObserveMagmawActors(Blackboard const& board,
        ActorSnapshot const& bot)
    {
        MagmawActorObservation observed;
        auto inspectTarget = [&observed, &bot](ActorSnapshot const& actor)
        {
            if (!actor.Alive)
                return;
            if (actor.Entry == BossEntry)
                observed.Boss = &actor;
            else if (actor.Entry == HeadEntry && actor.Selectable
                && actor.Attackable)
                observed.Head = &actor;
            else if (IsParasiteEntry(actor.Entry))
            {
                float const distance = Distance2d(bot.Position, actor.Position);
                if (!observed.NearestParasite
                    || distance < observed.NearestParasiteDistance)
                {
                    observed.NearestParasite = &actor;
                    observed.NearestParasiteDistance = distance;
                }
                if (MagmawParasitePolicy::PersonallyThreatens(bot, actor)
                    && (!observed.PersonalParasiteThreat
                        || distance
                            < observed.PersonalParasiteThreatDistance))
                {
                    observed.PersonalParasiteThreat = &actor;
                    observed.PersonalParasiteThreatDistance = distance;
                }
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspectTarget(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspectTarget(actor);
        return observed;
    }

    static bool IsPillarBaiter(Blackboard const& board, ObjectGuid botGuid)
    {
        std::pair<ObjectGuid, ObjectGuid> const baiters =
            MagmawParasitePolicy::ResolveFixedBaiters(board);
        return !baiters.first.IsEmpty() && !baiters.second.IsEmpty()
            && (botGuid == baiters.first || botGuid == baiters.second);
    }

    static bool IsDesignatedPullTank(Blackboard const& board,
        ObjectGuid botGuid, std::string_view role)
    {
        if (role != "tank")
            return false;
        ObjectGuid pullTank;
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && member.Role == "tank"
                && (pullTank.IsEmpty()
                    || member.Guid.GetRawValue() < pullTank.GetRawValue()))
                pullTank = member.Guid;
        return !pullTank.IsEmpty() && pullTank == botGuid;
    }

    static bool IsPrepull(Blackboard const& board, ActorSnapshot const& boss)
    {
        bool const bossEngaged = boss.InCombat || !boss.VictimGuid.IsEmpty();
        return !bossEngaged && board.NativeBossState != "in_progress";
    }

    static PrepullDecision EvaluatePrepull(Blackboard const& board,
        ActorSnapshot const& boss)
    {
        PrepullDecision decision;
        if (!IsPrepull(board, boss))
            return decision;

        bool const prepullHealthIncomplete = std::any_of(board.Players.begin(),
            board.Players.end(), [](ActorSnapshot const& member)
            {
                return !member.Alive || member.HealthPct < 94.0f;
            });
        if (prepullHealthIncomplete)
        {
            decision.Disposition = PrepullDisposition::HoldOffense;
            return decision;
        }
        // A tank may begin the pull from range.  Normal combat movement owns
        // melee closure after Magmaw is engaged; prepull suppression is only
        // for an injured cohort that still needs health recovery.
        return decision;
    }

    static ObjectGuid SelectDamageTarget(MagmawActorObservation const& observed,
        ObjectGuid botGuid,
        std::string_view role, MagmawParasiteCombatContract const& contract)
    {
        if (observed.Head)
            return observed.Head->Guid;
        if (role == "dps")
        {
            if (contract.IsAssignedBaiter(botGuid)
                && observed.NearestParasite
                && observed.NearestParasiteDistance
                    <= RangedParasiteTargetDistance
                && contract.AllowsParasiteTarget(botGuid,
                    observed.NearestParasite->Guid))
                return observed.NearestParasite->Guid;

            if (observed.PersonalParasiteThreat
                && observed.PersonalParasiteThreatDistance
                    <= RangedParasiteTargetDistance
                && contract.AllowsParasiteTarget(botGuid,
                    observed.PersonalParasiteThreat->Guid))
                return observed.PersonalParasiteThreat->Guid;

            if (observed.NearestParasite
                && observed.NearestParasiteDistance
                    <= RangedParasiteSupportTargetDistance
                && contract.IsSupportTarget(botGuid,
                    observed.NearestParasite->Guid))
                return observed.NearestParasite->Guid;
        }
        return observed.Boss->Guid;
    }

    static void BindParasiteDamageTargets(ActorSnapshot const& bot,
        std::string_view role,
        MagmawActorObservation const& observed,
        MagmawParasiteCombatContract& contract)
    {
        contract.PersonalThreatGuid.Clear();
        contract.SupportTargetGuid.Clear();
        if (role == "dps" && observed.PersonalParasiteThreat)
            contract.PersonalThreatGuid =
                observed.PersonalParasiteThreat->Guid;
        if (role != "dps" || contract.IsAssignedBaiter(bot.Guid)
            || !IsRangedParasiteSupportSpec(bot.ClassSpec)
            || observed.Head || !observed.NearestParasite
            || observed.NearestParasiteDistance
                > RangedParasiteSupportTargetDistance)
            return;
        contract.SupportTargetGuid = observed.NearestParasite->Guid;
    }

    static void EmitPersonalParasiteEscape(Blackboard const& board,
        ActorSnapshot const& bot, MagmawActorObservation const& observed,
        MagmawFacts const* facts,
        MagmawPersonalParasiteEscapeTask* personalEscapeTask,
        MagmawParasiteWaveTask* parasiteWaveTask,
        MagmawParasiteHazardState* hazardState,
        MagmawMovementIntentCollection& intents)
    {
        if (IsPillarBaiter(board, bot.Guid))
            return;
        if (facts && personalEscapeTask)
        {
            std::optional<BotNativeAction::Candidate> escape =
                personalEscapeTask->Tick(board, *facts, bot,
                    observed.PersonalParasiteThreat,
                    MagmawParasitePolicy::SafeClearance,
                    MagmawParasitePolicy::DestinationTolerance,
                    MagmawParasitePolicy::ObserveRouteFacts(board, bot).
                        EmergencyClearance, parasiteWaveTask);
            if (escape)
                intents.Propose(MagmawMovementProposalOrigin::Hazard,
                    std::move(*escape));
            return;
        }
        if (hazardState && hazardState->HasRetainedIntent())
        {
            std::optional<BotNativeAction::Candidate> retained =
                MagmawParasitePolicy::RetainedHazardMovement(board,
                    *hazardState);
            if (retained)
                intents.Propose(MagmawMovementProposalOrigin::Hazard,
                    std::move(*retained));
            return;
        }
        if (!observed.PersonalParasiteThreat)
            return;
        std::optional<BotNativeAction::Candidate> escape =
            MagmawParasitePolicy::ProposePersonalEscape(board, bot,
                *observed.PersonalParasiteThreat, hazardState);
        if (escape)
            intents.Propose(MagmawMovementProposalOrigin::Hazard,
                std::move(*escape));
    }

    static bool Finite(Vector3 const& point)
    {
        return std::isfinite(point.X) && std::isfinite(point.Y)
            && std::isfinite(point.Z);
    }

    static std::optional<MagmawRangedAnchors> ResolveRangedAnchors(
        Blackboard const& board, ActorSnapshot const& boss)
    {
        if (board.Route.NavigationHints.empty()
            || !Finite(board.Route.NavigationHints.front())
            || !Finite(boss.Position))
            return std::nullopt;

        Vector3 const& roomSide = board.Route.NavigationHints.front();
        float dx = roomSide.X - boss.Position.X;
        float dy = roomSide.Y - boss.Position.Y;
        float const length = std::sqrt(dx * dx + dy * dy);
        if (length < 1.0f)
            return std::nullopt;
        dx /= length;
        dy /= length;
        float const centerX = boss.Position.X + dx * RangedStackDistance;
        float const centerY = boss.Position.Y + dy * RangedStackDistance;
        float const supportX = boss.Position.X + dx * SupportStackDistance;
        float const supportY = boss.Position.Y + dy * SupportStackDistance;
        float const lateralX = -dy * RangedStackLateralOffset;
        float const lateralY = dx * RangedStackLateralOffset;
        return MagmawRangedAnchors{
            { supportX, supportY, roomSide.Z },
            { centerX + lateralX, centerY + lateralY, roomSide.Z },
            { centerX - lateralX, centerY - lateralY, roomSide.Z } };
    }

    static Vector3 const& PrepullAnchor(Blackboard const& board,
        MagmawRangedAnchors const& anchors)
    {
        return board.CurrentScope.AttemptId % 2 ? anchors.Left : anchors.Right;
    }

    static Vector3 const& FormationAnchor(Blackboard const& board,
        MagmawRangedAnchors const& anchors, ObjectGuid const& botGuid)
    {
        return IsPillarBaiter(board, botGuid)
            ? PrepullAnchor(board, anchors) : anchors.Support;
    }

    static std::optional<Vector3> OrdinarySupportDestination(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, MagmawRangedAnchors const& anchors)
    {
        // Profiles without an attributable filler retain ordinary formation.
        if (!bot.PreferredCombatRange)
            return anchors.Support;
        ConfiguredCombatRange const& range = *bot.PreferredCombatRange;
        if (boss.Entry != BossEntry || range.TargetGuid != boss.Guid
            || range.TargetEntry != boss.Entry
            || !range.SourceSpellId || !range.ProfileGeneration
            || range.ProfileGeneration != board.ProfileGeneration
            || range.ProfileContentHash.empty()
            || range.ProfileContentHash != board.ProfileContentHash
            || !std::isfinite(range.MinRange) || !std::isfinite(range.MaxRange)
            || !std::isfinite(range.PreferredRange) || range.MinRange < 0.0f
            || range.MaxRange <= range.MinRange
            || range.PreferredRange < range.MinRange
            || range.PreferredRange > range.MaxRange)
            return std::nullopt;
        auto distance = [&](Vector3 const& point)
        {
            float const dx = point.X - boss.Position.X;
            float const dy = point.Y - boss.Position.Y;
            float const dz = point.Z - boss.Position.Z;
            return std::sqrt(dx * dx + dy * dy + dz * dz);
        };
        float const nominalRange = distance(anchors.Support);
        if (range.MinRange == 0.0f)
            return anchors.Support;
        if (nominalRange >= range.MinRange && nominalRange <= range.MaxRange
            && MagmawParasitePolicy::FullLaneCorridorSafe(anchors))
            return anchors.Support;

        // Reuse the fixed room-side shoulder rays and native floor input.
        // The entire bait chord must remain clear of the actual support point.
        float const dz = anchors.Support.Z - boss.Position.Z;
        float const planarSquared = range.PreferredRange * range.PreferredRange - dz * dz;
        if (planarSquared <= 0.0f)
            return std::nullopt;
        float const planar = std::sqrt(planarSquared);
        std::optional<Vector3> selected;
        float bestDistance = std::numeric_limits<float>::max();
        for (Vector3 const& shoulder : { anchors.Left, anchors.Right })
        {
            float const dx = shoulder.X - boss.Position.X;
            float const dy = shoulder.Y - boss.Position.Y;
            float const length = std::sqrt(dx * dx + dy * dy);
            if (length <= 0.0f)
                continue;
            Vector3 const point{ boss.Position.X + dx * planar / length,
                boss.Position.Y + dy * planar / length, anchors.Support.Z };
            float const candidateRange = distance(point);
            MagmawRangedAnchors const candidateAnchors{ point, anchors.Left, anchors.Right };
            if (!Finite(point) || candidateRange < range.MinRange || candidateRange > range.MaxRange
                || !MagmawParasitePolicy::FullLaneCorridorSafe(candidateAnchors))
                continue;
            float const displacement = Distance2d(bot.Position, point);
            if (displacement < bestDistance)
            {
                selected = point;
                bestDistance = displacement;
            }
        }
        return selected;
    }

    static bool RangedGroupStaged(Blackboard const& board,
        MagmawRangedAnchors const& anchors)
    {
        return std::all_of(board.Players.begin(), board.Players.end(),
            [&board, &anchors](ActorSnapshot const& member)
            {
                Vector3 const& anchor = FormationAnchor(board, anchors,
                    member.Guid);
                return !member.Alive || member.Role == "tank"
                    || Distance2d(member.Position, anchor)
                        <= RangedStackTolerance;
            });
    }

    static std::optional<Vector3> ResolveHookApproachDestination(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss)
    {
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return std::nullopt;
        float dx = anchors->Left.X + anchors->Right.X
            - 2.0f * boss.Position.X;
        float dy = anchors->Left.Y + anchors->Right.Y
            - 2.0f * boss.Position.Y;
        float const length = std::sqrt(dx * dx + dy * dy);
        if (length < 0.01f)
            return std::nullopt;
        return Vector3{
            boss.Position.X + dx / length * 4.0f,
            boss.Position.Y + dy / length * 4.0f,
            bot.Position.Z };
    }

    static BotNativeAction::Candidate BuildPointMovement(
        Blackboard const& board, Vector3 const& point, std::string mechanic,
        BotActionArbitration::Priority priority, float utility)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_magmaw";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = priority;
        candidate.Utility = utility;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{ point.X, point.Y, point.Z };
        return candidate;
    }

    static ActorSnapshot const* FindFirstAliveActorByEntry(
        std::vector<ActorSnapshot> const& actors, uint32 entry)
    {
        auto itr = std::find_if(actors.begin(), actors.end(), [entry](
            ActorSnapshot const& actor)
        {
            return actor.Alive && actor.Entry == entry;
        });
        return itr == actors.end() ? nullptr : &*itr;
    }

    static bool IsImmediateHazard(ActorSnapshot const& actor)
    {
        bool const litCrash = actor.Entry == RoomStalkerEntry
            && HasAura(actor, 87949);
        bool const parasite = IsParasiteEntry(actor.Entry);
        return actor.Alive && (litCrash || parasite);
    }

    static MagmawHazardObservation ObserveHazards(Blackboard const& board,
        ActorSnapshot const& bot)
    {
        MagmawHazardObservation observed;
        for (ActorSnapshot const& actor : board.Summons)
            if (actor.Alive && actor.Entry == PillarEntry
                && (!observed.Pillar
                    || Distance2d(bot.Position, actor.Position)
                        < Distance2d(bot.Position, observed.Pillar->Position)))
                observed.Pillar = &actor;
        auto inspectHazard = [&observed, &bot](ActorSnapshot const& actor)
        {
            if (!IsImmediateHazard(actor))
                return;
            float const distance = Distance2d(bot.Position, actor.Position);
            if (IsCrashHazard(actor)
                && (!observed.Crash || distance < observed.CrashDistance))
            {
                observed.Crash = &actor;
                observed.CrashDistance = distance;
            }
            if (!IsParasiteEntry(actor.Entry))
                return;
            if (!observed.NearestImmediateHazard
                || distance < observed.NearestImmediateHazardDistance)
            {
                observed.NearestImmediateHazard = &actor;
                observed.NearestImmediateHazardDistance = distance;
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspectHazard(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspectHazard(actor);
        return observed;
    }
