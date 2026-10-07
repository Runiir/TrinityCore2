"""Only a successful owned Tame can identify a later disposable Wolf."""
import time
from .hunter_tame_boundary import saved_pet_preserved


def pair_preserved(before,after):
    if len(before)!=2 or len(after)!=2:return False
    b={r['id']:r for r in before};a={r['id']:r for r in after}
    return set(b)==set(a) and all(saved_pet_preserved(b[n],a[n]) for n in b)


def disposable_number(source,current,native):
    if (source.get('completed') is not True or source.get('failure') is not None or
        not source.get('finished_at') or source['finished_at']>=time.time() or
        source.get('phase')!='owned_tame_native_outcome_captured' or source.get('input_sent') is not True or
        source.get('capture_disarmed') is not True or source.get('qualification_added') is not False or
        source.get('runtime',{}).get('worldserver')!=native or
        tuple(source.get('actor',{}).get(k) for k in ('guid','account_id','class','level'))!=(6,2,3,10) or
        len(source.get('capture_checks',{}))!=14 or not all(v is True for v in source['capture_checks'].values())):
        raise RuntimeError('requires one whole successful owned Tame with unchanged native lifetime')
    fields=source.get('native_pet_after',{}).get('fields',{});number=fields.get('69')
    captured=source.get('retained_pet_after',[])
    if (type(number) is not int or not 4<number<2**31 or
        (fields.get('5'),fields.get('18'),fields.get('48'),fields.get('61'))!=(299,6,10,18156) or
        not pair_preserved(captured,current) or {r.get('id') for r in current}!={4,number}):
        raise RuntimeError('Tame-owned disposable saved pet identity differs')
    named=next(r for r in current if r['id']==4);wolf=next(r for r in current if r['id']==number)
    if (tuple(named.get(k) for k in ('owner','entry','name','renamed','slot','active','CreatedBySpell'))!=
        (6,42717,'Harnesswolf',1,5,0,883) or
        tuple(wolf.get(k) for k in ('owner','entry','name','renamed','slot','active','CreatedBySpell'))!=
        (6,299,'Wolf',0,0,1,13481)):
        raise RuntimeError('only the actually tamed Wolf may be abandoned')
    return number
