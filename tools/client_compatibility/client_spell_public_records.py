"""Inspect exact spell records in complete verified public60895 sections."""
import argparse
import json
import struct
from pathlib import Path
from . import lab_runtime as lab
from .client_spell_tables import TABLES, public_sections


FIELDS = {
    'SpellEffect': {0:'DifficultyID', 1:'EffectIndex', 2:'Effect', 4:'EffectAttributes',
        5:'EffectAura', 17:'EffectTriggerSpell'},
    'SkillLineAbility': {1:'ID', 2:'SkillLine', 3:'Spell', 4:'MinSkillLineRank',
        5:'ClassMask', 6:'SupercedesSpell', 7:'AcquireMethod', 10:'Flags'},
}


def scalar(bits, column, row_id, palette, common):
    offset, size, extra, kind, default, width, cardinality = column
    if kind == 2:
        return common.get(row_id, default)
    if kind not in (0, 1, 3, 5) or not size:
        raise ValueError('unsupported scalar compression')
    value = (bits >> offset) & ((1 << size)-1)
    if kind == 3:
        if value >= len(palette):raise ValueError('palette index out of bounds')
        return palette[value]
    if kind == 5 and value & (1 << (size-1)):
        value -= 1 << size
    return value


def records(directory, name, spells):
    path = directory/(name+'.public-prefix.db2')
    proof = directory/(name+'.public-prefix.json')
    data = path.read_bytes();manifest = json.loads(proof.read_text())
    if (manifest.get('build') != 60895 or manifest.get('prefix_sha256') != lab.sha256(path) or
        manifest.get('verified_prefix_bytes') != len(data)):
        raise ValueError('verified public prefix identity differs')
    h, sections = public_sections(data, TABLES[name])
    if sections != manifest.get('sections') or list(h) != manifest.get('header'):
        raise ValueError('public section proof differs')
    fields = h[1];start = 204+40*h[-1]+4*fields
    if h[14] != fields*24 or start+h[14]+h[15]+h[16] > sections[0]['base']:
        raise ValueError('unsupported field metadata boundary')
    columns = [struct.unpack_from('<HH5I', data, start+24*i) for i in range(fields)]
    palettes = {};commons = {};pos = start+h[14]
    for i, col in enumerate(columns):
        if col[3] in (3, 4):
            if col[2] % 4:raise ValueError('invalid palette size')
            palettes[i] = struct.unpack_from('<'+'I'*(col[2]//4), data, pos);pos += col[2]
    if pos != start+h[14]+h[16]:raise ValueError('palette metadata differs')
    for i, col in enumerate(columns):
        if col[3] == 2:
            if col[2] % 8:raise ValueError('invalid common-value size')
            pairs = [struct.unpack_from('<II', data, pos+j) for j in range(0, col[2], 8)]
            commons[i] = dict(pairs);pos += col[2]
            if len(commons[i]) != len(pairs):raise ValueError('duplicate common-value ID')
    if pos != start+h[14]+h[16]+h[15]:raise ValueError('common metadata differs')
    selected = []
    for section in sections:
        if section['copies']:raise ValueError('public copy tables require separate reconstruction')
        count = section['rows'];base = section['base'];tail = base+count*h[2]+section['strings']
        identifiers = list(struct.unpack_from('<'+'I'*count, data, tail)) if section['ids'] else None
        tail += section['ids'];relations = {}
        if section['relations']:
            relation_count = struct.unpack_from('<I', data, tail)[0]
            if section['relations'] != 12+8*relation_count:raise ValueError('relationship boundary differs')
            for n in range(relation_count):
                value, index = struct.unpack_from('<II', data, tail+12+8*n)
                if index >= count or index in relations:raise ValueError('invalid relationship index')
                relations[index] = value
        seen = set()
        for index in range(count):
            bits = int.from_bytes(data[base+index*h[2]:base+(index+1)*h[2]], 'little')
            row_id = identifiers[index] if identifiers is not None else scalar(bits, columns[h[10]], 0, [], {})
            if row_id <= 0 or row_id in seen:raise ValueError('invalid public row ID')
            seen.add(row_id)
            spell = relations.get(index) if name == 'SpellEffect' else scalar(bits, columns[3], row_id,
                palettes.get(3, []), commons.get(3, {}))
            if spell not in spells:continue
            row = {'ID':row_id, 'SpellID':spell, 'section':section['index']}
            for i, label in FIELDS[name].items():
                col = columns[i]
                if col[3] != 2 and col[0]+col[1] > h[2]*8:
                    raise ValueError('selected field exceeds record')
                row[label] = scalar(bits, col, row_id, palettes.get(i, []), commons.get(i, {}))
            if name == 'SkillLineAbility' and relations.get(index) != row['SkillLine']:
                raise ValueError('inline skill relationship differs')
            selected.append(row)
    return {'table':name, 'prefix_sha256':lab.sha256(path), 'proof_sha256':lab.sha256(proof),
        'requested_spells':sorted(spells), 'rows':selected, 'complete_table':False,
        'limits':'Positive records in verified public sections only; unread encrypted sections prevent global absence claims. Base tables do not include hotfix replay.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = [records(args.directory, name, {80388, 93375, 3127, 688}) for name in TABLES]
    lab.private_write(args.output, json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
