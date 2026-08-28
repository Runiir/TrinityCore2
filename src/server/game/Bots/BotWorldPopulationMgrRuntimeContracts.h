#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_RUNTIME_CONTRACTS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_RUNTIME_CONTRACTS_H

// This fragment is included inside BotWorldPopulationMgr's private section so
// runtime state retains the manager's private nested-type ownership.
    struct PartyRuntime
    {
        std::vector<WorldBotState> Bots;
        std::vector<WorldBotState> CalibrationBots;
        ObjectGuid GroupGuid;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        std::map<uint32, std::string> RoleByGuid;
        // Per-bot cursor for the bounded diagnostic trace export.  This keeps
        // repeated botauto_trace polls incremental without changing the
        // authoritative in-memory trace or dropping current decisions.
        mutable std::map<uint32, uint64> TraceExportCursorByGuid;

        ObjectGuid ValidationRouteFocusGuid;
        uint32 ValidationRouteFocusEntry = 0;
        uint32 ValidationRouteFocusMapId = 0;
        float ValidationRouteFocusX = 0.0f;
        float ValidationRouteFocusY = 0.0f;
        float ValidationRouteFocusZ = 0.0f;
        uint64 ValidationRouteFocusSeenMs = 0;
        ObjectGuid ValidationRouteAddFocusGuid;
        uint64 ValidationRouteAddFocusGeneration = 0;
        GuidSet ValidationRouteRecordedKillGuids;
        GuidSet ValidationRoutePackMemberGuids;
        GuidSet ValidationRoutePackEngagedGuids;
        GuidSet ValidationRoutePackDeathGuids;
        GuidSet ValidationRoutePackTransitionGuids;
        GuidSet ValidationRoutePendingFinalTransitionGuids;
        GuidSet ValidationRouteFinalTransitionGuids;
        uint64 ValidationRoutePackGeneration = 0;
        uint64 ValidationRoutePackSequence = 1;
        uint32 ValidationRouteCompletedPackCount = 0;
        bool ValidationRoutePackObservedEngagement = false;
        bool ValidationRouteDrudgePrepullStaged = false;
        uint64 ValidationRouteDrudgePrepullAttemptId = 0;
        uint32 ValidationRouteDrudgePrepullWipeGeneration = 0;
        uint64 ValidationRouteDrudgePrepullRouteGeneration = 0;
        uint64 ValidationRouteDrudgeChargeGeneration = 0;
        uint64 ValidationRouteDrudgeChargeLandedGeneration = 0;
        uint64 ValidationRouteDrudgeChargeObservedAtMs = 0;
        ObjectGuid ValidationRouteDrudgeChargeSourceGuid;
        ObjectGuid ValidationRouteDrudgeChargeTargetGuid;
        uint32 ValidationRouteDrudgeChargeSourceSpawnId = 0;
        float ValidationRouteDrudgeChargeObservedDistance = 0.0f;
        bool ValidationRouteDrudgeChargeRangeValid = false;
        bool ValidationRouteDrudgeChargeIntervalValid = false;
        std::map<uint32, uint64> ValidationRouteDrudgeLastChargeMsBySpawn;
        std::deque<ValidationRouteDrudgeChargeObservation> ValidationRouteDrudgeChargeObservations;
        uint64 ValidationRouteDrudgeEvidenceAttemptId = 0;
        uint32 ValidationRouteDrudgeEvidenceWipeGeneration = 0;
        uint64 ValidationRouteDrudgeEvidenceRouteGeneration = 0;
        std::vector<uint32> ValidationRouteDrudgeEvidenceSourceSpawnIds;
        uint32 ValidationRouteDrudgeChargePreparedCount = 0;
        uint32 ValidationRouteDrudgeChargeDeliveredCount = 0;
        bool ValidationRouteDrudgeChargeQueueOverflow = false;
        std::map<uint32, uint32> ValidationRouteDrudgeDeliveredBySpawn;
        std::map<uint32, uint32> ValidationRouteDrudgeValidIntervalsBySpawn;
        std::set<uint32> ValidationRouteDrudgeReseparatedRosterGuids;
        std::set<uint32> ValidationRouteDrudgeOwnershipRosterGuids;
        std::set<uint32> ValidationRouteDrudgeTauntRosterGuids;
        std::set<uint32> ValidationRouteDrudgeHealthSyncRosterGuids;
        std::set<uint32> ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids;
        uint32 ValidationRouteDrudgeHealthSyncHoldSourceSpawnId = 0;
        uint32 ValidationRouteDrudgeHealthSyncHoldTankGuid = 0;
        float ValidationRouteDrudgeHealthSyncHoldLowerPct = 0.0f;
        float ValidationRouteDrudgeHealthSyncHoldPeerPct = 0.0f;
        bool ValidationRouteDrudgeHealthSyncHoldLowerAlive = false;
        bool ValidationRouteDrudgeHealthSyncHoldPeerAlive = false;
        uint64 ValidationRouteDrudgeDeathAttemptId = 0;
        uint32 ValidationRouteDrudgeDeathWipeGeneration = 0;
        uint64 ValidationRouteDrudgeDeathRouteGeneration = 0;
        uint32 ValidationRouteDrudgeDeathSourceSpawnId = 0;
        uint32 ValidationRouteDrudgeDeathSourceGuid = 0;
        uint32 ValidationRouteDrudgeSurvivorSourceSpawnId = 0;
        uint32 ValidationRouteDrudgeSurvivorSourceGuid = 0;
        uint64 ValidationRouteDrudgeDeathEvidenceSequence = 0;
        uint64 ValidationRouteDrudgeRageWaitEvidenceSequence = 0;
        uint64 ValidationRouteDrudgeRageAuraEvidenceSequence = 0;
        uint64 ValidationRouteDrudgeHealthSyncEvidenceAttemptId = 0;
        uint32 ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration = 0;
        uint64 ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration = 0;
        std::set<uint32> ValidationRouteDrudgeProfileActionRosterGuids;
        uint64 ValidationRouteDrudgeThreatSeedAttemptId = 0;
        uint64 ValidationRouteDrudgeThreatSeedWipeGeneration = 0;
        uint64 ValidationRouteDrudgeThreatSeedRouteGeneration = 0;
        bool ValidationRouteDrudgeThreatSeedClosed = false;
        bool ValidationRouteDrudgeThreatSeedComplete = false;
        bool ValidationRouteDrudgeThreatSeedFailure = false;
        std::set<uint32> ValidationRouteDrudgeThreatSeedRosterGuids;
        std::vector<ValidationRouteDrudgeThreatSeedEvidence> ValidationRouteDrudgeThreatSeedEvidenceRows;
        uint64 ValidationRoutePackClearCandidateSinceMs = 0;
        uint64 ValidationRouteNodeClearCandidateSinceMs = 0;
        ObjectGuid ValidationRouteBossProgressTargetGuid;
        uint32 ValidationRouteBossSlowProgressCount = 0;
        bool ValidationRouteBossAddDensityPhase = false;
        uint64 ValidationRouteBossAddDensityGeneration = 0;
        bool ValidationRouteLargePassiveSwarmStaging = false;
        uint64 ValidationRouteLargePassiveSwarmStagingGeneration = 0;
        bool ValidationRouteBossAddEscapeActive = false;
        uint64 ValidationRouteBossAddEscapeGeneration = 0;
        float ValidationRouteBossAddEscapeX = 0.0f;
        float ValidationRouteBossAddEscapeY = 0.0f;
        float ValidationRouteBossAddEscapeZ = 0.0f;
        float ValidationRouteBossAddEscapeAnchorX = 0.0f;
        float ValidationRouteBossAddEscapeAnchorY = 0.0f;
        float ValidationRouteBossAddEscapeAnchorZ = 0.0f;
        float ValidationRouteBossAddCentroidX = 0.0f;
        float ValidationRouteBossAddCentroidY = 0.0f;
        GuidSet ValidationRouteBossAddEscapeIssuedGuids;
        bool ValidationRouteActivationApplied = false;
        uint32 ValidationRouteActivationAttempts = 0;
        uint32 ValidationRouteCanonicalBossRecoveryAttempts = 0;
        uint64 ValidationRouteCanonicalBossRecoveryLastMs = 0;
        std::vector<ValidationRouteManifestNode> ValidationRouteManifest;
        std::string ValidationRouteManifestSha256;
        std::vector<ValidationRouteEvidence> ValidationRouteTerminalEvidence;
        std::vector<ValidationRouteEvidence> ValidationRouteBossDeathEvidence;
        size_t ValidationRouteManifestIndex = 0;
        uint64 ValidationRouteGeneration = 0;
        ObjectGuid ValidationRouteEngagedBossGuid;
        uint64 ValidationRouteEngagedBossGeneration = 0;
        uint32 ValidationRouteEngagedBossMapId = 0;
        uint32 ValidationRouteEngagedBossInstanceId = 0;
        ObjectGuid ValidationRouteConfirmedBossDeathGuid;
        uint64 ValidationRouteConfirmedBossDeathGeneration = 0;
        uint32 ValidationRouteConfirmedBossDeathMapId = 0;
        uint32 ValidationRouteConfirmedBossDeathInstanceId = 0;
        uint32 ValidationRouteProgressBaselineKills = 0;
        bool ValidationRouteObservedEngagement = false;
        bool ValidationRouteObservedDeadScriptTarget = false;
        bool ValidationRouteManifestAdvancePending = false;
        uint64 ValidationRouteManifestAdvanceGeneration = 0;
        bool ValidationRouteManifestComplete = false;
        std::string ValidationRouteManifestAdvanceReason;
        std::string ValidationRouteManifestLoadError;

        mutable std::map<uint32, std::string> LastCombatMaskByBot;
        mutable std::map<uint32, std::string> LastCombatRejectsByBot;
        mutable std::map<uint32, std::string> LastChosenCombatByBot;
        mutable std::map<uint32, std::string> LastActionCategoryByBot;
        mutable std::map<uint32, RoleSaturationState> LastSaturationByBot;
        uint64 NextHealCastId = 1;
        std::map<uint64, PendingHealCast> PendingHealCasts;
        std::map<CombatLogAbilityKey, CombatLogAbilityAggregate> CombatLogAbilities;
        std::map<std::tuple<uint64, CombatLogPerspective, uint32, bool, uint64>, CombatLogSecondBucket> CombatLogSecondBuckets;
        std::deque<CombatLogEvent> CombatLogRecentEvents;
        uint64 CombatLogEventCount = 0;
        uint64 CombatLogRecentEventsDropped = 0;
    };

    struct RaidRosterItemIdentity
    {
        uint8 Slot = 0;
        uint32 Guid = 0;
        uint32 Entry = 0;
        uint32 EnchantId = 0;
        std::vector<uint32> GemItemIds;
        uint32 ReforgeId = 0;
    };

    struct RaidRosterSlot
    {
        std::string RosterSlotId;
        std::string LeaseRoleSlot;
        uint32 SlotIndex = 0;
        ObjectGuid Guid;
        uint32 AccountId = 0;
        std::string AccountName;
        std::string CharacterName;
        uint8 SubGroup = 0;
        std::string Role;
        uint8 ClassId = 0;
        std::string ClassSpec;
        float AverageItemLevel = 0.0f;
        std::string GearIdentity;
        std::string TalentIdentity;
        std::string GlyphIdentity;
        std::vector<uint32> Talents;
        std::vector<uint32> Glyphs;
        std::vector<RaidRosterItemIdentity> GearManifest;
        bool Active = false;
        bool LeaseOwned = false;
    };

    // Raid preparation receipts retain native item-use evidence per exact
    // roster member.  A receipt is complete only after the session callback,
    // inventory decrement, expected aura observation, and cooldown snapshot
    // have all been observed by the runtime.
    struct RaidPrepullConsumableReceipt
    {
        uint32 ItemId = 0;
        uint32 SpellId = 0;
        uint32 AuraSpellId = 0;
        uint32 RequiredUses = 1;
        uint32 SubmissionCount = 0;
        uint32 SuccessfulUseCount = 0;
        uint32 PreUseItemCount = 0;
        uint32 PostUseItemCount = 0;
        uint32 CooldownRemainingMs = 0;
        uint32 GlobalCooldownRemainingMs = 0;
        uint64 SubmittedAtMs = 0;
        uint64 FinishedAtMs = 0;
        uint64 NextRetryAtMs = 0;
        uint64 AuraDeadlineAtMs = 0;
        uint64 AuraObservedAtMs = 0;
        uint64 AuraTimedOutAtMs = 0;
        uint64 CooldownObservedAtMs = 0;
        ObjectGuid SubmittedItemGuid;
        ObjectGuid FinishedItemGuid;
        bool NativeUseFinishedSuccessfully = false;
        bool NativeUseAwaitingAura = false;
        bool CooldownObserved = false;
        std::string Phase;
        std::string FailureReason;
    };

    struct RaidPrepullConsumableMember
    {
        uint64 AttemptId = 0;
        uint64 WipeGeneration = 0;
        uint64 RouteGeneration = 0;
        std::string RosterSlotId;
        std::string Role;
        std::string ClassSpec;
        bool AliveAndHealed = false;
        bool Failed = false;
        std::string FailureReason;
        RaidPrepullConsumableReceipt Flask;
        RaidPrepullConsumableReceipt Food;
        RaidPrepullConsumableReceipt Prepot;
        uint32 CombatPotionReservedCount = 0;
        uint64 SetupReadyAtMs = 0;
        uint64 PrepotEligibleAtMs = 0;
    };

    struct RaidNativeSignalState
    {
        bool Initialized = false;
        bool Alive = false;
        bool HasCorpse = false;
        bool Released = false;
        bool OutsideOriginalInstance = false;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        uint64 WipeGeneration = 0;
        uint64 DeathSequence = 0;
        uint64 CorpseSequence = 0;
        uint64 ReleaseSequence = 0;
        uint64 RunbackSequence = 0;
        uint64 ReentrySequence = 0;
        uint64 ResurrectionSequence = 0;
    };

    struct CohortAdmissionMemberReceipt
    {
        ObjectGuid Guid;
        ObjectGuid GroupGuid;
        ObjectGuid LeaderGuid;
        std::string RosterSlotId;
        std::string Role;
        std::string ClassSpec;
        uint8 ClassId = 0;
        uint8 ActiveSpecIndex = 0;
        uint32 PrimaryTalentTreeId = 0;
        uint32 ActiveTalentCount = 0;
        std::vector<uint32> ActiveTalentSpellIds;
        bool PetIdentityPresent = false;
        uint32 PetId = 0;
        uint32 PetEntry = 0;
        ObjectGuid PetOwnerGuid;
        uint32 PetSpellCount = 0;
        std::vector<std::pair<uint32, uint8>> PetSpellbook;
        std::string PetSpellbookSha256;
        std::vector<uint32> PetAutocastSpellIds;
        std::string GearProfileId;
        uint32 GearItemCount = 0;
        std::vector<RaidRosterItemIdentity> GearManifest;
        std::string GearManifestSha256;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        uint8 ExpectedDifficulty = 0;
        uint8 PlayerDifficulty = 0;
        int16 MapDifficulty = -1;
        float SpawnX = 0.0f;
        float SpawnY = 0.0f;
        float SpawnZ = 0.0f;
        float SpawnO = 0.0f;
        bool ServerProvisioned = false;
        bool InitialBaselineNormalized = false;
        bool InitialAliveStateVerified = false;
    };

    struct RaidRuntime
    {
        bool Active = false;
        bool RaidInstance = false;
        bool ServerProvisioningComplete = false;
        bool BotActionsEnabled = false;
        bool RosterComplete = false;
        bool DifficultyMatches = false;
        bool DifficultyReadbackComplete = false;
        bool UniqueLeases = false;
        ObjectGuid GroupGuid;
        ObjectGuid LeaderGuid;
        uint32 ExpectedSize = 0;
        uint32 ActiveSize = 0;
        uint32 AliveSize = 0;
        uint8 ExpectedDifficulty = 0;
        uint8 GroupDifficulty = 0;
        int16 MapDifficulty = -1;
        uint32 DifficultyMemberCount = 0;
        uint32 DifficultyMatchingMemberCount = 0;
        uint32 ProvisionedMemberCount = 0;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        uint32 LockoutSaveId = 0;
        uint64 ServerEpoch = 0;
        uint64 AttemptId = 0;
        uint64 ProfileGeneration = 0;
        std::string ProfileContentHash;
        uint64 AdmissionCommittedAtMs = 0;
        uint64 AdmissionAttemptId = 0;
        bool AdmissionActionGateEnabled = false;
        std::string AdmissionScenarioId;
        std::string AdmissionRuntimeProfile;
        std::string AdmissionRouteManifestSha256;
        uint32 AdmissionRecoveryEntranceAreaTriggerId = 0;
        uint32 AdmissionRecoveryEntranceSourceMapId = 0;
        uint32 AdmissionRecoveryEntranceTargetMapId = 0;
        uint32 AdmissionEntranceMapId = 0;
        float AdmissionEntranceX = 0.0f;
        float AdmissionEntranceY = 0.0f;
        float AdmissionEntranceZ = 0.0f;
        float AdmissionEntranceO = 0.0f;
        std::map<uint32, CohortAdmissionMemberReceipt> AdmissionReceiptByGuid;
        uint64 AssignmentGeneration = 0;
        uint64 EvidenceSequence = 0;
        uint64 WipeGeneration = 0;
        uint64 BossResetGeneration = 0;
        uint64 BossResetGenerationAtWipe = 0;
        uint64 RecoveryGeneration = 0;
        bool EncounterInProgress = false;
        bool ReadyCheckSatisfied = false;
        bool RosterCompositionValid = false;
        bool NativeDeathObserved = false;
        bool NativeCorpseObserved = false;
        bool NativeReleaseObserved = false;
        bool NativeResurrectionObserved = false;
        bool NativeRunbackObserved = false;
        bool NativeReadyCheckActionObserved = false;
        bool NativeReadyCheckPending = false;
        uint32 NativeReadyCheckResponseCount = 0;
        uint64 NativeReadyCheckActionGeneration = 0;
        uint64 NativeReadyCheckActionAttemptId = 0;
        uint64 NativeReadyCheckActionWipeGeneration = 0;
        uint64 NativeReadyCheckAssignmentGeneration = 0;
        uint64 NativeReadyCheckActionEvidenceSequence = 0;
        std::set<uint32> NativeReadyCheckResponders;
        bool NativeRecoveryEvidenceComplete = false;
        // Once an exact native all-dead transition is observed, keep the
        // entire cohort in recovery authority until the current wipe's native
        // ready-check-backed evidence is complete.  This is deliberately a
        // raid-scoped latch rather than a transient WipeState predicate: the
        // latter can briefly look route-ready on the first all-alive sample
        // after resurrection, before the next runtime refresh records the
        // ready-check/evidence edge.
        bool NativeRecoveryHoldActive = false;
        // Bind the hold to the exact route node that observed the native
        // all-dead edge. Wipe/runtime fields are monotonic across nodes and
        // therefore cannot authorize recovery on their own.
        uint64 NativeRecoveryRouteGeneration = 0;
        std::string NativeRecoveryNodeId;
        // A raid instance can contain an active trash pack without an
        // IN_PROGRESS boss state. Native recovery must observe the pack
        // itself evading/resetting before released ghosts may re-enter.
        bool NativeHostileActivityActive = false;
        bool NativeHostileActivitySeen = false;
        bool NativeHostileActivitySeenAtWipe = false;
        bool NativeHostileInactivityObserved = false;
        uint64 NativeHostileInactiveSinceMs = 0;
        uint64 NativeHostileResetGeneration = 0;
        uint64 NativeHostileResetGenerationAtWipe = 0;
        uint64 NativeHostileObservationAttemptId = 0;
        uint64 NativeHostileObservationRouteGeneration = 0;
        std::string NativeHostileObservationNodeId;
        uint32 NativeHostileActivityEntry = 0;
        ObjectGuid NativeHostileActivityGuid;
        std::string NativeHostileActivityReason;
        std::string StrategyId;
        std::string PreviousStrategyId;
        uint64 StrategyTransitionRouteGeneration = 0;
        std::string EncounterPhase = "formation";
        std::string WipeState = "ready";
        std::string RecoveryState = "none";
        std::vector<uint8> BossStates;
        std::map<uint32, RaidRosterSlot> RosterByGuid;
        std::map<uint32, RaidNativeSignalState> NativeSignalsByGuid;
        bool PrepullConsumablesRequired = false;
        bool PrepullConsumablesReady = false;
        bool PrepullConsumablesFailed = false;
        uint64 PrepullConsumablesAttemptId = 0;
        uint64 PrepullConsumablesWipeGeneration = 0;
        uint64 PrepullConsumablesRouteGeneration = 0;
        uint64 PrepullConsumablesReadyAtMs = 0;
        std::string PrepullConsumablesFailureReason;
        std::map<uint32, RaidPrepullConsumableMember> PrepullConsumablesByGuid;
        // One native Bloodlust trigger belongs to the exact Magmaw 10N raid
        // scope.  These fields are a raid latch, not per-bot cooldown state:
        // the native spell/GCD/readiness gates remain authoritative and the
        // latch is committed only after CastSpell submission succeeds.
        bool MagmawBloodlustSubmitted = false;
        bool MagmawBloodlustAuraObserved = false;
        uint64 MagmawBloodlustAttemptId = 0;
        uint64 MagmawBloodlustWipeGeneration = 0;
        uint64 MagmawBloodlustRouteGeneration = 0;
        uint64 MagmawBloodlustSubmittedAtMs = 0;
        ObjectGuid MagmawBloodlustOwnerGuid;
        ObjectGuid MagmawBloodlustHeadGuid;
        std::map<uint32, std::string> AccountNameById;
        std::set<uint32> AccountNameLookupAttempted;
    };

    struct CohortRuntime
    {
        std::string Id;
        uint64 AttemptId = 0;
        uint64 PinnedProfileGeneration = 0;
        std::string PinnedProfileContentHash;
        std::set<uint32> RosterLeases;
        bool Active = false;
        BotWorldRuntimeMode RuntimeMode = BotWorldRuntimeMode::ManualExperiment;
        // Synthetic setup is permitted only inside an isolated fixture mode.
        // It is always non-certifying and may never coexist with live Party().Bots.
        bool NonCertifyingAssistance = false;
        uint64 ExperimentId = 0;
        uint64 RunId = 0;
        uint32 ElapsedMs = 0;
        uint32 RecordingWindowElapsedMs = 0;
        uint32 RecordingWindowIndex = 0;
        uint64 EncounterSnapshotRevision = 0;
        uint64 EncounterSnapshotNextRefreshMs = 0;
        std::shared_ptr<BotEncounter::Blackboard const> EncounterSnapshot;
        BotWorldExperimentConfig Config;
        std::string ProfileManifestPath;
        std::map<std::string, BotWorldExperimentProfile> RuntimeProfiles;
        std::vector<std::string> RuntimeProfileOrder;
        std::string SelectedProfileName;
        std::string PreparedPoolTagFilter;
        std::vector<std::string> PreparedClassSpecs;
        std::string ProfileManifestLoadError;
        bool RuntimeProfilesLoaded = false;
        bool RuntimeProfileDirty = false;
        bool RuntimeProfileSelectionPending = false;
        BotExperienceLearningConfig LearningConfig;
        BotPolicyModelConfig PolicyModelConfig;
        bool CalibrationActive = false;
        bool CalibrationStopping = false;
        bool CalibrationAoePhase = false;
        bool CalibrationWindowComplete = false;
        std::string CalibrationFailureReason;
        std::string CalibrationMode = "single_target_300";
        std::string CalibrationTargetSpec;
        uint32 CalibrationSeed = 1;
        ObjectGuid CalibrationTargetGuid;
        ObjectGuid CalibrationFixtureTargetGuid;
        uint32 CalibrationFixtureTargetEntry = 0;
        uint32 CalibrationFixtureExpectedTargetLevel = 0;
        uint32 CalibrationFixtureExpectedTargetArmor = 0;
        uint32 CalibrationFixtureExpectedTargetCreatureType = 0;
        uint32 CalibrationFixtureExpectedTargetMaxHealth = 0;
        uint32 CalibrationFixtureObservedTargetLevel = 0;
        uint32 CalibrationFixtureObservedTargetArmor = 0;
        uint32 CalibrationFixtureObservedTargetCreatureType = 0;
        uint32 CalibrationFixtureObservedTargetCreatureTypeMask = 0;
        uint32 CalibrationFixtureObservedTargetMaxHealth = 0;
        uint32 CalibrationFixtureTargetMapId = 0;
        float CalibrationFixtureTargetX = 0.0f;
        float CalibrationFixtureTargetY = 0.0f;
        float CalibrationFixtureTargetZ = 0.0f;
        float CalibrationFixtureTargetNearestHostileClearance = 0.0f;
        uint64 CalibrationFixtureTargetProvisionedAtMs = 0;
        uint64 CalibrationFixtureTargetObservedBeforeScoringAtMs = 0;
        uint32 CalibrationFixtureBeforeScoringTargetLevel = 0;
        uint32 CalibrationFixtureBeforeScoringTargetArmor = 0;
        uint32 CalibrationFixtureBeforeScoringTargetCreatureType = 0;
        uint32 CalibrationFixtureBeforeScoringTargetCreatureTypeMask = 0;
        uint32 CalibrationFixtureBeforeScoringTargetMaxHealth = 0;
        uint32 CalibrationFixtureBeforeScoringTargetMapId = 0;
        ObjectGuid CalibrationFixtureBeforeScoringTargetGuid;
        float CalibrationFixtureBeforeScoringTargetX = 0.0f;
        float CalibrationFixtureBeforeScoringTargetY = 0.0f;
        float CalibrationFixtureBeforeScoringTargetZ = 0.0f;
        float CalibrationFixtureBeforeScoringBotTargetDistance = 0.0f;
        bool CalibrationFixtureBeforeScoringTargetInCombat = false;
        bool CalibrationFixtureBeforeScoringTargetHasVictim = false;
        uint32 CalibrationFixtureTargetPassiveObservationSampleCount = 0;
        uint32 CalibrationFixtureTargetVictimObservationSampleCount = 0;
        uint32 CalibrationFixtureTargetAttackEventCount = 0;
        uint32 CalibrationFixtureTargetOriginatedDamageEventCount = 0;
        uint64 CalibrationFixtureTargetFirstPassiveObservedAtMs = 0;
        uint64 CalibrationFixtureTargetLastPassiveObservedAtMs = 0;
        uint64 CalibrationFixtureTargetMaximumPassiveObservationGapMs = 0;
        float CalibrationFixtureBotSpawnX = 0.0f;
        float CalibrationFixtureBotSpawnY = 0.0f;
        float CalibrationFixtureBotSpawnZ = 0.0f;
        float CalibrationFixtureBotTargetDistance = 0.0f;
        bool CalibrationFixtureNativeLineOfSight = false;
        bool CalibrationFixtureNativePathReachable = false;
        bool CalibrationFixtureNativeMeleeReachable = false;
        bool CalibrationFixtureNativeDryLand = false;
        bool CalibrationFixtureGeometryValidated = false;
        std::string CalibrationFixtureProfileLane;
        ObjectGuid CalibrationInterruptTargetGuid;
        uint64 CalibrationStartedMs = 0;
        uint64 CalibrationScoredStartedMs = 0;
        uint64 CalibrationScoredEndedMs = 0;
        uint64 CalibrationLastPostWindowDrainMs = 0;
        uint64 CalibrationLastControlledEventSecond = std::numeric_limits<uint64>::max();
        uint32 CalibrationCrossWindowEventCount = 0;
        uint32 CalibrationExcludedBoundaryDamageEventCount = 0;
        std::string CalibrationResetId;
        std::string CalibrationCurrentDamagePhase;
        std::map<uint32, CalibrationMetrics> CalibrationMetricsByGuid;
        bool CalibrationPreviousWindowValid = false;
        bool CalibrationPreviousAoePhase = false;
        std::map<uint32, CalibrationMetrics> CalibrationPreviousMetrics;
        std::map<uint32, CalibrationMetrics> CalibrationBestSingleMetrics;
        std::map<uint32, CalibrationMetrics> CalibrationBestAoeMetrics;
        uint32 CalibrationCompletedSingleWindows = 0;
        uint32 CalibrationCompletedAoeWindows = 0;
        std::set<uint32> FailedSpawnGuids;
        std::string LastPopulationFailureReason;
        // A runtime/encounter terminal is different from a transient
        // population failure.  Keep it for the entire native attempt so
        // status/capture can stop promptly and every living/dead member holds
        // the same fail-closed state until the coordinator starts a new run.
        std::string ValidationAttemptFailureReason;
        uint64 ValidationAttemptFailureAttemptId = 0;
        uint64 ValidationAttemptFailureRouteGeneration = 0;
        ValidationAdmissionPhase ValidationAdmission = ValidationAdmissionPhase::Provisioning;
        bool ValidationAdmissionStarted = false;
        bool ValidationAdmissionBatchSealed = false;
        bool ValidationRaidAdmissionComplete = false;
        bool ValidationRaidAdmissionFailed = false;
        uint64 LastNativeWorldportDeferredLogMs = 0;
        uint32 SuppressedNativeWorldportDeferredLogs = 0;
        BotWorldStatus Metrics;
        BotTelemetryBuffer TelemetryBuffer;
        BotExperimentCoordinator ExperimentCoordinator;
        PartyRuntime Party;
        RaidRuntime Raid;
    };

    struct BotGuidLease
    {
        uint64 ServerEpoch = 0;
        std::string CohortId;
        uint64 AttemptId = 0;
        std::string RoleSlot;
    };

#endif
