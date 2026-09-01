#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPersonalParasiteEscapeDiagnostics.h"

#include <sstream>

namespace BotEncounter
{
namespace
{
std::string JsonEscape(std::string const& value)
{
    std::ostringstream escaped;
    for (char character : value)
    {
        switch (character)
        {
            case '\\': escaped << "\\\\"; break;
            case '"': escaped << "\\\""; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default: escaped << character; break;
        }
    }
    return escaped.str();
}

void AppendObservedLifecycle(std::ostringstream& json, uint32 mask)
{
    bool first = true;
    for (uint32 raw = uint32(
            MagmawPersonalParasiteEscapeLifecycle::TaskCreated);
        raw <= uint32(MagmawPersonalParasiteEscapeLifecycle::Failed); ++raw)
    {
        if (!(mask & (uint32{1} << raw)))
            continue;
        if (!first)
            json << ',';
        first = false;
        json << '"' << ToString(
            MagmawPersonalParasiteEscapeLifecycle(raw)) << '"';
    }
}
}

std::string BuildMagmawPersonalParasiteEscapeDiagnosticsJson(
    MagmawPersonalParasiteEscapeTask const& task,
    MagmawParasiteWaveTask const* sharedWave)
{
    MagmawParasiteWaveTask const& wave = sharedWave
        ? *sharedWave : task.LocalWave;
    auto const& diagnostics = task.Diagnostics;
    std::string candidateKey = diagnostics.CandidateKey;
    if (candidateKey.empty() && task.CandidateGeneration)
    {
        BotNativeAction::CandidateIdentity identity;
        identity.ScopeKey = task.ScopeKey;
        identity.Strategy = "adaptive_magmaw";
        identity.Mechanic = "parasite_contact_evade";
        identity.Actor = task.ActorGuid;
        identity.EventGeneration = task.CandidateGeneration;
        candidateKey = identity.Key();
    }
    std::ostringstream json;
    json << "{\"parent_wave\":{\"scope_key\":\""
         << JsonEscape(wave.ScopeKey) << "\",\"generation\":"
         << wave.Generation << ",\"generation_authoritative\":"
         << (wave.GenerationAuthoritative ? "true" : "false")
         << ",\"active\":" << (wave.Active ? "true" : "false")
         << ",\"awaiting_authoritative_facts\":"
         << (wave.AwaitingAuthoritativeFacts ? "true" : "false")
         << ",\"created_at_ms\":" << wave.CreatedAtMs
         << ",\"last_observed_at_ms\":" << wave.LastObservedAtMs << "}"
         << ",\"child\":{\"actor_guid\":"
         << task.ActorGuid.GetCounter()
         << ",\"wave_generation\":" << task.WaveGeneration
         << ",\"task_generation\":" << task.TaskGeneration
         << ",\"candidate_generation\":" << task.CandidateGeneration
         << ",\"candidate_key\":\""
         << JsonEscape(candidateKey) << "\""
         << ",\"lifecycle\":\"" << ToString(diagnostics.Lifecycle)
         << "\",\"observed_lifecycle_mask\":"
         << diagnostics.ObservedLifecycleMask
         << ",\"observed_lifecycle\":[";
    AppendObservedLifecycle(json, diagnostics.ObservedLifecycleMask);
    json << "]"
         << ",\"authority_gap_mask\":" << diagnostics.AuthorityGapMask
         << ",\"failure\":\"" << ToString(task.Failure) << "\""
         << ",\"created_at_ms\":" << diagnostics.CreatedAtMs
         << ",\"awaiting_facts_at_ms\":"
         << diagnostics.AwaitingFactsAtMs
         << ",\"candidate_built_at_ms\":"
         << diagnostics.CandidateBuiltAtMs
         << ",\"submitted_at_ms\":" << diagnostics.SubmittedAtMs
         << ",\"native_progress_at_ms\":"
         << diagnostics.NativeProgressAtMs
         << ",\"terminal_at_ms\":" << diagnostics.TerminalAtMs
         << ",\"native_outcome_count\":"
         << diagnostics.NativeOutcomeCount
         << ",\"last_native_reason\":\""
         << JsonEscape(diagnostics.LastNativeReason) << "\"}}";
    return json.str();
}
}
