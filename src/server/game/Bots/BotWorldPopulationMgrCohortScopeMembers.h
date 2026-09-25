// Included inside the private section of class BotWorldPopulationMgr, after
// BotWorldPopulationMgrRuntimeContracts.h. Cohort registry, thread-local
// scope and GUID leases. Cohort() aborts without an explicit scope: callers
// bind one through ScopeCohort/ScopeCohortById (commands, update loop) or
// ScopeCallbackCohort (native hooks, which drop unresolved events).

    BotWorldPopulationMgr();
    // Starts the scoped cohort. Private so no caller outside the manager can
    // start autonomy without naming a cohort: use StartAutonomyForCohort.
    bool StartAutonomy(BotWorldExperimentConfig const* overrideConfig = nullptr);
    CohortRuntime& Cohort();
    CohortRuntime const& Cohort() const;
    PartyRuntime& Party();
    PartyRuntime const& Party() const;
    CohortRuntime* FindCohort(std::string const& cohortId);
    CohortRuntime const* FindCohort(std::string const& cohortId) const;
    uint32 ActiveCohortCount() const;
    CohortScope ScopeCohort(CohortRuntime* runtime);
    CohortScope ScopeCallbackCohort(Unit* first, Unit* second = nullptr);
    CohortRuntime* ResolveCallbackCohort(Unit* first, Unit* second = nullptr);
    BotWorldCohortScope::RuntimeIdentity RuntimeIdentityFor(
        CohortRuntime const& runtime) const;
    uint32 MapWorkerThreadCount() const;
    void UpdateCohort(uint32 diff);
    void ShutdownCohort();
    // Drops per-cohort encounter ledgers kept outside CohortRuntime (for
    // example the Magmaw baiter rotation) once the cohort stops.
    void ReleaseCohortEncounterState();
    bool ClaimBotGuid(uint32 guid, std::string const& roleSlot);
    bool ReleaseBotGuid(uint32 guid);
    void ReleaseCohortLeases();
    bool LeaseOwnedByCurrentCohort(uint32 guid) const;
    bool LeaseOwnedByCurrentCohort(uint32 guid, std::string const& roleSlot) const;
    bool EligibleForDiagnosticCleanup(uint32 guid) const;
    std::string UnknownCohortJson(char const* action, std::string const& cohortId) const;

    uint64 _serverEpoch = 0;
    std::map<std::string, std::unique_ptr<CohortRuntime>> _cohorts;
    static thread_local CohortRuntime* _scopedCohort;
    mutable std::mutex _leaseMutex;
    std::map<uint32, BotGuidLease> _guidLeases;
