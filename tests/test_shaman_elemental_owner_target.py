"""Compile the production acquisition function with native-shaped observations."""
from pathlib import Path
import subprocess
from test_warlock_doomguard_guardian import function as extract_function

ROOT = Path(__file__).resolve().parents[1]
function_source = extract_function


def nth_function(source: str, signature: str, occurrence: int) -> str:
    start = -1
    for _ in range(occurrence + 1):
        start = source.index(signature, start + 1)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_elemental_acquires_native_owner_helper_only_without_victim(tmp_path):
    text = (ROOT / "src/server/scripts/Pet/pet_shaman.cpp").read_text()
    start = text.index("Unit* ShamanElementalOwner(")
    end = text.index("\nenum ShamanSpells", start)
    function = text[start:end]
    native_spells = (ROOT / "src/server/game/Entities/Object/WorldObjectSpells.cpp").read_text()
    native_owner_source = (ROOT / "src/server/game/Entities/Object/WorldObjectSummons.cpp").read_text()
    native_owner_player = function_source(
        native_owner_source,
        "Player* WorldObject::GetCharmerOrOwnerPlayerOrPlayerItself() const",
    )
    native_affecting = function_source(
        native_owner_source,
        "Player* WorldObject::GetAffectingPlayer() const",
    )
    assert "totem->GetCharmerOrOwnerGUID().IsEmpty()" in native_affecting
    assert "creature->GetOwnerGUID() != owner->GetGUID()" in native_affecting
    reaction_start = native_spells.index("            if (selfPlayerOwner && targetPlayerOwner)")
    reaction_end = native_spells.index("            // check FFA_PVP", reaction_start)
    native_reaction_block = native_spells[reaction_start:reaction_end]
    friendly_start = native_spells.index("    // PvP, PvC, CvP case")
    friendly_end = native_spells.index("    Player const* playerAffectingAttacker", friendly_start)
    native_friendly_rejection = native_spells[friendly_start:friendly_end]
    assert "selfPlayerOwner->IsInRaidWith(targetPlayerOwner)" in native_reaction_block
    assert "selfPlayerOwner->duel->opponent" in native_reaction_block
    assert "if (IsFriendlyTo(target) || target->IsFriendlyTo(this))" in native_friendly_rejection
    forced_start = native_spells.index("    // check forced reputation")
    forced_end = native_spells.index("    Unit const* unit =", forced_start)
    native_forced_block = native_spells[forced_start:forced_end]
    assert "GetForcedRankIfAny" in native_forced_block
    spell_source = (ROOT / "src/server/game/Spells/Spell.cpp").read_text()
    enemy_start = spell_source.index("            case TARGET_CHECK_ENEMY:")
    enemy_end = spell_source.index("                break;", enemy_start) + len("                break;")
    native_enemy_check = spell_source[enemy_start:enemy_end]
    assert "_caster->IsValidAttackTarget(unitTarget, _spellInfo)" in native_enemy_check
    attack = nth_function(text, "void AttackStart(Unit* target) override", 0)
    attack_second = nth_function(text, "void AttackStart(Unit* target) override", 1)
    reset = nth_function(text, "void Reset() override", 0)
    reset_second = nth_function(text, "void Reset() override", 1)
    update = nth_function(text, "void UpdateAI(uint32 diff) override", 0)
    update_second = nth_function(text, "void UpdateAI(uint32 diff) override", 1)
    assert attack == attack_second
    assert reset.startswith("void Reset() override\n            {")
    assert reset_second.startswith("void Reset() override\n            {")
    assert "InitializeShamanElementalPlayerControlled(me);" in reset
    assert "InitializeShamanElementalPlayerControlled(me);" in reset_second
    assert "InitializeShamanElementalPlayerControlled(me);" in update
    assert "InitializeShamanElementalPlayerControlled(me);" in update_second
    assert "target && me->IsValidAttackTarget(target)" in text
    victim_update = extract_function((ROOT / "src/server/game/AI/CreatureAI.cpp").read_text(), "bool CreatureAI::UpdateVictim()")
    assert text.count("StopShamanProtectedVictim(me);") == 2
    assert "IsInSameRaidWith" not in text
    assert text.count("SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED)") == 1
    assert "SetTargetMap" not in text
    source = tmp_path / "elemental_owner.cpp"
    source.write_text(r'''
#include <cassert>
#include <initializer_list>
#include <algorithm>
#include <tuple>
#include <vector>
#include <functional>
#include "Bots/BotRaidAreaAuthority.h"
#include "ObjectGuid.h"
ObjectGuid const ObjectGuid::Empty{};
constexpr int UNIT_FIELD_FLAGS = 1;
constexpr int UNIT_FLAG_PLAYER_CONTROLLED = 8;
constexpr int UNIT_STATE_CASTING = 1;
constexpr int TARGET_CHECK_ENEMY = 0;
enum ReputationRank { REP_HATED = 0, REP_HOSTILE = 1, REP_UNFRIENDLY = 2,
    REP_NEUTRAL = 3, REP_FRIENDLY = 4 };
struct FactionTemplateEntry {};
struct WorldObject; struct Player; struct Totem; struct Creature; struct TempSummon; struct Unit;
struct SpellInfo {};
struct ReputationMgr {
    bool forced = false; ReputationRank rank = REP_NEUTRAL;
    ReputationRank const* GetForcedRankIfAny(FactionTemplateEntry const*) const { return forced ? &rank : nullptr; }
};
struct CombatRef {Unit* target;bool suppressed=false;Unit* GetOther(Unit const*)const{return target;}bool IsSuppressedFor(Unit const*)const{return suppressed;}};
struct CombatManager {std::vector<std::pair<int,CombatRef*>> pve,pvp;
 auto const& GetPvECombatRefs()const{return pve;}auto const& GetPvPCombatRefs()const{return pvp;}};
struct ObjectAccessor {
    static Unit* GetUnit(WorldObject const&, ObjectGuid);
    static Player* GetPlayer(WorldObject const&, ObjectGuid);
};
struct WorldObject {
    virtual ~WorldObject()=default;
    virtual Player* ToPlayer(){return nullptr;}
    virtual Unit* ToUnit(){return nullptr;}
    virtual Unit const* ToUnit() const {return nullptr;}
    virtual Creature const* ToCreature() const {return nullptr;}
    virtual ObjectGuid GetOwnerGUID() const {return ObjectGuid::Empty;}
    virtual ObjectGuid GetCharmerOrOwnerGUID() const {return GetOwnerGUID();}
    virtual FactionTemplateEntry const* GetFactionTemplateEntry() const {return nullptr;}
    bool IsCorpse() const {return false;}
    Unit* GetOwner() const;
    Unit* GetCharmerOrOwner() const;
    Player* GetCharmerOrOwnerPlayerOrPlayerItself() const;
    Player* GetAffectingPlayer() const;
    ReputationRank GetReactionTo(WorldObject const* target) const;
    bool IsFriendlyTo(WorldObject const* target) const {return GetReactionTo(target) >= REP_FRIENDLY;}
    bool IsValidAttackTarget(Unit const* target, SpellInfo const* spell = nullptr) const;
};
struct Unit : WorldObject {
    virtual ~Unit()=default;
    ObjectGuid guid{HighGuid::Unit,30010u},ownerGuid=ObjectGuid::Empty,charmerGuid=ObjectGuid::Empty;
    uint32 entry=0;CombatManager combat;Unit* charmer=nullptr;Unit* victim=nullptr;Unit* helper=nullptr;
    FactionTemplateEntry* faction=nullptr;ReputationMgr reputation;
    bool alive=true,valid=true,engaged=true,totem=false,guardian=false,hostile=false,charmed=false;
    int type=TYPEID_UNIT,helperCalls=0,raidId=0,flags=0;
    ObjectGuid GetGUID()const{return guid;}uint32 GetEntry()const{return entry;}
    CombatManager& GetCombatManager(){return combat;}
    ObjectGuid GetOwnerGUID() const override {return ownerGuid;}
    ObjectGuid GetCharmerOrOwnerGUID() const override {return charmed ? charmerGuid : GetOwnerGUID();}
    Unit* ToUnit() override {return this;} Unit const* ToUnit() const override {return this;}
    Unit* GetCharmerOrOwner() const {return charmed ? charmer : GetOwner();}
    virtual Totem* ToTotem(){return nullptr;}
    FactionTemplateEntry const* GetFactionTemplateEntry() const override {return faction;}
    bool IsTotem()const{return totem;}bool IsGuardian()const{return guardian;}bool IsCharmed()const{return charmed;}
    Unit* GetVictim()const{return victim;}
    Unit* getAttackerForHelper(){++helperCalls;return engaged?helper:nullptr;}
    bool IsAlive()const{return alive;}
    bool HasFlag(int field,int flag)const{return field==UNIT_FIELD_FLAGS&&(flags&flag)==flag;}
    void SetFlag(int field,int flag){assert(field==UNIT_FIELD_FLAGS);flags|=flag;}
    int GetTypeId()const{return type;}
};
struct Player : Unit {
    struct DuelInfo {Player* opponent;int startTime;}; DuelInfo* duel=nullptr;
    Player(){type=TYPEID_PLAYER;} Player* ToPlayer()override{return this;}
    ReputationMgr const& GetReputationMgr()const{return reputation;}
    bool IsInRaidWith(Player const* other)const{return other&&raidId&&raidId==other->raidId;}
};
struct Totem : Unit {
    Unit* nativeOwner=nullptr;
    Totem(){totem=true;type=3;} Totem* ToTotem()override{return this;}
    Unit* GetOwner()const{return nativeOwner;}
};
struct Creature : Unit {
    Creature(){hostile=true;}TempSummon* summon=nullptr;Unit* selected=nullptr;
    bool HasReactState(int)const{return false;}bool IsInCombat()const{return true;}
    Unit* SelectVictim(){return selected;}
    int interrupts=0,stops=0,casts=0,melee=0;bool casting=false;Unit* lastCastTarget=nullptr;uint32 lastSpell=0;
    uint32 GetSpawnId()const{return 0;}void InterruptNonMeleeSpells(bool){++interrupts;casting=false;}
    void AttackStop(){++stops;victim=nullptr;}bool HasUnitState(int state)const{return state==UNIT_STATE_CASTING&&casting;}
    void ApplySpellImmune(int,int,int,bool){}bool CanStartAttack(Unit*,bool)const{return true;}
    struct Controller {Creature* parent;int attacks=0;Unit* target=nullptr;bool reject=false;std::function<void(Unit*)> dispatch{};
        void AttackStart(Unit* unit){if(dispatch){dispatch(unit);return;}++attacks;if(!reject){target=unit;parent->victim=unit;}}} ai{this};
    virtual TempSummon* ToTempSummon(){return summon;}Creature const* ToCreature()const override{return this;}
    Controller* AI(){return &ai;}
};
struct TempSummon : Creature {
    Unit* summoner=nullptr;TempSummon(){summon=this;}Unit* GetSummoner()const{return summoner;}
    TempSummon* ToTempSummon()override{return this;}
};
std::vector<Unit*> unitRegistry;
Unit* ObjectAccessor::GetUnit(WorldObject const&, ObjectGuid guid){for(Unit* unit:unitRegistry)if(unit&&unit->GetGUID()==guid)return unit;return nullptr;}
Player* ObjectAccessor::GetPlayer(WorldObject const&, ObjectGuid guid){for(Unit* unit:unitRegistry)if(unit&&unit->GetGUID()==guid)if(Player* player=unit->ToPlayer())return player;return nullptr;}
void Register(Unit& unit){unitRegistry.push_back(&unit);}
Unit* WorldObject::GetOwner()const{return ObjectAccessor::GetUnit(*this,GetOwnerGUID());}
Unit* WorldObject::GetCharmerOrOwner()const{if(Unit const* unit=ToUnit())return unit->GetCharmerOrOwner();return nullptr;}
''' + native_owner_player + r'''
''' + native_affecting + r'''
Player* HistoricalGetAffectingPlayer(WorldObject const* object){
    if(!object->GetCharmerOrOwnerGUID())return const_cast<WorldObject*>(object)->ToPlayer();
    if(Unit* owner=object->GetCharmerOrOwner())return owner->GetCharmerOrOwnerPlayerOrPlayerItself();
    return nullptr;
}
ReputationRank WorldObject::GetReactionTo(WorldObject const* target)const{
    if(this==target)return REP_FRIENDLY;
    Player const* selfPlayerOwner=GetAffectingPlayer();Player const* targetPlayerOwner=target->GetAffectingPlayer();
''' + native_forced_block + r'''
    Unit const* unit=ToUnit();Unit const* targetUnit=target->ToUnit();
    if(unit&&unit->HasFlag(UNIT_FIELD_FLAGS,UNIT_FLAG_PLAYER_CONTROLLED)&&targetUnit&&targetUnit->HasFlag(UNIT_FIELD_FLAGS,UNIT_FLAG_PLAYER_CONTROLLED)){
''' + native_reaction_block + r'''
    }
    return (unit&&unit->hostile)||(targetUnit&&targetUnit->hostile)?REP_HOSTILE:REP_NEUTRAL;
}
bool WorldObject::IsValidAttackTarget(Unit const* target,SpellInfo const*)const{
    if(!target||!target->alive||!target->valid)return false;
''' + native_friendly_rejection + r'''
    return true;
}
static bool NativeEnemyTargetAdmission(WorldObject const* caster,WorldObject* target){
    WorldObject const* _caster=caster;Unit* unitTarget=target?target->ToUnit():nullptr;SpellInfo const* _spellInfo=nullptr;
    switch(0){
''' + native_enemy_check + r'''
    }
    return true;
}
''' + function + r'''
enum ShamanSpells {
    SPELL_SHAMAN_ANGEREDEARTH = 36213,
    SPELL_SHAMAN_FIREBLAST = 57984,
    SPELL_SHAMAN_FIRENOVA = 12470,
    SPELL_SHAMAN_FIRESHIELD = 13376
};
enum ShamanEvents {
    EVENT_SHAMAN_ANGEREDEARTH = 1,
    EVENT_SHAMAN_FIRENOVA = 1,
    EVENT_SHAMAN_FIRESHIELD = 2,
    EVENT_SHAMAN_FIREBLAST = 3
};
constexpr int REACT_PASSIVE=0,EVADE_REASON_NO_HOSTILES=0;
constexpr int IMMUNITY_SCHOOL=0,SPELL_SCHOOL_MASK_NATURE=1,SPELL_SCHOOL_MASK_FIRE=2;
struct EventMap {
    std::vector<uint32> ready;
    void Reset(){ready.clear();}
    void ScheduleEvent(uint32 id,uint32 delay){if(delay==0)ready.push_back(id);}
    void Update(uint32){}
    uint32 ExecuteEvent(){if(ready.empty())return 0;uint32 id=ready.front();ready.erase(ready.begin());return id;}
};
uint32 urand(uint32 min,uint32){return min;}
struct ScriptedAI {
 Creature* me;explicit ScriptedAI(Creature* value):me(value){}
 virtual ~ScriptedAI()=default;
 virtual void Reset(){}
 virtual void UpdateAI(uint32){}
 virtual void AttackStart(Unit* target){me->victim=target;}
 bool IsEngaged()const{return me->engaged;}void EngagementOver(){me->engaged=false;}
 void EnterEvadeMode(int){me->AttackStop();}
 void DoCastVictim(uint32 spell){++me->casts;me->lastSpell=spell;me->lastCastTarget=me->GetVictim();}
 void DoMeleeAttackIfReady(){++me->melee;}
 bool UpdateVictim();
};
''' + victim_update.replace('CreatureAI::', 'ScriptedAI::') + r'''
struct ActualEarthElementalAI : ScriptedAI {
 using ScriptedAI::ScriptedAI;
''' + reset + r'''
''' + attack + r'''
''' + update + r'''
 private:
 EventMap _events;
};
struct ActualFireElementalAI : ScriptedAI {
 using ScriptedAI::ScriptedAI;
''' + reset_second + r'''
''' + attack_second + r'''
''' + update_second + r'''
 private:
 EventMap _events;
};
'''+r'''
static void Reject(Creature& elemental, bool playerOwned = false) {
    assert(!AcquireShamanOwnerVictim(&elemental));
    assert(elemental.ai.attacks == 0);
    assert(elemental.flags == (playerOwned ? UNIT_FLAG_PLAYER_CONTROLLED : 0));
}
int main() {
    Player player;
    player.guid = ObjectGuid(HighGuid::Player, 30010u);
    Register(player);
    Unit target, different;
    Unit nearbyHostile;
    target.hostile = different.hostile = nearbyHostile.hostile = true;
    player.helper = &target;
    Creature direct;
    direct.ownerGuid = player.guid;
    assert(AcquireShamanOwnerVictim(&direct));
    assert(direct.ai.attacks == 1 && direct.ai.target == &target);
    assert(direct.flags == UNIT_FLAG_PLAYER_CONTROLLED && player.helperCalls == 1);

    // An existing victim always wins, even if the helper would choose another.
    player.victim = &target; player.helper = &different; player.helperCalls = 0;
    Creature current; current.ownerGuid = player.guid;
    assert(AcquireShamanOwnerVictim(&current));
    assert(current.ai.attacks == 1 && current.ai.target == &target);
    assert(player.helperCalls == 0);
    for (bool dead : {false, true}) {
        target.alive = !dead; target.valid = dead;
        Creature rejected; rejected.ownerGuid = player.guid;
        Reject(rejected, true);
        assert(player.helperCalls == 0); // no fallback from invalid/dead victim
    }
    target.alive = target.valid = true; player.victim = nullptr;
    for (int failure = 0; failure < 4; ++failure) {
        player.helper = failure == 0 ? nullptr : &target;
        player.engaged = failure != 1;
        target.alive = failure != 2; target.valid = failure != 3;
        Creature rejected; rejected.ownerGuid = player.guid;
        Reject(rejected, true);
    }
    player.engaged = target.alive = target.valid = true;
    player.helper = &target;
    Totem totem; totem.guid = ObjectGuid(HighGuid::Unit, 154390u); totem.entry = 15439; totem.nativeOwner = &player;
    Register(totem);
    assert(static_cast<Unit*>(&totem)->GetOwner() == nullptr);
    assert(totem.GetOwner() == &player);
    TempSummon chained; chained.summoner = &totem;
    assert(AcquireShamanOwnerVictim(&chained));
    assert(chained.ai.attacks == 1 && chained.ai.target == &target);
    assert(chained.flags == UNIT_FLAG_PLAYER_CONTROLLED);
    TempSummon summoned; summoned.summoner = &player;
    assert(AcquireShamanOwnerVictim(&summoned));
    assert(summoned.ai.attacks == 1);
    Creature ownerless; Reject(ownerless);
    TempSummon orphan; Reject(orphan);
    totem.nativeOwner = nullptr;
    TempSummon ownerlessTotem; ownerlessTotem.summoner = &totem; Reject(ownerlessTotem);
    assert(!AcquireShamanOwnerVictim(nullptr));
    Unit npc; npc.guid = ObjectGuid(HighGuid::Unit, 9000u); npc.type = 3; npc.helper = &target;
    Register(npc);
    Creature npcElemental; npcElemental.ownerGuid = npc.guid;
    assert(AcquireShamanOwnerVictim(&npcElemental));
    assert(npcElemental.ai.attacks == 1 && npcElemental.flags == 0);

    // No acquisition claim on an actual AI binding refusal.
    Creature refused;refused.ownerGuid=player.guid;refused.ai.reject=true;
    assert(!AcquireShamanOwnerVictim(&refused)&&!refused.victim);
    using namespace BotRaidAreaAuthority;
    auto key=player.GetGUID().GetRawValue();player.victim=nullptr;
    Creature parasite,body,head,allowed;
    parasite.entry=41806;parasite.guid=ObjectGuid(HighGuid::Unit,41806u,191u);
    body.entry=41570;body.guid=ObjectGuid(HighGuid::Unit,41570u,39u);
    head.entry=42347;head.guid=ObjectGuid(HighGuid::Unit,42347u,76u);
    allowed.entry=42321;allowed.guid=ObjectGuid(HighGuid::Unit,42321u,192u);
    CombatRef parasiteRef{&parasite},bodyRef{&body},headRef{&head},allowedRef{&allowed};
    player.helper=&parasite;player.combat.pve={{0,&parasiteRef},{1,&allowedRef},{2,&headRef},{3,&bodyRef}};
    Creature evolving;evolving.ownerGuid=player.guid;
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&parasite);evolving.casting=true;
    SetCurrentEncounterRestrictions(key,{41806,42321},{allowed.guid.GetRawValue()});
    StopShamanProtectedVictim(&evolving);assert(!evolving.victim&&!evolving.casting&&evolving.interrupts==1);
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&body);
    // Reverse reference iteration: same ordinary winner by raw GUID, not hash order.
    std::reverse(player.combat.pve.begin(),player.combat.pve.end());evolving.AttackStop();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&body);
    SetProtectedEncounterEntries(key,{41570});evolving.AttackStop();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&head);
    SetProtectedEncounterEntries(key,{41570,42347});evolving.AttackStop();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&allowed);
    // Explicit legal owner victim still wins over fallback refs.
    SetProtectedEncounterEntries(key,{});player.victim=&allowed;evolving.AttackStop();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&allowed);player.victim=nullptr;
    // Suppressed refs provide no authority; all illegal refs fail closed.
    bodyRef.suppressed=headRef.suppressed=allowedRef.suppressed=true;evolving.AttackStop();
    assert(!AcquireShamanOwnerVictim(&evolving)&&!evolving.victim);
    bodyRef.suppressed=false;player.combat.pvp={{1,&bodyRef}};player.combat.pve.clear();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&body);
    SetAllOffenseSuppressed(key,true);evolving.casting=true;StopShamanProtectedVictim(&evolving);
    assert(!evolving.victim&&!evolving.casting&&!AcquireShamanOwnerVictim(&evolving));
    Clear(key);
    // The native reaction contract rejects a same-raid controlled wolf, while
    // its duel state remains a lawful hostile exception.
    totem.nativeOwner=&player;
    Player wolfOwner;wolfOwner.guid=ObjectGuid(HighGuid::Player,30011u);Register(wolfOwner);
    player.raidId=17;wolfOwner.raidId=17;
    FactionTemplateEntry fireFaction,wolfFaction;
    Unit wolf;wolf.guid=ObjectGuid(HighGuid::Unit,8959u);wolf.hostile=true;
    wolf.flags=UNIT_FLAG_PLAYER_CONTROLLED;wolf.ownerGuid=wolfOwner.guid;wolf.faction=&wolfFaction;Register(wolf);
    TempSummon nativeFire;nativeFire.guid=ObjectGuid(HighGuid::Unit,15438u);nativeFire.entry=15438;
    nativeFire.guardian=true;nativeFire.summoner=&totem;nativeFire.ownerGuid=totem.guid;
    nativeFire.faction=&fireFaction;Register(nativeFire);
    // Historical accessor result: this is the recorded pre-fix counterexample.
    assert(HistoricalGetAffectingPlayer(&nativeFire)==nullptr);
    InitializeShamanElementalPlayerControlled(&nativeFire);
    assert(nativeFire.GetAffectingPlayer()==&player);
    assert(nativeFire.GetReactionTo(&wolf)==REP_FRIENDLY);
    assert(!NativeEnemyTargetAdmission(&nativeFire,&wolf));
    player.reputation.forced=true;player.reputation.rank=REP_HOSTILE;
    assert(nativeFire.GetReactionTo(&wolf)==REP_HOSTILE);
    player.reputation.forced=false;
    Player::DuelInfo playerDuel{&wolfOwner,1},wolfDuel{&player,1};
    player.duel=&playerDuel;wolfOwner.duel=&wolfDuel;
    assert(nativeFire.GetReactionTo(&wolf)==REP_HOSTILE);
    assert(NativeEnemyTargetAdmission(&nativeFire,&wolf));
    player.reputation.forced=true;player.reputation.rank=REP_FRIENDLY;
    assert(nativeFire.GetReactionTo(&wolf)==REP_FRIENDLY);
    assert(!NativeEnemyTargetAdmission(&nativeFire,&wolf));
    player.reputation.forced=false;
    player.duel=nullptr;wolfOwner.duel=nullptr;
    assert(NativeEnemyTargetAdmission(&nativeFire,&nearbyHostile));

    // Exact owner-chain guards retain ordinary, NPC, unresolved, and special
    // charmer paths around the narrow 15438 -> 15439 fallback.
    assert(player.GetAffectingPlayer()==&player);
    TempSummon playerPet;playerPet.ownerGuid=player.guid;
    assert(playerPet.GetAffectingPlayer()==&player);
    Creature directGuardian;directGuardian.guardian=true;directGuardian.entry=15352;directGuardian.ownerGuid=player.guid;
    assert(directGuardian.GetAffectingPlayer()==&player);
    Creature npcGuardian;npcGuardian.guardian=true;npcGuardian.entry=15438;npcGuardian.ownerGuid=npc.guid;
    assert(npcGuardian.GetAffectingPlayer()==nullptr);
    Creature ownerlessObject;assert(ownerlessObject.GetAffectingPlayer()==nullptr);
    Creature unresolvedOwner;unresolvedOwner.ownerGuid=ObjectGuid(HighGuid::Unit,999999u);
    assert(unresolvedOwner.GetAffectingPlayer()==nullptr);
    Totem hiddenNull;hiddenNull.guid=ObjectGuid(HighGuid::Unit,154391u);hiddenNull.entry=15439;hiddenNull.nativeOwner=nullptr;Register(hiddenNull);
    TempSummon nullFire;nullFire.guardian=true;nullFire.entry=15438;nullFire.ownerGuid=hiddenNull.guid;
    assert(nullFire.GetAffectingPlayer()==nullptr);
    Totem hiddenNpc;hiddenNpc.guid=ObjectGuid(HighGuid::Unit,154392u);hiddenNpc.entry=15439;hiddenNpc.nativeOwner=&npc;Register(hiddenNpc);
    TempSummon npcFire;npcFire.guardian=true;npcFire.entry=15438;npcFire.ownerGuid=hiddenNpc.guid;
    assert(npcFire.GetAffectingPlayer()==nullptr);
    Creature wrongGuardian;wrongGuardian.guardian=true;wrongGuardian.entry=999;wrongGuardian.ownerGuid=totem.guid;
    assert(wrongGuardian.GetAffectingPlayer()==nullptr);
    Totem wrongTotem;wrongTotem.guid=ObjectGuid(HighGuid::Unit,154393u);wrongTotem.entry=999;wrongTotem.nativeOwner=&player;Register(wrongTotem);
    TempSummon wrongTotemFire;wrongTotemFire.guardian=true;wrongTotemFire.entry=15438;wrongTotemFire.ownerGuid=wrongTotem.guid;
    assert(wrongTotemFire.GetAffectingPlayer()==nullptr);
    Creature nonGuardian;nonGuardian.entry=15438;nonGuardian.ownerGuid=totem.guid;
    assert(nonGuardian.GetAffectingPlayer()==nullptr);
    Player charmer;charmer.guid=ObjectGuid(HighGuid::Player,30012u);Register(charmer);
    TempSummon charmedFire;charmedFire.guardian=true;charmedFire.entry=15438;charmedFire.ownerGuid=totem.guid;
    charmedFire.charmed=true;charmedFire.charmer=&charmer;charmedFire.charmerGuid=charmer.guid;
    assert(charmedFire.GetAffectingPlayer()==&charmer);
    Totem explicitTotem;explicitTotem.guid=ObjectGuid(HighGuid::Unit,154394u);explicitTotem.entry=15439;explicitTotem.nativeOwner=&player;
    explicitTotem.ownerGuid=npc.guid;Register(explicitTotem);
    TempSummon explicitFire;explicitFire.guardian=true;explicitFire.entry=15438;explicitFire.ownerGuid=explicitTotem.guid;
    assert(explicitFire.GetAffectingPlayer()==nullptr);
    Totem explicitPlayerTotem;explicitPlayerTotem.guid=ObjectGuid(HighGuid::Unit,154396u);explicitPlayerTotem.entry=15439;
    explicitPlayerTotem.nativeOwner=&player;explicitPlayerTotem.ownerGuid=wolfOwner.guid;Register(explicitPlayerTotem);
    TempSummon explicitPlayerFire;explicitPlayerFire.guardian=true;explicitPlayerFire.entry=15438;
    explicitPlayerFire.ownerGuid=explicitPlayerTotem.guid;
    assert(explicitPlayerFire.GetAffectingPlayer()==&wolfOwner);
    Totem charmedTotem;charmedTotem.guid=ObjectGuid(HighGuid::Unit,154395u);charmedTotem.entry=15439;charmedTotem.nativeOwner=&player;
    charmedTotem.charmed=true;charmedTotem.charmer=&npc;charmedTotem.charmerGuid=npc.guid;Register(charmedTotem);
    TempSummon charmedTotemFire;charmedTotemFire.guardian=true;charmedTotemFire.entry=15438;
    charmedTotemFire.ownerGuid=charmedTotem.guid;
    assert(charmedTotemFire.GetAffectingPlayer()==nullptr);

    // Execute both production Reset/UpdateAI bodies.  A pre-existing lawful
    // victim exercises the UpdateVictim short circuit; a same-raid victim is
    // stopped by native validity before it can receive a spell.
    TempSummon chainedUpdate;chainedUpdate.summoner=&totem;chainedUpdate.ownerGuid=totem.guid;
    chainedUpdate.guardian=true;chainedUpdate.entry=15438;
    chainedUpdate.victim=&wolf;chainedUpdate.selected=&wolf;
    ActualEarthElementalAI earth(&chainedUpdate);
    chainedUpdate.ai.dispatch=[&](Unit* target){earth.AttackStart(target);};
    earth.Reset();assert(chainedUpdate.flags==UNIT_FLAG_PLAYER_CONTROLLED);
    player.helper=&body;bodyRef.suppressed=false;player.victim=nullptr;
    earth.UpdateAI(1);
    assert(chainedUpdate.victim==&body&&chainedUpdate.lastCastTarget==&body);
    assert(chainedUpdate.melee==1);

    TempSummon fireSummon;fireSummon.summoner=&totem;fireSummon.ownerGuid=totem.guid;
    fireSummon.guardian=true;fireSummon.entry=15438;
    fireSummon.victim=&nearbyHostile;fireSummon.selected=&nearbyHostile;
    ActualFireElementalAI fire(&fireSummon);
    fireSummon.ai.dispatch=[&](Unit* target){fire.AttackStart(target);};
    fire.Reset();assert(fireSummon.flags==UNIT_FLAG_PLAYER_CONTROLLED);
    fire.UpdateAI(1);
    assert(fireSummon.lastSpell==SPELL_SHAMAN_FIRESHIELD);
    assert(fireSummon.lastCastTarget==&nearbyHostile);
    fire.AttackStart(nullptr);assert(fireSummon.victim==&nearbyHostile);

    // Existing friendly victim, protected target, and offense suppression all
    // fail closed; ordinary hostile acquisition remains available.
    fireSummon.victim=&wolf;fireSummon.selected=&wolf;fireSummon.casts=0;fireSummon.melee=0;
    player.helper=&nearbyHostile;player.victim=nullptr;fire.Reset();
    fire.UpdateAI(1);
    assert(fireSummon.victim==&nearbyHostile&&fireSummon.lastCastTarget==&nearbyHostile);
    assert(fireSummon.interrupts==1);
    fire.AttackStart(&wolf);assert(fireSummon.victim==&nearbyHostile);
    SetProtectedEncounterEntries(key,{0});
    fire.AttackStart(&nearbyHostile);assert(fireSummon.victim==&nearbyHostile);
    SetAllOffenseSuppressed(key,true);fire.AttackStart(&nearbyHostile);
    assert(fireSummon.victim==&nearbyHostile);
    Clear(key);

    // NPC-owned elementals retain the native non-player path and do not gain
    // the player-controlled classification.
    TempSummon npcSummon;npcSummon.summoner=&npc;npcSummon.helper=&target;
    ActualEarthElementalAI npcEarth(&npcSummon);npcEarth.Reset();
    assert(npcSummon.flags==0);
    Clear(key);
}
''')
    binary = tmp_path / "elemental_owner"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    "-I", str(ROOT / "src/server/game/Entities/Object"), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
