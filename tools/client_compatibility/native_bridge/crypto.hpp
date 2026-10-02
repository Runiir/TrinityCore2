#pragma once
#include "buffer.hpp"
#include <array>
#include <optional>

namespace bridge
{
Bytes random_bytes(std::size_t size);
Bytes hash(View data, std::string_view algorithm = "SHA512");
Bytes mac(View key, View data, std::string_view algorithm = "SHA512");
bool constant_equal(View a, View b);
std::pair<Bytes, Bytes> derive(View key_data, View local, View server, View proof, std::string_view variant);
Bytes enabled_signature(View key);
Bytes rsa_signature(std::filesystem::path const &pem, View data);
Bytes const &encryption_seed();
Bytes const &continued_seed();
class PacketCrypt
{
  public:
    Bytes key;
    std::uint64_t send_counter = 0, recv_counter = 0;
    Bytes encode(std::uint32_t opcode, View body);
    std::pair<std::uint32_t, Bytes> decode(View payload, View tag);
};
class LegacyCrypt
{
    std::array<std::uint8_t, 256> state_{};
    std::uint8_t i_ = 0, j_ = 0;

  public:
    LegacyCrypt(View key, View seed);
    Bytes transform(View input);
};
} // namespace bridge
