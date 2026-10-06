#include "control_skill_metadata.hpp"
#include "crypto.hpp"
#include <map>

namespace bridge
{
Array control_skill_hotfixes(View native, Value const &config)
{
    constexpr unsigned Table=4282664694u;
    if (str(get(config,"schema"))!="client442_control_skill_metadata_v1" ||
        integer(get(config,"client_build"))!=60895 || integer(get(config,"native_build"))!=15595 ||
        integer(get(config,"table_hash"))!=Table || str(get(config,"layout_hash"))!="738BFEE1" ||
        native.size()>16*1024*1024 || hex(hash(native,"SHA256"))!=str(get(config,"native_source_sha256")))
        throw std::runtime_error("native control skill source or pinned layout differs");
    Reader r(native);
    if (hex(r.raw(4))!="57444243")throw std::runtime_error("invalid control skill DBC signature");
    auto count=r.take<std::uint32_t>(),fields=r.take<std::uint32_t>();
    auto width=r.take<std::uint32_t>(),strings=r.take<std::uint32_t>();
    if (fields!=14 || width!=56 || count>100000 || native.size()!=20ull+count*width+strings)
        throw std::runtime_error("invalid control skill DBC boundary");
    std::map<unsigned,Array> source;
    for (unsigned i=0;i<count;++i)
    {
        auto row=r.unpack("14I");auto id=integer(row[0]);
        if (id==21975 || id==23872)
            if (!source.emplace(id,std::move(row)).second)
                throw std::runtime_error("duplicate native control skill record");
    }
    r.raw(strings);r.end();
    auto const &records=get(config,"records").as_array();
    if (source.size()!=2 || records.size()!=2)
        throw std::runtime_error("native control skill allowlist differs");
    Array hotfixes;
    for (unsigned i=0;i<2;++i)
    {
        auto const &spec=records[i];unsigned id=i ? 23872 : 21975,spell=i ? 93375 : 80388;
        unsigned push=60895004+i;
        auto const &v=source.at(id),&expected=get(spec,"native_values").as_array();
        if (integer(get(spec,"record_id"))!=id || integer(get(spec,"push_id"))!=push ||
            integer(get(spec,"unique_id"))!=push || expected.size()!=14)
            throw std::runtime_error("control skill hotfix identity differs");
        for (unsigned column=0;column<14;++column)
            if (integer(v[column])!=integer(expected[column]))
                throw std::runtime_error("native control skill fields differ from evidence");
        // These two recorded native rows have no rank successor or race
        // exclusion. Preserve the class/skill association without inventing
        // modern rank direction, acquisition rules or learning outcomes.
        Array exact{id,354,spell,0,256,0,0,1,0,0,0,0,0,0};
        for (unsigned column=0;column<14;++column)
            if (integer(v[column])!=integer(exact[column]))
                throw std::runtime_error("unsupported native control skill semantics");
        auto payload=Writer().pack("QIHIHIIIHHIBHHH2I",
            {v[3],v[0],v[1],v[2],v[7],v[4],v[8],v[9],v[10],v[11],0,v[12],v[13],0,0,0,0}).finish();
        hotfixes.push_back(Object{{"push_id",push},{"unique_id",push},{"table_hash",Table},
            {"record_id",id},{"data",hex(payload)}});
    }
    return hotfixes;
}
}
