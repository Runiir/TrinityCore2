"""Inspect a fresh owned player link before closing either native fixture."""
import argparse
from pathlib import Path
from . import lab_runtime as lab
from .interaction_reply_chat import run
from .interaction_chat_player_menu import live


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--operation',choices=['inspect','copy','report'],default='inspect')
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(lab.ROOT/'evidence'):p.error('requires a private owned evidence output')
    run(out,seed_only=True,after_seed=lambda t,peer,seed:live(t,peer,seed,out/'primary/review.json',a.operation))
