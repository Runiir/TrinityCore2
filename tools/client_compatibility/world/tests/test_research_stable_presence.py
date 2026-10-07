"""A later login research response cannot revoke the owned stable catalog."""
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,action
from tools.client_compatibility.world.tests.test_tame_pet_added_stable import owned,baseline
from tools.client_compatibility.world.tests.test_archaeology_projects import history,mask


def test_login_stable_catalog_survives_following_empty_native_research_history(codec):
    rows=owned(codec,[baseline(),action('research_history','SMSG_SETUP_RESEARCH_HISTORY',history([]))])
    assert rows[0][0]==rows[1][0]=='SMSG_UPDATE_OBJECT'
    r=Reader(bytes.fromhex(rows[1][1]));assert r.unpack('HI')==(0,1) and r.bits(1)==1 and r.bits(1)==0
    length,=r.unpack('I');o=Reader(r.raw(length));r.end();assert o.unpack('B')==(0,);o.guid()
    length,=o.unpack('I');f=Reader(o.raw(length));o.end();assert f.unpack('BBBI')==(1,0,3,128)
    assert mask(f,46,first32=True)=={102,122};f.align()
    assert f.bits(1)==1
    f.align();assert f.bits(2)==3 and f.bits(32)==0;f.end()
