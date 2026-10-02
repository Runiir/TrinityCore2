// Pinned Trinity development protocol identity, GPL-2.0-or-later.
#include "crypto.hpp"
#include <algorithm>
#include <memory>
#include <numeric>
#include <openssl/core_names.h>
#include <openssl/evp.h>
#include <openssl/params.h>
#include <openssl/pem.h>
#include <openssl/rand.h>

namespace bridge
{
namespace
{
template <typename T, auto Free> using Owned = std::unique_ptr<T, decltype(Free)>;
void check(int result)
{
    if (result != 1)
        throw std::runtime_error("cryptographic operation failed");
}
Bytes const AUTH = unhex("de3a2a8e6b895266889d7e7a771d5d1f4ed90c239bcd0edcd2e8043a6864c7b0");
Bytes const SESSION = unhex("e81e8b5927621eaa861518eac0bf668c6dbf8393bcaa80525b1edc23a012b750");
Bytes const ENCRYPT = unhex("71c9ed5aa70e4dff4c36a65a3e468a4a5da148c830474adef60d6cbe6fe45573");
Bytes const CONTINUED = unhex("565c619c483a521f615d0549b29a39bf4b97b01bf96cded6801dab2602a99b9d");
Bytes const ENABLE = unhex("66be2979eff2d5b56153f65f45ae81cb32ec94ec75b35f446a63436717204434");
Bytes const CONTEXT = unhex("a71fb69bc97cdd96e9bbb821398d5ad4");
Bytes const DEV_KEY = unhex("08bdc7a3ccc34f3f6a0bffcf31c1b697691e729a0aab2c77c36f8ae75a9aa7c9");
std::pair<Bytes, Bytes> gcm(View key, View input, View nonce, View tag, bool encrypt)
{
    Owned<EVP_CIPHER_CTX, EVP_CIPHER_CTX_free> ctx(EVP_CIPHER_CTX_new(), EVP_CIPHER_CTX_free);
    check(EVP_CipherInit_ex(ctx.get(), EVP_aes_256_gcm(), nullptr, nullptr, nullptr, encrypt));
    check(EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_SET_IVLEN, nonce.size(), nullptr));
    check(EVP_CipherInit_ex(ctx.get(), nullptr, nullptr, key.data(), nonce.data(), encrypt));
    Bytes output(input.size() + 16), result_tag(12);
    int written = 0, tail = 0;
    check(EVP_CipherUpdate(ctx.get(), output.data(), &written, input.data(), input.size()));
    if (!encrypt)
    {
        if (tag.size() != 12)
            throw std::runtime_error("invalid integrity tag size");
        check(EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_SET_TAG, tag.size(),
                                  const_cast<std::uint8_t *>(tag.data())));
    }
    check(EVP_CipherFinal_ex(ctx.get(), output.data() + written, &tail));
    output.resize(written + tail);
    if (encrypt)
        check(EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_GET_TAG, result_tag.size(), result_tag.data()));
    return {std::move(output), std::move(result_tag)};
}
} // namespace
Bytes const &encryption_seed()
{
    return ENCRYPT;
}
Bytes const &continued_seed()
{
    return CONTINUED;
}
Bytes random_bytes(std::size_t size)
{
    Bytes result(size);
    check(RAND_bytes(result.data(), result.size()));
    return result;
}
Bytes hash(View input, std::string_view algorithm)
{
    Owned<EVP_MD, EVP_MD_free> md(EVP_MD_fetch(nullptr, std::string(algorithm).c_str(), nullptr),
                                  EVP_MD_free);
    if (!md)
        throw std::runtime_error("digest unavailable");
    Bytes result(EVP_MD_get_size(md.get()));
    unsigned size;
    check(EVP_Digest(input.data(), input.size(), result.data(), &size, md.get(), nullptr));
    result.resize(size);
    return result;
}
Bytes mac(View key, View input, std::string_view algorithm)
{
    Owned<EVP_MAC, EVP_MAC_free> alg(EVP_MAC_fetch(nullptr, "HMAC", nullptr), EVP_MAC_free);
    if (!alg)
        throw std::runtime_error("HMAC unavailable");
    Owned<EVP_MAC_CTX, EVP_MAC_CTX_free> ctx(EVP_MAC_CTX_new(alg.get()), EVP_MAC_CTX_free);
    std::string digest(algorithm);
    OSSL_PARAM params[] = {OSSL_PARAM_construct_utf8_string(OSSL_MAC_PARAM_DIGEST, digest.data(), 0),
                           OSSL_PARAM_END};
    check(EVP_MAC_init(ctx.get(), key.data(), key.size(), params));
    check(EVP_MAC_update(ctx.get(), input.data(), input.size()));
    Bytes result(64);
    std::size_t size;
    check(EVP_MAC_final(ctx.get(), result.data(), &size, result.size()));
    result.resize(size);
    return result;
}
bool constant_equal(View a, View b)
{
    return a.size() == b.size() && CRYPTO_memcmp(a.data(), b.data(), a.size()) == 0;
}
std::pair<Bytes, Bytes> derive(View data, View local, View server, View proof, std::string_view variant)
{
    if (data.size() != 64 || local.size() != 32 || server.size() != 32 || proof.size() != 24)
        throw std::runtime_error("invalid authentication material size");
    auto build = variant == "WoW"    ? unhex("5885e3019ae3f51d0227f92c365babd3")
                 : variant == "WoWC" ? unhex("0cae464f32d03f1eef0f14b2529907d2")
                                     : throw std::runtime_error("unsupported build variant");
    auto expected = mac(hash(concatenate({data, build})), concatenate({local, server, AUTH}));
    if (!constant_equal(View(expected).first(24), proof))
        throw std::runtime_error("world authentication proof rejected");
    auto material = mac(hash(data), concatenate({server, local, SESSION}));
    auto first = hash(View(material).first(32)), second = hash(View(material).subspan(32));
    auto session = hash(concatenate({first, Bytes(64), second}));
    session.resize(40);
    auto encrypt = mac(session, concatenate({local, server, ENCRYPT}));
    encrypt.resize(32);
    return {session, encrypt};
}
Bytes enabled_signature(View key)
{
    auto message = mac(key, concatenate({Bytes{1}, ENABLE}));
    Owned<EVP_PKEY, EVP_PKEY_free> pkey(
        EVP_PKEY_new_raw_private_key_ex(nullptr, "ED25519", nullptr, DEV_KEY.data(), DEV_KEY.size()),
        EVP_PKEY_free);
    Owned<EVP_MD_CTX, EVP_MD_CTX_free> ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
    char instance[] = "Ed25519ctx";
    OSSL_PARAM params[] = {OSSL_PARAM_construct_utf8_string(OSSL_SIGNATURE_PARAM_INSTANCE, instance, 0),
                           OSSL_PARAM_construct_octet_string(OSSL_SIGNATURE_PARAM_CONTEXT_STRING,
                                                             const_cast<std::uint8_t *>(CONTEXT.data()),
                                                             CONTEXT.size()),
                           OSSL_PARAM_END};
    check(EVP_DigestSignInit_ex(ctx.get(), nullptr, nullptr, nullptr, nullptr, pkey.get(), params));
    Bytes signature(64);
    std::size_t size = signature.size();
    check(EVP_DigestSign(ctx.get(), signature.data(), &size, message.data(), message.size()));
    if (size != 64)
        throw std::runtime_error("unexpected signature size");
    signature.push_back(0x80);
    return signature;
}
Bytes rsa_signature(std::filesystem::path const &path, View message)
{
    Owned<BIO, BIO_free> file(BIO_new_file(path.c_str(), "r"), BIO_free);
    if (!file)
        throw std::runtime_error("redirect identity missing");
    Owned<EVP_PKEY, EVP_PKEY_free> key(PEM_read_bio_PrivateKey(file.get(), nullptr, nullptr, nullptr),
                                       EVP_PKEY_free);
    Owned<EVP_MD_CTX, EVP_MD_CTX_free> ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
    check(EVP_DigestSignInit(ctx.get(), nullptr, EVP_sha256(), nullptr, key.get()));
    std::size_t size = 0;
    check(EVP_DigestSign(ctx.get(), nullptr, &size, message.data(), message.size()));
    Bytes result(size);
    check(EVP_DigestSign(ctx.get(), result.data(), &size, message.data(), message.size()));
    result.resize(size);
    std::reverse(result.begin(), result.end());
    return result;
}
Bytes PacketCrypt::encode(std::uint32_t opcode, View body)
{
    if (!key.empty() && key.size() != 32)
        throw std::runtime_error("invalid encryption key size");
    if (body.size() > 65532 || send_counter == UINT64_MAX)
        throw std::runtime_error("modern outbound frame bound");
    auto payload = Writer().put(opcode).raw(body).finish();
    Bytes tag(12);
    if (!key.empty())
    {
        auto nonce = Writer().pack("QI", {send_counter, 0x52565253}).finish();
        auto encrypted = gcm(key, payload, nonce, {}, true);
        payload = std::move(encrypted.first);
        tag = std::move(encrypted.second);
    }
    ++send_counter;
    return Writer().put<std::uint32_t>(payload.size()).raw(tag).raw(payload).finish();
}
std::pair<std::uint32_t, Bytes> PacketCrypt::decode(View payload, View tag)
{
    if (!key.empty() && key.size() != 32)
        throw std::runtime_error("invalid encryption key size");
    if (payload.size() < 4 || payload.size() > 65536 || recv_counter == UINT64_MAX)
        throw std::runtime_error("modern inbound frame bound");
    Bytes clear(payload.begin(), payload.end());
    if (!key.empty())
    {
        auto nonce = Writer().pack("QI", {recv_counter, 0x544e4c43}).finish();
        clear = gcm(key, payload, nonce, tag, false).first;
    }
    else if (!constant_equal(tag, Bytes(12)))
        throw std::runtime_error("unexpected integrity tag before encryption");
    ++recv_counter;
    Reader r(clear);
    auto opcode = r.take<std::uint32_t>();
    auto body = r.raw(r.remaining());
    return {opcode, Bytes(body.begin(), body.end())};
}
LegacyCrypt::LegacyCrypt(View key, View seed)
{
    auto material = mac(seed, key, "SHA1");
    std::iota(state_.begin(), state_.end(), 0);
    std::uint8_t j = 0;
    for (unsigned i = 0; i < 256; ++i)
    {
        j += state_[i] + material[i % material.size()];
        std::swap(state_[i], state_[j]);
    }
    transform(Bytes(1024));
}
Bytes LegacyCrypt::transform(View input)
{
    Bytes result;
    result.reserve(input.size());
    for (auto n : input)
    {
        ++i_;
        j_ += state_[i_];
        std::swap(state_[i_], state_[j_]);
        result.push_back(n ^ state_[static_cast<std::uint8_t>(state_[i_] + state_[j_])]);
    }
    return result;
}
} // namespace bridge
