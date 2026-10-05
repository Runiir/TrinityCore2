#!/usr/bin/env bash
# Only tcpdump receives sudo privileges; parsing and mailbox writes stay unprivileged.
set -euo pipefail
whitemane_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "$whitemane_repo"
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml \
    python -m tools.live_whitemane.bearing_scope
pixi install --manifest-path tools/live_whitemane/packet/pixi.toml
echo "Enter your sudo password here. Only the endpoint capture runs as root."
echo "Stops after 30 minutes without Survey, gathering, spell casts or player movement."
echo "Raw packets stay in the pipe. Ctrl+C stops capture and clears the bearing mailbox."
sudo /usr/bin/tcpdump \
    -npi any -B 1024 -U -s 0 -w - 'host 51.255.74.57 and tcp port 8085' | \
    pixi run --manifest-path tools/live_whitemane/packet/pixi.toml \
    python -m tools.live_whitemane.bearing_reader
