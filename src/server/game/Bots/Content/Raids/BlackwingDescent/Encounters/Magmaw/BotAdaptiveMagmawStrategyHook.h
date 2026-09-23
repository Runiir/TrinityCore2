// Included inside AdaptiveMagmawStrategy private scope.
    static bool IsFixedBaiter(
        std::pair<ObjectGuid, ObjectGuid> const& baiters, ObjectGuid guid)
    {
        return guid == baiters.first || guid == baiters.second;
    }

    // A healer rides only while two other living healers keep healing Mangle.
    static constexpr std::size_t HookHealerMinimumLivingHealers = 3;

    // Static prior of each healer's share of raid healing, lowest first.
    // Baselines 0891a99 k1-k3 (10N): Discipline 0.8-1.8k HPS against
    // Restoration Druid and Holy Paladin at 4-6k. Unlisted specs never ride.
    static std::optional<std::size_t> HookHealerLoadRank(
        std::string_view classSpec)
    {
        static constexpr std::array<std::string_view, 5> order = {
            "discipline_priest", "holy_priest", "restoration_shaman",
            "restoration_druid", "holy_paladin" };
        auto itr = std::find(order.begin(), order.end(), classSpec);
        if (itr == order.end())
            return std::nullopt;
        return std::size_t(std::distance(order.begin(), itr));
    }

    static ObjectGuid SelectHookHealer(Blackboard const& board)
    {
        std::size_t livingHealers = 0;
        ActorSnapshot const* selected = nullptr;
        std::size_t selectedRank = 0;
        for (ActorSnapshot const& member : board.Players)
        {
            if (!member.Alive || member.Role != "healer")
                continue;
            ++livingHealers;
            std::optional<std::size_t> const rank =
                HookHealerLoadRank(member.ClassSpec);
            if (rank && (!selected || *rank < selectedRank
                || (*rank == selectedRank && member.Guid.GetRawValue()
                    < selected->Guid.GetRawValue())))
            {
                selected = &member;
                selectedRank = *rank;
            }
        }
        return selected && livingHealers >= HookHealerMinimumLivingHealers
            ? selected->Guid : ObjectGuid();
    }

    static bool SeatedOnPincer(Blackboard const& board,
        ActorSnapshot const& member)
    {
        ActorSnapshot const* vehicle = member.VehicleGuid.IsEmpty()
            ? nullptr : board.FindActor(member.VehicleGuid);
        return vehicle && vehicle->Alive && IsPincerVehicle(*vehicle);
    }

    // Every hook caller derives the riders from this one ordered list; only
    // the first two are assigned. Preference order:
    //  1. living riders already seated on a pincer, so a roster change during
    //     the ride never strands an unassigned actor in a pincer seat;
    //  2. the lowest-load healer while three or more healers are alive;
    //  3. non-baiter DPS by raw GUID, except Balance, which keeps its
    //     stationary casts and the parasite mushroom duty;
    //  4. the previous choice: non-baiter DPS by raw GUID, then any other
    //     non-tank, now by raw GUID instead of board order.
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
                || IsFixedBaiter(baiters, member.Guid))
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
        append(SelectHookHealer(board));
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

    static MagmawHookAssignment ResolveHookAssignment(
        Blackboard const& board, ActorSnapshot const& bot, ObjectGuid botGuid)
    {
        std::vector<ObjectGuid> const hookUsers = BuildHookUsers(board);
        if (!IsAssignedHookUser(hookUsers, botGuid))
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

    static std::optional<BotNativeAction::Candidate> ProposeHookInteraction(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        MagmawHookAssignment const assignment = ResolveHookAssignment(board,
            bot, botGuid);
        if (!assignment.Assigned)
            return std::nullopt;
        if (assignment.Vehicle && assignment.Spike
            && IsPincerVehicle(*assignment.Vehicle)
            && HookPairReady(board))
            return BuildHookCandidate(board, *assignment.Vehicle,
                *assignment.Spike);
        if (boss.Interactable && bot.VehicleGuid.IsEmpty())
            return BuildMountCandidate(board, boss);
        return std::nullopt;
    }

    static std::optional<BotNativeAction::Candidate> ProposeHookPreposition(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        MagmawHookAssignment const assignment = ResolveHookAssignment(board,
            bot, botGuid);
        if (!assignment.Assigned || assignment.Vehicle || boss.Interactable
            || !PincerWarningObserved(board)
            || Distance2d(bot.Position, boss.Position)
                <= HookInteractionDistance)
            return std::nullopt;

        std::optional<Vector3> const destination =
            ResolveHookApproachDestination(board, boss);
        if (!destination)
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
