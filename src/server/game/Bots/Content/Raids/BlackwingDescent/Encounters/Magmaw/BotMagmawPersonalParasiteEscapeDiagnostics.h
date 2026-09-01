#ifndef TRINITY_BOT_MAGMAW_PERSONAL_PARASITE_ESCAPE_DIAGNOSTICS_H
#define TRINITY_BOT_MAGMAW_PERSONAL_PARASITE_ESCAPE_DIAGNOSTICS_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPersonalParasiteEscapeTask.h"

#include <string>

namespace BotEncounter
{
std::string BuildMagmawPersonalParasiteEscapeDiagnosticsJson(
    MagmawPersonalParasiteEscapeTask const& task,
    MagmawParasiteWaveTask const* sharedWave = nullptr);
}

#endif
