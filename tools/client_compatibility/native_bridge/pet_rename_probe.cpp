#include "pet_rename_probe.hpp"
#include "protocol.hpp"

namespace bridge
{
bool owned_pet_rename_probe(std::filesystem::path const &root, std::string const &direction,
    std::string const &name, View body, std::string const &session, double now)
{
    if(name!="CMSG_PET_RENAME" || (direction!="from_client" && direction!="to_native"))return false;
    try
    {
        auto path=root/"run/owned_pet_rename_probe.json";
        if(!std::filesystem::is_regular_file(path) || std::filesystem::file_size(path)>4096)return false;
        auto config=load_json(path);
        if(str(get(config,"schema"))!="client442_owned_pet_rename_probe_v1" ||
           str(get(config,"session"))!=session || integer(get(config,"owner"))!=6 ||
           integer(get(config,"pet_number"))!=4 || str(get(config,"synthetic_name"))!="Harnesswolf")return false;
        auto created=number(get(config,"created_at")),expires=number(get(config,"expires_at"));
        if(created>now || expires<=now || expires<=created || expires-created>120)return false;
        auto native=integer(get(config,"native_pet_guid"));
        if(native>>52!=0xf14 || ((native>>32)&0xfffff)!=42717 ||
           get(config,"modern_pet_guid")!=Protocol::modern_guid(native,0))return false;
        Reader r(body);
        if(direction=="from_client")
        {
            if(r.guid()!=get(config,"modern_pet_guid") || r.take<std::int32_t>()!=4)return false;
            if(r.bits(8)!=11 || r.bits(1) || r.bits(7))return false;
        }
        else if(r.take<std::uint64_t>()!=integer(get(config,"native_pet_guid")))return false;
        auto raw=r.raw(11);
        if(std::string_view(reinterpret_cast<char const *>(raw.data()),raw.size())!="Harnesswolf")return false;
        if(direction=="to_native" && (r.take<std::uint8_t>() || r.take<std::uint8_t>()))return false;
        r.end();return true;
    }
    catch(std::exception const &) {return false;}
}
}
