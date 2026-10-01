"""Append diagnostic events without request bodies, passwords or tickets."""
import json
import os
import threading
import time

from tools.client_compatibility.lab_runtime import ROOT

LOCK = threading.Lock()


def event(name, **fields):
    allowed = {"session", "method", "service", "status", "build", "mode", "account_id",
               "command", "bytes", "error", "port"}
    if not set(fields) <= allowed:
        raise ValueError("unreviewed diagnostic fields")
    record = {"time": time.time(), "event": name, **fields}
    path = ROOT / "logs/modern_auth.jsonl"
    with LOCK:
        with path.open("a") as handle:
            os.chmod(path, 0o600)
            handle.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)
