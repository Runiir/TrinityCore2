"""Archive analysed live-run evidence through DVC, verify the remote, evict it.

    pixi run python -m experiments.archive_run_evidence \
        --name magmaw_spell_queue_sq1_evidence_20260922 /tmp/run-dir /tmp/extra.log

The evidence is packed into artifacts/cata_raid_program/<name>.tar.gz and
pushed.  The remote bytes are read back and checked against the pointer and
the packed member list before the local archive, its cache object and the
source paths are deleted.  Only paths under /tmp are ever removed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "artifacts" / "cata_raid_program"


def _pack(archive: Path, sources: list[Path]) -> list[str]:
    members = []
    with tarfile.open(archive, "w:gz") as tar:
        for source in sources:
            tar.add(source, arcname=source.name)
    with tarfile.open(archive, "r:gz") as tar:
        members = sorted(member.name for member in tar.getmembers() if member.isfile())
    return members


def _verify_remote(pointer: Path, members: list[str]) -> dict[str, object]:
    import yaml
    from dvc.repo import Repo

    entry, = yaml.safe_load(pointer.read_text())["outs"]
    with Repo(str(ROOT)) as repo, tempfile.TemporaryDirectory(prefix="evidence-verify-") as temp:
        remote = repo.cloud.get_remote_odb()
        path = Path(temp) / "remote.tar.gz"
        md5, sha256, size = hashlib.md5(), hashlib.sha256(), 0
        with remote.fs.open(remote.oid_to_path(entry["md5"]), "rb") as source, path.open("wb") as dest:
            while block := source.read(1024 * 1024):
                md5.update(block)
                sha256.update(block)
                size += len(block)
                dest.write(block)
        if md5.hexdigest() != entry["md5"] or size != entry["size"]:
            raise ValueError("remote bytes differ from the DVC pointer")
        with tarfile.open(path, "r:gz") as tar:
            remote_members = sorted(member.name for member in tar.getmembers() if member.isfile())
        if remote_members != members:
            raise ValueError("remote archive member list differs from the packed evidence")
        return {"remote_md5": entry["md5"], "remote_sha256": sha256.hexdigest(), "archive_bytes": size}


def _evict(pointer: Path, archive: Path) -> None:
    import yaml
    from dvc.repo import Repo

    entry, = yaml.safe_load(pointer.read_text())["outs"]
    archive.unlink(missing_ok=True)
    with Repo(str(ROOT)) as repo:
        Path(repo.cache.local.oid_to_path(entry["md5"])).unlink(missing_ok=True)


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()

    sources = [source.resolve() for source in args.sources]
    for source in sources:
        if not source.exists():
            raise SystemExit(f"missing evidence path: {source}")
        if source.parts[:2] != ("/", "tmp"):
            raise SystemExit(f"refusing to archive and delete a path outside /tmp: {source}")

    archive = DIRECTORY / f"{args.name}.tar.gz"
    pointer = archive.with_name(archive.name + ".dvc")
    if pointer.exists():
        raise SystemExit(f"pointer already exists: {pointer}")
    members = _pack(archive, sources)

    from tools.bot_ml.live_validation_session import dvc_repository_lock

    with dvc_repository_lock(ROOT):
        for command, target in (("add", archive), ("push", pointer)):
            subprocess.run(["pixi", "run", "dvc", command, str(target.relative_to(ROOT))],
                           cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        remote = _verify_remote(pointer, members)
        _evict(pointer, archive)

    evicted = sum(_size(source) for source in sources)
    for source in sources:
        if source.is_dir():
            shutil.rmtree(source)
        else:
            source.unlink()

    receipt = {
        "schema": "cata_evidence_cleanup_v1",
        "dvc_pointer": str(pointer.relative_to(ROOT)),
        "dvc_push_completed": True,
        "remote_verified": True,
        **remote,
        "verified_payload_files": len(members),
        "evicted_temporary_bytes": evicted,
        "exact_archive_and_cache_evicted": not archive.exists(),
        "removed_roots": [str(source) for source in sources],
    }
    receipt_path = DIRECTORY / f"{args.name}.publication.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
