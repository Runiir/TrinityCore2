#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_DIAGNOSTICS_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_DIAGNOSTICS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneIntent.h"

#include <string>

namespace BotEncounter
{
struct MagmawTransferLaneActorIntentDiagnostics
{
    ObjectGuid Actor;
    MagmawTransferLaneIntentComparison Comparison;
    MagmawTransferLaneIntentEpisodeAccumulator EpisodeAccumulator;
};

std::string BuildMagmawTransferLaneIntentComparisonDiagnosticsJson(
    MagmawTransferLaneIntentComparison const& comparison);
std::string BuildMagmawTransferLaneIntentEpisodeSummaryDiagnosticsJson(
    MagmawTransferLaneIntentEpisodeSummary const& summary);
std::string BuildMagmawTransferLaneIntentEpisodeAccumulatorDiagnosticsJson(
    MagmawTransferLaneIntentEpisodeAccumulator const& accumulator);
std::string BuildMagmawTransferLaneTaskDiagnosticsJson(
    MagmawTransferLaneTask const& task);
std::string BuildMagmawTransferLaneTaskCollectionDiagnosticsJson(
    std::vector<MagmawTransferLaneTask> const& tasks);
std::string BuildMagmawRetiredTransferLaneTaskDiagnosticsJson(
    MagmawRetiredTransferLaneTask const& retired);
std::string BuildMagmawRetiredTransferLaneTaskCollectionDiagnosticsJson(
    std::vector<MagmawRetiredTransferLaneTask> const& retired);
std::string BuildMagmawTransferLaneTaskShadowDiagnosticsJson(
    MagmawTransferLaneTaskShadow const* shadow,
    std::vector<MagmawTransferLaneActorIntentDiagnostics> const& actors);
}

#endif
