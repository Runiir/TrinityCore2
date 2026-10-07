#include "stable_probe.hpp"
#include "protocol.hpp"
#include "stables.hpp"

namespace bridge
{
bool owned_stable_request_probe(std::filesystem::path const &root, std::string const &direction,
    std::string const &name, View body, std::string const &session, double now)
{
    bool request=name=="CMSG_REQUEST_STABLED_PETS" && direction=="from_client";
    bool catalog=name=="MSG_LIST_STABLED_PETS" && direction=="from_native";
    if(!request && !catalog)return false;
    try
    {
        auto path=root/"run/owned_stable_request_probe.json";
        if(!std::filesystem::is_regular_file(path) || std::filesystem::file_size(path)>4096)return false;
        auto config=load_json(path);
        if(str(get(config,"schema"))!="client442_owned_stable_request_probe_v1" ||
           str(get(config,"session"))!=session || integer(get(config,"owner"))!=6)return false;
        auto created=number(get(config,"created_at")),expires=number(get(config,"expires_at"));
        if(created>now || expires<=now || expires<=created || expires-created>120)return false;
        auto native=integer(get(config,"native_master_guid"));
        if(native>>52!=0xf13 || ((native>>32)&0xfffff)!=6749 || !(native&0xffffffff) ||
           get(config,"modern_master_guid")!=Protocol::modern_guid(native,0))return false;
        if(catalog)return integer(get(native_stable_list(body),"native_master"))==native;
        Reader r(body);
        if(r.guid()!=get(config,"modern_master_guid"))return false;
        r.end();return true;
    }
    catch(std::exception const &) {return false;}
}
}
