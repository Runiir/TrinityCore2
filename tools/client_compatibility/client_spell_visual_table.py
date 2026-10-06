"""Extract the installed60895 public SpellXSpellVisual table with strict CASC checks.

Layout01147920 is explicitly listed for4.4.2.60895 in wowdev/WoWDBDefs:
https://github.com/wowdev/WoWDBDefs/blob/master/definitions/SpellXSpellVisual.dbd
The extraction preserves verified plaintext bytes only. It does not select a
visual or infer missing/encrypted records, and does not download client data.
"""
import argparse
from pathlib import Path
from .client_spell_tables import extract_tables

LAYOUT = 0x01147920


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    extract_tables(args.directory, {'SpellXSpellVisual': LAYOUT})
