import subprocess
from . import runtime


def test_public_fare_policy_and_bounded_capture():
    subprocess.run(['lua','tools/live_whitemane/test_fare_routes.lua'],cwd=runtime.REPO,check=True)


def test_public_environment_unknown_and_false_are_distinct():
    subprocess.run(['lua','tools/live_whitemane/test_environment_facts.lua'],cwd=runtime.REPO,check=True)
