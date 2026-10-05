"""Native-authorized Who identities and modern request correlation."""
import copy,struct
import pytest
from tools.client_compatibility.world.buffer import Writer,Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,action

HIGH=(2<<58)|(1<<42)
GUILD_HIGH=(28<<58)|(1<<42)
IDENTITY={'guid':1,'name':'Harnessone','race':1,'gender':0,'class':1,'level':85,
    'guild_id':0,'guild_name':''}


def request(name='Harnessone',id=17,minimum=0,maximum=100,race=-1,klass=-1,areas=(),words=(),
            exact=False,addon=False,enemies=False,arena=False,realm='',guild='',guild_realm='',server=None,origin=1):
    w=Writer().bits(len(areas),4).bits(addon,1).pack('iiqi',minimum,maximum,race,klass)
    for value,width in [(len(name.encode()),6),(len(realm.encode()),9),(len(guild.encode()),7),
                        (len(guild_realm.encode()),9),(len(words),3)]:w.bits(value,width)
    w.bits(enemies,1).bits(arena,1).bits(exact,1).bits(server is not None,1).flush()
    for word in words:w.bits(len(word.encode()),7).raw(word.encode()).flush()
    w.raw((name+realm+guild+guild_realm).encode())
    if server is not None:w.pack('iiI',*server)
    w.pack('IB',id,origin)
    for area in areas:w.pack('i',area)
    return action('who_request','CMSG_WHO',w.finish())


def response(rows=None,count=None,total=None):
    if rows is None:rows=[dict(IDENTITY,area=3)]
    n=len(rows) if count is None else count;t=n if total is None else total
    body=struct.pack('<II',n,t)
    for row in rows:
        body+=row['name'].encode()+b'\0'+row['guild_name'].encode()+b'\0'
        body+=struct.pack('<IIIBI',row['level'],row['class'],row['race'],row['gender'],row['area'])
    return action('who_response','SMSG_WHO',body)


def run(codec,actions,identities=None,active=True):
    return result(codec,op='stateful',character={'guid':1},snapshot={} if active else None,
        identities=[IDENTITY] if identities is None else identities,actions=actions)


def decoded(packet):
    assert packet[0]=='SMSG_WHO';r=Reader(bytes.fromhex(packet[1]));id,=r.unpack('I');n=r.bits(6);rows=[]
    for _ in range(n):
        assert r.bits(1)==0;length=r.bits(6);assert [r.bits(7) for _ in range(5)]==[0]*5
        assert r.guid()==(0,0) and r.guid()==(0,0);guid=r.guid()
        club,realm,race,sex,klass,level,unused,season=r.unpack('QI5Bi')
        assert (club,realm,unused,season)==(0,1,0,0)
        name=r.raw(length).decode();guild_guid=r.guid();guild_realm,area=r.unpack('Ii')
        gl=r.bits(7);gm=r.bits(1);guild=r.raw(gl).decode()
        rows.append((guid,name,level,klass,race,sex,guild_guid,guild_realm,area,guild,gm))
    r.end();return id,rows


def test_owned_query_forwards_native_fields_and_echoes_modern_request_id(codec):
    out=run(codec,[request(),response()])
    assert out[0]==['CMSG_WHO',(struct.pack('<ii',0,100)+b'Harnessone\0\0'+struct.pack('<iiII',-1,-1,0,0)).hex()]
    assert decoded(out[1])==(17,[((1,HIGH),'Harnessone',85,1,1,0,(0,0),0,3,'',0)])


def test_local_realm_words_areas_class_and_optional_server_metadata(codec):
    out=run(codec,[request(name='',race=0,klass=2,areas=(3,12),words=('Badlands','é'),
        realm='Client442Lab',server=(0,0,1)),response([])])
    expected=struct.pack('<ii',0,100)+b'\0\0'+struct.pack('<iiIiiI',-1,2,2,3,12,2)+b'Badlands\0'+ 'é'.encode()+b'\0'
    assert out[0]==['CMSG_WHO',expected.hex()] and decoded(out[1])==(17,[])


def test_authoritative_guild_and_public_identity_are_serialized(codec):
    row=dict(IDENTITY,guid=2,name='Harnesstwo',guild_id=7,guild_name='Owned Guild',area=12)
    out=run(codec,[request(name='Harnesstwo',id=91),response([row])],identities=[row])
    assert decoded(out[1])==(91,[((2,HIGH),'Harnesstwo',85,1,1,0,(7,GUILD_HIGH),1,12,'Owned Guild',0)])


def test_exact_name_filters_only_native_authorized_rows_and_keeps_correlation(codec):
    second=dict(IDENTITY,guid=2,name='Harnessoneextra',area=3);own=dict(IDENTITY,area=3)
    out=run(codec,[request(name='HARNESSone',exact=True,id=999),response([own,second])],identities=[own,second])
    assert decoded(out[1])[0]==999 and len(decoded(out[1])[1])==1
    assert decoded(run(codec,[request(name='NoMatch',exact=True),response()],identities=[IDENTITY])[1])==(17,[])


@pytest.mark.parametrize('kw',[{'minimum':-1},{'maximum':256},{'minimum':10,'maximum':9},
    {'race':1},{'klass':-2},{'areas':tuple(range(11))},{'areas':(-1,)},{'words':('a',)*5},
    {'addon':True},{'enemies':True},{'arena':True},{'realm':'OtherRealm'},
    {'guild_realm':'OtherRealm'},{'server':(0,1,1)},{'server':(0,0,2)},
    {'name':'Name\0Other'},{'words':('x\0y',)},{'origin':0},{'origin':4},{'name':'é','exact':True}])
def test_unsupported_or_malformed_queries_do_not_create_pending_authority(codec,kw):
    out=run(codec,[request(**kw),response()]);assert 'error' in out[0] and out[1] is None


@pytest.mark.parametrize('body',[b'',b'\0',bytes.fromhex(request()['body'])[:-1],bytes.fromhex(request()['body'])+b'x'])
def test_truncated_and_trailing_query_bytes_are_rejected(codec,body):
    assert 'error' in run(codec,[action('who_request','CMSG_WHO',body)])[0]


@pytest.mark.parametrize('change',['missing','duplicate_name','wrong_guid','duplicate_guid','level','race',
    'gender','class','guild_name','guild_id'])
def test_missing_ambiguous_or_changed_identity_never_fabricates_a_result(codec,change):
    identities=[copy.deepcopy(IDENTITY)];rows=[dict(IDENTITY,area=3)]
    if change=='missing':identities=[]
    elif change=='duplicate_name':identities*=2
    elif change=='wrong_guid':identities[0]['guid']=0
    elif change=='duplicate_guid':
        rows.append(dict(rows[0],name='Harnesstwo'));identities.append(dict(identities[0],name='Harnesstwo'))
    elif change=='guild_name':identities[0]['guild_name']='New Guild'
    elif change=='guild_id':identities[0]['guild_id']=7
    else:identities[0][change]+=1
    assert 'error' in run(codec,[request(),response(rows)],identities=identities)[1]


@pytest.mark.parametrize('reply',[response(count=51),response(total=2),response([dict(IDENTITY,area=3)]*2),
    response([dict(IDENTITY,level=256,area=3)]),response([dict(IDENTITY,gender=2,area=3)]),
    action('who_response','SMSG_WHO',b'\0'),{**response(),'body':response()['body']+'00'}])
def test_bad_native_catalogs_never_emit_partial_results(codec,reply):
    assert 'error' in run(codec,[request(),reply])[1]


def test_one_unanswered_native_query_cannot_be_replaced_and_logout_revokes_it(codec):
    out=run(codec,[response(),request(id=10),request(id=20),response(),response(),request(id=30),response([])])
    assert out[0] is None and 'error' in out[2] and decoded(out[3])[0]==10 and out[4] is None
    assert decoded(out[-1])==(30,[])
    out=run(codec,[request(),action('logout_complete','SMSG_LOGOUT_COMPLETE',b''),response(),request()])
    assert out[2] is None and 'error' in out[3]
    assert 'error' in run(codec,[request()],active=False)[0]
