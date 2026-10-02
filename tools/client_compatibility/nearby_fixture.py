"""Stage two owned players nearby without restarting the private worldserver."""
import json,time
from . import lab_runtime as lab


class NearbyFixture:
    def __init__(self,out,primary,peer,open_ground=False):
        if (primary['guid'],peer['guid'])!=(1,2):raise ValueError('requires the registered primary and scout')
        self.out,self.primary,self.peer=out,primary,peer
        self.rows=[];self.before=None
        self.open_ground=open_ground

    def prepare(self):
        lab.server_command('saveall');time.sleep(1)
        with lab.connection() as con,con.cursor() as cur:
            cur.execute('SELECT guid,account,name,position_x,position_y,position_z,orientation,map '
                'FROM client442_characters.characters WHERE guid IN (1,2) ORDER BY guid')
            rows=cur.fetchall()
            if len(rows)!=2 or any(tuple(r[:3])!=(f['guid'],f['account_id'],f['character_name'])
                for r,f in zip(rows,[self.primary,self.peer])):raise RuntimeError('nearby fixture account binding mismatch')
            self.before={r[0]:r for r in rows}
            names=['TC442NearbyRestore','TC442NearbyPeer']
            sources=[rows[0][3:],rows[1][3:]]
            if self.open_ground:
                names.append('TC442NearbyScoutRestore');sources.append(rows[1][3:])
                sources[1]=(-8921.09,-119.135,82.195,0,0)
            cur.execute('SELECT id FROM client442_world.game_tele WHERE name IN ('+','.join(['%s']*len(names))+')',names)
            if cur.fetchone():raise RuntimeError('an earlier nearby fixture needs cleanup')
            cur.execute('SELECT MAX(id) FROM client442_world.game_tele');start=cur.fetchone()[0]+1
            for i,(name,source) in enumerate(zip(names,sources)):
                row=(start+i,*source,name)
                cur.execute('INSERT INTO client442_world.game_tele '
                    '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',row)
                self.rows.append(row)
        lab.private_write(self.out/'nearby_fixture.json',json.dumps({'source':'code_fixture_native_console',
            'before':self.before,'temporary_teleports':self.rows,'native_worldserver':{
                k:lab.owned_process('worldserver')[k] for k in ['pid','start_ticks']}},indent=2)+'\n')
        lab.server_command('reload game_tele');time.sleep(.5)
        lab.server_command('tele name Harnessone TC442NearbyPeer');time.sleep(4)
        if self.open_ground:
            lab.server_command('tele name Harnesstwo TC442NearbyPeer');time.sleep(4)

    def restore(self):
        if not self.rows:return
        lab.server_command('tele name Harnessone TC442NearbyRestore');time.sleep(4)
        if self.open_ground:
            lab.server_command('tele name Harnesstwo TC442NearbyScoutRestore');time.sleep(4)
        lab.server_command('saveall');time.sleep(1)
        restored={}
        with lab.connection() as con,con.cursor() as cur:
            for guid in ([1,2] if self.open_ground else [1]):
                cur.execute('SELECT position_x,position_y,position_z,orientation,map '
                    'FROM client442_characters.characters WHERE guid=%s',(guid,));position=cur.fetchone()
                if any(abs(a-b)>.01 for a,b in zip(position,self.before[guid][3:])):
                    raise RuntimeError('nearby fixture position restoration failed; preserving restore teleport')
                restored[guid]=position
            for row in self.rows:
                cur.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],));found=cur.fetchone()
                if found!=row:raise RuntimeError('temporary teleport changed; refusing deletion')
                cur.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
        lab.server_command('reload game_tele')
        lab.private_write(self.out/'nearby_restoration.json',json.dumps({'positions':restored,
            'temporary_teleports_removed':[row[0] for row in self.rows]},indent=2)+'\n')
