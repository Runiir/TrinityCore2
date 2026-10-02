#include "data.hpp"
#include <ctime>
#include <fstream>

namespace bridge
{
namespace
{
Bytes read_file(std::filesystem::path const &path)
{
    auto size = std::filesystem::file_size(path);
    if (size > 128 * 1024 * 1024)
        throw std::runtime_error("public table exceeds bound");
    std::ifstream file(path, std::ios::binary);
    if (!file)
        throw std::runtime_error("public table absent");
    return Bytes(std::istreambuf_iterator<char>(file), {});
}
Array dbc(std::filesystem::path const &path, unsigned wanted_fields)
{
    auto data = read_file(path);
    Reader r(data);
    if (hex(r.raw(4)) != "57444243")
        throw std::runtime_error("unexpected DBC signature");
    auto count = r.take<std::uint32_t>(), fields = r.take<std::uint32_t>(), width = r.take<std::uint32_t>(),
         strings = r.take<std::uint32_t>();
    if (fields != wanted_fields || width != fields * 4 || count > 1000000 ||
        data.size() != 20ull + count * width + strings)
        throw std::runtime_error("unexpected public DBC layout");
    Array rows;
    for (unsigned i = 0; i < count; ++i)
        rows.push_back(r.unpack(std::string(fields, 'I')));
    return rows;
}
} // namespace
PublicData::PublicData(std::filesystem::path const &root, std::filesystem::path const &repo)
{
    auto directory = root / "data/dbc/enUS";
    for (auto const &row : dbc(directory / "TaxiPath.dbc", 4))
    {
        auto const &v = row.as_array();
        taxi_paths.push_back(Object{{"id", v[0]}, {"source", v[1]}, {"destination", v[2]}, {"cost", v[3]}});
    }
    auto data = read_file(directory / "Item.db2");
    Reader r(data);
    if (hex(r.raw(4)) != "57444232")
        throw std::runtime_error("unexpected native item table");
    auto head = r.unpack("11I");
    auto count = integer(head[0]), fields = integer(head[1]), width = integer(head[2]),
         strings = integer(head[3]);
    auto build = integer(head[5]), minimum = integer(head[7]), maximum = integer(head[8]);
    if (fields != 8 || width != 32 || build != 15595 || count > 1000000 || (maximum && maximum < minimum))
        throw std::runtime_error("unexpected native item display table");
    if (maximum)
        r.raw((maximum - minimum + 1) * 6);
    if (count * width + strings > r.remaining())
        throw std::runtime_error("truncated item display table");
    for (unsigned i = 0; i < count; ++i)
    {
        auto row = r.unpack("8I");
        item_displays[integer(row[0])] = Array{row[5], row[6], row[2]};
    }
    Database db(root);
    for (auto const &row :
         db.query("SELECT ID,DisplayInfoID,InventoryType,SubclassID FROM client442_hotfixes.item"))
        item_displays[integer(get(row, "ID"))] =
            Array{get(row, "DisplayInfoID"), get(row, "InventoryType"), get(row, "SubclassID")};
    for (auto const &row :
         db.query("SELECT "
                  "ID,BroadcastTextID0,BroadcastTextID1,BroadcastTextID2,BroadcastTextID3,BroadcastTextID4,"
                  "BroadcastTextID5,BroadcastTextID6,BroadcastTextID7 FROM client442_world.npc_text"))
    {
        Array ids;
        for (unsigned i = 0; i < 8; ++i)
            ids.push_back(get(row, "BroadcastTextID" + std::to_string(i)));
        npc_broadcasts[integer(get(row, "ID"))] = ids;
    }
    for (auto const &row :
         db.query("SELECT "
                  "Text,Text1,ID,LanguageID,EmotesID,Flags,EmoteID1,EmoteID2,EmoteID3,EmoteDelay1,"
                  "EmoteDelay2,EmoteDelay3 FROM client442_world.broadcast_text"))
    {
        auto male = str(get(row, "Text")), female = str(get(row, "Text1"));
        if (male.size() > 16384 || female.size() > 16384 || male.find('\0') != std::string::npos ||
            female.find('\0') != std::string::npos)
            throw std::runtime_error("invalid public broadcast string");
        Writer w;
        w.raw(male).put<std::uint8_t>(0).raw(female).put<std::uint8_t>(0);
        w.pack("IiiHHIi2I6H",
               {get(row, "ID"), get(row, "LanguageID"), 0, get(row, "EmotesID"), get(row, "Flags"), 0, 0, 0,
                0, get(row, "EmoteID1"), get(row, "EmoteID2"), get(row, "EmoteID3"), get(row, "EmoteDelay1"),
                get(row, "EmoteDelay2"), get(row, "EmoteDelay3")});
        broadcasts[integer(get(row, "ID"))] = w.finish();
    }
    auto config = load_json(repo / "experiments/configs/client_harness/public_portal_hotfix_v1.json");
    if (integer(get(config, "client_build")) != 60895)
        throw std::runtime_error("public hotfix build mismatch");
    hotfixes = get(config, "records").as_array();
    if (hotfixes.size() != 2)
        throw std::runtime_error("public hotfix allowlist mismatch");
    std::unordered_set<unsigned> expected{4352, 4354};
    for (auto const &row : hotfixes)
    {
        if (integer(get(row, "table_hash")) != 0x1a5081e1 ||
            !expected.erase(integer(get(row, "record_id"))) || unhex(str(get(row, "data"))).size() != 55)
            throw std::runtime_error("public portal hotfix layout mismatch");
    }
}
Bytes PublicData::available() const
{
    Writer w;
    w.pack("II", {0x01010001, hotfixes.size()});
    for (auto const &row : hotfixes)
        w.pack("iI", {get(row, "push_id"), get(row, "unique_id")});
    return w.finish();
}
Bytes PublicData::hotfix_request(View body) const
{
    Reader r(body);
    auto build = r.take<std::uint32_t>();
    r.take<std::uint32_t>();
    auto count = r.take<std::uint32_t>();
    if (build != 60895 || count > 512)
        throw std::runtime_error("unsupported hotfix request build or count");
    std::unordered_set<std::int32_t> ids;
    for (unsigned i = 0; i < count; ++i)
        ids.insert(r.take<std::int32_t>());
    r.end();
    Writer w, data;
    unsigned rows = 0;
    for (auto const &row : hotfixes)
        if (ids.contains(signed_integer(get(row, "push_id"))))
            ++rows;
    if (ids.size() != rows)
        throw std::runtime_error("unadvertised hotfix requested");
    w.pack("I", {rows});
    for (auto const &row : hotfixes)
        if (ids.contains(signed_integer(get(row, "push_id"))))
        {
            auto payload = unhex(str(get(row, "data")));
            data.raw(payload);
            w.pack("IIIiI", {get(row, "push_id"), get(row, "unique_id"), get(row, "table_hash"),
                             get(row, "record_id"), payload.size()})
                .bits(1, 3);
        }
    return w.put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
std::vector<Packet> PublicData::bulk_query(View body) const
{
    Reader r(body);
    auto table = r.take<std::uint32_t>();
    auto count = r.bits(13);
    if (count > 1024)
        throw std::runtime_error("excessive DB query");
    auto records = r.unpack(std::string(count, 'I'));
    r.end();
    std::vector<Packet> result;
    for (auto const &record : records)
    {
        std::optional<Bytes> data;
        if (table == 0x021826bb)
        {
            auto pos = broadcasts.find(integer(record));
            if (pos != broadcasts.end())
                data = pos->second;
        }
        if (!data)
            for (auto const &row : hotfixes)
                if (table == integer(get(row, "table_hash")) && record == get(row, "record_id"))
                    data = unhex(str(get(row, "data")));
        Writer w;
        w.pack("III", {table, record, static_cast<unsigned>(std::time(nullptr))})
            .bits(data ? 1 : 3, 3)
            .put<std::uint32_t>(data ? data->size() : 0);
        if (data)
            w.raw(*data);
        result.push_back({"SMSG_DB_REPLY", w.finish()});
    }
    return result;
}
} // namespace bridge
