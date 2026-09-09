"""Execute the native proc filter/handler with deterministic event adapters."""
import re
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_09_01_hunter_wild_quiver_hit_phase.sql"
ROLLBACK = ROOT / "sql/custom/rollback/world/2026_09_09_01_hunter_wild_quiver_hit_phase_rollback.sql"


def _database():
    db = sqlite3.connect(":memory:")
    # Exact implicated row settings; neighboring rows and non-phase fields are
    # sentinels. DBC defaults resolve ProcFlags=0 to 0x140 and Chance=0 to 100.
    db.execute("CREATE TABLE spell_proc (SpellID INT, SpellPhaseMask INT, "
               "SpellFamilyName INT, ProcFlags INT, SpellTypeMask INT, "
               "DisableEffectsMask INT, Chance INT)")
    db.executemany("INSERT INTO spell_proc VALUES (?, ?, 9, 0, 1, 2, 0)",
                   [(76659, 1), (76658, 1), (76663, 2)])
    return db


def test_migration_is_one_field_idempotent_and_rollback_exact():
    db = _database()
    before = db.execute("SELECT * FROM spell_proc ORDER BY SpellID").fetchall()
    sql = MIGRATION.read_text()
    db.executescript(sql)
    after = db.execute("SELECT * FROM spell_proc ORDER BY SpellID").fetchall()
    assert after == [tuple([r[0], 2, *r[2:]]) if r[0] == 76659 else r for r in before]
    db.executescript(sql)
    assert db.execute("SELECT * FROM spell_proc ORDER BY SpellID").fetchall() == after
    db.executescript(ROLLBACK.read_text())
    assert db.execute("SELECT * FROM spell_proc ORDER BY SpellID").fetchall() == before
    db.executescript(ROLLBACK.read_text())
    assert db.execute("SELECT * FROM spell_proc ORDER BY SpellID").fetchall() == before
    # SQL cannot add, delete, or overwrite unspecified settings.
    for path, new, old in ((MIGRATION, 2, 1), (ROLLBACK, 1, 2)):
        statement = re.sub(r"--[^\n]*", "", path.read_text()).strip()
        assert re.fullmatch(rf"UPDATE `spell_proc` SET `SpellPhaseMask` = {new}\s+"
                            rf"WHERE `SpellID` = 76659 AND `SpellPhaseMask` = {old};", statement)
    db.execute("UPDATE spell_proc SET SpellPhaseMask=4 WHERE SpellID=76659")
    db.executescript(sql)
    db.executescript(ROLLBACK.read_text())
    assert db.execute("SELECT SpellPhaseMask FROM spell_proc WHERE SpellID=76659").fetchone() == (4,)


def _body(source, signature):
    start = source.index("{", source.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_native_filter_and_target_handler_cross_cast_to_hit(tmp_path):
    mgr = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "src/server/game/Spells").glob("SpellMgr*.cpp")))
    header = (ROOT / "src/server/game/Spells/SpellMgr.h").read_text()
    hunter = (ROOT / "src/server/scripts/Spells/spell_hunter.cpp").read_text()
    spell = (ROOT / "src/server/game/Spells/Spell.cpp").read_text()
    assert re.search(r"SPELL_HUNTER_WILD_QUIVER_DAMAGE\s*=\s*76663", hunter)
    assert "procEntry.ProcFlags = ProcFlags(spellInfo->ProcFlags);" in mgr
    assert "procEntry.Chance = static_cast<float>(spellInfo->ProcChance);" in mgr
    # Bind the deterministic adapters below to the two actual event producers.
    assert "ProcSkillsAndAuras(m_originalCaster, nullptr, procAttacker, PROC_FLAG_NONE, PROC_SPELL_TYPE_MASK_ALL, PROC_SPELL_PHASE_CAST" in spell
    assert "ProcSkillsAndAuras(caster, spell->unitTarget, procAttacker, procVictim, procSpellType, PROC_SPELL_PHASE_HIT" in spell
    enums = "\n".join(re.search(r"enum " + name + r"\s*:\s*uint32\s*\{.*?\};", header, re.S).group()
                      for name in ("ProcFlags", "ProcFlagsSpellType", "ProcFlagsSpellPhase", "ProcFlagsHit", "ProcAttributes"))
    filter_body = _body(mgr, "bool SpellMgr::CanSpellTriggerProcOnEvent(")
    handler_body = _body(hunter[hunter.index("class spell_hun_wild_quiver"):], "void HandleEffectProc(")
    db = _database()
    db.executescript(MIGRATION.read_text())
    phase = db.execute("SELECT SpellPhaseMask FROM spell_proc WHERE SpellID=76659").fetchone()[0]
    source = tmp_path / "wild_quiver.cpp"
    source.write_text('''
#include <cassert>
#include <cstdint>
#include <initializer_list>
using uint32 = uint32_t;
''' + enums + '''
struct AuraEffect {};
struct Player;
struct Unit {
    int casts=0; Unit* last=nullptr;
    Player* ToPlayer() { return nullptr; }
    void CastSpell(Unit* target, int id, AuraEffect const*) {
        assert(id==76663); ++casts; last=target;
    }
};
struct Player : Unit { bool isHonorOrXPTarget(Unit*) { return true; } };
struct SpellInfo {
    int ManaCost=0, ManaCostPercentage=0;
    bool IsAffected(uint32, uint32) const { return true; }
};
struct SpellProcEntry {
    uint32 ProcFlags=0x140, AttributesMask=0, SchoolMask=0;
    uint32 SpellFamilyName=9, SpellFamilyMask=0, SpellTypeMask=1;
    uint32 SpellPhaseMask=1, HitMask=0;
};
struct ProcEventInfo {
    Unit* actor; Unit* target; uint32 type, phase, hit=PROC_HIT_NORMAL;
    uint32 GetTypeMask() { return type; }
    Unit* GetActor() { return actor; }
    Unit* GetActionTarget() { return target; }
    SpellInfo const* GetSpellInfo() { static SpellInfo info; return &info; }
    uint32 GetSchoolMask() { return 1; }
    uint32 GetSpellTypeMask() { return PROC_SPELL_TYPE_DAMAGE; }
    uint32 GetSpellPhaseMask() { return phase; }
    uint32 GetHitMask() { return hit; }
};
struct SpellMgr {
    static bool CanSpellTriggerProcOnEvent(SpellProcEntry const& procEntry, ProcEventInfo& eventInfo)
''' + filter_body + '''
};
constexpr int SPELL_HUNTER_WILD_QUIVER_DAMAGE=76663;
struct Handler {
    Unit* caster;
    Unit* GetCaster() { return caster; }
    void PreventDefaultAction() {}
    void HandleEffectProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
''' + handler_body + '''
};
int main() {
    Unit caster, target; Handler handler{&caster};
    for (uint32 type : {uint32(PROC_FLAG_DEAL_RANGED_ATTACK), uint32(PROC_FLAG_DEAL_RANGED_ABILITY)}) {
        SpellProcEntry entry;
        ProcEventInfo cast{&caster, nullptr, type, PROC_SPELL_PHASE_CAST};
        ProcEventInfo hit{&caster, &target, type, PROC_SPELL_PHASE_HIT};
        caster.casts=0;
        assert(SpellMgr::CanSpellTriggerProcOnEvent(entry, cast));
        handler.HandleEffectProc(nullptr, cast);
        assert(caster.casts==0);
        assert(!SpellMgr::CanSpellTriggerProcOnEvent(entry, hit));
        entry.SpellPhaseMask=''' + str(phase) + ''';
        assert(!SpellMgr::CanSpellTriggerProcOnEvent(entry, cast));
        assert(SpellMgr::CanSpellTriggerProcOnEvent(entry, hit));
        handler.HandleEffectProc(nullptr, hit);
        assert(caster.casts==1 && caster.last==&target);
        hit.hit=PROC_HIT_CRITICAL;
        assert(SpellMgr::CanSpellTriggerProcOnEvent(entry, hit));
        hit.hit=PROC_HIT_MISS;
        assert(!SpellMgr::CanSpellTriggerProcOnEvent(entry, hit));
        hit.hit=PROC_HIT_NORMAL; hit.type=PROC_FLAG_DEAL_MELEE_SWING;
        assert(!SpellMgr::CanSpellTriggerProcOnEvent(entry, hit));
    }
}
''')
    # Compile only extracted unmodified native methods with event/storage stubs;
    # no worldserver build, RNG simulation, or claimed damage amount.
    binary = tmp_path / "wild_quiver"
    subprocess.run(["c++", "-std=c++17", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
