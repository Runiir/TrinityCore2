"""Read positive owned-pet spell visual rows from strictly verified public bytes."""
import argparse,json
from pathlib import Path
from . import lab_runtime as lab
from .client_spell_public_records import records


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=records(args.directory,'SpellXSpellVisual',{3110,6307})
    lab.private_write(args.output,json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
