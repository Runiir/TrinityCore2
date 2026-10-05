"""Quarantine unreadable screenshot bytes without replaying player input."""
import hashlib
from . import owned_input


def retain_capture_failure(t,label,path,error,frame=None):
    path=path.resolve()
    if not path.is_relative_to(t.out.resolve()):
        raise ValueError('capture failure must belong to this trial')
    records=t.receipt.setdefault('capture_failures',[])
    row=next((r for r in records if r['label']==label and r['error']==str(error)),None)
    if row is None:
        data=path.read_bytes()
        saved=t.out/('capture_failure_'+str(len(records))+'.bin')
        saved.write_bytes(data)
        row={'label':label,'error':str(error),'count':0,'capture_file':saved.name,
            'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
            'monitor':frame.get('monitor') if frame is not None else owned_input.focus(),
            'accepted_as_image':False,'input_replayed':False}
        records.append(row)
    row['count']+=1;t.persist()
    # Never leave malformed PNGs in the set of archive-reviewable images.
    path.unlink()
