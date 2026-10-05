"""Historical journal priming must retain constant memory and no old packets."""
from tools.client_compatibility import interaction_lifecycle as lifecycle


def test_priming_streams_history_without_materializing_it(monkeypatch):
    counters={'live':0,'peak':0}
    class Record(dict):
        def __init__(self):
            super().__init__(session='historical',time=1)
            counters['live']+=1;counters['peak']=max(counters['peak'],counters['live'])
        def __del__(self):counters['live']-=1
    class Cursor:
        def __init__(self):self.calls=0
        def poll(self):
            self.calls+=1
            if self.calls==1:
                for _ in range(2500):yield Record()
            else:yield {'session':'owned','time':5,'name':'CMSG_WHO'}
    cursor=Cursor();monkeypatch.setattr(lifecycle,'Cursor',lambda path:cursor)
    packets=lifecycle.Packets('owned')
    assert counters['peak']<=2
    assert counters['live']==0 and packets.rows==[]
    assert packets.since(2)==[{'session':'owned','time':5,'name':'CMSG_WHO'}]
