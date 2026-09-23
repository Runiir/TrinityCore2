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
SKILL_FILES = sorted(SKILLS.glob("*/SKILL.md"))
LEDGER_DOCUMENTS = [ROOT / "docs/bot_raids/error_ledger.md", ROOT / "docs/bot_raids/archive/error_ledger_closed.md"]


def _assert_local_links_resolve(document: Path) -> None:
    for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith(("mailto:", "<")):
            continue
        # Code placeholders describe user-supplied inputs, not packaged files.
        if "<" in target or ">" in target:
            continue
        assert (document.parent / target).exists(), f"{document}: missing {target}"


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: str(path.relative_to(SKILLS)))
def test_skill_local_markdown_references_resolve(document: Path) -> None:
    _assert_local_links_resolve(document)


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda path: path.parent.name)
def test_skill_frontmatter_names_its_directory(skill: Path) -> None:
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---\n"), skill
    frontmatter = text.split("---\n", 2)[1]
    assert re.search(rf"^name: {re.escape(skill.parent.name)}$", frontmatter, re.M), skill
    assert re.search(r"^description: \S", frontmatter, re.M), skill


def test_agents_skill_paths_exist() -> None:
    for path in re.findall(r"\.agents/skills/[\w./-]+\.md", (ROOT / "AGENTS.md").read_text(encoding="utf-8")):
        assert (ROOT / path).is_file(), path


@pytest.mark.parametrize("document", LEDGER_DOCUMENTS, ids=lambda path: path.name)
def test_error_ledger_links_resolve(document: Path) -> None:
    _assert_local_links_resolve(document)
