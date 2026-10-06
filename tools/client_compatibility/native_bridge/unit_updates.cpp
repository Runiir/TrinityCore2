#include "protocol.hpp"

namespace bridge
{
Bytes Protocol::scalar_block(Value const &s, Value const &character, Value const &changed,
                             unsigned visibility) const
{
    struct Scalar {char const *name; unsigned index; char fmt; char const *native; bool owner=false;};
    // Pinned UnitData::WriteUpdate order and visibility. Array payloads are interleaved,
    // not sorted by their mask indices. Zeroes and signed debuffs must be transmitted.
    static Scalar const scalars[] = {
        {"Health",5,'q',"UNIT_FIELD_HEALTH"}, {"MaxHealth",6,'q',"UNIT_FIELD_MAXHEALTH"},
        {"DisplayID",7,'i',"UNIT_FIELD_DISPLAYID"},
        {"Summon",14,'g',"UNIT_FIELD_SUMMON"},
        {"SummonedBy",17,'g',"UNIT_FIELD_SUMMONEDBY"}, {"CreatedBy",18,'g',"UNIT_FIELD_CREATEDBY"},
        {"Target",21,'g',"UNIT_FIELD_TARGET"}, {"Flags",41,'I',"UNIT_FIELD_FLAGS"},
        {"Flags2",42,'I',"UNIT_FIELD_FLAGS_2"},
        {"RangedAttackRoundBaseTime",46,'I',"UNIT_FIELD_RANGEDATTACKTIME"},
        {"MountDisplayID",52,'i',"UNIT_FIELD_MOUNTDISPLAYID"},
        {"MinDamage",53,'f',"UNIT_FIELD_MINDAMAGE",true}, {"MaxDamage",54,'f',"UNIT_FIELD_MAXDAMAGE",true},
        {"MinOffHandDamage",55,'f',"UNIT_FIELD_MINOFFHANDDAMAGE",true}, {"MaxOffHandDamage",56,'f',"UNIT_FIELD_MAXOFFHANDDAMAGE",true},
        {"StandState",57,'B',"UNIT_FIELD_BYTES_1"}, {"VisFlags",59,'B',"UNIT_FIELD_BYTES_1"},
        {"AnimTier",60,'B',"UNIT_FIELD_BYTES_1"},
        {"PetNumber",61,'I',"UNIT_FIELD_PETNUMBER"}, {"PetNameTimestamp",62,'I',"UNIT_FIELD_PET_NAME_TIMESTAMP"},
        {"ModCastingSpeed",66,'f',"UNIT_MOD_CAST_SPEED"},
        {"ModSpellHaste",67,'f',"UNIT_MOD_CAST_HASTE"},
        {"ModHaste",68,'f',"PLAYER_FIELD_MOD_HASTE",true},
        {"ModRangedHaste",69,'f',"PLAYER_FIELD_MOD_RANGED_HASTE",true},
        {"ModHasteRegen",70,'f',"PLAYER_FIELD_MOD_HASTE_REGEN",true},
        {"SheatheState",78,'B',"UNIT_FIELD_BYTES_2"},
        {"PvpFlags",79,'B',"UNIT_FIELD_BYTES_2"}, {"PetFlags",80,'B',"UNIT_FIELD_BYTES_2"},
        {"ShapeshiftForm",81,'B',"UNIT_FIELD_BYTES_2"},
        {"AttackPower",82,'i',"UNIT_FIELD_ATTACK_POWER",true}, {"AttackPowerModPos",83,'i',"UNIT_FIELD_ATTACK_POWER_MOD_POS",true},
        {"AttackPowerModNeg",84,'i',"UNIT_FIELD_ATTACK_POWER_MOD_NEG",true}, {"AttackPowerMultiplier",85,'f',"UNIT_FIELD_ATTACK_POWER_MULTIPLIER",true},
        {"RangedAttackPower",86,'i',"UNIT_FIELD_RANGED_ATTACK_POWER",true}, {"RangedAttackPowerModPos",87,'i',"UNIT_FIELD_RANGED_ATTACK_POWER_MOD_POS",true},
        {"RangedAttackPowerModNeg",88,'i',"UNIT_FIELD_RANGED_ATTACK_POWER_MOD_NEG",true}, {"RangedAttackPowerMultiplier",89,'f',"UNIT_FIELD_RANGED_ATTACK_POWER_MULTIPLIER",true},
        {"MinRangedDamage",92,'f',"UNIT_FIELD_MINRANGEDDAMAGE",true}, {"MaxRangedDamage",93,'f',"UNIT_FIELD_MAXRANGEDDAMAGE",true}};
    struct Payload {char fmt; Value value;};
    std::array<std::uint32_t,8> masks{};
    std::vector<Payload> payload;
    auto values=field_values(s,character);auto const &unit=get(values,"UnitData");
    auto append=[&](unsigned index,unsigned parent,char fmt,Value const &value)
    {
        masks[index/32]|=1u<<(index%32);
        masks[parent/32]|=1u<<(parent%32);
        payload.push_back({fmt,value});
    };
    auto has=[&](char const *native,unsigned offset=0)
    {return changed.as_object().contains(std::to_string(field_index(native)+offset));};
    for(auto const &spec:scalars)
        if((!spec.owner || (visibility&1)) &&
           (has(spec.native) || (spec.fmt=='g' && has(spec.native,1))))
            append(spec.index,(spec.index/32)*32,spec.fmt,get(unit,spec.name));
    auto element=[&](char const *modern,char const *native,unsigned i,unsigned index,unsigned parent,char fmt='i')
    {
        if(has(native,i))append(index,parent,fmt,get(unit,modern).as_array().at(i));
    };
    for(unsigned i=0;i<5;++i)
    {
        element("Power","UNIT_FIELD_POWER1",i,138+i,117);
        element("MaxPower","UNIT_FIELD_MAXPOWER1",i,148+i,117);
    }
    for(unsigned i=0;i<2;++i)
        element("AttackRoundBaseTime","UNIT_FIELD_BASEATTACKTIME",i,173+i,172,'I');
    if(has("UNIT_FIELD_RANGEDATTACKTIME"))
        append(175,172,'I',get(unit,"AttackRoundBaseTime").as_array().at(2));
    if(visibility&1)
    {
        for(unsigned i=0;i<5;++i)
        {
            element("Stats","UNIT_FIELD_STAT0",i,177+i,176);
            element("StatPosBuff","UNIT_FIELD_POSSTAT0",i,182+i,176);
            element("StatNegBuff","UNIT_FIELD_NEGSTAT0",i,187+i,176);
        }
        for(unsigned i=0;i<7;++i)
        {
            element("Resistances","UNIT_FIELD_RESISTANCES",i,193+i,192);
            element("ResistanceBuffModsPositive","UNIT_FIELD_RESISTANCEBUFFMODSPOSITIVE",i,200+i,192);
            element("ResistanceBuffModsNegative","UNIT_FIELD_RESISTANCEBUFFMODSNEGATIVE",i,207+i,192);
            element("PowerCostModifier","UNIT_FIELD_POWER_COST_MODIFIER",i,214+i,192);
            element("PowerCostMultiplier","UNIT_FIELD_POWER_COST_MULTIPLIER",i,221+i,192,'f');
        }
    }
    if(payload.empty())return {};
    Writer data;data.pack("BBBI",{visibility,0,3,1u<<5});
    unsigned presence=0;for(unsigned i=0;i<8;++i)if(masks[i])presence|=1u<<i;
    data.bits(presence,8);for(auto mask:masks)if(mask)data.bits(mask,32);data.flush();
    for(auto const &part:payload)
        if(part.fmt=='g')data.guid(part.value.as_array());
        else data.pack(std::string(1,part.fmt),{part.value});
    return Writer().pack("B",{0}).guid(modern_guid(integer(get(s,"guid")),integer(get(s,"map"))))
        .put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
} // namespace bridge
