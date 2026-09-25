// Included inside the public section of class BotWorldPopulationMgr
// (BotWorldPopulationMgr.h). Cohort-qualified entry points: every command,
// hook or harness path names the cohort it acts on. Cohort state is reached
// only through an explicit scope (CohortScope); there is no process-wide
// selected cohort to fall back to.

    // Boss shards of one worldserver (docs/bot_raids/full_raid_parallel_shards.md).
    // Concurrent admission still requires serialized map updates
    // (MapUpdate.Threads <= 1, BotWorldCohortScope::AllowsConcurrentAdmission).
    static constexpr uint32 MaxActiveCohorts = 6;
    // Legacy unqualified commands (.botexp, `.botauto status` with a single
    // registered cohort, BotWorld.AutoStart) act on this cohort explicitly.
    static constexpr char const* DefaultCohortId = "default";

    // RAII binding of the calling thread to one cohort; defined after the
    // class. An unknown cohort yields an empty (false) scope.
    class CohortScope;
    CohortScope ScopeCohortById(std::string const& cohortId) const;

    std::string CreateCohort(std::string const& cohortId);
    bool HasCohort(std::string const& cohortId) const;
    size_t GetCohortCount() const;
    uint32 GetActiveCohortCount() const;
    // A boss shard is running: an active cohort that is neither the default
    // cohort nor a human play session (both keep their legacy commands).
    bool HasActiveShardCohort() const;
    std::string ResolveGlobalCohortId() const;
    std::string GetCohortRegistryJson() const;
    std::string GetCohortIsolationContractJson();
    bool StartAutonomyForCohort(std::string const& cohortId, BotWorldExperimentConfig const* overrideConfig = nullptr);
    std::string StopAutonomyForCohort(std::string const& cohortId);
    std::string SelectRuntimeProfileForCohort(std::string const& cohortId, std::string const& name);
    std::string PrepareValidationProfileForCohort(std::string const& cohortId, std::string const& name,
        std::string const& poolTag = {}, std::vector<std::string> const& classSpecs = {});
    std::string GetStatusJsonForCohort(std::string const& cohortId) const;
    std::string RequestNativeRaidReadyCheckForCohort(std::string const& cohortId);
    std::string GetBotDiagnosisJsonForCohort(std::string const& cohortId, std::string const& selector);
    std::string GetBotTraceJsonForCohort(std::string const& cohortId, std::string const& selector, uint32 limit, bool delta = false) const;
    std::string ApplyTraceTransportTestPressureForCohort(std::string const& cohortId, uint32 requestedCount);
    std::string ArmChainwielderOwnerCheckpointForCohort(
        std::string const& cohortId, uint32 actorGuid,
        std::string const& sealSha256,
        std::string const& sourceCommit);
    std::string StartAutonomyHeldForCohort(
        std::string const& cohortId, uint32 actorGuid,
        std::string const& fixtureId,
        std::string const& sealSha256,
        std::string const& sourceCommit);
    std::string ReleaseControllerRouteHoldForCohort(
        std::string const& cohortId, uint32 actorGuid,
        std::string const& sealSha256,
        std::string const& sourceCommit);
    std::string GetChainwielderOwnerCheckpointJsonForCohort(
        std::string const& cohortId) const;
    std::string ArmNativePathCheckpointForCohort(
        std::string const& cohortId, uint32 actorGuid,
        std::string const& caseId, std::string const& sealSha256,
        std::string const& sourceCommit);
    std::string GetNativePathCheckpointJsonForCohort(
        std::string const& cohortId) const;
    std::string ArmProfileCombatRangeCheckpointForCohort(
        std::string const& cohortId, uint32 actorGuid, uint64 targetGuid,
        std::string const& caseId, std::string const& sealSha256,
        std::string const& sourceCommit);
    std::string GetProfileCombatRangeCheckpointJsonForCohort(
        std::string const& cohortId) const;
    std::string ArmMagmawTransferLaneCheckpointForCohort(
        std::string const& cohortId, uint32 actorGuid,
        std::string const& caseId, std::string const& sealSha256,
        std::string const& sourceCommit);
    std::string GetMagmawTransferLaneCheckpointJsonForCohort(
        std::string const& cohortId) const;
    std::string GetCombatLogJsonForCohort(std::string const& cohortId) const;
    std::string GetCombatLogDeltaJsonForCohort(std::string const& cohortId,
        uint64 cursor, uint32 limit) const;
    std::string StartCombatCalibrationForCohort(std::string const& cohortId, std::string const& mode = "single_target_300", std::string const& targetSpec = "", uint32 seed = 1);
    std::string StopCombatCalibrationForCohort(std::string const& cohortId);
    std::string GetCombatCalibrationJsonForCohort(std::string const& cohortId, bool includeBotDetails = true) const;
