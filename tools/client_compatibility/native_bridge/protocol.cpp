#include "protocol.hpp"
#include <bit>

namespace bridge
{
Protocol::Protocol(std::filesystem::path const &path)
    : directory(path), index(load_json(path / "native_fields.json")),
      sequences(get(load_json(path / "native_movement.json"), "sequences")),
      opcodes(load_json(path / "opcodes.json")),
      inventory_results(get(load_json(path / "inventory_results.json"),"results")), fields(path / "fields.json")
{
    for (auto const &[name, number] : get(opcodes, "modern").as_object())
        modern_names[integer(number)] = std::string(name);
    for (auto const &[name, number] : get(opcodes, "legacy").as_object())
        legacy_names[integer(number)] = std::string(name);
}
std::uint32_t Protocol::field(Value const &snapshot, std::string_view name, unsigned offset) const
{
    if (!index.as_object().contains(name))
        throw std::runtime_error("unknown native field");
    return integer(get(get(snapshot, "fields"), std::to_string(field_index(name) + offset)));
}
float Protocol::float_field(Value const &snapshot, std::string_view name, unsigned offset) const
{
    return std::bit_cast<float>(field(snapshot, name, offset));
}
Array Protocol::modern_guid(std::uint64_t native, unsigned map)
{
    if (!native)
        return {0, 0};
    auto high = native >> 52;
    if(native >> 48 == 0x4000)return inventory_guid(native);
    if (!high)
        return {native, player_high()};
    auto type = high == 0xf11   ? 11ull
                : high == 0xf13 ? 8ull
                                : throw std::runtime_error("unsupported visible-object identity");
    auto entry = (native >> 32) & 0xfffff;
    return {native & 0xffffffff,
            (type << 58) | (1ull << 42) | (static_cast<std::uint64_t>(map) << 29) | (entry << 6)};
}
Array Protocol::inventory_guid(std::uint64_t native)
{
    if (!native)
        return {0, 0};
    auto high = native >> 48;
    if (high == 0x4000)
        return {native & 0xffffffff, (3ull << 58) | (1ull << 42)};
    if (!high)
        return {native, player_high()};
    throw std::runtime_error("unsupported inventory GUID type");
}
std::uint64_t owned_gameobject(State const &state, Array const &identity)
{
    for (auto const &[native, record] : state.visible_gameobjects)
        if (identity == Protocol::modern_guid(native, integer(get(record, "map"))))
            return native;
    throw std::runtime_error("game object is not visible to the native character");
}
std::uint64_t owned_unit(State const &state, Array const &identity)
{
    for (auto const &[native, record] : state.visible_units)
        if (identity == Protocol::modern_guid(native, integer(get(record, "map"))))
            return native;
    throw std::runtime_error("creature is not visible to the owned native session");
}
} // namespace bridge
