"""Reviewed operation-to-receipt mappings; never infer coverage from a panel or prefix."""
import json
import re
from pathlib import PurePosixPath


def reconcile(data,ledger,repo):
    operations={case['id']:case for case in data['cases']};records={}
    for record in ledger['qualifications']:
        key=record['id']
        if key in records or not re.fullmatch(r'[a-z0-9_]+',key):raise ValueError('invalid qualification identity')
        if not record['scope'] or not record['limits'] or not record['operations'] or not record['evidence']:
            raise ValueError('qualification requires scope, limits, operations and evidence')
        for proof in record['evidence']:
            pointer=PurePosixPath(proof['pointer']);member=PurePosixPath(proof['member'])
            if (pointer.is_absolute() or '..' in pointer.parts or member.is_absolute() or '..' in member.parts or
                    not str(pointer).startswith('artifacts/client_harness/') or pointer.suffix!='.dvc' or
                    not (repo/str(pointer)).is_file() or not re.fullmatch(r'[0-9a-f]{64}',proof['sha256'])):
                raise ValueError('qualification requires a committed evidence pointer and receipt digest')
        for operation in record['operations']:
            if operation not in operations:raise ValueError('unknown qualified operation: '+operation)
            case=operations[operation]
            if 'qualification' in case:raise ValueError('duplicate qualified operation: '+operation)
            case['qualification']=key;case['automation']='live_variant_qualified'
        records[key]=record
    data['qualification_records']=list(records.values())
    data['qualified_operations']=sum('qualification' in case for case in data['cases'])
    data['qualification_limits']='Checked means the documented fixture variant passed. Other variants and whole-family coverage remain open.'
    return data


def load(repo):
    path=repo/'experiments/configs/client_harness/442_interaction_qualifications_v1.json'
    return json.loads(path.read_text()) if path.exists() else {'qualifications':[]}


def render_evidence(records):
    lines=['## Qualification evidence','','Each checked operation refers to one reviewed record below. Receipt paths are members of the linked DVC archive; hashes identify the reviewed JSON receipt.','']
    for record in records:
        lines.extend(['### '+record['id'],'',record['scope'],'','Remaining limits: '+record['limits'],''])
        for proof in record['evidence']:
            pointer=proof['pointer'];label=PurePosixPath(pointer).name
            lines.append('- ['+label+'](../../'+pointer+'), member `'+proof['member']+'`, SHA-256 `'+proof['sha256']+'`.')
            if proof.get('cases'):
                lines.append('  Checked cases: '+', '.join('`'+key+'` ('+status+')' for key,status in proof['cases'].items())+'.')
        lines.append('')
    return lines
