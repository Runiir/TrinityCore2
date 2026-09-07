"""Skill packaging checks, not runtime or agent-behavior certification.

Earlier tests matched exact prose. Those assertions could not demonstrate that
an agent followed instructions and made editing the instructions needlessly
fragile. Check the local resource graph instead; native behavior belongs in
executable policy and runtime fixtures.
"""
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents/skills"
DOCUMENTS = sorted(SKILLS.rglob("*.md"))


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: str(path.relative_to(SKILLS)))
def test_skill_local_markdown_references_resolve(document: Path) -> None:
    for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith(("mailto:", "<")):
            continue
        # Code placeholders describe user-supplied inputs, not packaged files.
        if "<" in target or ">" in target:
            continue
        assert (document.parent / target).exists(), f"{document}: missing {target}"
