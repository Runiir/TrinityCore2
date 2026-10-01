#ifndef TRINITY_BOT_RAID_HEALER_MANA_STATUS_H
#define TRINITY_BOT_RAID_HEALER_MANA_STATUS_H

#include "Define.h"

#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

// The canonical raid healers' current mana in the heartbeat status
// (status.raid_runtime.healer_mana), asked for by the round 4 Chimaeron and
// Magmaw packets to test the healer out-of-mana reading of the r03 wipes
// (Chimaeron: the Discipline priest about 70% dry at the third Massacre).
// Additive: the field is written only for a canonical-composition raid cohort
// (BotCanonicalRaidScope.h) with at least one healer in its roster, so every
// other status payload (Stonecore, Phase 8 calibration, legacy BWD shards,
// a roster with no healer) stays byte-identical.
namespace BotRaidHealerManaStatus
{
struct Row
{
    uint32 Guid = 0;
    std::string Name;
    std::string ClassSpec;
    bool Present = false;
    bool Alive = false;
    uint32 Mana = 0;
    uint32 MaxMana = 0;
};

inline std::string Escape(std::string const& text)
{
    std::string escaped;
    escaped.reserve(text.size());
    for (char character : text)
    {
        if (character == '"' || character == '\\')
            escaped += '\\';
        if (static_cast<unsigned char>(character) >= 0x20)
            escaped += character;
    }
    return escaped;
}

// "" for no rows; otherwise ',"healer_mana":{...}' to append to an object.
inline std::string JsonField(std::vector<Row> const& rows)
{
    if (rows.empty())
        return {};
    std::ostringstream json;
    json << ",\"healer_mana\":{\"schema\":\"raid_healer_mana_v1\",\"members\":[";
    bool first = true;
    for (Row const& row : rows)
    {
        if (!first)
            json << ',';
        first = false;
        double const pct = row.MaxMana ? 100.0 * double(row.Mana) / double(row.MaxMana) : 0.0;
        json << "{\"guid\":" << row.Guid
             << ",\"name\":\"" << Escape(row.Name)
             << "\",\"class_spec\":\"" << Escape(row.ClassSpec)
             << "\",\"present\":" << (row.Present ? "true" : "false")
             << ",\"alive\":" << (row.Alive ? "true" : "false")
             << ",\"mana\":" << row.Mana
             << ",\"max_mana\":" << row.MaxMana
             << ",\"mana_pct\":" << std::fixed << std::setprecision(1) << pct
             << std::defaultfloat << '}';
    }
    json << "]}";
    return json.str();
}
}

#endif
