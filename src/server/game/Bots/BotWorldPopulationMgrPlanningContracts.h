#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_PLANNING_CONTRACTS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_PLANNING_CONTRACTS_H

// This fragment is included inside BotWorldPopulationMgr's private section so
// these contracts retain the manager's private nested-type ownership.
    struct QuestObjectivePlan
    {
        uint32 QuestId = 0;
        int32 RequiredEntry = 0;
        uint32 RequiredCount = 0;
        uint32 CurrentCount = 0;
        bool IsGameObject = false;
        bool IsItemObjective = false;
        uint32 ItemId = 0;
        QuestObjectiveType ObjectiveType = QuestObjectiveType::Kill;
        uint32 RequiredSpellId = 0;
        uint32 ObjectiveIndex = 0;
        bool RequiresTrainingDummy = false;
    };

    struct QuestActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "questing";
        std::string Action = "wait";
        Unit* Target = nullptr;
        uint32 QuestId = 0;
        uint32 RewardChoice = 0;
        uint32 RewardItemId = 0;
    };

    struct BotDiagnosis
    {
        std::string DiagnosisCode = "waiting_decision_tick";
        std::string Severity = "info";
        float Confidence = 0.5f;
        std::string Intent = "increase_character_power";
        std::string CurrentAction = "wait";
        std::string Blocker;
        std::string NextExpectedAction = "wait_for_next_decision_tick";
        std::string SuggestedInvestigation = "inspect_trace_for_repeated_state";
    };

    struct QuestRoutePoint
    {
        bool Valid = false;
        uint32 MapId = 0;
        uint32 ZoneId = 0;
        uint32 QuestId = 0;
        uint32 ObjectiveIndex = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float Score = 0.0f;
        std::string Source;
    };

    struct QuestObjectiveBucket
    {
        uint32 BucketId = 0;
        uint32 MapId = 0;
        float CenterX = 0.0f;
        float CenterY = 0.0f;
        float CenterZ = 0.0f;
        float Score = 0.0f;
        std::vector<QuestObjectivePlan> Objectives;
        std::string Reason;
    };

    struct QuestPortfolioPlan
    {
        uint32 ActiveQuestCount = 0;
        std::vector<QuestObjectiveBucket> Buckets;
        std::vector<QuestObjectivePlan> UnresolvedObjectives;
    };

    struct DungeonTrashPackFeatures
    {
        uint32 PackSize = 0;
        uint32 EliteCount = 0;
        uint32 CasterCount = 0;
        uint32 HealerCount = 0;
        uint32 ActiveCasts = 0;
        uint32 DangerousCasts = 0;
        float InterruptPriority = 0.0f;
        float AoeValue = 0.0f;
        float CcValue = 0.0f;
        float PullRisk = 0.0f;
        float TankThreat = 0.0f;
        float PartyAverageHpPct = 1.0f;
        float LowestAllyHpPct = 1.0f;
        float HealerManaPct = 1.0f;
        bool PatrolNearby = false;
        ObjectGuid PriorityTargetGuid;
        uint32 PriorityTargetEntry = 0;
        uint32 PrioritySpellId = 0;
    };

    struct DungeonTrashActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "dungeon_trash";
        std::string Action = "follow_tank";
        Unit* Target = nullptr;
        uint32 SpellId = 0;
        DungeonTrashPackFeatures Pack;
    };

    struct BossMechanicFeatures
    {
        bool RaidEncounter = false;
        bool BossPresent = false;
        bool BossCasting = false;
        uint32 BossEntry = 0;
        uint32 CastSpellId = 0;
        int32 CastRemainingMs = 0;
        bool DangerousCast = false;
        bool MustInterrupt = false;
        bool GroundDanger = false;
        bool MoveOut = false;
        bool TankSpike = false;
        bool RaidDamage = false;
        bool AddsActive = false;
        bool StackPlaceholder = false;
        bool SpreadPlaceholder = false;
        bool InteractableObserved = false;
        bool VehicleObserved = false;
        bool TransportObserved = false;
        bool PlatformTransferObserved = false;
        uint32 AddCount = 0;
        uint32 InteractableCount = 0;
        uint32 VehicleCount = 0;
        float TankHpPct = 1.0f;
        float PartyAverageHpPct = 1.0f;
        float LowestAllyHpPct = 1.0f;
        float HealerManaPct = 1.0f;
        float DangerScore = 0.0f;
        float InterruptPriority = 0.0f;
        ObjectGuid BossGuid;
        ObjectGuid PriorityAddGuid;
        ObjectGuid InteractableGuid;
        ObjectGuid VehicleGuid;
        ObjectGuid TransportGuid;
    };

    struct BossMechanicActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "dungeon_boss";
        std::string Action = "boss_wait";
        Unit* Target = nullptr;
        uint32 SpellId = 0;
        BossMechanicFeatures Features;
    };

    struct RaidRoleAssignment
    {
        std::string Role = "dps";
        std::string RosterSlotId;
        std::string LeaseRoleSlot;
        std::string ClassSpec;
        float AverageItemLevel = 0.0f;
        uint8 SubGroup = 0;
        uint32 RaidSize = 0;
        uint32 TankCount = 0;
        uint32 HealerCount = 0;
        uint32 DpsCount = 0;
        uint32 RoleIndex = 0;
        ObjectGuid MainTankGuid;
        ObjectGuid OffTankGuid;
        ObjectGuid RaidLeaderGuid;
    };

    struct RaidPositioningAnchors
    {
        bool Active = false;
        std::string AnchorType = "leader";
        ObjectGuid AnchorGuid;
        float AnchorX = 0.0f;
        float AnchorY = 0.0f;
        float AnchorZ = 0.0f;
        float StackX = 0.0f;
        float StackY = 0.0f;
        float StackZ = 0.0f;
        float SpreadX = 0.0f;
        float SpreadY = 0.0f;
        float SpreadZ = 0.0f;
        std::string FormationFamily = "none";
        float ResolvedX = 0.0f;
        float ResolvedY = 0.0f;
        float ResolvedZ = 0.0f;
        float ArrivalToleranceYards = 0.0f;
        float DistanceToAnchor = 0.0f;
    };

    struct RaidMechanicAdapter
    {
        std::string MechanicFamily = "boss_pressure";
        std::string AssignmentType = "maintain_role";
        std::string RecommendedAction = "boss_single_target";
        // These are declarative, native-observation-backed primitives.  They
        // intentionally carry an explicit unknown/unobserved state instead
        // of manufacturing boss-specific behavior.
        std::string FormationFamily = "role_anchor";
        std::string SwapTrigger = "unobserved";
        std::string TargetControl = "boss_victim";
        std::string RotationDirective = "db_profile_declared";
        std::string HealDirective = "native_heal_profile";
        std::string SoakDirective = "unobserved";
        std::string CooldownDirective = "native_profile_declared";
        std::string BattleResDirective = "native_resurrection_only";
        std::string InteractableDirective = "unobserved";
        std::string VehicleDirective = "unobserved";
        std::string TransportDirective = "unobserved";
        std::string PlatformTransferDirective = "unobserved";
        ObjectGuid AssignedTargetGuid;
        ObjectGuid EvidenceGuid;
        uint32 TriggerSpellId = 0;
        float Priority = 0.0f;
        bool HeroicOnly = false;
        bool AssignmentObserved = false;
        bool EvidenceObserved = false;
        std::string ContractId;
        std::string ContractError;
        bool ContractResolved = false;
        std::string FormationScope = "raid";
        bool AllowAreaDamage = false;
        bool AllowMultidot = false;
        std::vector<uint32> TargetEntries;
        uint32 ControlledAoeMinimumTargets = 0;
        float KillSyncTolerancePct = 0.0f;
        float KillSyncExecutionFloorPct = 0.0f;
        std::string TankSwapTrigger;
        uint32 TankSwapAuraId = 0;
        uint32 TankSwapAuraStacks = 0;
        uint32 TankSwapIntervalMs = 0;
        uint32 TankSwapTriggerSpellId = 0;
        uint32 TankSwapAddEntry = 0;
        std::string TankSwapPhase;
        uint32 InterruptOwnerSlot = 0;
        uint32 InterruptBackupSlot = 0;
        uint32 InterruptTriggerSpellId = 0;
        uint32 InteractableEntry = 0;
        uint32 VehicleEntry = 0;
        uint32 TransportEntry = 0;
        uint32 TransferAreaTriggerId = 0;
        uint32 ExtraActionSpellId = 0;
        uint32 ExtraActionTriggerAuraId = 0;
        uint32 DispelAuraId = 0;
        uint32 DispelOwnerSlot = 0;
        uint32 DispelBackupSlot = 0;
        std::string CooldownCategory;
        uint32 CooldownOwnerSlot = 0;
        uint32 CooldownBackupSlot = 0;
        uint32 CooldownTriggerSpellId = 0;
        std::string CooldownTarget = "self";
        std::string HealerOwnership = "raid_triage";
        std::vector<uint32> HealerOwnerSlots;
        std::vector<uint32> SoakRosterSlots;
        uint32 SoakMinimumCount = 0;
        float SoakRadiusYards = 0.0f;
        uint32 SoakTriggerSpellId = 0;
        uint32 SoakTriggerAuraId = 0;
        uint32 SoakImmunitySpellId = 0;
        uint32 SoakPersonalCooldownSpellId = 0;
        std::string BattleResurrectionPolicy = "native_rotation";
        std::vector<uint32> BattleResurrectionSlots;
        std::string InteractionKind = "none";
        uint32 JumpPadEntry = 0;
        std::string MovementLink = "none";
        std::string PlatformPolicy = "ground";
        uint32 PlatformDestinationMapId = 0;
        uint32 PlatformDestinationAreaId = 0;
        float PlatformMinimumZ = 0.0f;
        float PlatformMaximumZ = 0.0f;
    };

    struct RaidGearTargetPlan
    {
        float CurrentItemLevel = 0.0f;
        float TargetItemLevel = 359.0f;
        float NeededItemLevel = 0.0f;
        std::string RecommendedActivity = "raid";
        bool ReadyForRaid = false;
        bool ReadyForHeroicRaid = false;
    };

    struct HeroicRaidProgression
    {
        bool TrackingEnabled = false;
        bool HeroicEligible = false;
        std::string Stage = "normal_raid";
        uint32 RaidAttempts = 0;
        uint32 RaidBossKills = 0;
        uint32 HeroicRaidBossKills = 0;
        uint32 Wipes = 0;
        float RolePowerScore = 0.0f;
        float TargetItemLevel = 372.0f;
    };

    struct PendingHealCast
    {
        uint64 CastId = 0;
        ObjectGuid BotGuid;
        uint32 SpellId = 0;
        ObjectGuid ChosenTargetGuid;
        uint64 StartedAtMs = 0;
        uint64 LastHealAtMs = 0;
        uint64 DeadlineMs = 0;
        uint32 ManaBefore = 0;
        uint32 AttemptedHeal = 0;
        uint32 EffectiveHeal = 0;
        uint32 AbsorbedHeal = 0;
        std::set<uint64> AffectedAllyGuids;
        uint32 AttackersBefore = 0;
        float ThreatBefore = 0.0f;
        std::string CandidateMaskJson;
        std::string ChosenActionJson;
        bool SpellFinished = false;
        uint64 FinishedAtMs = 0;
        uint32 ManaAfterCast = 0;
        uint32 AttackersAfterCast = 0;
        float ThreatAfterCast = 0.0f;
    };

    enum class CombatLogPerspective : uint8
    {
        DamageDone = 0,
        DamageTaken = 1,
        HealingDone = 2,
        HealingReceived = 3
    };

    struct CombatLogAbilityKey
    {
        uint64 RouteGeneration = 0;
        CombatLogPerspective Perspective = CombatLogPerspective::DamageDone;
        uint32 ActorGuid = 0;
        uint32 SourceEntry = 0;
        uint32 SpellId = 0;
        uint32 TargetEntry = 0;
        uint32 EffectType = 0;

        bool operator<(CombatLogAbilityKey const& other) const
        {
            return std::tie(RouteGeneration, Perspective, ActorGuid, SourceEntry, SpellId, TargetEntry, EffectType)
                < std::tie(other.RouteGeneration, other.Perspective, other.ActorGuid, other.SourceEntry,
                    other.SpellId, other.TargetEntry, other.EffectType);
        }
    };

    struct CombatLogAbilityAggregate
    {
        std::string RouteNodeId;
        std::string RouteLabel;
        std::string ActorName;
        std::string ActorRole;
        uint8 ActorClassId = 0;
        std::string SourceName;
        std::string SpellName;
        std::string TargetName;
        uint64 FirstAtMs = 0;
        uint64 LastAtMs = 0;
        uint64 EventCount = 0;
        uint64 Amount = 0;
        uint64 RawAmount = 0;
        uint64 AbsorbedAmount = 0;
        uint64 MovingEvents = 0;
        double DistanceTotal = 0.0;
        float MinDistance = -1.0f;
        float MaxDistance = 0.0f;
        bool SourceIsPet = false;
    };

    struct CombatLogEvent
    {
        uint64 TimestampMs = 0;
        uint64 RouteGeneration = 0;
        std::string RouteNodeId;
        std::string Kind;
        uint32 ActorGuid = 0;
        std::string ActorName;
        std::string ActorRole;
        uint8 ActorClassId = 0;
        uint32 SourceGuid = 0;
        uint32 SourceEntry = 0;
        std::string SourceName;
        uint32 TargetGuid = 0;
        uint32 TargetEntry = 0;
        std::string TargetName;
        uint32 SpellId = 0;
        std::string SpellName;
        uint32 EffectType = 0;
        uint32 SchoolMask = 0;
        uint32 Amount = 0;
        uint32 RawAmount = 0;
        uint32 AbsorbedAmount = 0;
        float SourceX = 0.0f;
        float SourceY = 0.0f;
        float SourceZ = 0.0f;
        float TargetX = 0.0f;
        float TargetY = 0.0f;
        float TargetZ = 0.0f;
        float Distance = 0.0f;
        bool SourceMoving = false;
        bool SourceIsPet = false;
    };

    struct SemanticOutcomeStats
    {
        bool Known = false;
        uint32 Samples = 0;
        uint32 Successes = 0;
        uint32 Failures = 0;
        uint32 Deaths = 0;
        float AvgReward = 0.0f;
        float AvgPowerDelta = 0.0f;
        float DangerScore = 0.0f;
        float ProgressionValue = 0.0f;
    };

    struct ReplayRecord
    {
        bool Loaded = false;
        uint64 Id = 0;
        uint64 ExperimentId = 0;
        uint64 RunId = 0;
        uint32 BotGuid = 0;
        std::string ReplayType;
        uint32 MapId = 0;
        uint32 ZoneId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float O = 0.0f;
        std::string BotSnapshotJson;
        std::string WorldSnapshotJson;
        std::string PartySnapshotJson;
        std::string RawStateJson;
        std::string SemanticStateJson;
        std::string ChosenActionJson;
        std::string FailureJson;
    };

    struct ReplayExecutionResult
    {
        bool Ok = false;
        bool Success = false;
        uint64 ReplayId = 0;
        uint64 RunId = 0;
        std::string BrainVersion;
        std::string FailureReason;
        uint32 Decisions = 0;
        uint32 Failures = 0;
        uint32 Deaths = 0;
        uint32 Kills = 0;
        uint32 StuckEvents = 0;
        float FinalPower = 0.0f;
        std::string FirstAction;
        std::string ReplayType;
    };

    struct SpawnPlacement
    {
        bool Valid = false;
        uint32 MapId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float O = 0.0f;
        std::string Source;
        bool RaceStartFallbackUsed = false;
    };

    struct BotDeathRecoveryPolicy
    {
        std::vector<std::string> Modes;
        uint32 MaxDeathsBeforeFallback = 3;
    };

    struct DeathRecoveryResult
    {
        bool Recovered = false;
        bool InProgress = false;
        bool UsedFallback = false;
        bool RepeatedDeath = false;
        std::string Mode;
        std::string Result = "failed";
    };

    struct PolicyModelTrace
    {
        bool Enabled = false;
        float ModelScore = 0.0f;
        uint32 ModelRank = 0;
        uint32 FeaturesHash = 0;
        std::string Json = "{}";
    };

#endif

