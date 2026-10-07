"""A stale saved pose must never suppress the live fixture's return teleport."""
from contextlib import nullcontext
from tools.client_compatibility import interaction_hunter_tame_stage as s


def test_flushes_live_pose_before_deciding_cleanup_is_already_home(monkeypatch):
    home=[-9465.12,50.9323,56.8473,4.58812,0]
    away=[-9365.37,28.1558,61.4795,2.06166,0]
    native={'pid':10,'start_ticks':'123'};rows=[[1,*home,s.NAMES[0]],[2,*away,s.NAMES[1]]]
    fixture={'owner':6,'native':native,'before':home,'rows':rows}
    state={'saved':home,'live':away};commands=[];deletions=[]
    class Query:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,text,args=None):
            if text.startswith('DELETE'):deletions.append(args)
        def fetchone(self):return tuple(home)
    class Connection:
        def cursor(self):return Query()
    class Trial:
        receipt={'runtime':{'worldserver':native}}
        def persist(self):pass
    def command(text):
        commands.append(text)
        if text=='saveall':state['saved']=state['live']
        elif text=='tele name Harnesshunt '+s.NAMES[0]:state['live']=home
    monkeypatch.setattr(s.lab,'connection',lambda:nullcontext(Connection()))
    monkeypatch.setattr(s.lab,'server_command',command)
    monkeypatch.setattr(s,'teleport_row',lambda q,n:rows[n-1])
    monkeypatch.setattr(s,'pose',lambda:list(state['saved']))
    monkeypatch.setattr(s,'saved',lambda n:{'spells':[1515]})
    monkeypatch.setattr(s,'protected',lambda old:{str(n):True for n in range(1,6)})
    monkeypatch.setattr(s.time,'sleep',lambda n:None)
    t=Trial();s.restore(t,fixture,{}, {'spells':[1515]})
    assert commands[:2]==['saveall','tele name Harnesshunt '+s.NAMES[0]]
    assert state['live']==state['saved']==home
    assert deletions==[(1,s.NAMES[0]),(2,s.NAMES[1])]
    assert all(t.receipt['pose_restoration']['checks'].values())
    assert t.receipt['pose_restoration']['native_teleport_replayed'] is True
