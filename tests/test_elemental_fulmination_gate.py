from pathlib import Path
import re
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/server/game/Bots"
MIGRATION = ROOT / "sql/custom/world/2026_09_08_03_elemental_fulmination_gate.sql"
ROLLBACK = ROOT / "sql/custom/rollback/world/2026_09_08_03_elemental_fulmination_gate_rollback.sql"


def migrated_row():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE bot_rotation_profile(id INTEGER,class_id INTEGER,spec_tag TEXT,role TEXT,enabled INTEGER);
      INSERT INTO bot_rotation_profile VALUES(1,7,'elemental_shaman','dps',1),(2,7,'elemental_shaman','dps',0),
        (3,8,'elemental_shaman','dps',1),(4,7,'enhancement','dps',1),(5,7,'elemental_shaman','healer',1);
      CREATE TABLE bot_rotation_action(id INTEGER,profile_id INTEGER,spell_id INTEGER,enabled INTEGER,
        required_self_aura INTEGER DEFAULT 0,required_self_aura_stacks INTEGER DEFAULT 0,
        max_self_aura_stacks INTEGER DEFAULT 0,required_owned_target_aura INTEGER DEFAULT 0,
        max_enemies INTEGER DEFAULT 0,mechanic_tags TEXT DEFAULT 'earth_shock,spender,instant',
        priority_bucket INTEGER DEFAULT 1,damage_weight REAL DEFAULT .76,min_range REAL DEFAULT 12,
        max_range REAL DEFAULT 35,target_selector TEXT DEFAULT 'enemy');
      INSERT INTO bot_rotation_action(id,profile_id,spell_id,enabled) VALUES
        (1,1,8042,1),(2,1,8042,0),(3,2,8042,1),(4,3,8042,1),(5,4,8042,1),(6,5,8042,1),(7,1,403,1);
    ''')
    before = [dict(row) for row in db.execute("SELECT * FROM bot_rotation_action ORDER BY id")]
    # SQLite lacks only MariaDB's idempotent column-clause spelling.
    db.executescript(MIGRATION.read_text().replace("IF NOT EXISTS ", ""))
    after = [dict(row) for row in db.execute("SELECT * FROM bot_rotation_action ORDER BY id")]
    new = {"required_self_aura_charges", "max_self_aura_charges", "min_owned_target_aura_remaining_ms"}
    for old, row in zip(before[1:], after[1:]):
        assert {k:v for k,v in row.items() if k not in new} == old
        assert all(row[k] == 0 for k in new)
    for key in ("priority_bucket", "damage_weight", "min_range", "max_range", "target_selector"):
        assert after[0][key] == before[0][key]
    result = after[0]
    assert [result[k] for k in ("required_self_aura", "required_self_aura_stacks", "max_self_aura_stacks",
        "required_self_aura_charges", "max_self_aura_charges", "required_owned_target_aura",
        "min_owned_target_aura_remaining_ms", "max_enemies")] == [324,0,0,9,9,8050,3000,1]
    db.executescript(ROLLBACK.read_text().replace("IF EXISTS ", ""))
    assert [dict(row) for row in db.execute("SELECT * FROM bot_rotation_action ORDER BY id")] == before
    return result


def test_sql_scopes_charge_gate_and_roundtrips():
    migrated_row()


def test_actual_candidate_builder_and_regular_selection_use_charges(tmp_path):
    row = migrated_row()
    source = (BOT / "BotClassSpecActionProfileCandidates.cpp").read_text()
    evaluator = source[source.index("std::string EvaluateCompiledConditions("):source.index("\n}\n\nstd::vector<BotActionCandidate>")]
    builder = source[source.index("std::vector<BotActionCandidate> BotClassSpecActionProfileStore::BuildCandidates("):source.index("\nstd::string BotClassSpecActionProfileStore::CandidateMaskJson")]
    header = re.sub(r'^#include "[^\"]+"\n', '', (BOT / "BotClassSpecActionProfile.h").read_text(), flags=re.M)
    catalog = (BOT / "BotCombatActionCatalog.h").read_text()
    enum = catalog[catalog.index("enum class BotCombatActionCategory"):catalog.index("\nstruct BotCombatActionDefinition")]
    resolver = (BOT / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    comparator = resolver[resolver.index("    auto candidatePreferred ="):resolver.index("    auto hasMechanicTag =")]
    enemy_gate = resolver[resolver.index("        if (candidate.Profile.MinEnemies > hostileCount)"):resolver.index('        if (bot->getClass() == CLASS_DRUID && profile.SpecTag == "balance_druid")')]
    call = re.search(r'    std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates\(bot, target, profile\);', resolver)[0]
    db_source = (BOT / "BotClassSpecActionProfileDb.cpp").read_text()
    validation = db_source[db_source.index("        if ((spell.RequiredSelfAuraStacks"):db_source.index("        if (spell.RequiresPet && spell.ForbidsPet)")]
    setup = '\n'.join(f'spell.{member} = {row[column]};' for column, member in (
        ("required_self_aura","RequiredSelfAura"),("required_self_aura_stacks","RequiredSelfAuraStacks"),
        ("max_self_aura_stacks","MaxSelfAuraStacks"),("required_self_aura_charges","RequiredSelfAuraCharges"),
        ("max_self_aura_charges","MaxSelfAuraCharges"),("required_owned_target_aura","RequiredOwnedTargetAura"),
        ("min_owned_target_aura_remaining_ms","MinOwnedTargetAuraRemainingMs"),("max_enemies","MaxEnemies")))
    cpp = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
using uint8=uint8_t;using uint16=uint16_t;using uint32=uint32_t;using uint64=uint64_t;using int32=int32_t;
#define TC_GAME_API
struct ObjectGuid {uint64 value=0;uint64 GetCounter()const{return value;}bool operator==(ObjectGuid x)const{return value==x.value;}bool operator!=(ObjectGuid x)const{return !(*this==x);}static ObjectGuid const Empty;};
ObjectGuid const ObjectGuid::Empty{};
using Powers=int;using AuraStateType=int;
constexpr int POWER_MANA=0,POWER_HOLY_POWER=1,POWER_SOUL_SHARDS=2,EQUIPMENT_SLOT_MAINHAND=0,EQUIPMENT_SLOT_OFFHAND=1,CURRENT_GENERIC_SPELL=0,CURRENT_CHANNELED_SPELL=1,UNIT_STATE_CASTING=1;
struct Aura {uint8 stacks=1,charges=9;int32 remaining=3000;uint8 GetStackAmount()const{return stacks;}uint8 GetCharges()const{return charges;}int32 GetDuration()const{return remaining;}};
struct SpellInfo {uint32 Id=8042,CasterAuraState=0,CasterAuraStateNot=0,CasterAuraSpell=0,ExcludeCasterAuraSpell=0,TargetAuraState=0,TargetAuraStateNot=0,TargetAuraSpell=0,ExcludeTargetAuraSpell=0;bool NeedsComboPoints()const{return false;}};
struct Spell {SpellInfo const* GetSpellInfo()const{return nullptr;}};
struct History {bool gcd=false,ready=true;bool HasGlobalCooldown(SpellInfo const*)const{return gcd;}bool IsReady(SpellInfo const*)const{return ready;}};
struct Creature;struct Player;
struct Unit {ObjectGuid guid{1};Aura* aura=nullptr;uint32 auraId=8050;ObjectGuid auraOwner{1};
 ObjectGuid GetGUID()const{return guid;}Aura const* GetAura(uint32 id)const{return id==auraId?aura:nullptr;}
 Aura const* GetAura(uint32 id,ObjectGuid owner)const{return owner==auraOwner?GetAura(id):nullptr;}
 bool HasAura(uint32 id)const{return GetAura(id);}bool HasAura(uint32 id,ObjectGuid owner)const{return GetAura(id,owner);}
 bool IsAlive()const{return true;}uint32 GetCreatureTypeMask()const{return 0;}uint32 GetMaxHealth()const{return 100;}uint32 GetHealth()const{return 100;}
 Creature const* ToCreature()const{return nullptr;}Spell const* GetCurrentSpell(int)const{return nullptr;}Unit const* GetVictim()const{return nullptr;}
 bool HasAuraState(int,SpellInfo const*,Player const*)const{return false;}
};
struct Creature:Unit {uint32 GetEntry()const{return 0;}};
struct GroupReference {GroupReference const* next()const{return nullptr;}Player const* GetSource()const{return nullptr;}};
struct Group {GroupReference const* GetFirstMember()const{return nullptr;}};
struct Player:Unit {History history;bool casting=false,moving=false,inRange=true,power=true;
 ObjectGuid GetComboTarget()const{return {};}uint8 GetComboPoints()const{return 0;}uint8 GetShapeshiftForm()const{return 0;}Unit const* GetPet()const{return nullptr;}
 uint32 GetPower(int)const{return 100;}uint32 GetMaxPower(int)const{return 100;}Powers GetPowerType()const{return 0;}std::set<int> getAttackers()const{return {};}
 bool isMoving()const{return moving;}Group const* GetGroup()const{return nullptr;}History const* GetSpellHistory()const{return &history;}
 bool HasUnitState(int)const{return casting;}bool IsWithinMeleeRange(Unit const*)const{return inRange;}float GetExactDist(Unit const*)const{return 15;}
 bool IsWithinDistInMap(Unit const*,float)const{return inRange;}
};
ENUM
HEADER
struct BotCombatActionCatalog {static uint32 StableActionId(BotCombatActionCategory,uint32 id){return id;}};
struct Manager {SpellInfo es,lb;Manager(){lb.Id=403;}SpellInfo const* GetSpellInfo(uint32 id)const{return id==8042?&es:&lb;}} manager;
auto sSpellMgr=&manager;
struct ReadyRuneObservation {uint8 Total=0,Blood=0,Unholy=0,Frost=0,Death=0;};
ReadyRuneObservation ObserveReadyRunes(Player const*){return {};}
uint8 ReadyRuneCount(Player const*){return 0;}uint32 EquippedTemporaryEnchant(Player const*,uint8){return 0;}
bool HasMechanicTag(std::string const& tags,char const* key){return tags.find(key)!=std::string::npos;}
bool MaintainedAuraBlocksRefresh(Unit const*,uint32,uint32){return false;}
bool IsPostPeriodicTickInterruptWindow(Player const*,Unit const*,uint32,uint32){return false;}
uint32 ProfileSpellCastTimeMs(Player const*,SpellInfo const*){return 0;}
float ProfileSpellMaximumRange(Player const*,Unit const*,SpellInfo const*){return 35;}
bool HasEnoughPowerForProfileSpell(Player const* p,SpellInfo const*){return p->power;}
bool FindOnUseItemForSpell(Player const*,uint32){return true;}
namespace BotClassSpecActionProfileDetail {char const* PowerName(int){return "mana";}}
uint32 BotClassSpecActionProfileStore::ReactionTimeMsForSpec(char const*){return 0;}
EVALUATOR
BUILDER
// Bounded regular rotation path: actual BuildCandidates caller, enemy gates,
// and priority comparator; density/encounter policies are outside this fixture.
uint32 resolve(Player const* bot,Unit const* target,BotClassSpecActionProfile const& profile,uint32 hostileCount){
CALL
COMPARATOR
 BotActionCandidate const* best=nullptr;
 for(auto& candidate:candidates){
  if(!candidate.RejectReason.empty())continue;
ENEMY
  if(candidatePreferred(candidate,best))best=&candidate;
 }
 return best?best->SpellId:0;
}
bool valid(BotActionProfileSpell const& spell){std::set<std::string> invalidReasons;std::string key="test";
VALIDATION
 return invalidReasons.empty();}
int main(){Player bot;Unit target;Aura shield,flame;bot.aura=&shield;bot.auraId=324;target.aura=&flame;
 BotActionProfileSpell spell;spell.SpellId=8042;spell.PriorityBucket=1;spell.DamageWeight=.76;
SETUP
 BotActionProfileSpell filler;filler.SpellId=403;filler.PriorityBucket=3;filler.DamageWeight=.80;
 BotClassSpecActionProfile profile;profile.SpecTag="elemental_shaman";profile.Spells={spell,filler};
 auto chosen=[&](uint32 n=1){return resolve(&bot,&target,profile,n);};
 assert(chosen()==8042);assert(chosen(2)==403);
 for(int c=0;c<=10;++c){shield.charges=c;assert(chosen()==(c==9?8042:403));}
 shield.stacks=9;shield.charges=3;assert(chosen()==403);shield.stacks=1;shield.charges=9;
 bot.aura=nullptr;assert(chosen()==403);bot.aura=&shield;
 target.aura=nullptr;assert(chosen()==403);target.aura=&flame;target.auraOwner.value=2;assert(chosen()==403);target.auraOwner.value=1;
 flame.remaining=2999;assert(chosen()==403);flame.remaining=3000;assert(chosen()==8042);flame.remaining=5000;assert(chosen()==8042);flame.remaining=-1;assert(chosen()==8042);
 bot.history.gcd=true;assert(chosen()==0);bot.history.gcd=false;bot.history.ready=false;assert(chosen()==0);bot.history.ready=true;
 bot.casting=true;assert(chosen()==0);bot.casting=false;bot.inRange=false;assert(chosen()==0);bot.inRange=true;bot.power=false;assert(chosen()==0);bot.power=true;
 // Existing stack gates remain stack-based and unrelated new fields default off.
 auto legacy=spell;legacy.RequiredSelfAuraCharges=legacy.MaxSelfAuraCharges=0;legacy.RequiredSelfAuraStacks=9;assert(!EvaluateCompiledConditions(&bot,&target,&target,legacy).empty());
 assert(valid(spell));assert(valid(filler));auto invalid=spell;invalid.RequiredSelfAura=0;assert(!valid(invalid));
 invalid=spell;invalid.RequiredSelfAuraCharges=10;assert(!valid(invalid));invalid=spell;invalid.RequiredOwnedTargetAura=0;assert(!valid(invalid));
 invalid=spell;invalid.MaxSelfAuraCharges=0;assert(valid(invalid));invalid=spell;invalid.RequiredSelfAuraCharges=0;assert(valid(invalid));
 assert(filler.RequiredSelfAuraCharges==0 && filler.MaxSelfAuraCharges==0 && filler.MinOwnedTargetAuraRemainingMs==0);
}
'''
    for marker,value in {'ENUM':enum,'HEADER':header,'EVALUATOR':evaluator,'BUILDER':builder,'CALL':call,'COMPARATOR':comparator,'ENEMY':enemy_gate,'SETUP':setup,'VALIDATION':validation}.items():
        cpp=cpp.replace(marker,value)
    path=tmp_path/'fixture.cpp';path.write_text(cpp);binary=tmp_path/'fixture'
    result=subprocess.run(['c++','-std=c++17',str(path),'-o',str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    subprocess.run([str(binary)],check=True)


def test_charge_columns_keep_select_load_snapshot_and_dump_identity():
    source = (BOT / "BotClassSpecActionProfileDb.cpp").read_text()
    query = source[source.index('"SELECT p.id'):source.index('"FROM bot_rotation_profile p')]
    columns = re.findall(r'\b[pa]\.([a-z_]+)', query)
    assert len(columns) == 80
    for column, member, index, kind in (
        ('required_self_aura_charges', 'RequiredSelfAuraCharges', 77, 'UInt8'),
        ('max_self_aura_charges', 'MaxSelfAuraCharges', 78, 'UInt8'),
        ('min_owned_target_aura_remaining_ms', 'MinOwnedTargetAuraRemainingMs', 79, 'UInt32'),
    ):
        assert columns[index] == column
        assert f'spell.{member} = fields[{index}].Get{kind}();' in source
        assert f'spell.{member}' in source[source.index('std::string SnapshotPayload'):source.index('std::shared_ptr<DbRotationSnapshot> Load')]
        assert '\\"' + column + '\\":' in source
    # Appending fields preserves every prior SELECT index, including the prior
    # hostile-health gate at76; no shifted trailing field silently changes type.
    assert columns[76] == 'min_hostile_target_health_pct'
