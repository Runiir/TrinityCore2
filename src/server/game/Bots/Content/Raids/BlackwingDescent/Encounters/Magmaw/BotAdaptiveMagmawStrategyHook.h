// Included inside AdaptiveMagmawStrategy private scope.
    static bool IsFixedBaiter(
        std::pair<ObjectGuid, ObjectGuid> const& baiters, ObjectGuid guid)
    {
        return guid == baiters.first || guid == baiters.second;
    }

    // Healers ride only as a last resort (live 3-kill bundle: a Discipline
    // rider left Mangle support and the tank died in 2 of 3 boss windows).
    // If one does sit in a no-cast pincer seat with its pair broken, it
    // leaves once fewer than three healers live or the mangled tank is below
    // 35%. Baselines 0891a99 k1-k3: tank 202-232k HP, lowest 49-57%, worst
    // Mangle 5 s bucket 136k (~12%/s); 35% (~75k) is about three seconds of
    // that, enough for the exit and one heal.
    static constexpr std::size_t HookHealerMinimumLivingHealers = 3;
    static constexpr float HookHealerCriticalTankHealthPct = 35.0f;

    static std::size_t LivingHealers(Blackboard const& board)
    {
        return std::size_t(std::count_if(board.Players.begin(),
            board.Players.end(), [](ActorSnapshot const& member)
            {
                return member.Alive && member.Role == "healer";
            }));
    }

    static bool SeatedOnPincer(Blackboard const& board,
        ActorSnapshot const& member)
    {
        ActorSnapshot const* vehicle = member.VehicleGuid.IsEmpty()
            ? nullptr : board.FindActor(member.VehicleGuid);
        return vehicle && vehicle->Alive && IsPincerVehicle(*vehicle);
    }

    // Both pincers are held by living players. This reads seats only, so
    // the release rule never depends on the rider list it shapes.
    static bool PincersPaired(Blackboard const& board)
    {
        bool left = false;
        bool right = false;
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && SeatedOnPincer(board, member))
            {
                uint32 const entry = board.FindActor(member.VehicleGuid)->Entry;
                left = left || entry == PincerLeftEntry;
                right = right || entry == PincerRightEntry;
            }
        return left && right;
    }

    static bool MangledTankCritical(Blackboard const& board)
    {
        ActorSnapshot const* owner = FindMangleOwner(board);
        return owner && owner->HealthPct < HookHealerCriticalTankHealthPct;
    }

    // A seated rider gives up its pincer (native exit, seat addon lands it
    // on the room floor) and its hook duty when the seat cannot produce the
    // hook, or when a seated healer is needed back:
    //  - any rider: the mount window (Massive Crash, 6 s) has closed with the
    //    other pincer empty. Nobody can join, and the script only ejects at
    //    the next Massive Crash;
    //  - a healer: the window has closed (after the impale this skips the
    //    3.5 s native eject), or its pair is broken while fewer than three
    //    healers live or the mangled tank is critical. With healers and tank
    //    healthy it keeps the seat for a replacement until the window closes.
    // A complete pair inside the window keeps both seats: the launch goes out
    // on this tick, and the impale is what frees the tank from Mangle.
    static bool SeatReleased(Blackboard const& board,
        ActorSnapshot const& member)
    {
        if (!member.Alive || !SeatedOnPincer(board, member))
            return false;
        ActorSnapshot const* boss = FindActorByEntry(board, BossEntry);
        bool const windowOpen = boss && boss->Interactable;
        bool const paired = PincersPaired(board);
        if (!windowOpen && !paired)
            return true;
        if (member.Role != "healer")
            return false;
        return !windowOpen || (!paired
            && (LivingHealers(board) < HookHealerMinimumLivingHealers
                || MangledTankCritical(board)));
    }

    // Every hook caller derives the riders from this one ordered list; only
    // the first two are assigned. Released seats (SeatReleased) are skipped
    // everywhere. Preference order:
    //  1. living riders already seated on a pincer, so a roster change during
    //     the ride never strands an unassigned actor in a pincer seat;
    //  2. non-baiter DPS by raw GUID, except Balance, which keeps its
    //     stationary casts and the parasite mushroom duty;
    //  3. non-baiter DPS including Balance, by raw GUID;
    //  4. only when no DPS can fill a seat, any other non-tank (healers) by
    //     raw GUID.
    // Tanks and the fixed pillar baiters never ride.
    static std::vector<ObjectGuid> BuildHookUsers(Blackboard const& board)
    {
        std::pair<ObjectGuid, ObjectGuid> const baiters =
            MagmawParasitePolicy::ResolveFixedBaiters(board);
        std::vector<ObjectGuid> seated;
        std::vector<ObjectGuid> dps;
        std::vector<ObjectGuid> balance;
        std::vector<ObjectGuid> others;
        for (ActorSnapshot const& member : board.Players)
        {
            if (!member.Alive || member.Role == "tank"
                || IsFixedBaiter(baiters, member.Guid)
                || SeatReleased(board, member))
                continue;
            if (SeatedOnPincer(board, member))
                seated.push_back(member.Guid);
            if (member.Role != "dps")
                others.push_back(member.Guid);
            else if (member.ClassSpec == "balance_druid")
                balance.push_back(member.Guid);
            else
                dps.push_back(member.Guid);
        }
        auto byRawGuid = [](ObjectGuid left, ObjectGuid right)
        {
            return left.GetRawValue() < right.GetRawValue();
        };
        std::sort(seated.begin(), seated.end(), byRawGuid);
        std::sort(dps.begin(), dps.end(), byRawGuid);
        std::sort(others.begin(), others.end(), byRawGuid);
        std::vector<ObjectGuid> previousDps = dps;
        previousDps.insert(previousDps.end(), balance.begin(), balance.end());
        std::sort(previousDps.begin(), previousDps.end(), byRawGuid);

        std::vector<ObjectGuid> hookUsers;
        auto append = [&hookUsers](ObjectGuid guid)
        {
            if (!guid.IsEmpty() && std::find(hookUsers.begin(),
                    hookUsers.end(), guid) == hookUsers.end())
                hookUsers.push_back(guid);
        };
        for (ObjectGuid guid : seated)
            append(guid);
        for (std::vector<ObjectGuid> const* tier : { &dps, &previousDps,
                 &others })
            for (ObjectGuid guid : *tier)
                append(guid);
        return hookUsers;
    }
    static bool IsAssignedHookUser(std::vector<ObjectGuid> const& hookUsers,
        ObjectGuid botGuid)
    {
        auto hookUser = std::find(hookUsers.begin(), hookUsers.end(), botGuid);
        return hookUser != hookUsers.end()
            && std::distance(hookUsers.begin(), hookUser) < 2;
    }

    // Assigned covers the two riders and any actor still holding a pincer
    // seat, so a released passenger stays committed to the mechanic (no
    // formation or Mangle staging move while the window or warning lasts)
    // until its exit lands.
    static MagmawHookAssignment ResolveHookAssignment(
        Blackboard const& board, ActorSnapshot const& bot, ObjectGuid botGuid)
    {
        std::vector<ObjectGuid> const hookUsers = BuildHookUsers(board);
        if (!IsAssignedHookUser(hookUsers, botGuid)
            && !SeatedOnPincer(board, bot))
            return {};
        return { true, board.FindActor(bot.VehicleGuid),
            FindActorByEntry(board, SpikeEntry) };
    }

    static bool IsPincerVehicle(ActorSnapshot const& vehicle)
    {
        return vehicle.Entry == PincerLeftEntry
            || vehicle.Entry == PincerRightEntry;
    }

    static bool HookPairReady(Blackboard const& board)
    {
        std::vector<ObjectGuid> const hookUsers = BuildHookUsers(board);
        if (hookUsers.size() < 2 || hookUsers[0] == hookUsers[1])
            return false;

        ActorSnapshot const* first = board.FindActor(hookUsers[0]);
        ActorSnapshot const* second = board.FindActor(hookUsers[1]);
        if (!first || !second || !first->Alive || !second->Alive
            || first->VehicleGuid.IsEmpty() || second->VehicleGuid.IsEmpty()
            || first->VehicleGuid == second->VehicleGuid)
            return false;

        ActorSnapshot const* firstVehicle = board.FindActor(
            first->VehicleGuid);
        ActorSnapshot const* secondVehicle = board.FindActor(
            second->VehicleGuid);
        return firstVehicle && secondVehicle && firstVehicle->Alive
            && secondVehicle->Alive && IsPincerVehicle(*firstVehicle)
            && IsPincerVehicle(*secondVehicle)
            && firstVehicle->Guid != secondVehicle->Guid
            && firstVehicle->Entry != secondVehicle->Entry;
    }

    static BotNativeAction::Candidate BuildHookCandidate(Blackboard const& board,
        ActorSnapshot const& vehicle, ActorSnapshot const& spike)
    {
        BotNativeAction::Candidate hook;
        hook.Id.ScopeKey = board.CurrentScope.Key();
        hook.Id.Strategy = "adaptive_magmaw";
        hook.Id.Mechanic = "launch_native_hook";
        hook.Id.Actor = spike.Guid;
        hook.Id.EventGeneration = board.Revision;
        hook.ActionPriority = BotActionArbitration::Priority::Mechanic;
        hook.Utility = 400.0f;
        hook.ExpiresAtMs = board.ObservedAtMs + 500;
        hook.Action = BotNativeAction::VehicleAction{
            vehicle.Entry == PincerLeftEntry ? 77917u : 77941u,
            spike.Guid };
        return hook;
    }

    static BotNativeAction::Candidate BuildMountCandidate(
        Blackboard const& board, ActorSnapshot const& boss)
    {
        BotNativeAction::Candidate mount;
        mount.Id.ScopeKey = board.CurrentScope.Key();
        mount.Id.Strategy = "adaptive_magmaw";
        mount.Id.Mechanic = "mount_free_pincer";
        mount.Id.Actor = boss.Guid;
        mount.Id.EventGeneration = board.Revision;
        mount.ActionPriority = BotActionArbitration::Priority::Mechanic;
        mount.Utility = 350.0f;
        mount.ExpiresAtMs = board.ObservedAtMs + 500;
        mount.Action = BotNativeAction::SpellClick{ boss.Guid };
        return mount;
    }

    static BotNativeAction::Candidate BuildSeatReleaseCandidate(
        Blackboard const& board, ActorSnapshot const& bot)
    {
        BotNativeAction::Candidate release;
        release.Id.ScopeKey = board.CurrentScope.Key();
        release.Id.Strategy = "adaptive_magmaw";
        release.Id.Mechanic = "release_pincer_seat";
        release.Id.Actor = bot.VehicleGuid;
        release.Id.EventGeneration = board.Revision;
        release.ActionPriority = BotActionArbitration::Priority::Mechanic;
        release.Utility = 420.0f;
        release.ExpiresAtMs = board.ObservedAtMs + 500;
        release.Action = BotNativeAction::VehicleExit{};
        return release;
    }

    // A healer rider mounts last: only once the other rider holds a pincer,
    // so its seat completes the pair and the launch follows at once. Until
    // then it waits at the approach point, where it can still heal. Two
    // healer riders mount in list order.
    static bool MayMountPincer(Blackboard const& board,
        std::vector<ObjectGuid> const& hookUsers, ActorSnapshot const& bot)
    {
        if (bot.Role != "healer")
            return true;
        if (hookUsers.size() < 2)
            return false;
        bool const first = hookUsers[0] == bot.Guid;
        ActorSnapshot const* partner = board.FindActor(
            hookUsers[first ? 1 : 0]);
        if (!partner || !partner->Alive)
            return false;
        return SeatedOnPincer(board, *partner)
            || (first && partner->Role == "healer");
    }

    static std::optional<BotNativeAction::Candidate> ProposeHookInteraction(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        std::vector<ObjectGuid> const hookUsers = BuildHookUsers(board);
        if (!IsAssignedHookUser(hookUsers, botGuid))
            return SeatedOnPincer(board, bot)
                ? std::optional<BotNativeAction::Candidate>(
                    BuildSeatReleaseCandidate(board, bot))
                : std::nullopt;
        ActorSnapshot const* vehicle = board.FindActor(bot.VehicleGuid);
        ActorSnapshot const* spike = FindActorByEntry(board, SpikeEntry);
        if (vehicle && spike && IsPincerVehicle(*vehicle)
            && HookPairReady(board))
            return BuildHookCandidate(board, *vehicle, *spike);
        if (boss.Interactable && bot.VehicleGuid.IsEmpty()
            && MayMountPincer(board, hookUsers, bot))
            return BuildMountCandidate(board, boss);
        return std::nullopt;
    }

    // Native reach inputs. The snapshot carries no per-unit combat reach, so
    // these are the units' own values: Magmaw is world DB creature_model_info
    // 32679 CombatReach 15 x creature_template scale 1; a player rider is
    // DEFAULT_PLAYER_COMBAT_REACH 1.5 x scale 1. Tests pin both to the data
    // and the engine constants.
    static constexpr float MagmawCombatReach = 15.0f;
    static constexpr float RiderCombatReach = 1.5f;
    // Unit::GetMeleeRange: attacker reach + target reach + 4/3, at least
    // NOMINAL_MELEE_RANGE, compared 3D centre to centre.
    static float NativeMeleeReach(float attackerReach, float targetReach)
    {
        return std::max(attackerReach + targetReach + 1.3333334f, 5.0f);
    }
    // The bot SpellClick executor admits IsWithinDistInMap(clickable,
    // INTERACTION_DISTANCE): 5 yd plus both combat reaches, 3D.
    static float NativeClickReach(float clickerReach, float clickableReach)
    {
        return 5.0f + clickerReach + clickableReach;
    }
    // Riders wait this far beyond Magmaw's melee reach (17.83 yd for a
    // player), 20.33 yd from his centre. A rider stops within the arrival
    // tolerance, so it is always at least 1.5 yd outside the reach and still
    // inside the 21.5 yd click reach: the click needs no walk when the window
    // opens.
    static constexpr float HookWaitMeleeMargin = 2.5f;
    static constexpr float HookWaitArrivalTolerance = 1.0f;

    static float HookWaitRadius()
    {
        return NativeMeleeReach(MagmawCombatReach, RiderCombatReach)
            + HookWaitMeleeMargin;
    }

    // The wait point sits on the room-side ray that carries the support and
    // ranged anchors and the pincer point, HookWaitRadius from Magmaw's centre
    // in 3D at the declared floor height. Magmaw's LOS point is his hit
    // sphere, 15 yd out on the same ray, so the sight line is ~5 yd of open
    // floor; the 4 yd pincer point failed LOS because it stands under him.
    static std::optional<Vector3> ResolveHookWaitDestination(
        Blackboard const& board, ActorSnapshot const& boss)
    {
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return std::nullopt;
        float const dx = anchors->Support.X - boss.Position.X;
        float const dy = anchors->Support.Y - boss.Position.Y;
        float const length = std::sqrt(dx * dx + dy * dy);
        float const dz = anchors->Support.Z - boss.Position.Z;
        float const radius = HookWaitRadius();
        if (length < 0.01f || !(radius > std::fabs(dz)))
            return std::nullopt;
        float const planar = std::sqrt(radius * radius - dz * dz);
        return Vector3{ boss.Position.X + dx / length * planar,
            boss.Position.Y + dy / length * planar, anchors->Support.Z };
    }

    // From the Mangle warning until the mount window opens, riders wait
    // outside Magmaw's melee reach: the seize wipes the tank's threat and
    // Magmaw stays aggressive until Prepare Massive Crash (3.5 s later).
    // Only the open window (Massive Crash, Magmaw passive) sends them in.
    static std::optional<BotNativeAction::Candidate> ProposeHookPreposition(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        MagmawHookAssignment const assignment = ResolveHookAssignment(board,
            bot, botGuid);
        if (!assignment.Assigned || assignment.Vehicle || boss.Interactable
            || !PincerWarningObserved(board))
            return std::nullopt;

        std::optional<Vector3> const destination =
            ResolveHookWaitDestination(board, boss);
        if (!destination || Distance2d(bot.Position, *destination)
                <= HookWaitArrivalTolerance)
            return std::nullopt;
        return BuildPointMovement(board, *destination,
            "pincer_preposition", BotActionArbitration::Priority::Mechanic,
            365.0f);
    }

    static std::optional<BotNativeAction::Candidate> ProposeHookApproach(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        MagmawHookAssignment const assignment = ResolveHookAssignment(board,
            bot, botGuid);
        if (!assignment.Assigned || assignment.Vehicle || !boss.Interactable
            || Distance2d(bot.Position, boss.Position)
                <= HookInteractionDistance)
            return std::nullopt;

        std::optional<Vector3> const destination =
            ResolveHookApproachDestination(board, boss);
        if (!destination)
            return std::nullopt;
        return BuildPointMovement(board, *destination,
            "pincer_approach", BotActionArbitration::Priority::Mechanic,
            375.0f);
    }

    static bool HasAura(ActorSnapshot const& actor, uint32 spellId)
    {
        return std::any_of(actor.Auras.begin(), actor.Auras.end(),
            [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
    }

    static ActorSnapshot const* FindActorByEntry(Blackboard const& board,
        uint32 entry)
    {
        auto find = [entry](std::vector<ActorSnapshot> const& actors)
            -> ActorSnapshot const*
        {
            auto itr = std::find_if(actors.begin(), actors.end(),
                [entry](ActorSnapshot const& actor)
                {
                    return actor.Alive && actor.Entry == entry;
                });
            return itr == actors.end() ? nullptr : &*itr;
        };
        if (ActorSnapshot const* actor = find(board.Hostiles))
            return actor;
        if (ActorSnapshot const* actor = find(board.Summons))
            return actor;
        return find(board.Interactables);
    }
