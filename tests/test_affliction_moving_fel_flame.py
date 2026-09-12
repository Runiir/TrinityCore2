from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/'sql/custom/world/2026_09_12_02_affliction_moving_fel_flame.sql'
ROLLBACK=ROOT/'sql/custom/rollback/world/2026_09_12_02_affliction_moving_fel_flame_rollback.sql'


def test_additive_moving_fallback_preserves_proc_and_other_profiles():
    db=sqlite3.connect(':memory:')
    db.row_factory=sqlite3.Row
    db.executescript('''
    CREATE TABLE bot_rotation_profile(id INTEGER,class_id INTEGER,spec_tag TEXT,role TEXT,enabled INTEGER);
    INSERT INTO bot_rotation_profile VALUES
      (1,9,'affliction_warlock','dps',1),(2,9,'affliction_warlock','dps',0),
      (3,8,'affliction_warlock','dps',1),(4,9,'demonology_warlock','dps',1),
      (5,9,'affliction_warlock','healer',1);
    CREATE TABLE bot_rotation_action(id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER,
      sort_order INTEGER, spell_id INTEGER,category TEXT,mechanic_tags TEXT,
      damage_weight REAL,priority_bucket INTEGER,min_enemies INTEGER,max_enemies INTEGER,
      target_selector TEXT,movement_directive TEXT,auto_attack_mode TEXT,
      min_range REAL,max_range REAL,requires_moving INTEGER DEFAULT 0,
      required_self_aura INTEGER DEFAULT 0,requires_stationary INTEGER DEFAULT 0,
      enabled INTEGER DEFAULT 1);
    ''')
    for profile in range(1,6):
        db.execute('''INSERT INTO bot_rotation_action
        (profile_id,sort_order,spell_id,category,mechanic_tags,damage_weight,priority_bucket,
        min_enemies,max_enemies,target_selector,movement_directive,auto_attack_mode,min_range,max_range,
        required_self_aura) VALUES(?,80,77799,'spender','fel_flame,proc,apl_priority_8',.82,8,
        1,0,'enemy','ranged','none',0,35,89937)''',(profile,))
    query='SELECT * FROM bot_rotation_action ORDER BY id'
    before=[dict(r) for r in db.execute(query)]
    db.executescript(SQL.read_text())
    after=[dict(r) for r in db.execute(query)]
    assert after[:len(before)]==before
    assert len(after)==len(before)+1
    row=after[-1]
    assert row['profile_id']==1 and row['spell_id']==77799
    assert row['requires_moving']==1 and row['requires_stationary']==0
    assert row['required_self_aura']==0 and row['enabled']==1
    assert row['priority_bucket']==14 and row['sort_order']==140
    assert row['priority_bucket']>before[0]['priority_bucket']
    assert (row['min_range'],row['max_range'])==(0,40)
    assert row['target_selector']=='enemy' and row['max_enemies']==0
    db.executescript(SQL.read_text())
    assert [dict(r) for r in db.execute(query)]==after
    db.executescript(ROLLBACK.read_text())
    assert [dict(r) for r in db.execute(query)]==before
