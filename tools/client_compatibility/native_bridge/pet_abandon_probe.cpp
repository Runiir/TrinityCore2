#include "pet_abandon_probe.hpp"
#include "protocol.hpp"
#include <algorithm>

namespace bridge
{
bool owned_pet_abandon_probe(std::filesystem::path const &root,std::string const &direction,
    std::string const &name,View body,std::string const &session,double now)
{
    if(name!="CMSG_PET_ABANDON" || (direction!="from_client" && direction!="to_native"))return false;
    try
    {
        auto path=root/"run/owned_pet_abandon_probe.json";
        if(!std::filesystem::is_regular_file(path) || std::filesystem::file_size(path)>4096)return false;
        auto c=load_json(path);auto created=number(get(c,"created_at")),expires=number(get(c,"expires_at"));
        if(str(get(c,"schema"))!="client442_owned_pet_abandon_probe_v1" || integer(get(c,"owner"))!=6 ||
           integer(get(c,"pet_number"))!=6 || str(get(c,"session"))!=session ||
           created>now || expires<=now || expires<=created || expires-created>90)return false;
        auto guid=integer(get(c,"native_pet_guid"));
        if(guid>>52!=0xf14 || ((guid>>32)&0xfffff)!=299 ||
           get(c,"modern_pet_guid")!=Protocol::modern_guid(guid,0))return false;
        auto canonical=direction=="from_client" ? Writer().guid(Protocol::modern_guid(guid,0)).finish() :
            Writer().put<std::uint64_t>(guid).finish();
        return body.size()==canonical.size() && std::equal(body.begin(),body.end(),canonical.begin());
    }
    catch(std::exception const &) {return false;}
}
}
