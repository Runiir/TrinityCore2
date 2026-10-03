"""Regression for the city passenger/vehicle creates that disconnected UI18."""
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

# Session d5fa257a, native packets at 1790992933; original trace is DVC evidence.
VEHICLE=bytes.fromhex('00000100000001f3a37e86cc50f103130000000080000000f6600000ac300000e007b08700009040000020405f190000dce9c542ee3108c619322844dce9c542b83308c6546b284436b7c542a53e08c658262944270ec642924908c65ce12944c0b8c5427f5408c65e9c2a4495b9c5426d5f08c650572b4415d1c5428b6508c6db432c445be5c542aa6b08c664302d44d6eec542b86e08c687a62d44d6eec542b86e08c687a62d440000803fa12800000000803fd6eec542b86e08c687a62d44f1b10300f3bac542cdc85f08c6c3f54840a2711c974010652b44f07f000020400c6cc800e00f4940510000e0407b47fb3f15000041000090407b47fb3f3d0600008502057300000e4308e37b002e00000000280000800000a37e000086cc50f10900000086cc00000000803f00020000b1010000ea010000b1010000ea010000cdcc9c40cdcc9c40140000006b030000008000000088000000004000d0070000d00700003d2cb43ecdccdc3fda930000da930000000000000000803f0000803f81000000ea010000010100000000803f')
PASSENGER=bytes.fromhex('00000100000001f3a47e87cc50f103830000000080000300275d9e0078860000904000002040f3bac542cdcdf00000000000000000000000003333333f00000000a2007f5187da6008c6c3f54840a5711c9740758e2b44f07fda388e3f0c6cc800e00f4940510000e0407b47fb3f05002040000090407b47fb3f3b06000005730000060100e37b102e00000000200000800000a47e000087cc50f10900000087cc00000000803f000102012a0000002a0000000100000007000000000000020008000000004000d0070000d00700000000003f0000c03f178200001782000000000003000000000000803f0000803f00000000010000000000803f')


def test_captured_city_passenger_and_vehicle_are_complete(codec):
    parent=result(codec,op='records',body=VEHICLE.hex())[0]
    passenger=result(codec,op='records',body=PASSENGER.hex())[0]
    move=passenger['movement'];transport=move['transport']
    assert transport['guid']==parent['guid']
    assert transport['seat']==0
    assert parent['kind']==passenger['kind']==3
    assert parent['guid']>>52==0xf15
    for snapshot in [parent,passenger]:
        body=bytes.fromhex(result(codec,op='object_block',kind='unit',snapshot=snapshot,character={'guid':1,'map':0}))
        r=Reader(body);assert r.unpack('B')==(1,)
        _,high=r.guid();assert high>>58==9 # Both are vehicles, one rides the other.
        assert r.unpack('B')==(5,)
        flags=[r.bits(1) for _ in range(19)];r.align()
        r.guid();r.unpack('4I4f2f2I')
        bits=[r.bits(1) for _ in range(8)];r.align()
        assert bits[1]==(snapshot is passenger)
        if bits[1]:
            _,parent_high=r.guid();assert parent_high>>58==9
            assert r.unpack('4f')==pytest.approx(transport['position'])
            assert r.unpack('bI')==(transport['seat'],transport['time'])
            assert r.bits(1)==bool(transport['previous_time'])
            assert r.bits(1)==bool(transport['vehicle_id']);r.align()
            if transport['previous_time']:assert r.unpack('I')==(transport['previous_time'],)
            if transport['vehicle_id']:assert r.unpack('I')==(transport['vehicle_id'],)
        r.unpack('9fIf17f');assert r.bits(1)==0;r.align();assert r.unpack('I')==(0,)
        assert flags[9]==1
        assert r.unpack('If')==pytest.approx((snapshot['movement']['vehicle']['id'],snapshot['movement']['vehicle']['facing']))
        size,=r.unpack('I');r.raw(size);r.end()


@pytest.mark.parametrize('body',[VEHICLE,PASSENGER])
def test_captured_transports_reject_truncation_and_trailing_bytes(codec,body):
    for malformed in [body[:len(body)//2],body[:-1],body+b'x']:
        assert 'error' in codec(op='records',body=malformed.hex())


def test_both_captured_vehicles_remain_visible_and_targetable(codec):
    passenger=result(codec,op='records',body=PASSENGER.hex())[0]
    guid=passenger['guid'];entry=(guid>>32)&0xfffff
    modern=Writer().guid(guid&0xffffffff,(9<<58)|(1<<42)|(entry<<6)).finish()
    actions=[{'fn':'object_updates','name':'SMSG_UPDATE_OBJECT','body':body.hex()} for body in [VEHICLE,PASSENGER]]
    actions.append({'fn':'combat_request','name':'CMSG_SET_SELECTION','body':modern.hex()})
    replies=result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
        units=[],gameobjects=[],actions=actions)
    assert [r[0] for r in replies]==['SMSG_UPDATE_OBJECT','SMSG_UPDATE_OBJECT','CMSG_SET_SELECTION']
    assert replies[-1][1]==guid.to_bytes(8,'little').hex()
