"""Bind a closed public warrior glyph catalog to native glyph IDs and types."""
import argparse,json,struct
from pathlib import Path
from . import lab_runtime as lab


def review(source):
    run=json.loads(source.read_text())
    if (not run.get('finished_at') or not run.get('completed') or run['actor']['guid']!=1 or
            not all(run.get('restoration',{}).values()) or not run.get('glyph_catalog_oracle',{}).get('passed') or
            not run.get('glyph_search_oracle',{}).get('passed')):
        raise RuntimeError('glyph review requires the closed restored catalog/search trial')
    path=lab.ROOT/'data/dbc/enUS/GlyphProperties.dbc';data=path.read_bytes()
    magic,count,fields,width,strings=struct.unpack_from('<4s4I',data)
    if (magic,count,fields,width)!=(b'WDBC',347,4,16) or len(data)!=20+count*width+strings:
        raise RuntimeError('pinned native glyph properties schema changed')
    native={r[0]:r for r in [struct.unpack_from('<4I',data,20+i*width) for i in range(count)]}
    rows=run['glyph_catalog_oracle']['rows'];glyphs=[r for r in rows if r.get('name')!='header']
    types={0:2,1:3,2:1};proof=[]
    for row in glyphs:
        item=native.get(row['id'])
        if not item or types.get(item[2])!=row['type']:raise RuntimeError('public glyph ID/type disagrees with native properties')
        proof.append({'public':row,'native':{'id':item[0],'aura_spell':item[1],'type':item[2],'icon':item[3]}})
    if len(glyphs)!=34 or len({r['id'] for r in glyphs})!=34:
        raise RuntimeError('public warrior glyph catalog is incomplete or duplicated')
    record={'schema':'client442_glyph_catalog_review_v1','source':str(source.relative_to(lab.ROOT)),
        'source_sha256':lab.sha256(source),'native_catalog_sha256':lab.sha256(path),'passed':True,
        'glyphs':proof,'headers':[r for r in rows if r.get('name')=='header'],
        'search':run['glyph_search_oracle'],'clear_search':run['glyph_detail']['glyph_search_cleared'],
        'scope':'Primary warrior catalog IDs/types, Battle name search and ordinary search clearing.',
        'limits':'Other classes, learned glyphs, filters, tooltips, application and aura effects remain open.'}
    target=source.parent/'glyph_catalog_review.json'
    if target.exists():raise RuntimeError('immutable glyph review already exists')
    lab.private_write(target,json.dumps(record,indent=2)+'\n')
    return {'file':str(target),'verified_glyphs':len(proof),'passed':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--episode',type=Path,required=True)
    print(json.dumps(review(p.parse_args().episode)),flush=True)
