"""Read transport attachments for independent native packet observations."""
import math


class Transport:
    def __init__(self,reader,gameobject=False):
        self.gameobject=gameobject;self.present={}
        if gameobject:
            self.present[5]=reader.bits(1);self.vehicle=reader.bits(1)
            for i in [0,3,6,1,4,2]:self.present[i]=reader.bits(1)
            self.previous=reader.bits(1);self.present[7]=reader.bits(1)
        else:
            self.present[1]=reader.bits(1);self.previous=reader.bits(1)
            for i in [4,0,6]:self.present[i]=reader.bits(1)
            self.vehicle=reader.bits(1)
            for i in [7,5,3,2]:self.present[i]=reader.bits(1)

    def read(self,r):
        identity=0
        def octet(i):
            nonlocal identity
            if self.present[i]:identity|=(r.raw(1)[0]^1)<<(i*8)
        previous=vehicle=0
        if self.gameobject:
            octet(0);octet(5)
            if self.vehicle:vehicle,=r.unpack('I')
            octet(3);x,=r.unpack('f')
            for i in [4,6,1]:octet(i)
            time,y=r.unpack('If');octet(2);octet(7)
            z,seat,o=r.unpack('fbf')
            if self.previous:previous,=r.unpack('I')
        else:
            octet(5);octet(7);time,o=r.unpack('If')
            if self.previous:previous,=r.unpack('I')
            y,x=r.unpack('ff');octet(3);z,=r.unpack('f');octet(0)
            if self.vehicle:vehicle,=r.unpack('I')
            seat,=r.unpack('b')
            for i in [1,6,2,4]:octet(i)
        if not identity or not all(math.isfinite(n) for n in [x,y,z,o]):
            raise ValueError('invalid native transport identity or position')
        return {'guid':identity,'position':(x,y,z,o),'seat':seat,'time':time,
                'previous_time':previous,'vehicle_id':vehicle}
