#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_CALIBRATION_METRICS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_CALIBRATION_METRICS_H

// This fragment is included inside BotWorldPopulationMgr's private section so
// calibration metrics retain the manager's private nested-type ownership and
// declaration order.
    struct CalibrationMetrics
    {
        struct NativeConsumableReceipt
        {
            uint32 ItemId = 0;
            uint32 SpellId = 0;
            uint32 RequiredUses = 1;
            uint32 SubmissionCount = 0;
            uint32 SuccessfulUseCount = 0;
            uint32 PreUseItemCount = 0;
            uint32 PostUseItemCount = 0;
            uint64 SubmittedAtMs = 0;
            uint64 FinishedAtMs = 0;
            uint64 NextRetryAtMs = 0;
            // Food's native item spell can finish by starting the ordinary
            // eating state before the Well Fed aura is applied. Keep that
            // request pending until the aura is observed; a timeout is a
            // bounded failed attempt, never an implicit success.
            uint64 NativeUseAuraDeadlineAtMs = 0;
            uint64 NativeUseAuraObservedAtMs = 0;
            uint64 NativeUseAuraTimedOutAtMs = 0;
            ObjectGuid SubmittedItemGuid;
            ObjectGuid FinishedItemGuid;
            bool NativeUseFinishedSuccessfully = false;
            bool NativeUseAwaitingAura = false;
            std::string Phase;
        };

        struct ScoredOtherItemUse
        {
            uint32 SpellId = 0;
            uint32 ItemEntry = 0;
            uint32 UseCount = 0;
        };

        struct EffectiveStatVector
        {
            struct AuraContribution
            {
                uint16 AuraType = 0;
                uint32 SpellId = 0;
                uint8 EffectIndex = 0;
                int32 Amount = 0;
                int32 MiscValue = 0;
                int32 MiscValueB = 0;
                uint64 CasterGuid = 0;
            };
            struct PrimaryStatLedger
            {
                uint8 StatIndex = 0;
                float CreateStat = 0.0f;
                float BaseValue = 0.0f;
                float BasePct = 1.0f;
                float TotalValue = 0.0f;
                float TotalPct = 1.0f;
                float RecomputedTotal = 0.0f;
                float PublishedStat = 0.0f;
                std::vector<AuraContribution> AuraContributions;
            };
            bool Observed = false;
            uint64 ObservedAtMs = 0;
            uint32 Guid = 0;
            uint32 Entry = 0;
            float Strength = 0.0f;
            float Agility = 0.0f;
            float Stamina = 0.0f;
            float Intellect = 0.0f;
            float Spirit = 0.0f;
            float AttackPower = 0.0f;
            float RangedAttackPower = 0.0f;
            int32 SpellPower = 0;
            int32 BonusDamage = 0;
            uint32 Armor = 0;
            uint64 Health = 0;
            uint32 Mana = 0;
            uint32 HitRating = 0;
            uint32 CritRating = 0;
            uint32 HasteRating = 0;
            uint32 ExpertiseRating = 0;
            uint32 MasteryRating = 0;
            float PhysicalHitPct = 0.0f;
            float SpellHitPct = 0.0f;
            float MeleeCritPct = 0.0f;
            float RangedCritPct = 0.0f;
            float SpellCritPct = 0.0f;
            float MasteryPoints = 0.0f;
            float MeleeSpeedMultiplier = 1.0f;
            float RangedSpeedMultiplier = 1.0f;
            float SpellSpeedMultiplier = 1.0f;
            std::array<PrimaryStatLedger, 5> PrimaryStatLedgerEntries;
        };
        struct InitialPowerObservation
        {
            uint8 PowerType = 0;
            uint32 ExpectedNativeValue = 0;
            uint32 ExpectedDisplayValue = 0;
            uint32 ObservedNativeValue = 0;
            uint32 ObservedDisplayValue = 0;
            uint32 ObservedMaximumNativeValue = 0;
            bool ExpectedMaximum = false;
            bool MatchesContract = false;
            uint32 UnitGuid = 0;
            std::string UnitKind;
            std::string PowerName;
        };
        struct TargetHealthPhaseObservation
        {
            uint32 SampleCount = 0;
            uint64 FirstObservedElapsedMs = 0;
            uint64 LastObservedElapsedMs = 0;
            uint64 MinimumObservedHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumObservedHealth = 0;
            uint64 MinimumObservedMaxHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumObservedMaxHealth = 0;
            uint32 DamageEventSampleCount = 0;
            uint64 FirstDamageEventElapsedMs = 0;
            uint64 LastDamageEventElapsedMs = 0;
            uint64 MinimumPreDamageHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumPreDamageHealth = 0;
            uint64 MinimumProjectedPostDamageHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumProjectedPostDamageHealth = 0;
            uint64 MinimumDamageEventMaxHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumDamageEventMaxHealth = 0;
            uint32 MaximumDamageEvent = 0;
        };
        struct DecisionTimelineEntry
        {
            uint64 ElapsedMs = 0;
            uint32 SpellId = 0;
            std::string Result;
            uint64 Health = 0;
            uint64 MaxHealth = 0;
            uint32 Mana = 0;
            uint32 MaxMana = 0;
            uint32 CurrentGenericSpellId = 0;
            uint32 CurrentChanneledSpellId = 0;
            uint64 PetHealth = 0;
            uint64 PetMaxHealth = 0;
            uint32 PetVictimGuid = 0;
            uint32 PetCurrentGenericSpellId = 0;
            uint32 PetCurrentChanneledSpellId = 0;
            uint32 PetCurrentAutorepeatSpellId = 0;
            uint8 PetCommandState = 0;
            bool PetAlive = false;
            bool PetAttacking = false;
            bool PetCommandAttack = false;
            float TargetDistance = 0.0f;
            bool Alive = false;
        };
        struct OffTargetDamageEvent
        {
            struct PeriodicHealthAuraCandidate
            {
                uint32 SpellId = 0;
                uint32 HolderGuid = 0;
                uint32 CasterGuid = 0;
                uint8 EffectIndex = 0;
                uint16 AuraType = 0;
            };
            uint64 ElapsedMs = 0;
            uint32 AttackerGuid = 0;
            uint32 VictimGuid = 0;
            uint32 VictimEntry = 0;
            uint32 SpellId = 0;
            uint32 CurrentGenericSpellId = 0;
            uint32 CurrentChanneledSpellId = 0;
            uint32 Damage = 0;
            uint8 VictimTypeId = 0;
            bool VictimIsOwner = false;
            std::vector<PeriodicHealthAuraCandidate> PeriodicHealthAuraCandidates;
        };
        struct PrimaryPetShadowBiteEvent
        {
            uint64 ElapsedMs = 0;
            uint32 MeasuredDamage = 0;
            uint32 UnmitigatedDamage = 0;
            int32 PetSpellPower = 0;
            float PetSpellCritPct = 0.0f;
            std::vector<uint32> OwnerCastWarlockPeriodicDamageAuraSpellIds;
        };
        uint64 WindowStartedMs = 0;
        uint64 WindowEndedMs = 0;
        uint64 Damage = 0;
        uint64 PetDamage = 0;
        uint64 PrimaryTargetDamage = 0;
        uint64 OffTargetDamage = 0;
        uint64 AttemptedHealing = 0;
        uint64 EffectiveHealing = 0;
        uint64 AbsorbedHealing = 0;
        uint32 Attempts = 0;
        uint32 Successes = 0;
        uint32 TickCount = 0;
        uint64 WarmupUpdateOrdinal = 0;
        uint64 LastPreScoreConsumableFinishedUpdateOrdinal = 0;
        uint32 RequiredPetReadyTicks = 0;
        uint32 PetSetupObservationSampleCount = 0;
        uint32 PetSetupReadySampleCount = 0;
        uint64 FirstPetSetupObservedAtMs = 0;
        uint64 LastPetSetupObservedAtMs = 0;
        uint64 MaximumPetSetupObservationGapMs = 0;
        uint32 FirstPetSetupObservedGuid = 0;
        uint32 LastPetSetupObservedGuid = 0;
        uint32 PetSetupGuidMismatchSampleCount = 0;
        uint32 PetSetupIdentityMismatchSampleCount = 0;
        uint32 ActiveTicks = 0;
        uint32 MovementRangeLossTicks = 0;
        uint32 ResourceCappedTicks = 0;
        uint32 ResourceStarvedTicks = 0;
        uint32 IllegalActionCount = 0;
        uint32 ShadowOrbPowerActiveTicks = 0;
        uint32 ShadowOrbActiveTicks = 0;
        uint32 EmpoweredShadowActiveTicks = 0;
        uint8 MaximumShadowOrbStacks = 0;
        uint32 AfflictionModifierObservationTicks = 0;
        uint32 AfflictionShadowMasteryActiveTicks = 0;
        uint32 AfflictionPotentAfflictionsActiveTicks = 0;
        uint32 AfflictionHauntDebuffActiveTicks = 0;
        uint32 AfflictionShadowEmbraceCasterActiveTicks = 0;
        uint8 AfflictionShadowEmbraceCasterEffectMask = 0;
        uint8 AfflictionMaximumShadowEmbraceCasterStacks = 0;
        uint32 AfflictionShadowEmbraceActiveTicks = 0;
        uint8 AfflictionMaximumShadowEmbraceStacks = 0;
        uint32 AfflictionHauntAffectsCorruptionTicks = 0;
        uint32 AfflictionShadowEmbraceAffectsCorruptionTicks = 0;
        int32 AfflictionMaximumHauntDamageModifierPct = 0;
        int32 AfflictionMaximumShadowEmbraceDamageModifierPct = 0;
        uint32 AfflictionMinimumCorruptionTakenMultiplierPpm = 0;
        uint32 AfflictionMaximumCorruptionTakenMultiplierPpm = 0;
        uint32 StanceFormActiveTicks = 0;
        uint32 MitigationCoveredTicks = 0;
        uint32 ThreatSampleCount = 0;
        uint32 AllHostilesRetainedSamples = 0;
        uint32 SnapThreatChecks = 0;
        uint32 SnapThreatSuccesses = 0;
        uint32 AddThreatChecks = 0;
        uint32 AddThreatSuccesses = 0;
        uint32 ThreatAuraActiveTicks = 0;
        uint32 HealerExposureTicks = 0;
        uint32 InterruptChecks = 0;
        uint32 InterruptSuccesses = 0;
        uint32 DefensiveActionCount = 0;
        uint32 ScheduledDamageEvents = 0;
        uint32 DeliveredDamageEvents = 0;
        uint32 DispelAttempts = 0;
        uint32 DispelSuccesses = 0;
        uint32 CooldownAttempts = 0;
        uint32 CooldownSuccesses = 0;
        uint32 HealSelectionAttempts = 0;
        uint32 HealSelectionSuccesses = 0;
        uint32 DemandTicks = 0;
        uint32 IdleUnderDemandTicks = 0;
        uint32 TargetCount = 0;
        uint32 DeathCount = 0;
        uint64 ControlledDamage = 0;
        uint64 MaximumControlledDamage = 0;
        float MaximumControlledDamageRatio = 0.0f;
        float ThreatBaseline = -1.0f;
        float ThreatCurrent = 0.0f;
        float MinimumHealthRatio = 1.0f;
        bool ReferenceBuffsReady = false;
        bool ReferenceReplenishmentObserved = false;
        bool ReferenceTargetDebuffsReady = false;
        bool ReferenceHeroismWindowObserved = false;
        bool BalanceMushroomsPreplanted = false;
        uint8 BalanceMushroomPreplantCount = 0;
        bool DeathRecorded = false;
        bool InitialResourcesApplied = false;
        bool InitialResourcesMatchContract = false;
        uint64 InitialResourcesObservedAtMs = 0;
        std::string InitialResourceSourceContract;
        std::vector<InitialPowerObservation> InitialPowerObservations;
        bool InitialRunesRequired = false;
        uint8 InitialExpectedRuneReadyMask = 0;
        uint8 InitialObservedRuneReadyMask = 0;
        bool InitialComboPointsRequired = false;
        uint8 InitialExpectedComboPoints = 0;
        uint8 InitialObservedComboPoints = 0;
        bool InitialNeutralEclipseRequired = false;
        bool InitialNeutralEclipseObserved = false;
        bool InitialPetResourceRequired = false;
        bool InitialPetResourceObserved = false;
        EffectiveStatVector ScoringStartPlayerStats;
        EffectiveStatVector ScoringStartPetStats;
        bool PreScorePersistentSetupReady = false;
        bool PreScoreReferenceBuffsReady = false;
        bool PreScoreReferenceTargetDebuffsReady = false;
        bool PreScoreHeroismReady = false;
        bool PreScoreNoActiveCast = false;
        bool PreScoreNoCombat = false;
        bool PreScoreGlobalCooldownClear = false;
        bool PreScoreCooldownResetApplied = false;
        bool WarmupProfileActionsSuppressed = false;
        bool PreScoreTemporalExternalsAbsent = false;
        bool PreScoreExternalBleedAbsent = false;
        uint64 PreScoreStateObservedAtMs = 0;
        uint32 ExternalWindowSampleCount = 0;
        uint64 FirstExternalWindowObservedAtMs = 0;
        uint64 LastExternalWindowObservedAtMs = 0;
        uint64 MaximumExternalWindowObservationGapMs = 0;
        uint32 HeroismExpectedActiveSamples = 0;
        uint32 HeroismObservedActiveSamples = 0;
        uint32 HeroismMismatchSamples = 0;
        uint32 PowerInfusionExpectedActiveSamples = 0;
        uint32 PowerInfusionObservedActiveSamples = 0;
        uint32 PowerInfusionMismatchSamples = 0;
        uint32 UnexpectedDarkIntentBaseSamples = 0;
        uint32 UnexpectedDarkIntentProcSamples = 0;
        uint32 UnexpectedSynapseSpringsSamples = 0;
        uint32 ReferenceConditionSampleCount = 0;
        uint64 FirstReferenceConditionObservedAtMs = 0;
        uint64 LastReferenceConditionObservedAtMs = 0;
        uint64 MaximumReferenceConditionObservationGapMs = 0;
        uint32 PreScoreLastPotionItemId = 0;
        uint32 LastPotionIdNonzeroSampleCount = 0;
        uint32 ScoredPotionUseCount = 0;
        uint32 ScoredTinkerOrOtherItemUseCount = 0;
        uint32 ScoredOtherItemUseCount = 0;
        std::array<ScoredOtherItemUse, 8> ScoredOtherItemUses;
        uint32 ScoredRacialUseCount = 0;
        uint32 ScoredTinkerSpellUseCount = 0;
        uint32 UnexpectedDynamicAuraActiveSamples = 0;
        uint32 UnexpectedExternalBleedActiveSamples = 0;
        uint32 UnexpectedSelfProvidedPlayerAuraActiveSamples = 0;
        uint32 UnexpectedSelfProvidedTargetAuraActiveSamples = 0;
        NativeConsumableReceipt FlaskConsumable;
        NativeConsumableReceipt FoodConsumable;
        NativeConsumableReceipt PrepotConsumable;
        NativeConsumableReceipt CombatPotionConsumable;
        bool PreScoreCooldownResetComplete = false;
        std::map<uint32, uint32> ReferencePlayerAuraActiveSamples;
        std::map<uint32, uint32> ReferencePlayerAuraInactiveSamples;
        std::map<uint32, uint32> ReferenceTargetAuraActiveSamples;
        std::map<uint32, uint32> ReferenceTargetAuraInactiveSamples;
        std::map<uint32, uint32> ReferenceTargetAuraOwnerMatchSamples;
        std::map<uint32, uint32> ReferenceTargetAuraOwnerMismatchSamples;
        uint32 ReferenceSunderMatchingStackSamples = 0;
        uint32 ReferenceSunderMismatchStackSamples = 0;
        uint8 ReferenceSunderMinimumObservedStacks =
            std::numeric_limits<uint8>::max();
        uint8 ReferenceSunderMaximumObservedStacks = 0;
        std::string InitialGearManifestSha256;
        std::string LastObservedGearManifestSha256;
        uint32 GearIdentitySampleCount = 0;
        uint32 GearIdentityMismatchSampleCount = 0;
        uint64 FirstGearIdentityObservedAtMs = 0;
        uint64 LastGearIdentityObservedAtMs = 0;
        uint64 MaximumGearIdentityObservationGapMs = 0;
        std::map<uint32, uint64> SpellDamage;
        std::map<uint32, uint32> SpellDamageEvents;
        // The owner's primary pet damage is kept separate from the owner's
        // spell totals. This intentionally excludes other controlled units
        // such as guardians, which remain in the aggregate PetDamage value.
        std::map<uint32, uint64> PrimaryPetSpellDamage;
        std::map<uint32, uint32> PrimaryPetSpellDamageEvents;
        std::map<uint32, uint32> ActionAttempts;
        std::map<uint32, uint32> HealTargetCounts;
        std::map<uint32, uint64> LastDamageMsByTarget;
        std::map<uint32, uint64> LastControlledDamageMsByTarget;
        std::vector<uint32> HealResponseLatenciesMs;
        std::set<std::string> ActionGroups;
        std::set<std::string> ExpectedActionGroups;
        std::set<std::string> ScheduledDamagePhases;
        std::set<std::string> DeliveredDamagePhases;
        std::map<std::string, uint32> ResultCounts;
        // Bounded, observation-only timeline used by the rotation review tool
        // to distinguish selection, movement, native submission, resource
        // state, and death. It never participates in arbitration or scoring.
        std::vector<DecisionTimelineEntry> DecisionTimeline;
        // Attribute every non-primary damage event instead of exposing only an
        // unauditable aggregate collateral counter.
        std::vector<OffTargetDamageEvent> OffTargetDamageEvents;
        // Bounded, observation-only landed-event evidence for the primary pet's
        // Shadow Bite. It is captured after native damage has been resolved and
        // never participates in gameplay or scoring.
        std::vector<PrimaryPetShadowBiteEvent> PrimaryPetShadowBiteEvents;
        // Raw server observations for the isolated single-target fixture's
        // five WoWSims execute-threshold bands. Evidence reconstructs the
        // schedule from these integers; it does not trust an aggregate flag.
        std::array<TargetHealthPhaseObservation, 5> TargetHealthPhaseObservations;
    };

#endif
