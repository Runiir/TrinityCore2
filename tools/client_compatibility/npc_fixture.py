"""Reversible staging beside a verified existing NPC in the isolated database."""
import json,math,re,time
from . import lab_runtime as lab


class NpcFixture:
    def __init__(self,out,player,entry,flag):
        if (player['guid'],player['account_id'],player['character_name'])!=(1,1,'Harnessone'):
            raise ValueError('NPC fixture requires the registered primary actor')
        self.out,self.player,self.entry,self.flag=out,player,entry,flag
        self.rows=[];self.before=None;self.npc=None

    def prepare(self):
        lab.server_command('saveall');time.sleep(1)
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT guid,account,name,position_x,position_y,position_z,orientation,map '
                'FROM client442_characters.characters WHERE guid=1');self.before=q.fetchone()
            if self.before[:3]!=(1,1,'Harnessone'):raise RuntimeError('owned character binding changed')
            q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
                'COALESCE(c.npcflag,t.npcflag),c.MovementType FROM client442_world.creature c '
                'JOIN client442_world.creature_template t ON c.id=t.entry WHERE c.id=%s AND c.map=0 ORDER BY c.guid',(self.entry,))
            rows=q.fetchall()
            if len(rows)!=1 or not rows[0][8]&self.flag or rows[0][9]!=0:
                raise RuntimeError('requires one stationary NPC with the requested service flag')
            self.npc=rows[0]
            if not re.fullmatch(r"[A-Za-z ']+",self.npc[2]):raise RuntimeError('unsupported NPC target name')
            names=['TC442NpcRestore','TC442NpcService']
            q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',names)
            if q.fetchone():raise RuntimeError('an earlier NPC fixture needs cleanup')
            q.execute('SELECT MAX(id) FROM client442_world.game_tele');start=q.fetchone()[0]+1
            x,y,z=self.npc[4:7]
            # Bank windows occlude the public-facing side. Other NPCs are
            # approached from their facing direction to avoid staging in a wall.
            dx,dy=(-1.5,2.6) if self.entry==2455 else (3*math.cos(self.npc[7]),3*math.sin(self.npc[7]))
            sources=[self.before[3:],(x+dx,y+dy,z,math.atan2(-dy,-dx)%(2*math.pi),0)]
            for i,(name,source) in enumerate(zip(names,sources)):
                row=(start+i,*source,name);self.rows.append(row)
                q.execute('INSERT INTO client442_world.game_tele '
                    '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',row)
                # FLOAT text output loses significant digits at world coordinates.
                # Retain the actual stored value, widened before SQL serialization.
                q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),'
                    'CAST(position_z AS DOUBLE),CAST(orientation AS DOUBLE),map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],))
                self.rows[-1]=q.fetchone()
        lab.private_write(self.out/'npc_fixture.json',json.dumps({'source':'code_fixture_native_console',
            'before':self.before,'npc':self.npc,'temporary_teleports':self.rows},indent=2)+'\n')
        lab.server_command('reload game_tele');time.sleep(.5)
        lab.server_command('tele name Harnessone TC442NpcService');time.sleep(4)

    def restore(self):
        if not self.rows:return
        lab.server_command('tele name Harnessone TC442NpcRestore');time.sleep(4)
        lab.server_command('saveall');time.sleep(1)
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT position_x,position_y,position_z,orientation,map '
                'FROM client442_characters.characters WHERE guid=1');position=q.fetchone()
            if any(abs(a-b)>.01 for a,b in zip(position,self.before[3:])):
                raise RuntimeError('NPC fixture position restoration failed; preserving restore teleport')
            for row in self.rows:
                q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),'
                    'CAST(position_z AS DOUBLE),CAST(orientation AS DOUBLE),map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],))
                # Database coordinates are floats; compare within native precision.
                found=q.fetchone()
                if not found or found[0]!=row[0] or found[-1]!=row[-1] or any(abs(a-b)>.001 for a,b in zip(found[1:-1],row[1:-1])):
                    raise RuntimeError('temporary NPC teleport changed; refusing deletion')
            for row in self.rows:
                q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
        lab.server_command('reload game_tele')
        lab.private_write(self.out/'npc_restoration.json',json.dumps({'position':position,
            'temporary_teleports_removed':[r[0] for r in self.rows]},indent=2)+'\n')
