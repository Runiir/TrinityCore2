"""Publishing Python can replay pet identities and timing without UI imports."""
import json
from pathlib import Path
import subprocess
import pytest
from tools.client_compatibility import hunter_revive_timing as timing
from tools.client_compatibility import pet_packet_identity as identity


FIXTURES=Path(__file__).parent/'fixtures'


def test_root_publishing_subprocess_replays_actual_packets_without_ui_dependencies():
    repo=Path(__file__).resolve().parents[4]
    python=repo/'.pixi/envs/default/bin/python'
    script="""
import importlib.abc,json,sys
from pathlib import Path
class PureImports(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if (fullname.startswith(('google','Xlib','pymysql')) or
            fullname.startswith('tools.client_compatibility.interaction_') or
            fullname.startswith('tools.client_compatibility.auth.') or
            fullname=='tools.client_compatibility.hunter_revive_lifecycle'):
            raise AssertionError('publishing helper imported UI/runtime dependency: '+fullname)
sys.meta_path.insert(0,PureImports())
from tools.client_compatibility.hunter_revive_timing import CORPSE_SECONDS,MAX_SETUP_AGE,MIN_SUBMISSION_REMAINING,native_revive_timing
from tools.client_compatibility.pet_packet_identity import cast_identity,expected_guid
fixtures=Path('tools/client_compatibility/world/tests/fixtures')
revive=json.loads((fixtures/'hunter_revive_expiry_ui167.json').read_text())
result=native_revive_timing(revive['packets'],{'counter':4},revive['call_fixture_chat_setup_started_at'])
assert (CORPSE_SECONDS,MAX_SETUP_AGE,MIN_SUBMISSION_REMAINING)==(59,25,15)
assert result['one_matching_start_and_completion'] and result['native_ten_second_cast']
assert result['native_completion_ordered'] and not result['completion_within_conservative_corpse_deadline']
summon=json.loads((fixtures/'native_pet_summon_cleanup_ui121.json').read_text())
requests=[cast_identity(p) for p in summon['packets']]
assert requests[1]=={'counter':1,'spell':688,'misc':0,'flags':0,'target_flags':0}
assert requests[2]=={'caster':5,'unit':5,'counter':1,'spell':688}
assert requests[3] is None and requests[4]['counter']==0
assert expected_guid({'guid':0xf14001a000000012,'map':0})=='Pet-0-1-0-0-416-0000000012'
print(json.dumps({'expired_deadline_rejected':True,'ordinary_counter':requests[2]['counter'],'triggered_counter':requests[4]['counter']}))
"""
    result=subprocess.run([str(python),'-c',script],cwd=repo,text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)=={'expired_deadline_rejected':True,'ordinary_counter':1,'triggered_counter':0}


def test_public_pet_guid_preserves_native_entry_map_and_low_identity():
    assert identity.expected_guid({'guid':17383895845845336076,'map':0})=='Pet-0-1-0-0-299-000000000C'


@pytest.mark.parametrize('packet',[
    {'name':'CMSG_CAST_SPELL','direction':'to_native','body':'01'},
    {'name':'SMSG_SPELL_GO','direction':'from_native','body':'01'},
    {'name':'SMSG_CAST_FAILED','direction':'from_native','body':'01'}])
def test_malformed_pet_prefixes_still_fail_instead_of_inventing_identity(packet):
    with pytest.raises(ValueError):identity.cast_identity(packet)


def test_missing_matching_completion_still_cannot_prove_revive():
    trace=json.loads((FIXTURES/'hunter_revive_expiry_ui167.json').read_text())
    packets=[p for p in trace['packets'] if p['name']!='SMSG_SPELL_GO']
    assert not timing.native_revive_timing(packets,{'counter':4},trace['call_fixture_chat_setup_started_at'])[
        'one_matching_start_and_completion']
