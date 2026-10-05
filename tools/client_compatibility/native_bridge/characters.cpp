#include "data.hpp"
#include "character_list.hpp"
#include <ctime>
#include <map>

namespace bridge
{
Bytes character_list(Array const &characters, Array const &equipment,
                     std::unordered_map<unsigned, Array> const &item_displays)
{
    std::unordered_map<std::uint64_t, std::unordered_map<unsigned, Array>> visible;
    for (auto const &row : equipment)
    {
        auto item = integer(get(row, "itemEntry"));
        auto pos = item_displays.find(item);
        auto template_data = pos == item_displays.end() ? Array{0, 0, 0} : pos->second;
        visible[integer(get(row, "guid"))][integer(get(row, "slot"))] =
            Array{template_data[0], template_data[1], 0, template_data[2], 0, item, 0};
    }
    Writer w;
    for (auto bit : {1, 0, 0, 1, 0, 0, 0, 1, 0})
        w.bits(bit, 1);
    w.pack("IIiIIIII", {characters.size(), 0, 85, 1, 0, 0, 0, 0});
    for (auto const &c : characters)
    {
        auto guid = integer(get(c, "guid"));
        w.guid(guid, player_high())
            .pack("IBBBBhI",
                  {0x01010001, get(c, "slot"), get(c, "race"), get(c, "gender"), get(c, "class"), 0, 0});
        w.pack("Bii3fQ", {get(c, "level"), get(c, "map"), get(c, "zone"), get(c, "position_x"),
                          get(c, "position_y"), get(c, "position_z"), 0})
            .guid();
        // Character-list Classic hide bits retain their native positions. World
        // PlayerFlagsEx uses a different representation. Other login flags are
        // not covered by this translation.
        auto visibility = integer(get(c, "characterFlags")) & 0xc00u;
        w.pack("IIIBIII", {visibility, 0, 0, 0, 0, 0, 0});
        for (unsigned slot = 0; slot < 19; ++slot)
        {
            auto &items = visible[guid];
            auto pos = items.find(slot);
            w.pack("IBIBiII", pos == items.end() ? Array{0, 0, 0, 0, 0, 0, 0} : pos->second);
        }
        w.pack("iQi5iIIiI", {0, get(c, "logout_time"), 60895, 0, 0, 0, 0, 0, 0, 0, 0, 0});
        auto name = str(get(c, "name"));
        w.bits(name.size(), 6).bits(0, 1).raw(name).bits(0, 3).pack("III", {0, 0, 0});
    }
    return w.pack("i", {1}).bits(1, 1).bits(1, 1).bits(0, 3).finish();
}
Bytes PublicData::enumeration(Array const &characters, Array const &equipment) const
{
    return character_list(characters, equipment, item_displays);
}
Bytes auth_success(Array const &race_classes)
{
    std::map<unsigned, std::map<unsigned, unsigned>> supported;
    for (auto const &row : race_classes)
    {
        auto race = integer(get(row, "race")), cls = integer(get(row, "class")), expansion = integer(get(row, "expansion"));
        if (!race || race > 255 || !cls || cls > 255 || expansion > 3 ||
            !supported[race].emplace(cls, expansion).second)
            throw std::runtime_error("invalid native race/class availability");
    }
    Writer w;
    w.pack("I", {0}).bits(1, 1).bits(0, 1);
    w.pack("IIIBBIIIIq", {0x01010001, 1, 0, 3, 3, 0, supported.size(), 0, 0, std::time(nullptr)});
    for (auto const &[race, classes] : supported)
    {
        w.pack("BI", {race, classes.size()});
        for (auto const &[cls, expansion] : classes)
            w.pack("BBBB", {cls, expansion, expansion, expansion});
    }
    w.bits(0, 6).pack("III", {0, 0, 0}).bits(0, 3);
    std::string name = "Client442 Lab", normalized = "Client442Lab";
    return w.pack("I", {0x01010001})
        .bits(1, 1)
        .bits(0, 1)
        .bits(name.size(), 8)
        .bits(normalized.size(), 8)
        .raw(name + normalized)
        .finish();
}
std::vector<Packet> bootstrap_packets(PublicData const &data)
{
    Writer zone;
    zone.bits(3, 7).bits(3, 7).bits(3, 7).raw("UTCUTCUTC");
    Writer features;
    features.bits(0, 32).bits(1, 11).bits(0, 3).pack("IIqiII", {0, 0, 0, 10, 0, 0});
    features.pack("iiiiiIii", {0, 0, 3, 3, 3, 0, 0, 0}).pack("hhIIII", {100, 0, 0, 0, 0, 0});
    return {{"SMSG_CACHE_VERSION", Writer().pack("I", {60895}).finish()},
            {"SMSG_AVAILABLE_HOTFIXES", data.available()},
            {"SMSG_SET_TIME_ZONE_INFORMATION", zone.finish()},
            {"SMSG_FEATURE_SYSTEM_STATUS_GLUE_SCREEN", features.finish()}};
}
} // namespace bridge
