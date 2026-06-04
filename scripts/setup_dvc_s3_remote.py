#!/usr/bin/env python3
"""Configure the repo DVC remote from environment variables.

Required:
  DVC_S3_URL=s3://bucket/prefix

Optional:
  DVC_S3_ENDPOINT_URL=https://...
  DVC_REMOTE_NAME=object
"""

from __future__ import annotations

import os
import subprocess
import sys


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def main() -> int:
    remote_name = os.environ.get("DVC_REMOTE_NAME", "object")
    remote_url = os.environ.get("DVC_S3_URL")
    endpoint_url = os.environ.get("DVC_S3_ENDPOINT_URL")

    if not remote_url:
        print("DVC_S3_URL is required, for example s3://bucket/trinity-cata", file=sys.stderr)
        return 2

    run(["dvc", "remote", "add", "--force", "-d", remote_name, remote_url])
    if endpoint_url:
        run(["dvc", "remote", "modify", remote_name, "endpointurl", endpoint_url])

    print(f"Configured DVC remote {remote_name!r} -> {remote_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
