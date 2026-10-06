"""Owned stock geometry and independent native reaction-mode readbacks."""
from .interaction_pet_react_capture import active_mode
from .interaction_pet_command_probe import expected_guid

TOKENS={0:'PET_MODE_PASSIVE',3:'PET_MODE_ASSIST'}
SLOTS={0:10,3:8}


def mode_button(probe,mode):
    rows=[r for r in probe.get('actions',[]) if r.get('name')==TOKENS[mode] and r.get('slot')==SLOTS[mode]
        and r.get('is_token') is True and r.get('available') is True]
    if len(rows)!=1:raise RuntimeError('owned stock mode row is absent or ambiguous')
    row=rows[0];f=row.get('frame',{})
    if (f.get('button')!='PetActionButton'+str(SLOTS[mode]) or
        not all(f.get(k) is True for k in ('available','visible','enabled')) or
        any(type(f.get(k)) is not int or not 0<=f[k]<=65535 for k in ('x','y'))):
        raise RuntimeError('stock pet mode button lacks a visible enabled viewport point')
    return row,[round(f['x']/65535*1280),round(f['y']/65535*720)]


def info_pairs(rows,session,since,until):
    scoped=[p for p in rows if p.get('session')==session and since<=p.get('time',0)<=until
        and p.get('name')=='CMSG_REQUEST_PET_INFO']
    result=[]
    for p in scoped:
        if p.get('direction')!='from_client':continue
        matches=[n for n in scoped if n.get('direction')=='to_native' and n.get('body')==p.get('body')==''
            and 0<=n['time']-p['time']<2]
        result.append({'modern':p,'native':matches[0] if len(matches)==1 else None})
    return result


def readback_checks(catalog,pet,mode,queries,sample,persisted):
    probe=sample['probe']
    tokens={'PET_MODE_PASSIVE','PET_MODE_ASSIST','PET_MODE_DEFENSIVE'}
    rows=[r for r in probe.get('actions',[]) if r.get('is_token') is True and r.get('available') is True
        and r.get('name') in tokens]
    return {'ordinary_native_info_query':bool(queries) and all(p['native'] is not None for p in queries),
        'native_owned_catalog_mode':bool(catalog and catalog['guid']==pet['guid'] and catalog['react']==mode
            and catalog['command']==1 and catalog['packet'].get('direction')=='from_native'
            and catalog['packet'].get('name')=='SMSG_PET_SPELLS'),'persisted_owned_react':all(persisted.get(k)==v for k,v in
                [('id',2),('entry',416),('owner',5),('Reactstate',mode)]),
        'public_owned_pet':probe.get('pet_guid')==expected_guid(pet) and probe.get('owner_guid')=='Player-1-00000005',
        'public_mode_selected':active_mode(probe,TOKENS[mode]),
        'public_other_modes_inactive':len(rows)==3 and {r['name'] for r in rows}==tokens and
            all(r.get('active') is False for r in rows if r['name']!=TOKENS[mode]),
        'public_idle':probe.get('pet_speed')==probe.get('player_speed')==0,
        'public_ui_clean':sample['ui_clean']}
